# Changes in 2.2.0

- The app is now called **SpyBrain** and is aimed at journalists, investigators and threat-intelligence teams. The first-start notice, the guide and the reports say it is for lawful, authorized investigations; "Search only yourself" is gone. Reports from the earlier OSINT Hub move to `%LOCALAPPDATA%\SpyBrain` on first start.
- **Leaks page (new):** which known breaches expose an email address, when, and what they leaked, with a timeline by year coloured by what was exposed (passwords, personal data, only the address). A password check sends only a 5-character hash prefix (k-anonymity) and never stores or shows the password. Sources: XposedOrNot (no key) and Have I Been Pwned (your key). Leaked passwords and records are never shown or saved.
- Email scans now include a **Leaks** source; breaches appear in the findings, the report (with the HIBP credit its license requires) and History.
- **Photo page** (formerly Locate) estimates where a photo was taken with GeoCLIP on this computer. In this version it offers GeoCLIP only: Gemini, Claude, Google Vision (landmarks and web matches) and FaceCheck.ID face search are built and tested but switched off (`ENABLED_ENGINES` in `geolocate.py`), so no key is needed and no photo leaves the computer.
  - GeoCLIP takes about half a minute per photo instead of up to several minutes: the place features are prepared once and kept, instead of being recomputed in one huge batch for every photo.
  - New dot-matrix world map with probes while GeoCLIP works and a crosshair that locks onto the best estimate.
  - Photo metadata (Scan page) and photo location (Photo page) are separate.
  - The switched-off engines include an age check that blocks face search for photos of babies, children and teenagers, a required purpose and a one-time consent.
- Key window: warns when a pasted key can't be right for the service (for example an `AQ.` key for Google Vision), supports the workspace ID some Anthropic keys need, and Google's and Anthropic's errors are explained in plain words.
- Radar on the Scan page: the sweep turns continuously, contacts flare as it passes and fade like phosphor, sonar rings ripple out during a scan, sources flash when the sweep crosses them, and a bearing bezel surrounds the target. The owl at its centre now moves (a short loop made with Kling 3.0).
- Fixed: new rows on the Photo page tables now glow smoothly, the *Analyze photo* button stays visible while the engine list scrolls, and the map's lock box shows its coordinates.
- 159 tests (was 35).

# Changes in 2.1.0

- New interface: black terminal look with signal green (amber marks warnings, red failures), Bahnschrift Condensed headings and Consolas data, top navigation and a matching black title bar.
- New logo: a green night-vision owl on a branch. It sits in the centre of the Scan page until a target is set, then fades into the target reticle.
- Link chart on the Scan page: the target sits in a reticle that locks on when a scan starts, a thread runs to every source, packets travel while a source is queried, a radar sweep runs during the scan, and findings pop out and pin to the source that found them.
- Findings count shown as a green evidence marker; new rows slide in and glow briefly. The table keeps the order sources reported until you sort it.
- History and Sources redrawn as aligned ledgers with status glyphs; Guide rewritten as a reference table.
- The whole app is in English: interface, error messages, CLI output, HTML reports, quick start and README.
- Animations follow the Windows *Animation effects* setting.
- New owl icon to match.
- Locate page: estimates where a photo was taken with GeoCLIP (on this computer) and, with your own API key, Gemini and Claude, which also list the clues they used. Candidates drop onto an animated world map that zooms to them; EXIF GPS, if present, is marked for comparison. Reverse image search for Google Lens, Bing, Yandex and TinEye.
- Photo scans are split: Scan reads photo metadata, Locate estimates the location.
- "Search only yourself" notice on first start and throughout the app.
- Report labels are now English (for example `Dimensions`, `Account`). Saved 2.0 reports still open; their GPS map links keep working.

The 2.0 interface, engine and icon are kept in `backups/pred-grafikou`.

# Changes in 2.0.0

- Native interface, custom icon, history, filtering and sorting of results.
- Portable Windows bundle with an EXE; no Python installation needed.
- Parallel sources, live results, failure isolation, time limits and process stopping.
- Domain DNS records, basic photo details and SHA-256.
- HTML, structured JSON with scan metadata, and CSV; safe links and CSV formula neutralisation.
- Fixed passing paths with spaces and removed opening an unrelated previous report.
- Quick mode really limits Sherlock too; Maigret uses limited concurrency and the system DNS.
- Reports have unique names, temporary files are cleaned up and finished results survive a stop.
- Tests for validation, tool adapters, exports, process stopping and the interface.

The original source code and documentation remain in `backups/original`.
