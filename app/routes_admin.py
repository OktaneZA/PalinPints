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
    list_beer_library,
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
        "untappd_slug": f.get("source_slug") or f.get("untappd_slug") or None,
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


@bp.route("/taps/<int:tap_number>/image", methods=["POST"])
def save_tap_image(tap_number: int):
    """Image-only update for a tap.

    The master "Save all taps" flow updates rows over JSON without
    reloading, so the legacy per-tap form's hidden text/price/color
    inputs go stale. This endpoint only touches ``image_override_path``
    so an image upload after a master save can't clobber unrelated
    fields with stale values.
    """
    if not get_tap(tap_number):
        return ("not found", 404)

    values: dict = {}
    if "image" in request.files:
        image_path = save_upload(request.files["image"])
        if image_path:
            values["image_override_path"] = image_path
    if request.form.get("clear_image") and "image_override_path" not in values:
        values["image_override_path"] = None

    if values:
        update_tap(tap_number, values)
        flash(f"Tap {tap_number} image updated.", "success")
    else:
        flash(f"Tap {tap_number} — no image change.", "info")
    return redirect(url_for("admin.taps"))


@bp.route("/taps/<int:tap_number>/clear", methods=["POST"])
def clear(tap_number: int):
    clear_tap(tap_number)
    flash(f"Tap {tap_number} cleared.", "success")
    return redirect(url_for("admin.taps"))


def _validate_tap_payload(idx: int, raw: dict) -> tuple[dict | None, list[str]]:
    """Build the update_tap() kwargs from one tap's JSON dict. Returns
    (values, errors). When errors is non-empty, the row is rejected."""
    errors: list[str] = []
    active = 1 if raw.get("active") else 0
    brewery = (raw.get("brewery") or "").strip() or None
    beer_name = (raw.get("beer_name") or "").strip() or None
    abv = _to_float(str(raw.get("abv")) if raw.get("abv") is not None else None)

    prices: dict[str, float | None] = {}
    enabled: dict[str, int] = {}
    for kind in PRICE_KINDS:
        prices[kind] = _to_float(
            str(raw.get(f"price_{kind}")) if raw.get(f"price_{kind}") is not None else None
        )
        enabled[kind] = 1 if raw.get(f"price_{kind}_enabled") else 0
    any_priced = any(enabled[k] and prices[k] is not None for k in PRICE_KINDS)

    if active:
        if not brewery: errors.append("brewery")
        if not beer_name: errors.append("beer name")
        if abv is None: errors.append("ABV %")
        if not any_priced: errors.append("at least one enabled price")
    if errors:
        return None, errors

    values: dict = {
        "active": active,
        "brewery": brewery,
        "beer_name": beer_name,
        "style_category": (raw.get("style_category") or None) or None,
        "sub_style": (raw.get("sub_style") or "").strip() or None,
        "abv": abv,
        "ibu": _to_int(str(raw.get("ibu")) if raw.get("ibu") is not None else None),
        "location": (raw.get("location") or "").strip() or None,
        "untappd_slug": (raw.get("source_slug") or raw.get("untappd_slug") or None),
        "library_external_id": (raw.get("library_external_id") or None),
        "image_override_path": (raw.get("image_override_path") or "").strip() or None,
    }
    for kind in PRICE_KINDS:
        values[f"price_{kind}"] = prices[kind]
        values[f"price_{kind}_enabled"] = enabled[kind]
    return values, []


@bp.route("/taps/save-all", methods=["POST"])
def save_all_taps():
    """Master save: accepts JSON ``{taps: [{tap_number, ...}, ...]}`` and
    validates each tap independently. Valid taps are updated in one
    request; rejected taps are returned so the client can highlight them."""
    if not request.is_json:
        return jsonify({"error": "expected JSON"}), 400
    body = request.get_json(silent=True) or {}
    submitted = body.get("taps") or []
    if not isinstance(submitted, list):
        return jsonify({"error": "taps must be a list"}), 400

    saved: list[int] = []
    rejected: list[dict] = []
    for raw in submitted:
        try:
            tap_number = int(raw.get("tap_number"))
        except (TypeError, ValueError):
            rejected.append({"tap_number": raw.get("tap_number"), "errors": ["bad tap_number"]})
            continue
        if not get_tap(tap_number):
            rejected.append({"tap_number": tap_number, "errors": ["unknown tap"]})
            continue
        values, errors = _validate_tap_payload(tap_number, raw)
        if errors:
            rejected.append({"tap_number": tap_number, "errors": errors})
            continue
        update_tap(tap_number, values)
        saved.append(tap_number)

    return jsonify({
        "saved": saved,
        "rejected": rejected,
        "message": (
            f"Saved {len(saved)} tap{'s' if len(saved) != 1 else ''}"
            + (f"; {len(rejected)} not saved" if rejected else "")
            + "."
        ),
    })


_TAP_ORDER_MODES = {"tap_number", "style_category", "home_first"}
_EXTERNAL_DB_SOURCES = {"mock", "postgres"}

_ALLOWED_THEMES = {"marble", "neon", "chalkboard", "palindrome1", "palindrome2", "palindrome3", "palindrome4", "palindrome5", "palindrome6"}


