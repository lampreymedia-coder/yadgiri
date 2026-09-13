"""Media pipeline: download from Bale, hash, compress videos, store via Storage.

The default backend writes files under MEDIA_ROOT on the local disk.
STORAGE_BACKEND=s3 switches to the S3 implementation without changing callers.
Files larger than the download cap stay in the Bale archive chat only.

Deduplication by sha256 happens *before* ``put`` so duplicate bytes are never
written. Video compression runs only in the media worker backlog.
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
from app.domain.video_compress import compress_video, is_video_media
from app.observability.logging import get_logger

logger = get_logger(__name__)


class Storage(Protocol):
    """Abstract file store. Local now; S3 later via STORAGE_BACKEND."""

    async def put(self, key: str, data: bytes, content_type: str) -> str:
        """Persist ``data`` under ``key`` and return the stored identifier."""

    async def delete(self, key: str) -> None:
        """Best-effort delete of a previously stored object."""


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

    async def delete(self, key: str) -> None:
        try:
            dest = self._destination(key)
        except ValueError:
            return
        try:
            if dest.is_file():
                dest.unlink()
        except OSError as exc:
            logger.warning("storage_delete_failed", path=str(dest), error=str(exc))


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

    async def delete(self, key: str) -> None:
        import aioboto3
        from botocore.config import Config

        session = aioboto3.Session()
        config = Config(
            s3={"addressing_style": "path"},
            retries={"max_attempts": 3, "mode": "adaptive"},
            connect_timeout=10,
            read_timeout=30,
        )
        try:
            async with session.client(
                "s3",
                endpoint_url=self._endpoint,
                aws_access_key_id=self._access_key,
                aws_secret_access_key=self._secret_key,
                region_name="",
                config=config,
            ) as client:
                await client.delete_object(Bucket=self._bucket, Key=key)
        except Exception as exc:
            if type(exc).__module__.startswith(("botocore", "boto3", "aioboto3", "aiohttp")):
                logger.warning("s3_delete_failed", key=key, error=str(exc))
                return
            raise


@dataclass(slots=True)
class MediaProcessResult:
    status: StorageStatus
    sha256: str | None = None
    storage_key: str | None = None
    error: str | None = None
    duplicate_of_media_id: int | None = None
    original_size_bytes: int | None = None
    stored_size_bytes: int | None = None
    is_compressed: bool = False
    # Populated when status is STORED and bytes still need a Storage.put.
    payload: bytes | None = None


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


@dataclass(slots=True, frozen=True)
class VideoCompressionSettings:
    enabled: bool = True
    crf: int = 24
    max_height: int = 720
    audio_bitrate: str = "96k"
    keep_original: bool = False


async def prepare_media_bytes(
    api: BaleAPI,
    media: MediaFile,
    max_download_bytes: int,
    compression: VideoCompressionSettings | None = None,
) -> MediaProcessResult:
    """Download one media file, hash it, optionally compress video.

    Does **not** write to Storage — the worker checks sha256 dedup first.
    """
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

    original_size = len(data)
    sha256 = hashlib.sha256(data).hexdigest()
    is_compressed = False
    settings = compression or VideoCompressionSettings(enabled=False)

    if (
        settings.enabled
        and is_video_media(mime_type=media.mime_type, file_name=media.file_name)
    ):
        result = await compress_video(
            data,
            crf=settings.crf,
            max_height=settings.max_height,
            audio_bitrate=settings.audio_bitrate,
        )
        if result.used_compressed:
            data = result.data
            is_compressed = True
            # keep_original is reserved for future dual-file storage; default
            # false means we only keep the compressed payload on disk.
            _ = settings.keep_original

    return MediaProcessResult(
        status=StorageStatus.STORED,
        sha256=sha256,
        original_size_bytes=original_size,
        stored_size_bytes=len(data),
        is_compressed=is_compressed,
        payload=data,
    )


async def process_media_file(
    api: BaleAPI,
    storage: Storage | None,
    media: MediaFile,
    max_download_bytes: int,
    compression: VideoCompressionSettings | None = None,
) -> MediaProcessResult:
    """Download, prepare, and optionally store when no external dedup is needed.

    Prefer the worker path that calls ``prepare_media_bytes`` then dedupes
    before ``put``. This helper remains for simple callers/tests.
    """
    prepared = await prepare_media_bytes(api, media, max_download_bytes, compression)
    if prepared.status is not StorageStatus.STORED or prepared.payload is None:
        return prepared
    if storage is None:
        prepared.payload = None
        return prepared
    key = storage_key_for(media)
    try:
        stored = await storage.put(
            key, prepared.payload, media.mime_type or "application/octet-stream"
        )
    except (ConnectionError, OSError, TimeoutError, ValueError) as exc:
        return MediaProcessResult(
            status=StorageStatus.FAILED,
            sha256=prepared.sha256,
            error=str(exc),
            original_size_bytes=prepared.original_size_bytes,
            stored_size_bytes=prepared.stored_size_bytes,
            is_compressed=prepared.is_compressed,
        )
    except Exception as exc:
        if type(exc).__module__.startswith(("botocore", "boto3", "aioboto3", "aiohttp")):
            return MediaProcessResult(
                status=StorageStatus.FAILED,
                sha256=prepared.sha256,
                error=str(exc),
                original_size_bytes=prepared.original_size_bytes,
                stored_size_bytes=prepared.stored_size_bytes,
                is_compressed=prepared.is_compressed,
            )
        raise
    prepared.storage_key = stored
    prepared.payload = None
    return prepared
