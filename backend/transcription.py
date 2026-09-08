"""Dutch speech-to-text with faster-whisper."""

import json
import os
import re
import subprocess
from pathlib import Path
from typing import Callable

from .models import TEMPLATES_DIR, Segment, Transcript

LANGUAGE = "nl"
VOCABULARY_PATH = TEMPLATES_DIR / "woordenlijst.json"
MODEL_SIZE = os.environ.get("WHISPER_MODEL", "small")
DEVICE = os.environ.get("WHISPER_DEVICE", "cpu")
COMPUTE_TYPE = os.environ.get("WHISPER_COMPUTE_TYPE", "int8" if DEVICE == "cpu" else "float16")

# Caption chunking: subtitles for reels read best as short phrases.
MAX_CHARS = 60  # roughly two lines of subtitle text
MAX_DURATION = 6.0  # seconds
PAUSE_SPLIT = 0.7  # a pause longer than this starts a new segment
EXTRACT_SHARE = 0.08  # first slice of the progress bar: pulling the audio out of the video

_model = None

DEFAULT_VOCABULARY = {
    "initialPrompt": (
        "Opname van een Nederlandse kerkdienst. Er komen woorden in voor als: gemeente, genade, geloof, "
        "vertrouwen, gebed, zegen, Heer, Here, HEER, Jezus Christus, Heilige Geest, Vader, discipelen, "
        "evangelie, psalm, lied, Opwekking, Bijbel, Mattheüs, Marcus, Lucas, Johannes, Handelingen, Romeinen, "
        "Korinthiërs, Galaten, Efeziërs, Filippenzen, Kolossenzen, Hebreeën, Openbaring, avondmaal, doop, "
        "voorganger, dominee, kerkenraad, collecte, halleluja, amen."
    ),
    "corrections": {
        "lee": "Lied",
        "here jezus": "Here Jezus",
        "heilige geest": "Heilige Geest",
    },
}


