import csv
import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch
import osinthub as hub

class EngineTests(unittest.TestCase):
    def test_detect_and_validate(self):
        for target, expected in [("name_here", "username"), ("example.org", "domain"), ("team@example.org", "email"), ("+421 900 123 456", "phone")]:
            self.assertEqual(hub.validate(target)[1], expected)
        self.assertEqual(hub.validate("@sample", "username"), ("sample", "username"))
        self.assertEqual(hub.validate("EXAMPLE.ORG.", "domain")[0], "example.org")
        self.assertEqual(hub.validate("čaj.sk", "domain")[0], "xn--aj-dma.sk")

    def test_reject_invalid_input(self):
        for target, kind in [("", None), ("--help", "username"), ("a b", "username"), ("a@b", "email"), ("-bad.org", "domain"), ("https://example.org", "domain"), ("+1", "phone"), ("missing image.jpg", None)]:
            with self.subTest(target=target), self.assertRaises(ValueError):
                hub.validate(target, kind)

    def test_email_routes_without_claiming_ownership(self):
        # The leak check always runs on the whole address; the other sources search the name or the domain.
        personal = hub.jobs_for("team@gmail.com", "email")
        self.assertEqual([name for name, _, _ in personal], ["Leaks", "Sherlock", "Maigret"])
        self.assertEqual(personal[0][2], "team@gmail.com")
        self.assertEqual(len(hub.jobs_for("team@example.org", "email")), 5)
        # A name that can't be a username still gets the leak check.
        self.assertEqual([name for name, _, _ in hub.jobs_for("a+b@gmail.com", "email")], ["Leaks"])

    def test_accounts_deduplicate_by_url(self):
        data = [{"tool": t, "found": [{"site": "Site", "url": "https://example.org/u"}]} for t in ("Sherlock", "Maigret")]
        rows = hub.flatten(data)
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]["source"], "Sherlock, Maigret")

    def test_www_and_trailing_slash_deduplicate(self):
        rows=hub.flatten([{"tool":"Sherlock","found":[{"site":"GitHub","url":"https://www.github.com/example/"}]},{"tool":"Maigret","found":[{"site":"GitHub","url":"https://github.com/example"}]}])
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]["source"],"Sherlock, Maigret")

    def test_sherlock_csv_adapter(self):
        with tempfile.TemporaryDirectory() as temp:
            def fake_run(cmd, **kwargs):
                out = Path(kwargs["cwd"]) / "test.csv"
                out.write_text("name,url_user,exists\nSite,https://example.org/u,Claimed\nOther,https://example.org/x,Available\n", encoding="utf-8")
                return 0,"done"
            with patch.object(hub, "run", side_effect=fake_run):
                result = hub.m_sherlock("user",Path(temp),True)
            self.assertEqual(len(result["found"]),1)
            self.assertTrue(result["ok"])

    def test_maigret_json_adapter(self):
        with tempfile.TemporaryDirectory() as temp:
            def fake_run(cmd, **kwargs):
                (Path(kwargs["cwd"])/"report_user_simple.json").write_text(json.dumps({"Site":{"url_user":"https://example.org/u","status":{"status":"Claimed","tags":["tech"],"ids":{"id":12}}}}),encoding="utf-8")
                return 0,"done"
            with patch.object(hub,"run",side_effect=fake_run):
                result = hub.m_maigret("user",Path(temp),True)
            self.assertEqual(result["ids"]["id"],["12"])
            self.assertEqual(result["found"][0]["tags"],"tech")

    def test_image_path_with_spaces_and_metadata(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)/"fotka s medzerou.png"
            Image.new("RGB",(32,24)).save(path)
            report = hub.scan(str(path),out=Path(temp)/"reports")
            self.assertEqual(report["status"],"complete")
            self.assertEqual(report["results"][0]["important"]["Dimensions"],"32 × 24 px")
            self.assertEqual(len(report["results"][0]["important"]["SHA-256"]),64)
            for file in report["files"].values():
                self.assertTrue(Path(file).is_file())

    def test_bad_image_reports_failure_without_crash(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/"bad.jpg"
            path.write_text("not an image")
            report=hub.scan(str(path),out=Path(temp)/"reports")
            self.assertEqual(report["status"],"failed")

    def test_exif_gps_south_and_west(self):
        from PIL import Image
        from PIL.TiffImagePlugin import IFDRational as Rational
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/"gps.jpg"
            exif=Image.Exif()
            exif[34853]={1:"S",2:(Rational(48),Rational(30),Rational(0)),3:"W",4:(Rational(17),Rational(15),Rational(0))}
            Image.new("RGB",(20,20)).save(path,exif=exif)
            result=hub.m_image(str(path),Path(temp),True)
            self.assertEqual(result["gps"]["lat"],-48.5)
            self.assertEqual(result["gps"]["lon"],-17.25)
            self.assertTrue(hub.safe_url(result["gps"]["map"]))

    def test_reports_from_2_0_keep_their_map_link(self):
        rows = hub.flatten([{"tool": "EXIF", "gps": {"lat": 1, "lon": 2, "mapa": "https://www.openstreetmap.org/?mlat=1&mlon=2"}}])
        self.assertEqual(rows[0]["url"], "https://www.openstreetmap.org/?mlat=1&mlon=2")

    def test_partial_failure_preserves_success(self):
        def broken(*args):
            raise RuntimeError("source offline")
        def good(*args):
            return hub.result("Good",records=[{"type":"A","value":"192.0.2.1"}])
        with tempfile.TemporaryDirectory() as temp, patch.object(hub,"jobs_for",return_value=[("Bad",broken,"example.org"),("Good",good,"example.org")]):
            events=[]
            report=hub.scan("example.org",callback=events.append,out=temp)
            self.assertEqual(report["status"],"partial")
            self.assertEqual(len(hub.flatten(report["results"])),1)
            self.assertEqual(events[-1]["state"],"finished")

    def test_cancel_terminates_real_process(self):
        import sys
        context=hub.ScanContext()
        token=hub.CONTEXT.set(context)
        timer=threading.Timer(.25,context.cancel.set)
        timer.start()
        start=time.monotonic()
        try:
            with self.assertRaises(hub.Cancelled):
                hub.run([sys.executable,"-c","import time; time.sleep(30)"])
            self.assertLess(time.monotonic()-start,5)
        finally:
            timer.cancel()
            hub.CONTEXT.reset(token)

    def test_timeout_terminates_process(self):
        import sys
        code,log=hub.run([sys.executable,"-c","import time; time.sleep(30)"],timeout=.2)
        self.assertEqual(code,-1)
        self.assertIn("limit",log)

    def test_cancelled_scan_still_saves(self):
        cancel=threading.Event()
        cancel.set()
        with tempfile.TemporaryDirectory() as temp:
            report=hub.scan("example.org",cancel=cancel,out=temp)
            self.assertEqual(report["status"],"cancelled")
            self.assertTrue(Path(report["files"]["json"]).exists())

    def test_export_escaping_csv_and_unique_names(self):
        report={"schema":2,"id":"12345678a","target":"example.org","kind":"domain","started":"now","duration":0,"status":"complete","results":[hub.result("<script>",records=[{"type":"TXT","value":"=2+2<script>"}])]}
        with tempfile.TemporaryDirectory() as temp:
            hub.save_report(report,temp)
            first=report["files"]["json"]
            self.assertIn("example.org",first)
            rendered=Path(report["files"]["html"]).read_text(encoding="utf-8")
            self.assertNotIn("<script>",rendered)
            with open(report["files"]["csv"],encoding="utf-8-sig",newline="") as handle:
                self.assertEqual(list(csv.DictReader(handle))[0]["value"],"'=2+2<script>")
            report["id"]="98765432b"
            hub.save_report(report,temp)
            self.assertNotEqual(first,report["files"]["json"])
            self.assertTrue(Path(first).exists())

    def test_safe_urls(self):
        for value in ("javascript:alert(1)","file:///etc/passwd","https://user:password@example.org","http://[bad"):
            self.assertFalse(hub.safe_url(value))
        self.assertTrue(hub.safe_url("https://example.org"))

    def test_history_skips_old_and_corrupt_json(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(hub,"REPORTS",Path(temp)):
            (Path(temp)/"bad.json").write_text("{")
            (Path(temp)/"old.json").write_text("[]")
            (Path(temp)/"incomplete.json").write_text('{"schema":2,"kind":"domain","results":[]}')
            report={"schema":2,"id":"abcdef123","target":"example.org","kind":"domain","started":"now","duration":0,"status":"complete","results":[]}
            hub.save_report(report,temp)
            self.assertEqual(len(hub.history()),1)

if __name__=="__main__":
    unittest.main()
