import json
import unittest
import urllib.error
from unittest.mock import patch, MagicMock
import osinthub as hub
import leaks

XPOSED_BODY = json.dumps({"ExposedBreaches": {"breaches_details": [
    {"breach": "Adobe", "domain": "adobe.com", "xposed_date": "2013", "xposed_data": "Email addresses;Password hints;Passwords;Usernames",
     "xposed_records": 152445165, "password_risk": "easytocrack", "verified": "Yes"},
    {"breach": "Canva", "domain": "canva.com", "xposed_date": "2019", "xposed_data": "Email addresses;Names;Passwords",
     "xposed_records": 137272116, "password_risk": "hardtocrack", "verified": "Yes"},
    {"breach": "Dropbox", "domain": "dropbox.com", "xposed_date": "2012", "xposed_data": "Email addresses;Passwords",
     "xposed_records": "68648009", "password_risk": "plaintext", "verified": "Yes"},
    {"breach": "Forum", "domain": "", "xposed_date": "", "xposed_data": "Email addresses", "xposed_records": 0, "password_risk": "unknown"},
    {"breach": "adobe", "domain": "adobe.com", "xposed_date": "2013", "xposed_data": "Email addresses", "xposed_records": 1},   # duplicate name
]}})
HIBP_BODY = json.dumps([
    {"Name": "Adobe", "Title": "Adobe", "Domain": "adobe.com", "BreachDate": "2013-10-04", "PwnCount": 152445165,
     "DataClasses": ["Email addresses", "Password hints", "Passwords", "Usernames"], "IsVerified": True, "IsSensitive": False},
    {"Name": "Stealer", "Title": "Alien Stealer Logs", "Domain": "", "BreachDate": "2024-02-01", "PwnCount": 23000000,
     "DataClasses": ["Email addresses", "Passwords"], "IsVerified": True, "IsStealerLog": True},
    {"Name": "Fake", "Title": "Fabricated", "Domain": "x.com", "BreachDate": "2020-01-01", "PwnCount": 5, "DataClasses": ["Email addresses"], "IsFabricated": True},
])

def http_error(code, headers=None):
    return urllib.error.HTTPError("https://example.test", code, "error", headers or {}, None)


