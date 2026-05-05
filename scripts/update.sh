#!/usr/bin/env bash
# Pull latest PalinPints code, refresh dependencies, and restart the service.
# Usage: bash scripts/update.sh

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"

log() { echo ">>> $*"; }

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

if [ ! -d .venv ]; then
    log "No .venv found. Run scripts/install.sh first."
    exit 1
fi

log "Refreshing Python dependencies..."
.venv/bin/pip install --upgrade --quiet pip wheel
.venv/bin/pip install --upgrade --quiet -r requirements.txt

log "Restarting service..."
systemctl --user restart palibeerview.service

sleep 1
systemctl --user --no-pager --quiet is-active palibeerview.service \
    && log "Service is active."
