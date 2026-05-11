"""Background worker.

A single daemon thread handles two periodic jobs:
  1. Beer-library sync (interval-driven by ``external_db_sync_interval_minutes``).
  2. Weekly DB backup (every 7 days).

Boot behaviour: both run once on startup if due (sync always runs;
backup runs only if no backup exists yet, so first-time installs get
an immediate fallback). The manual "Sync now" endpoint sets
``wake_event`` to trigger an out-of-cycle sync.

The thread is best-effort — failures are logged and stored in settings
(for sync) but never crash the app.
"""
from __future__ import annotations

import logging
import threading

from .backup import backup_now, should_backup
from .beer_library import should_run, sync_now
from .models import get_settings

log = logging.getLogger(__name__)

# Module-level so routes can wake the worker without import gymnastics.
wake_event = threading.Event()

_started = False
_lock = threading.Lock()
_force_wake = False  # set when wake came from a manual "Sync now" click


def trigger_sync() -> None:
    """Tell the worker to run now (bypass the interval check)."""
    global _force_wake
    _force_wake = True
    wake_event.set()


def start_sync_worker(app) -> None:
    """Spawn the daemon thread. Idempotent across reloader runs."""
    global _started
    with _lock:
        if _started:
            return
        _started = True

    t = threading.Thread(
        target=_worker_loop, args=(app,), name="palipints-background", daemon=True,
    )
    t.start()


def _worker_loop(app) -> None:
    # Boot: kick off an immediate sync, and back up if no backup exists yet.
    _safe_sync(app, force=True)
    _safe_backup(app)

    while True:
        # 60s heartbeat. trigger_sync() wakes us early.
        wake_event.wait(timeout=60)
        wake_event.clear()
        global _force_wake
        force = _force_wake
        _force_wake = False

        if force:
            _safe_sync(app, force=True)
        else:
            with app.app_context():
                settings = get_settings()
            if should_run(settings):
                _safe_sync(app, force=False)

        # Always check backup cadence on every wake — cheap stat() call.
        _safe_backup(app)


def _safe_sync(app, force: bool) -> None:
    try:
        result = sync_now(app=app, force=force)
        log.info("beer-library sync: %s", result.status)
    except Exception:  # noqa: BLE001 — never let the worker die
        log.exception("beer-library sync failed unexpectedly")


def _safe_backup(app) -> None:
    try:
        if not should_backup():
            return
        with app.app_context():
            result = backup_now()
        if result.get("ok"):
            log.info("DB backup: ok (%d bytes)", result.get("size_bytes", 0))
        else:
            log.warning("DB backup: %s", result.get("error", "unknown"))
    except Exception:  # noqa: BLE001 — never let the worker die
        log.exception("DB backup failed unexpectedly")
