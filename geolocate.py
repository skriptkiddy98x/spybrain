"""Photo intelligence: where a photo was taken, where it appears online, and face search.

GeoCLIP and the age check run on this computer in worker processes. Gemini, Claude, Google Cloud
Vision and FaceCheck.ID are optional online engines that use the user's own API key; the photo is
re-encoded without EXIF before it leaves the machine. Face search refuses photos that appear to
show children or teenagers and requires a stated purpose.
"""
from __future__ import annotations
import base64, gzip, html, importlib.metadata, importlib.util, io, json, math, os, re, sys, time, urllib.error, urllib.request
from pathlib import Path
from urllib.parse import urlsplit
import osinthub as hub

# group: which results tab the engine feeds; service: whose API key it needs (None = no key).
ENGINES = {
    "geoclip": {"title": "GeoCLIP", "group": "LOCATION", "where": "THIS COMPUTER", "service": None,
                "about": "Open model (MIT) that compares the photo with 100,000 places worldwide. Works offline after a one-time 1.7 GB download."},
    "gemini": {"title": "Gemini", "group": "LOCATION", "where": "GOOGLE AI", "service": "gemini",
               "about": "Google's vision model; the strongest in public geolocation benchmarks. Lists the clues it used."},
    "claude": {"title": "Claude", "group": "LOCATION", "where": "ANTHROPIC", "service": "claude",
               "about": "Anthropic's vision model with step-by-step reasoning. Lists the clues it used."},
    "landmarks": {"title": "Google Vision", "group": "LOCATION", "where": "GOOGLE CLOUD", "service": "vision",
                  "about": "Recognises well-known landmarks and returns their exact coordinates."},
    "web": {"title": "Web matches", "group": "WEB", "where": "GOOGLE CLOUD", "service": "vision",
            "about": "Finds pages where this photo, or a cropped or edited copy, appears online, plus visually similar images."},
    "faces": {"title": "Face search", "group": "FACES", "where": "FACECHECK.ID", "service": "facecheck",
              "about": "Finds pages showing the same face. Blocked for photos of children or teenagers; needs a stated purpose."},
}
for _meta in ENGINES.values():
    _meta["online"] = _meta["service"] is not None
# The engines the Photo page offers in this version. The others are built and tested but switched off:
# add a name here ("gemini", "claude", "landmarks", "web", "faces") to bring one back.
ENABLED_ENGINES = ("geoclip",)
SERVICES = {
    "gemini": {"title": "Gemini", "key_url": "https://aistudio.google.com/apikey",
               "privacy": "The photo is sent to Google without EXIF metadata. Free-tier keys let Google use requests to improve its products."},
    "claude": {"title": "Claude", "key_url": "https://console.anthropic.com/settings/keys",
               "privacy": "The photo is sent to Anthropic without EXIF metadata. Each request is billed to your Anthropic account.",
               "extra": {"name": "claude_workspace", "label": "WORKSPACE ID (OPTIONAL)", "placeholder": "wrkspc_… only if Anthropic asks for it",
                         "hint": "Some Anthropic keys aren't tied to a workspace, and then every request must name one. "
                                 "Copy its ID from the Anthropic Console under Settings > Workspaces, or create the key inside a workspace instead."}},
    "vision": {"title": "Google Cloud Vision", "key_url": "https://console.cloud.google.com/apis/credentials",
               "privacy": "Used by Google Vision landmarks and Web matches. Enable the Cloud Vision API in your Google Cloud project and restrict the key to it. "
                          "The first 1,000 requests per feature each month are free."},
    "facecheck": {"title": "FaceCheck.ID", "key_url": "https://facecheck.id/en/Face-Search/API",
                  "privacy": "The photo is uploaded to FaceCheck.ID and deleted from its queue after the search. A search costs credits unless test mode is on."},
    "hibp": {"title": "Have I Been Pwned", "key_url": "https://haveibeenpwned.com/API/Key", "used_by": "Leaks (email breach search)",
             "privacy": "Optional. Adds Have I Been Pwned's own breach list to the email leak check. Only the email address is sent, over HTTPS. "
                        "A key costs a few dollars a month from HIBP; the free XposedOrNot source works without it."},
}
DEFAULT_MODELS = {"gemini": "gemini-flash-latest", "claude": "claude-opus-4-8"}
# What a real key looks like, so a credential pasted into the wrong slot is caught before it fails.
KEY_RULES = {
    "gemini": (r"AIza[\w-]{35}|AQ\.[\w.\-]{20,}", "Gemini keys come from Google AI Studio and start with AIza or AQ."),
    "vision": (r"AIza[\w-]{35}", "Google Cloud Vision needs a standard Cloud API key: 39 characters starting with AIza, created under APIs & Services > Credentials. "
                                 "Keys that start with AQ. are for Gemini and Vertex AI, and Vision rejects them."),
    "claude": (r"sk-ant-[\w-]{20,}", "Anthropic API keys start with sk-ant-."),
    "hibp": (r"[0-9a-fA-F]{32}", "Have I Been Pwned keys are 32 hexadecimal characters."),
}
CLIP_ID = "openai/clip-vit-large-patch14"
CLIP_REPO = "models--openai--clip-vit-large-patch14"
CLIP_BYTES = 1_710_000_000
# Zero-shot age prompts for the face-search guard; True marks a minor.
AGE_PROMPTS = {"a photo of a baby": True, "a photo of a young child": True, "a photo of a teenager": True,
               "a photo of a young adult": False, "a photo of an adult": False, "a photo of an elderly person": False}
