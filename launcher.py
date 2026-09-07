"""One-click launcher for Church Reel Maker.

Started by start.bat (Windows) or start.command (macOS) after those scripts
have created the Python environment. This script:

  1. loads config.env (API key, model choices),
  2. makes sure ffmpeg/ffprobe are available (downloads a build into tools/ if not),
  3. starts the web server and opens the browser.

It can also be run by hand:  python launcher.py
"""

import os
import platform
import shutil
import socket
import stat
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TOOLS = ROOT / "tools" / "ffmpeg"
CONFIG = ROOT / "config.env"
CONFIG_EXAMPLE = ROOT / "config.example.env"
PORT = int(os.environ.get("PORT", "8000"))

FFMPEG_DOWNLOADS = {
    "Windows": [("https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip", ("ffmpeg.exe", "ffprobe.exe"))],
    "Darwin": [
        ("https://evermeet.cx/ffmpeg/getrelease/zip", ("ffmpeg",)),
        ("https://evermeet.cx/ffmpeg/getrelease/ffprobe/zip", ("ffprobe",)),
    ],
}


def say(message: str) -> None:
    print(f"[Church Reel Maker] {message}", flush=True)


# --- config.env ---------------------------------------------------------------


def load_config() -> None:
    if not CONFIG.exists() and CONFIG_EXAMPLE.exists():
        shutil.copy(CONFIG_EXAMPLE, CONFIG)
        say(f"Created {CONFIG.name}. Put your ANTHROPIC_API_KEY in it to enable clip suggestions.")
    if not CONFIG.exists():
        return
    for line in CONFIG.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip('"').strip("'")
        if key and value and key not in os.environ:
            os.environ[key] = value


# --- ffmpeg -------------------------------------------------------------------


def ffmpeg_ready() -> bool:
    return shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


def download(url: str, target: Path) -> None:
    say(f"Downloading {url}")
    with urllib.request.urlopen(url, timeout=120) as res, target.open("wb") as out:
        total = int(res.headers.get("content-length") or 0)
        done = 0
        while chunk := res.read(1024 * 256):
            out.write(chunk)
            done += len(chunk)
            if total:
                print(f"\r  {done * 100 // total:3d}%  ({done // 1_000_000} MB)", end="", flush=True)
        print()


def extract_binaries(archive: Path, names: tuple[str, ...]) -> None:
    TOOLS.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as zf:
        for member in zf.namelist():
            base = member.rsplit("/", 1)[-1]
            if base in names and not member.endswith("/"):
                target = TOOLS / base
                with zf.open(member) as src, target.open("wb") as dst:
                    shutil.copyfileobj(src, dst)
                target.chmod(target.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    if platform.system() == "Darwin":  # remove the quarantine flag so Gatekeeper lets the binaries run
        for name in names:
            subprocess.run(["xattr", "-d", "com.apple.quarantine", str(TOOLS / name)], capture_output=True)


def ensure_ffmpeg() -> None:
    if TOOLS.is_dir():
        os.environ["PATH"] = str(TOOLS) + os.pathsep + os.environ.get("PATH", "")
    if ffmpeg_ready():
        return
    downloads = FFMPEG_DOWNLOADS.get(platform.system())
    if not downloads:
        raise SystemExit("ffmpeg and ffprobe are not installed. Install them with your package manager "
                         "(for example: sudo apt install ffmpeg) and start again.")
    say("FFmpeg was not found. Downloading it once (about 100 MB) into tools/ffmpeg …")
    for url, names in downloads:
        archive = TOOLS.parent / "download.zip"
        TOOLS.parent.mkdir(parents=True, exist_ok=True)
        download(url, archive)
        extract_binaries(archive, names)
        archive.unlink()
    os.environ["PATH"] = str(TOOLS) + os.pathsep + os.environ.get("PATH", "")
    if not ffmpeg_ready():
        raise SystemExit("FFmpeg download failed. Install FFmpeg manually (https://ffmpeg.org/download.html) and start again.")
    say("FFmpeg is ready.")


# --- frontend -----------------------------------------------------------------


def ensure_frontend() -> None:
    dist = ROOT / "frontend" / "dist" / "index.html"
    if dist.exists():
        return
    npm = shutil.which("npm")
    if npm is None:
        raise SystemExit("The web interface has not been built (frontend/dist is missing) and Node.js is not "
                         "installed. Ask a developer to run `npm run build` in frontend/ or install Node.js.")
    say("Building the web interface (first time only) …")
    frontend = ROOT / "frontend"
    if not (frontend / "node_modules").is_dir():
        subprocess.run([npm, "install"], cwd=frontend, check=True)
    subprocess.run([npm, "run", "build"], cwd=frontend, check=True)


# --- server -------------------------------------------------------------------


def port_in_use(port: int) -> bool:
    with socket.socket() as s:
        return s.connect_ex(("127.0.0.1", port)) == 0


def open_browser_when_ready(url: str) -> None:
    for _ in range(60):
        if port_in_use(PORT):
            say(f"Open {url} in your browser if it did not open by itself.")
            webbrowser.open(url)
            return
        time.sleep(0.5)


def main() -> None:
    os.chdir(ROOT)
    load_config()
    ensure_ffmpeg()
    ensure_frontend()
    url = f"http://localhost:{PORT}"
    if port_in_use(PORT):
        say(f"Something is already running on port {PORT}; opening {url}.")
        webbrowser.open(url)
        return
    say(f"Starting the app at {url}  (close this window to stop it)")
    threading.Thread(target=open_browser_when_ready, args=(url,), daemon=True).start()
    import uvicorn

    uvicorn.run("backend.main:app", host="127.0.0.1", port=PORT, log_level="warning")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
    except SystemExit as exc:
        if exc.code not in (None, 0):
            say(str(exc.code))
            if sys.stdin and sys.stdin.isatty():
                input("Press Enter to close.")
            raise
