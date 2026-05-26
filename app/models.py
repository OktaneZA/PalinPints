"""Thin query layer over SQLite. No ORM — just functions returning dicts."""
from __future__ import annotations

import hashlib
import json
from typing import Any

from .db import get_db
from .holidays import active_holiday
from .sun import effective_theme, ensure_sun_cache_fresh

CATEGORY_TO_COLOR_FIELD = {
    "IPA & Pale Ales": "color_ipa",
    "Sour & Wild Ales": "color_sour",
    "Stout & Porter": "color_stout",
    "Lager & Pilsner": "color_lager",
    "Belgian & Farmhouse": "color_belgian",
    "Historical & Specialty": "color_specialty",
}


def _row_to_dict(row) -> dict[str, Any] | None:
    return dict(row) if row is not None else None


def get_settings() -> dict[str, Any]:
    row = get_db().execute("SELECT * FROM settings WHERE id = 1").fetchone()
    return dict(row)


def update_settings(values: dict[str, Any]) -> None:
    allowed = {
        "home_brewery", "home_brewery_location", "home_brewery_logo_path",
        "display_style", "display_scale", "theme",
        "day_theme", "night_theme", "day_night_auto",
        "latitude", "longitude",
        "override_day_start", "override_night_start",
        "cached_sunrise", "cached_sunset", "cache_fetched_at",
        "beers_per_page", "page_rotation_interval",
        "color_ipa", "color_sour", "color_stout",
        "color_lager", "color_belgian", "color_specialty",
        "external_db_source", "external_db_sync_interval_minutes",
        "external_db_last_sync_at", "external_db_last_sync_status",
        "tap_order_mode",
        "holiday_fun_enabled",
    }
    fields = [(k, v) for k, v in values.items() if k in allowed]
    if not fields:
        return
    set_clause = ", ".join(f"{k} = ?" for k, _ in fields)
    params = [v for _, v in fields] + [1]
    get_db().execute(f"UPDATE settings SET {set_clause} WHERE id = ?", params)
    get_db().commit()


def list_taps(active_only: bool = False) -> list[dict[str, Any]]:
    sql = "SELECT * FROM taps"
    if active_only:
        sql += " WHERE active = 1"
    sql += " ORDER BY tap_number"
    return [dict(r) for r in get_db().execute(sql).fetchall()]


def get_tap(tap_number: int) -> dict[str, Any] | None:
    row = get_db().execute("SELECT * FROM taps WHERE tap_number = ?", (tap_number,)).fetchone()
    return _row_to_dict(row)


def update_tap(tap_number: int, values: dict[str, Any]) -> None:
    allowed = {
        "active", "brewery", "beer_name", "style_category", "sub_style",
        "abv", "ibu", "location",
        "price_third", "price_half", "price_pint", "price_takeaway",
        "price_third_enabled", "price_half_enabled",
        "price_pint_enabled", "price_takeaway_enabled",
        "color_override", "image_override_path", "untappd_slug",
        "library_external_id",
    }
    fields = [(k, v) for k, v in values.items() if k in allowed]
    if not fields:
        return
    set_clause = ", ".join(f"{k} = ?" for k, _ in fields)
    params = [v for _, v in fields] + [tap_number]
    get_db().execute(f"UPDATE taps SET {set_clause} WHERE tap_number = ?", params)
    get_db().commit()


def clear_tap(tap_number: int) -> None:
    get_db().execute(
        """UPDATE taps SET active=0, brewery=NULL, beer_name=NULL, style_category=NULL,
           sub_style=NULL, abv=NULL, ibu=NULL, location=NULL,
           price_third=NULL, price_half=NULL, price_pint=NULL, price_takeaway=NULL,
           price_third_enabled=0, price_half_enabled=0,
           price_pint_enabled=0, price_takeaway_enabled=0,
           color_override=NULL, image_override_path=NULL, untappd_slug=NULL,
           library_external_id=NULL
           WHERE tap_number = ?""",
        (tap_number,),
    )
    get_db().commit()


