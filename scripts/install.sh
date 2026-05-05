#!/usr/bin/env bash
# PaliBeerView Pi installer.
# Run as the user that will own the kiosk session (typically `pi`).
# Usage: bash scripts/install.sh

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
USER_NAME="$(id -un)"
SYSTEMD_USER_DIR="$HOME/.config/systemd/user"
AUTOSTART_DIR="$HOME/.config/autostart"

echo ">>> PaliBeerView install for user $USER_NAME at $PROJECT_DIR"

# 1. System deps (Pillow needs libjpeg/zlib; Chromium for kiosk)
echo ">>> Installing apt packages (sudo required)..."
sudo apt-get update
sudo apt-get install -y python3 python3-venv python3-pip \
    libjpeg-dev zlib1g-dev \
    chromium-browser xdotool unclutter

# 2. Python venv
echo ">>> Creating Python virtualenv..."
cd "$PROJECT_DIR"
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt

# 3. systemd --user service for the Flask app
echo ">>> Installing systemd user service..."
mkdir -p "$SYSTEMD_USER_DIR"
sed "s|@PROJECT_DIR@|$PROJECT_DIR|g" "$PROJECT_DIR/scripts/palibeerview.service" \
    > "$SYSTEMD_USER_DIR/palibeerview.service"

# Enable lingering so the user service starts at boot without login
sudo loginctl enable-linger "$USER_NAME"

systemctl --user daemon-reload
systemctl --user enable palibeerview.service
systemctl --user restart palibeerview.service

# 4. Chromium kiosk autostart
echo ">>> Installing Chromium kiosk autostart..."
mkdir -p "$AUTOSTART_DIR"
cp "$PROJECT_DIR/scripts/kiosk-autostart.sh" "$HOME/palibeerview-kiosk.sh"
chmod +x "$HOME/palibeerview-kiosk.sh"

cat > "$AUTOSTART_DIR/palibeerview-kiosk.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=PaliBeerView Kiosk
Exec=/bin/bash $HOME/palibeerview-kiosk.sh
X-GNOME-Autostart-enabled=true
EOF

echo ">>> Done."
echo ">>> Admin: http://$(hostname -I | awk '{print $1}'):8080/admin"
echo ">>> Display will appear after next reboot, or run: bash ~/palibeerview-kiosk.sh"
