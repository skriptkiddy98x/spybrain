# SpyBrain user guide

The full reference for SpyBrain 2.2. For the overview, screenshots and quick start see the [README](../README.md).

A Windows desktop app for journalists, investigators and threat-intelligence teams: one target, several public sources, findings on one screen. It runs sources in parallel, checks whether an email or password appears in known breaches, estimates where photos were taken, keeps a history of scans and exports to HTML, JSON and CSV.

**For lawful, authorized investigations only.** Findings are leads, not proof. Verify them by hand, and protect saved reports and any personal data you collect. Face search is blocked for children and teenagers.

## Running it

**Double-click `start.bat` or `dist\SpyBrain\SpyBrain.exe`** (the EXE exists after you build it, see below). Without arguments, `osint.bat` opens the app too.

The Windows bundle contains Python, the interface and the OSINT tools. To move it to another computer, copy the **whole `dist\SpyBrain` folder**, including `_internal`. The EXE alone isn't enough. The first start can be slower while antivirus checks the files. The bundle isn't digitally signed.

## What it checks

| Input | Sources and results |
|---|---|
| Username | Sherlock + Maigret, merged accounts and public identifiers |
| Domain | DNS (A, AAAA, MX, NS, TXT, CAA) + theHarvester |
| Phone | libphonenumber + PhoneInfoga, numbering plan and links |
| Email | **Leaks** (XposedOrNot, plus Have I Been Pwned with your key) for the whole address; the name before @ via Sherlock + Maigret; for a company domain also DNS + theHarvester |
| Photo metadata (Scan page) | EXIF, GPS if present, dimensions, format, size and SHA-256 |
| Photo page | Where it was taken, estimated by GeoCLIP on this computer (online engines are built but switched off, see below) |
| Leaks page | Which known breaches expose an email, and whether a password is known |

- The type is detected automatically or chosen by hand. A name with a dot can look like a domain: choose Username then.
- Quick scan: 12 selected Sherlock sites + Maigret's top 100; a domain uses 2 public theHarvester sources.
- Deep scan: every Sherlock site + Maigret's top 500; 6 theHarvester sources. The number of sites depends on each tool's database.
- Findings appear as each source finishes. The radar on the Scan page shows the target, every source and the findings pinned to it; the table can be filtered and sorted, and each source's diagnostics are in Run log.
- Stop ends the tools and their child processes. Finished results are saved. A running DNS query can take up to 4 more seconds; local photo processing can also finish briefly.
- One failing tool doesn't stop the rest of the scan. Errors, timeouts and missing tools each have their own status. An empty result doesn't prove the data isn't out there.
- The HTML report has a print layout; your browser can save it as PDF.
- Photo metadata is read on this computer and never uploaded. Other scans connect to public services.
- Animations follow the Windows setting *Animation effects* (Settings › Accessibility › Visual effects).

## Photo page

Choose a photo and press **Analyze photo**. **GeoCLIP** (an open model, MIT license) compares it with 100,000 places worldwide and runs on this computer: the photo is never uploaded and no key is needed. The first run downloads a 1.7 GB model to `%LOCALAPPDATA%\SpyBrain\models` and prepares the places once, which can take a few minutes; after that a photo takes about half a minute. Results are estimates: usually the right region, rarely the exact spot. EXIF GPS, if present, is marked on the map for comparison.

**Switched off in this version:** Gemini, Claude, Google Vision (landmarks and web matches) and FaceCheck.ID face search are built and tested, but the Photo page, Sources and Guide don't show them and no scan uses them. To bring one back, add its name (`gemini`, `claude`, `landmarks`, `web`, `faces`) to `ENABLED_ENGINES` in `geolocate.py`. When they are on, every online engine re-encodes the photo without EXIF (no GPS, camera or owner data) and asks once before it is sent. What they need:

| Group | Engine | Where it runs | Needs |
|---|---|---|---|
| Where was it taken | GeoCLIP | This computer | Nothing. One-time 1.7 GB model download to `%LOCALAPPDATA%\SpyBrain\models` |
| | Gemini | Google AI | Your Gemini key (starts with `AIza` or `AQ.`) |
| | Claude | Anthropic | Your Anthropic key, and a workspace ID if Anthropic asks for one |
| | Google Vision | Google Cloud | A standard Cloud API key (starts with `AIza`) with the Cloud Vision API enabled and billing on |
| Where is it online | Web matches | Google Cloud | The same Google Vision key |
| Who else shows this face | Face search | FaceCheck.ID | Your FaceCheck.ID key and credits |

