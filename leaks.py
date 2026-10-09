"""SpyBrain leak checks: which breaches expose an email, and whether a password is known.

XposedOrNot and HIBP Pwned Passwords are free and need no key. The password never leaves this
computer: only the first five characters of its SHA-1 hash are sent (k-anonymity), and the rest is
matched locally. Have I Been Pwned breach search is optional and uses the user's own API key.

No leaked password or record is ever shown or stored. Only the breach name, its date and the
categories of data it exposed are reported.
"""
from __future__ import annotations
import datetime as dt, hashlib, json, time, urllib.error, urllib.parse, urllib.request
import geolocate
import osinthub as hub

EngineError = geolocate.EngineError
load_key, save_key = geolocate.load_key, geolocate.save_key

SERVICE = "hibp"   # key name in geolocate.SERVICES / keys.dat
USER_AGENT = "SpyBrain-OSINT-Tool"
# XposedOrNot's free tier is for personal, low-volume use: 25 requests per hour and 100 per day per IP.
XPOSED = "https://api.xposedornot.com/v1"
HIBP = "https://haveibeenpwned.com/api/v3"
PWNED = "https://api.pwnedpasswords.com/range/"
CACHE_SECONDS = 3600
_cache = {}   # email checks kept in memory only, so repeating one doesn't spend the free hourly quota

# How the breached site stored passwords, as XposedOrNot reports it.
PASSWORD_RISK = {"plaintext": "plain text", "easytocrack": "weak hash", "hardtocrack": "strong hash"}
# Data classes that identify an address and nothing more. Any other class a breach lists (names, phone
# numbers, addresses, birth dates, IP addresses, payment data...) makes it a personal-data breach.
BASIC = {"email addresses", "email address", "usernames", "username", "user names"}


def _wait(seconds):
    seconds = int(seconds or 0)
    if seconds <= 0:
        return "a moment"
    if seconds < 90:
        return f"{seconds} s"
    if seconds < 5400:
        return f"{round(seconds / 60)} min"
    return f"{round(seconds / 3600)} h"


def _request(url, headers, timeout, name, accept_404=False):
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json", **headers})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, response.read().decode("utf-8")
    except urllib.error.HTTPError as error:
        if error.code == 404 and accept_404:
            return 404, ""
        if error.code in (401, 403):
            raise EngineError(f"{name} rejected the API key. Check it under Set key.") from None
        if error.code == 429:
            try:
                retry = int(error.headers.get("Retry-After", "") or 0)
            except ValueError:
                retry = 0
            raise RateLimited(f"{name} rate limit reached. Try again in {_wait(retry)}.", retry) from None
        raise EngineError(f"{name} error {error.code}. Try again later.") from None
    except (urllib.error.URLError, TimeoutError, ConnectionError):
        raise EngineError(f"Can't reach {name}. Check the internet connection.") from None


class RateLimited(EngineError):
    """The service refused the request because of its rate limit; retry_after is in seconds."""
    def __init__(self, message, retry_after=0):
        super().__init__(message)
        self.retry_after = retry_after


# ---- Ranking: what a breach exposes.

def severity(breach):
    """3 = passwords exposed, 2 = personal data exposed, 1 = only email addresses or usernames,
    0 = the source didn't say what was exposed."""
    classes = [c.lower() for c in breach.get("data", [])]
    if not classes:
        return 0
    if any("password" in c for c in classes):
        return 3
    return 1 if all(c in BASIC for c in classes) else 2


def _data_list(value):
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    return [part.strip() for part in str(value or "").replace(",", ";").split(";") if part.strip()]


def year_of(breach):
    """Year of a breach, or 0 when its date is missing or implausible."""
    digits = "".join(c for c in str(breach.get("date", "")) if c.isdigit())[:4]
    year = int(digits) if len(digits) == 4 else 0
    return year if 1990 <= year <= dt.date.today().year + 1 else 0


# ---- Email: which breaches include this address.

