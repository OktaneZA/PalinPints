"""External-beer-DB sync.

The beer catalogue is mastered in an external system (real Postgres later;
JSON-file mock for now). We mirror it into the local SQLite ``beer_library``
table so the kiosk works offline. Local edits on a row set ``local_overridden``
and are preserved across syncs until the user resets that row.
"""
from __future__ import annotations

import json
import time
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass
from typing import Iterable

from . import DATA_DIR
from .models import (
    get_settings,
    mark_beers_deleted_in_source,
    update_settings,
    upsert_beer_from_source,
)


MOCK_SOURCE_PATH = DATA_DIR / "mock_beer_source.json"


class BeerSourceError(RuntimeError):
    """Raised when a source can't be read (offline, auth, bad payload).
    Caught by sync_now and surfaced via settings.external_db_last_sync_status."""


@dataclass
class BeerRecord:
    external_id: str
    beer_name: str | None = None
    brewery: str | None = None
    style_category: str | None = None
    sub_style: str | None = None
    location: str | None = None
    description: str | None = None
    abv: float | None = None
    ibu: int | None = None
    is_home_brewery: int = 0
    untappd_slug: str | None = None
    brewery_logo_url: str | None = None
    external_updated_at: int | None = None


@dataclass
class SyncResult:
    added: int = 0
    updated: int = 0
    skipped_overridden: int = 0
    soft_deleted: int = 0
    status: str = ""
    ran_at: int = 0

    def to_dict(self) -> dict:
        return asdict(self)


class BeerSource(ABC):
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    def fetch_all(self) -> Iterable[BeerRecord]: ...


class MockBeerSource(BeerSource):
    """Reads beers from ``data/mock_beer_source.json``.

    Used while the real Postgres source isn't wired up. Edit the JSON file
    to simulate adds/updates/removals from the master catalogue.
    """

    def name(self) -> str:
        return "mock"

    def fetch_all(self) -> Iterable[BeerRecord]:
        if not MOCK_SOURCE_PATH.exists():
            raise BeerSourceError(
                f"mock source not found at {MOCK_SOURCE_PATH}. "
                "Create the file or switch source in settings."
            )
        try:
            with MOCK_SOURCE_PATH.open("r", encoding="utf-8") as f:
                payload = json.load(f)
        except json.JSONDecodeError as e:
            raise BeerSourceError(f"mock source is invalid JSON: {e}")

        items = payload.get("beers") if isinstance(payload, dict) else payload
        if not isinstance(items, list):
            raise BeerSourceError("mock source must contain a 'beers' list")

        records = []
        for item in items:
            if not isinstance(item, dict) or not item.get("external_id"):
                continue
            records.append(BeerRecord(
                external_id=str(item["external_id"]),
                beer_name=item.get("beer_name"),
                brewery=item.get("brewery"),
                style_category=item.get("style_category"),
                sub_style=item.get("sub_style"),
                location=item.get("location"),
                description=item.get("description"),
                abv=_as_float(item.get("abv")),
                ibu=_as_int(item.get("ibu")),
                is_home_brewery=1 if item.get("is_home_brewery") else 0,
                untappd_slug=item.get("untappd_slug"),
                brewery_logo_url=item.get("brewery_logo_url"),
                external_updated_at=_as_int(item.get("external_updated_at")),
            ))
        return records


class PostgresBeerSource(BeerSource):
    """Placeholder for the real source.

    TODO when credentials arrive:
      - Add config keys: external_db_dsn, external_db_table,
        external_db_id_column, and a column-name map for non-default schemas.
      - Use psycopg (>=3) — keep the import lazy so the app boots without it.
      - fetch_all() runs a single SELECT and yields BeerRecord rows.
      - Map source's is_home flag (boolean) to integer 0/1 here.
    """

    def name(self) -> str:
        return "postgres"

    def fetch_all(self) -> Iterable[BeerRecord]:
        raise BeerSourceError(
            "Postgres source is not configured yet. "
            "Switch to 'mock' in settings or finish wiring PostgresBeerSource."
        )


def get_source(source_name: str) -> BeerSource:
    if source_name == "postgres":
        return PostgresBeerSource()
    return MockBeerSource()


def should_run(settings: dict) -> bool:
    interval = int(settings.get("external_db_sync_interval_minutes") or 360)
    last = settings.get("external_db_last_sync_at")
    if not last:
        return True
    return (int(time.time()) - int(last)) >= interval * 60


def sync_now(app=None, force: bool = False) -> SyncResult:
    """Pull the source and upsert into beer_library.

    Pass the Flask app so we can push an app context — required because the
    DB layer uses ``flask.g`` for the connection. Background threads call
    this with the app from the worker.
    """
    if app is not None:
        with app.app_context():
            return _do_sync(force=force)
    return _do_sync(force=force)


def _do_sync(force: bool = False) -> SyncResult:
    result = SyncResult(ran_at=int(time.time()))
    settings = get_settings()

    if not force and not should_run(settings):
        result.status = "skipped (interval not elapsed)"
        return result

    source = get_source(settings.get("external_db_source") or "mock")

    try:
        records = list(source.fetch_all())
    except BeerSourceError as e:
        result.status = f"offline: {e}"
        _persist_status(result)
        return result
    except Exception as e:  # noqa: BLE001 — never let sync crash the app
        result.status = f"error: {type(e).__name__}: {e}"
        _persist_status(result)
        return result

    present_ids: set[str] = set()
    try:
        for rec in records:
            present_ids.add(rec.external_id)
            outcome = upsert_beer_from_source(asdict(rec), result.ran_at)
            if outcome == "added":
                result.added += 1
            elif outcome == "updated":
                result.updated += 1
            elif outcome == "skipped":
                result.skipped_overridden += 1

        result.soft_deleted = mark_beers_deleted_in_source(present_ids)
    except Exception as e:  # noqa: BLE001 — never let sync crash the app
        result.status = f"error: {type(e).__name__}: {e}"
        _persist_status(result)
        return result

    result.status = (
        f"ok: {result.added} added, {result.updated} updated, "
        f"{result.skipped_overridden} skipped, {result.soft_deleted} removed"
    )
    _persist_status(result)
    return result


def _persist_status(result: SyncResult) -> None:
    update_settings({
        "external_db_last_sync_at": result.ran_at,
        "external_db_last_sync_status": result.status,
    })


def _as_float(v) -> float | None:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _as_int(v) -> int | None:
    if v is None or v == "":
        return None
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None
