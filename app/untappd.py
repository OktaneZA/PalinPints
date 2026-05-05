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
import ssl
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

# Use the OS certificate store on Windows/macOS so corporate or system-installed
# CA roots resolve. Falls back to httpx default (certifi) if unavailable.
try:
    import truststore
    _SSL_CONTEXT: Any = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
except Exception:
    _SSL_CONTEXT = True

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
    thumbnail_url: str | None = None
    error: str | None = None


def _polite_get(url: str) -> str:
    global _last_request_at
    elapsed = time.time() - _last_request_at
    if elapsed < REQUEST_DELAY_SECONDS:
        time.sleep(REQUEST_DELAY_SECONDS - elapsed)
    headers = {"User-Agent": USER_AGENT, "Accept-Language": "en-GB,en;q=0.9"}
    with httpx.Client(timeout=TIMEOUT, follow_redirects=True, headers=headers, verify=_SSL_CONTEXT) as client:
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


def search_beers(query: str, limit: int = 5) -> tuple[list[BeerHit], str | None]:
    """Search Untappd and return up to `limit` parsed search-result hits.

    Returns (results, error). Each hit has basic info from the search page;
    call `fetch_beer_detail(slug)` to resolve location/IBU/logo on pick.
    """
    query = query.strip()
    if not query:
        return [], "empty query"

    cache_key = f"search_multi:{query.lower()}:{limit}"
    cached = _cache_get(cache_key)
    if cached:
        return [BeerHit(**h) for h in cached.get("results", [])], cached.get("error")

    try:
        search_html = _polite_get(
            f"https://untappd.com/search?q={httpx.QueryParams({'q': query})['q']}"
        )
    except httpx.HTTPError as e:
        return [], f"search request failed: {e}"

    soup = BeautifulSoup(search_html, "html.parser")
    items = _find_beer_result_items(soup)
    results: list[BeerHit] = []
    for item in items[:limit]:
        hit = _parse_search_result(item)
        if hit and hit.untappd_slug:
            results.append(hit)

    err = None if results else "no beer results found"
    _cache_set(cache_key, {"results": [asdict(h) for h in results], "error": err})
    return results, err


def fetch_beer_detail(slug: str) -> BeerHit:
    """Given an Untappd beer slug ('brewery-name/12345'), fetch full detail."""
    slug = (slug or "").strip().strip("/")
    if not slug:
        return BeerHit(error="empty slug")

    cache_key = f"detail:{slug}"
    cached = _cache_get(cache_key)
    if cached:
        return BeerHit(**cached)

    beer_url = f"https://untappd.com/b/{slug}"
    try:
        beer_html = _polite_get(beer_url)
    except httpx.HTTPError as e:
        return BeerHit(error=f"beer page request failed: {e}")

    hit = _parse_beer_page(beer_html, beer_url)
    _cache_set(cache_key, asdict(hit))
    return hit


def _find_beer_result_items(soup: BeautifulSoup):
    """Return a list of search result containers."""
    for sel in [
        "div.beer-item",
        "div.search-result",
        "li.beer-item",
    ]:
        items = soup.select(sel)
        if items:
            return items
    # Fallback: each beer link is wrapped in something — group by parent.
    seen_parents = []
    for a in soup.select("a[href^='/b/']"):
        parent = a.find_parent(["div", "li", "section"]) or a
        if parent not in seen_parents:
            seen_parents.append(parent)
    return seen_parents


def _parse_search_result(item) -> BeerHit | None:
    """Pull basic fields out of a single search-result container."""
    a = item.select_one("p.name a[href^='/b/']") or item.select_one("a[href^='/b/']")
    if not a or not a.get("href"):
        return None
    href = a["href"]
    slug_match = re.search(r"/b/([^/?#]+/\d+)", href)
    if not slug_match:
        return None

    hit = BeerHit(untappd_slug=slug_match.group(1))
    hit.beer_name = a.get_text(strip=True) or None

    brewery_a = item.select_one("p.brewery a") or item.select_one(".brewery a")
    if brewery_a:
        hit.brewery = brewery_a.get_text(strip=True)
        m = re.search(r"/([^/]+)$", brewery_a.get("href", "").rstrip("/"))
        if m:
            hit.brewery_slug = m.group(1)
    else:
        em = item.select_one("p.name em") or item.select_one("em")
        if em:
            hit.brewery = em.get_text(strip=True)

    style_el = item.select_one("p.style") or item.select_one(".style")
    if style_el:
        hit.sub_style = style_el.get_text(strip=True)

    text = item.get_text(" ", strip=True)
    abv_m = re.search(r"([\d.]+)\s*%\s*ABV", text, re.IGNORECASE)
    if abv_m:
        try:
            hit.abv = float(abv_m.group(1))
        except ValueError:
            pass
    ibu_m = re.search(r"([\d.]+)\s*IBU", text, re.IGNORECASE)
    if ibu_m:
        try:
            hit.ibu = int(float(ibu_m.group(1)))
        except ValueError:
            pass

    img = item.select_one("img")
    if img and img.get("src"):
        hit.thumbnail_url = img["src"]

    return hit


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

    # The beer page often has stray `.location` elements from recent
    # check-ins (someone's local pub) that aren't the brewery's location.
    # The brewery page is the authoritative source — fetch it (we need it
    # for the logo anyway) and pull location from there.
    if hit.brewery_slug:
        try:
            info = _fetch_brewery_info(hit.brewery_slug)
            hit.brewery_logo_url = info.get("logo_url")
            hit.location = info.get("location") or None
        except httpx.HTTPError:
            pass

    return hit