def list_specials(active_only: bool = False) -> list[dict[str, Any]]:
    sql = "SELECT * FROM specials"
    if active_only:
        sql += " WHERE active = 1"
    sql += " ORDER BY sort_order, id"
    return [dict(r) for r in get_db().execute(sql).fetchall()]


def add_special(title: str, description: str | None, price: float | None, active: int = 1) -> int:
    cur = get_db().execute(
        "INSERT INTO specials (sort_order, active, title, description, price) "
        "VALUES (COALESCE((SELECT MAX(sort_order)+1 FROM specials), 0), ?, ?, ?, ?)",
        (active, title, description, price),
    )
    get_db().commit()
    return cur.lastrowid


def update_special(special_id: int, title: str, description: str | None,
                   price: float | None, active: int = 1) -> None:
    get_db().execute(
        "UPDATE specials SET title=?, description=?, price=?, active=? WHERE id=?",
        (title, description, price, active, special_id),
    )
    get_db().commit()


def delete_special(special_id: int) -> None:
    get_db().execute("DELETE FROM specials WHERE id=?", (special_id,))
    get_db().commit()


# ---- Events --------------------------------------------------------------
EVENT_LIMIT = 3


def list_events(active_only: bool = False) -> list[dict[str, Any]]:
    sql = "SELECT * FROM events"
    if active_only:
        sql += " WHERE active = 1"
    sql += " ORDER BY sort_order, id"
    return [dict(r) for r in get_db().execute(sql).fetchall()]


def event_count() -> int:
    return get_db().execute("SELECT COUNT(*) AS c FROM events").fetchone()["c"]


def add_event(name: str, event_date: str | None, location: str | None, url: str | None) -> int | None:
    if event_count() >= EVENT_LIMIT:
        return None
    cur = get_db().execute(
        "INSERT INTO events (sort_order, active, name, event_date, location, url) "
        "VALUES (COALESCE((SELECT MAX(sort_order)+1 FROM events), 0), 1, ?, ?, ?, ?)",
        (name, event_date, location, url),
    )
    get_db().commit()
    return cur.lastrowid


def update_event(event_id: int, name: str, event_date: str | None,
                 location: str | None, url: str | None, active: int) -> None:
    get_db().execute(
        "UPDATE events SET name=?, event_date=?, location=?, url=?, active=? WHERE id=?",
        (name, event_date, location, url, active, event_id),
    )
    get_db().commit()


def delete_event(event_id: int) -> None:
    get_db().execute("DELETE FROM events WHERE id=?", (event_id,))
    get_db().commit()


def is_home_brewery(tap_brewery: str | None, home_brewery: str | None) -> bool:
    """Match a tap's brewery name against the home brewery setting.

    Accepts case-insensitive equality and word-boundary prefix match in either
    direction so users can set "Palindrome" while taps say
    "Palindrome Brewing Co" (or vice versa) and still get the home logo.
    """
    a = (tap_brewery or "").strip().lower()
    b = (home_brewery or "").strip().lower()
    if not a or not b:
        return False
    if a == b:
        return True
    shorter, longer = (a, b) if len(a) <= len(b) else (b, a)
    if not longer.startswith(shorter):
        return False
    return len(longer) == len(shorter) or longer[len(shorter)] in " \t-"


def color_for_tap(tap: dict[str, Any], settings: dict[str, Any]) -> str:
    if tap.get("color_override"):
        return tap["color_override"]
    field = CATEGORY_TO_COLOR_FIELD.get(tap.get("style_category") or "")
    if field:
        return settings[field]
    return "#888888"


