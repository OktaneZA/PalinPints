#!/usr/bin/env bash
# PaliPints kiosk client installer.
#
# For a *secondary* Pi (typically a Pi Zero 2 W) that should display the
# PaliPints draft list on a second monitor by pointing a Chromium kiosk at
# the primary Pi's URL. This installer skips Python, Flask, the venv, and the
# systemd app service — only Chromium + a kiosk autostart are configured.
#
# Run as the user that owns the desktop session (typically `pi`).
# Usage: bash scripts/install-client.sh
#
# Idempotent: safe to re-run. Use scripts/update.sh for routine updates.

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
USER_NAME="$(id -un)"
AUTOSTART_DIR="$HOME/.config/autostart"
URL_FILE="$HOME/.palipints-client-url"
DEFAULT_URL="http://palipints.local:8080/"

log() { echo ">>> $*"; }
log "PaliPints client install for user $USER_NAME at $PROJECT_DIR"

# Sanity check: must be run on the Pi (or another Linux box), not from Windows.
if ! command -v apt-get >/dev/null; then
    echo "This installer expects apt-get (Raspberry Pi OS / Debian)." >&2
    exit 1
fi

# 1. Capture the primary Pi's URL.
log "Configuring the primary PaliPints URL."
CURRENT=""
if [ -f "$URL_FILE" ]; then
    CURRENT="$(grep -vE '^\s*(#|$)' "$URL_FILE" | head -n 1 | tr -d '[:space:]' || true)"
fi
PROMPT_DEFAULT="${CURRENT:-$DEFAULT_URL}"
echo
echo "The Pi Zero will open this URL in Chromium on every boot. Examples:"
echo "  http://palipints.local:8080/   (mDNS — works on most home LANs)"
echo "  http://192.168.1.42:8080/      (static IP / DHCP reservation)"
echo
echo -n "Primary PaliPints URL [${PROMPT_DEFAULT}]: "
read -r INPUT_URL || INPUT_URL=""
INPUT_URL="$(echo "${INPUT_URL}" | tr -d '[:space:]')"
PRIMARY_URL="${INPUT_URL:-$PROMPT_DEFAULT}"

# Tolerant validation: just make sure it looks like an http(s) URL.
if ! echo "$PRIMARY_URL" | grep -qE '^https?://[^[:space:]]+$'; then
    echo "URL '$PRIMARY_URL' doesn't look like http(s)://… — aborting." >&2
    exit 1
fi

log "Using primary URL: $PRIMARY_URL"
cat > "$URL_FILE" <<EOF
# PaliPints client target — read by ~/palipints-kiosk.sh at boot.
# Edit this file (and reboot, or pkill chromium and re-launch the kiosk) to
# point this client at a different primary server.
$PRIMARY_URL
EOF
chmod 600 "$URL_FILE"

# 2. System deps — only the kiosk side. No python, no libjpeg.
log "Installing apt packages (sudo required)..."
sudo apt-get update

if apt-cache show chromium >/dev/null 2>&1; then
    CHROMIUM_PKG=chromium
elif apt-cache show chromium-browser >/dev/null 2>&1; then
    CHROMIUM_PKG=chromium-browser
else
    echo "Neither 'chromium' nor 'chromium-browser' is available via apt." >&2
    echo "Run 'sudo apt-get update' and check your apt sources." >&2
    exit 1
fi
log "Using Chromium package: $CHROMIUM_PKG"

sudo apt-get install -y --no-install-recommends \
    "$CHROMIUM_PKG" xdotool unclutter \
    curl ca-certificates

# 3. Enable lingering so the autostart desktop fires at boot without login.
sudo loginctl enable-linger "$USER_NAME"

# 4. Chromium kiosk autostart — same target paths as the primary installer
# so update.sh and the troubleshooting recipes work identically on both.
log "Installing Chromium kiosk autostart..."
mkdir -p "$AUTOSTART_DIR"
cp "$PROJECT_DIR/scripts/kiosk-autostart-client.sh" "$HOME/palipints-kiosk.sh"
chmod +x "$HOME/palipints-kiosk.sh"

cat > "$AUTOSTART_DIR/palipints-kiosk.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=PaliPints Kiosk
Exec=/bin/bash $HOME/palipints-kiosk.sh
X-GNOME-Autostart-enabled=true
EOF

echo
log "Done."
log "Primary URL:   $PRIMARY_URL"
log "URL config:    $URL_FILE   (edit + reboot to change)"
log "Launcher:      $HOME/palipints-kiosk.sh"
log "Update:        bash scripts/update.sh"
echo
log "Reboot the Pi to bring up the kiosk:  sudo reboot"