- Keys are entered with **Set key** and encrypted with Windows DPAPI in `%LOCALAPPDATA%\SpyBrain\keys.dat`. They never leave this computer except in the request to their own service.
- Results are estimates: usually the right region, rarely the exact spot. Gemini and Claude list the clues they used. EXIF GPS, if present, is marked on the map for comparison.
- **Face search** is never ticked for you. It needs a stated purpose (saved with the results) and a one-time consent. An age check on this computer (CLIP zero-shot) runs before anything is uploaded; if the photo appears to show a baby, child or teenager (30 % or more), or the check can't run, face search is blocked. The check is an estimate and can be wrong, so don't use photos of children. A matching face is a lead, not an identification.
- FaceCheck.ID's *test mode* is free but searches only 100,000 faces, so its results aren't meaningful.

## Leaks page

- **Email:** which breaches expose the address, when, and what kind of data (passwords, personal data, only the address). A timeline shows the breaches by year; click a block to find it in the list. *Scan this email* runs the full scan on the Scan page, and that scan is saved to History.
- **Password:** whether it appears in known breaches, and how many times. The password never leaves this computer: only the first 5 characters of its SHA-1 hash are sent to Pwned Passwords, and the match is made here. The box is cleared after the check, and nothing is saved.
- Sources: **XposedOrNot** (no key; the free API is for personal, low-volume use, 25 requests an hour and 100 a day per IP) and, optionally, **Have I Been Pwned** with your own key (**Set HIBP key**). When both answer, the results are merged. If XposedOrNot's detailed lookup is used up, the quick name-only check still answers. Checks are kept in memory for an hour so repeats don't use the quota.
- Leaked passwords and records are never shown, saved or put in reports. Only the breach name, date and the categories of data it exposed are. "No breaches found" doesn't mean an address is safe. Breach data from Have I Been Pwned is CC BY 4.0, and reports credit it.

## Reports and history

The EXE saves reports to `%LOCALAPPDATA%\SpyBrain\reports`; the first start moves the folder of the earlier OSINT Hub there. **Open reports folder** on the History page opens that path. When run from source, the project's `reports` folder is used.

Each scan gets a unique name and three files. **Export** saves a copy of the chosen format wherever you like. The CSV uses UTF-8 with BOM and neutralises values Excel could run as formulas. The HTML report escapes text and only links to web addresses.

History lists the last 100 reports in the version 2 format. Version 1 HTML/JSON reports stay untouched in the original `reports` folder and aren't imported. A backup of the original three files is in `backups\original`; the 2.0 interface, engine and icon are in `backups\pred-grafikou`. The quick checks on the Leaks page are not saved.

## Command line

```bat
osint.bat myname --fast
osint.bat example.org --fast
osint.bat person@example.org --fast
osint.bat "+421 900 123 456" --type phone
osint.bat "C:\path with spaces\photo.jpg" --type image
.venv\Scripts\python.exe osinthub.py name.with.dot --type username --fast
```

The CLI needs the project's Python environment; the desktop bundle doesn't. `--out` changes the output folder. Ctrl+C asks the scan to stop and save its results. Exit code 0 = every source finished, 2 = partial, failed or stopped scan, 1 = input or save error. Without `--fast` the CLI runs a deep scan; the app defaults to quick.

The EXE also has a `--cli` mode for automation, for example `"SpyBrain.exe" --cli example.org --fast --out "C:\reports"`. Because it is a windowed app without a console, read the resulting JSON and the process exit code; the Python CLI prints text output.

## Development and builds

Windows x64, Python 3.13. Direct dependencies are pinned in `requirements.txt`; the full environment, including theHarvester from its git commit (it isn't on PyPI in this version), is in `requirements-lock.txt`. Install from the lock file first.

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt pyinstaller==6.22.3
.\.venv\Scripts\python.exe app.py
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
powershell -ExecutionPolicy Bypass -File .\build.ps1
```

`bin\phoneinfoga.exe` is bundled with the app. When tool versions change, check their arguments and output formats. The app never downloads or runs updates silently; the site databases ship with the bundled tools. Update in the environment, test, and build a new bundle. The build runs the tests first, then PyInstaller with `SpyBrain.spec` (it takes about 15 minutes because of PyTorch).

The interface uses [Qt for Python](https://doc.qt.io/qtforpython-6/) and is packaged with [PyInstaller](https://pyinstaller.org/en/stable/). Sources run in separate processes; the frozen EXE has its own worker mode, so it isn't used like a plain `python.exe`.

Modules: `app.py` (interface), `osinthub.py` (scan engine, reports, CLI), `geolocate.py` (photo engines and API keys), `leaks.py` (breach and password checks).

## Limits of the results

A matching name doesn't confirm identity. For email, neither the mailbox nor account ownership is verified, and a breach list shows where an address was exposed, not who owns it. Phone data doesn't identify the owner or a live location, and the number may have been ported to another carrier. EXIF can be edited, and social networks often strip it. Photo location and face search results are estimates and leads. Network sources can return false matches, CAPTCHAs or blocks. The default theHarvester sources don't need an API key, but their availability isn't guaranteed.

Use SpyBrain only for lawful, authorized work. Verify findings by hand and protect saved reports as sensitive data.
