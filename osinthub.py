"""SpyBrain: scan engine, CLI and isolated tool workers."""
from __future__ import annotations
import argparse, contextvars, csv, datetime as dt, hashlib, html, importlib.util, json, os, re
import subprocess, sys, tempfile, threading, time, uuid
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlsplit

VERSION = "2.2.0"
ROOT = Path(sys.executable if getattr(sys, "frozen", False) else __file__).resolve().parent
ASSETS = Path(getattr(sys, "_MEIPASS", ROOT))
APP_DIR = Path(os.environ.get("LOCALAPPDATA", str(ROOT))) / "SpyBrain"

def _migrate_app_dir():
    """SpyBrain used to be called OSINT Hub; carry its reports, keys and model over once."""
    old = APP_DIR.parent / "OSINT Hub"
    if not old.is_dir():
        return
    try:
        if not APP_DIR.exists():
            old.rename(APP_DIR)
            return
        # Merge item by item, so a half-finished move (files in use) completes on a later start.
        for item in old.iterdir():
            if not (APP_DIR / item.name).exists():
                item.rename(APP_DIR / item.name)
        old.rmdir()
    except OSError:
        pass

if getattr(sys, "frozen", False):
    _migrate_app_dir()
elif not APP_DIR.exists() and (APP_DIR.parent / "OSINT Hub").is_dir():
    # The source checkout keeps using the 2.x folder until the SpyBrain EXE moves it, so the
    # installed OSINT Hub app doesn't lose its history and keys before it is replaced.
    APP_DIR = APP_DIR.parent / "OSINT Hub"
DATA_ROOT = APP_DIR if getattr(sys, "frozen", False) else ROOT
REPORTS = DATA_ROOT / "reports"
PACKAGES = {"sherlock": "sherlock_project", "maigret": "maigret", "theHarvester": "theHarvester"}
KINDS = {"username": "Username", "domain": "Domain", "email": "Email", "phone": "Phone", "image": "Photo metadata", "location": "Photo location"}
STATUS_LABELS = {"ok": "Done", "error": "Source error", "missing": "Not installed", "timeout": "Timed out", "cancelled": "Stopped", "partial": "Partial", "complete": "Complete", "failed": "Failed", "blocked": "Blocked"}


def owl_data_uri():
    """The SpyBrain owl logo as a data URI for HTML reports; empty if missing."""
    global _OWL_URI
    if _OWL_URI is None:
        import base64
        path = ASSETS / "assets" / "owl-small.png"
        _OWL_URI = "data:image/png;base64," + base64.b64encode(path.read_bytes()).decode("ascii") if path.is_file() else ""
    return _OWL_URI

_OWL_URI = None
CONTEXT = contextvars.ContextVar("scan_context", default=None)
MAIL_PROVIDERS = {"gmail.com", "googlemail.com", "outlook.com", "hotmail.com", "live.com", "yahoo.com", "azet.sk", "centrum.sk", "seznam.cz", "icloud.com", "proton.me", "protonmail.com", "zoznam.sk"}

class Cancelled(Exception):
    pass

class ScanContext:
    def __init__(self, callback=None, cancel=None):
        self.callback = callback or (lambda event: None)
        self.cancel = cancel or threading.Event()
    def check(self):
        if self.cancel.is_set():
            raise Cancelled("Scan stopped.")
    def emit(self, **event):
        self.callback(event)

def phoneinfoga_path():
    for base in (ROOT, ASSETS):
        path = base / "bin" / ("phoneinfoga.exe" if os.name == "nt" else "phoneinfoga")
        if path.is_file():
            return path
    return None

def tool_status():
    status = {}
    for tool, package in PACKAGES.items():
        try:
            status[tool] = importlib.util.find_spec(package) is not None
        except (ImportError, ValueError):
            status[tool] = False
    status.update({"PhoneInfoga": phoneinfoga_path() is not None, "DNS": True, "EXIF": True, "libphonenumber": True})
    # Online location engines are always present; whether a key is saved is checked when they run.
    import geolocate
    local = geolocate.geoclip_installed()
    status.update({"GeoCLIP": local, "Gemini": True, "Claude": True, "Google Vision": True, "Web matches": True, "Face search": local})
    # Leak checks use free sources (plus HIBP if a key is saved); always available.
    status["Leaks"] = True
    return status

