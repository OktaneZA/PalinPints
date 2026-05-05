"""Admin web UI routes."""
from __future__ import annotations

from flask import Blueprint, flash, jsonify, redirect, render_template, request, url_for

from . import STYLE_CATEGORIES, STYLE_SUBSTYLES
from .images import save_upload
from .sun import auto_detect_location
from .models import (
    EVENT_LIMIT,
    add_event,
    add_special,
    clear_tap,
    delete_event,
    delete_special,
    get_settings,
    get_tap,
    list_events,
    list_specials,
    list_taps,
    update_event,
    update_special,
    update_tap,
    update_settings,
)

bp = Blueprint("admin", __name__, url_prefix="/admin")


def _to_float(v: str | None) -> float | None:
    if v is None or v.strip() == "":
        return None
    try:
        return float(v)
    except ValueError:
        return None


def _to_int(v: str | None) -> int | None:
    if v is None or v.strip() == "":
        return None
    try:
        return int(float(v))
    except ValueError:
        return None


@bp.route("/")
def index():
    return redirect(url_for("admin.taps"))


@bp.route("/taps", methods=["GET"])
def taps():
    settings = get_settings()
    return render_template(
        "admin/taps.html",
        taps=list_taps(),
        settings=settings,
        categories=STYLE_CATEGORIES,
        substyles=STYLE_SUBSTYLES,
    )


PRICE_KINDS = ("third", "half", "pint", "takeaway")


@bp.route("/taps/<int:tap_number>", methods=["POST"])
def save_tap(tap_number: int):
    if not get_tap(tap_number):
        return ("not found", 404)

    f = request.form
    image_path = None
    if "image" in request.files:
        image_path = save_upload(request.files["image"])

    active = 1 if f.get("active") else 0
    brewery = (f.get("brewery") or "").strip() or None
    beer_name = (f.get("beer_name") or "").strip() or None
    abv = _to_float(f.get("abv"))

    prices: dict[str, float | None] = {}
    enabled: dict[str, int] = {}
    for kind in PRICE_KINDS:
        prices[kind] = _to_float(f.get(f"price_{kind}"))
        enabled[kind] = 1 if f.get(f"price_{kind}_enabled") else 0
    any_priced = any(enabled[k] and prices[k] is not None for k in PRICE_KINDS)

    if active:
        missing = []
        if not brewery: missing.append("brewery")
        if not beer_name: missing.append("beer name")
        if abv is None: missing.append("ABV %")
        if not any_priced: missing.append("at least one enabled price")
        if missing:
            flash(
                f"Tap {tap_number} not saved — missing required field(s): "
                + ", ".join(missing) + ".",
                "error",
            )
            return redirect(url_for("admin.taps"))

    values = {
        "active": active,
        "brewery": brewery,
        "beer_name": beer_name,
        "style_category": f.get("style_category") or None,
        "sub_style": (f.get("sub_style") or "").strip() or None,
        "abv": abv,
        "ibu": _to_int(f.get("ibu")),
        "location": (f.get("location") or "").strip() or None,
        "color_override": (f.get("color_override") or None) if f.get("use_color_override") else None,
        "untappd_slug": f.get("untappd_slug") or None,
    }
    for kind in PRICE_KINDS:
        values[f"price_{kind}"] = prices[kind]
        values[f"price_{kind}_enabled"] = enabled[kind]
    if image_path:
        values["image_override_path"] = image_path
    elif f.get("clear_image"):
        values["image_override_path"] = None

    update_tap(tap_number, values)
    flash(f"Tap {tap_number} saved.", "success")
    return redirect(url_for("admin.taps"))


@bp.route("/taps/<int:tap_number>/clear", methods=["POST"])
def clear(tap_number: int):
    clear_tap(tap_number)
    flash(f"Tap {tap_number} cleared.", "success")
    return redirect(url_for("admin.taps"))


_ALLOWED_THEMES = {"marble", "neon", "chalkboard", "palindrome1", "palindrome2", "palindrome3"}


def _normalise_theme(value: str | None, fallback: str = "marble") -> str:
    return value if value in _ALLOWED_THEMES else fallback


def _normalise_hhmm(value: str | None) -> str | None:
    """Accept HH:MM or HH:MM:SS, normalise to HH:MM. None for blank/invalid."""
    if not value:
        return None
    parts = value.strip().split(":")
    if len(parts) < 2:
        return None
    try:
        h, m = int(parts[0]), int(parts[1])
    except ValueError:
        return None
    if not (0 <= h < 24 and 0 <= m < 60):
        return None
    return f"{h:02d}:{m:02d}"