class ParsingTests(unittest.TestCase):
    def test_xposed_details_are_parsed_and_deduplicated(self):
        with patch.object(leaks, "_request", return_value=(200, XPOSED_BODY)):
            rows = {r["name"]: r for r in leaks.xposed_breaches("a@b.co")}
        self.assertEqual(set(rows), {"Adobe", "Canva", "Dropbox", "Forum"})
        self.assertEqual(rows["Adobe"]["records"], 152445165)
        self.assertEqual(rows["Adobe"]["password_risk"], "weak hash")
        self.assertEqual(rows["Dropbox"]["records"], 68648009)             # numbers sent as text still count
        self.assertEqual(rows["Dropbox"]["password_risk"], "plain text")
        self.assertEqual(rows["Forum"]["password_risk"], "")                # "unknown" says nothing
        self.assertIsNone(rows["Forum"]["records"])
        self.assertEqual(rows["Adobe"]["data"], ["Email addresses", "Password hints", "Passwords", "Usernames"])

    def test_xposed_not_found_in_both_shapes(self):
        empty = json.dumps({"BreachesSummary": {"site": ""}, "ExposedBreaches": None, "ExposedPastes": None})
        with patch.object(leaks, "_request", return_value=(200, empty)):
            self.assertEqual(leaks.xposed_breaches("a@b.co"), [])
        with patch.object(leaks, "_request", return_value=(404, "")):
            self.assertEqual(leaks.xposed_breaches("a@b.co"), [])
        with patch.object(leaks, "_request", return_value=(200, json.dumps({"Error": "Not found", "email": None}))):
            self.assertEqual(leaks.xposed_breaches("a@b.co"), [])

    def test_unreadable_answer_is_a_clear_error(self):
        with patch.object(leaks, "_request", return_value=(200, "<html>maintenance</html>")):
            with self.assertRaises(leaks.EngineError):
                leaks.xposed_breaches("a@b.co")

    def test_xposed_names_only(self):
        body = json.dumps({"breaches": [["Adobe", "LinkedIn", "Adobe"]], "email": "a@b.co", "status": "success"})
        with patch.object(leaks, "_request", return_value=(200, body)):
            rows = leaks.xposed_names("a@b.co")
        self.assertEqual([r["name"] for r in rows], ["Adobe", "LinkedIn"])
        self.assertTrue(all(r["data"] == [] and r["date"] == "" for r in rows))

    def test_hibp_rows_flags_and_fabricated_breaches(self):
        with patch.object(leaks, "_request", return_value=(200, HIBP_BODY)) as request:
            rows = leaks.hibp_breaches("a@b.co", "k" * 32)
        url, headers = request.call_args[0][0], request.call_args[0][1]
        self.assertIn("/breachedAccount/a%40b.co?truncateResponse=false", url)
        self.assertEqual(headers, {"hibp-api-key": "k" * 32})
        self.assertEqual([r["name"] for r in rows], ["Adobe", "Alien Stealer Logs"])    # the fabricated one is dropped
        self.assertEqual(rows[1]["flags"], ["stealer log"])
        self.assertEqual(rows[0]["date"], "2013-10-04")

    def test_severity_and_year(self):
        self.assertEqual(leaks.severity({"data": ["Email addresses", "Passwords"]}), 3)
        self.assertEqual(leaks.severity({"data": ["Email addresses", "Phone numbers"]}), 2)
        self.assertEqual(leaks.severity({"data": ["Email addresses", "Usernames"]}), 1)     # "name" and "address" inside those words must not count
        self.assertEqual(leaks.severity({"data": ["Email addresses", "IP addresses", "Usernames"]}), 2)
        self.assertEqual(leaks.severity({"data": ["Names", "Dates of birth", "Genders"]}), 2)
        self.assertEqual(leaks.severity({"data": ["Password hints"]}), 3)
        self.assertEqual(leaks.severity({"data": []}), 0)                                   # names-only answers don't claim to know
        self.assertEqual(leaks.year_of({"date": "2013-10-04"}), 2013)
        self.assertEqual(leaks.year_of({"date": "2019"}), 2019)
        self.assertEqual(leaks.year_of({"date": ""}), 0)
        self.assertEqual(leaks.year_of({"date": "0000"}), 0)
        self.assertEqual(leaks.year_of({"date": "9999"}), 0)


class MergeTests(unittest.TestCase):
    def test_merge_joins_sources_keeps_details_and_sorts_newest_first(self):
        with patch.object(leaks, "_request", side_effect=[(200, HIBP_BODY), (200, XPOSED_BODY)]):
            hibp = leaks.hibp_breaches("a@b.co", "k" * 32)
            xposed = leaks.xposed_breaches("a@b.co")
        merged = leaks.merge(hibp, xposed)
        names = [r["name"] for r in merged]
        self.assertEqual(names, ["Alien Stealer Logs", "Canva", "Adobe", "Dropbox", "Forum"])
        adobe = merged[2]
        self.assertEqual(adobe["source"], "HIBP + XposedOrNot")
        self.assertEqual(adobe["password_risk"], "weak hash")      # only XposedOrNot knows how Adobe stored passwords
        self.assertEqual(adobe["date"], "2013-10-04")              # HIBP's fuller date wins
        self.assertEqual(len(merged), len({n.lower() for n in names}))

    def test_summary(self):
        with patch.object(leaks, "_request", return_value=(200, XPOSED_BODY)):
            rows = leaks.xposed_breaches("a@b.co")
        self.assertEqual(leaks.breach_summary(rows), "4 breaches since 2012 · passwords in 3 · 1 in plain text")
        self.assertEqual(leaks.breach_summary([]), "No breaches found")
        self.assertEqual(leaks.breach_summary([{"name": "X", "date": "", "data": [], "records": None}]), "1 breach")


