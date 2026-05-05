"""Public display routes: the TV view and its state endpoint."""
from __future__ import annotations

import io

import qrcode
import qrcode.image.svg
from flask import Blueprint, Response, abort, jsonify, render_template, request, send_file, url_for

from . import IMAGES_DIR, STYLE_CATEGORIES, THEME_HOP_FALLBACK
from .images import resolve_logo_path
from .models import state_snapshot

bp = Blueprint("display", __name__)


def _hop_fallback_url(theme: str | None) -> str:
    """Per-theme hop SVG URL. Falls back to the original green hop."""
    asset = THEME_HOP_FALLBACK.get(theme or "", "img/hop-fallback.svg")
    return url_for("static", filename=asset)


@bp.route("/")
def display():
    snap = state_snapshot()
    settings = snap["settings"]
    fallback = _hop_fallback_url(settings.get("theme"))
    by_category: dict[str, list[dict]] = {c: [] for c in STYLE_CATEGORIES}
    for tap in snap["taps"]:
        cat = tap.get("style_category") or "Historical & Specialty"
        if cat not in by_category:
            by_category[cat] = []
        rel = resolve_logo_path(tap, settings)
        tap["logo_url"] = url_for("serve_data_image", relpath=rel) if rel else fallback
        by_category[cat].append(tap)

    grouped = [(cat, by_category[cat]) for cat in STYLE_CATEGORIES if by_category.get(cat)]

    return render_template(
        "display.html",
        settings=settings,
        grouped=grouped,
        specials=snap["specials"],
        events=snap["events"],
        version_hash=snap["version_hash"],
        fallback_logo_url=fallback,
    )


@bp.route("/qr")
def qr_code():
    """Render a URL as an SVG QR code. Used by the events panel on the TV."""
    data = (request.args.get("data") or "").strip()
    if not data:
        abort(400)
    factory = qrcode.image.svg.SvgPathImage
    img = qrcode.make(data, image_factory=factory, box_size=10, border=2)
    buf = io.BytesIO()
    img.save(buf)
    return Response(buf.getvalue(), mimetype="image/svg+xml",
                    headers={"Cache-Control": "public, max-age=3600"})


@bp.route("/api/state")
def api_state():
    snap = state_snapshot()
    settings = snap["settings"]
    fallback = _hop_fallback_url(settings.get("theme"))
    for tap in snap["taps"]:
        rel = resolve_logo_path(tap, settings)
        tap["logo_url"] = url_for("serve_data_image", relpath=rel) if rel else fallback
    for ev in snap.get("events", []):
        ev["qr_url"] = url_for("display.qr_code", data=ev["url"]) if ev.get("url") else None
    snap["fallback_logo_url"] = fallback
    return jsonify(snap)


def serve_data_image(relpath: str):
    """Serves files under data/images/ via /data-image/<relpath>."""
    safe_root = IMAGES_DIR.resolve()
    target = (safe_root / relpath).resolve()
    try:
        target.relative_to(safe_root)
    except ValueError:
        abort(404)
    if not target.is_file():
        abort(404)
    return send_file(target)
