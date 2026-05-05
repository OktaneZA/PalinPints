#!/usr/bin/env bash
# Demo data for screenshots — 15 beers across all 6 categories + 2 specials.
set -e
B=http://127.0.0.1:8080

post_tap() {
  curl -sf -X POST -o /dev/null \
    -F "active=1" -F "brewery=$2" -F "beer_name=$3" \
    -F "style_category=$4" -F "sub_style=$5" \
    -F "abv=$6" -F "ibu=$7" -F "location=$8" \
    -F "price_half=$9" -F "price_pint=${10}" -F "price_takeaway=${11}" \
    "$B/admin/taps/$1"
}

# IPA & Pale Ales (3)
post_tap 1  "Palindrome Brewing Co"   "Doppelganger"           "IPA & Pale Ales"        "American IPA"             6.2 55  "Faversham, UK"        3.50 6.00 10.00
post_tap 2  "Sierra Nevada"           "Hazy Little Thing"      "IPA & Pale Ales"        "New England / Hazy IPA"   6.7 35  "Chico, CA"            3.75 6.50 11.00
post_tap 3  "Deschutes"               "Fresh Squeezed"         "IPA & Pale Ales"        "American IPA"             6.4 60  "Bend, OR"             3.75 6.50 11.00

# Sour & Wild Ales (2)
post_tap 4  "Petrus"                  "Aged Pale"              "Sour & Wild Ales"       "Flanders Oud Bruin"       7.3 12  "Bavikhove, BE"        4.00 7.00 12.00
post_tap 5  "Cantillon"               "Gueuze 100% Lambic"     "Sour & Wild Ales"       "Lambic - Gueuze"          5.0 0   "Brussels, BE"         4.50 8.00 14.00

# Stout & Porter (3)
post_tap 6  "Palindrome Brewing Co"   "Mirror Mirror"          "Stout & Porter"         "Imperial Stout"           9.0 65  "Faversham, UK"        4.00 7.00 12.00
post_tap 7  "Deschutes"               "Black Butte Porter"     "Stout & Porter"         "American Porter"          5.5 30  "Bend, OR"             3.50 6.00 10.00
post_tap 8  "Ballast Point"           "Victory at Sea"         "Stout & Porter"         "Imperial Coffee Porter"   10.0 60 "San Diego, CA"        4.50 7.50 13.00

# Lager & Pilsner (3)
post_tap 9  "Pilsner Urquell"         "Pilsner Urquell"        "Lager & Pilsner"        "Czech Pilsner"            4.4 40  "Pilsen, CZ"           3.00 5.50 9.00
post_tap 10 "Miller"                  "Miller Lite"            "Lager & Pilsner"        "American Light Lager"     4.2 10  "Milwaukee, WI"        3.00 5.00 8.00
post_tap 11 "Lion"                    "Ceylon Lion Lager"      "Lager & Pilsner"        "Pale Lager"               4.8 18  "Gampaha, LK"          3.00 5.50 9.00

# Belgian & Farmhouse (2)
post_tap 12 "Brasserie Dupont"        "Saison Dupont"          "Belgian & Farmhouse"    "Saison / Farmhouse"       6.5 25  "Tourpes, BE"          3.75 6.50 11.00
post_tap 13 "Westmalle"               "Tripel"                 "Belgian & Farmhouse"    "Belgian Tripel"           9.5 30  "Westmalle, BE"        4.50 7.50 13.00

# Historical & Specialty (2)
post_tap 14 "Anderson Valley"         "Gose"                   "Historical & Specialty" "Leipzig Gose"             4.2 12  "Boonville, CA"        3.50 6.00 10.00
post_tap 15 "Mikkeller"               "Crooked Moon dIPA"      "Historical & Specialty" "Imperial Double IPA"      9.0 85  "Copenhagen, DK"       4.50 7.50 13.00

# Specials
curl -sf -X POST -o /dev/null -F "title=IPA Flight"   -F "description=4 x 1/3 pint of any IPA"  -F "price=10.00" "$B/admin/specials"
curl -sf -X POST -o /dev/null -F "title=Belgian Duo"  -F "description=Saison + Tripel, 1/2 pint each" -F "price=8.50" "$B/admin/specials"
curl -sf -X POST -o /dev/null -F "title=Happy Hour"   -F "description=Mon-Thu 4-6pm, £1 off all pints" -F "price=" "$B/admin/specials"

echo "Seeded."
