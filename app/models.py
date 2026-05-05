"""Thin query layer over SQLite. No ORM — just functions returning dicts."""
from __future__ import annotations

import hashlib
import json
from typing import Any

from .db import get_db

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
        "home_brewery", "home_brewery_logo_path", "display_style", "theme",
        "beers_per_page", "page_rotation_interval",
        "color_ipa", "color_sour", "color_stout",
        "color_lager", "color_belgian", "color_specialty",
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
           color_override=NULL, image_override_path=NULL, untappd_slug=NULL
           WHERE tap_number = ?""",
        (tap_number,),
    )
    get_db().commit()


def list_specials() -> list[dict[str, Any]]:
    return [dict(r) for r in get_db().execute(
        "SELECT * FROM specials ORDER BY sort_order, id"
    ).fetchall()]


def add_special(title: str, description: str | None, price: float | None) -> int:
    cur = get_db().execute(
        "INSERT INTO specials (sort_order, title, description, price) "
        "VALUES (COALESCE((SELECT MAX(sort_order)+1 FROM specials), 0), ?, ?, ?)",
        (title, description, price),
    )
    get_db().commit()
    return cur.lastrowid


def update_special(special_id: int, title: str, description: str | None, price: float | None) -> None:
    get_db().execute(
        "UPDATE specials SET title=?, description=?, price=? WHERE id=?",
        (title, description, price, special_id),
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
    taps = list_taps(active_only=True)
    specials = list_specials()
    events = list_events(active_only=True)

    enriched_taps = []
    for tap in taps:
        enriched_taps.append({
            **tap,
            "display_color": color_for_tap(tap, settings),
        })

    payload = {
        "settings": {
            k: settings[k] for k in (
                "home_brewery", "home_brewery_logo_path", "display_style", "theme",
                "beers_per_page", "page_rotation_interval",
                "color_ipa", "color_sour", "color_stout",
                "color_lager", "color_belgian", "color_specialty",
            )
        },
        "taps": enriched_taps,
        "specials": specials,
        "events": events,
    }
    canonical = json.dumps(payload, sort_keys=True, default=str)
    payload["version_hash"] = hashlib.sha1(canonical.encode("utf-8")).hexdigest()[:12]
    return payload