MINOR_LIMIT = 0.30
PROMPT = """You are an OSINT geolocation analyst. Estimate where this photo was taken using only visible evidence: terrain, vegetation, architecture, road markings, signs and their language or script, vehicles and number plates, utility poles, sun angle and climate. Do not try to identify any person.
Reply with JSON only, in exactly this shape:
{"clues": ["short clue", "..."], "candidates": [{"place": "nearest town or landmark", "region": "state or region", "country": "country", "lat": 0.0, "lon": 0.0, "confidence": 0.0, "reasoning": "one sentence"}]}
Give 3 to 5 candidates, most likely first. confidence is a probability from 0 to 1. If the photo shows few clues, still give your best guesses with low confidence."""
CANDIDATE = {"type": "object", "additionalProperties": False, "required": ["place", "region", "country", "lat", "lon", "confidence", "reasoning"],
             "properties": {"place": {"type": "string"}, "region": {"type": "string"}, "country": {"type": "string"}, "lat": {"type": "number"},
                            "lon": {"type": "number"}, "confidence": {"type": "number"}, "reasoning": {"type": "string"}}}
SCHEMA = {"type": "object", "additionalProperties": False, "required": ["clues", "candidates"],
          "properties": {"clues": {"type": "array", "items": {"type": "string"}}, "candidates": {"type": "array", "items": CANDIDATE}}}

class EngineError(Exception):
    """A message that can be shown to the user as-is."""

# ---- Keys, stored with Windows DPAPI so only this Windows account can read them.

def user_dir():
    """Shared by the EXE and the source checkout, so keys and the model are set up once."""
    return hub.APP_DIR

def _keys_file():
    return user_dir() / "keys.dat"

