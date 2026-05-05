"""Public display routes: the TV view and its state endpoint."""
from __future__ import annotations

from flask import Blueprint, abort, jsonify, render_template, send_file, url_for

from . import IMAGES_DIR, STYLE_CATEGORIES
from .images import resolve_logo_path
from .models import state_snapshot

bp = Blueprint("display", __name__)


@bp.route("/")
def display():
    snap = state_snapshot()
    settings = snap["settings"]
    by_category: dict[str, list[dict]] = {c: [] for c in STYLE_CATEGORIES}
    for tap in snap["taps"]:
        cat = tap.get("style_category") or "Historical & Specialty"
        if cat not in by_category:
            by_category[cat] = []
        rel = resolve_logo_path(tap, settings)
        tap["logo_url"] = url_for("serve_data_image", relpath=rel) if rel else url_for("static", filename="img/hop-fallback.svg")
        by_category[cat].append(tap)

    grouped = [(cat, by_category[cat]) for cat in STYLE_CATEGORIES if by_category.get(cat)]

    return render_template(
        "display.html",
        settings=settings,
        grouped=grouped,
        specials=snap["specials"],
        version_hash=snap["version_hash"],
    )


@bp.route("/api/state")
def api_state():
    snap = state_snapshot()
    settings = snap["settings"]
    for tap in snap["taps"]:
        rel = resolve_logo_path(tap, settings)
        tap["logo_url"] = url_for("serve_data_image", relpath=rel) if rel else url_for("static", filename="img/hop-fallback.svg")
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
