import base64
import io
import json
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from PIL import Image
import geolocate
import osinthub as hub


def photo_in(folder, size=(60, 40), color="#335533"):
    path = Path(folder) / "photo.jpg"
    Image.new("RGB", size, color).save(path)
    return path


def thumb_b64(size=(300, 300), fmt="PNG"):
    buffer = io.BytesIO()
    Image.new("RGB", size, "#aa8844").save(buffer, fmt)
    return base64.b64encode(buffer.getvalue()).decode("ascii")


class GeoclipPlacesTests(unittest.TestCase):
    """GeoCLIP's 100,000 place features are computed once, in small batches, and reused."""
    def setUp(self):
        import torch
        self.torch = torch
        torch.manual_seed(7)
        self.temp = tempfile.TemporaryDirectory()
        self.cache = Path(self.temp.name) / "models" / "places.pt"
        outer = self
        class Model:
            gps_gallery = torch.randn(50, 2)
            linear = torch.nn.Linear(2, 8)
            calls = 0
            def location_encoder(self, points):
                Model.calls += 1
                return self.linear(points)
        self.model = Model()
        Model.calls = 0

    def tearDown(self):
        self.temp.cleanup()

    def expected(self):
        return self.torch.nn.functional.normalize(self.model.linear(self.model.gps_gallery), dim=1)

    def test_batches_give_the_same_features_as_one_big_pass(self):
        features = geolocate.gallery_features(self.model, self.cache, chunk=16)
        self.assertEqual(type(self.model).calls, 4)                      # 50 places in batches of 16
        self.assertTrue(self.torch.allclose(features, self.expected(), atol=1e-6))
        self.assertTrue(self.torch.allclose(features.norm(dim=1), self.torch.ones(50), atol=1e-5))

    def test_the_second_photo_reuses_the_saved_features(self):
        geolocate.gallery_features(self.model, self.cache, chunk=16)
        type(self.model).calls = 0
        again = geolocate.gallery_features(self.model, self.cache, chunk=16)
        self.assertEqual(type(self.model).calls, 0)
        self.assertTrue(self.cache.exists())
        self.assertFalse(Path(str(self.cache) + ".tmp").exists())
        self.assertTrue(self.torch.allclose(again, self.expected(), atol=1e-6))

    def test_a_damaged_or_outdated_file_is_rebuilt(self):
        self.cache.parent.mkdir(parents=True)
        self.cache.write_bytes(b"not a tensor")
        features = geolocate.gallery_features(self.model, self.cache, chunk=25)
        self.assertTrue(self.torch.allclose(features, self.expected(), atol=1e-6))
        self.torch.save(self.torch.zeros(10, 8), self.cache)             # saved for a different number of places
        type(self.model).calls = 0
        features = geolocate.gallery_features(self.model, self.cache, chunk=25)
        self.assertEqual(type(self.model).calls, 2)
        self.assertEqual(features.shape, (50, 8))

    def test_an_unwritable_cache_does_not_stop_the_search(self):
        blocked = Path(self.temp.name) / "file"
        blocked.write_text("x")
        features = geolocate.gallery_features(self.model, blocked / "places.pt", chunk=25)   # the "folder" is a file
        self.assertEqual(features.shape, (50, 8))

    def test_the_cache_is_named_after_the_model_version(self):
        with patch.object(geolocate, "user_dir", return_value=Path(self.temp.name)):
            self.assertRegex(geolocate.places_cache().name, r"^geoclip-places-[\d.]+\.pt$")

    def test_first_run_is_announced_and_given_time(self):
        for item in (patch.object(geolocate, "user_dir", return_value=Path(self.temp.name)),
                     patch.object(geolocate, "geoclip_installed", return_value=True),
                     patch.object(geolocate, "geoclip_downloaded", return_value=True)):
            item.start()
            self.addCleanup(item.stop)
        self.assertEqual(geolocate.engine_status()["geoclip"], (True, "First run is slow"))
        seen = {}
        def fake_run(cmd, **kwargs):
            seen["timeout"] = kwargs["timeout"]
            return 1, "stopped"
        with patch.object(hub, "run", fake_run):
            geolocate.m_geoclip(str(photo_in(self.temp.name)), Path(self.temp.name), True)
        self.assertEqual(seen["timeout"], 3600)               # preparing the places can take minutes on a busy computer
        places = geolocate.places_cache()
        places.parent.mkdir(parents=True, exist_ok=True)
        places.write_bytes(b"x")
        self.assertEqual(geolocate.engine_status()["geoclip"], (True, "Ready"))
        with patch.object(hub, "run", fake_run):
            geolocate.m_geoclip(str(photo_in(self.temp.name)), Path(self.temp.name), True)
        self.assertEqual(seen["timeout"], 300)


