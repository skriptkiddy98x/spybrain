#!/usr/bin/env bash
# Build the SpyBrain bundle on Linux: install deps, run the tests, then PyInstaller.
# The Linux counterpart of build.ps1. Takes a while because of PyTorch.
set -euo pipefail
cd "$(dirname "$0")"

PYTHON=".venv/bin/python"
[ -x "$PYTHON" ] || { echo ".venv is missing. Follow README first." >&2; exit 1; }

"$PYTHON" -m pip install -r requirements.txt 'pyinstaller==6.22.3'
"$PYTHON" -m unittest discover -s tests -v
"$PYTHON" -m PyInstaller --clean --noconfirm SpyBrain.spec

BUNDLE="dist/SpyBrain"
cp QUICKSTART.txt THIRD_PARTY_NOTICES.md requirements-lock.txt "$BUNDLE/"
cp -R licenses "$BUNDLE/"

# A Source copy, so the bundle can be rebuilt. Mirrors build.ps1.
SRC="$BUNDLE/Source"
mkdir -p "$SRC"
cp app.py osinthub.py geolocate.py leaks.py SpyBrain.spec \
   build.ps1 build.sh start.sh osint.sh \
   requirements.txt requirements-lock.txt README.md CHANGELOG.md \
   QUICKSTART.txt THIRD_PARTY_NOTICES.md "$SRC/"
cp -R tests assets licenses "$SRC/"

# Rebuilding from Source can reuse the PhoneInfoga binary, if bin/ has one (see bin/README.md).
mkdir -p "$SRC/bin"
cp bin/README.md "$SRC/bin/"
[ -f bin/phoneinfoga ] && cp bin/phoneinfoga "$SRC/bin/" || true

echo "Done: dist/SpyBrain/SpyBrain. Copy the whole SpyBrain folder when moving it."
