#!/bin/bash
# Church Reel Maker launcher for macOS (double-click this file).
cd "$(dirname "$0")" || exit 1

fail() {
  echo
  echo "Something went wrong. Read the messages above, then press Enter to close."
  read -r
  exit 1
}

# --- 1. Find Python 3.10+ ---------------------------------------------------------
PY=""
for candidate in python3.13 python3.12 python3.11 python3.10 python3; do
  if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)' >/dev/null 2>&1; then
    PY="$candidate"
    break
  fi
done
if [ -z "$PY" ]; then
  if command -v brew >/dev/null 2>&1; then
    echo "Python was not found. Installing it with Homebrew ..."
    brew install python || fail
    PY="python3"
  else
    echo "Python 3 was not found. Install it from https://www.python.org/downloads/macos/ and run start.command again."
    fail
  fi
fi

# --- 2. Create the Python environment on first run ----------------------------------
if [ ! -x ".venv/bin/python" ]; then
  echo "Setting up the app for the first time, this takes a few minutes ..."
  "$PY" -m venv .venv || fail
  .venv/bin/python -m pip install --upgrade pip >/dev/null
fi

# --- 3. Start (installs/updates packages and FFmpeg when needed, opens the browser) ---
.venv/bin/python launcher.py || fail