def xposed_breaches(email):
    """Breaches from XposedOrNot (free, no key), with details. Empty list means none found."""
    url = f"{XPOSED}/breach-analytics?email=" + urllib.parse.quote(email)
    status, text = _request(url, {}, 20, "XposedOrNot", accept_404=True)
    if status == 404 or not text:
        return []
    try:
        data = json.loads(text)
    except ValueError:
        raise EngineError("XposedOrNot returned an unreadable answer.") from None
    if not isinstance(data, dict) or data.get("Error"):
        return []
    rows, seen = [], set()
    for detail in ((data.get("ExposedBreaches") or {}).get("breaches_details") or []):
        name = str(detail.get("breach") or "").strip()
        if not name or name.lower() in seen:
            continue
        seen.add(name.lower())
        try:
            records = int(detail.get("xposed_records") or 0) or None
        except (TypeError, ValueError):
            records = None
        rows.append({"name": name, "domain": str(detail.get("domain") or "").strip(), "date": str(detail.get("xposed_date") or "").strip(),
                     "data": _data_list(detail.get("xposed_data")), "records": records, "source": "XposedOrNot",
                     "password_risk": PASSWORD_RISK.get(str(detail.get("password_risk") or "").lower(), ""),
                     "verified": str(detail.get("verified") or "").lower() == "yes", "flags": []})
    return rows


def xposed_names(email):
    """Breach names only, from XposedOrNot's quick check. It has its own rate limit, so it still
    answers when the detailed endpoint is used up for the hour."""
    status, text = _request(f"{XPOSED}/check-email/" + urllib.parse.quote(email), {}, 20, "XposedOrNot", accept_404=True)
    if status == 404 or not text:
        return []
    try:
        data = json.loads(text)
    except ValueError:
        raise EngineError("XposedOrNot returned an unreadable answer.") from None
    names = []
    for group in (data.get("breaches") or []) if isinstance(data, dict) else []:
        names += [str(n).strip() for n in (group if isinstance(group, list) else [group]) if str(n).strip()]
    return [{"name": n, "domain": "", "date": "", "data": [], "records": None, "source": "XposedOrNot", "password_risk": "",
             "verified": False, "flags": []} for n in dict.fromkeys(names)]


def hibp_breaches(email, key):
    """Breaches from Have I Been Pwned (needs the user's key). Empty list means none found."""
    url = f"{HIBP}/breachedAccount/" + urllib.parse.quote(email) + "?truncateResponse=false"
    status, text = _request(url, {"hibp-api-key": key}, 20, "Have I Been Pwned", accept_404=True)
    if status == 404 or not text:
        return []
    try:
        data = json.loads(text)
    except ValueError:
        raise EngineError("Have I Been Pwned returned an unreadable answer.") from None
    rows = []
    for breach in data if isinstance(data, list) else []:
        name = str(breach.get("Title") or breach.get("Name") or "").strip()
        if not name or breach.get("IsFabricated"):
            continue
        flags = [label for field, label in (("IsStealerLog", "stealer log"), ("IsSpamList", "spam list"), ("IsMalware", "malware"),
                                            ("IsSensitive", "sensitive")) if breach.get(field)]
        rows.append({"name": name, "domain": str(breach.get("Domain") or "").strip(), "date": str(breach.get("BreachDate") or "").strip(),
                     "data": _data_list(breach.get("DataClasses")), "records": breach.get("PwnCount") if isinstance(breach.get("PwnCount"), int) else None,
                     "source": "HIBP", "password_risk": "", "verified": bool(breach.get("IsVerified")), "flags": flags})
    return rows


def merge(primary, extra):
    """Combine two breach lists. The primary list wins on overlap, but gains what the other adds
    (an HIBP row gets XposedOrNot's password storage note, and the reverse), then newest first."""
    merged = {row["name"].lower(): dict(row, source=row["source"]) for row in primary}
    for row in extra:
        key = row["name"].lower()
        if key not in merged:
            merged[key] = dict(row)
            continue
        mine = merged[key]
        if row["source"] not in mine["source"].split(" + "):
            mine["source"] += " + " + row["source"]
        for field in ("password_risk", "domain", "date"):
            mine[field] = mine.get(field) or row.get(field, "")
        mine["data"] = mine["data"] or row["data"]
        mine["records"] = mine["records"] or row["records"]
        mine["flags"] = sorted(set(mine.get("flags", [])) | set(row.get("flags", [])))
        mine["verified"] = mine.get("verified") or row.get("verified", False)
    return sorted(merged.values(), key=lambda row: (year_of(row), row.get("records") or 0), reverse=True)


