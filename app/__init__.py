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
DB_PATH = DATA_DIR / "palibeerview.db"

STYLE_CATEGORIES = [
    "IPA & Pale Ales",
    "Sour & Wild Ales",
    "Stout & Porter",
    "Lager & Pilsner",
    "Belgian & Farmhouse",
    "Historical & Specialty",
]

DEFAULT_CATEGORY_COLORS = {
    "IPA & Pale Ales": "#E89923",
    "Sour & Wild Ales": "#D63B5E",
    "Stout & Porter": "#2A1810",
    "Lager & Pilsner": "#F5D547",
    "Belgian & Farmhouse": "#C77B2D",
    "Historical & Specialty": "#6E1A28",
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
    for d in (DATA_DIR, IMAGES_DIR, UPLOADS_DIR, BREWERIES_DIR):
        d.mkdir(parents=True, exist_ok=True)

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

    return app