class VisionTests(unittest.TestCase):
    def test_landmarks_return_exact_coordinates(self):
        reply = {"responses": [{"landmarkAnnotations": [
            {"description": "Bratislava Castle", "score": 0.91, "locations": [{"latLng": {"latitude": 48.1421, "longitude": 17.1002}}]},
            {"description": "No place", "score": 0.5, "locations": []}]}]}
        with tempfile.TemporaryDirectory() as temp, patch.object(geolocate, "_post_json", return_value=reply) as call:
            rows, clues = geolocate.vision_landmarks(photo_in(temp), "key")
        self.assertEqual([(r["place"], r["lat"], r["lon"], r["confidence"]) for r in rows], [("Bratislava Castle", 48.1421, 17.1002, 0.91)])
        self.assertEqual(clues, [])
        body = call.call_args[0][1]
        self.assertEqual(body["requests"][0]["features"][0]["type"], "LANDMARK_DETECTION")
        self.assertEqual(call.call_args[0][2], {"x-goog-api-key": "key"})        # the key travels in a header, never in the URL

    def test_no_landmark_is_a_plain_message(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(geolocate, "_post_json", return_value={"responses": [{}]}):
            with self.assertRaisesRegex(geolocate.EngineError, "No well-known landmark"):
                geolocate.vision_landmarks(photo_in(temp), "key")

    def test_web_matches_are_cleaned_and_deduplicated(self):
        web = {"webDetection": {
            "pagesWithMatchingImages": [
                {"url": "https://example.org/a", "pageTitle": "<b>Owl</b> &amp; friends", "fullMatchingImages": [{"url": "https://example.org/a.jpg"}]},
                {"url": "https://example.org/b", "pageTitle": "", "partialMatchingImages": [{"url": "https://example.org/b.jpg"}]},
                {"url": "javascript:alert(1)", "pageTitle": "bad"},
                {"url": "https://user:pass@example.org/c", "pageTitle": "credentials in the address"},
            ],
            "fullMatchingImages": [{"url": "https://example.org/a.jpg"}, {"url": "https://img.example.org/1.jpg"}],
            "partialMatchingImages": [{"url": "https://img.example.org/2.jpg"}],
            "visuallySimilarImages": [{"url": "https://img.example.org/3.jpg"}, {"url": "https://img.example.org/3.jpg"}],
            "bestGuessLabels": [{"label": "barred owl"}],
            "webEntities": [{"description": "Barred owl", "score": 0.93}, {"score": 0.4}]}}
        with tempfile.TemporaryDirectory() as temp, patch.object(geolocate, "_post_json", return_value={"responses": [web]}):
            matches, labels, entities = geolocate.vision_web(photo_in(temp), "key")
        urls = [m["url"] for m in matches]
        self.assertEqual(urls, ["https://example.org/a", "https://example.org/b", "https://example.org/a.jpg", "https://img.example.org/1.jpg",
                                "https://img.example.org/2.jpg", "https://img.example.org/3.jpg"])
        self.assertEqual([m["kind"] for m in matches[2:]], ["Full image match", "Full image match", "Partial image match", "Similar image"])
        self.assertNotIn("javascript:alert(1)", urls)
        self.assertFalse(any("user:pass" in u for u in urls))
        self.assertEqual(len(urls), len(set(urls)))
        first = matches[0]
        self.assertEqual((first["kind"], first["title"]), ("Page · full match", "Owl & friends"))
        self.assertEqual(matches[1]["kind"], "Page · partial match")
        self.assertEqual(matches[1]["title"], "example.org")                      # untitled pages are named after their site
        self.assertEqual(labels, ["barred owl"])
        self.assertEqual(entities, ["Barred owl (0.93)"])

    def test_a_key_google_does_not_accept_is_explained(self):
        refused = geolocate.EngineError("Google Vision rejected the API key or the API isn't enabled for it. API keys are not supported by this API. "
                                        "Expected OAuth2 access token or other authentication credentials that assert a principal.")
        with tempfile.TemporaryDirectory() as temp, patch.object(geolocate, "_post_json", side_effect=refused):
            with self.assertRaises(geolocate.EngineError) as caught:
                geolocate.vision_landmarks(photo_in(temp), "AQ.something")
        self.assertIn("AIza", str(caught.exception))
        self.assertIn("Vertex", str(caught.exception))
        self.assertNotIn("OAuth2", str(caught.exception))

    def test_other_google_errors_pass_through_untouched(self):
        refused = geolocate.EngineError("Google Vision rejected the API key or the API isn't enabled for it. Cloud Vision API has not been used in project 123.")
        with tempfile.TemporaryDirectory() as temp, patch.object(geolocate, "_post_json", side_effect=refused):
            with self.assertRaisesRegex(geolocate.EngineError, "has not been used in project 123"):
                geolocate.vision_landmarks(photo_in(temp), "AIza" + "x" * 35)

    def test_vision_answer_with_an_error_object(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(geolocate, "_post_json", return_value={"responses": [{"error": {"message": "Bad image data."}}]}):
            with self.assertRaisesRegex(geolocate.EngineError, "Bad image data"):
                geolocate.vision_web(photo_in(temp), "key")


class FakeFaceCheck:
    """Stands in for requests.post against FaceCheck.ID."""
    def __init__(self, search_answers, upload=None):
        self.upload = upload or {"id_search": "s1", "input": [{"id_pic": "p1"}]}
        self.search_answers = list(search_answers)
        self.calls = []
    def __call__(self, url, **kwargs):
        self.calls.append((url.removeprefix("https://facecheck.id"), kwargs))
        path = self.calls[-1][0]
        response = MagicMock()
        if path == "/api/upload_pic":
            response.json.return_value = self.upload
        elif path == "/api/search":
            response.json.return_value = self.search_answers.pop(0) if len(self.search_answers) > 1 else self.search_answers[0]
        else:
            response.json.return_value = {}
        return response
    def paths(self):
        return [path for path, _ in self.calls]


class FaceCheckTests(unittest.TestCase):
    def search(self, fake, **options):
        with tempfile.TemporaryDirectory() as temp, patch("requests.post", fake), patch.object(geolocate.time, "sleep"):
            return geolocate.facecheck_search(photo_in(temp), "token", options.pop("demo", False), **options)

    def test_results_are_cleaned_and_the_upload_is_deleted(self):
        items = [{"score": 91.6, "url": "https://www.example.org/profile/1", "base64": thumb_b64()},
                 {"score": 40, "url": "javascript:alert(1)", "base64": ""},
                 {"score": 38, "url": "https://user:pw@example.org/x", "base64": ""},
                 {"score": 33, "url": "https://social.example.net/u/2", "base64": "not an image"}]
        fake = FakeFaceCheck([{"output": None, "progress": 20}, {"output": {"items": items}}])
        faces = self.search(fake)
        self.assertEqual([f["url"] for f in faces], ["https://www.example.org/profile/1", "https://social.example.net/u/2"])
        self.assertEqual(faces[0]["score"], 91)
        self.assertEqual(faces[0]["site"], "example.org")
        thumb = Image.open(io.BytesIO(base64.b64decode(faces[0]["thumb"])))
        self.assertEqual(thumb.format, "JPEG")
        self.assertLessEqual(max(thumb.size), 120)
        self.assertEqual(faces[1]["thumb"], "")                              # an unreadable thumbnail doesn't lose the match
        self.assertEqual(fake.paths(), ["/api/upload_pic", "/api/search", "/api/search", "/api/delete_pic"])
        delete = fake.calls[-1][1]
        self.assertEqual(delete["params"], {"id_search": "s1", "id_pic": "p1"})
        self.assertEqual(fake.calls[0][1]["headers"]["Authorization"], "token")

    def test_demo_flag_is_sent(self):
        fake = FakeFaceCheck([{"output": {"items": []}}])
        self.search(fake, demo=True)
        self.assertTrue(fake.calls[1][1]["json"]["demo"])
        fake = FakeFaceCheck([{"output": {"items": []}}])
        self.search(fake, demo=False)
        self.assertFalse(fake.calls[1][1]["json"]["demo"])

    def test_service_errors_are_reported_and_the_photo_is_still_deleted(self):
        fake = FakeFaceCheck([{"error": "Insufficient credits", "code": "INSUFFICIENT_CREDITS"}])
        with self.assertRaisesRegex(geolocate.EngineError, "Insufficient credits"):
            self.search(fake)
        self.assertEqual(fake.paths()[-1], "/api/delete_pic")

    def test_upload_errors_stop_before_searching(self):
        fake = FakeFaceCheck([], upload={"error": "Invalid token", "code": "UNAUTHORIZED"})
        with self.assertRaisesRegex(geolocate.EngineError, "Invalid token"):
            self.search(fake)
        self.assertEqual(fake.paths(), ["/api/upload_pic"])

    def test_cancelling_deletes_the_photo(self):
        fake = FakeFaceCheck([{"output": None}])
        def stop():
            raise hub.Cancelled("Scan stopped.")
        with self.assertRaises(hub.Cancelled):
            self.search(fake, check=stop)
        self.assertEqual(fake.paths()[-1], "/api/delete_pic")

    def test_a_search_that_never_finishes_gives_up(self):
        fake = FakeFaceCheck([{"output": None}])
        with self.assertRaisesRegex(geolocate.EngineError, "didn't finish"):
            self.search(fake, limit=-1)
        self.assertEqual(fake.paths()[-1], "/api/delete_pic")

    def test_network_failure(self):
        import requests
        with tempfile.TemporaryDirectory() as temp, patch("requests.post", side_effect=requests.ConnectionError("down")):
            with self.assertRaisesRegex(geolocate.EngineError, "Can't reach FaceCheck.ID"):
                geolocate.facecheck_search(photo_in(temp), "token", False)

    def test_results_are_capped(self):
        items = [{"score": 50, "url": f"https://example.org/{i}", "base64": ""} for i in range(200)]
        faces = self.search(FakeFaceCheck([{"output": {"items": items}}]))
        self.assertEqual(len(faces), 60)


class FaceGuardTests(unittest.TestCase):
    """Face search must never run on children or teenagers, and never without a stated purpose."""
    ADULT = {"a photo of a baby": 0.01, "a photo of a young child": 0.01, "a photo of a teenager": 0.02,
             "a photo of a young adult": 0.4, "a photo of an adult": 0.5, "a photo of an elderly person": 0.06}

    def run_job(self, purpose="Verifying a source for case 12", verdict=None, key="token", agecheck_code=0, demo=False):
        calls = {"search": 0}
        def fake_run(cmd, **kwargs):
            if agecheck_code == 0 and verdict is not None:
                Path(cmd[2]).write_text(json.dumps(verdict), encoding="utf-8")
            return agecheck_code, "worker log"
        def fake_search(photo, token, demo_mode, check=lambda: None, **kwargs):
            calls["search"] += 1
            return [{"score": 88, "url": "https://example.org/p", "site": "example.org", "thumb": ""}]
        with tempfile.TemporaryDirectory() as temp, patch.object(geolocate, "load_key", return_value=key), \
             patch.object(hub, "run", fake_run), patch.object(geolocate, "facecheck_search", fake_search):
            data = geolocate._face_job(purpose, demo)(str(photo_in(temp)), Path(temp), True)
        return data, calls

    def test_an_adult_photo_is_searched_and_records_the_purpose(self):
        data, calls = self.run_job(verdict=self.ADULT)
        self.assertEqual(data["status"], "ok")
        self.assertEqual(calls["search"], 1)
        self.assertEqual(data["purpose"], "Verifying a source for case 12")
        self.assertEqual(data["faces"][0]["url"], "https://example.org/p")
        self.assertIn("Minor estimate: 4%", data["log"])

    def test_a_child_is_blocked_before_anything_is_uploaded(self):
        child = {"a photo of a baby": 0.05, "a photo of a young child": 0.62, "a photo of a teenager": 0.1,
                 "a photo of a young adult": 0.1, "a photo of an adult": 0.1, "a photo of an elderly person": 0.03}
        data, calls = self.run_job(verdict=child)
        self.assertEqual((data["status"], data["ok"]), ("blocked", False))
        self.assertEqual(calls["search"], 0)
        self.assertIn("child or teenager", data["log"])

    def test_a_teenager_is_blocked(self):
        teen = {"a photo of a baby": 0.0, "a photo of a young child": 0.05, "a photo of a teenager": 0.55,
                "a photo of a young adult": 0.3, "a photo of an adult": 0.09, "a photo of an elderly person": 0.01}
        data, calls = self.run_job(verdict=teen)
        self.assertEqual(data["status"], "blocked")
        self.assertEqual(calls["search"], 0)

    def test_the_block_starts_at_thirty_percent(self):
        at_limit = {"a photo of a baby": 0.1, "a photo of a young child": 0.1, "a photo of a teenager": 0.1,
                    "a photo of a young adult": 0.4, "a photo of an adult": 0.3, "a photo of an elderly person": 0.0}
        self.assertGreaterEqual(geolocate.minor_share(at_limit), geolocate.MINOR_LIMIT)
        data, calls = self.run_job(verdict=at_limit)
        self.assertEqual((data["status"], calls["search"]), ("blocked", 0))
        below = {"a photo of a baby": 0.05, "a photo of a young child": 0.05, "a photo of a teenager": 0.1,
                 "a photo of a young adult": 0.3, "a photo of an adult": 0.4, "a photo of an elderly person": 0.1}
        self.assertLess(geolocate.minor_share(below), geolocate.MINOR_LIMIT)
        data, calls = self.run_job(verdict=below)
        self.assertEqual((data["status"], calls["search"]), ("ok", 1))

    def test_if_the_age_check_cannot_run_face_search_does_not_start(self):
        data, calls = self.run_job(verdict={}, agecheck_code=1)
        self.assertEqual(data["status"], "blocked")
        self.assertEqual(calls["search"], 0)
        self.assertIn("age check couldn't run", data["log"])

    def test_no_purpose_no_search(self):
        for purpose in ("", "   ", None):
            data, calls = self.run_job(purpose=purpose, verdict={})
            self.assertEqual(data["status"], "blocked", purpose)
            self.assertEqual(calls["search"], 0)
            self.assertIn("purpose", data["log"])

    def test_no_key_means_missing_not_blocked(self):
        data, calls = self.run_job(key="", verdict={})
        self.assertEqual(data["status"], "missing")
        self.assertEqual(calls["search"], 0)

    def test_every_age_prompt_is_classified(self):
        self.assertEqual({p for p, minor in geolocate.AGE_PROMPTS.items() if minor},
                         {"a photo of a baby", "a photo of a young child", "a photo of a teenager"})
        self.assertAlmostEqual(geolocate.minor_share({"a photo of a baby": 0.2, "a photo of an adult": 0.8}), 0.2)

    def test_face_search_is_only_run_when_chosen(self):
        with patch.object(geolocate, "engine_status", return_value={n: (True, "Ready") for n in geolocate.ENGINES}):
            names = [name for name, _, _ in geolocate.jobs("photo.jpg", {})]
        self.assertNotIn("Face search", names)
        names = [name for name, _, _ in geolocate.jobs("photo.jpg", {"engines": ["faces"], "purpose": "case 12"})]
        self.assertEqual(names, ["Face search"])


class ClaudeTests(unittest.TestCase):
    def fake_anthropic(self, reply=None, error=None):
        created = {}
        class Client:
            def __init__(self, **kwargs):
                created.update(kwargs)
                self.messages = SimpleNamespace(create=self.create)
            def create(self, **kwargs):
                created["request"] = kwargs
                if error:
                    raise error
                return reply
        return Client, created

    def answer(self):
        text = json.dumps({"clues": ["Tram lines"], "candidates": [{"place": "Skalica", "region": "", "country": "Slovakia", "lat": 48.84, "lon": 17.23, "confidence": 0.7, "reasoning": "Tram"}]})
        return SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="thinking", text=""), SimpleNamespace(type="text", text=text)])

    def test_workspace_id_is_sent_when_one_is_saved(self):
        import anthropic
        Client, created = self.fake_anthropic(reply=self.answer())
        with tempfile.TemporaryDirectory() as temp, patch.object(anthropic, "Anthropic", Client), \
             patch.object(geolocate, "load_key", side_effect=lambda service: "wrkspc_01ABC" if service == "claude_workspace" else ""):
            rows, clues = geolocate.claude_locate(photo_in(temp), "sk-ant-key", "claude-opus-4-8")
        self.assertEqual(created["default_headers"], {"anthropic-workspace-id": "wrkspc_01ABC"})
        self.assertEqual(created["api_key"], "sk-ant-key")
        self.assertEqual(rows[0]["place"], "Skalica, Slovakia")
        self.assertEqual(clues, ["Tram lines"])
        self.assertEqual(created["request"]["model"], "claude-opus-4-8")
        self.assertEqual(created["request"]["thinking"], {"type": "adaptive"})

    def test_no_workspace_header_by_default(self):
        import anthropic
        Client, created = self.fake_anthropic(reply=self.answer())
        with tempfile.TemporaryDirectory() as temp, patch.object(anthropic, "Anthropic", Client), patch.object(geolocate, "load_key", return_value=""):
            geolocate.claude_locate(photo_in(temp), "sk-ant-key", "claude-opus-4-8")
        self.assertIsNone(created["default_headers"])

    def test_the_workspace_error_is_explained(self):
        import anthropic, httpx
        response = httpx.Response(400, request=httpx.Request("POST", "https://api.anthropic.com/v1/messages"))
        error = anthropic.BadRequestError("This API key is not scoped to a workspace, so this request must include the anthropic-workspace-id header.",
                                          response=response, body=None)
        Client, _ = self.fake_anthropic(error=error)
        with tempfile.TemporaryDirectory() as temp, patch.object(anthropic, "Anthropic", Client), patch.object(geolocate, "load_key", return_value=""):
            with self.assertRaises(geolocate.EngineError) as caught:
                geolocate.claude_locate(photo_in(temp), "sk-ant-key", "claude-opus-4-8")
        self.assertIn("workspace ID", str(caught.exception))
        self.assertNotIn("anthropic-workspace-id header", str(caught.exception))

    def test_other_bad_requests_keep_their_message(self):
        import anthropic, httpx
        response = httpx.Response(400, request=httpx.Request("POST", "https://api.anthropic.com/v1/messages"))
        Client, _ = self.fake_anthropic(error=anthropic.BadRequestError("Image too large.", response=response, body=None))
        with tempfile.TemporaryDirectory() as temp, patch.object(anthropic, "Anthropic", Client), patch.object(geolocate, "load_key", return_value=""):
            with self.assertRaisesRegex(geolocate.EngineError, "Image too large"):
                geolocate.claude_locate(photo_in(temp), "sk-ant-key", "claude-opus-4-8")

    def test_a_refusal_is_reported(self):
        import anthropic
        Client, _ = self.fake_anthropic(reply=SimpleNamespace(stop_reason="refusal", content=[]))
        with tempfile.TemporaryDirectory() as temp, patch.object(anthropic, "Anthropic", Client), patch.object(geolocate, "load_key", return_value=""):
            with self.assertRaisesRegex(geolocate.EngineError, "declined"):
                geolocate.claude_locate(photo_in(temp), "sk-ant-key", "claude-opus-4-8")


