#!/usr/bin/env bash
# Launch Chromium in fullscreen kiosk mode pointing at a *remote* PaliPints
# server (the primary Pi). Used on a Pi Zero 2 W (or any second Pi) acting as
# a thin display-only client. The primary's URL is read from
# ~/.palipints-client-url at boot so the operator can change it later without
# re-running the installer.

set -e

DEFAULT_URL="http://palipints.local:8080/"
URL_FILE="$HOME/.palipints-client-url"

# Resolve the target URL. The first non-empty, non-comment line in the file
# wins. If the file is missing or empty, fall back to the mDNS default.
URL=""
if [ -f "$URL_FILE" ]; then
    URL="$(grep -vE '^\s*(#|$)' "$URL_FILE" | head -n 1 | tr -d '[:space:]')"
fi
URL="${URL:-$DEFAULT_URL}"

# Disable screen blanking / DPMS
xset s off || true
xset -dpms || true
xset s noblank || true

# Hide the cursor when idle
unclutter -idle 0 -root &

# Wait for the primary's display endpoint to respond. 60s is enough for the
# usual case where both Pis power on together and the primary is still
# booting Flask. After 60s we launch Chromium anyway — it will show a
# connection-error page that auto-recovers when the primary comes back.
for i in $(seq 1 60); do
  if curl -sf --max-time 3 "$URL" >/dev/null; then break; fi
  sleep 1
done

# Pick whichever Chromium binary exists on this Pi OS image
BROWSER=""
if command -v chromium-browser >/dev/null; then BROWSER="chromium-browser"
elif command -v chromium >/dev/null; then BROWSER="chromium"
fi

if [ -z "$BROWSER" ]; then
  echo "No Chromium binary found. Install chromium-browser." >&2
  exit 1
fi

exec "$BROWSER" \
  --kiosk \
  --incognito \
  --noerrdialogs \
  --disable-infobars \
  --disable-session-crashed-bubble \
  --disable-translate \
  --check-for-update-interval=31536000 \
  --overscroll-history-navigation=0 \
  --autoplay-policy=no-user-gesture-required \
  "$URL"
