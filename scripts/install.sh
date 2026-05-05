#!/usr/bin/env bash
# PaliPints Pi installer.
# Run as the user that will own the kiosk session (typically `pi`).
# Usage: bash scripts/install.sh
#
# Idempotent: safe to re-run. Use scripts/update.sh for routine updates.

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
USER_NAME="$(id -un)"
SYSTEMD_USER_DIR="$HOME/.config/systemd/user"
AUTOSTART_DIR="$HOME/.config/autostart"

log() { echo ">>> $*"; }
log "PaliPints install for user $USER_NAME at $PROJECT_DIR"

# Sanity check: must be run on the Pi (or another Linux box), not from Windows.
if ! command -v apt-get >/dev/null; then
    echo "This installer expects apt-get (Raspberry Pi OS / Debian)." >&2
    exit 1
fi

# 1. System deps (Pillow needs libjpeg/zlib; Chromium for kiosk)
log "Installing apt packages (sudo required)..."
sudo apt-get update
sudo apt-get install -y --no-install-recommends \
    python3 python3-venv python3-pip \
    libjpeg-dev zlib1g-dev \
    chromium-browser xdotool unclutter \
    curl ca-certificates

# 2. Python venv
log "Creating Python virtualenv..."
cd "$PROJECT_DIR"
if [ ! -d .venv ]; then
    python3 -m venv .venv
fi
.venv/bin/pip install --upgrade pip wheel
.venv/bin/pip install -r requirements.txt

# 3. systemd --user service for the Flask app
log "Installing systemd user service..."
mkdir -p "$SYSTEMD_USER_DIR"
sed "s|@PROJECT_DIR@|$PROJECT_DIR|g" "$PROJECT_DIR/scripts/palipints.service" \
    > "$SYSTEMD_USER_DIR/palipints.service"

# Clean up the old service name from previous installs (safe if missing).
if [ -f "$SYSTEMD_USER_DIR/palibeerview.service" ]; then
    log "Removing old palibeerview.service unit..."
    systemctl --user disable --now palibeerview.service 2>/dev/null || true
    rm -f "$SYSTEMD_USER_DIR/palibeerview.service"
fi

# Enable lingering so the user service starts at boot without login
sudo loginctl enable-linger "$USER_NAME"

systemctl --user daemon-reload
systemctl --user enable palipints.service
systemctl --user restart palipints.service

# 4. Chromium kiosk autostart
log "Installing Chromium kiosk autostart..."
mkdir -p "$AUTOSTART_DIR"
cp "$PROJECT_DIR/scripts/kiosk-autostart.sh" "$HOME/palipints-kiosk.sh"
chmod +x "$HOME/palipints-kiosk.sh"
# Remove old kiosk script names from previous installs.
rm -f "$HOME/palinpints-kiosk.sh" "$HOME/palibeerview-kiosk.sh"

cat > "$AUTOSTART_DIR/palipints-kiosk.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=PaliPints Kiosk
Exec=/bin/bash $HOME/palipints-kiosk.sh
X-GNOME-Autostart-enabled=true
EOF
rm -f "$AUTOSTART_DIR/palinpints-kiosk.desktop" "$AUTOSTART_DIR/palibeerview-kiosk.desktop"

# 5. Optional: Raspberry Pi Connect for remote management
log "Optional: Raspberry Pi Connect for remote browser-based access."
if [ "${SKIP_RPI_CONNECT:-0}" != "1" ] && apt-cache show rpi-connect >/dev/null 2>&1; then
    log "  Installing rpi-connect package..."
    sudo apt-get install -y rpi-connect
    loginctl enable-linger "$USER_NAME" >/dev/null 2>&1 || true
    systemctl --user enable --now rpi-connect 2>&1 | sed 's/^/    /' || true
    echo
    echo "  To finish: run  rpi-connect signin  and follow the URL in your browser."
    echo "  Then visit https://connect.raspberrypi.com/devices to manage this Pi."
    echo "  Skip this step on future runs by exporting SKIP_RPI_CONNECT=1."
else
    log "  Skipped (SKIP_RPI_CONNECT=1 or package unavailable)."
fi

IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
echo
log "Done."
log "Admin:    http://${IP:-<pi-ip>}:8080/admin"
log "Display:  http://localhost:8080/  (auto-launches after reboot)"
log "Update:   bash scripts/update.sh"
log "Logs:     journalctl --user -u palipints.service -f"
