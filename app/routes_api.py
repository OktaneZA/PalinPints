"""JSON endpoints used by the admin UI (Untappd autofill)."""
from __future__ import annotations

from dataclasses import asdict

from flask import Blueprint, jsonify, request

from .untappd import download_brewery_logo, search_beer

bp = Blueprint("api", __name__, url_prefix="/admin/api")


@bp.route("/untappd/search")
def untappd_search():
    query = (request.args.get("q") or "").strip()
    if not query:
        return jsonify({"error": "missing query"}), 400

    hit = search_beer(query)
    payload = asdict(hit)

    if hit.brewery_logo_url and hit.brewery_slug and not hit.error:
        rel = download_brewery_logo(hit.brewery_slug, hit.brewery_logo_url)
        payload["brewery_logo_local"] = rel
        if rel:
            payload["brewery_logo_local_url"] = f"/data-image/{rel}"

    return jsonify(payload)