class KeyShapeTests(unittest.TestCase):
    def test_keys_that_cannot_work_are_flagged(self):
        flagged = [("vision", "AQ." + "x" * 50), ("vision", "short"), ("claude", "AIza" + "x" * 35), ("hibp", "not-hex"), ("gemini", "sk-ant-abc")]
        for service, value in flagged:
            with self.subTest(service=service):
                self.assertTrue(geolocate.key_problem(service, value))

    def test_real_looking_keys_pass(self):
        fine = [("vision", "AIza" + "a1_-" * 8 + "xyz"), ("gemini", "AIza" + "x" * 35), ("gemini", "AQ.Ab8" + "x" * 45),
                ("claude", "sk-ant-api03-" + "x" * 40), ("hibp", "0123456789abcdef" * 2), ("facecheck", "anything goes"), ("vision", "")]
        for service, value in fine[:-1]:
            with self.subTest(service=service):
                self.assertEqual(geolocate.key_problem(service, value), "")
        self.assertTrue(geolocate.key_problem("vision", fine[-1][1]))      # an empty value is not a key

    def test_the_message_names_the_problem(self):
        self.assertIn("AIza", geolocate.key_problem("vision", "AQ." + "x" * 50))


class KeyDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        import app
        cls.app = app
        cls.qt = QApplication.instance() or QApplication([])
        cls.qt.setStyleSheet(app.STYLE)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.patch = patch.object(geolocate, "user_dir", return_value=Path(self.temp.name))
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.temp.cleanup()

    def test_claude_dialog_saves_the_key_and_workspace(self):
        dialog = self.app.KeyDialog(None, "claude", "claude-opus-4-8")
        self.assertIsNotNone(dialog.extra)
        dialog.key.setText("sk-ant-api03-" + "x" * 40)
        dialog.extra.setText("  wrkspc_01ABC ")
        dialog.save()
        self.assertTrue(geolocate.load_key("claude").startswith("sk-ant-"))
        self.assertEqual(geolocate.load_key("claude_workspace"), "wrkspc_01ABC")
        again = self.app.KeyDialog(None, "claude", "claude-opus-4-8")
        self.assertEqual(again.extra.text(), "wrkspc_01ABC")
        again.remove()
        self.assertEqual((geolocate.load_key("claude"), geolocate.load_key("claude_workspace")), ("", ""))

    def test_a_workspace_can_be_added_without_retyping_the_key(self):
        geolocate.save_key("claude", "sk-ant-api03-" + "x" * 40)
        dialog = self.app.KeyDialog(None, "claude", "claude-opus-4-8")
        dialog.extra.setText("wrkspc_01XYZ")
        dialog.save()
        self.assertTrue(geolocate.load_key("claude").startswith("sk-ant-"))
        self.assertEqual(geolocate.load_key("claude_workspace"), "wrkspc_01XYZ")

    def test_a_suspicious_key_asks_before_saving(self):
        from PySide6.QtWidgets import QMessageBox
        dialog = self.app.KeyDialog(None, "vision")
        dialog.key.setText("AQ." + "x" * 50)
        with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.No) as asked:
            dialog.save()
        self.assertIn("AIza", asked.call_args[0][2])
        self.assertEqual(geolocate.load_key("vision"), "")
        with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes):
            dialog.save()
        self.assertEqual(geolocate.load_key("vision"), "AQ." + "x" * 50)

    def test_a_good_key_saves_without_a_question(self):
        from PySide6.QtWidgets import QMessageBox
        dialog = self.app.KeyDialog(None, "vision")
        dialog.key.setText("AIza" + "x" * 35)
        with patch.object(QMessageBox, "question") as asked:
            dialog.save()
        asked.assert_not_called()
        self.assertEqual(geolocate.load_key("vision"), "AIza" + "x" * 35)

    def test_hibp_dialog_names_what_uses_it(self):
        dialog = self.app.KeyDialog(None, "hibp")
        self.assertIsNone(dialog.extra)
        self.assertIsNone(dialog.model)


