"""Upload normalization and fallback resolution for tap imagery."""
from __future__ import annotations

import secrets
from pathlib import Path

from PIL import Image
from werkzeug.datastructures import FileStorage

from . import UPLOADS_DIR
from .internetscraping import get_cached_brewery_logo

ALLOWED_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
MAX_DIMENSION = 512


def save_upload(file: FileStorage) -> str | None:
    """Persist an uploaded image, resized down to MAX_DIMENSION. Returns relative path."""
    if not file or not file.filename:
        return None
    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_EXTS:
        return None

    token = secrets.token_hex(8)
    out_path = UPLOADS_DIR / f"{token}{ext}"

    try:
        img = Image.open(file.stream)
        img.thumbnail((MAX_DIMENSION, MAX_DIMENSION))
        img.save(out_path)
    except (OSError, ValueError):
        return None

    return str(Path("uploads") / out_path.name).replace("\\", "/")


def resolve_logo_path(tap: dict, settings: dict) -> str | None:
    """
    Apply the FR4 fallback chain. Returns a path relative to data/images/,
    suitable for the /data-image/<path> URL, or None if nothing is available
    (caller should then use the bundled hop fallback).
    """
    if tap.get("image_override_path"):
        return tap["image_override_path"]

    brewery = (tap.get("brewery") or "").strip()
    home_brewery = (settings.get("home_brewery") or "").strip()
    home_logo = settings.get("home_brewery_logo_path")
    if brewery and home_brewery and brewery.lower() == home_brewery.lower() and home_logo:
        return home_logo

    cached = get_cached_brewery_logo(brewery)
    if cached:
        return cached

    return None
