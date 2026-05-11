"""SQLite connection and schema migrations."""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager

from flask import g

from . import DB_PATH, DEFAULT_CATEGORY_COLORS

SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    home_brewery TEXT NOT NULL DEFAULT 'Palindrome Brewing Co',
    home_brewery_logo_path TEXT,
    display_style TEXT NOT NULL DEFAULT 'logo',
    display_scale REAL NOT NULL DEFAULT 1.0,
    theme TEXT NOT NULL DEFAULT 'palindrome1',
    day_theme TEXT NOT NULL DEFAULT 'palindrome1',
    night_theme TEXT NOT NULL DEFAULT 'palindrome1',
    latitude REAL,
    longitude REAL,
    override_day_start TEXT,
    override_night_start TEXT,
    cached_sunrise TEXT,
    cached_sunset TEXT,
    cache_fetched_at TEXT,
    beers_per_page INTEGER NOT NULL DEFAULT 12,
    page_rotation_interval INTEGER NOT NULL DEFAULT 15,
    color_ipa TEXT NOT NULL,
    color_sour TEXT NOT NULL,
    color_stout TEXT NOT NULL,
    color_lager TEXT NOT NULL,
    color_belgian TEXT NOT NULL,
    color_specialty TEXT NOT NULL,
    external_db_source TEXT NOT NULL DEFAULT 'mock',
    external_db_sync_interval_minutes INTEGER NOT NULL DEFAULT 360,
    external_db_last_sync_at INTEGER,
    external_db_last_sync_status TEXT,
    tap_order_mode TEXT NOT NULL DEFAULT 'style_category',
    holiday_fun_enabled INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS taps (
    tap_number INTEGER PRIMARY KEY,
    active INTEGER NOT NULL DEFAULT 0,
    brewery TEXT,
    beer_name TEXT,
    style_category TEXT,
    sub_style TEXT,
    abv REAL,
    ibu INTEGER,
    location TEXT,
    price_third REAL,
    price_half REAL,
    price_pint REAL,
    price_takeaway REAL,
    price_third_enabled INTEGER NOT NULL DEFAULT 0,
    price_half_enabled INTEGER NOT NULL DEFAULT 0,
    price_pint_enabled INTEGER NOT NULL DEFAULT 0,
    price_takeaway_enabled INTEGER NOT NULL DEFAULT 0,
    color_override TEXT,
    image_override_path TEXT,
    untappd_slug TEXT,
    library_external_id TEXT
);

CREATE TABLE IF NOT EXISTS beer_library (
    external_id TEXT PRIMARY KEY,
    beer_name TEXT,
    brewery TEXT,
    style_category TEXT,
    sub_style TEXT,
    location TEXT,
    description TEXT,
    abv REAL,
    ibu INTEGER,
    is_home_brewery INTEGER NOT NULL DEFAULT 0,
    untappd_slug TEXT,
    brewery_logo_url TEXT,
    external_updated_at INTEGER,
    synced_at INTEGER,
    local_overridden INTEGER NOT NULL DEFAULT 0,
    deleted_in_source INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_beer_library_brewery ON beer_library(brewery COLLATE NOCASE);
CREATE INDEX IF NOT EXISTS idx_beer_library_beer_name ON beer_library(beer_name COLLATE NOCASE);

CREATE TABLE IF NOT EXISTS specials (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sort_order INTEGER NOT NULL DEFAULT 0,
    active INTEGER NOT NULL DEFAULT 1,
    title TEXT NOT NULL,
    description TEXT,
    price REAL
);

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sort_order INTEGER NOT NULL DEFAULT 0,
    active INTEGER NOT NULL DEFAULT 1,
    name TEXT NOT NULL,
    event_date TEXT,
    location TEXT,
    url TEXT
);