def stop_process(process):
    import psutil
    try:
        parent = psutil.Process(process.pid)
        for child in reversed(parent.children(recursive=True)):
            try:
                child.kill()
            except psutil.NoSuchProcess:
                pass
        parent.kill()
    except psutil.NoSuchProcess:
        pass
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()

def read_tail(path, limit=24000):
    with path.open("rb") as handle:
        handle.seek(max(0, path.stat().st_size - limit))
        return handle.read().decode("utf-8", errors="replace")

def run(cmd, timeout=240, cwd=None, worker=False):
    ctx = CONTEXT.get() or ScanContext()
    ctx.check()
    with tempfile.TemporaryDirectory(prefix="spybrain_log_") as temp:
        logpath = Path(temp) / "output.log"
        command = [str(c) for c in cmd]
        if worker:
            prefix = [sys.executable] if getattr(sys, "frozen", False) else [sys.executable, str(Path(__file__).resolve())]
            command = prefix + ["--worker-log", str(logpath), "--worker"] + command
        with logpath.open("ab") as output:
            try:
                process = subprocess.Popen(command, stdout=output, stderr=output, cwd=cwd,
                    env={**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"},
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
            except OSError as error:
                return -2, str(error)
            deadline = time.monotonic() + timeout
            while process.poll() is None:
                if ctx.cancel.wait(0.15):
                    stop_process(process)
                    raise Cancelled("Scan stopped.")
                if time.monotonic() >= deadline:
                    stop_process(process)
                    return -1, read_tail(logpath) + "\nSource time limit exceeded."
        ctx.check()
        return process.returncode, read_tail(logpath)

def worker_main():
    if "--worker" not in sys.argv:
        return False
    pos = sys.argv.index("--worker")
    tool, args = sys.argv[pos + 1], sys.argv[pos + 2:]
    logpath = sys.argv[sys.argv.index("--worker-log") + 1]
    with open(logpath, "a", encoding="utf-8", buffering=1) as log:
        sys.stdout = sys.stderr = log
        sys.argv = [tool] + args
        try:
            if tool == "sherlock":
                from sherlock_project.sherlock import main
            elif tool == "maigret":
                from maigret.maigret import run as main
            elif tool == "theHarvester":
                from theHarvester.theHarvester import main
            elif tool == "geoclip":
                from geolocate import geoclip_main as main
            elif tool == "agecheck":
                from geolocate import agecheck_main as main
            else:
                raise ValueError("Unknown tool")
            main()
        except SystemExit:
            raise
        except Exception:
            import traceback
            traceback.print_exc()
            raise SystemExit(1)
    return True

def validate_domain(value):
    try:
        domain = value.rstrip(".").encode("idna").decode("ascii").lower()
    except UnicodeError:
        raise ValueError("Invalid domain format.") from None
    labels = domain.split(".")
    if len(domain) > 253 or len(labels) < 2 or not all(re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label) for label in labels) or labels[-1].isdigit():
        raise ValueError("Enter a domain without https:// or a path, for example example.org.")
    return domain

def detect(target):
    value = target.strip().strip('"')
    if Path(value).is_file():
        return "image"
    if re.search(r"[\\/]|\.(jpe?g|png|heic|tiff?|webp|bmp)$", value, re.I):
        raise ValueError(f"File not found: {value}")
    if "@" in value and not value.startswith("@"):
        return "email"
    if re.fullmatch(r"\+?[\d\s\-()]{7,}", value):
        return "phone"
    if "." in value:
        try:
            validate_domain(value)
            return "domain"
        except ValueError:
            pass
    return "username"

def validate(target, kind=None):
    target = target.strip().strip('"')
    if not target or len(target) > 1024 or any(ord(c) < 32 for c in target):
        raise ValueError("Enter a valid scan target.")
    kind = kind or detect(target)
    if kind not in KINDS:
        raise ValueError("Unknown target type.")
    if kind in ("image", "location"):
        if not Path(target).is_file():
            raise ValueError("Photo not found. Choose an existing file.")
        target = str(Path(target).resolve())
    elif kind == "domain":
        target = validate_domain(target)
    elif kind == "email":
        if not re.fullmatch(r"[^@\s]+@[^@\s]+", target):
            raise ValueError("Enter a valid email address.")
        local, domain = target.rsplit("@", 1)
        if len(local) > 64:
            raise ValueError("The email address is too long.")
        target = local + "@" + validate_domain(domain)
    elif kind == "phone":
        import phonenumbers
        try:
            number = phonenumbers.parse(target, None if target.startswith("+") else "SK")
        except phonenumbers.NumberParseException:
            raise ValueError("Number not recognized. Use the international format, for example +421…") from None
        if not phonenumbers.is_possible_number(number):
            raise ValueError("The phone number has an invalid length or prefix.")
        target = phonenumbers.format_number(number, phonenumbers.PhoneNumberFormat.E164)
    else:
        target = target.removeprefix("@")
        if not re.fullmatch(r"[\w.\-]{1,80}", target) or target.startswith("-"):
            raise ValueError("Usernames can contain letters, digits, dots, hyphens and underscores (up to 80 characters).")
    return target, kind

def result(tool, code=0, log="", **data):
    return {"tool": tool, "ok": code == 0, "status": "ok" if code == 0 else ("timeout" if code == -1 else "error"), "log": log[-6000:], **data}

def m_sherlock(target, work, fast):
    out = work / "sherlock"
    out.mkdir()
    cmd = ["sherlock", target, "--csv", "--folderoutput", out, "--print-found", "--no-color", "--local", "--timeout", "8" if fast else "12"]
    if fast:
        for site in ("GitHub", "Reddit", "Instagram", "Pinterest", "Steam Community (User)", "Twitch", "YouTube", "GitLab", "Medium", "Patreon", "SoundCloud", "DeviantArt"):
            cmd += ["--site", site]
    code, log = run(cmd, timeout=120 if fast else 420, cwd=out, worker=True)
    rows = []
    for file in out.glob("*.csv"):
        with file.open(encoding="utf-8-sig", errors="replace", newline="") as handle:
            for row in csv.DictReader(handle):
                if str(row.get("exists", "")).lower() == "claimed" and row.get("url_user"):
                    rows.append({"site": row.get("name", ""), "url": row["url_user"]})
    return result("Sherlock", code, log, found=rows)

def m_maigret(target, work, fast):
    out = work / "maigret"
    out.mkdir()
    code, log = run(["maigret", target, "-J", "simple", "--folderoutput", out, "--no-color", "--no-progressbar", "--timeout", "8", "--top-sites", "100" if fast else "500", "--no-recursion", "--no-autoupdate", "--dns-resolver", "threaded", "-n", "20"], timeout=180 if fast else 420, cwd=out, worker=True)
    rows, ids = [], {}
    for file in out.glob("*simple*.json"):
        data = json.loads(file.read_text(encoding="utf-8"))
        for site, info in data.items():
            status = info.get("status") or {}
            if isinstance(status, dict) and str(status.get("status", "")).lower() == "claimed" and info.get("url_user"):
                rows.append({"site": site, "url": info["url_user"], "tags": ", ".join(status.get("tags") or [])})
                for key, val in (status.get("ids") or {}).items():
                    ids.setdefault(key, set()).add(str(val))
    return result("Maigret", code, log, found=rows, ids={k: sorted(v)[:20] for k, v in ids.items()})

def m_harvester(target, work, fast):
    base = work / "harvester"
    sources = "hackertarget,crtsh" if fast else "crtsh,hackertarget,rapiddns,otx,urlscan,certspotter"
    code, log = run(["theHarvester", "-d", target, "-b", sources, "-l", "100" if fast else "300", "-f", base, "-q"], timeout=120 if fast else 300, cwd=work, worker=True)
    data = {}
    if base.with_suffix(".json").exists():
        data = json.loads(base.with_suffix(".json").read_text(encoding="utf-8"))
    def items(key):
        return sorted({str(v) for v in data.get(key) or []})[:500]
    return result("theHarvester", code if data else (code or 1), log, emails=items("emails"), hosts=items("hosts"), ips=items("ips"))

def m_dns(target, work, fast):
    import dns.resolver
    resolver = dns.resolver.Resolver()
    resolver.timeout, resolver.lifetime = 2, 4
    records, errors = [], []
    for record_type in ("A", "AAAA", "MX", "NS", "TXT", "CAA"):
        (CONTEXT.get() or ScanContext()).check()
        try:
            for item in resolver.resolve(target, record_type):
                records.append({"type": record_type, "value": item.to_text()})
        except dns.resolver.NoAnswer:
            continue
        except dns.resolver.NXDOMAIN:
            return result("DNS", 1, "Domain does not exist.", records=[])
        except Exception as error:
            errors.append(f"{record_type}: {error}")
    data = result("DNS", 0 if records else 1, "\n".join(errors), records=records)
    if records and errors:
        data.update(status="partial", ok=False)
    return data

def m_phone(target, work, fast):
    import phonenumbers
    from phonenumbers import carrier, geocoder, timezone
    number = phonenumbers.parse(target, None)
    names = {v: k for k, v in vars(phonenumbers.PhoneNumberType).items() if isinstance(v, int)}
    info = {"International format": target, "Valid number": phonenumbers.is_valid_number(number), "Region": geocoder.description_for_number(number, "en") or phonenumbers.region_code_for_number(number), "Original carrier": carrier.name_for_number(number, "en") or "Unknown", "Line type": names.get(phonenumbers.number_type(number), "UNKNOWN"), "Time zones": ", ".join(timezone.time_zones_for_number(number))}
    return result("libphonenumber", info=info, note="Numbering-plan data doesn't identify the owner or the current location. The carrier may have changed if the number was ported.")

def m_phoneinfoga(target, work, fast):
    code, log = run([phoneinfoga_path(), "scan", "-n", target], timeout=60 if fast else 120, cwd=work)
    links = sorted(set(re.findall(r"https?://[^\s\x1b<>]+", log)))[:100]
    return result("PhoneInfoga", code, log, links=links)

def m_image(target, work, fast):
    import exifread
    from PIL import Image, UnidentifiedImageError
    try:
        with Image.open(target) as image:
            important = {"File": Path(target).name, "Format": image.format, "Dimensions": f"{image.width} × {image.height} px", "Size": f"{Path(target).stat().st_size:,} B"}
    except (UnidentifiedImageError, OSError):
        raise ValueError("Unsupported or damaged photo. Use JPEG, PNG, TIFF, WebP or BMP.") from None
    digest = hashlib.sha256()
    with open(target, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            (CONTEXT.get() or ScanContext()).check()
            digest.update(block)
        handle.seek(0)
        tags = exifread.process_file(handle, details=False)
    keep = {k: str(v) for k, v in tags.items() if k not in ("JPEGThumbnail", "TIFFThumbnail", "EXIF MakerNote")}
    important["SHA-256"] = digest.hexdigest()
    important.update({k: keep[k] for k in ("Image Make", "Image Model", "EXIF DateTimeOriginal", "Image Software", "EXIF LensModel", "Image Artist") if k in keep})
    return result("EXIF", important=important, gps=exif_gps(tags), all=keep)

def exif_gps(tags):
    """GPS position from exifread tags, or None."""
    if "GPS GPSLatitude" not in tags or "GPS GPSLongitude" not in tags:
        return None
    try:
        def degrees(key, ref):
            d, m, s = [float(value) for value in tags[key].values]
            return (d + m / 60 + s / 3600) * (-1 if str(tags.get(ref, "")) in ("S", "W") else 1)
        lat, lon = degrees("GPS GPSLatitude", "GPS GPSLatitudeRef"), degrees("GPS GPSLongitude", "GPS GPSLongitudeRef")
    except (ValueError, TypeError, ZeroDivisionError):
        return None
    if abs(lat) > 90 or abs(lon) > 180:
        return None
    return {"lat": round(lat, 6), "lon": round(lon, 6), "map": f"https://www.openstreetmap.org/?mlat={lat:.6f}&mlon={lon:.6f}#map=17/{lat:.6f}/{lon:.6f}"}

def photo_gps(path):
    """GPS position stored in a photo's EXIF, or None."""
    import exifread
    try:
        with open(path, "rb") as handle:
            return exif_gps(exifread.process_file(handle, details=False))
    except OSError:
        return None

def jobs_for(target, kind, options=None):
    if kind == "location":
        import geolocate
        return geolocate.jobs(target, options)
    if kind == "username":
        return [("Sherlock", m_sherlock, target), ("Maigret", m_maigret, target)]
    if kind == "domain":
        return [("DNS", m_dns, target), ("theHarvester", m_harvester, target)]
    if kind == "phone":
        return [("libphonenumber", m_phone, target), ("PhoneInfoga", m_phoneinfoga, target)]
    if kind == "image":
        return [("EXIF", m_image, target)]
    local, domain = target.rsplit("@", 1)
    import leaks
    # The leak check uses the whole address; the other sources search the name or the domain.
    jobs = [("Leaks", leaks.m_leaks, target)]
    if re.fullmatch(r"[\w.\-]{1,80}", local) and not local.startswith("-"):
        jobs += [("Sherlock", m_sherlock, local), ("Maigret", m_maigret, local)]
    if domain not in MAIL_PROVIDERS:
        jobs += [("DNS", m_dns, domain), ("theHarvester", m_harvester, domain)]
    return jobs

def flatten(results):
    rows, accounts = [], {}
    for data in results:
        tool = data["tool"]
        for item in data.get("found", []):
            url = item.get("url", "")
            if not url:
                continue
            try:
                parts = urlsplit(url)
                key = (parts.netloc.lower().removeprefix("www."), parts.path.rstrip("/"), parts.query)
            except ValueError:
                key = url
            if key not in accounts:
                row = {"category": "Account", "label": item.get("site", ""), "value": url, "source": tool, "url": url}
                accounts[key] = row
                rows.append(row)
            elif tool not in accounts[key]["source"].split(", "):
                accounts[key]["source"] += ", " + tool
        for key, label in (("emails", "Email"), ("hosts", "Host"), ("ips", "IP address")):
            for value in data.get(key, []):
                rows.append({"category": label, "label": label, "value": str(value), "source": tool, "url": ""})
        for item in data.get("records", []):
            rows.append({"category": "DNS", "label": item["type"], "value": item["value"], "source": tool, "url": ""})
        for key in ("info", "important"):
            for label, value in data.get(key, {}).items():
                rows.append({"category": "Metadata", "label": label, "value": str(value), "source": tool, "url": ""})
        for url in data.get("links", []):
            rows.append({"category": "Link", "label": "Check manually", "value": url, "source": tool, "url": url})
        if data.get("gps"):
            gps = data["gps"]
            # Reports saved before 2.1 stored the map link under "mapa".
            rows.append({"category": "GPS", "label": "Location in metadata", "value": f"{gps['lat']}, {gps['lon']}", "source": tool, "url": gps.get("map") or gps.get("mapa", "")})
        for key, values in data.get("ids", {}).items():
            rows.append({"category": "Identifier", "label": key, "value": ", ".join(values), "source": tool, "url": ""})
        for index, spot in enumerate(data.get("locations", []), 1):
            rows.append({"category": "Location", "label": f"{tool} #{index}", "value": f"{spot.get('place', '')} · {spot['lat']:.5f}, {spot['lon']:.5f} · {spot.get('confidence', 0):.1%}",
                         "source": tool, "url": spot.get("map", "")})
        for clue in data.get("clues", []):
            rows.append({"category": "Clue", "label": tool, "value": str(clue), "source": tool, "url": ""})
        for match in data.get("matches", []):
            rows.append({"category": "Web match", "label": match.get("kind", ""), "value": match.get("title") or match["url"], "source": tool, "url": match["url"]})
        for guess in data.get("labels", []):
            rows.append({"category": "Best guess", "label": tool, "value": str(guess), "source": tool, "url": ""})
        for entity in data.get("entities", []):
            rows.append({"category": "Entity", "label": tool, "value": str(entity), "source": tool, "url": ""})
        for face in data.get("faces", []):
            rows.append({"category": "Face match", "label": f"{face.get('score', 0)} %", "value": face.get("site") or face["url"], "source": tool, "url": face["url"]})
        for breach in data.get("breaches", []):
            risk = breach.get("password_risk")
            parts = [breach.get("domain", ""), breach.get("date", ""), ", ".join(breach.get("data", [])[:6]),
                     f"{breach['records']:,} records" if breach.get("records") else "",
                     f"passwords stored as {risk}" if risk else "", ", ".join(breach.get("flags", []))]
            value = " · ".join(part for part in parts if part) or "Exposed in this breach"
            # The breached site's address is shown as text only: some of these domains are hostile.
            rows.append({"category": "Leak", "label": breach.get("name", ""), "value": value, "source": tool, "url": ""})
    return rows

def safe_url(value):
    try:
        parts = urlsplit(str(value))
        return parts.scheme in ("https", "http") and bool(parts.netloc) and not parts.username
    except ValueError:
        return False

REPORT_CSS = """:root{color-scheme:dark;--ink:#000;--panel:#070a08;--line:#19201b;--rule:#29332c;--bone:#e2ebe4;--ash:#7d8c81;--signal:#00ff41;--warn:#ffa31a;--alert:#ff5c5c}
*{box-sizing:border-box}body{margin:0;background:var(--ink);color:var(--bone);font:15px/1.6 Bahnschrift,'Segoe UI',sans-serif}
main{max-width:1180px;margin:auto;padding:44px 28px 72px}.mono,table,ul,pre,.meta,.eyebrow{font-family:Consolas,'Courier New',monospace}
.eyebrow{font-size:12px;letter-spacing:.24em;color:var(--ash);margin:0}.eyebrow{display:flex;align-items:center;gap:12px}.eyebrow img{width:44px;height:44px;flex:none}
h1{font:600 46px/1.05 'Bahnschrift SemiBold Condensed',Bahnschrift,sans-serif;letter-spacing:.02em;margin:12px 0 8px;overflow-wrap:anywhere}
.meta{font-size:13px;color:var(--ash);margin:0}.notice{border-left:3px solid var(--signal);background:var(--panel);padding:12px 16px;margin:14px 0}
h2{display:flex;align-items:center;gap:14px;font:600 22px 'Bahnschrift SemiBold Condensed',Bahnschrift,sans-serif;letter-spacing:.12em;margin:44px 0 10px}
.tag{display:inline-block;min-width:44px;padding:2px 12px;text-align:center;background:var(--signal);color:#000;clip-path:polygon(14% 0,86% 0,100% 100%,0 100%)}
.scroll{overflow:auto}table{width:100%;border-collapse:collapse;font-size:13px}th{color:var(--ash);font-weight:400;letter-spacing:.16em;text-align:left;padding:10px;border-bottom:1px solid var(--rule)}
td{padding:10px;border-bottom:1px solid var(--line);overflow-wrap:anywhere;vertical-align:top}td:first-child,td:last-child{color:var(--ash)}a{color:var(--signal)}
ul{list-style:none;margin:0;padding:0;font-size:13px}li{padding:10px 0;border-bottom:1px solid var(--line)}.ok{color:var(--bone)}.warn{color:var(--warn)}.bad{color:var(--alert)}
pre{white-space:pre-wrap;overflow-wrap:anywhere;background:var(--panel);padding:14px;font-size:12px;color:var(--ash)}summary{cursor:pointer;color:var(--ash)}
@media print{:root{color-scheme:light}body,pre,.notice{background:#fff;color:#000}.tag{background:none;color:#000;border:1px solid #000}a,.meta,th,.eyebrow,td:first-child,td:last-child{color:#333}main{padding:0}details{display:none}}"""

def render(report):
    esc = lambda value: html.escape(str(value), quote=True)
    rows, body = flatten(report["results"]), []
    for row in rows:
        value = esc(row["value"])
        if safe_url(row["url"]):
            value = f'<a href="{esc(row["url"])}" target="_blank" rel="noopener noreferrer">{value}</a>'
        body.append(f'<tr><td>{esc(row["category"]).upper()}</td><td>{esc(row["label"])}</td><td>{value}</td><td>{esc(row["source"])}</td></tr>')
    tone = lambda status: "ok" if status in ("ok", "complete") else "bad" if status in ("error", "failed") else "warn"
    label = lambda status: esc(STATUS_LABELS.get(status, status))
    statuses = "".join(f'<li><b>{esc(r["tool"])}</b> · <span class="{tone(r["status"])}">{label(r["status"])}</span>' + (f'<details><summary>Run log</summary><pre>{esc(r.get("log", ""))}</pre></details>' if r.get("log") else "") + "</li>" for r in report["results"])
    extras = "".join(f'<details><summary>All EXIF fields</summary><pre>{esc(json.dumps(r["all"], ensure_ascii=False, indent=2))}</pre></details>' for r in report["results"] if r.get("all"))
    notes = "".join(f'<p class="notice">{esc(r["note"])}</p>' for r in report["results"] if r.get("note"))
    leaked = [b for r in report["results"] for b in r.get("breaches", [])]
    if leaked:
        credit = ' Breach data from <a href="https://haveibeenpwned.com" target="_blank" rel="noopener noreferrer">Have I Been Pwned</a>, licensed CC BY 4.0.' if any("HIBP" in b.get("source", "") for b in leaked) else ""
        notes += f'<p class="notice">Leaks lists what each breach exposed, never the leaked passwords or records. A clean result does not mean an address is safe.{credit}</p>'
    if report["kind"] == "email":
        notes += '<p class="notice">The name before @ is searched. A matching name doesn\'t link the account to this email address, and the mailbox itself isn\'t verified.</p>'
    empty = '<tr><td colspan="4">No findings. Check source status below.</td></tr>'
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>SpyBrain · {esc(report['target'])}</title>
<style>{REPORT_CSS}</style></head><body><main>
<p class="eyebrow">{f'<img src="{owl_data_uri()}" alt="">' if owl_data_uri() else ""}<span>SPYBRAIN · TARGET · {esc(KINDS[report['kind']]).upper()}</span></p><h1>{esc(report['target'])}</h1><p class="meta">{esc(report['started'])} · {report['duration']:.1f} s · <span class="{tone(report['status'])}">{label(report['status'])}</span></p>
{f'<p class="notice">Purpose: {esc(report["purpose"])}</p>' if report.get("purpose") else ""}<p class="notice">Findings are leads from public sources. A matching name doesn't confirm identity: verify every match by hand. Use this report only for lawful, authorized investigations and protect it as personal data.</p>{notes}<h2><span class="tag">{len(rows)}</span> FINDINGS</h2><div class="scroll"><table><thead><tr><th>TYPE</th><th>ITEM</th><th>VALUE / LINK</th><th>SOURCE</th></tr></thead><tbody>{''.join(body) or empty}</tbody></table></div><h2>SOURCES</h2><ul>{statuses}</ul>{extras}</main></body></html>'''

def save_report(report, out=None):
    directory = Path(out) if out else REPORTS
    directory.mkdir(parents=True, exist_ok=True)
    name = Path(report["target"]).name if report["kind"] == "image" else report["target"]
    safe = re.sub(r"[^\w.-]+", "_", name)[:55]
    # Do not use with_suffix on a basename containing the user's domain extension.
    base = directory / f"{dt.datetime.now():%Y%m%d_%H%M%S}_{report['kind']}_{safe}_{report['id'][:8]}"
    files = {key: str(base) + "." + key for key in ("html", "json", "csv")}
    report["files"] = files
    Path(files["html"]).write_text(render(report), encoding="utf-8")
    with Path(files["csv"]).open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["category", "label", "value", "source", "url"])
        writer.writeheader()
        for row in flatten(report["results"]):
            writer.writerow({k: "'" + v if v.startswith(("=", "+", "-", "@", "\t", "\r")) else v for k, v in row.items()})
    destination = Path(files["json"])
    temporary = destination.with_suffix(".tmp")
    temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, destination)
    return report

