"""
Untappd public-page scraper.

This is the ONE place that knows about Untappd's HTML. When Untappd ships a
markup change, fix the selectors here only.

Selectors are best-effort and based on Untappd's structure as of writing. We
try several fallbacks per field; if everything fails, the field is None and
the admin can fill it manually.
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

from . import BREWERIES_DIR
from .db import get_db

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux armv7l) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 PaliBeerView/1.0"
)
CACHE_TTL_SECONDS = 24 * 60 * 60
REQUEST_DELAY_SECONDS = 1.0
TIMEOUT = httpx.Timeout(15.0)

_last_request_at = 0.0


@dataclass
class BeerHit:
    untappd_slug: str | None = None
    beer_name: str | None = None
    brewery: str | None = None
    sub_style: str | None = None
    abv: float | None = None
    ibu: int | None = None
    location: str | None = None
    brewery_logo_url: str | None = None
    brewery_slug: str | None = None
    error: str | None = None


def _polite_get(url: str) -> str:
    global _last_request_at
    elapsed = time.time() - _last_request_at
    if elapsed < REQUEST_DELAY_SECONDS:
        time.sleep(REQUEST_DELAY_SECONDS - elapsed)
    headers = {"User-Agent": USER_AGENT, "Accept-Language": "en-GB,en;q=0.9"}
    with httpx.Client(timeout=TIMEOUT, follow_redirects=True, headers=headers) as client:
        resp = client.get(url)
        resp.raise_for_status()
        _last_request_at = time.time()
        return resp.text


def _cache_get(key: str) -> dict[str, Any] | None:
    row = get_db().execute(
        "SELECT fetched_at, payload FROM untappd_cache WHERE cache_key = ?",
        (key,),
    ).fetchone()
    if not row:
        return None
    if time.time() - row["fetched_at"] > CACHE_TTL_SECONDS:
        return None
    try:
        return json.loads(row["payload"])
    except json.JSONDecodeError:
        return None


def _cache_set(key: str, payload: dict[str, Any]) -> None:
    get_db().execute(
        "INSERT OR REPLACE INTO untappd_cache (cache_key, fetched_at, payload) VALUES (?, ?, ?)",
        (key, int(time.time()), json.dumps(payload)),
    )
    get_db().commit()


def search_beer(query: str) -> BeerHit:
    """Search Untappd, follow the top hit, and return parsed beer info."""
    query = query.strip()
    if not query:
        return BeerHit(error="empty query")

    cache_key = f"search:{query.lower()}"
    cached = _cache_get(cache_key)
    if cached:
        return BeerHit(**cached)

    try:
        search_html = _polite_get(f"https://untappd.com/search?q={httpx.QueryParams({'q': query})['q']}")
    except httpx.HTTPError as e:
        return BeerHit(error=f"search request failed: {e}")

    soup = BeautifulSoup(search_html, "html.parser")
    beer_link = _first_beer_result_link(soup)
    if not beer_link:
        hit = BeerHit(error="no beer results found")
        _cache_set(cache_key, asdict(hit))
        return hit

    beer_url = urljoin("https://untappd.com", beer_link)
    try:
        beer_html = _polite_get(beer_url)
    except httpx.HTTPError as e:
        return BeerHit(error=f"beer page request failed: {e}")

    hit = _parse_beer_page(beer_html, beer_url)
    _cache_set(cache_key, asdict(hit))
    return hit


def _first_beer_result_link(soup: BeautifulSoup) -> str | None:
    for sel in [
        "div.beer-item a[href^='/b/']",
        "a[href^='/b/']",
        "p.name a[href^='/b/']",
    ]:
        a = soup.select_one(sel)
        if a and a.get("href"):
            return a["href"]
    return None


def _parse_beer_page(html: str, beer_url: str) -> BeerHit:
    soup = BeautifulSoup(html, "html.parser")
    hit = BeerHit()

    slug_match = re.search(r"/b/([^/]+/\d+)", beer_url)
    if slug_match:
        hit.untappd_slug = slug_match.group(1)

    name_el = soup.select_one("h1") or soup.select_one(".name h1")
    if name_el:
        hit.beer_name = name_el.get_text(strip=True)

    brewery_el = soup.select_one("p.brewery a") or soup.select_one(".brewery a")
    if brewery_el:
        hit.brewery = brewery_el.get_text(strip=True)
        href = brewery_el.get("href", "")
        m = re.search(r"/([^/]+)$", href.rstrip("/"))
        if m:
            hit.brewery_slug = m.group(1)

    style_el = soup.select_one("p.style") or soup.select_one(".style")
    if style_el:
        hit.sub_style = style_el.get_text(strip=True)

    page_text = soup.get_text(" ", strip=True)
    abv_match = re.search(r"([\d.]+)\s*%\s*ABV", page_text, re.IGNORECASE)
    if abv_match:
        try:
            hit.abv = float(abv_match.group(1))
        except ValueError:
            pass
    ibu_match = re.search(r"([\d.]+)\s*IBU", page_text, re.IGNORECASE)
    if ibu_match:
        try:
            hit.ibu = int(float(ibu_match.group(1)))
        except ValueError:
            pass

    loc_el = soup.select_one("p.brewery + p") or soup.select_one(".brewery-location")
    if loc_el:
        hit.location = loc_el.get_text(strip=True)

    if hit.brewery_slug:
        try:
            logo_url = _fetch_brewery_logo_url(hit.brewery_slug)
            hit.brewery_logo_url = logo_url
        except httpx.HTTPError:
            pass

    return hit


def _fetch_brewery_logo_url(brewery_slug: str) -> str | None:
    cache_key = f"brewery_logo:{brewery_slug}"
    cached = _cache_get(cache_key)
    if cached:
        return cached.get("logo_url")

    html = _polite_get(f"https://untappd.com/{brewery_slug}")
    soup = BeautifulSoup(html, "html.parser")
    for sel in [
        "div.label img",
        "a.label img",
        "img.brewery-label",
        "div.brewery-label img",
    ]:
        img = soup.select_one(sel)
        if img and img.get("src"):
            url = img["src"]
            _cache_set(cache_key, {"logo_url": url})
            return url
    _cache_set(cache_key, {"logo_url": None})
    return None


def download_brewery_logo(brewery_slug: str, logo_url: str) -> str | None:
    """Download a brewery logo into BREWERIES_DIR. Returns relative path."""
    if not logo_url:
        return None
    ext = ".png"
    m = re.search(r"\.(png|jpg|jpeg|gif|webp)(?:\?|$)", logo_url, re.IGNORECASE)
    if m:
        ext = "." + m.group(1).lower()

    safe_slug = re.sub(r"[^a-z0-9_-]+", "-", brewery_slug.lower()).strip("-") or "brewery"
    dest = BREWERIES_DIR / f"{safe_slug}{ext}"

    try:
        with httpx.Client(timeout=TIMEOUT, follow_redirects=True,
                          headers={"User-Agent": USER_AGENT}) as client:
            resp = client.get(logo_url)
            resp.raise_for_status()
            dest.write_bytes(resp.content)
    except httpx.HTTPError:
        return None

    rel = Path("breweries") / dest.name
    get_db().execute(
        "INSERT OR REPLACE INTO brewery_logos (brewery_slug, image_path, fetched_at) VALUES (?, ?, ?)",
        (safe_slug, str(rel).replace("\\", "/"), int(time.time())),
    )
    get_db().commit()
    return str(rel).replace("\\", "/")


def get_cached_brewery_logo(brewery_slug: str | None) -> str | None:
    if not brewery_slug:
        return None
    safe_slug = re.sub(r"[^a-z0-9_-]+", "-", brewery_slug.lower()).strip("-")
    row = get_db().execute(
        "SELECT image_path FROM brewery_logos WHERE brewery_slug = ?",
        (safe_slug,),
    ).fetchone()
    return row["image_path"] if row else None
