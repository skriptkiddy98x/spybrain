import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch
import geolocate
import leaks
import osinthub as hub


def breach(name, year, data, records=1000, source="XposedOrNot", risk="", flags=()):
    return {"name": name, "domain": f"{name.lower()}.com", "date": str(year) if year else "", "data": list(data), "records": records,
            "source": source, "password_risk": risk, "verified": True, "flags": list(flags)}

MIXED = [breach("Adobe", 2013, ["Email addresses", "Passwords"], 152445165, risk="weak hash"),
         breach("Canva", 2019, ["Email addresses", "Names", "Passwords"], 137272116, source="HIBP"),
         breach("Gravatar", 2020, ["Email addresses", "Names", "Usernames"], 113990759, source="HIBP", flags=["spam list"]),
         breach("Lazada", 2020, ["Email addresses", "Usernames"], 1300000),
         breach("Unknown", 0, [], None)]

def outcome(breaches, sources=("XposedOrNot",), errors=()):
    return {"breaches": breaches, "sources": list(sources), "errors": list(errors), "limited": 0}


class LeaksPageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        import app
        cls.app = app
        cls.qt = QApplication.instance() or QApplication([])
        cls.qt.setStyleSheet(app.STYLE)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        real, ini = self.app.QSettings, str(Path(self.temp.name) / "settings.ini")
        self.patches = [patch.object(hub, "REPORTS", Path(self.temp.name) / "reports"), patch.object(geolocate, "user_dir", return_value=Path(self.temp.name)),
                        patch.object(self.app, "QSettings", lambda *args: real(ini, real.Format.IniFormat))]
        for item in self.patches:
            item.start()
        leaks._cache.clear()
        self.window = self.app.Window()
        self.window.navigate(self.app.LEAKS_PAGE)

    def tearDown(self):
        self.finish()
        self.window.close()
        self.window.deleteLater()
        for item in self.patches:
            item.stop()
        self.temp.cleanup()

    def finish(self, seconds=10):
        end = time.monotonic() + seconds
        while self.window.leak_task and time.monotonic() < end:
            self.qt.processEvents()
            time.sleep(0.01)
        self.qt.processEvents()

    def check_email(self, text="someone@example.org", result=None, error=None):
        self.window.leak_email.setText(text)
        with patch.object(leaks, "check_email", side_effect=error, return_value=result):
            self.window.start_leak_email()
            self.finish()

    # ---- Navigation and input
    def test_page_is_in_the_navigation(self):
        self.assertEqual(self.window.pages.currentIndex(), self.app.LEAKS_PAGE)
        self.assertEqual(self.window.pages.widget(self.app.LEAKS_PAGE), self.window.leak_stack.parentWidget())
        self.assertIsNotNone(self.window.topbar.button_for(self.app.LEAKS_PAGE))

    def test_tabs_switch_between_email_and_password(self):
        self.window.show_leak_tab(1)
        self.assertEqual(self.window.leak_stack.currentIndex(), 1)
        self.assertTrue(self.window.leak_tabs[1].isChecked() and not self.window.leak_tabs[0].isChecked())
        self.window.show_leak_tab(0)
        self.assertEqual(self.window.leak_stack.currentIndex(), 0)

    def test_a_bad_address_is_explained_and_nothing_starts(self):
        for text in ("", "not-an-email", "a@b", "x@@y.org"):
            self.window.leak_email.setText(text)
            with patch.object(leaks, "check_email") as call:
                self.window.start_leak_email()
            call.assert_not_called()
            self.assertIsNone(self.window.leak_task)
            self.assertEqual(self.window.leak_hint.property("tone"), "warn", text)

    def test_the_hint_recovers_after_a_good_address(self):
        self.window.leak_email.setText("nope")
        self.window.start_leak_email()
        self.check_email(result=outcome([]))
        self.assertFalse(self.window.leak_hint.property("tone"))
        self.assertEqual(self.window.leak_hint.text(), self.window.LEAK_HINT)

    # ---- Email results
    def test_breaches_fill_the_banner_the_timeline_and_the_table(self):
        self.check_email("Someone@Example.org", outcome(MIXED, ("XposedOrNot", "Have I Been Pwned")))
        w = self.window
        self.assertEqual(w.leak_count.text(), str(len(MIXED)))
        self.assertEqual(w.leak_count.property("tone"), "bad")             # passwords were exposed
        self.assertEqual(w.leak_frame.property("tone"), "bad")
        self.assertIn("SINCE 2013", w.leak_verdict.text())
        self.assertIn("Passwords were exposed in 2 breaches", w.leak_detail.text())
        self.assertIn("Personal data, but no passwords, in 1", w.leak_detail.text())
        self.assertIn("1 listed without details", w.leak_detail.text())
        self.assertEqual(w.leak_timeline.state, "found")
        self.assertEqual(w.leak_table.rowCount(), len(MIXED))
        names = {w.leak_table.item(r, 1).text(): w.leak_table.item(r, 0).text() for r in range(5)}
        self.assertEqual(names, {"Adobe": "PASSWORDS", "Canva": "PASSWORDS", "Gravatar": "PERSONAL DATA", "Lazada": "EMAIL ONLY", "Unknown": "NOT LISTED"})
        self.assertTrue(w.leak_scan_button.isEnabled())
        self.assertEqual(w.leak_email.text(), "Someone@example.org")      # the domain is normalised, the name is left alone
        self.assertTrue(w.leak_email_button.isEnabled())
        self.assertEqual(w.leak_email_button.text(), "CHECK EMAIL")

    def test_a_personal_data_only_result_is_amber(self):
        self.check_email(result=outcome([breach("Forum", 2018, ["Email addresses", "Phone numbers"])]))
        self.assertEqual(self.window.leak_count.property("tone"), "warn")
        self.assertIn("Personal data was exposed in 1", self.window.leak_detail.text())

    def test_an_email_only_result_says_so(self):
        self.check_email(result=outcome([breach("Forum", 2018, ["Email addresses", "Usernames"])]))
        self.assertIn("Only the address and usernames were exposed", self.window.leak_detail.text())
        self.assertEqual(self.window.leak_verdict.text(), "BREACH SINCE 2018")

    def test_no_breaches_is_green_but_not_a_promise(self):
        self.check_email(result=outcome([]))
        w = self.window
        self.assertEqual((w.leak_count.text(), w.leak_count.property("tone")), ("0", "ok"))
        self.assertEqual(w.leak_timeline.state, "clean")
        self.assertIn("isn't a guarantee", w.leak_detail.text())
        self.assertEqual(w.leak_table.rowCount(), 0)
        self.assertTrue(w.leak_scan_button.isEnabled())

    def test_source_warnings_are_shown(self):
        self.check_email(result=outcome(MIXED[:1], errors=["Have I Been Pwned: rejected the API key. Check it under Set key."]))
        self.assertIn("rejected the API key", self.window.leak_detail.text())

    def test_a_cached_answer_says_so(self):
        found = outcome(MIXED[:1])
        found["cached"] = True
        self.check_email(result=found)
        self.assertIn("less than an hour ago", self.window.leak_detail.text())
        self.assertIn("from memory", self.window.leak_state.text())

    def test_a_rate_limit_is_a_warning_not_a_crash(self):
        self.check_email(error=leaks.RateLimited("XposedOrNot rate limit reached. Try again in 41 min.", 2460))
        w = self.window
        self.assertEqual(w.leak_timeline.state, "error")
        self.assertIn("41 min", w.leak_timeline.message)
        self.assertEqual((w.leak_count.text(), w.leak_count.property("tone")), ("—", "warn"))
        self.assertEqual(w.leak_verdict.text(), "CHECK FAILED")
        self.assertFalse(w.leak_scan_button.isEnabled())
        self.assertTrue(w.leak_email_button.isEnabled())                    # you can try again

    def test_unexpected_errors_do_not_leave_the_page_locked(self):
        self.check_email(error=RuntimeError("boom"))
        self.assertIn("RuntimeError", self.window.leak_state.text())
        self.assertTrue(self.window.leak_email_button.isEnabled())
        self.assertIsNone(self.window.leak_task)

    def test_the_hibp_key_is_passed_to_the_check(self):
        geolocate.save_key("hibp", "0123456789abcdef" * 2)
        self.window.leak_email.setText("someone@example.org")
        with patch.object(leaks, "check_email", return_value=outcome([])) as call:
            self.window.start_leak_email()
            self.finish()
        self.assertEqual(call.call_args[0][:2], ("someone@example.org", "0123456789abcdef" * 2))

    def test_controls_are_locked_while_checking(self):
        gate = threading.Event()
        def slow(email, key, check):
            gate.wait(5)
            return outcome([])
        self.window.leak_email.setText("someone@example.org")
        with patch.object(leaks, "check_email", slow):
            self.window.start_leak_email()
            self.assertFalse(self.window.leak_email_button.isEnabled())
            self.assertEqual(self.window.leak_email_button.text(), "CHECKING")
            self.assertFalse(self.window.leak_password_button.isEnabled())
            self.assertEqual(self.window.leak_timeline.state, "checking")
            self.window.start_leak_email()                                  # a second click does nothing
            gate.set()
            self.finish()
        self.assertTrue(self.window.leak_email_button.isEnabled())

    # ---- Timeline and list
    def test_timeline_and_table_select_each_other(self):
        patcher = patch.object(self.app, "MOTION", False)    # without animation every block is there at once
        patcher.start()
        self.addCleanup(patcher.stop)
        self.check_email(result=outcome(MIXED))
        from PySide6.QtCore import QPointF
        w = self.window
        w.leak_timeline.resize(900, 200)
        w.leak_timeline.grab()
        cell = next(b for rect, b in w.leak_timeline.cells if b["name"] == "Canva")
        rect = next(rect for rect, b in w.leak_timeline.cells if b["name"] == "Canva")
        self.assertIs(w.leak_timeline.cell_at(rect.center()), cell)
        self.assertIsNone(w.leak_timeline.cell_at(rect.center() + QPointF(0, -400)))
        w.leak_timeline.picked.emit("Canva")
        rows = w.leak_table.selectionModel().selectedRows()
        self.assertEqual(w.leak_table.item(rows[0].row(), 1).text(), "Canva")
        self.assertEqual(w.leak_timeline.selected, "Canva")
        w.leak_table.selectRow(next(r for r in range(w.leak_table.rowCount()) if w.leak_table.item(r, 1).text() == "Lazada"))
        self.assertEqual(w.leak_timeline.selected, "Lazada")

    def test_timeline_paints_every_state_and_size(self):
        patcher = patch.object(self.app, "MOTION", False)
        patcher.start()
        self.addCleanup(patcher.stop)
        timeline = self.window.leak_timeline
        many = [breach(f"B{i}", 2009 + i % 18, ["Email addresses", "Passwords"] if i % 3 == 0 else ["Email addresses", "Names"] if i % 3 == 1 else ["Usernames"], i + 1)
                for i in range(300)]
        for states in (lambda: timeline.reset(), lambda: timeline.begin_check(), lambda: timeline.show_error("Offline. " * 30),
                       lambda: timeline.show_breaches([]), lambda: timeline.show_breaches(MIXED), lambda: timeline.show_breaches(many),
                       lambda: timeline.show_breaches([breach("Old", 1995, ["Passwords"]), breach("Future", 2099, ["Passwords"])])):
            states()
            for size in ((900, 180), (300, 120), (40, 40), (1500, 400)):
                timeline.resize(*size)
                timeline.hover = timeline.cells[0][1] if timeline.cells else None
                self.assertFalse(timeline.grab().isNull())
        timeline.show_breaches(many)
        timeline.resize(900, 180)
        timeline.grab()
        self.assertEqual(len(timeline.cells), 300)
        self.assertEqual(timeline.slots()[0], 2009)

    def test_the_animation_reveals_blocks_over_time(self):
        if not self.app.MOTION:
            self.skipTest("Windows animation effects are off")
        timeline = self.window.leak_timeline
        timeline.resize(900, 180)
        timeline.show_breaches(MIXED)
        timeline.grab()
        early = len(timeline.cells)
        time.sleep(1.4)
        timeline.grab()
        self.assertLess(early, len(MIXED))
        self.assertEqual(len(timeline.cells), len(MIXED))

    def test_undated_breaches_get_their_own_column(self):
        timeline = self.window.leak_timeline
        timeline.show_breaches(MIXED)
        self.assertEqual(timeline.slots()[0], 0)
        timeline.show_breaches(MIXED[:2])
        self.assertNotIn(0, timeline.slots())
        self.assertGreaterEqual(len(timeline.slots()), 10)

    # ---- Hand-off to the Scan page
    def test_scan_this_email_prepares_the_scan_page(self):
        self.check_email("someone@example.org", outcome(MIXED))
        self.window.scan_leak_email()
        self.assertEqual(self.window.pages.currentIndex(), self.app.SCAN_PAGE)
        self.assertEqual(self.window.target.text(), "someone@example.org")
        self.assertEqual(self.window.kind.currentData(), "email")
        self.assertIsNone(self.window.worker)                               # the scan waits for you to press Run

    def test_scan_this_email_waits_while_a_scan_runs(self):
        self.check_email("someone@example.org", outcome(MIXED))
        self.window.worker = object()
        try:
            self.window.scan_leak_email()
            self.assertEqual(self.window.pages.currentIndex(), self.app.LEAKS_PAGE)
            self.assertIn("scan is running", self.window.leak_state.text())
        finally:
            self.window.worker = None

    # ---- Passwords
    def test_the_password_box_is_cleared_and_the_password_goes_nowhere_else(self):
        self.window.show_leak_tab(1)
        secret = "correct-horse-battery-staple-42"
        self.window.leak_password.setText(secret)
        with patch.object(leaks, "password_pwned", return_value=1234) as call:
            self.window.start_leak_password()
            self.assertEqual(self.window.leak_password.text(), "")           # gone as soon as the check starts
            self.finish()
        call.assert_called_once_with(secret)
        shown = " ".join(label.text() for label in self.window.findChildren(self.app.QLabel)) + self.window.leak_state.text()
        self.assertNotIn(secret, shown)

    def test_a_known_password_is_red(self):
        self.window.show_leak_tab(1)
        self.window.leak_password.setText("password")
        with patch.object(leaks, "password_pwned", return_value=52372427):
            self.window.start_leak_password()
            self.finish()
        w = self.window
        self.assertEqual((w.pw_count.text(), w.pw_count.property("tone")), ("52,372,427", "bad"))
        self.assertEqual(w.pw_verdict.text(), "TIMES IN KNOWN BREACHES")
        self.assertIn("one of the most common", w.pw_detail.text())
        self.assertIn("known breaches", w.leak_state.text())

    def test_a_rarely_seen_password_is_still_red_but_not_called_common(self):
        self.window.show_leak_tab(1)
        self.window.leak_password.setText("something-a-bit-odd")
        with patch.object(leaks, "password_pwned", return_value=3):
            self.window.start_leak_password()
            self.finish()
        self.assertEqual(self.window.pw_count.text(), "3")
        self.assertNotIn("most common", self.window.pw_detail.text())

    def test_an_unknown_password_is_green_but_not_a_promise(self):
        self.window.show_leak_tab(1)
        self.window.leak_password.setText("a-long-unique-passphrase")
        with patch.object(leaks, "password_pwned", return_value=0):
            self.window.start_leak_password()
            self.finish()
        w = self.window
        self.assertEqual((w.pw_count.text(), w.pw_count.property("tone")), ("0", "ok"))
        self.assertIn("not a guarantee", w.pw_detail.text())

    def test_an_empty_password_is_not_checked(self):
        self.window.show_leak_tab(1)
        with patch.object(leaks, "password_pwned") as call:
            self.window.start_leak_password()
        call.assert_not_called()
        self.assertIn("password first", self.window.leak_state.text())

    def test_a_password_check_failure_is_reported(self):
        self.window.show_leak_tab(1)
        self.window.leak_password.setText("whatever")
        with patch.object(leaks, "password_pwned", side_effect=leaks.EngineError("Can't reach Pwned Passwords. Check the internet connection.")):
            self.window.start_leak_password()
            self.finish()
        self.assertEqual(self.window.pw_verdict.text(), "CHECK FAILED")
        self.assertTrue(self.window.leak_password_button.isEnabled())

    def test_show_and_hide(self):
        from PySide6.QtWidgets import QLineEdit
        self.assertEqual(self.window.leak_password.echoMode(), QLineEdit.EchoMode.Password)
        self.window.toggle_leak_password()
        self.assertEqual((self.window.leak_password.echoMode(), self.window.leak_show.text()), (QLineEdit.EchoMode.Normal, "HIDE"))
        self.window.toggle_leak_password()
        self.assertEqual((self.window.leak_password.echoMode(), self.window.leak_show.text()), (QLineEdit.EchoMode.Password, "SHOW"))

    # ---- Keys, sources, closing
    def test_hibp_key_status_is_shown(self):
        self.window.refresh_leaks()
        self.assertIn("Add a Have I Been Pwned key", self.window.leak_sources.text())
        geolocate.save_key("hibp", "0123456789abcdef" * 2)
        self.window.refresh_leaks()
        self.assertIn("your key is saved", self.window.leak_sources.text())

    def test_the_sources_page_lists_leaks(self):
        self.window.navigate(self.app.SOURCES_PAGE)
        titles = [self.window.source_list.item(i).data(self.app.Qt.ItemDataRole.UserRole)["cells"][1][0] for i in range(self.window.source_list.count())]
        self.assertIn("Leaks", titles)

    def test_the_window_waits_for_a_running_check_before_closing(self):
        gate = threading.Event()
        def slow(email, key, check):
            gate.wait(5)
            check()
            return outcome([])
        self.window.show()
        self.window.leak_email.setText("someone@example.org")
        with patch.object(leaks, "check_email", slow):
            self.window.start_leak_email()
            self.window.close()
            self.assertTrue(self.window.isVisible())                         # the close was held back
            self.assertTrue(self.window.close_pending)
            self.assertTrue(self.window.leak_cancel.is_set())                # and the check was told to stop
            gate.set()
            self.finish()
        self.qt.processEvents()
        self.assertFalse(self.window.isVisible())


