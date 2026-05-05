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
    theme TEXT NOT NULL DEFAULT 'marble',
    beers_per_page INTEGER NOT NULL DEFAULT 12,
    page_rotation_interval INTEGER NOT NULL DEFAULT 15,
    color_ipa TEXT NOT NULL,
    color_sour TEXT NOT NULL,
    color_stout TEXT NOT NULL,
    color_lager TEXT NOT NULL,
    color_belgian TEXT NOT NULL,
    color_specialty TEXT NOT NULL
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
    price_half REAL,
    price_pint REAL,
    price_takeaway REAL,
    color_override TEXT,
    image_override_path TEXT,
    untappd_slug TEXT
);

CREATE TABLE IF NOT EXISTS specials (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sort_order INTEGER NOT NULL DEFAULT 0,
    title TEXT NOT NULL,
    description TEXT,
    price REAL
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
            conn.execute("ALTER TABLE settings ADD COLUMN theme TEXT NOT NULL DEFAULT 'marble'")

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
