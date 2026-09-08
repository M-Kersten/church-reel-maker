"""Checks the interface shows so the user knows the app can do its work."""

import os
import shutil
import socket
import subprocess
from pathlib import Path

from pydantic import BaseModel

from . import discovery, storage
from .models import PROJECTS_DIR, ROOT, SERVICES_DIR, TEMPLATES_DIR
from .transcription import MODEL_SIZE


class Check(BaseModel):
    name: str
    ok: bool
    detail: str


def _ffmpeg() -> Check:
    binary = shutil.which("ffmpeg")
    if not binary:
        tools = ROOT / "tools" / "ffmpeg"
        binary = next((str(p) for p in (tools / "ffmpeg.exe", tools / "ffmpeg") if p.is_file()), None)
    if not binary:
        return Check(name="FFmpeg", ok=False,
                     detail="Niet gevonden. Sluit de app en start opnieuw met start.bat of start.command; FFmpeg wordt dan opgehaald.")
    try:
        first = subprocess.run([binary, "-version"], capture_output=True, text=True, timeout=15).stdout.splitlines()[0]
        version = first.split(" ")[2] if len(first.split(" ")) > 2 else "onbekend"
    except Exception:  # noqa: BLE001
        return Check(name="FFmpeg", ok=False, detail="Gevonden, maar de versie kon niet gelezen worden.")
    return Check(name="FFmpeg", ok=True, detail=f"versie {version}")


def _whisper() -> Check:
    cache = Path(os.environ.get("HF_HOME", Path.home() / ".cache" / "huggingface")) / "hub"
    downloaded = any(cache.glob(f"models--*faster-whisper-{MODEL_SIZE}")) if cache.is_dir() else False
    return Check(name="Spraakmodel", ok=True,
                 detail=f"{MODEL_SIZE}, klaar voor gebruik" if downloaded
                 else f"{MODEL_SIZE}, wordt bij de eerste keer uitschrijven gedownload (ongeveer 460 MB)")


def _llm() -> Check:
    if discovery.LLM_PROVIDER == "ollama":
        host = discovery.OLLAMA_URL.split("//")[-1]
        name, _, port = host.partition(":")
        try:
            with socket.create_connection((name, int(port or 11434)), timeout=1):
                return Check(name="Momenten zoeken", ok=True, detail=f"lokaal via Ollama ({discovery.LLM_MODEL or 'llama3.1'})")
        except OSError:
            return Check(name="Momenten zoeken", ok=False,
                         detail=f"Ollama antwoordt niet op {discovery.OLLAMA_URL}. Start Ollama, of zet LLM_PROVIDER weer op anthropic.")
    if os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"):
        return Check(name="Momenten zoeken", ok=True, detail=f"Claude ({discovery.LLM_MODEL or 'claude-opus-5'})")
    return Check(name="Momenten zoeken", ok=False,
                 detail="Er is geen Claude API-sleutel ingesteld. Zet ANTHROPIC_API_KEY in config.env en start de app opnieuw.")


def _disk() -> Check:
    free_gb = shutil.disk_usage(ROOT).free / 1e9
    if free_gb >= 3:
        return Check(name="Schijfruimte", ok=True, detail=f"{free_gb:.0f} GB vrij")
    try:
        recoverable = storage.survey()["usedMb"] / 1000
    except Exception:  # noqa: BLE001
        recoverable = 0.0
    advice = (f" Onder Opruimen staat {recoverable:.1f} GB aan opnames en werkbestanden klaar om weg te gooien."
              if recoverable >= 0.5 else "")
    return Check(name="Schijfruimte", ok=False,
                 detail=f"Nog maar {free_gb:.1f} GB vrij. Een dienst van anderhalf uur heeft al gauw "
                        f"enkele GB nodig.{advice}")


def _folders() -> Check:
    problems = []
    for directory in (PROJECTS_DIR, SERVICES_DIR, TEMPLATES_DIR):
        try:
            directory.mkdir(parents=True, exist_ok=True)
            probe = directory / ".schrijftest"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink()
        except OSError:
            problems.append(directory.name)
    return Check(name="Mappen", ok=not problems, detail="Alles beschrijfbaar" if not problems
                 else f"Kan niet schrijven in: {', '.join(problems)}")


def report() -> dict:
    checks = [_ffmpeg(), _whisper(), _llm(), _disk(), _folders()]
    return {"ok": all(c.ok for c in checks), "checks": [c.model_dump() for c in checks]}