def scan(target, kind=None, fast=True, callback=None, cancel=None, out=None, options=None):
    target, kind = validate(target, kind)
    jobs, context, availability = jobs_for(target, kind, options), ScanContext(callback, cancel), tool_status()
    started, clock, results = dt.datetime.now().astimezone(), time.monotonic(), []
    context.emit(state="plan", tools=[name for name, _, _ in jobs], total=len(jobs))
    def execute(name, function, value, work):
        CONTEXT.set(context)
        context.check()
        context.emit(state="running", tool=name)
        lookup = "sherlock" if name == "Sherlock" else "maigret" if name == "Maigret" else name
        if not availability.get(lookup, True):
            data = {"tool": name, "ok": False, "status": "missing", "log": "This tool isn't included in this installation. See README or build the full version."}
        else:
            try:
                data = function(value, work, fast)
            except Cancelled:
                data = {"tool": name, "ok": False, "status": "cancelled", "log": "Stopped by user."}
            except Exception as error:
                data = result(name, 1, f"{type(error).__name__}: {error}")
        context.emit(state="done", tool=name, result=data)
        return data
    with tempfile.TemporaryDirectory(prefix="spybrain_") as temp:
        with ThreadPoolExecutor(max_workers=4, thread_name_prefix="osint") as executor:
            futures = {executor.submit(execute, name, fn, value, Path(temp)): name for name, fn, value in jobs}
            for future in as_completed(futures):
                try:
                    results.append(future.result())
                except Cancelled:
                    results.append({"tool": futures[future], "ok": False, "status": "cancelled", "log": "Stopped before it started."})
    order = {name: index for index, (name, _, _) in enumerate(jobs)}
    results.sort(key=lambda r: order[r["tool"]])
    status = "cancelled" if context.cancel.is_set() else "complete" if all(r["ok"] for r in results) else "partial" if any(r["ok"] for r in results) else "failed"
    report = {"schema": 2, "version": VERSION, "id": uuid.uuid4().hex, "target": target, "kind": kind, "mode": "fast" if fast else "full", "started": started.isoformat(timespec="seconds"), "duration": round(time.monotonic() - clock, 2), "status": status, "results": results}
    if options and options.get("purpose"):
        report["purpose"] = str(options["purpose"])
    save_report(report, out)
    context.emit(state="finished", report=report)
    return report

