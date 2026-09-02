"""Media pipeline: download from Bale, hash, store via the Storage interface.

The default backend writes files under MEDIA_ROOT on the local disk.
STORAGE_BACKEND=s3 switches to the S3 implementation without changing callers.
Files larger than the download cap stay in the Bale archive chat only.
"""

from __future__ import annotations

import hashlib
import os
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from app.bale.errors import BadRequest, BaleAPIError, NetworkError
from app.bale.methods import BaleAPI
from app.db.models import MediaFile, StorageStatus
from app.observability.logging import get_logger

logger = get_logger(__name__)


class Storage(Protocol):
    """Abstract file store. Local now; S3 later via STORAGE_BACKEND."""

    async def put(self, key: str, data: bytes, content_type: str) -> str:
        """Persist ``data`` under ``key`` and return the stored identifier."""


class LocalStorage:
    """Write files under a local MEDIA_ROOT directory using pathlib."""

    def __init__(self, root: Path) -> None:
        self._root = root
        self._root.mkdir(parents=True, exist_ok=True)

    def _destination(self, key: str) -> Path:
        parts = [part for part in Path(key).parts if part not in ("", ".", "..")]
        dest = self._root.joinpath(*parts).resolve()
        root = self._root.resolve()
        if not dest.is_relative_to(root):
            msg = "storage key escapes MEDIA_ROOT"
            raise ValueError(msg)
        return dest

    async def put(self, key: str, data: bytes, content_type: str) -> str:
        dest = self._destination(key)
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_name(dest.name + ".tmp")
        try:
            with tmp.open("wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            tmp.replace(dest)
        finally:
            if tmp.exists() and tmp != dest:
                try:
                    tmp.unlink()
                except OSError as exc:
                    logger.warning("temp_file_unlink_failed", path=str(tmp), error=str(exc))
        return str(dest)


class S3Storage:
    """Optional S3 backend, loaded only when STORAGE_BACKEND=s3."""

    def __init__(self, endpoint_url: str, access_key: str, secret_key: str, bucket: str) -> None:
        self._endpoint = endpoint_url
        self._access_key = access_key
        self._secret_key = secret_key
        self._bucket = bucket

    async def put(self, key: str, data: bytes, content_type: str) -> str:
        import aioboto3
        from botocore.config import Config

        session = aioboto3.Session()
        config = Config(
            s3={"addressing_style": "path"},
            retries={"max_attempts": 5, "mode": "adaptive"},
            connect_timeout=10,
            read_timeout=60,
        )
        async with session.client(
            "s3",
            endpoint_url=self._endpoint,
            aws_access_key_id=self._access_key,
            aws_secret_access_key=self._secret_key,
            region_name="",
            config=config,
        ) as client:
            await client.put_object(
                Bucket=self._bucket, Key=key, Body=data, ContentType=content_type
            )
        return key


@dataclass(slots=True)
class MediaProcessResult:
    status: StorageStatus
    sha256: str | None = None
    storage_key: str | None = None
    error: str | None = None
    duplicate_of_media_id: int | None = None


def storage_key_for(media: MediaFile) -> str:
    """Short relative key: two-char prefix + uuid. Never uses user filenames."""
    name = uuid.uuid4().hex
    suffix = ""
    if media.file_name:
        candidate = Path(media.file_name).suffix.lower()
        token = candidate[1:] if candidate.startswith(".") else candidate
        if token.isalnum() and len(token) <= 8:
            suffix = "." + token
    return str(Path(name[:2]) / f"{name}{suffix}")


async def process_media_file(
    api: BaleAPI,
    storage: Storage | None,
    media: MediaFile,
    max_download_bytes: int,
) -> MediaProcessResult:
    """Download one media file, hash it and store it. Always closes file handles."""
    if media.file_size_bytes is not None and media.file_size_bytes > max_download_bytes:
        logger.info("media_too_large_for_download", media_id=media.id, size=media.file_size_bytes)
        return MediaProcessResult(status=StorageStatus.SKIPPED_TOO_LARGE)

    try:
        file_info = await api.get_file(media.bale_file_id)
    except (BaleAPIError, NetworkError) as exc:
        return MediaProcessResult(status=StorageStatus.FAILED, error=str(exc))

    if file_info.file_size is not None and file_info.file_size > max_download_bytes:
        return MediaProcessResult(status=StorageStatus.SKIPPED_TOO_LARGE)
    if not file_info.file_path:
        return MediaProcessResult(status=StorageStatus.FAILED, error="missing file_path")

    try:
        data = await api.client.download_file(file_info.file_path, max_download_bytes)
    except BadRequest as exc:
        if exc.error_code == 413:
            return MediaProcessResult(status=StorageStatus.SKIPPED_TOO_LARGE)
        return MediaProcessResult(status=StorageStatus.FAILED, error=str(exc))
    except (BaleAPIError, NetworkError) as exc:
        return MediaProcessResult(status=StorageStatus.FAILED, error=str(exc))

    sha256 = hashlib.sha256(data).hexdigest()

    if storage is None:
        return MediaProcessResult(status=StorageStatus.STORED, sha256=sha256)

    key = storage_key_for(media)
    try:
        stored = await storage.put(key, data, media.mime_type or "application/octet-stream")
    except (ConnectionError, OSError, TimeoutError, ValueError) as exc:
        return MediaProcessResult(status=StorageStatus.FAILED, sha256=sha256, error=str(exc))
    except Exception as exc:
        if type(exc).__module__.startswith(("botocore", "boto3", "aioboto3", "aiohttp")):
            return MediaProcessResult(status=StorageStatus.FAILED, sha256=sha256, error=str(exc))
        raise
    return MediaProcessResult(status=StorageStatus.STORED, sha256=sha256, storage_key=stored)