class ReportTests(unittest.TestCase):
    def render(self, breaches):
        return hub.render({"target": "someone@example.org", "kind": "email", "started": "2026-10-08T12:00:00", "duration": 3.0, "status": "complete",
                           "results": [hub.result("Leaks", 0, "", breaches=breaches)]})

    def test_hibp_data_is_credited_with_a_link(self):
        page = self.render([breach("Canva", 2019, ["Passwords"], source="HIBP")])
        self.assertIn('href="https://haveibeenpwned.com"', page)
        self.assertIn("CC BY 4.0", page)
        self.assertIn("never the leaked passwords", page)

    def test_without_hibp_there_is_no_credit_but_the_caveat_stays(self):
        page = self.render([breach("Adobe", 2013, ["Passwords"])])
        self.assertNotIn("haveibeenpwned.com", page)
        self.assertIn("does not mean an address is safe", page)

    def test_breach_names_are_escaped(self):
        page = self.render([breach("<script>alert(1)</script>", 2019, ["Passwords"])])
        self.assertNotIn("<script>alert(1)</script>", page)
        self.assertIn("&lt;script&gt;", page)

    def test_the_old_self_search_wording_is_gone(self):
        page = self.render([])
        self.assertNotIn("Search only yourself", page)
        self.assertIn("lawful, authorized investigations", page)


if __name__ == "__main__":
    unittest.main()
