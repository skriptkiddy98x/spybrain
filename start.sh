#!/usr/bin/env bash
# Launch the SpyBrain desktop app: prefer a built bundle, else the source checkout's venv.
set -euo pipefail
cd "$(dirname "$0")"

if [ -x "dist/SpyBrain/SpyBrain" ]; then
  exec "dist/SpyBrain/SpyBrain" "$@"
fi
if [ -x ".venv/bin/python" ]; then
  exec ".venv/bin/python" app.py "$@"
fi

echo "Set up the Python environment first, see README.md." >&2
exit 1
