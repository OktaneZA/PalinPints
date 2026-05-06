"""JSON endpoints used by the admin UI."""
from __future__ import annotations

from dataclasses import asdict

from flask import Blueprint, jsonify, request

from .db import get_db
from .internetscraping import download_brewery_logo, fetch_beer_detail, search_beers

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
