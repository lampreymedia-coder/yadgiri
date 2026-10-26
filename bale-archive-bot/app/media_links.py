"""Signed links to stored files: view (/m/<id>/<sig>) and manual upload (/u/<id>/<sig>).

sig = first 32 hex chars of HMAC-SHA256(MEDIA_LINK_SECRET, "<kind>:<media_id>").
Every place that shows a file link (Excel, panel, admin notices) uses
:func:`build_media_url` / :func:`build_upload_url`.
"""

from __future__ import annotations

import hashlib
import hmac

from app.config import Settings, get_settings

VIEW = "view"
UPLOAD = "upload"


def sign(kind: str, media_id: int, secret: str) -> str:
    message = f"{kind}:{int(media_id)}".encode()
    return hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()[:32]


def verify(kind: str, media_id: int, sig: str, secret: str) -> bool:
    if not secret or not sig:
        return False
    return hmac.compare_digest(sign(kind, media_id, secret), sig)


def _settings(settings: Settings | None) -> Settings:
    return settings if settings is not None else get_settings()


def build_media_url(media_id: int, settings: Settings | None = None) -> str:
    cfg = _settings(settings)
    base = cfg.media_public_base.rstrip("/")
    return f"{base}/m/{int(media_id)}/{sign(VIEW, media_id, cfg.media_link_secret)}"


def build_upload_url(media_id: int, settings: Settings | None = None) -> str:
    cfg = _settings(settings)
    base = cfg.media_public_base.rstrip("/")
    return f"{base}/u/{int(media_id)}/{sign(UPLOAD, media_id, cfg.media_link_secret)}"


def parse_bale_ref(storage_path: str) -> tuple[int, int] | None:
    """'bale:<chat>/<message>' → (chat, message)."""
    if not storage_path.startswith("bale:"):
        return None
    chat, _, message = storage_path[5:].partition("/")
    try:
        return int(chat), int(message)
    except ValueError:
        return None
