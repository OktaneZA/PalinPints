# PaliPints — Requirements

## Context

Palindrome Brewing Co needs a digital draft list shown on a horizontally-mounted TV driven by a Raspberry Pi. Two surfaces:

1. **Admin web app** — a local-network site for staff to manage taps, prices, specials, and display settings.
2. **TV display app** — a fullscreen page rendered in Chromium kiosk mode that shows the current draft list, grouped by beer style category, with a rotating multi-page layout when there are more taps than fit on one page.

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

---

## Functional Requirements

### FR1. Admin web UI (LAN-only, no auth)

Served by the same Python process that serves the display. Bound to the Pi's LAN IP.

**FR1.1 Tap list page** — primary admin screen.
- Shows up to 22 tap rows, each editable inline:
  - Tap number (1–22, fixed, only the rows in use are "active")
  - Brewery (text, **defaults to home brewery** when adding a new beer)
  - Beer name
  - Style category (dropdown: IPA & Pale Ales, Sour & Wild Ales, Stout & Porter, Lager & Pilsner, Belgian & Farmhouse, Historical & Specialty)
  - Sub-style (free text, e.g. "American IPA", "Imperial Stout")
  - ABV (%)
  - IBU
  - Location (free text, e.g. "Milwaukee, WI")
  - Prices (GBP) — four optional kinds, each with an enable checkbox + value:
    1/3 pint, 1/2 pint, pint, takeaway. Only enabled prices show on the display.
  - Beer color override (color picker; blank = use category default)
  - Image override (file upload; blank = use scraped/fallback)
  - "Active" toggle (inactive taps are hidden from the display)
- A tap can only be saved as **active** when brewery, beer name, ABV, and at least one enabled price are filled in.
- "Search the web" button per row — fetches name, brewery, sub-style, ABV, IBU, location, and the brewery's logo. All fields stay editable after autofill.
- Drag-to-reorder is **not** required; tap number is the canonical order.

**FR1.2 Settings page**
- Home brewery name (used as the default for new taps; defaults to "Palindrome Brewing Co").
- Home brewery logo (file upload — replaces the scraped logo for any beer brewed by the home brewery).
- Display style: **Brewery logo** OR **Beer color** (radio).
- Theme picker (six themes — see [README.md](README.md)).
- Beers per page on the display (default 12; range 6–14).
- Page rotation interval in seconds (default 15).
- Default color per style category (six color pickers; pre-populated with the palette in §"Color defaults").

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
- If active taps exceed `beers_per_page`, beers split across pages and the display rotates between pages every `page_rotation_interval` seconds. Pagination indicator: "Page N of M" centered along the bottom.
- **Specials panel** in the top-right corner: persistent, does not rotate with tap pages. Hidden if no specials are configured.
- **Events panel** below the Specials panel (top-right column): persistent, does not rotate. Each active event shows name, date, location, and a QR code generated from the URL. Hidden if no active events.
- Bottom-right shows the current date + time, refreshed client-side every second.
- Empty state: if zero active taps, show the Palindrome logo centered with "Coming soon".

### FR3. Web search integration

The "Search the web" button on each tap row autofills brewery, beer name, sub-style, ABV, IBU, location and the brewery logo from a public beer source.

- Returns up to 5 matches; admin picks one to apply.
- Caches search results and parsed detail for 24h to avoid hammering the source.
- Downloads brewery logos to `data/images/breweries/<slug>.<ext>` (cached indefinitely; admin can clear by deleting the file).
- Sets a polite User-Agent and a 1s delay between outbound requests.
- Failure mode: surfaces a non-blocking warning in the admin UI — staff can still fill the row by hand.

Implementation note: the current backend scrapes public Untappd pages, encapsulated in `app/untappd.py` so the data source can be swapped without touching the rest of the app.

### FR4. Image fallbacks (in priority order)

When the display style is "Brewery logo":
1. Admin-uploaded image override on the tap (if any).
2. Home brewery logo (from settings) if the beer's brewery == home brewery.
3. Cached brewery logo from a previous web lookup.
4. Bundled hop silhouette PNG (`static/img/hop-fallback.png`).

### FR5. Live updates

Display polls `/api/state` every 5 seconds. State endpoint returns a JSON snapshot of all active taps + specials + events + settings. The display re-renders only if the state hash has changed.

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

## Non-functional requirements

- **Platform**: Raspberry Pi 4, 2GB+, Raspberry Pi OS (Bookworm, 64-bit).
- **Python**: 3.11+.
- **Browser**: Chromium in kiosk mode, started on boot, pointed at `http://localhost:8080/`.
- **Service**: Flask app runs as a `systemd` user service so it restarts on crash and starts on boot.
- **Storage**: SQLite file at `data/palipints.db`. Images on disk under `data/images/`.
