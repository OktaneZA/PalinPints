"""JSON endpoints used by the admin UI."""
from __future__ import annotations

from dataclasses import asdict

from flask import Blueprint, jsonify, request

from .db import get_db
from .untappd import download_brewery_logo, fetch_beer_detail, search_beers

bp = Blueprint("api", __name__, url_prefix="/admin/api")


@bp.route("/breweries")
def breweries():
    """Distinct breweries we've already seen, used to populate brewery autocomplete."""
    rows = get_db().execute(
        "SELECT DISTINCT brewery FROM taps "
        "WHERE brewery IS NOT NULL AND TRIM(brewery) != '' "
        "ORDER BY brewery COLLATE NOCASE"
    ).fetchall()
    return jsonify([r["brewery"] for r in rows])


@bp.route("/untappd/search")
def untappd_search():
    """Return up to N parsed Untappd search results for the query."""
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
        "results": [asdict(h) for h in results],
    })


@bp.route("/untappd/select")
def untappd_select():
    """Fetch full detail for a selected slug + download brewery logo."""
    slug = (request.args.get("slug") or "").strip()
    if not slug:
        return jsonify({"error": "missing slug"}), 400

    hit = fetch_beer_detail(slug)
    payload = asdict(hit)
    if hit.brewery_logo_url and hit.brewery_slug and not hit.error:
        rel = download_brewery_logo(hit.brewery_slug, hit.brewery_logo_url)
        payload["brewery_logo_local"] = rel
        if rel:
            payload["brewery_logo_local_url"] = f"/data-image/{rel}"
    return jsonify(payload)
