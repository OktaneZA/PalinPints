"""Sunrise/sunset lookup, IP geolocation, and effective-theme picker.

The display picks one of two configured themes (day/night) based on the
local time. Sunrise/sunset are fetched once a week from a public API and
cached in the settings row. The user can override either transition time
manually with an HH:MM string.
"""
from __future__ import annotations

import logging
import ssl
from datetime import datetime, time, timedelta, timezone
from typing import Any

import httpx
import truststore

log = logging.getLogger(__name__)

CACHE_TTL = timedelta(days=7)
NIGHT_LEAD_MINUTES = 30  # switch to night theme this long before sunset

# Pure-python httpx client with the OS trust store, matching app/internetscraping.py.
_SSL_CTX = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)


def _client(timeout: float = 8.0) -> httpx.Client:
    return httpx.Client(
        timeout=timeout,
        verify=_SSL_CTX,
        headers={"User-Agent": "PaliPints/1.0 (+https://github.com/OktaneZA/PalinPints)"},
    )


def auto_detect_location() -> tuple[float, float] | None:
    """Approximate lat/lon from the public IP. Returns None on any error."""
    try:
        with _client(5.0) as c:
            r = c.get("https://ipapi.co/json/")
            r.raise_for_status()
            data = r.json()
            lat = data.get("latitude")
            lon = data.get("longitude")
            if lat is not None and lon is not None:
                return float(lat), float(lon)
    except Exception as exc:  # network, DNS, JSON, key — all fall through
        log.warning("IP geolocation failed: %s", exc)
    return None


def fetch_sun_times(lat: float, lon: float) -> tuple[time, time] | None:
    """Today's local sunrise + sunset for the given coords. None on failure.

    Uses sunrise-sunset.org (free, no key, ISO-8601 UTC output).
    """
    try:
        with _client(8.0) as c:
            r = c.get(
                "https://api.sunrise-sunset.org/json",
                params={"lat": lat, "lng": lon, "formatted": 0},
            )
            r.raise_for_status()
            results = r.json().get("results") or {}
            sunrise_iso = results.get("sunrise")
            sunset_iso = results.get("sunset")
            if not (sunrise_iso and sunset_iso):
                return None
            sunrise_local = datetime.fromisoformat(sunrise_iso).astimezone()
            sunset_local = datetime.fromisoformat(sunset_iso).astimezone()
            return sunrise_local.time().replace(microsecond=0), sunset_local.time().replace(microsecond=0)
    except Exception as exc:
        log.warning("Sunrise-sunset fetch failed: %s", exc)
    return None


def _is_cache_stale(fetched_at_iso: str | None) -> bool:
    if not fetched_at_iso:
        return True
    try:
        fetched = datetime.fromisoformat(fetched_at_iso)
    except ValueError:
        return True
    return datetime.now(timezone.utc) - fetched.astimezone(timezone.utc) >= CACHE_TTL


def ensure_sun_cache_fresh(settings: dict[str, Any]) -> dict[str, Any] | None:
    """Refresh cached_sunrise / cached_sunset if older than the TTL.

    Returns a dict of fields to persist, or None if no update needed.
    No-op when lat/lon are unset.
    """
    if not _is_cache_stale(settings.get("cache_fetched_at")):
        return None
    lat = settings.get("latitude")
    lon = settings.get("longitude")
    if lat is None or lon is None:
        return None
    times = fetch_sun_times(float(lat), float(lon))
    if times is None:
        return None
    sunrise, sunset = times
    return {
        "cached_sunrise": sunrise.isoformat(),
        "cached_sunset": sunset.isoformat(),
        "cache_fetched_at": datetime.now(timezone.utc).isoformat(),
    }


def _parse_hhmm(s: str | None) -> time | None:
    if not s:
        return None
    try:
        h, m = s.split(":", 1)
        return time(int(h), int(m))
    except (ValueError, AttributeError):
        return None


def _parse_iso_time(s: str | None) -> time | None:
    if not s:
        return None
    try:
        return time.fromisoformat(s)
    except ValueError:
        return None


def _minus_minutes(t: time, minutes: int) -> time:
    """Subtract minutes from a time-of-day, wrapping at midnight."""
    total = (t.hour * 60 + t.minute - minutes) % (24 * 60)
    return time(total // 60, total % 60)


def effective_theme(settings: dict[str, Any]) -> str:
    """Pick day_theme or night_theme based on the current local time.

    Day window is [day_start, night_start). Outside that window we render
    the night theme. day_start defaults to sunrise; night_start defaults to
    sunset minus NIGHT_LEAD_MINUTES. Either can be overridden by the
    operator via override_day_start / override_night_start (HH:MM, 24h).

    Falls back to day_theme when no times are configured (e.g. fresh
    install with no lat/lon and no overrides).
    """
    day_theme = settings.get("day_theme") or settings.get("theme") or "marble"
    night_theme = settings.get("night_theme") or day_theme

    day_start = (
        _parse_hhmm(settings.get("override_day_start"))
        or _parse_iso_time(settings.get("cached_sunrise"))
    )
    sunset = _parse_iso_time(settings.get("cached_sunset"))
    night_start = (
        _parse_hhmm(settings.get("override_night_start"))
        or (_minus_minutes(sunset, NIGHT_LEAD_MINUTES) if sunset else None)
    )

    if day_start is None or night_start is None:
        return day_theme

    now = datetime.now().time()
    # Handle the normal case where day_start < night_start; if someone sets
    # an inverted override (rare), fall back to day theme.
    if day_start <= night_start:
        return day_theme if day_start <= now < night_start else night_theme
    return day_theme