def load_vocabulary() -> dict:
    """Words that help the speech model, and fixes for the mistakes it keeps making.

    Lives in templates/woordenlijst.json so every church can add its own names.
    """
    if not VOCABULARY_PATH.is_file():
        VOCABULARY_PATH.write_text(json.dumps(DEFAULT_VOCABULARY, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return dict(DEFAULT_VOCABULARY)
    try:
        data = json.loads(VOCABULARY_PATH.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001  a broken file should not stop a transcription
        return dict(DEFAULT_VOCABULARY)
    return {"initialPrompt": data.get("initialPrompt", ""), "corrections": data.get("corrections", {})}


def initial_prompt() -> str:
    """The vocabulary plus the name of the church, which the model would not guess by itself."""
    prompt = load_vocabulary().get("initialPrompt", "")
    try:
        from . import brands

        name = brands.active().church.churchName
        if name and name.lower() not in prompt.lower():
            prompt = f"{prompt} De kerk heet {name}."
    except Exception:  # noqa: BLE001
        pass
    return prompt.strip()


def apply_corrections(text: str, corrections: dict[str, str]) -> str:
    """Replace known mishearings, whole words only, keeping the sentence's capital."""
    for wrong, right in corrections.items():
        if not wrong.strip():
            continue
        pattern = re.compile(rf"\b{re.escape(wrong)}\b", re.IGNORECASE)
        text = pattern.sub(right, text)
    return text


def get_model():
    global _model
    if _model is None:
        from faster_whisper import WhisperModel

        try:
            _model = WhisperModel(MODEL_SIZE, device=DEVICE, compute_type=COMPUTE_TYPE)
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(
                f"Het spraakmodel '{MODEL_SIZE}' kon niet geladen worden. De eerste keer wordt het gedownload; "
                f"controleer de internetverbinding en de vrije schijfruimte. ({exc})"
            ) from exc
    return _model


def extract_audio(source: Path, wav_path: Path, should_stop: Callable[[], None] | None = None,
                  on_progress: Callable[[float], None] | None = None, duration: float | None = None,
                  start: float = 0.0) -> None:
    """Pull the audio out of the video, or out of a range of it.

    Reports how far it is and checks `should_stop` while running, so the bar moves from the
    first second and stopping feels immediate.
    """
    seek = ["-ss", f"{start:.3f}"] if start else []
    limit = ["-t", f"{duration:.3f}"] if duration else []
    command = ["ffmpeg", "-y", "-loglevel", "error", "-nostats", "-progress", "pipe:1",
               *seek, "-i", str(source), *limit,
               "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(wav_path)]
    try:
        proc = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    except FileNotFoundError as exc:
        raise RuntimeError("FFmpeg is niet gevonden. Sluit de app en start opnieuw met start.bat of start.command.") from exc
    assert proc.stdout is not None
    for line in proc.stdout:
        if should_stop:
            try:
                should_stop()
            except BaseException:
                proc.terminate()
                proc.wait(timeout=10)
                wav_path.unlink(missing_ok=True)
                raise
        key, _, value = line.strip().partition("=")
        if key in ("out_time_us", "out_time_ms") and value.lstrip("-").isdigit() and on_progress and duration:
            on_progress(min(1.0, (int(value) / 1_000_000) / duration))
    if proc.wait() != 0:
        stderr = proc.stderr.read() if proc.stderr else ""
        raise RuntimeError("Het geluid kon niet uit de video gehaald worden: " + stderr.strip()[-400:])


def transcribe(source: Path, work_dir: Path, on_progress: Callable[[float], None] | None = None,
               duration: float | None = None, should_stop: Callable[[], None] | None = None,
               start: float = 0.0) -> Transcript:
    """Transcribe `source`, or the `duration` seconds of it that begin at `start`.

    `on_progress(fraction)` is called as segments come in when `duration` is known, and
    `should_stop()` between segments; it may raise to end the work early. Timecodes come
    back relative to the start of the range, matching the clip the user sees.
    """
    wav_path = work_dir / "audio.wav"
    extract_audio(source, wav_path, should_stop,
                  on_progress=(lambda f: on_progress(EXTRACT_SHARE * f)) if on_progress else None,
                  duration=duration, start=start)

    model = get_model()
    if should_stop:
        should_stop()
    vocabulary = load_vocabulary()
    whisper_segments, _info = model.transcribe(
        str(wav_path),
        language=LANGUAGE,
        beam_size=5,
        vad_filter=True,
        word_timestamps=True,
        initial_prompt=initial_prompt() or None,
    )

    words = []
    fallback: list[Segment] = []
    for seg in whisper_segments:
        if should_stop:
            should_stop()
        if on_progress and duration:
            on_progress(min(0.99, EXTRACT_SHARE + (1 - EXTRACT_SHARE) * (seg.end / duration)))
        fallback.append(Segment(start=round(seg.start, 2), end=round(seg.end, 2), text=seg.text.strip()))
        if seg.words:
            words.extend(seg.words)

    segments = chunk_words(words) if words else fallback
    corrections = vocabulary.get("corrections", {})
    for seg in segments:
        seg.text = apply_corrections(seg.text, corrections)
    return Transcript(language=LANGUAGE, segments=[s for s in segments if s.text])


def chunk_words(words) -> list[Segment]:
    """Group whisper words into caption-sized segments."""
    segments: list[Segment] = []
    current: list = []

    def flush() -> None:
        if current:
            text = " ".join(w.word.strip() for w in current)
            segments.append(Segment(start=round(current[0].start, 2), end=round(current[-1].end, 2), text=text))
            current.clear()

    for word in words:
        if current:
            text_len = sum(len(w.word.strip()) + 1 for w in current) + len(word.word.strip())
            duration = word.end - current[0].start
            pause = word.start - current[-1].end
            ends_sentence = current[-1].word.strip().endswith((".", "?", "!"))
            if text_len > MAX_CHARS or duration > MAX_DURATION or pause > PAUSE_SPLIT or (ends_sentence and text_len > 20):
                flush()
        current.append(word)
    flush()
    return segments
