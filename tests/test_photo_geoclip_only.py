"""This version's Photo page offers GeoCLIP only. The other engines are built but switched off."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
import geolocate
import osinthub as hub

READY = {name: (True, "Ready") for name in geolocate.ENGINES}


class EngineSwitchTests(unittest.TestCase):
    def test_the_default_is_geoclip_alone(self):
        self.assertEqual(geolocate.ENABLED_ENGINES, ("geoclip",))
        self.assertTrue(set(geolocate.ENABLED_ENGINES) <= set(geolocate.ENGINES))

    def test_saved_keys_never_send_a_photo_online_on_their_own(self):
        with patch.object(geolocate, "engine_status", return_value=READY):
            names = [name for name, _, _ in geolocate.jobs("photo.jpg", {})]
            self.assertEqual(names, ["GeoCLIP"])
            self.assertEqual([name for name, _, _ in hub.jobs_for("photo.jpg", "location")], ["GeoCLIP"])
            self.assertEqual([name for name, _, _ in geolocate.jobs("photo.jpg", None)], ["GeoCLIP"])

    def test_switching_an_engine_back_on_adds_it_to_the_default_choice(self):
        with patch.object(geolocate, "engine_status", return_value=READY), patch.object(geolocate, "ENABLED_ENGINES", ("geoclip", "gemini", "faces")):
            names = [name for name, _, _ in geolocate.jobs("photo.jpg", {})]
        self.assertEqual(names, ["GeoCLIP", "Gemini"])              # face search still needs an explicit choice

    def test_an_explicit_choice_is_still_honoured(self):
        names = [name for name, _, _ in geolocate.jobs("photo.jpg", {"engines": ["claude", "geoclip"]})]
        self.assertEqual(names, ["GeoCLIP", "Claude"])

    def test_every_engine_is_still_built_and_has_a_job(self):
        with patch.object(geolocate, "engine_status", return_value=READY):
            names = [name for name, _, _ in geolocate.jobs("photo.jpg", {"engines": list(geolocate.ENGINES), "purpose": "case 12"})]
        self.assertEqual(names, [meta["title"] for meta in geolocate.ENGINES.values()])


class PhotoPageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        import app
        cls.app = app
        cls.qt = QApplication.instance() or QApplication([])
        cls.qt.setStyleSheet(app.STYLE)

    def make_window(self, engines=None):
        self.temp = tempfile.TemporaryDirectory()
        real, ini = self.app.QSettings, str(Path(self.temp.name) / "settings.ini")
        items = [patch.object(hub, "REPORTS", Path(self.temp.name) / "reports"), patch.object(geolocate, "user_dir", return_value=Path(self.temp.name)),
                 patch.object(self.app, "QSettings", lambda *args: real(ini, real.Format.IniFormat)),
                 patch.object(geolocate, "engine_status", return_value=READY)]
        if engines is not None:
            items.append(patch.object(geolocate, "ENABLED_ENGINES", engines))
        for item in items:
            item.start()
            self.addCleanup(item.stop)
        self.addCleanup(self.temp.cleanup)
        window = self.app.Window()
        self.addCleanup(window.deleteLater)
        self.addCleanup(window.close)
        window.refresh_engines(initial=True)
        return window

    def labels(self, widget):
        """Text of the labels on a page, leaving out the result tabs' own pages (the hidden ones hold placeholder text)."""
        QLabel = self.app.QLabel
        skipped = set()
        for stack in widget.findChildren(self.app.QStackedWidget):
            skipped.update(stack.findChildren(QLabel))
        return " ".join(label.text() for label in widget.findChildren(QLabel) if label not in skipped)

    def source_titles(self, window):
        window.navigate(self.app.SOURCES_PAGE)
        return [window.source_list.item(i).data(self.app.Qt.ItemDataRole.UserRole)["cells"][1][0] for i in range(window.source_list.count())]

    def test_only_geoclip_is_offered(self):
        window = self.make_window()
        self.assertEqual(list(window.engine_rows), ["geoclip"])
        self.assertTrue(window.engine_rows["geoclip"].check.isChecked())
        page = self.labels(window.pages.widget(self.app.LOCATE_PAGE))
        for hidden in ("Gemini", "Claude", "Google Vision", "Web matches", "Face search", "WHERE IS IT ONLINE", "WHO ELSE SHOWS THIS FACE", "age check"):
            self.assertNotIn(hidden, page, hidden)
        self.assertIn("WHERE WAS IT TAKEN", page)
        self.assertIn("GeoCLIP", page)

    def test_the_page_says_what_it_does(self):
        window = self.make_window()
        self.assertIn("Where a photo was taken. For lawful", self.labels(window.pages.widget(self.app.LOCATE_PAGE)))
        self.assertNotIn("face", self.labels(window.pages.widget(self.app.LOCATE_PAGE)).lower())

    def test_web_and_face_tabs_and_the_purpose_box_are_hidden(self):
        window = self.make_window()
        self.assertEqual([tab.isHidden() for tab in window.result_tabs], [False, True, True])
        self.assertTrue(window.purpose.isHidden())

    def test_a_saved_analysis_with_web_results_still_shows_them(self):
        window = self.make_window()
        photo = Path(self.temp.name) / "photo.jpg"
        Image.new("RGB", (60, 40), "#224422").save(photo)
        window.show_location({"kind": "location", "target": str(photo), "started": "2026-10-08T12:00:00", "results": [
            {"tool": "Web matches", "status": "ok", "ok": True, "matches": [{"kind": "Page · full match", "url": "https://example.org/a", "title": "Owl"}], "labels": ["owl"]}]})
        self.assertEqual(window.web_table.rowCount(), 1)
        self.assertFalse(window.result_tabs[1].isHidden())
        self.assertIn("1", window.result_tabs[1].text())
        self.assertTrue(window.result_tabs[2].isHidden())

    def test_the_sources_page_lists_geoclip_only_for_photos(self):
        titles = self.source_titles(self.make_window())
        self.assertIn("GeoCLIP", titles)
        for hidden in ("Gemini", "Claude", "Google Vision", "Web matches", "Face search"):
            self.assertNotIn(hidden, titles)
        self.assertIn("Leaks", titles)

    def test_the_guide_matches(self):
        window = self.make_window()
        guide = self.labels(window.pages.widget(self.app.GUIDE_PAGE))
        self.assertIn("100,000 places", guide)
        for hidden in ("Gemini", "Claude", "FaceCheck", "Google Vision"):
            self.assertNotIn(hidden, guide, hidden)
        self.assertIn("LEAKS", guide)

    def test_geoclip_alone_needs_no_consent_and_no_purpose(self):
        from PySide6.QtWidgets import QMessageBox
        window = self.make_window()
        photo = Path(self.temp.name) / "photo.jpg"
        Image.new("RGB", (60, 40), "#224422").save(photo)
        window.set_locate_photo(str(photo))
        started = {}
        def fake_start(self_worker):
            started["engines"] = self_worker.options["engines"] if hasattr(self_worker, "options") else None
        with patch.object(QMessageBox, "question") as asked, patch.object(self.app.ScanWorker, "start", fake_start):
            window.start_locate()
        asked.assert_not_called()                                      # nothing leaves this computer, so nothing to agree to
        self.assertIsNotNone(window.locate_worker)
        window.locate_worker = None

    def test_every_engine_comes_back_with_the_switch(self):
        window = self.make_window(tuple(geolocate.ENGINES))
        self.assertEqual(list(window.engine_rows), list(geolocate.ENGINES))
        self.assertEqual([tab.isHidden() for tab in window.result_tabs], [False, False, False])
        self.assertFalse(window.purpose.isHidden())
        page = self.labels(window.pages.widget(self.app.LOCATE_PAGE))
        for shown in ("Gemini", "Claude", "Google Vision", "Web matches", "Face search", "WHERE IS IT ONLINE", "WHO ELSE SHOWS THIS FACE"):
            self.assertIn(shown, page, shown)
        self.assertIn("who else shows the same face", page)
        self.assertIn("Gemini", self.source_titles(window))
        self.assertIn("FaceCheck", self.labels(window.pages.widget(self.app.GUIDE_PAGE)))


if __name__ == "__main__":
    unittest.main()