def history(limit=100):
    REPORTS.mkdir(parents=True, exist_ok=True)
    reports = []
    for file in sorted(REPORTS.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            data = json.loads(file.read_text(encoding="utf-8"))
            if (isinstance(data, dict) and data.get("schema") == 2 and data.get("kind") in KINDS
                and isinstance(data.get("results"), list) and isinstance(data.get("target"), str)
                and isinstance(data.get("started"), str) and isinstance(data.get("duration"), (int, float))
                and isinstance(data.get("status"), str)
                and all(isinstance(r, dict) and isinstance(r.get("tool"), str) and isinstance(r.get("status"), str) for r in data["results"])):
                flatten(data["results"])
                data["files"] = {ext: str(file.with_suffix("." + ext)) for ext in ("html", "json", "csv")}
                reports.append(data)
                if len(reports) >= limit:
                    break
        except (OSError, ValueError, TypeError, KeyError, AttributeError):
            continue
    return reports

def main():
    if worker_main():
        return 0
    parser = argparse.ArgumentParser(description="SpyBrain")
    parser.add_argument("target")
    parser.add_argument("--type", choices=KINDS)
    parser.add_argument("--fast", action="store_true")
    parser.add_argument("--out", default=None)
    args = parser.parse_args()
    cancel = threading.Event()
    import signal
    signal.signal(signal.SIGINT, lambda *_: cancel.set())
    def progress(event):
        if event["state"] == "done":
            print(f"  {event['tool']}: {event['result']['status']}", flush=True)
    try:
        report = scan(args.target, args.type, args.fast, progress, cancel, args.out)
        print(f"[{report['status']}] {report['files']['html']}")
        return 0 if report["status"] == "complete" else 2
    except (ValueError, OSError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1

if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()
    sys.exit(main())
