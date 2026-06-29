# PaliPints

Digital draft list for Palindrome Brewing Co — a Python/Flask app that runs on a Raspberry Pi, drives a horizontal TV via HDMI in Chromium kiosk mode, and exposes a LAN-only admin web UI for managing taps, prices, specials, and upcoming events (with scannable QR codes).

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
git clone https://github.com/OktaneZA/PalinPints.git ~/PaliPints
cd ~/PaliPints
bash scripts/install.sh
```

`install.sh` creates the virtualenv, installs deps, sets up a `systemd --user` service, configures Chromium to launch in kiosk mode pointing at `http://localhost:8080/` on boot, and offers to set up Raspberry Pi Connect for remote management.

Update later with `bash scripts/update.sh`.

### Multiple displays

To drive a second TV from a separate Pi (typically a **Pi Zero 2 W**), run [`scripts/install-client.sh`](scripts/install-client.sh) on the second Pi instead of `install.sh`. The client installer skips Python / Flask / systemd entirely — it only configures a Chromium kiosk pointed at the primary Pi's URL. The two TVs mirror identical content (page rotation runs independently per screen). Full walkthrough in **[INSTALL.md §10](INSTALL.md)**.

## Style categories

- IPA & Pale Ales
- Sour & Wild Ales
- Stout & Porter
- Lager & Pilsner
- Belgian & Farmhouse
- Historical & Specialty

## Display themes

Nine themes are available, switchable from the admin Settings page. Each works with both display modes (brewery logo or beer-color disc):

| Theme | Look |
|---|---|
| Marble | Light marble background, premium feel |
| Neon | Black with pink/cyan gradient border, glowing accents |
| Chalkboard | Slate background with chalk-style text |
| Palindrome 1 | Light off-white green, brand palette (Bebas Neue) |
| Palindrome 2 | Vampire black with main-green pop (Bebas Neue) |
| Palindrome 3 | Green-forward, brand-immersive (Bebas Neue) |
| Palindrome 4 | Light brand, PP Fragment Glare + Alegreya Sans |
| Palindrome 5 | Dark brand, PP Fragment Glare + Alegreya Sans |
| Palindrome 6 | Green-forward, PP Fragment Glare + Alegreya Sans |

The theme picker on the Settings page previews each theme's heading font.

### Day / night switching

There is a single toggle on the Settings page — **Switch theme automatically between day and night** — that gates the whole feature.

- **Off (default)** — the display always uses one theme. The Settings page shows a single "Theme" picker.
- **On** — picks `day_theme` between sunrise (or the day-start override) and 30 min before sunset (or the night-start override), and `night_theme` otherwise. The Settings page shows separate Day-theme / Night-theme pickers and a Location & times block (lat/lon auto-detect from IP, plus manual HH:MM overrides). Sunrise/sunset is looked up once a week from sunrise-sunset.org.

## Brand fonts

Every typeface the app uses is **self-hosted** under [`app/static/fonts/`](app/static/fonts/) — the display loads no fonts from any CDN at runtime. The Palindrome 4 / 5 / 6 themes use **PP Fragment Glare ExtraBold** for headings (commercial Pangram Pangram font — free personal-use trial available [here](https://pangrampangram.com/products/fragment-glare)) and **Alegreya Sans** for body. Other themes use Bebas Neue, Inter, Playfair Display, Caveat, Special Elite, or Archivo Black — all bundled as open-source `.woff2` files. See the [fonts README](app/static/fonts/README.md) for the full inventory and licensing.

## Branding

The Palindrome wordmark and circular seal are bundled in `app/static/img/`. To override the home brewery logo at runtime, upload a new file via the admin Settings page — it gets stored under `data/images/uploads/` and used for any beer brewed by the home brewery (matched via word-boundary prefix, so the setting `Palindrome` matches a tap with brewery `Palindrome Brewing Co`).

## Tap image fallback chain

When the display renders a tap in **logo** mode, it walks this chain top-to-bottom and uses the first available image:

1. **Per-tap image override** — auto-set from the web-search result when you pick a beer (Untappd beer icon, downloaded under `data/images/beers/`). Can also be set manually via the per-tap upload form.
2. **Home brewery logo** — when the tap brewery is recognised as the home brewery and a logo was uploaded on the Settings page.
3. **Bundled home-brewery wordmark** — for home-brewery taps with no other image.
4. **Cached brewery logo** — downloaded during a previous web-search lookup, under `data/images/breweries/`.
5. **Theme hop fallback** — the small hop SVG bundled in `static/img/`, picked per-theme.

## Holiday overlay

The display shows a Twemoji-based holiday icon in the top-right around Christmas, New Year's, Valentine's, St Patrick's, April Fools', Easter, 4th of July, Halloween, and Thanksgiving. Toggle from the Settings page. A gallery preview of every icon is shown next to the toggle.

The state snapshot includes the active holiday in its version hash, so a kiosk left running overnight automatically reloads when the date rolls in or out of a holiday window — no admin intervention required.

## Project layout

```
app/                Flask app: routes, templates, static assets
  static/css/       Layout, theme stylesheets, shared @font-face (fonts.css)
  static/fonts/     PP Fragment Glare ExtraBold + Alegreya Sans (see README)
  static/img/       Bundled brand assets, hop fallbacks, holiday Twemoji
  templates/        Jinja2 templates (admin + display)
data/               SQLite DB and uploaded/cached images (gitignored)
  images/uploads/   Per-tap image uploads
  images/breweries/ Cached brewery logos from web search
  images/beers/     Per-beer icons downloaded by web search
scripts/            Pi installer, systemd unit, kiosk autostart
```
