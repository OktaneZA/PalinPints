#!/usr/bin/env bash
# Pull latest PaliPints code, refresh dependencies, and restart the service.
# Usage: bash scripts/update.sh
#
# Behaviour on failure: if the service fails to come back up after the update,
# the script offers to restore the database from the rolling weekly backup at
# data/backups/palipints.db.backup. The user must explicitly confirm — typing
# "RESTORE" (caps) — before any file is touched.

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"

DB_PATH="$PROJECT_DIR/data/palipints.db"
BACKUP_PATH="$PROJECT_DIR/data/backups/palipints.db.backup"
PRE_RESTORE_PATH="$PROJECT_DIR/data/palipints.db.pre-restore"

log() { echo ">>> $*"; }

offer_restore() {
    echo
    log "Service failed to start after the update."
    if [ ! -f "$BACKUP_PATH" ]; then
        log "No backup found at $BACKUP_PATH — cannot offer a rollback."
        log "Check 'journalctl --user -u palipints.service -n 50' for details."
        return 1
    fi
    log "A backup is available: $BACKUP_PATH"
    log "  size:     $(stat -c%s "$BACKUP_PATH" 2>/dev/null || echo unknown) bytes"
    log "  modified: $(stat -c%y "$BACKUP_PATH" 2>/dev/null || echo unknown)"
    echo
    echo "Restoring will REPLACE the current database with the backup. The"
    echo "current database will be copied to:"
    echo "  $PRE_RESTORE_PATH"
    echo "as a one-time safety net before being overwritten."
    echo
    echo -n 'Type RESTORE (in caps) to confirm rollback, anything else cancels: '
    read -r answer
    if [ "$answer" != "RESTORE" ]; then
        log "Rollback cancelled. Service is still failed."
        return 1
    fi
    log "Saving current DB to $PRE_RESTORE_PATH..."
    [ -f "$DB_PATH" ] && cp "$DB_PATH" "$PRE_RESTORE_PATH"
    log "Copying backup over current DB..."
    cp "$BACKUP_PATH" "$DB_PATH"
    log "Restarting service..."
    systemctl --user restart palipints.service
    sleep 2
    if systemctl --user --no-pager --quiet is-active palipints.service; then
        log "Service is active after restore."
        return 0
    fi
    log "Service still not active after restore. Check the journal:"
    log "  journalctl --user -u palipints.service -n 50"
    return 1
}

log "Pulling latest from origin..."
git fetch --quiet
LOCAL=$(git rev-parse HEAD)
REMOTE=$(git rev-parse '@{u}')
if [ "$LOCAL" = "$REMOTE" ]; then
    log "Already up to date ($LOCAL)."
else
    git pull --ff-only
    log "Updated: $LOCAL -> $(git rev-parse HEAD)"
fi

# Client-mode update — a Pi Zero (or other thin client) installed via
# scripts/install-client.sh has no .venv and a ~/.palipints-client-url file.
# The only thing to refresh is the kiosk launcher; Flask runs on the primary.
if [ ! -d .venv ] && [ -f "$HOME/.palipints-client-url" ]; then
    log "Client install detected — refreshing kiosk launcher only."
    cp "$PROJECT_DIR/scripts/kiosk-autostart-client.sh" "$HOME/palipints-kiosk.sh"
    chmod +x "$HOME/palipints-kiosk.sh"
    log "Done. To pick up changes without rebooting:"
    log "  pkill chromium || true"
    log "  DISPLAY=:0 bash \$HOME/palipints-kiosk.sh &"
    exit 0
fi

if [ ! -d .venv ]; then
    log "No .venv found. Run scripts/install.sh first."
    exit 1
fi

log "Refreshing Python dependencies..."
.venv/bin/pip install --upgrade --quiet pip wheel
.venv/bin/pip install --upgrade --quiet -r requirements.txt

log "Restarting service..."
systemctl --user restart palipints.service

# Give it a moment to settle. Service init runs DB migrations, source sync,
# etc. — a couple of seconds is usually enough; allow up to 8s before giving up.
for _ in 1 2 3 4 5 6 7 8; do
    if systemctl --user --no-pager --quiet is-active palipints.service; then
        log "Service is active."
        exit 0
    fi
    sleep 1
done

# Service did not come up cleanly. Offer to restore from backup.
offer_restore