class CheckEmailTests(unittest.TestCase):
    def setUp(self):
        leaks._cache.clear()

    def test_combines_both_sources(self):
        with patch.object(leaks, "xposed_breaches", return_value=leaks.merge(
                [{"name": "Adobe", "date": "2013", "data": ["Passwords"], "records": 1, "source": "XposedOrNot", "password_risk": "weak hash", "flags": []}], [])), \
             patch.object(leaks, "hibp_breaches", return_value=[
                {"name": "Canva", "date": "2019", "data": ["Passwords"], "records": 2, "source": "HIBP", "password_risk": "", "flags": []}]):
            outcome = leaks.check_email("a@b.co", "k" * 32)
        self.assertEqual(outcome["sources"], ["XposedOrNot", "Have I Been Pwned"])
        self.assertEqual([b["name"] for b in outcome["breaches"]], ["Canva", "Adobe"])
        self.assertEqual(outcome["errors"], [])

    def test_hibp_is_skipped_without_a_key(self):
        with patch.object(leaks, "xposed_breaches", return_value=[]), patch.object(leaks, "hibp_breaches") as hibp:
            outcome = leaks.check_email("a@b.co", "")
        hibp.assert_not_called()
        self.assertEqual(outcome["sources"], ["XposedOrNot"])

    def test_rate_limited_detail_falls_back_to_names(self):
        names = [{"name": "Adobe", "date": "", "data": [], "records": None, "source": "XposedOrNot", "password_risk": "", "flags": []}]
        with patch.object(leaks, "xposed_breaches", side_effect=leaks.RateLimited("limit", 1800)), patch.object(leaks, "xposed_names", return_value=names):
            outcome = leaks.check_email("a@b.co", "")
        self.assertEqual([b["name"] for b in outcome["breaches"]], ["Adobe"])
        self.assertEqual(outcome["limited"], 1800)
        self.assertIn("names only", outcome["errors"][0])
        self.assertIn("30 min", outcome["errors"][0])

    def test_failed_source_does_not_stop_the_other(self):
        with patch.object(leaks, "xposed_breaches", side_effect=leaks.EngineError("Can't reach XposedOrNot.")), \
             patch.object(leaks, "hibp_breaches", return_value=[{"name": "Canva", "date": "2019", "data": [], "records": None, "source": "HIBP", "password_risk": "", "flags": []}]):
            outcome = leaks.check_email("a@b.co", "k" * 32)
        self.assertEqual(outcome["sources"], ["Have I Been Pwned"])
        self.assertEqual(len(outcome["breaches"]), 1)
        self.assertIn("XposedOrNot", outcome["errors"][0])

    def test_every_source_failing_raises_without_a_prefix(self):
        with patch.object(leaks, "xposed_breaches", side_effect=leaks.EngineError("Can't reach XposedOrNot. Check the internet connection.")):
            with self.assertRaises(leaks.EngineError) as caught:
                leaks.check_email("a@b.co", "")
        self.assertEqual(str(caught.exception), "Can't reach XposedOrNot. Check the internet connection.")

    def test_rate_limit_everywhere_raises_with_wait_time(self):
        with patch.object(leaks, "xposed_breaches", side_effect=leaks.RateLimited("XposedOrNot rate limit reached. Try again in 20 min.", 1200)), \
             patch.object(leaks, "xposed_names", side_effect=leaks.RateLimited("XposedOrNot rate limit reached. Try again in 20 min.", 1200)):
            with self.assertRaises(leaks.RateLimited) as caught:
                leaks.check_email("a@b.co", "")
        self.assertEqual(caught.exception.retry_after, 1200)

    def test_repeated_checks_come_from_memory_so_the_free_quota_is_kept(self):
        with patch.object(leaks, "xposed_breaches", return_value=[]) as call:
            first = leaks.check_email("A@B.co", "")
            second = leaks.check_email("a@b.co", "")
            leaks.check_email("a@b.co", "", use_cache=False)
        self.assertEqual(call.call_count, 2)
        self.assertNotIn("cached", first)
        self.assertTrue(second["cached"])

    def test_results_with_errors_are_not_cached(self):
        with patch.object(leaks, "xposed_breaches", return_value=[]), \
             patch.object(leaks, "hibp_breaches", side_effect=leaks.EngineError("Have I Been Pwned rejected the API key.")) as hibp:
            leaks.check_email("a@b.co", "k" * 32)
            leaks.check_email("a@b.co", "k" * 32)
        self.assertEqual(hibp.call_count, 2)

    def test_cancel_between_sources(self):
        def stop():
            raise hub.Cancelled("Scan stopped.")
        with patch.object(leaks, "xposed_breaches", return_value=[]):
            with self.assertRaises(hub.Cancelled):
                leaks.check_email("a@b.co", "k" * 32, stop)


