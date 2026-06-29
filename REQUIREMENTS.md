# PaliPints — Requirements

## Context

Palindrome Brewing Co needs a digital draft list shown on a horizontally-mounted TV driven by a Raspberry Pi. Two surfaces:

1. **Admin web app** — a local-network site for staff to manage taps, prices, specials, and display settings.
2. **TV display app** — a fullscreen page rendered in Chromium kiosk mode that shows the current draft list, grouped by beer style category, with a rotating multi-page layout when there are more taps than fit on one page. One primary Pi hosts the Flask app and drives one TV; additional read-only client Pis (e.g. a Pi Zero 2 W) can mirror the same display on extra TVs by running a thin Chromium kiosk pointed at the primary's LAN URL — no extra services or code on the client.

The system should make day-to-day tap turnover fast: type a beer name, let it autofill from a web lookup, tweak if needed, save — the TV updates within seconds.

## Goals

- Staff can update any tap in under 30 seconds.
- TV view always reflects the current state without manual refresh.
- Works offline once images are cached (network outage doesn't blank the TV).
- Runs on a stock Raspberry Pi 4 with Raspberry Pi OS.

## Non-goals

- No POS / payment integration.
- No customer-facing app.
- No multi-venue support — one Pi, one venue, one home brewery.
- No inventory tracking (kegs left, etc.).
- No authentication or CSRF protection on the admin UI — assumes a trusted LAN. If the kiosk is ever exposed beyond a local network, add auth before doing so.

---

## Functional Requirements

### FR1. Admin web UI (LAN-only, no auth)

Served by the same Python process that serves the display. Bound to the Pi's LAN IP.

**FR1.1 Tap list page** — primary admin screen.
- Shows up to 22 tap rows, each editable inline:
  - Tap number (1–22, fixed, only the rows in use are "active")
  - Brewery (text, **defaults to home brewery** when adding a new beer; matched against the home-brewery setting via case-insensitive word-boundary prefix, so `Palindrome` matches `Palindrome Brewing Co`)
  - Beer name
  - Style category (dropdown: IPA & Pale Ales, Sour & Wild Ales, Stout & Porter, Lager & Pilsner, Belgian & Farmhouse, Historical & Specialty)
  - Sub-style (free text, e.g. "American IPA", "Imperial Stout")
  - ABV (%)
  - IBU
  - Location (free text, e.g. "London, UK"; auto-fills from the home-brewery location setting on new home-brewery taps)
  - Prices (GBP) — four optional kinds, each with an enable checkbox + value:
    1/3 pint, 1/2 pint, pint, takeaway. Only enabled prices show on the display.
  - "Active" toggle (inactive taps are hidden from the display)
- The four-column layout vertically aligns inputs row-by-row regardless of which labels carry a required `*` marker.
- A tap can only be saved as **active** when brewery, beer name, ABV, and at least one enabled price are filled in.
- **Search the web** button per row — fetches name, brewery, sub-style, ABV, IBU, location, the brewery's logo, **and the beer's own icon** (saved as the per-tap image override). All fields stay editable after autofill.
- **Clear tap** button per row — wipes all details for that tap after confirmation.
- **Unsaved-changes guard** — editing any tap field arms a `beforeunload` prompt that warns before reload / close / navigation. Cleared on successful bulk save, on Clear-tap submit, and on per-tap image-upload submit so intentional actions don't double-prompt.
- Drag-to-reorder is **not** required; tap number is the canonical order.

**FR1.2 Settings page**
- **Home brewery name** (default `Palindrome Brewing Co`) — used as the default for new taps and as the source-of-truth identity for the home-brewery match.
- **Home brewery location** (default `London, UK`) — pre-fills the Location field on new home-brewery taps and overrides whatever the web scraper returns for the home brewery's own beers.
- **Home brewery logo** (file upload) — replaces the scraped logo for any beer brewed by the home brewery.
- **Day / night switching toggle** (default off) — gates the whole feature.
  - When off: a single "Theme" picker is shown.
  - When on: separate "Day theme" and "Night theme" pickers appear, plus a "Location & times" block (lat/lon with IP auto-detect + manual `HH:MM` overrides). Sunrise/sunset is cached weekly from sunrise-sunset.org.
- **Theme picker** — nine themes (three legacy + Palindrome 1/2/3 + Palindrome 4/5/6 with PP Fragment Glare + Alegreya Sans). Each card previews its display heading font.
- **Display style**: **Brewery logo** OR **Beer color** (radio).
- **Beers per page** on the display (default 12; range 6–14).
- **Page rotation interval** in seconds (default 15).
- **Display scale** (%) — multiplier on top of the auto-fit (50–150%, default 100). Lets staff nudge for bezels.
- **Tap list ordering** (lives inside the Display fieldset) — by tap number, grouped by style category (default), or home-brewery first with a "Guest Beers" separator.
- **Default color per style category** — shown only when display style is set to "Beer color disc".
- **Holiday fun** — toggle to enable seasonal Twemoji icons on the display; a gallery previews each icon (Christmas, New Year's, Valentine's, St Patrick's, April Fools', Easter, 4th July, Halloween, Thanksgiving).
- **External beer database** — sync interval + source (mock JSON or a future Postgres adapter).
- **Database backup / restore** — manual backup-now button + restore-from-latest with an online SQLite-backup API for safety.

All form labels inside `.settings-form` use a uniform 14-px size for visual consistency.

**FR1.3 Specials page**
- Add/edit/remove a structured list of specials, each with:
  - Title (e.g. "IPA Flight")
  - Description (optional, e.g. "4 × 1/3 pint")
  - Price (GBP)
- Specials render in a fixed panel on the **top-right** of the TV display and do not rotate with the tap pages.

**FR1.4 Events page**
- Add/edit/remove up to **3** events. Each event has:
  - Name (required)
  - Date (optional)
  - Location (optional, free text)
  - URL (optional — when present, rendered as a QR code on the display so customers can scan it)
- Per-event "Active" toggle — inactive events stay saved but don't appear on the display.
- Events render in a fixed panel on the right of the TV display, **directly under the Specials panel**, in the same styling. The whole panel is hidden when there are no active events.

**FR1.5 Beer library page**
- Local mirror of beers from an external source (mock JSON in dev; future Postgres adapter). Used by the Beer-name typeahead on the Tap page so popular beers fill in without a web round-trip.
- Per-row local edit + reset-to-source. Reset polls the sync worker until completion before reloading, so the UI reflects the resynced row deterministically (no fixed-timer race).
- Manual "Sync now" button with a status indicator showing last sync time + outcome.

### FR2. TV display view

Single fullscreen page at `/`. Designed for **1920×1080 horizontal**. Auto-polls a JSON state endpoint and re-renders on change.

- Header: "DRAFT LIST" title + small Palindrome logo.
- Body: beers grouped under **style category** headings, in this order:
  1. IPA & Pale Ales
  2. Sour & Wild Ales
  3. Stout & Porter
  4. Lager & Pilsner
  5. Belgian & Farmhouse
  6. Historical & Specialty
- Each beer row shows: tap number, brewery, beer name, sub-style, ABV, IBU, location, the enabled prices (any subset of ⅓ / ½ / pint / takeaway in GBP), and either the brewery logo (logo style) or a colored disc/strip in the beer's color (color style).
- Prices align in fixed columns across all rows. Column headers (⅓ / ½ / pint / takeaway) appear once at the top of the list — only columns that have at least one beer using that price kind are shown.
- If active taps exceed `beers_per_page`, beers split across pages and the display rotates between pages every `page_rotation_interval` seconds with a cross-fade transition. Pagination indicator: "Page N of M" centered along the bottom.
- **Specials panel** in the top-right corner: persistent, does not rotate with tap pages. Hidden if no specials are configured.
- **Events panel** below the Specials panel (top-right column): persistent, does not rotate. Each active event shows name, date (dd/mm/yyyy), location, and a QR code generated from the URL. Hidden if no active events.
- **Holiday overlay** (when enabled) — small Twemoji shown in the top-right of the header.
- Bottom-right shows the current date + time, refreshed client-side every second.
- Empty state: if zero active taps, show the Palindrome logo centered with "Coming soon".

### FR3. Web search integration

The "Search the web" button on each tap row autofills brewery, beer name, sub-style, ABV, IBU, location, the brewery logo, and the beer's own icon from a public beer source (currently Untappd).

- Returns up to 5 matches; admin picks one to apply.
- Caches search results and parsed detail for 24h to avoid hammering the source.
- Downloads brewery logos to `data/images/breweries/<slug>.<ext>` (cached indefinitely; admin can clear by deleting the file).
- Downloads per-beer icons to `data/images/beers/<slug>.<ext>` and stores the relative path on the tap as `image_override_path`. Attempts the medium Untappd variant first, falls back to small on 403/404.
- Outbound requests send a full set of browser-identity headers: a Chrome 149 / Windows 10 `User-Agent` plus the matching `Sec-Ch-Ua`, `Sec-Ch-Ua-Mobile`, `Sec-Ch-Ua-Platform`, and `Accept-Language` Client Hints. Polite 1 s minimum delay between scraper requests.
- Brewery location is pulled from the schema.org JSON-LD `address` block embedded on every brewery page (`addressLocality, addressRegion`), with the legacy CSS selectors retained as a fallback.
- When the result's brewery is recognised as the home brewery (via the word-boundary match), the scraped location is overridden with the operator-configured **home_brewery_location** setting — Untappd's data is frequently incomplete for the home brewery, and the operator's setting is the source of truth for their own beers.
- Failure mode: surfaces a non-blocking warning in the admin UI — staff can still fill the row by hand.

Implementation note: the public-beer-page scraper is encapsulated in `app/internetscraping.py` so the data source can be swapped without touching the rest of the app.

### FR4. Image fallbacks (in priority order)

When the display style is "Brewery logo", the resolver walks this chain and uses the first hit:

1. **Per-tap image override** (`tap.image_override_path`) — set either via the per-tap upload form or auto-populated from a web-search beer icon.
2. **Home brewery uploaded logo** (`settings.home_brewery_logo_path`) — only used when the tap's brewery matches the home-brewery setting via `is_home_brewery()` (word-boundary prefix, case-insensitive).
3. **Cached brewery logo** from a previous web-search lookup (under `data/images/breweries/`).
4. **Bundled home-brewery wordmark** (`static/img/palindrome-logo.svg`) — only used when the tap brewery matches the home brewery and no other image is available.
5. **Per-theme hop SVG fallback** (`static/img/hop-*.svg`) — final fallback for guest breweries with no cached logo. Each theme picks a hop colour suited to its palette.

### FR5. Live updates

Display polls `/api/state` every 5 seconds. State endpoint returns a JSON snapshot of all active taps + specials + events + settings + active holiday. The display re-renders only if `version_hash` has changed.

The active holiday key is included in the hashed payload, so the kiosk reloads automatically when the date rolls into or out of a holiday window — even when no admin change has been made.

### FR6. QR codes for events

Event URLs are rendered as scannable QR codes server-side via the `/qr?data=…` endpoint (SVG output). The display embeds these directly so the codes scale crisply at any TV resolution.

---

## Color defaults (style category → hex)

| Category | Default |
|---|---|
| IPA & Pale Ales | `#E89923` (amber-gold) |
| Sour & Wild Ales | `#D63B5E` (rose-red) |
| Stout & Porter | `#2A1810` (near-black brown) |
| Lager & Pilsner | `#F5D547` (pale gold) |
| Belgian & Farmhouse | `#C77B2D` (burnt orange) |
| Historical & Specialty | `#6E1A28` (burgundy) |

---

## Brand palette (Palindrome themes)

| Token | Hex | Used as |
|---|---|---|
| Main green | `#93BB48` | Accent in all six Palindrome themes |
| Light green | `#E9F1DA` | Off-white background / contrast surface |
| Dark green | `#688531` | Heading / deep accent |
| Vampire black | `#080808` | Text / dark background |

---

## Brand typography

**Palindrome 1 / 2 / 3** — `Bebas Neue` (display) + `Inter` (body), both Google Fonts.

**Palindrome 4 / 5 / 6** —
- Display headings: `PP Fragment Glare ExtraBold` (Pangram Pangram, commercial — free personal-use trial at https://pangrampangram.com/products/fragment-glare). Falls back to `Archivo Black` from Google Fonts.
- Body: `Alegreya Sans` (Regular / Bold / Black, SIL OFL).
- Files live under `app/static/fonts/`; see [`app/static/fonts/README.md`](app/static/fonts/README.md) for the licence note and sourcing instructions.

---

## Non-functional requirements

- **Platform**: Raspberry Pi 4, 2GB+, Raspberry Pi OS (Bookworm, 64-bit).
- **Python**: 3.11+.
- **Browser**: Chromium in kiosk mode, started on boot, pointed at `http://localhost:8080/`.
- **Service**: Flask app runs as a `systemd` user service so it restarts on crash and starts on boot.
- **Storage**: SQLite file at `data/palipints.db`. Images on disk under `data/images/` (`breweries/`, `uploads/`, `beers/`).
- **Schema migrations**: additive only, applied lazily on `init_db()`. Existing rows are backfilled where it preserves user intent (e.g. `day_night_auto = 1` when an install already had distinct day/night themes).
- **Trust boundary**: LAN-only. No authentication or CSRF protection on admin routes; do not expose this app to the public internet.
- **Multi-display**: one primary Pi hosts the Flask service; N read-only kiosk clients on the same LAN render the same `/` URL. The primary's URL is stored on each client in `~/.palipints-client-url`. Clients run Chromium only — no Flask, no DB, no app code execution. Page-rotation timers are per-client so screens may drift; synchronised rotation is explicitly **not** a requirement at this stage.
- **Offline operation**: the display and admin must work fully without internet. All typefaces are self-hosted under `app/static/fonts/` (no Google Fonts CDN at runtime), all images are cached on disk after a one-time download, holidays/QR codes are generated locally, and the SQLite DB is local. Internet is only required for opt-in features the operator triggers explicitly (web search, IP geolocation, the weekly sunrise/sunset refresh, and any networked beer-library source). The kiosk also uses `--incognito` so no browser cache accumulates between sessions — combined with self-hosted fonts, every Chromium relaunch renders correctly even with the WAN unavailable.
