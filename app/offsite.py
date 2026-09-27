"""Off-site DB backup to Google Drive, via rclone.

Strategy:
  - Weekly (every 7 days), the background worker snapshots the live DB and
    uploads it to ``gdrive:PaliPints/db/palipints-YYYY-MM-DD.db``, plus a
    copy of ``data/images/`` to ``gdrive:PaliPints/images/``. Only the
    newest ``KEEP_COPIES`` DB snapshots are kept in Drive.
  - rclone does the Google Drive talking. Its config (which holds the
    Google refresh token) lives at ``data/rclone.conf`` — gitignored, and
    separate from any rclone setup the Pi user has of their own.
  - Access uses the ``drive.file`` scope: rclone can only see files it
    created, never the rest of the user's Drive.
  - Connecting is done from the admin Settings page, with no SSH needed.
    The Pi runs ``rclone authorize``, which listens on 127.0.0.1:53682 for
    Google's OAuth redirect. That redirect lands in the *admin's* browser
    (phone/laptop), where 127.0.0.1 is the wrong machine, so the page shows
    "can't connect". The admin pastes that URL back into the Settings page
    and we replay it against the Pi's own loopback, where rclone is
    waiting. rclone swaps the code for a token and prints it; we write it
    into ``data/rclone.conf``.
  - Status (last run, last error) is kept in ``data/backups/offsite.json``
    rather than the DB, so restoring a DB doesn't rewind it.
"""
from __future__ import annotations

import base64
import json
import logging
import os
import re
import shutil
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from . import DATA_DIR, DB_PATH, IMAGES_DIR
from .backup import BACKUP_DIR, _io_lock, _sqlite_copy, restore_from_backup

log = logging.getLogger(__name__)

RCLONE_CONF = DATA_DIR / "rclone.conf"
REMOTE_NAME = "gdrive"
REMOTE = f"{REMOTE_NAME}:PaliPints"
STAGING_DIR = BACKUP_DIR / "offsite"
STATUS_PATH = BACKUP_DIR / "offsite.json"

INTERVAL_SECONDS = 7 * 24 * 60 * 60   # weekly
RETRY_SECONDS = 6 * 60 * 60           # after a failure, try again in 6h
KEEP_COPIES = 4
AUTH_TIMEOUT_SECONDS = 10 * 60        # abandon a half-finished connect
SNAPSHOT_RE = re.compile(r"^palipints-\d{4}-\d{2}-\d{2}\.db$")

# Serialises uploads/restores so a worker run can't overlap a manual click.
_run_lock = threading.Lock()


# ---- rclone plumbing ------------------------------------------------------

def _rclone_bin() -> str | None:
    return os.environ.get("RCLONE_BIN") or shutil.which("rclone")


def _last_error_line(output: str) -> str:
    """The last non-blank line of rclone output, minus its log prefix
    (``2026/01/01 12:00:00 NOTICE: Fatal error:``)."""
    lines = [ln for ln in output.strip().splitlines() if ln.strip()]
    if not lines:
        return ""
    line = re.sub(r"^\d{4}/\d\d/\d\d \d\d:\d\d:\d\d \w+\s*:\s*", "", lines[-1])
    return re.sub(r"^Fatal error:\s*", "", line)


def _rclone(*args: str, timeout: int = 600) -> subprocess.CompletedProcess:
    """Run an rclone command against our private config. Raises
    RuntimeError with rclone's own error text on failure."""
    binary = _rclone_bin()
    if not binary:
        raise RuntimeError("rclone is not installed")
    proc = subprocess.run(
        [binary, "--config", str(RCLONE_CONF), *args],
        capture_output=True, text=True, timeout=timeout,
    )
    if proc.returncode != 0:
        raise RuntimeError(_last_error_line(proc.stderr) or f"rclone exited {proc.returncode}")
    return proc


def is_connected() -> bool:
    if not RCLONE_CONF.exists():
        return False
    text = RCLONE_CONF.read_text(encoding="utf-8")
    return f"[{REMOTE_NAME}]" in text and "token =" in text