def state_snapshot() -> dict[str, Any]:
    """Full state used by the display. Stable JSON => stable hash."""
    settings = get_settings()

    # Refresh the weekly sunrise/sunset cache lazily, only when stale.
    refresh = ensure_sun_cache_fresh(settings)
    if refresh:
        update_settings(refresh)
        settings.update(refresh)

    # Pick the active theme based on current local time. The display
    # only sees the resolved 'theme' key, so its template is unchanged.
    settings["theme"] = effective_theme(settings)

    taps = list_taps(active_only=True)
    specials = list_specials(active_only=True)
    events = list_events(active_only=True)

    enriched_taps = []
    for tap in taps:
        enriched_taps.append({
            **tap,
            "display_color": color_for_tap(tap, settings),
        })

    # Active holiday key (or None). Included in the hash so the kiosk
    # picks up date-driven changes (e.g. Christmas window opens overnight)
    # on the next /api/state poll without any other state having to move.
    holiday = active_holiday() if settings.get("holiday_fun_enabled") else None

    payload = {
        "settings": {
            k: settings[k] for k in (
                "home_brewery", "home_brewery_logo_path", "display_style", "display_scale", "theme",
                "beers_per_page", "page_rotation_interval",
                "color_ipa", "color_sour", "color_stout",
                "color_lager", "color_belgian", "color_specialty",
                "tap_order_mode",
                "holiday_fun_enabled",
            )
        },
        "taps": enriched_taps,
        "specials": specials,
        "events": events,
        "holiday": holiday,
    }
    canonical = json.dumps(payload, sort_keys=True, default=str)
    payload["version_hash"] = hashlib.sha1(canonical.encode("utf-8")).hexdigest()[:12]
    return payload


# ---- Beer library --------------------------------------------------------

BEER_LIBRARY_EDITABLE_FIELDS = (
    "beer_name", "brewery", "style_category", "sub_style",
    "location", "description", "abv", "ibu",
    "untappd_slug", "brewery_logo_url", "is_home_brewery",
)

_BEER_LIBRARY_SORT_COLS = {
    "name": "beer_name COLLATE NOCASE",
    "brewery": "brewery COLLATE NOCASE, beer_name COLLATE NOCASE",
    "style": "style_category, sub_style, beer_name COLLATE NOCASE",
    # `abv IS NULL` sorts NULLs last on every SQLite version (3.30 added
    # NULLS LAST but we don't depend on it).
    "abv": "abv IS NULL, abv DESC, beer_name COLLATE NOCASE",
}