def _dpapi(data: bytes, protect: bool) -> bytes:
    import ctypes
    from ctypes import wintypes
    class Blob(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]
    buffer = ctypes.create_string_buffer(data, len(data))
    source, result = Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char))), Blob()
    call = ctypes.windll.crypt32.CryptProtectData if protect else ctypes.windll.crypt32.CryptUnprotectData
    if not call(ctypes.byref(source), None, None, None, None, 0x1, ctypes.byref(result)):  # CRYPTPROTECT_UI_FORBIDDEN
        raise OSError("Windows couldn't protect or read the stored key.")
    try:
        return ctypes.string_at(result.pbData, result.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(ctypes.cast(result.pbData, ctypes.c_void_p))

def _read_keys():
    try:
        return json.loads(_keys_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}

def load_key(service):
    stored = _read_keys().get(service)
    if not stored:
        return ""
    try:
        return _dpapi(base64.b64decode(stored), False).decode("utf-8")
    except (OSError, ValueError):
        return ""

def save_key(service, value):
    keys = _read_keys()
    if value:
        keys[service] = base64.b64encode(_dpapi(value.strip().encode("utf-8"), True)).decode("ascii")
    else:
        keys.pop(service, None)
    _keys_file().parent.mkdir(parents=True, exist_ok=True)
    _keys_file().write_text(json.dumps(keys), encoding="utf-8")

def key_problem(service, value):
    """Why a pasted key can't be right for the service, or an empty string when it looks fine."""
    rule = KEY_RULES.get(service)
    return "" if not rule or re.fullmatch(rule[0], (value or "").strip()) else rule[1]

# ---- Local models (GeoCLIP and the CLIP age check share the CLIP backbone).

def model_dir():
    return user_dir() / "models" / "huggingface"

def geoclip_installed():
    try:
        return importlib.util.find_spec("geoclip") is not None and importlib.util.find_spec("torch") is not None
    except (ImportError, ValueError):
        return False

def geoclip_downloaded():
    snapshots = model_dir() / "hub" / CLIP_REPO / "snapshots"
    return any(snapshots.glob("*/model.safetensors")) or any(snapshots.glob("*/pytorch_model.bin"))

def places_cache():
    """Where GeoCLIP's precomputed place features are kept (see gallery_features)."""
    try:
        version = importlib.metadata.version("geoclip")
    except importlib.metadata.PackageNotFoundError:
        version = "0"
    return user_dir() / "models" / f"geoclip-places-{version}.pt"

def geoclip_download_progress():
    """Bytes of the CLIP backbone fetched so far, for the progress line during the first run."""
    blobs = model_dir() / "hub" / CLIP_REPO / "blobs"
    try:
        return max((p.stat().st_size for p in blobs.iterdir()), default=0)
    except OSError:
        return 0

def engine_status():
    """Which engines can run right now, and why not."""
    status = {}
    local = geoclip_installed()
    for name, meta in ENGINES.items():
        if meta["service"] is None:
            status[name] = (local, ("Ready" if geoclip_downloaded() and places_cache().exists() else "First run is slow") if local else "Not installed")
        elif not load_key(meta["service"]):
            status[name] = (False, "Needs a key")
        elif name == "faces" and not local:
            status[name] = (False, "Age check not installed")
        else:
            status[name] = (True, "Key saved")
    return status

def _torch_worker_setup():
    os.environ.setdefault("HF_HOME", str(model_dir()))
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
    # GeoCLIP compiles a helper with TorchScript at import, which needs .py sources the EXE
    # doesn't ship; with TorchScript off the same function runs as plain Python.
    os.environ["PYTORCH_JIT"] = "0"

def gallery_features(model, cache, chunk=2048):
    """Normalised features of GeoCLIP's 100,000 candidate places.

    They never change, but GeoCLIP's own predict() recomputes them for every photo in one huge batch.
    That is the slow, memory-hungry part: with little free RAM Windows starts swapping and a photo can
    take minutes. So they are computed once, in small batches, and kept in `cache`."""
    import torch
    import torch.nn.functional as F
    gallery = model.gps_gallery
    try:
        saved = torch.load(cache, map_location="cpu", weights_only=True)
        if saved.shape == (gallery.shape[0], saved.shape[1]):
            return saved
    except Exception:
        pass
    with torch.no_grad():
        features = torch.cat([F.normalize(model.location_encoder(gallery[i:i+chunk]), dim=1) for i in range(0, len(gallery), chunk)])
    try:
        Path(cache).parent.mkdir(parents=True, exist_ok=True)
        partial = Path(str(cache) + ".tmp")
        torch.save(features, partial)
        os.replace(partial, cache)
    except OSError:
        pass
    return features

def geoclip_main():
    """Worker entry point: geoclip <photo> <output.json> [top_k]."""
    photo, output = sys.argv[1], sys.argv[2]
    top = int(sys.argv[3]) if len(sys.argv) > 3 else 5
    _torch_worker_setup()
    print("Loading GeoCLIP. The first run downloads the 1.7 GB CLIP model.", flush=True)
    import torch
    import torch.nn.functional as F
    from PIL import Image
    from geoclip import GeoCLIP
    model = GeoCLIP()
    model.eval()
    cache = places_cache()
    print("Loading the candidate places." if cache.exists() else "Preparing the 100,000 candidate places. This happens once.", flush=True)
    with torch.no_grad():
        places = gallery_features(model, cache)
        with Image.open(photo) as image:
            tensor = model.image_encoder.preprocess_image(image.convert("RGB"))
        features = F.normalize(model.image_encoder(tensor), dim=1)
        probabilities = (model.logit_scale.exp() * (features @ places.t())).softmax(dim=-1)
        best = torch.topk(probabilities, top, dim=1)
        gps = model.gps_gallery.index_select(0, best.indices[0]).cpu()
        probability = best.values[0].cpu()
    rows = [{"lat": float(lat), "lon": float(lon), "confidence": float(p)} for (lat, lon), p in zip(gps.tolist(), probability.tolist())]
    Path(output).write_text(json.dumps(rows), encoding="utf-8")
    print(f"GeoCLIP returned {len(rows)} predictions.", flush=True)

def agecheck_main():
    """Worker entry point: agecheck <photo> <output.json>. Zero-shot CLIP age estimate."""
    photo, output = sys.argv[1], sys.argv[2]
    _torch_worker_setup()
    print("Checking the photo for children before a face search.", flush=True)
    import torch
    from PIL import Image
    from transformers import CLIPModel, CLIPProcessor
    model, processor = CLIPModel.from_pretrained(CLIP_ID), CLIPProcessor.from_pretrained(CLIP_ID)
    model.eval()
    with Image.open(photo) as image:
        inputs = processor(text=list(AGE_PROMPTS), images=image.convert("RGB"), return_tensors="pt", padding=True)
    with torch.no_grad():
        probabilities = model(**inputs).logits_per_image.softmax(dim=1)[0].tolist()
    Path(output).write_text(json.dumps(dict(zip(AGE_PROMPTS, probabilities))), encoding="utf-8")

def minor_share(scores):
    return sum(p for prompt, p in scores.items() if AGE_PROMPTS.get(prompt))

# ---- Places, offline: nearest GeoNames town for coordinates.

_PLACES = None

def _places():
    global _PLACES
    if _PLACES is None:
        import numpy as np
        folder = hub.ASSETS / "assets" / "geo"
        names, codes, lats, lons = [], [], [], []
        with gzip.open(folder / "places.tsv.gz", "rt", encoding="utf-8") as handle:
            for line in handle:
                name, code, lat, lon, _ = line.rstrip("\n").split("\t")
                names.append(name); codes.append(code); lats.append(float(lat)); lons.append(float(lon))
        countries = json.loads((folder / "countries.json").read_text(encoding="utf-8"))
        _PLACES = (names, codes, np.radians(np.array(lats)), np.radians(np.array(lons)), countries)
    return _PLACES

def nearest_place(lat, lon):
    """Nearest town with 5,000+ people: (town, country, distance in km)."""
    import numpy as np
    names, codes, lats, lons, countries = _places()
    la, lo = math.radians(lat), math.radians(lon)
    h = np.sin((lats - la) / 2) ** 2 + math.cos(la) * np.cos(lats) * np.sin((lons - lo) / 2) ** 2
    index = int(np.argmin(h))
    distance = 2 * 6371 * math.asin(min(1.0, math.sqrt(float(h[index]))))
    return names[index], countries.get(codes[index], codes[index]), distance

def map_url(lat, lon, zoom=11):
    return f"https://www.openstreetmap.org/?mlat={lat:.6f}&mlon={lon:.6f}#map={zoom}/{lat:.6f}/{lon:.6f}"

def distance_km(a, b):
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((la2-la1)/2)**2 + math.cos(la1)*math.cos(la2)*math.sin((lo2-lo1)/2)**2
    return 2*6371*math.asin(min(1.0, math.sqrt(h)))

# ---- Shared helpers.

def clean_photo(path, work, max_side=1600):
    """Re-encode as JPEG without EXIF (no GPS, camera or owner data), upright and at most max_side px."""
    from PIL import Image, ImageOps, UnidentifiedImageError
    try:
        with Image.open(path) as image:
            image = ImageOps.exif_transpose(image).convert("RGB")
            image.thumbnail((max_side, max_side))
            output = Path(work) / f"photo-clean-{max_side}.jpg"
            image.save(output, "JPEG", quality=90)
    except (UnidentifiedImageError, OSError):
        raise EngineError("Unsupported or damaged photo. Use JPEG, PNG, TIFF, WebP or BMP.") from None
    return output

def _lenient_json(text):
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < start:
        raise EngineError("The model didn't return any coordinates.")
    try:
        return json.loads(text[start:end+1])
    except ValueError:
        raise EngineError("The model's answer couldn't be read.") from None

def _candidates(data):
    rows = []
    for item in (data.get("candidates") or [])[:5]:
        try:
            lat, lon = float(item["lat"]), float(item["lon"])
        except (KeyError, TypeError, ValueError):
            continue
        if abs(lat) > 90 or abs(lon) > 180:
            continue
        confidence = item.get("confidence", 0)
        try:
            confidence = min(1.0, max(0.0, float(confidence)))
        except (TypeError, ValueError):
            confidence = 0.0
        place = ", ".join(str(item.get(k, "")).strip() for k in ("place", "region", "country") if str(item.get(k, "")).strip())
        rows.append({"lat": round(lat, 6), "lon": round(lon, 6), "confidence": round(confidence, 4), "place": place,
                     "reasoning": str(item.get("reasoning", "")).strip()})
    if not rows:
        raise EngineError("The model didn't return any usable coordinates.")
    clues = [str(c).strip() for c in (data.get("clues") or []) if str(c).strip()][:12]
    return rows, clues

def _b64(path):
    return base64.standard_b64encode(Path(path).read_bytes()).decode("ascii")

def _post_json(url, body, headers, timeout, name):
    """POST JSON with urllib; turn HTTP and network failures into readable EngineErrors."""
    request = urllib.request.Request(url, data=json.dumps(body).encode("utf-8") if body is not None else None,
                                     headers={**headers, "Content-Type": "application/json"}, method="POST" if body is not None else "GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        try:
            message = json.loads(error.read().decode("utf-8")).get("error", {}).get("message", "")
        except ValueError:
            message = ""
        if error.code in (401, 403):
            raise EngineError(f"{name} rejected the API key or the API isn't enabled for it. {message}".strip()) from None
        if error.code == 404:
            raise EngineError(f"That {name} model or endpoint isn't available to this key.") from None
        if error.code == 429:
            raise EngineError(f"{name} quota reached. Wait a minute or check your plan.") from None
        raise EngineError(f"{name} API error {error.code}: {message or error.reason}") from None
    except (urllib.error.URLError, TimeoutError):
        raise EngineError(f"Can't reach the {name} API. Check the internet connection.") from None

# ---- Gemini (REST generateContent).

GEMINI_API = "https://generativelanguage.googleapis.com/v1beta"

def _gemini(path, key, body=None, timeout=60):
    return _post_json(GEMINI_API + path, body, {"x-goog-api-key": key}, timeout, "Gemini")

def gemini_models(key):
    data = _gemini("/models?pageSize=1000", key)
    names = [m["name"].removeprefix("models/") for m in data.get("models", []) if "generateContent" in m.get("supportedGenerationMethods", [])]
    return sorted(n for n in names if n.startswith("gemini") and not any(word in n for word in ("embedding", "tts", "image-generation", "audio")))

def gemini_locate(photo, key, model):
    body = {"contents": [{"role": "user", "parts": [{"inline_data": {"mime_type": "image/jpeg", "data": _b64(photo)}}, {"text": PROMPT}]}],
            "generationConfig": {"responseMimeType": "application/json"}}
    data = _gemini(f"/models/{model}:generateContent", key, body, timeout=240)
    if (data.get("promptFeedback") or {}).get("blockReason"):
        raise EngineError("Gemini declined to analyse this photo.")
    try:
        parts = data["candidates"][0]["content"]["parts"]
    except (KeyError, IndexError, TypeError):
        raise EngineError("Gemini returned no answer for this photo.") from None
    return _candidates(_lenient_json("".join(p.get("text", "") for p in parts if not p.get("thought"))))

# ---- Claude (official Anthropic SDK, structured JSON output).

def _claude_client(key, timeout, retries, workspace=None):
    """Official client; names the workspace when the key isn't tied to one."""
    import anthropic
    workspace = load_key("claude_workspace") if workspace is None else workspace.strip()
    return anthropic.Anthropic(api_key=key, timeout=timeout, max_retries=retries,
                               default_headers={"anthropic-workspace-id": workspace} if workspace else None)

def _claude_message(error):
    """The user-facing text for a rejected Claude request."""
    text = str(getattr(error, "message", "") or error)
    if "workspace" in text.lower():
        return ("Anthropic says this key isn't tied to a workspace. Open Set key and add the workspace ID "
                "(Anthropic Console > Settings > Workspaces), or create the key inside a workspace.")
    return f"Claude rejected the request: {text}"

def claude_models(key, workspace=None):
    import anthropic
    client = _claude_client(key, 30.0, 2, workspace)
    try:
        return sorted((m.id for m in client.models.list()), reverse=True)
    except anthropic.AuthenticationError:
        raise EngineError("Claude rejected the API key. Check it under Set key.") from None
    except anthropic.APIConnectionError:
        raise EngineError("Can't reach the Claude API. Check the internet connection.") from None
    except anthropic.APIStatusError as error:
        if error.status_code == 400:
            raise EngineError(_claude_message(error)) from None
        raise EngineError(f"Claude API error {error.status_code}: {error.message}") from None

def claude_locate(photo, key, model):
    import anthropic
    client = _claude_client(key, 300.0, 2)
    try:
        response = client.messages.create(
            model=model,
            max_tokens=16000,
            thinking={"type": "adaptive"},
            output_config={"format": {"type": "json_schema", "schema": SCHEMA}},
            messages=[{"role": "user", "content": [
                {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": _b64(photo)}},
                {"type": "text", "text": PROMPT}]}],
        )
    except anthropic.AuthenticationError:
        raise EngineError("Claude rejected the API key. Check it under Set key.") from None
    except anthropic.PermissionDeniedError:
        raise EngineError("This Claude API key isn't allowed to use that model.") from None
    except anthropic.NotFoundError:
        raise EngineError(f"Claude model {model} isn't available to this key. Pick another model.") from None
    except anthropic.RateLimitError:
        raise EngineError("Claude rate limit reached. Try again in a minute.") from None
    except anthropic.BadRequestError as error:
        raise EngineError(_claude_message(error)) from None
    except anthropic.APIStatusError as error:
        raise EngineError(f"Claude API error {error.status_code}: {error.message}") from None
    except anthropic.APIConnectionError:
        raise EngineError("Can't reach the Claude API. Check the internet connection.") from None
    if response.stop_reason == "refusal":
        raise EngineError("Claude declined to analyse this photo.")
    text = next((block.text for block in response.content if block.type == "text"), "")
    return _candidates(_lenient_json(text))

# ---- Google Cloud Vision (REST images:annotate): landmarks and web detection.

VISION_API = "https://vision.googleapis.com/v1/images:annotate"

def _vision(photo, key, feature, max_results):
    body = {"requests": [{"image": {"content": _b64(photo)}, "features": [{"type": feature, "maxResults": max_results}]}]}
    try:
        data = _post_json(VISION_API, body, {"x-goog-api-key": key}, 120, "Google Vision")
    except EngineError as error:
        if "not supported by this API" in str(error):
            raise EngineError("Google rejected this key for Cloud Vision. It needs a standard Cloud API key (starts with AIza) from a project "
                              "with the Cloud Vision API enabled and billing on. Keys that start with AQ. only work with Gemini and Vertex AI.") from None
        raise
    response = (data.get("responses") or [{}])[0]
    if response.get("error"):
        raise EngineError("Google Vision: " + response["error"].get("message", "request failed"))
    return response

def vision_landmarks(photo, key, model=None):
    response = _vision(photo, key, "LANDMARK_DETECTION", 5)
    rows = []
    for item in response.get("landmarkAnnotations", []):
        for spot in item.get("locations", [])[:1]:
            point = spot.get("latLng") or {}
            if "latitude" in point and "longitude" in point:
                rows.append({"lat": round(point["latitude"], 6), "lon": round(point["longitude"], 6), "confidence": round(float(item.get("score", 0)), 4),
                             "place": item.get("description", ""), "reasoning": "Recognised landmark"})
    if not rows:
        raise EngineError("No well-known landmark recognised in this photo.")
    return rows, []

def _plain(text):
    return html.unescape(re.sub(r"<[^>]+>", "", text or "")).strip()

def vision_web(photo, key):
    """Pages and images matching the photo, plus Google's best guess of what it shows."""
    web = _vision(photo, key, "WEB_DETECTION", 50).get("webDetection", {})
    matches, seen = [], set()
    def add(kind, url, title=""):
        if url and url not in seen and hub.safe_url(url):
            seen.add(url)
            matches.append({"kind": kind, "url": url, "title": _plain(title) or urlsplit(url).netloc})
    for page in web.get("pagesWithMatchingImages", []):
        kind = "Page · full match" if page.get("fullMatchingImages") else "Page · partial match"
        add(kind, page.get("url"), page.get("pageTitle", ""))
    for kind, key_name in (("Full image match", "fullMatchingImages"), ("Partial image match", "partialMatchingImages"), ("Similar image", "visuallySimilarImages")):
        for image in web.get(key_name, []):
            add(kind, image.get("url"))
    labels = [l["label"] for l in web.get("bestGuessLabels", []) if l.get("label")]
    entities = [f"{e['description']} ({e.get('score', 0):.2f})" for e in web.get("webEntities", []) if e.get("description")][:12]
    return matches, labels, entities

# ---- FaceCheck.ID face search.

FACECHECK = "https://facecheck.id"

def _thumbnail(data):
    """FaceCheck thumbnails come as base64 (often WebP); store a small JPEG instead."""
    from PIL import Image
    try:
        raw = base64.b64decode(data.split(",", 1)[-1])
        with Image.open(io.BytesIO(raw)) as image:
            image = image.convert("RGB")
            image.thumbnail((120, 120))
            buffer = io.BytesIO()
            image.save(buffer, "JPEG", quality=82)
        return base64.b64encode(buffer.getvalue()).decode("ascii")
    except Exception:
        return ""

def facecheck_search(photo, key, demo, check=lambda: None, poll=2.0, limit=600):
    import requests
    headers = {"accept": "application/json", "Authorization": key}
    def call(path, **kwargs):
        try:
            body = requests.post(FACECHECK + path, headers=headers, timeout=60, **kwargs).json()
        except (requests.RequestException, ValueError):
            raise EngineError("Can't reach FaceCheck.ID. Check the internet connection.") from None
        if body.get("error"):
            raise EngineError(f"FaceCheck.ID: {body['error']} ({body.get('code', '')})")
        return body
    with open(photo, "rb") as handle:
        uploaded = call("/api/upload_pic", files={"images": handle, "id_search": None})
    id_search = uploaded["id_search"]
    try:
        payload = {"id_search": id_search, "with_progress": True, "status_only": False, "demo": bool(demo)}
        deadline = time.monotonic() + limit
        while True:
            check()
            body = call("/api/search", json=payload)
            if body.get("output"):
                items = body["output"].get("items") or []
                break
            if time.monotonic() > deadline:
                raise EngineError("FaceCheck.ID didn't finish within 10 minutes.")
            time.sleep(poll)
    finally:
        for picture in uploaded.get("input") or []:
            try:
                requests.post(FACECHECK + "/api/delete_pic", headers=headers, timeout=30,
                              params={"id_search": id_search, "id_pic": picture.get("id_pic", "")})
            except Exception:
                pass
    faces = []
    for item in items[:60]:
        url = item.get("url") or ""
        if hub.safe_url(url):
            faces.append({"score": int(item.get("score", 0)), "url": url, "site": urlsplit(url).netloc.removeprefix("www."),
                          "thumb": _thumbnail(item.get("base64") or "")})
    return faces

# ---- Scan jobs (same shape as the other adapters in osinthub).

def _located(tool, rows, clues=(), log=""):
    for row in rows:
        if not row.get("place"):
            town, country, km = nearest_place(row["lat"], row["lon"])
            row["place"] = f"near {town}, {country}" if km > 3 else f"{town}, {country}"
        row["map"] = map_url(row["lat"], row["lon"])
    return hub.result(tool, 0, log, locations=rows, clues=list(clues))

def m_geoclip(target, work, fast):
    photo = clean_photo(target, work, 1024)
    output = Path(work) / "geoclip.json"
    # The first run downloads the model and prepares the place features, and can take a long time.
    code, log = hub.run(["geoclip", photo, output, "5"], timeout=300 if geoclip_downloaded() and places_cache().exists() else 3600, cwd=work, worker=True)
    if code != 0 or not output.exists():
        return hub.result("GeoCLIP", code or 1, log)
    return _located("GeoCLIP", json.loads(output.read_text(encoding="utf-8")), log=log)

def _missing(tool):
    return {"tool": tool, "ok": False, "status": "missing", "log": f"Add the API key for {tool} on the Photo page (Set key)."}

def _online(tool, service, locate, model):
    def job(target, work, fast):
        key = load_key(service)
        if not key:
            return _missing(tool)
        context = hub.CONTEXT.get() or hub.ScanContext()
        context.check()
        try:
            rows, clues = locate(clean_photo(target, work), key, model)
        except EngineError as error:
            return hub.result(tool, 1, str(error))
        context.check()
        return _located(tool, rows, clues, log=f"Model: {model}" if model else "")
    return job

def m_web(target, work, fast):
    key = load_key("vision")
    if not key:
        return _missing("Web matches")
    try:
        matches, labels, entities = vision_web(clean_photo(target, work), key)
    except EngineError as error:
        return hub.result("Web matches", 1, str(error))
    return hub.result("Web matches", 0, f"{len(matches)} matches", matches=matches, labels=labels, entities=entities)

def _face_job(purpose, demo):
    def job(target, work, fast):
        tool = "Face search"
        key = load_key("facecheck")
        if not key:
            return _missing(tool)
        if not (purpose or "").strip():
            return {"tool": tool, "ok": False, "status": "blocked", "log": "Face search needs a stated purpose."}
        context = hub.CONTEXT.get() or hub.ScanContext()
        photo = clean_photo(target, work, 1024)
        verdict = Path(work) / "agecheck.json"
        code, log = hub.run(["agecheck", photo, verdict], timeout=300 if geoclip_downloaded() else 3600, cwd=work, worker=True)
        if code != 0 or not verdict.exists():
            return {"tool": tool, "ok": False, "status": "blocked", "log": "The age check couldn't run, so face search was not started.\n" + log[-1500:]}
        minors = minor_share(json.loads(verdict.read_text(encoding="utf-8")))
        if minors >= MINOR_LIMIT:
            return {"tool": tool, "ok": False, "status": "blocked",
                    "log": f"Blocked: the photo appears to show a child or teenager (estimate {minors:.0%}). Face search is never run on minors."}
        try:
            faces = facecheck_search(photo, key, demo, context.check)
        except EngineError as error:
            return hub.result(tool, 1, str(error))
        note = "Test mode: only 100,000 faces searched; results aren't meaningful." if demo else ""
        return hub.result(tool, 0, f"Purpose: {purpose}\nMinor estimate: {minors:.0%}\n{note}".strip(), faces=faces, purpose=purpose, demo=bool(demo))
    return job

def jobs(target, options=None):
    options = options or {}
    # Without an explicit choice only enabled engines run, so saved keys never send a photo anywhere on their own.
    # Face search only runs when chosen explicitly.
    chosen = options.get("engines") or [name for name, (ready, _) in engine_status().items() if ready and name in ENABLED_ENGINES and name != "faces"]
    models = {**DEFAULT_MODELS, **(options.get("models") or {})}
    table = {"geoclip": ("GeoCLIP", m_geoclip),
             "gemini": ("Gemini", _online("Gemini", "gemini", gemini_locate, models["gemini"])),
             "claude": ("Claude", _online("Claude", "claude", claude_locate, models["claude"])),
             "landmarks": ("Google Vision", _online("Google Vision", "vision", vision_landmarks, None)),
             "web": ("Web matches", m_web),
             "faces": ("Face search", _face_job(options.get("purpose", ""), options.get("demo", False)))}
    picked = [(table[name][0], table[name][1], target) for name in ENGINES if name in chosen]
    if not picked:
        raise ValueError("Choose at least one engine. GeoCLIP needs no key.")
    return picked
