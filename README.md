# PalinPints

Digital draft list for Palindrome Brewing Co — a Python/Flask app that runs on a Raspberry Pi, drives a horizontal TV via HDMI in Chromium kiosk mode, and exposes a LAN-only admin web UI for managing taps, prices, and specials.

See [REQUIREMENTS.md](REQUIREMENTS.md) for the full spec.

## Quick start (development, any platform)

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS/Linux
source .venv/bin/activate

pip install -r requirements.txt
python run.py
```

Then open:

- Display: http://localhost:8080/
- Admin:   http://localhost:8080/admin

The SQLite DB and image cache live under `data/` and are auto-created on first run.

## Pi deployment

For the full walkthrough — flashing the SD card with WiFi pre-configured, first-boot SSH, install, updates, Raspberry Pi Connect, changing WiFi later, and troubleshooting — see **[INSTALL.md](INSTALL.md)**.

Short version, once the Pi is on the network:

```bash
git clone https://github.com/OktaneZA/PalinPints.git ~/PalinPints
cd ~/PalinPints
bash scripts/install.sh
```

`install.sh` creates the virtualenv, installs deps, sets up a `systemd --user` service, configures Chromium to launch in kiosk mode pointing at `http://localhost:8080/` on boot, and offers to set up Raspberry Pi Connect for remote management.

Update later with `bash scripts/update.sh`.

## Style categories

- IPA & Pale Ales
- Sour & Wild Ales
- Stout & Porter
- Lager & Pilsner
- Belgian & Farmhouse
- Historical & Specialty

## Display themes

Six themes are available, switchable from the admin Settings page. Each works with both display modes (brewery logo or beer-color disc):

| Theme | Look |
|---|---|
| Marble | Light marble background, premium feel |
| Neon | Black with pink/cyan gradient border, glowing accents |
| Chalkboard | Slate background with chalk-style text |
| Palindrome 1 | Light off-white green, brand palette |
| Palindrome 2 | Vampire black with main-green pop |
| Palindrome 3 | Green-forward, brand-immersive |

Screenshots of each are in [`screenshots/`](screenshots/).

## Branding

The Palindrome wordmark and circular seal are bundled in `app/static/img/`. To override the home brewery logo at runtime, upload a new file via the admin Settings page — it gets stored under `data/images/uploads/` and used for any beer brewed by the home brewery.

## Project layout

```
app/                Flask app: routes, templates, static assets
  static/css/       Layout + theme stylesheets
  static/img/       Bundled brand assets
  templates/        Jinja2 templates (admin + display)
data/               SQLite DB and uploaded/cached images (gitignored)
scripts/            Pi installer, systemd unit, kiosk autostart
screenshots/        Reference screenshots of each theme
```