def list_beer_library(
    q: str | None = None,
    sort: str = "name",
    page: int = 1,
    page_size: int = 50,
    include_deleted: bool = False,
) -> dict[str, Any]:
    where = []
    params: list[Any] = []
    if not include_deleted:
        where.append("deleted_in_source = 0")
    if q:
        where.append("(beer_name LIKE ? OR brewery LIKE ?)")
        like = f"%{q}%"
        params.extend([like, like])
    sql_where = ("WHERE " + " AND ".join(where)) if where else ""
    order = _BEER_LIBRARY_SORT_COLS.get(sort, _BEER_LIBRARY_SORT_COLS["name"])

    page = max(1, page)
    page_size = max(10, min(200, page_size))

    total = get_db().execute(
        f"SELECT COUNT(*) AS c FROM beer_library {sql_where}", params
    ).fetchone()["c"]

    rows = get_db().execute(
        f"SELECT * FROM beer_library {sql_where} ORDER BY {order} "
        f"LIMIT ? OFFSET ?",
        params + [page_size, (page - 1) * page_size],
    ).fetchall()

    return {
        "items": [dict(r) for r in rows],
        "page": page,
        "page_size": page_size,
        "total": total,
        "pages": max(1, (total + page_size - 1) // page_size),
    }


def search_beer_library(q: str, limit: int = 20) -> list[dict[str, Any]]:
    q = (q or "").strip()
    if not q:
        return []
    like = f"%{q}%"
    rows = get_db().execute(
        "SELECT * FROM beer_library "
        "WHERE deleted_in_source = 0 "
        "AND (beer_name LIKE ? OR brewery LIKE ?) "
        "ORDER BY "
        "  CASE WHEN beer_name LIKE ? THEN 0 ELSE 1 END, "
        "  brewery COLLATE NOCASE, beer_name COLLATE NOCASE "
        "LIMIT ?",
        (like, like, f"{q}%", max(1, min(50, limit))),
    ).fetchall()
    return [dict(r) for r in rows]


def get_beer(external_id: str) -> dict[str, Any] | None:
    row = get_db().execute(
        "SELECT * FROM beer_library WHERE external_id = ?", (external_id,)
    ).fetchone()
    return _row_to_dict(row)


def update_beer_override(external_id: str, fields: dict[str, Any]) -> bool:
    edits = [(k, v) for k, v in fields.items() if k in BEER_LIBRARY_EDITABLE_FIELDS]
    if not edits:
        return False
    set_clause = ", ".join(f"{k} = ?" for k, _ in edits) + ", local_overridden = 1"
    params = [v for _, v in edits] + [external_id]
    cur = get_db().execute(
        f"UPDATE beer_library SET {set_clause} WHERE external_id = ?", params
    )
    get_db().commit()
    return cur.rowcount > 0


def reset_beer_override(external_id: str) -> bool:
    cur = get_db().execute(
        "UPDATE beer_library SET local_overridden = 0 WHERE external_id = ?",
        (external_id,),
    )
    get_db().commit()
    return cur.rowcount > 0


def upsert_beer_from_source(record: dict[str, Any], synced_at: int) -> str:
    """Insert or update from external source. Returns 'added' | 'updated' | 'skipped'.

    Skips when local_overridden=1 — user edits are preserved until reset.
    Updates also clear the deleted_in_source flag (beer is back).
    """
    existing = get_beer(record["external_id"])
    if existing and existing.get("local_overridden"):
        return "skipped"

    payload = {
        "external_id": record["external_id"],
        "beer_name": record.get("beer_name"),
        "brewery": record.get("brewery"),
        "style_category": record.get("style_category"),
        "sub_style": record.get("sub_style"),
        "location": record.get("location"),
        "description": record.get("description"),
        "abv": record.get("abv"),
        "ibu": record.get("ibu"),
        "is_home_brewery": 1 if record.get("is_home_brewery") else 0,
        "untappd_slug": record.get("untappd_slug"),
        "brewery_logo_url": record.get("brewery_logo_url"),
        "external_updated_at": record.get("external_updated_at"),
        "synced_at": synced_at,
        "deleted_in_source": 0,
    }
    if existing:
        cols = ", ".join(f"{k} = ?" for k in payload if k != "external_id")
        params = [payload[k] for k in payload if k != "external_id"] + [record["external_id"]]
        get_db().execute(
            f"UPDATE beer_library SET {cols} WHERE external_id = ?", params
        )
        get_db().commit()
        return "updated"
    cols = ", ".join(payload.keys())
    placeholders = ", ".join("?" for _ in payload)
    get_db().execute(
        f"INSERT INTO beer_library ({cols}) VALUES ({placeholders})",
        list(payload.values()),
    )
    get_db().commit()
    return "added"


def mark_beers_deleted_in_source(present_external_ids: set[str]) -> int:
    """Flag beers no longer in the source. Returns the number newly soft-deleted."""
    if present_external_ids:
        placeholders = ", ".join("?" * len(present_external_ids))
        cur = get_db().execute(
            f"UPDATE beer_library SET deleted_in_source = 1 "
            f"WHERE deleted_in_source = 0 "
            f"AND local_overridden = 0 "
            f"AND external_id NOT IN ({placeholders})",
            list(present_external_ids),
        )
    else:
        cur = get_db().execute(
            "UPDATE beer_library SET deleted_in_source = 1 "
            "WHERE deleted_in_source = 0 AND local_overridden = 0"
        )
    get_db().commit()
    return cur.rowcount
