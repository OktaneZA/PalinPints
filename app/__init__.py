"""Flask application factory."""
from __future__ import annotations

import os
import secrets
from pathlib import Path

from flask import Flask

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
IMAGES_DIR = DATA_DIR / "images"
UPLOADS_DIR = IMAGES_DIR / "uploads"
BREWERIES_DIR = IMAGES_DIR / "breweries"
BEERS_DIR = IMAGES_DIR / "beers"
DB_PATH = DATA_DIR / "palipints.db"
LEGACY_DB_PATH = DATA_DIR / "palibeerview.db"

STYLE_CATEGORIES = [
    "IPA & Pale Ales",
    "Sour & Wild Ales",
    "Stout & Porter",
    "Lager & Pilsner",
    "Belgian & Farmhouse",
    "Historical & Specialty",
]

# Per-theme hop fallback. Picked when a tap has no brewery logo cached.
# Themes with light logo cards work best with the black variant; brand
# themes use the green hop; chalkboard uses the outlined one.
THEME_HOP_FALLBACK: dict[str, str] = {
    "marble":      "img/hop-black.svg",
    "neon":        "img/hop-black.svg",
    "chalkboard":  "img/hop-outline.svg",
    "palindrome1": "img/hop-green.svg",
    "palindrome2": "img/hop-green.svg",
    "palindrome3": "img/hop-black.svg",
    "palindrome4": "img/hop-green.svg",
    "palindrome5": "img/hop-green.svg",
    "palindrome6": "img/hop-black.svg",
    "newsprint":   "img/hop-black.svg",   # dark ink on cream stock
    "terminal":    "img/hop-outline.svg", # thin outline reads on black
    "editorial":   "img/hop-black.svg",   # black hop on white paper
}

DEFAULT_CATEGORY_COLORS = {
    "IPA & Pale Ales": "#E89923",
    "Sour & Wild Ales": "#D63B5E",
    "Stout & Porter": "#2A1810",
    "Lager & Pilsner": "#F5D547",
    "Belgian & Farmhouse": "#C77B2D",
    "Historical & Specialty": "#6E1A28",
}

STYLE_SUBSTYLES: dict[str, list[str]] = {
    "IPA & Pale Ales": [
        "American IPA", "New England / Hazy IPA", "West Coast IPA",
        "Double / Imperial IPA", "Triple IPA", "Session IPA",
        "Black IPA", "White IPA", "English IPA", "Belgian IPA",
        "Brut IPA", "American Pale Ale", "English Pale Ale",
        "Blonde Ale", "Cream Ale", "Hoppy Lager",
    ],
    "Sour & Wild Ales": [
        "American Wild Ale", "Berliner Weisse", "Gose",
        "Lambic - Gueuze", "Lambic - Fruit", "Lambic - Faro",
        "Lambic - Traditional", "Flanders Red Ale",
        "Flanders Oud Bruin", "Brett Beer", "Fruited Sour Ale",
    ],
    "Stout & Porter": [
        "American Stout", "American Porter", "English Porter",
        "Baltic Porter", "Imperial Stout", "Russian Imperial Stout",
        "Milk / Sweet Stout", "Oatmeal Stout", "Coffee Stout",
        "Pastry Stout", "Dry Stout", "Foreign / Export Stout",
        "Imperial Coffee Porter",
    ],
    "Lager & Pilsner": [
        "American Lager", "American Light Lager", "Helles",
        "Munich Dunkel", "Bock", "Doppelbock", "Maibock", "Eisbock",
        "Vienna Lager", "Czech Pilsner", "German Pilsner",
        "Italian Pilsner", "Mexican Lager", "Schwarzbier",
        "Märzen / Oktoberfest", "Pale Lager",
    ],
    "Belgian & Farmhouse": [
        "Belgian Blonde", "Belgian Strong Pale", "Belgian Strong Dark",
        "Belgian Tripel", "Belgian Dubbel", "Belgian Quadrupel",
        "Belgian Witbier", "Saison / Farmhouse", "Bière de Garde",
        "Belgian IPA", "Trappist Single",
    ],
    "Historical & Specialty": [
        "Smoked Beer / Rauchbier", "Barleywine - American",
        "Barleywine - English", "Old Ale", "Scottish Ale",
        "Wee Heavy / Scotch Ale", "Strong Ale - American",
        "Pumpkin / Yam Beer", "Fruit Beer",
        "Spice / Herb / Vegetable Beer", "Christmas / Winter Warmer",
        "Hefeweizen", "Dunkelweizen", "Weizenbock", "Roggenbier",
        "California Common", "Kölsch", "Altbier", "Honey Beer",
        "Gluten-Free", "Non-Alcoholic",
    ],
}


def _load_or_create_secret_key() -> str:
    env = os.environ.get("PALIBEERVIEW_SECRET_KEY")
    if env:
        return env
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    key_path = DATA_DIR / ".secret_key"
    if key_path.exists():
        return key_path.read_text(encoding="utf-8").strip()
    key = secrets.token_urlsafe(48)
    key_path.write_text(key, encoding="utf-8")
    return key


def create_app() -> Flask:
    for d in (DATA_DIR, IMAGES_DIR, UPLOADS_DIR, BREWERIES_DIR, BEERS_DIR):
        d.mkdir(parents=True, exist_ok=True)

    # One-shot migration from the previous filename. Running installs that
    # were started before the rename keep all their data.
    if LEGACY_DB_PATH.exists() and not DB_PATH.exists():
        LEGACY_DB_PATH.rename(DB_PATH)

    app = Flask(__name__, instance_relative_config=False)
    app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024  # 8 MB upload cap
    app.config["DATA_DIR"] = str(DATA_DIR)
    app.config["SECRET_KEY"] = _load_or_create_secret_key()

    from . import db
    db.init_db()
    app.teardown_appcontext(db.close_db)

    from .routes_display import bp as display_bp
    from .routes_admin import bp as admin_bp
    from .routes_api import bp as api_bp
    app.register_blueprint(display_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(api_bp)

    from .routes_display import serve_data_image
    app.add_url_rule("/data-image/<path:relpath>", "serve_data_image", serve_data_image)

    # Make the active display theme available to every template (admin
    # uses it to mirror the display's look). Computed lazily per-request
    # so admin auto-switches alongside the display at sunrise/sunset.
    @app.context_processor
    def _inject_theme():
        from .models import get_settings
        from .sun import effective_theme
        try:
            return {"active_theme": effective_theme(get_settings())}
        except Exception:
            return {"active_theme": "palindrome1"}

    # Jinja filter: format a Unix epoch integer as a friendly local
    # "day-of-week, DD mon HH:MM" string. Used by the Beer library and
    # anywhere else we surface a stored sync/backup timestamp.
    import datetime as _dt

    @app.template_filter("epoch_local")
    def _epoch_local(value):
        if value is None or value == "":
            return "—"
        try:
            ts = int(value)
        except (TypeError, ValueError):
            return str(value)
        try:
            return _dt.datetime.fromtimestamp(ts).strftime("%a %d %b %H:%M")
        except (OSError, ValueError, OverflowError):
            return str(value)

    # Expose the shared is_home_brewery() predicate to templates so the
    # admin's home-brewery detection is consistent with the display's
    # (case-insensitive word-boundary prefix match, not strict equality).
    from .models import is_home_brewery as _is_home_brewery
    app.jinja_env.globals["is_home_brewery"] = _is_home_brewery

    from .sync_worker import start_sync_worker
    start_sync_worker(app)

    return app