def check_email(email, hibp_key="", check=lambda: None, use_cache=True):
    """All breaches for an email, merged from the available sources.

    Returns {"breaches": [...], "sources": [...], "errors": [...], "limited": seconds or 0}. A source
    that fails is reported in errors but doesn't stop the others; if every source fails, it raises.
    """
    key = (email.lower(), bool(hibp_key))
    cached = _cache.get(key)
    if use_cache and cached and time.monotonic() - cached[0] < CACHE_SECONDS:
        return dict(cached[1], cached=True)
    breaches, sources, errors, limited = [], [], [], 0
    check()
    try:
        try:
            found = xposed_breaches(email)
        except RateLimited as error:
            # The detailed endpoint is used up; the quick check has its own allowance and still gives names.
            limited = error.retry_after
            found = xposed_names(email)
            errors.append(f"XposedOrNot: detailed lookup limited, showing names only (full detail again in {_wait(error.retry_after)}).")
        breaches = merge(found, [])
        sources.append("XposedOrNot")
    except RateLimited as error:
        limited = max(limited, error.retry_after)
        errors.append(f"XposedOrNot: {error}")
    except EngineError as error:
        errors.append(f"XposedOrNot: {error}")
    if hibp_key:
        check()
        try:
            breaches = merge(hibp_breaches(email, hibp_key), breaches)
            sources.append("Have I Been Pwned")
        except RateLimited as error:
            limited = max(limited, error.retry_after)
            errors.append(f"Have I Been Pwned: {error}")
        except EngineError as error:
            errors.append(f"Have I Been Pwned: {error}")
    if not sources:
        raise (RateLimited(errors[0].split(": ", 1)[-1], limited) if limited else EngineError(errors[0].split(": ", 1)[-1]))
    outcome = {"breaches": breaches, "sources": sources, "errors": errors, "limited": limited}
    if not errors:
        _cache[key] = (time.monotonic(), outcome)
    return dict(outcome)


# ---- Password: is it in a known breach? (k-anonymity; the password never leaves this computer.)

def password_pwned(password):
    """How many times the password appears in known breaches. Only a 5-character hash prefix is sent."""
    if not password:
        raise EngineError("Enter a password to check.")
    digest = hashlib.sha1(password.encode("utf-8", "surrogatepass")).hexdigest().upper()
    prefix, suffix = digest[:5], digest[5:]
    _, text = _request(PWNED + prefix, {"Add-Padding": "true", "Accept": "text/plain"}, 20, "Pwned Passwords")
    for line in text.splitlines():
        parts = line.strip().split(":")
        if len(parts) == 2 and parts[0].upper() == suffix:
            try:
                return max(0, int(parts[1]))   # padded filler lines carry a count of 0
            except ValueError:
                return 0
    return 0


# ---- Scan job (plugs into osinthub like the other adapters).

def m_leaks(target, work, fast):
    """Email breach check as a scan source: XposedOrNot plus HIBP if a key is saved."""
    context = hub.CONTEXT.get() or hub.ScanContext()
    try:
        found = check_email(target, load_key(SERVICE), context.check)
    except EngineError as error:
        return hub.result("Leaks", 1, str(error))
    lines = [f"Sources: {', '.join(found['sources'])}", f"{len(found['breaches'])} breaches found."] + found["errors"]
    data = hub.result("Leaks", 0, "\n".join(lines), breaches=found["breaches"])
    if found["errors"]:
        data.update(status="partial", ok=False)
    return data


def breach_summary(breaches):
    """Headline for a set of breaches, e.g. '7 breaches since 2012 · passwords in 3 · 1 in plain text'."""
    if not breaches:
        return "No breaches found"
    years = [y for y in (year_of(b) for b in breaches) if y]
    parts = [f"{len(breaches)} breach" + ("" if len(breaches) == 1 else "es") + (f" since {min(years)}" if years else "")]
    passwords = [b for b in breaches if severity(b) == 3]
    if passwords:
        parts.append(f"passwords in {len(passwords)}")
        plain = sum(1 for b in passwords if b.get("password_risk") == "plain text")
        if plain:
            parts.append(f"{plain} in plain text")
    return " · ".join(parts)
