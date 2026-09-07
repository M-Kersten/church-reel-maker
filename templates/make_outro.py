"""Rebuild templates/outro.mp4 from templates/outro.json and templates/church.json.

Run it from anywhere:  python templates/make_outro.py

The app rebuilds the end screen by itself when the config changed, so this script
is only handy when you want to see the result without starting the app.
"""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VENV_DIR = ROOT / ".venv"
VENV = VENV_DIR / ("Scripts/python.exe" if os.name == "nt" else "bin/python")

# Use the app's own Python, which has the packages this script needs.
if VENV.is_file() and Path(sys.prefix).resolve() != VENV_DIR.resolve():
    os.execv(str(VENV), [str(VENV), str(Path(__file__).resolve()), *sys.argv[1:]])

sys.path.insert(0, str(ROOT))

try:
    from backend import outro
except ImportError:
    sys.exit("Start de app eerst een keer met start.bat of start.command; daarna werkt dit script.")

try:
    outro.save_default_config()
    print("geschreven:", outro.build())
except Exception as exc:  # noqa: BLE001
    sys.exit(str(exc))
