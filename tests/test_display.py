"""Template and route regressions. All database writes use a temporary DB."""
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase, main
from unittest.mock import patch

from bs4 import BeautifulSoup

from app import create_app, db
from app.models import get_settings
from app.sun import effective_theme


class DisplayTests(TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        db_patch = patch.object(db, "DB_PATH", Path(directory.name) / "test.db")
        db_patch.start()
        self.addCleanup(db_patch.stop)
        with patch("app.sync_worker.start_sync_worker"):
            self.app = create_app()
        self.app.testing = True
        self.client = self.app.test_client()
        with self.app.app_context():
            self.settings = get_settings()
        self.settings["theme"] = "palindrome5"
        self.tap = dict(
            tap_number=1, beer_name="A very long beer name & a <special> release",
            brewery="Palindrome Brewing Co", style_category="IPA & Pale Ales",
            sub_style="New England / Hazy IPA", abv=6.5, ibu=40,
            location="London, UK", display_color="#c58b20",
        )
        for kind in ("third", "half", "pint", "takeaway"):
            self.tap["price_" + kind] = 5.5
            self.tap["price_" + kind + "_enabled"] = True

    def render(self, *, taps=None, specials=None, events=None, **settings):
        snapshot = dict(
            settings={**self.settings, **settings},
            taps=deepcopy([self.tap] if taps is None else taps),
            specials=specials or [], events=events or [],
            version_hash="test", holiday=None,
        )
        with patch("app.routes_display.state_snapshot", return_value=snapshot), patch(
            "app.routes_display._resolve_tap_logo_url", return_value="/static/img/hop-green.svg"
        ):
            response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        return BeautifulSoup(response.data, "html.parser")

    def test_all_themes_and_image_modes_render_with_existing_assets(self):
        themes = [path.stem[6:] for path in Path("app/static/css").glob("theme-*.css")
                  if path.stem != "theme-menu"]
        self.assertEqual(len(themes), 12)
        for theme in themes:
            for mode in ("logo", "color"):
                with self.subTest(theme=theme, mode=mode):
                    soup = self.render(theme=theme, display_style=mode)
                    self.assertEqual(soup.body["data-theme"], theme)
                    self.assertEqual(bool(soup.select_one(".color-disc")), mode == "color")
                    assets = [node["href"] for node in soup.select("link[rel=stylesheet]")]
                    assets += [node["src"] for node in soup.select("script[src]")]
                    for asset in assets:
                        with self.client.get(asset) as response:
                            self.assertEqual(response.status_code, 200, asset)
                    self.assertEqual("/static/css/theme-menu.css" in assets,
                                     theme in ("palindrome4", "palindrome5", "editorial", "chalkboard"))

    def test_names_are_escaped_and_brewery_is_secondary(self):
        soup = self.render()
        self.assertEqual(soup.select_one(".line-1").get_text(strip=True), self.tap["beer_name"])
        self.assertIsNotNone(soup.select_one(".line-2 .brewery"))
        self.assertIsNone(soup.select_one(".line-1 special"))

    def test_sidebar_is_only_reserved_when_populated(self):
        soup = self.render()
        self.assertIsNone(soup.select_one(".side-panels"))
        self.assertIsNotNone(soup.select_one(".display-body--full"))
        for panels in (
            {"specials": [dict(title="Flight", price=8, description="Three tasters")]},
            {"events": [dict(name="Quiz", event_date="2026-10-01", location="Taproom", url="")]},
        ):
            with self.subTest(panels=panels):
                soup = self.render(**panels)
                self.assertIsNotNone(soup.select_one(".side-panels"))
                self.assertIsNone(soup.select_one(".display-body--full"))

    def test_event_without_url_uses_full_width(self):
        events = [dict(name="Quiz", event_date="2026-10-01", location="Taproom", url="")]
        soup = self.render(events=events)
        self.assertIsNotNone(soup.select_one(".event-item--no-qr"))
        self.assertIsNone(soup.select_one(".ev-qr"))
        events[0]["url"] = "https://example.com/quiz"
        soup = self.render(events=events)
        self.assertIsNone(soup.select_one(".event-item--no-qr"))
        self.assertEqual(self.client.get(soup.select_one(".ev-qr img")["src"]).status_code, 200)

    def test_price_columns_and_gaps_remain_aligned(self):
        for count in range(5):
            with self.subTest(price_columns=count):
                first, second = deepcopy(self.tap), deepcopy(self.tap)
                second["tap_number"] = 2
                for index, kind in enumerate(("third", "half", "pint", "takeaway")):
                    first["price_" + kind + "_enabled"] = index < count
                    second["price_" + kind + "_enabled"] = False
                soup = self.render(taps=[first, second])
                self.assertEqual(len(soup.select(".price-head")), count)
                self.assertEqual(len(soup.select(".beer-row .price-cell")), 2 * count)
                self.assertEqual(len(soup.select(".price-cell.is-empty")), count)
                self.assertEqual(bool(soup.select_one(".categories--no-prices")), count == 0)

    def test_empty_menu_and_home_guest_separator(self):
        soup = self.render(taps=[])
        self.assertEqual(soup.select_one(".empty p").text, "Coming soon")
        guest = {**self.tap, "tap_number": 2, "brewery": "Guest Brewery"}
        soup = self.render(taps=[self.tap, guest], tap_order_mode="home_first")
        self.assertEqual(soup.select_one(".tap-separator").text, "Guest Beers")
        scripts = [node["src"] for node in soup.select("script[src]")]
        self.assertLess(scripts.index("/static/js/pagination.js"), scripts.index("/static/js/display.js"))

    def test_admin_routes_and_day_night_pair_save(self):
        for path in ("taps", "settings", "specials", "events", "beer-library"):
            self.assertEqual(self.client.get("/admin/" + path).status_code, 200, path)
        soup = BeautifulSoup(self.client.get("/admin/settings").data, "html.parser")
        self.assertEqual(soup.select_one("#brandThemePair")["type"], "button")
        form = {**self.settings, "day_theme": "palindrome4", "night_theme": "palindrome5",
                "day_night_auto": "1", "override_day_start": "08:00", "override_night_start": "18:00"}
        form = {key: value for key, value in form.items() if value is not None}
        self.assertEqual(self.client.post("/admin/settings", data=form).status_code, 302)
        with self.app.app_context():
            settings = get_settings()
        for hour, expected in ((7, "palindrome5"), (8, "palindrome4"), (17, "palindrome4"), (18, "palindrome5")):
            with patch("app.sun.datetime") as clock:
                clock.now.return_value = datetime(2026, 9, 27, hour)
                self.assertEqual(effective_theme(settings), expected)


if __name__ == "__main__":
    main()
