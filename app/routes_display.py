"""Public display routes: the TV view and its state endpoint."""
from __future__ import annotations

import io

import qrcode
import qrcode.image.svg
from flask import Blueprint, Response, abort, jsonify, render_template, request, send_file, url_for

from . import IMAGES_DIR, STYLE_CATEGORIES, THEME_HOP_FALLBACK
from .holidays import active_holiday
from .images import resolve_logo_path
from .models import state_snapshot

bp = Blueprint("display", __name__)


def _hop_fallback_url(theme: str | None) -> str:
    """Per-theme hop SVG URL. Falls back to the original green hop."""
    asset = THEME_HOP_FALLBACK.get(theme or "", "img/hop-fallback.svg")
    return url_for("static", filename=asset)


def _resolve_tap_logo_url(tap: dict, settings: dict, hop_fallback_url: str) -> str:
    """Resolve a tap's logo URL with the home-brewery fallback chain:

    1. Per-tap override / user-uploaded brewery logo / cached Untappd logo
       (whatever ``resolve_logo_path`` returns).
    2. If the tap is the home brewery and no upload exists, use the bundled
       palindrome-logo.png static asset.
    3. Otherwise, the theme's hop fallback.
    """
    rel = resolve_logo_path(tap, settings)
    if rel:
        return url_for("serve_data_image", relpath=rel)

    brewery = (tap.get("brewery") or "").strip().lower()
    home_brewery = (settings.get("home_brewery") or "").strip().lower()
    if brewery and home_brewery and brewery == home_brewery:
        return url_for("static", filename="img/palindrome-logo.svg")

    return hop_fallback_url


def _build_groups(taps: list[dict], settings: dict) -> list[tuple[str, list[dict]]]:
    """Group taps for the display according to settings.tap_order_mode.

    Returns a list of (label, taps) pairs. The template renders each group
    as a heading-less block by default; a group whose label starts with
    '__sep:' becomes a visual separator on the page instead of a tap list.
    """
    mode = (settings.get("tap_order_mode") or "style_category").strip()

    if mode == "tap_number":
        return [("", sorted(taps, key=lambda t: t.get("tap_number") or 0))]

    if mode == "home_first":
        home_name = (settings.get("home_brewery") or "").strip().lower()
        home, guests = [], []
        for tap in taps:
            tap_brewery = (tap.get("brewery") or "").strip().lower()
            if home_name and tap_brewery == home_name:
                home.append(tap)
            else:
                guests.append(tap)
        home.sort(key=lambda t: t.get("tap_number") or 0)
        guests.sort(key=lambda t: t.get("tap_number") or 0)
        groups: list[tuple[str, list[dict]]] = []
        if home:
            groups.append(("", home))
        if guests:
            groups.append(("__sep:Guest Beers", []))
            groups.append(("", guests))
        # Fall back to a flat list if no home brewery match (avoids empty page).
        if not home and guests:
            return [("", guests)]
        return groups

    # Default: group by style category (legacy behaviour).
    by_category: dict[str, list[dict]] = {c: [] for c in STYLE_CATEGORIES}
    for tap in taps:
        cat = tap.get("style_category") or "Historical & Specialty"
        if cat not in by_category:
            by_category[cat] = []
        by_category[cat].append(tap)
    return [(cat, by_category[cat]) for cat in STYLE_CATEGORIES if by_category.get(cat)]


@bp.route("/")
def display():
    snap = state_snapshot()
    settings = snap["settings"]
    fallback = _hop_fallback_url(settings.get("theme"))
    for tap in snap["taps"]:
        tap["logo_url"] = _resolve_tap_logo_url(tap, settings, fallback)

    grouped = _build_groups(snap["taps"], settings)

    holiday = active_holiday() if settings.get("holiday_fun_enabled") else None
    # Debug/preview override: ?holiday=xmas forces the icon to render today.
    # Only honoured when holiday_fun_enabled is on so a stuck URL can't bypass the toggle.
    override = request.args.get("holiday")
    if override and settings.get("holiday_fun_enabled"):
        from .holidays import HOLIDAY_LABELS
        if override in HOLIDAY_LABELS:
            holiday = override

    return render_template(
        "display.html",
        settings=settings,
        grouped=grouped,
        specials=snap["specials"],
        events=snap["events"],
        version_hash=snap["version_hash"],
        fallback_logo_url=fallback,
        holiday=holiday,
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
        tap["logo_url"] = _resolve_tap_logo_url(tap, settings, fallback)
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