@bp.route("/settings", methods=["GET", "POST"])
def settings():
    if request.method == "POST":
        f = request.form
        day_theme = _normalise_theme(f.get("day_theme"))
        night_theme = _normalise_theme(f.get("night_theme"), fallback="neon")

        lat = _to_float(f.get("latitude"))
        lon = _to_float(f.get("longitude"))
        latitude = lat if lat is not None and -90 <= lat <= 90 else None
        longitude = lon if lon is not None and -180 <= lon <= 180 else None

        existing = get_settings()
        values = {
            "home_brewery": f.get("home_brewery") or "Palindrome Brewing Co",
            "display_style": "color" if f.get("display_style") == "color" else "logo",
            "day_theme": day_theme,
            "night_theme": night_theme,
            # Keep the legacy `theme` column in sync with the day theme so any
            # consumer still reading it (or a stale state cache) stays valid.
            "theme": day_theme,
            "latitude": latitude,
            "longitude": longitude,
            "override_day_start": _normalise_hhmm(f.get("override_day_start")),
            "override_night_start": _normalise_hhmm(f.get("override_night_start")),
            "beers_per_page": max(6, min(14, _to_int(f.get("beers_per_page")) or 12)),
            "page_rotation_interval": max(5, min(120, _to_int(f.get("page_rotation_interval")) or 15)),
            "color_ipa": f.get("color_ipa"),
            "color_sour": f.get("color_sour"),
            "color_stout": f.get("color_stout"),
            "color_lager": f.get("color_lager"),
            "color_belgian": f.get("color_belgian"),
            "color_specialty": f.get("color_specialty"),
        }
        # Force a fresh sunset lookup on the next state poll if the user
        # changed the coordinates. Saves them having to wait a week.
        if (existing.get("latitude") != latitude
                or existing.get("longitude") != longitude):
            values["cache_fetched_at"] = None
        if "home_brewery_logo" in request.files:
            uploaded = save_upload(request.files["home_brewery_logo"])
            if uploaded:
                values["home_brewery_logo_path"] = uploaded
        update_settings(values)
        flash("Settings saved.", "success")
        return redirect(url_for("admin.settings"))

    return render_template("admin/settings.html", settings=get_settings(), categories=STYLE_CATEGORIES)


@bp.route("/api/geolocate", methods=["GET"])
def geolocate():
    """Best-effort IP-based lat/lon for the auto-detect button."""
    coords = auto_detect_location()
    if coords is None:
        return jsonify({"error": "lookup failed"}), 502
    return jsonify({"latitude": coords[0], "longitude": coords[1]})


@bp.route("/specials", methods=["GET", "POST"])
def specials():
    if request.method == "POST":
        title = (request.form.get("title") or "").strip()
        description = (request.form.get("description") or "").strip() or None
        price = _to_float(request.form.get("price"))
        active = 1 if request.form.get("active") else 0
        if title:
            add_special(title, description, price, active)
            flash("Special added.", "success")
        return redirect(url_for("admin.specials"))
    return render_template("admin/specials.html", specials=list_specials())


@bp.route("/specials/<int:special_id>/update", methods=["POST"])
def update_special_route(special_id: int):
    title = (request.form.get("title") or "").strip()
    description = (request.form.get("description") or "").strip() or None
    price = _to_float(request.form.get("price"))
    active = 1 if request.form.get("active") else 0
    if title:
        update_special(special_id, title, description, price, active)
        flash("Special updated.", "success")
    return redirect(url_for("admin.specials"))


@bp.route("/specials/<int:special_id>/delete", methods=["POST"])
def delete_special_route(special_id: int):
    delete_special(special_id)
    flash("Special deleted.", "success")
    return redirect(url_for("admin.specials"))


@bp.route("/events", methods=["GET", "POST"])
def events():
    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        if not name:
            flash("Event name is required.", "error")
            return redirect(url_for("admin.events"))
        event_date = (request.form.get("event_date") or "").strip() or None
        location = (request.form.get("location") or "").strip() or None
        url = (request.form.get("url") or "").strip() or None
        new_id = add_event(name, event_date, location, url)
        if new_id is None:
            flash(f"Maximum of {EVENT_LIMIT} events reached — remove one first.", "error")
        else:
            flash("Event added.", "success")
        return redirect(url_for("admin.events"))
    return render_template(
        "admin/events.html",
        events=list_events(),
        event_limit=EVENT_LIMIT,
    )


@bp.route("/events/<int:event_id>/update", methods=["POST"])
def update_event_route(event_id: int):
    name = (request.form.get("name") or "").strip()
    if not name:
        flash("Event name is required.", "error")
        return redirect(url_for("admin.events"))
    event_date = (request.form.get("event_date") or "").strip() or None
    location = (request.form.get("location") or "").strip() or None
    url = (request.form.get("url") or "").strip() or None
    active = 1 if request.form.get("active") else 0
    update_event(event_id, name, event_date, location, url, active)
    flash("Event updated.", "success")
    return redirect(url_for("admin.events"))


@bp.route("/events/<int:event_id>/delete", methods=["POST"])
def delete_event_route(event_id: int):
    delete_event(event_id)
    flash("Event deleted.", "success")
    return redirect(url_for("admin.events"))