@bp.route("/beer-library", methods=["GET"])
def beer_library_page():
    q = (request.args.get("q") or "").strip() or None
    sort = request.args.get("sort") or "name"
    try:
        page = max(1, int(request.args.get("page") or 1))
    except ValueError:
        page = 1
    try:
        page_size = int(request.args.get("page_size") or 50)
    except ValueError:
        page_size = 50

    result = list_beer_library(q=q, sort=sort, page=page, page_size=page_size)
    return render_template(
        "admin/beer_library.html",
        settings=get_settings(),
        items=result["items"],
        page=result["page"],
        pages=result["pages"],
        page_size=result["page_size"],
        total=result["total"],
        q=q or "",
        sort=sort,
        categories=STYLE_CATEGORIES,
    )


def _normalise_theme(value: str | None, fallback: str = "palindrome1") -> str:
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
        night_theme = _normalise_theme(f.get("night_theme"))

        lat = _to_float(f.get("latitude"))
        lon = _to_float(f.get("longitude"))
        latitude = lat if lat is not None and -90 <= lat <= 90 else None
        longitude = lon if lon is not None and -180 <= lon <= 180 else None

        existing = get_settings()

        # Display scale is a fine-tune multiplier on top of the auto-fit;
        # comes in as a percentage (50–150) and persists as a float (0.5–1.5).
        scale_pct = _to_int(f.get("display_scale_pct")) or 100
        display_scale = max(0.5, min(1.5, scale_pct / 100.0))

        tap_order = f.get("tap_order_mode")
        if tap_order not in _TAP_ORDER_MODES:
            tap_order = "style_category"
        external_source = f.get("external_db_source")
        if external_source not in _EXTERNAL_DB_SOURCES:
            external_source = "mock"

        values = {
            "home_brewery": (f.get("home_brewery") or "").strip() or "Palindrome Brewing Co",
            "home_brewery_location": (f.get("home_brewery_location") or "").strip() or "London, UK",
            "display_style": "color" if f.get("display_style") == "color" else "logo",
            "display_scale": display_scale,
            "day_theme": day_theme,
            "night_theme": night_theme,
            "day_night_auto": 1 if f.get("day_night_auto") else 0,
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
            "tap_order_mode": tap_order,
            "external_db_source": external_source,
            "external_db_sync_interval_minutes": max(
                15, min(1440, _to_int(f.get("external_db_sync_interval_minutes")) or 360)
            ),
            "holiday_fun_enabled": 1 if f.get("holiday_fun_enabled") else 0,
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

    from .backup import backup_info
    from .holidays import HOLIDAY_LABELS
    return render_template(
        "admin/settings.html",
        settings=get_settings(),
        backup=backup_info(),
        holiday_labels=HOLIDAY_LABELS,
    )


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


@bp.route("/specials/save-all", methods=["POST"])
def save_all_specials():
    if not request.is_json:
        return jsonify({"error": "expected JSON"}), 400
    items = (request.get_json(silent=True) or {}).get("specials") or []
    saved: list[int] = []
    rejected: list[dict] = []
    for raw in items:
        try:
            sid = int(raw.get("id"))
        except (TypeError, ValueError):
            rejected.append({"id": raw.get("id"), "errors": ["bad id"]})
            continue
        title = (raw.get("title") or "").strip()
        if not title:
            rejected.append({"id": sid, "errors": ["title required"]})
            continue
        description = (raw.get("description") or "").strip() or None
        raw_price = raw.get("price")
        price = _to_float(str(raw_price) if raw_price not in (None, "") else None)
        active = 1 if raw.get("active") else 0
        update_special(sid, title, description, price, active)
        saved.append(sid)
    return jsonify({
        "saved": saved,
        "rejected": rejected,
        "message": (
            f"Saved {len(saved)} special{'s' if len(saved) != 1 else ''}"
            + (f"; {len(rejected)} not saved" if rejected else "")
            + "."
        ),
    })


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


@bp.route("/events/save-all", methods=["POST"])
def save_all_events():
    if not request.is_json:
        return jsonify({"error": "expected JSON"}), 400
    items = (request.get_json(silent=True) or {}).get("events") or []
    saved: list[int] = []
    rejected: list[dict] = []
    for raw in items:
        try:
            eid = int(raw.get("id"))
        except (TypeError, ValueError):
            rejected.append({"id": raw.get("id"), "errors": ["bad id"]})
            continue
        name = (raw.get("name") or "").strip()
        if not name:
            rejected.append({"id": eid, "errors": ["name required"]})
            continue
        event_date = (raw.get("event_date") or "").strip() or None
        location = (raw.get("location") or "").strip() or None
        url_field = (raw.get("url") or "").strip() or None
        active = 1 if raw.get("active") else 0
        update_event(eid, name, event_date, location, url_field, active)
        saved.append(eid)
    return jsonify({
        "saved": saved,
        "rejected": rejected,
        "message": (
            f"Saved {len(saved)} event{'s' if len(saved) != 1 else ''}"
            + (f"; {len(rejected)} not saved" if rejected else "")
            + "."
        ),
    })
