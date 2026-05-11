"""JSON endpoints used by the admin UI."""
from __future__ import annotations

from dataclasses import asdict

from flask import Blueprint, jsonify, request

from .backup import backup_info, backup_now, restore_from_backup
from .db import close_db, get_db
from .internetscraping import download_brewery_logo, fetch_beer_detail, search_beers
from .models import (
    BEER_LIBRARY_EDITABLE_FIELDS,
    get_beer,
    get_settings,
    reset_beer_override,
    search_beer_library,
    update_beer_override,
)
from .sync_worker import trigger_sync

bp = Blueprint("api", __name__, url_prefix="/admin/api")


def _public_hit(hit) -> dict:
    payload = asdict(hit)
    payload["source_slug"] = payload.pop("untappd_slug", None)
    return payload


@bp.route("/breweries")
def breweries():
    """Distinct breweries we've already seen, used to populate brewery autocomplete."""
    rows = get_db().execute(
        "SELECT DISTINCT brewery FROM taps "
        "WHERE brewery IS NOT NULL AND TRIM(brewery) != '' "
        "ORDER BY brewery COLLATE NOCASE"
    ).fetchall()
    return jsonify([r["brewery"] for r in rows])


@bp.route("/web-search/search")
def web_search():
    """Return up to N parsed beer search results for the query."""
    query = (request.args.get("q") or "").strip()
    if not query:
        return jsonify({"error": "missing query", "results": []}), 400

    try:
        limit = max(1, min(10, int(request.args.get("limit") or 5)))
    except ValueError:
        limit = 5

    results, err = search_beers(query, limit=limit)
    return jsonify({
        "query": query,
        "error": err,
        "results": [_public_hit(h) for h in results],
    })


@bp.route("/web-search/select")
def web_select():
    """Fetch full detail for a selected slug + download brewery logo."""
    slug = (request.args.get("slug") or "").strip()
    if not slug:
        return jsonify({"error": "missing slug"}), 400

    hit = fetch_beer_detail(slug)
    payload = _public_hit(hit)
    if hit.brewery_logo_url and hit.brewery and not hit.error:
        rel = download_brewery_logo(hit.brewery, hit.brewery_logo_url)
        payload["brewery_logo_local"] = rel
        if rel:
            payload["brewery_logo_local_url"] = f"/data-image/{rel}"
    return jsonify(payload)


# ---- Beer library --------------------------------------------------------

@bp.route("/beer-library/search")
def beer_library_search():
    """Autocomplete endpoint for the tap form. Returns full beer records so
    the client can populate every field without a second roundtrip."""
    q = (request.args.get("q") or "").strip()
    try:
        limit = max(1, min(50, int(request.args.get("limit") or 20)))
    except ValueError:
        limit = 20
    return jsonify({"query": q, "results": search_beer_library(q, limit=limit)})


@bp.route("/beer-library/<external_id>/edit", methods=["POST"])
def beer_library_edit(external_id: str):
    if not get_beer(external_id):
        return jsonify({"error": "not found"}), 404
    body = request.get_json(silent=True) or {}
    fields = {k: v for k, v in body.items() if k in BEER_LIBRARY_EDITABLE_FIELDS}
    if not fields:
        return jsonify({"error": "no editable fields supplied"}), 400
    if "abv" in fields and fields["abv"] not in (None, ""):
        try: fields["abv"] = float(fields["abv"])
        except (TypeError, ValueError): fields["abv"] = None
    if "ibu" in fields and fields["ibu"] not in (None, ""):
        try: fields["ibu"] = int(float(fields["ibu"]))
        except (TypeError, ValueError): fields["ibu"] = None
    if "is_home_brewery" in fields:
        fields["is_home_brewery"] = 1 if fields["is_home_brewery"] else 0
    update_beer_override(external_id, fields)
    return jsonify({"ok": True, "beer": get_beer(external_id)})


@bp.route("/beer-library/<external_id>/reset", methods=["POST"])
def beer_library_reset(external_id: str):
    if not get_beer(external_id):
        return jsonify({"error": "not found"}), 404
    reset_beer_override(external_id)
    # Wake the worker — next sync pass restores this row from the source.
    trigger_sync()
    return jsonify({"ok": True})


@bp.route("/beer-library/sync", methods=["POST"])
def beer_library_sync_now():
    trigger_sync()
    settings = get_settings()
    return jsonify({
        "queued": True,
        "last_sync_at": settings.get("external_db_last_sync_at"),
        "last_sync_status": settings.get("external_db_last_sync_status"),
    })


@bp.route("/beer-library/status")
def beer_library_status():
    settings = get_settings()
    return jsonify({
        "last_sync_at": settings.get("external_db_last_sync_at"),
        "last_sync_status": settings.get("external_db_last_sync_status"),
        "source": settings.get("external_db_source"),
        "interval_minutes": settings.get("external_db_sync_interval_minutes"),
    })


# ---- DB backup / restore -------------------------------------------------

@bp.route("/backup/status")
def backup_status():
    return jsonify(backup_info())


@bp.route("/backup/now", methods=["POST"])
def backup_run_now():
    """Take an immediate backup. Used by the admin "Back up now" button."""
    result = backup_now()
    return (jsonify(result), 200 if result.get("ok") else 500)


@bp.route("/backup/restore", methods=["POST"])
def backup_restore():
    """Restore the live DB from the rolling backup. Requires the caller to
    pass ``{"confirm": "RESTORE"}`` in the JSON body — double-confirmation
    is enforced at the UI layer; this is the server-side safety net."""
    body = request.get_json(silent=True) or {}
    if (body.get("confirm") or "").strip().upper() != "RESTORE":
        return jsonify({
            "error": "missing or invalid confirmation",
            "hint": 'send {"confirm": "RESTORE"} in the request body',
        }), 400

    # Drop the per-request DB connection before swapping the file. Next
    # request will reopen against the restored DB.
    close_db()

    result = restore_from_backup()
    return (jsonify(result), 200 if result.get("ok") else 500)
