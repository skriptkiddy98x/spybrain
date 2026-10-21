#!/usr/bin/env bash
# SpyBrain command line. With no arguments, opens the desktop app instead.
#   ./osint.sh example.org --fast
set -euo pipefail
cd "$(dirname "$0")"
export PYTHONIOENCODING=utf-8 PYTHONUTF8=1

if [ "$#" -eq 0 ]; then
  exec ./start.sh
fi
if [ ! -x ".venv/bin/python" ]; then
  echo "The Python environment is missing. Use ./start.sh for the desktop app, or see README.md." >&2
  exit 1
fi
exec ".venv/bin/python" osinthub.py "$@"