CREATE TABLE IF NOT EXISTS untappd_cache (
    cache_key TEXT PRIMARY KEY,
    fetched_at INTEGER NOT NULL,
    payload TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS brewery_logos (
    brewery_slug TEXT PRIMARY KEY,
    image_path TEXT NOT NULL,
    fetched_at INTEGER NOT NULL
);
"""


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, detect_types=sqlite3.PARSE_DECLTYPES)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        g.db = _connect()
    return g.db


@contextmanager
def db_cursor():
    """Standalone cursor for use outside a request (e.g. init_db)."""
    conn = _connect()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with db_cursor() as conn:
        conn.executescript(SCHEMA)

        # Add columns introduced after the original schema
        existing_cols = {c[1] for c in conn.execute("PRAGMA table_info(settings)").fetchall()}
        if "theme" not in existing_cols:
            conn.execute("ALTER TABLE settings ADD COLUMN theme TEXT NOT NULL DEFAULT 'palindrome1'")

        # Display scale for non-1080p TVs (1.0 = native, 2.0 = 4K panel).
        if "display_scale" not in existing_cols:
            conn.execute("ALTER TABLE settings ADD COLUMN display_scale REAL NOT NULL DEFAULT 1.0")

        # Day/night theme switch + sunset cache columns.
        sunset_cols = {
            "day_theme": "TEXT NOT NULL DEFAULT 'palindrome1'",
            "night_theme": "TEXT NOT NULL DEFAULT 'palindrome1'",
            "latitude": "REAL",
            "longitude": "REAL",
            "override_day_start": "TEXT",
            "override_night_start": "TEXT",
            "cached_sunrise": "TEXT",
            "cached_sunset": "TEXT",
            "cache_fetched_at": "TEXT",
        }
        for col, decl in sunset_cols.items():
            if col not in existing_cols:
                conn.execute(f"ALTER TABLE settings ADD COLUMN {col} {decl}")
        # Seed day_theme from the existing single theme value if we just
        # added it — preserves the user's current look as the daytime default.
        if "day_theme" not in existing_cols and "theme" in existing_cols:
            conn.execute("UPDATE settings SET day_theme = theme WHERE id = 1")

        # Specials gained an active flag when events landed.
        special_cols = {c[1] for c in conn.execute("PRAGMA table_info(specials)").fetchall()}
        if "active" not in special_cols:
            conn.execute("ALTER TABLE specials ADD COLUMN active INTEGER NOT NULL DEFAULT 1")

        # Tap price flags + 1/3 pint, added when the price model became flexible.
        tap_cols = {c[1] for c in conn.execute("PRAGMA table_info(taps)").fetchall()}
        for col in ("price_third",):
            if col not in tap_cols:
                conn.execute(f"ALTER TABLE taps ADD COLUMN {col} REAL")
        for col in (
            "price_third_enabled",
            "price_half_enabled",
            "price_pint_enabled",
            "price_takeaway_enabled",
        ):
            if col not in tap_cols:
                conn.execute(f"ALTER TABLE taps ADD COLUMN {col} INTEGER NOT NULL DEFAULT 0")
                # Seed flag from corresponding price column for existing rows.
                price_col = col[: -len("_enabled")]
                if price_col != "price_third":  # third pint is brand-new, never had a value
                    conn.execute(
                        f"UPDATE taps SET {col} = 1 WHERE {price_col} IS NOT NULL"
                    )

        # Link to the beer_library row a tap was populated from (informational —
        # tap stays a snapshot, doesn't auto-refresh from library edits).
        if "library_external_id" not in tap_cols:
            conn.execute("ALTER TABLE taps ADD COLUMN library_external_id TEXT")

        # External-DB sync settings + tap ordering mode.
        external_db_cols = {
            "external_db_source": "TEXT NOT NULL DEFAULT 'mock'",
            "external_db_sync_interval_minutes": "INTEGER NOT NULL DEFAULT 360",
            "external_db_last_sync_at": "INTEGER",
            "external_db_last_sync_status": "TEXT",
            "tap_order_mode": "TEXT NOT NULL DEFAULT 'style_category'",
            "holiday_fun_enabled": "INTEGER NOT NULL DEFAULT 1",
        }
        for col, decl in external_db_cols.items():
            if col not in existing_cols:
                conn.execute(f"ALTER TABLE settings ADD COLUMN {col} {decl}")

        existing = conn.execute("SELECT id FROM settings WHERE id = 1").fetchone()
        if not existing:
            conn.execute(
                """
                INSERT INTO settings (
                    id, home_brewery, display_style, beers_per_page, page_rotation_interval,
                    color_ipa, color_sour, color_stout, color_lager, color_belgian, color_specialty
                ) VALUES (1, 'Palindrome Brewing Co', 'logo', 12, 15, ?, ?, ?, ?, ?, ?)
                """,
                (
                    DEFAULT_CATEGORY_COLORS["IPA & Pale Ales"],
                    DEFAULT_CATEGORY_COLORS["Sour & Wild Ales"],
                    DEFAULT_CATEGORY_COLORS["Stout & Porter"],
                    DEFAULT_CATEGORY_COLORS["Lager & Pilsner"],
                    DEFAULT_CATEGORY_COLORS["Belgian & Farmhouse"],
                    DEFAULT_CATEGORY_COLORS["Historical & Specialty"],
                ),
            )

        for tap_number in range(1, 23):
            conn.execute(
                "INSERT OR IGNORE INTO taps (tap_number, active) VALUES (?, 0)",
                (tap_number,),
            )


def close_db(_exc=None) -> None:
    db = g.pop("db", None)
    if db is not None:
        db.close()