class RequestTests(unittest.TestCase):
    def test_rate_limit_reports_the_wait(self):
        with patch("urllib.request.urlopen", side_effect=http_error(429, {"Retry-After": "120"})):
            with self.assertRaises(leaks.RateLimited) as caught:
                leaks._request("https://example.test", {}, 5, "XposedOrNot")
        self.assertEqual(caught.exception.retry_after, 120)
        self.assertIn("2 min", str(caught.exception))

    def test_rate_limit_without_a_header(self):
        with patch("urllib.request.urlopen", side_effect=http_error(429)):
            with self.assertRaises(leaks.RateLimited) as caught:
                leaks._request("https://example.test", {}, 5, "XposedOrNot")
        self.assertEqual(caught.exception.retry_after, 0)
        self.assertIn("a moment", str(caught.exception))

    def test_bad_key_and_server_errors(self):
        with patch("urllib.request.urlopen", side_effect=http_error(401)):
            with self.assertRaisesRegex(leaks.EngineError, "rejected the API key"):
                leaks._request("https://example.test", {}, 5, "Have I Been Pwned")
        with patch("urllib.request.urlopen", side_effect=http_error(503)):
            with self.assertRaisesRegex(leaks.EngineError, "error 503"):
                leaks._request("https://example.test", {}, 5, "XposedOrNot")

    def test_offline(self):
        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("no route")):
            with self.assertRaisesRegex(leaks.EngineError, "Can't reach XposedOrNot"):
                leaks._request("https://example.test", {}, 5, "XposedOrNot")

    def test_404_is_a_result_only_when_the_caller_expects_it(self):
        with patch("urllib.request.urlopen", side_effect=http_error(404)):
            self.assertEqual(leaks._request("https://example.test", {}, 5, "X", accept_404=True), (404, ""))
            with self.assertRaises(leaks.EngineError):
                leaks._request("https://example.test", {}, 5, "X")

    def test_user_agent_is_always_sent(self):
        response = MagicMock()
        response.__enter__.return_value = response
        response.status, response.read.return_value = 200, b"{}"
        with patch("urllib.request.urlopen", return_value=response) as opened:
            leaks._request("https://example.test", {"hibp-api-key": "k"}, 5, "HIBP")
        request = opened.call_args[0][0]
        self.assertEqual(request.get_header("User-agent"), leaks.USER_AGENT)
        self.assertEqual(request.get_header("Hibp-api-key"), "k")


class PasswordTests(unittest.TestCase):
    def test_only_a_five_character_prefix_is_sent_and_the_match_is_local(self):
        import hashlib
        digest = hashlib.sha1(b"hunter2").hexdigest().upper()
        body = "\r\n".join([digest[5:] + ":3861", "0" * 35 + ":0", "ABCDEF" + "0" * 29 + ":17"])
        with patch.object(leaks, "_request", return_value=(200, body)) as request:
            self.assertEqual(leaks.password_pwned("hunter2"), 3861)
        url, headers = request.call_args[0][0], request.call_args[0][1]
        self.assertTrue(url.endswith("/range/" + digest[:5]))
        self.assertNotIn(digest[5:], url)
        self.assertNotIn("hunter2", url + json.dumps(headers))
        self.assertEqual(headers["Add-Padding"], "true")

    def test_padding_lines_and_misses_count_as_not_found(self):
        import hashlib
        digest = hashlib.sha1(b"hunter2").hexdigest().upper()
        with patch.object(leaks, "_request", return_value=(200, digest[5:] + ":0\r\nFFFFF" + "0" * 30 + ":9")):
            self.assertEqual(leaks.password_pwned("hunter2"), 0)       # a padded filler line has a count of 0
        with patch.object(leaks, "_request", return_value=(200, "")):
            self.assertEqual(leaks.password_pwned("hunter2"), 0)

    def test_unicode_and_empty_passwords(self):
        with patch.object(leaks, "_request", return_value=(200, "")):
            self.assertEqual(leaks.password_pwned("héslo-čaj-€"), 0)
        with self.assertRaises(leaks.EngineError):
            leaks.password_pwned("")

    def test_the_password_is_never_in_an_error_message(self):
        with patch("urllib.request.urlopen", side_effect=http_error(503)):
            with self.assertRaises(leaks.EngineError) as caught:
                leaks.password_pwned("s3cret-pass")
        self.assertNotIn("s3cret", str(caught.exception))