class PhotoPageGuardTests(unittest.TestCase):
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
                        patch.object(self.app, "QSettings", lambda *args: real(ini, real.Format.IniFormat)),
                        patch.object(geolocate, "ENABLED_ENGINES", tuple(geolocate.ENGINES)),      # these tests cover face search too
                        patch.object(geolocate, "engine_status", return_value={n: (True, "Ready") for n in geolocate.ENGINES})]
        for item in self.patches:
            item.start()
        self.window = self.app.Window()
        self.window.refresh_engines(initial=True)

    def tearDown(self):
        self.window.close()
        self.window.deleteLater()
        for item in self.patches:
            item.stop()
        self.temp.cleanup()

    def test_face_search_is_never_ticked_for_you(self):
        self.assertFalse(self.window.engine_rows["faces"].check.isChecked())
        self.assertTrue(self.window.engine_rows["geoclip"].check.isChecked())

    def test_face_search_needs_a_purpose_before_anything_starts(self):
        self.window.set_locate_photo(str(photo_in(self.temp.name)))
        for name, row in self.window.engine_rows.items():
            row.check.setChecked(name == "faces")
        for text in ("", "case", "       "):
            self.window.purpose.setText(text)
            self.window.start_locate()
            self.assertIsNone(self.window.locate_worker, repr(text))
            self.assertIn("purpose", self.window.locate_state.text())

    def test_declining_the_face_consent_starts_nothing(self):
        from PySide6.QtWidgets import QMessageBox
        self.window.set_locate_photo(str(photo_in(self.temp.name)))
        for name, row in self.window.engine_rows.items():
            row.check.setChecked(name == "faces")
        self.window.purpose.setText("Verifying a source for case 12")
        with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.No):
            self.window.start_locate()
        self.assertIsNone(self.window.locate_worker)
        self.assertFalse(self.window.settings.value("consent/faces", False, type=bool))


if __name__ == "__main__":
    unittest.main()
