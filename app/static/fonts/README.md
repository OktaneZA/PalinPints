# Brand fonts (self-hosted)

This directory holds every typeface the app needs. The display **does not
load any fonts from Google or any other CDN at runtime** — the kiosk is
fully offline-capable. `@font-face` declarations live in
[`../css/fonts.css`](../css/fonts.css).

Each Google font is shipped in two subsets:

- `latin` — basic English + Western European chars; loaded by default
- `latin-ext` — extended Latin (Polish, Czech, Vietnamese, etc.); loaded
  lazily only when a glyph in that range is actually rendered

## Files

### Commercial — Pangram Pangram

| File                              | Used as                | Licence                                  |
| --------------------------------- | ---------------------- | ---------------------------------------- |
| `PPFragment-GlareExtraBold.otf`   | display headings (4-6) | **Pangram Pangram — commercial / trial** |

### Open-source — SIL Open Font Licence (safe to redistribute)

| Family                | Weights         | Files (each in latin + latin-ext) |
| --------------------- | --------------- | --------------------------------- |
| Alegreya Sans         | 400, 500, 700, 800 | `AlegreyaSans-{400,500,700,800}-{latin,latin-ext}.woff2` |
| Archivo Black         | 400             | `ArchivoBlack-400-{latin,latin-ext}.woff2`         |
| Bebas Neue            | 400             | `BebasNeue-400-{latin,latin-ext}.woff2`            |
| Caveat                | 500, 700        | `Caveat-{500,700}-{latin,latin-ext}.woff2`         |
| Inter                 | 400, 500, 700   | `Inter-{400,500,700}-{latin,latin-ext}.woff2`      |
| Playfair Display      | 700, 900        | `PlayfairDisplay-{700,900}-{latin,latin-ext}.woff2`|
| Special Elite         | 400             | `SpecialElite-400-{latin,latin-ext}.woff2`         |

All of the above were downloaded directly from Google Fonts (which serves
them under the SIL Open Font Licence) and are safe to commit and
redistribute. ~1 MB total on disk.

## ⚠️ PP Fragment Glare licensing

**PP Fragment Glare cannot be used in production without a paid licence
from Pangram Pangram.** For personal / non-commercial projects, Pangram
Pangram distributes a free trial version of this typeface — sign up for a
free account on their site to download it.

- Product page (paid + free trial): https://pangrampangram.com/products/fragment-glare
- Pangram Pangram licences: https://pangrampangram.com/pages/licenses

If you are deploying this kiosk somewhere customers will see it, that is
a commercial use and you will need to purchase the appropriate licence —
the free trial does **not** cover commercial display. Remove the `.otf`
from this folder if you are unsure; the themes will fall back gracefully
to `Archivo Black` (which is also bundled here under OFL, no licence
concerns).

The file checked into the repo is included as a convenience for the
project owner (who holds the appropriate licence/trial registration).
Anyone forking this repo needs to source their own copy under their own
licence terms.

## Re-syncing the open-source fonts

If a Google Fonts update changes a glyph or a hint, the open-source files
in this directory can be regenerated. The pattern is the same as the
initial download:

1. Hit `https://fonts.googleapis.com/css2?family=...&display=swap` with a
   modern Chrome User-Agent so Google's CDN returns woff2 URLs.
2. For each `@font-face` block in the response that has a `/* latin */`
   or `/* latin-ext */` subset comment, download the woff2 URL.
3. Save with the `{Family}-{weight}-{subset}.woff2` filename convention
   used here so the existing `fonts.css` @font-face rules continue to
   match.

No live download script is checked in — this is a one-time regeneration
operation and doing it inline keeps the install path simple.

## Adding more weights / families

1. Drop the new `.woff2` (or `.otf` / `.ttf`) here.
2. Add a `@font-face` rule in [`../css/fonts.css`](../css/fonts.css)
   matching the filename convention above. Include the appropriate
   `unicode-range` if you want subset-aware lazy loading.
3. Reference the family in a theme CSS via `font-family: 'My New Font'`.