class ScanIntegrationTests(unittest.TestCase):
    def setUp(self):
        leaks._cache.clear()

    def test_email_scan_includes_leaks_and_reports_rows(self):
        found = {"breaches": [{"name": "Adobe", "domain": "adobe.com", "date": "2013", "data": ["Email addresses", "Passwords"], "records": 152445165,
                               "source": "XposedOrNot", "password_risk": "plain text", "flags": ["stealer log"]}],
                 "sources": ["XposedOrNot"], "errors": [], "limited": 0}
        with patch.object(leaks, "check_email", return_value=found), patch.object(leaks, "load_key", return_value=""):
            data = leaks.m_leaks("a@b.co", None, True)
        self.assertEqual((data["tool"], data["status"], data["ok"]), ("Leaks", "ok", True))
        rows = hub.flatten([data])
        self.assertEqual([r["category"] for r in rows], ["Leak"])
        self.assertEqual(rows[0]["label"], "Adobe")
        for part in ("adobe.com", "2013", "Email addresses, Passwords", "152,445,165 records", "passwords stored as plain text", "stealer log"):
            self.assertIn(part, rows[0]["value"])
        self.assertEqual(rows[0]["url"], "")                              # breach domains are never linked

    def test_a_partial_answer_is_marked_partial(self):
        found = {"breaches": [], "sources": ["XposedOrNot"], "errors": ["Have I Been Pwned: rejected the API key."], "limited": 0}
        with patch.object(leaks, "check_email", return_value=found), patch.object(leaks, "load_key", return_value="k"):
            data = leaks.m_leaks("a@b.co", None, True)
        self.assertEqual((data["status"], data["ok"]), ("partial", False))

    def test_a_failure_is_a_source_error_not_a_crash(self):
        with patch.object(leaks, "check_email", side_effect=leaks.EngineError("Can't reach XposedOrNot.")), patch.object(leaks, "load_key", return_value=""):
            data = leaks.m_leaks("a@b.co", None, True)
        self.assertEqual((data["status"], data["ok"]), ("error", False))
        self.assertIn("Can't reach", data["log"])

    def test_full_scan_report_for_an_email(self):
        import tempfile
        from pathlib import Path
        found = {"breaches": [{"name": "Adobe", "domain": "adobe.com", "date": "2013", "data": ["Passwords"], "records": 5,
                               "source": "XposedOrNot", "password_risk": "", "flags": []}], "sources": ["XposedOrNot"], "errors": [], "limited": 0}
        def quiet(target, work, fast):
            return hub.result("Sherlock", 0, "", found=[])
        with tempfile.TemporaryDirectory() as temp, patch.object(leaks, "check_email", return_value=found), patch.object(leaks, "load_key", return_value=""), \
             patch.object(hub, "m_sherlock", quiet), patch.object(hub, "m_maigret", lambda t, w, f: hub.result("Maigret", 0, "", found=[])):
            report = hub.scan("someone@gmail.com", "email", True, out=Path(temp))
            html = Path(report["files"]["html"]).read_text(encoding="utf-8")
            csv_text = Path(report["files"]["csv"]).read_text(encoding="utf-8-sig")
        self.assertEqual(report["status"], "complete")
        self.assertEqual([r["tool"] for r in report["results"]], ["Leaks", "Sherlock", "Maigret"])
        self.assertIn("Adobe", html)
        self.assertIn("LEAK", html)
        self.assertIn("Leak,Adobe", csv_text)


class KeyTests(unittest.TestCase):
    def test_hibp_is_a_known_key_service(self):
        import geolocate
        self.assertEqual(leaks.SERVICE, "hibp")
        self.assertIn("hibp", geolocate.SERVICES)
        self.assertIn("haveibeenpwned.com", geolocate.SERVICES["hibp"]["key_url"])
        self.assertTrue(geolocate.SERVICES["hibp"]["used_by"])


if __name__ == "__main__":
    unittest.main()