def _load_status() -> dict:
    try:
        return json.loads(STATUS_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _save_status(**changes) -> None:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    status = _load_status()
    status.update(changes)
    STATUS_PATH.write_text(json.dumps(status, indent=2), encoding="utf-8")


# ---- Connect / disconnect -------------------------------------------------

class _AuthSession:
    """One in-flight ``rclone authorize`` process."""

    def __init__(self) -> None:
        self.output: list[str] = []
        self.state: str | None = None
        self.started_at = time.time()
        blob = base64.urlsafe_b64encode(
            json.dumps({"scope": "drive.file"}).encode()
        ).decode().rstrip("=")
        self.proc = subprocess.Popen(
            [_rclone_bin(), "--config", str(RCLONE_CONF),
             "authorize", "drive", blob, "--auth-no-open-browser"],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        )
        threading.Thread(target=self._pump, daemon=True).start()

    def _pump(self) -> None:
        for line in self.proc.stdout:
            self.output.append(line)

    def text(self) -> str:
        return "".join(self.output)

    def kill(self) -> None:
        if self.proc.poll() is None:
            self.proc.kill()


_auth: _AuthSession | None = None
_auth_lock = threading.Lock()


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def start_connect() -> dict:
    """Begin linking a Google account. Returns the Google sign-in URL for
    the admin to open."""
    global _auth
    if not _rclone_bin():
        return {"ok": False, "error": "rclone is not installed on this Pi (sudo apt-get install -y rclone)"}

    with _auth_lock:
        if _auth:
            _auth.kill()
        _auth = session = _AuthSession()

        # rclone prints a local link that 302s to Google's consent page.
        local_url = None
        deadline = time.time() + 15
        while time.time() < deadline and session.proc.poll() is None:
            m = re.search(r"(http://127\.0\.0\.1:53682/auth\?state=[\w-]+)", session.text())
            if m:
                local_url = m.group(1)
                break
            time.sleep(0.1)
        if not local_url:
            session.kill()
            _auth = None
            return {"ok": False, "error": "rclone did not start the sign-in: " + session.text()[-300:]}

        session.state = urllib.parse.parse_qs(urllib.parse.urlparse(local_url).query)["state"][0]
        opener = urllib.request.build_opener(_NoRedirect)
        try:
            opener.open(local_url, timeout=5)
            google_url = None
        except urllib.error.HTTPError as e:
            google_url = e.headers.get("Location")
        if not google_url or "accounts.google.com" not in google_url:
            session.kill()
            _auth = None
            return {"ok": False, "error": "could not get the Google sign-in link from rclone"}
        return {"ok": True, "auth_url": google_url}


def finish_connect(pasted_url: str) -> dict:
    """Complete linking with the URL the admin's browser was redirected to
    (``http://127.0.0.1:53682/?state=...&code=...``)."""
    global _auth
    with _auth_lock:
        session = _auth
        if not session or session.proc.poll() is not None \
                or time.time() - session.started_at > AUTH_TIMEOUT_SECONDS:
            if session:
                session.kill()
            _auth = None
            return {"ok": False, "error": "sign-in expired — click Connect Google Drive again"}

        query = urllib.parse.parse_qs(urllib.parse.urlparse(pasted_url.strip()).query)
        if "error" in query:
            return {"ok": False, "error": f"Google refused access: {query['error'][0]}"}
        code = (query.get("code") or [None])[0]
        state = (query.get("state") or [None])[0]
        if not code or state != session.state:
            return {"ok": False, "error": "that doesn't look like the right URL — copy the whole address "
                                          "from the page that failed to load after you clicked Allow"}

        # Hand the code to rclone on our own loopback.
        callback = "http://127.0.0.1:53682/?" + urllib.parse.urlencode({"state": state, "code": code})
        try:
            urllib.request.urlopen(callback, timeout=10).read()
        except (urllib.error.URLError, OSError) as e:
            session.kill()
            _auth = None
            return {"ok": False, "error": f"could not reach rclone: {e}"}

        try:
            session.proc.wait(timeout=30)
        except subprocess.TimeoutExpired:
            session.kill()
        _auth = None

        m = re.search(r"(\{.*\"access_token\".*\})", session.text())
        if not m:
            return {"ok": False, "error": "Google sign-in failed ("
                    + (_last_error_line(session.text()) or "no output")
                    + ") — click Connect Google Drive to try again"}
        token = m.group(1)

    RCLONE_CONF.write_text(
        f"[{REMOTE_NAME}]\ntype = drive\nscope = drive.file\ntoken = {token}\n",
        encoding="utf-8",
    )
    try:
        os.chmod(RCLONE_CONF, 0o600)
    except OSError:
        pass
    log.info("Google Drive connected for off-site backup")
    _save_status(connected_at=int(time.time()), last_error=None)
    return {"ok": True}


def disconnect() -> dict:
    """Forget the Google account. Backups already in Drive are left alone."""
    if RCLONE_CONF.exists():
        RCLONE_CONF.unlink()
    _save_status(connected_at=None)
    return {"ok": True}


# ---- Backup / list / restore ---------------------------------------------

def list_backups() -> list[dict]:
    """DB snapshots in Drive, newest first."""
    proc = _rclone("lsjson", "--files-only", f"{REMOTE}/db/", timeout=60)
    items = [
        {"name": f["Name"], "size_bytes": f.get("Size", 0), "modified": f.get("ModTime")}
        for f in json.loads(proc.stdout or "[]")
        if SNAPSHOT_RE.match(f["Name"])
    ]
    return sorted(items, key=lambda f: f["name"], reverse=True)


def should_run() -> bool:
    if not is_connected():
        return False
    status = _load_status()
    now = time.time()
    if now - (status.get("last_ok_at") or 0) < INTERVAL_SECONDS:
        return False
    # Don't hammer Drive every minute while it's failing.
    return now - (status.get("last_attempt_at") or 0) >= RETRY_SECONDS


def backup_now() -> dict:
    """Snapshot the DB and upload it (plus images) to Drive, then prune
    down to the newest KEEP_COPIES snapshots."""
    if not is_connected():
        return {"ok": False, "error": "Google Drive is not connected"}
    if not _run_lock.acquire(blocking=False):
        return {"ok": False, "error": "a Drive backup is already running"}
    started = int(time.time())
    try:
        _save_status(last_attempt_at=started)
        STAGING_DIR.mkdir(parents=True, exist_ok=True)
        name = time.strftime("palipints-%Y-%m-%d.db")
        snapshot = STAGING_DIR / name
        with _io_lock:
            if snapshot.exists():
                snapshot.unlink()
            _sqlite_copy(DB_PATH, snapshot)

        _rclone("copy", str(snapshot), f"{REMOTE}/db/")
        if IMAGES_DIR.exists():
            # copy, not sync: an image deleted locally stays in Drive.
            _rclone("copy", str(IMAGES_DIR), f"{REMOTE}/images/")

        for old in list_backups()[KEEP_COPIES:]:
            _rclone("deletefile", f"{REMOTE}/db/{old['name']}", timeout=60)

        snapshot.unlink()
        _save_status(last_ok_at=int(time.time()), last_file=name, last_error=None)
        log.info("off-site backup uploaded: %s", name)
        return {"ok": True, "name": name, "finished_at": int(time.time())}
    except Exception as e:  # noqa: BLE001 — surface any failure to the UI
        log.exception("off-site backup failed")
        _save_status(last_error=str(e))
        return {"ok": False, "error": str(e)}
    finally:
        _run_lock.release()


def restore(name: str) -> dict:
    """Download a snapshot from Drive and restore the live DB from it.
    Also pulls back any images missing locally."""
    if not SNAPSHOT_RE.match(name or ""):
        return {"ok": False, "error": "invalid backup name"}
    if not _run_lock.acquire(blocking=False):
        return {"ok": False, "error": "a Drive backup is already running"}
    try:
        STAGING_DIR.mkdir(parents=True, exist_ok=True)
        local = STAGING_DIR / f"restore-{name}"
        _rclone("copyto", f"{REMOTE}/db/{name}", str(local))
        try:
            result = restore_from_backup(local)
        finally:
            local.unlink(missing_ok=True)
        if result.get("ok"):
            try:
                _rclone("copy", f"{REMOTE}/images/", str(IMAGES_DIR))
            except RuntimeError as e:
                result["images_warning"] = str(e)
        return result
    except Exception as e:  # noqa: BLE001
        log.exception("off-site restore failed")
        return {"ok": False, "error": str(e)}
    finally:
        _run_lock.release()


def status() -> dict:
    """Everything the Settings page needs. Lists Drive contents only when
    connected (a network call, ~1s)."""
    info = {
        "rclone_installed": bool(_rclone_bin()),
        "connected": is_connected(),
        "keep_copies": KEEP_COPIES,
        "interval_days": INTERVAL_SECONDS // 86400,
        **_load_status(),
    }
    if info["connected"]:
        try:
            info["backups"] = list_backups()
        except Exception as e:  # noqa: BLE001
            info["backups"] = []
            info["list_error"] = str(e)
    return info
