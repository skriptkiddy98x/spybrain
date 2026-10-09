import io
import json
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
import geolocate
import osinthub as hub

class LocateEngineTests(unittest.TestCase):
    def test_model_answers_are_read_leniently(self):
        text = '```json\n{"clues": ["Cyrillic signs"], "candidates": [{"place": "Lviv", "region": "", "country": "Ukraine", "lat": 49.84, "lon": 24.03, "confidence": 1.4, "reasoning": "Signs"}]}\n```'
        rows, clues = geolocate._candidates(geolocate._lenient_json(text))
        self.assertEqual(rows[0]["place"], "Lviv, Ukraine")
        self.assertEqual(rows[0]["confidence"], 1.0)
        self.assertEqual(clues, ["Cyrillic signs"])

    def test_impossible_coordinates_are_dropped(self):
        with self.assertRaises(geolocate.EngineError):
            geolocate._candidates({"candidates": [{"lat": 120, "lon": 10}, {"lat": "x", "lon": 1}]})

    def test_keys_are_encrypted_and_removable(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(geolocate, "user_dir", return_value=Path(temp)):
            geolocate.save_key("gemini", "  secret-key  ")
            self.assertNotIn("secret-key", (Path(temp) / "keys.dat").read_text(encoding="utf-8"))
            self.assertEqual(geolocate.load_key("gemini"), "secret-key")
            geolocate.save_key("gemini", "")
            self.assertEqual(geolocate.load_key("gemini"), "")

    def test_nearest_place_is_offline(self):
        town, country, km = geolocate.nearest_place(48.1486, 17.1077)
        self.assertEqual(country, "Slovakia")
        self.assertLess(km, 10)

    def test_clean_photo_strips_exif(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "gps.jpg"
            exif = Image.Exif()
            exif[0x010F] = "Camera maker"
            Image.new("RGB", (40, 30)).save(path, exif=exif)
            clean = geolocate.clean_photo(path, temp)
            with Image.open(clean) as image:
                self.assertEqual(len(image.getexif()), 0)

    def test_gemini_reply_is_parsed(self):
        reply = {"candidates": [{"content": {"parts": [{"text": json.dumps({"clues": ["Alps"], "candidates": [{"place": "Zermatt", "region": "Valais", "country": "Switzerland", "lat": 46.02, "lon": 7.75, "confidence": 0.6, "reasoning": "Matterhorn"}]})}]}}]}
        class Response(io.BytesIO):
            def __enter__(self): return self
            def __exit__(self, *args): return False
        with tempfile.TemporaryDirectory() as temp:
            photo = Path(temp) / "p.jpg"
            Image.new("RGB", (20, 20)).save(photo)
            with patch("urllib.request.urlopen", return_value=Response(json.dumps(reply).encode())) as opened:
                rows, clues = geolocate.gemini_locate(photo, "key", "gemini-flash-latest")
            request = opened.call_args[0][0]
            self.assertIn("gemini-flash-latest:generateContent", request.full_url)
            self.assertEqual(request.headers["X-goog-api-key"], "key")
        self.assertEqual(rows[0]["place"], "Zermatt, Valais, Switzerland")
        self.assertEqual(clues, ["Alps"])

    def test_missing_key_is_reported_not_crashed(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(geolocate, "user_dir", return_value=Path(temp)):
            photo = Path(temp) / "p.jpg"
            Image.new("RGB", (20, 20)).save(photo)
            job = geolocate.jobs(str(photo), {"engines": ["claude"]})[0][1]
            self.assertEqual(job(str(photo), Path(temp), True)["status"], "missing")

    def test_engine_choice_and_location_rows(self):
        with self.assertRaises(ValueError):
            geolocate.jobs("photo.jpg", {"engines": ["unknown"]})
        names = [name for name, _, _ in geolocate.jobs("photo.jpg", {"engines": ["claude", "geoclip"]})]
        self.assertEqual(names, ["GeoCLIP", "Claude"])
        rows = hub.flatten([{"tool": "GeoCLIP", "locations": [{"lat": 1.5, "lon": 2.5, "confidence": 0.25, "place": "Somewhere", "map": geolocate.map_url(1.5, 2.5)}], "clues": ["Palm trees"]}])
        self.assertEqual(rows[0]["category"], "Location")
        self.assertTrue(hub.safe_url(rows[0]["url"]))
        self.assertEqual(rows[1]["value"], "Palm trees")

class LocatePageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        import app
        cls.app = app
        cls.qt = QApplication.instance() or QApplication([])
        cls.qt.setStyleSheet(app.STYLE)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        # These tests cover every engine, so they switch all of them on; the default is tested in test_photo_geoclip_only.
        self.patches = [patch.object(hub, "REPORTS", Path(self.temp.name) / "reports"),
                        patch.object(geolocate, "user_dir", return_value=Path(self.temp.name)),
                        patch.object(geolocate, "ENABLED_ENGINES", tuple(geolocate.ENGINES))]
        for item in self.patches:
            item.start()
        self.window = self.app.Window()

    def tearDown(self):
        self.window.close()
        self.window.deleteLater()
        for item in self.patches:
            item.stop()
        self.temp.cleanup()

    def test_needs_a_photo_first(self):
        self.window.navigate(self.app.LOCATE_PAGE)
        self.window.start_locate()
        self.assertIsNone(self.window.locate_worker)
        self.assertIn("photo", self.window.locate_state.text())

    def test_online_engines_wait_for_a_key(self):
        self.assertFalse(self.window.engine_rows["gemini"].check.isEnabled())
        self.assertFalse(self.window.engine_rows["claude"].check.isChecked())

    def test_results_and_saved_scans_reach_the_map(self):
        photo = Path(self.temp.name) / "photo.jpg"
        Image.new("RGB", (60, 40), "#224422").save(photo)
        report = {"kind": "location", "target": str(photo), "started": "2026-10-08T12:00:00", "results": [
            {"tool": "GeoCLIP", "status": "ok", "ok": True, "locations": [{"lat": 48.1, "lon": 17.1, "confidence": 0.3, "place": "Bratislava", "map": geolocate.map_url(48.1, 17.1)}]},
            {"tool": "Gemini", "status": "missing", "ok": False, "log": "Add your Gemini API key on the Locate page."}]}
        self.window.show_location(report)
        self.assertEqual(self.window.locate_table.rowCount(), 2)
        self.assertEqual(len(self.window.world.pins), 1)
        self.assertIn("Needs key", self.window.locate_table.item(1, 2).text())
        self.window.world.resize(800, 400)
        self.window.world.grab()

if __name__ == "__main__":
    unittest.main()