def _fetch_brewery_info(brewery_slug: str) -> dict[str, Any]:
    """Returns {'logo_url': ..., 'location': ...} for a brewery, both optional."""
    cache_key = f"brewery_info:{brewery_slug}"
    cached = _cache_get(cache_key)
    if cached:
        return cached

    html = _polite_get(f"https://untappd.com/{brewery_slug}")
    soup = BeautifulSoup(html, "html.parser")

    info: dict[str, Any] = {"logo_url": None, "location": None}

    for sel in [
        "div.label img",
        "a.label img",
        "img.brewery-label",
        "div.brewery-label img",
    ]:
        img = soup.select_one(sel)
        if img and img.get("src"):
            info["logo_url"] = img["src"]
            break

    for sel in [".location", "span.location", "p.location", ".brewery-location"]:
        loc_el = soup.select_one(sel)
        if loc_el:
            text = loc_el.get_text(strip=True)
            if text and "," in text:
                info["location"] = text
                break

    _cache_set(cache_key, info)
    return info


# Backwards-compatible shim — older callers expected just the logo URL.
def _fetch_brewery_logo_url(brewery_slug: str) -> str | None:
    return _fetch_brewery_info(brewery_slug).get("logo_url")


def brewery_name_slug(brewery_name: str | None) -> str:
    """Canonical slug derived from a brewery's display name. The same string is
    used as the cache key on both write (download) and read (display)."""
    if not brewery_name:
        return ""
    return re.sub(r"[^a-z0-9_-]+", "-", brewery_name.lower()).strip("-")


def download_brewery_logo(brewery_name: str, logo_url: str | None) -> str | None:
    """Download a brewery logo into BREWERIES_DIR keyed by the brewery's
    display-name slug. Returns the relative path to the saved image. If we
    already have the file on disk for this brewery, skip the download."""
    if not brewery_name:
        return None

    slug = brewery_name_slug(brewery_name) or "brewery"

    # Already cached and present on disk? Don't re-download.
    cached = get_cached_brewery_logo(brewery_name)
    if cached:
        on_disk = BREWERIES_DIR / Path(cached).name
        if on_disk.is_file():
            return cached

    if not logo_url:
        return cached  # nothing to fetch with — return whatever we have (or None)

    ext = ".png"
    m = re.search(r"\.(png|jpg|jpeg|gif|webp)(?:\?|$)", logo_url, re.IGNORECASE)
    if m:
        ext = "." + m.group(1).lower()

    dest = BREWERIES_DIR / f"{slug}{ext}"

    try:
        with httpx.Client(timeout=TIMEOUT, follow_redirects=True,
                          headers={"User-Agent": USER_AGENT},
                          verify=_SSL_CONTEXT) as client:
            resp = client.get(logo_url)
            resp.raise_for_status()
            dest.write_bytes(resp.content)
    except httpx.HTTPError:
        return None

    rel = Path("breweries") / dest.name
    get_db().execute(
        "INSERT OR REPLACE INTO brewery_logos (brewery_slug, image_path, fetched_at) VALUES (?, ?, ?)",
        (slug, str(rel).replace("\\", "/"), int(time.time())),
    )
    get_db().commit()
    return str(rel).replace("\\", "/")


def get_cached_brewery_logo(brewery_name: str | None) -> str | None:
    """Look up a cached logo by brewery display name (slugified)."""
    slug = brewery_name_slug(brewery_name)
    if not slug:
        return None
    row = get_db().execute(
        "SELECT image_path FROM brewery_logos WHERE brewery_slug = ?",
        (slug,),
    ).fetchone()
    return row["image_path"] if row else None
