"""Media pipeline: download from Bale (≤20MB), hash, upload to object storage.

Files between 20MB and 50MB cannot be downloaded by bots at all — for those
the archive-channel copy is the retention layer and the media row is marked
``skipped_too_large``.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from typing import Protocol

from app.bale.errors import BadRequest, BaleAPIError, NetworkError
from app.bale.methods import BaleAPI
from app.db.models import MediaFile, StorageStatus
from app.observability.logging import get_logger

logger = get_logger(__name__)


class ObjectStorage(Protocol):
    """Minimal storage interface (implemented by S3Storage and test fakes)."""

    async def put(self, bucket: str, key: str, data: bytes, content_type: str) -> None: ...


class S3Storage:
    """Arvan object storage via aioboto3 (path-style, region empty)."""

    def __init__(self, endpoint_url: str, access_key: str, secret_key: str) -> None:
        self._endpoint = endpoint_url
        self._access_key = access_key
        self._secret_key = secret_key

    async def put(self, bucket: str, key: str, data: bytes, content_type: str) -> None:
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
            await client.put_object(Bucket=bucket, Key=key, Body=data, ContentType=content_type)


@dataclass(slots=True)
class MediaProcessResult:
    status: StorageStatus
    sha256: str | None = None
    storage_key: str | None = None
    error: str | None = None
    duplicate_of_media_id: int | None = None


def storage_key_for(media: MediaFile) -> str:
    """Object keys are UUID-based — never derived from user-provided names."""
    extension = ""
    if media.file_name and "." in media.file_name:
        candidate = media.file_name.rsplit(".", 1)[-1].lower()
        if candidate.isalnum() and len(candidate) <= 8:
            extension = f".{candidate}"
    return f"media/{uuid.uuid4().hex}{extension}"


async def process_media_file(
    api: BaleAPI,
    storage: ObjectStorage | None,
    media: MediaFile,
    bucket: str,
    max_download_bytes: int,
    find_duplicate_sha: str | None = None,
) -> MediaProcessResult:
    """Download one media file, hash it and upload it to object storage."""
    if media.file_size_bytes is not None and media.file_size_bytes > max_download_bytes:
        logger.info(
            "media_too_large_for_download",
            media_id=media.id,
            size=media.file_size_bytes,
        )
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
        # file_path links expire after one hour; we download immediately.
        data = await api.client.download_file(file_info.file_path, max_download_bytes)
    except BadRequest as exc:
        if exc.error_code == 413:
            return MediaProcessResult(status=StorageStatus.SKIPPED_TOO_LARGE)
        return MediaProcessResult(status=StorageStatus.FAILED, error=str(exc))
    except (BaleAPIError, NetworkError) as exc:
        return MediaProcessResult(status=StorageStatus.FAILED, error=str(exc))

    sha256 = hashlib.sha256(data).hexdigest()

    if storage is None:
        # Storage disabled: hashing still enables duplicate detection; the
        # archive-channel message remains the retention layer.
        return MediaProcessResult(status=StorageStatus.STORED, sha256=sha256)

    key = storage_key_for(media)
    try:
        await storage.put(bucket, key, data, media.mime_type or "application/octet-stream")
    except (ConnectionError, OSError, TimeoutError) as exc:
        return MediaProcessResult(status=StorageStatus.FAILED, sha256=sha256, error=str(exc))
    except Exception as exc:  # botocore raises dynamic exception classes
        if type(exc).__module__.startswith(("botocore", "boto3", "aioboto3", "aiohttp")):
            return MediaProcessResult(status=StorageStatus.FAILED, sha256=sha256, error=str(exc))
        raise

    return MediaProcessResult(status=StorageStatus.STORED, sha256=sha256, storage_key=key)
