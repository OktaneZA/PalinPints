"""
Public beer-page scraper.

This is the ONE place that knows about beer 's HTML. When beer ships a
markup change, fix the selectors here only.

Selectors are best-effort and based on beers's structure as of writing. We
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

from . import BEERS_DIR, BREWERIES_DIR
from .db import get_db

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/149.0.0.0 Safari/537.36"
)
# Client Hints headers that modern Chromium sends alongside the UA string —
# many sites check these in addition to (or instead of) User-Agent. Versions
# match the Chrome 149 claim in USER_AGENT above; keep them in sync if the UA
# is ever bumped.
BROWSER_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept-Language": "en-US,en;q=0.9",
    "Sec-Ch-Ua": '"Google Chrome";v="149", "Chromium";v="149", "Not?A_Brand";v="24"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
}
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
    with httpx.Client(timeout=TIMEOUT, follow_redirects=True,
                      headers=BROWSER_HEADERS, verify=_SSL_CONTEXT) as client:
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


_ALGOLIA_CONFIG_CACHE: dict[str, Any] | None = None
_ALGOLIA_CONFIG_EXPIRY: float = 0.0


def _get_algolia_config() -> dict[str, str] | None:
    """Return {'appId', 'searchKey'} used by Untappd's Algolia search.

    Untappd stopped server-rendering search results — the beer search page is
    now a small JS shell that queries Algolia client-side. The Algolia app ID
    and search-only API key are exposed in a `window.UNTAPPD_SEARCH_CONFIG`
    JSON blob on every /search page load. We fetch it once every 24 h and
    cache in memory, so a query pass is 1 Algolia POST rather than an HTML
    scrape."""
    global _ALGOLIA_CONFIG_CACHE, _ALGOLIA_CONFIG_EXPIRY
    now = time.time()
    if _ALGOLIA_CONFIG_CACHE and now < _ALGOLIA_CONFIG_EXPIRY:
        return _ALGOLIA_CONFIG_CACHE
    try:
        html = _polite_get("https://untappd.com/search")
    except httpx.HTTPError:
        return None
    m = re.search(r"window\.UNTAPPD_SEARCH_CONFIG\s*=\s*(\{.+?\});", html, re.DOTALL)
    if not m:
        return None
    try:
        cfg = json.loads(m.group(1))
    except json.JSONDecodeError:
        return None
    app_id = cfg.get("appId")
    search_key = cfg.get("searchKey")
    if not (app_id and search_key):
        return None
    _ALGOLIA_CONFIG_CACHE = {"appId": app_id, "searchKey": search_key}
    _ALGOLIA_CONFIG_EXPIRY = now + 24 * 3600
    return _ALGOLIA_CONFIG_CACHE


def _hit_from_algolia(record: dict[str, Any]) -> BeerHit | None:
    """Map one Algolia beer index hit to our BeerHit dataclass. Skips
    records that don't have the two fields needed to build a beer-page slug.

    Field mapping (from Algolia's `beer` index):
      untappd_slug     = `{beer_slug}/{bid}`         used for the beer page URL
      beer_name        = beer_name
      brewery          = brewery_name
      sub_style        = type_name (e.g. "IPA - New England / Hazy")
      abv              = beer_abv                     numeric %
      ibu              = beer_ibu                     0 = often "unmeasured"
      brewery_logo_url = brewery_label                filled in on search hit
                                                      so we don't need a
                                                      second HTTP round trip
      thumbnail_url    = beer_label_hd or beer_label  HD preferred; the
                                                      _sm URL is a fallback
    """
    beer_slug = (record.get("beer_slug") or "").strip()
    bid = record.get("bid")
    if not (beer_slug and bid):
        return None
    thumbnail = (record.get("beer_label_hd") or record.get("beer_label") or "").strip()
    return BeerHit(
        untappd_slug=f"{beer_slug}/{bid}",
        beer_name=(record.get("beer_name") or "").strip() or None,
        brewery=(record.get("brewery_name") or "").strip() or None,
        sub_style=(record.get("type_name") or "").strip() or None,
        abv=record.get("beer_abv") if record.get("beer_abv") is not None else None,
        ibu=int(record["beer_ibu"]) if record.get("beer_ibu") is not None else None,
        brewery_logo_url=(record.get("brewery_label") or "").strip() or None,
        thumbnail_url=thumbnail or None,
    )


def search_beers(query: str, limit: int = 5) -> tuple[list[BeerHit], str | None]:
    """Search Untappd via its public Algolia search index. Returns
    (results, error). Basic info only — call `fetch_beer_detail(slug)` on the
    picked hit to resolve full location / brewery logo."""
    query = query.strip()
    if not query:
        return [], "empty query"

    # v2 = Algolia-backed. Bump if the response shape ever changes so we
    # don't hand back cached garbage from the old HTML scraper.
    cache_key = f"search_multi:v2:{query.lower()}:{limit}"
    cached = _cache_get(cache_key)
    if cached:
        return [BeerHit(**h) for h in cached.get("results", [])], cached.get("error")

    cfg = _get_algolia_config()
    if not cfg:
        return [], "search config unavailable"

    url = f"https://{cfg['appId'].lower()}-dsn.algolia.net/1/indexes/beer/query"
    headers = {
        "X-Algolia-Application-Id": cfg["appId"],
        "X-Algolia-API-Key": cfg["searchKey"],
        "Content-Type": "application/x-www-form-urlencoded",
        "User-Agent": USER_AGENT,
    }
    # Algolia's `params` is a URL-encoded string.
    params = httpx.QueryParams({"query": query, "hitsPerPage": limit})
    body = {"params": str(params)}

    try:
        with httpx.Client(timeout=TIMEOUT, verify=_SSL_CONTEXT) as client:
            resp = client.post(url, headers=headers, json=body)
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPError as e:
        return [], f"search request failed: {e}"
    except json.JSONDecodeError:
        return [], "search response was not valid JSON"

    results: list[BeerHit] = []
    for record in data.get("hits", [])[:limit]:
        hit = _hit_from_algolia(record)
        if hit:
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
        # Brewery URLs come in two shapes:
        #   /VerdantBrewingCo            (legacy)
        #   /w/brasserie-cantillon/202   (newer wiki style)
        # Keep the full path (minus leading slash) so we can rebuild the URL.
        slug = href.strip("/")
        if slug:
            hit.brewery_slug = slug

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

    # Prefer the JSON-LD structured address Untappd embeds on every brewery
    # page — it has clean city/region fields. Falls back to the legacy
    # `.location` CSS selectors for pages that don't carry the LD block.
    info["location"] = _location_from_ld(soup) or _location_from_selectors(soup)

    _cache_set(cache_key, info)
    return info


def _location_from_ld(soup: BeautifulSoup) -> str | None:
    """Pull a 'City, Region' string out of the schema.org JSON-LD block."""
    for script in soup.find_all("script", {"type": "application/ld+json"}):
        try:
            data = json.loads(script.string or "")
        except (ValueError, TypeError):
            continue
        addr = (data or {}).get("address") or {}
        if not isinstance(addr, dict):
            continue
        city = (addr.get("addressLocality") or "").strip()
        region = (addr.get("addressRegion") or "").strip()
        parts = [p for p in (city, region) if p]
        if parts:
            return ", ".join(parts)
    return None


def _location_from_selectors(soup: BeautifulSoup) -> str | None:
    for sel in [".location", "span.location", "p.location", ".brewery-location"]:
        loc_el = soup.select_one(sel)
        if loc_el:
            text = loc_el.get_text(strip=True)
            if text and "," in text:
                return text
    return None


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
                          headers=BROWSER_HEADERS,
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


def download_beer_image(beer_slug: str, image_url: str | None) -> str | None:
    """Download a beer's icon (Untappd thumbnail) into BEERS_DIR keyed by the
    beer slug. Returns the relative path. Existing files are overwritten so a
    re-search refreshes the image. Untappd's "_sm" URLs are small (~100px) —
    try "_md" first for sharper kiosk display, fall back to "_sm" if 403/404."""
    if not beer_slug or not image_url:
        return None

    slug = re.sub(r"[^a-z0-9_-]+", "-", beer_slug.lower()).strip("-") or "beer"

    candidates: list[str] = []
    if "_sm." in image_url:
        candidates.append(image_url.replace("_sm.", "_md."))
    candidates.append(image_url)
    # de-dup while preserving order
    seen: set[str] = set()
    candidates = [u for u in candidates if not (u in seen or seen.add(u))]

    for url in candidates:
        ext = ".png"
        m = re.search(r"\.(png|jpg|jpeg|gif|webp)(?:\?|$)", url, re.IGNORECASE)
        if m:
            ext = "." + m.group(1).lower()
        dest = BEERS_DIR / f"{slug}{ext}"
        try:
            with httpx.Client(timeout=TIMEOUT, follow_redirects=True,
                              headers=BROWSER_HEADERS,
                              verify=_SSL_CONTEXT) as client:
                resp = client.get(url)
                resp.raise_for_status()
                dest.write_bytes(resp.content)
            return f"beers/{dest.name}"
        except httpx.HTTPError:
            continue
    return None


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
