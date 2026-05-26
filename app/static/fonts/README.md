# Brand fonts

This directory holds the licensed and open-source font files used by the
Palindrome 4 / 5 / 6 themes. The display falls back to Google-Fonts
alternatives (Archivo Black + Inter) if a file is missing, so the kiosk
will still render — just not with the brand typography.

`@font-face` declarations live in [`../css/fonts.css`](../css/fonts.css).

## Files

| File                              | Used as              | Licence                                    |
| --------------------------------- | -------------------- | ------------------------------------------ |
| `PPFragment-GlareExtraBold.otf`   | display headings     | Pangram Pangram — **commercial / trial**   |
| `AlegreyaSans-Regular.ttf`        | display body (400)   | SIL Open Font Licence (free for any use)   |
| `AlegreyaSans-Bold.ttf`           | display body (700)   | SIL Open Font Licence                      |
| `AlegreyaSans-Black.ttf`          | display body (900)   | SIL Open Font Licence                      |

## ⚠️ PP Fragment Glare licensing

**PP Fragment Glare cannot be used in production without a paid licence
from Pangram Pangram.** For personal / non-commercial projects (including
testing on your own kiosk before any commercial release), Pangram Pangram
distributes a free trial version of this typeface — you have to sign up
for an account on their site to download it.

- Product page (paid + free trial): https://pangrampangram.com/products/fragment-glare
- Pangram Pangram licences: https://pangrampangram.com/pages/licenses

If you are deploying this kiosk somewhere customers will see it, that is
a commercial use and you will need to purchase the appropriate licence —
the free trial does **not** cover commercial display. Remove the .otf
from this folder if you are unsure; the themes will fall back gracefully
to Archivo Black.

The file checked into the repo is included as a convenience for the
project owner (who holds the appropriate licence/trial registration).
Anyone forking this repo needs to source their own copy under their own
licence terms.

## Alegreya Sans

Alegreya Sans is licensed under the SIL Open Font Licence 1.1 — free for
personal and commercial use, including redistribution. Source:
https://fonts.google.com/specimen/Alegreya+Sans

## Replacing or adding weights

If you want to add more Alegreya weights (e.g. Medium 500, ExtraBold 800
which the body text never actually requests but the Google-Fonts URL in
`display.html` covers), drop the `.ttf` here and add a matching
`@font-face` rule in `../css/fonts.css`.
