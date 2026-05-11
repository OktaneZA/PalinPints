"""Local DB backup + restore.

Strategy:
  - One rolling backup file at ``data/backups/palipints.db.backup``.
  - Weekly schedule (every 7 days). Also runs on first start if no backup
    exists yet, so the user always has a fallback.
  - Uses sqlite3's ``Connection.backup()`` so it's safe to run while the
    app is live — no need to stop the app.
  - Restore copies the current DB to ``data/palipints.db.pre-restore``
    first (safety net), then writes the backup over the current DB.
  - All file ops guarded by a module-level lock so a sync running in the
    background thread can't race with a restore from the admin UI.
"""
from __future__ import annotations

import logging
import shutil
import sqlite3
import threading
import time
from pathlib import Path

from . import DATA_DIR, DB_PATH

log = logging.getLogger(__name__)

BACKUP_DIR = DATA_DIR / "backups"
BACKUP_PATH = BACKUP_DIR / "palipints.db.backup"
PRE_RESTORE_PATH = DATA_DIR / "palipints.db.pre-restore"

BACKUP_INTERVAL_SECONDS = 7 * 24 * 60 * 60  # 7 days

# Serialises backup_now() and restore_from_backup() so they don't overlap
# with each other or with sync writes that share the DB file.
_io_lock = threading.Lock()


def _ensure_dirs() -> None:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)


def backup_info() -> dict:
    """Metadata about the current backup (for the admin UI)."""
    _ensure_dirs()
    if not BACKUP_PATH.exists():
        return {"exists": False, "path": str(BACKUP_PATH)}
    stat = BACKUP_PATH.stat()
    return {
        "exists": True,
        "path": str(BACKUP_PATH),
        "size_bytes": stat.st_size,
        "modified_at": int(stat.st_mtime),
    }


def should_backup() -> bool:
    """True if no backup exists yet, or the existing one is >= 7 days old."""
    if not BACKUP_PATH.exists():
        return True
    age = time.time() - BACKUP_PATH.stat().st_mtime
    return age >= BACKUP_INTERVAL_SECONDS


def backup_now() -> dict:
    """Take a backup of the current DB, overwriting any previous backup.

    Returns a result dict describing what happened. Safe to call while the
    app is running — uses SQLite's online backup API which copies pages
    transactionally.
    """
    _ensure_dirs()
    if not DB_PATH.exists():
        return {"ok": False, "error": "no DB to back up"}

    started = int(time.time())
    tmp_path = BACKUP_PATH.with_suffix(".backup.tmp")

    with _io_lock:
        # Clean any leftover from a previous interrupted attempt.
        if tmp_path.exists():
            tmp_path.unlink()

        try:
            src = sqlite3.connect(str(DB_PATH))
            dst = sqlite3.connect(str(tmp_path))
            try:
                with dst:
                    src.backup(dst)
            finally:
                dst.close()
                src.close()
        except sqlite3.Error as e:
            log.exception("backup failed")
            if tmp_path.exists():
                tmp_path.unlink()
            return {"ok": False, "error": f"sqlite error: {e}"}

        # Integrity check the new backup before committing it.
        try:
            check = sqlite3.connect(str(tmp_path))
            row = check.execute("PRAGMA integrity_check").fetchone()
            check.close()
            if row is None or row[0] != "ok":
                tmp_path.unlink()
                return {"ok": False, "error": f"integrity check failed: {row}"}
        except sqlite3.Error as e:
            if tmp_path.exists():
                tmp_path.unlink()
            return {"ok": False, "error": f"integrity check error: {e}"}

        # Atomic-ish replace.
        tmp_path.replace(BACKUP_PATH)

    log.info("backup written to %s (%d bytes)", BACKUP_PATH, BACKUP_PATH.stat().st_size)
    return {
        "ok": True,
        "path": str(BACKUP_PATH),
        "size_bytes": BACKUP_PATH.stat().st_size,
        "modified_at": int(BACKUP_PATH.stat().st_mtime),
        "started_at": started,
    }


def restore_from_backup() -> dict:
    """Replace the current DB with the backup.

    Caller is expected to invalidate any open DB connections (Flask's
    teardown handlers will reopen on the next request). The current DB
    is copied to ``data/palipints.db.pre-restore`` before being
    overwritten, so the user has one more level of safety net.
    """
    _ensure_dirs()
    if not BACKUP_PATH.exists():
        return {"ok": False, "error": "no backup to restore"}

    # Validate the backup before touching the live DB.
    try:
        check = sqlite3.connect(str(BACKUP_PATH))
        row = check.execute("PRAGMA integrity_check").fetchone()
        check.close()
        if row is None or row[0] != "ok":
            return {"ok": False, "error": f"backup failed integrity check: {row}"}
    except sqlite3.Error as e:
        return {"ok": False, "error": f"could not open backup: {e}"}

    with _io_lock:
        try:
            # Snapshot the current DB to the pre-restore file (safety net).
            if DB_PATH.exists():
                shutil.copy2(DB_PATH, PRE_RESTORE_PATH)
            # Replace current DB with backup contents.
            shutil.copy2(BACKUP_PATH, DB_PATH)
        except OSError as e:
            log.exception("restore failed")
            return {"ok": False, "error": f"file copy error: {e}"}

    log.info("restored DB from %s; previous DB saved to %s", BACKUP_PATH, PRE_RESTORE_PATH)
    return {
        "ok": True,
        "restored_from": str(BACKUP_PATH),
        "pre_restore_path": str(PRE_RESTORE_PATH),
        "restored_at": int(time.time()),
    }
