#!/usr/bin/env bash
# Launch Chromium in fullscreen kiosk mode pointing at the local display.
# Hides cursor, disables screen blanking. Waits for the Flask app to come up.

set -e

URL="http://localhost:8080/"

# Disable screen blanking / DPMS
xset s off || true
xset -dpms || true
xset s noblank || true

# Hide the cursor when idle
unclutter -idle 0 -root &

# Wait for the Flask app to respond
for i in $(seq 1 60); do
  if curl -sf "$URL" >/dev/null; then break; fi
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
  --noerrdialogs \
  --disable-infobars \
  --disable-session-crashed-bubble \
  --disable-translate \
  --check-for-update-interval=31536000 \
  --overscroll-history-navigation=0 \
  --autoplay-policy=no-user-gesture-required \
  "$URL"
