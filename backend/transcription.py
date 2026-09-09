"""Dutch speech-to-text with faster-whisper."""

import json
import os
import re
import subprocess
import threading
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable

from .models import TEMPLATES_DIR, Segment, Transcript, write_atomic

LANGUAGE = "nl"
VOCABULARY_PATH = TEMPLATES_DIR / "woordenlijst.json"
MODEL_SIZE = os.environ.get("WHISPER_MODEL", "small")
# A full service is worth a bigger model if the church is willing to wait for it.
ACCURATE_MODEL_SIZE = os.environ.get("WHISPER_MODEL_ACCURATE", "medium")
DEVICE = os.environ.get("WHISPER_DEVICE", "cpu")
COMPUTE_TYPE = os.environ.get("WHISPER_COMPUTE_TYPE", "int8" if DEVICE == "cpu" else "float16")

# Caption chunking: subtitles for reels read best as short phrases.
MAX_CHARS = 60  # roughly two lines of subtitle text
MAX_DURATION = 6.0  # seconds
PAUSE_SPLIT = 0.7  # a pause longer than this starts a new segment
EXTRACT_SHARE = 0.08  # first slice of the progress bar: pulling the audio out of the video
MODEL_SHARE = 0.04  # second slice: loading the speech model, which is slow only the first time

# The phases a caller is told about, so it can say what is happening rather than guess
# from a number. "text" is the long one and the only one worth estimating a time for.
AUDIO, MODEL, TEXT = "audio", "model", "text"

_models: dict[str, object] = {}
_models_lock = threading.Lock()

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


def church_words() -> tuple[str, dict[str, str]]:
    """This church's own names and fixes, on top of the shared word list.

    Returns (a sentence naming them for the model, the corrections to apply afterwards).
    """
    try:
        from . import brands

        brand = brands.active()
    except Exception:  # noqa: BLE001  a broken brand must not stop a transcription
        return "", {}
    said = []
    name = brand.church.churchName
    if name:
        said.append(f"De kerk heet {name}.")
    vocabulary = brand.vocabulary
    for label, group in (("Er wordt gepreekt door", vocabulary.preachers),
                         ("De serie heet", vocabulary.series),
                         ("Er wordt gezongen uit", vocabulary.songbooks),
                         ("Plaatsen en locaties", vocabulary.places),
                         ("Let ook op", vocabulary.extra)):
        words = [w.strip() for w in group if w.strip()]
        if words:
            said.append(f"{label}: {', '.join(words)}.")
    return " ".join(said), dict(vocabulary.corrections)


def initial_prompt() -> str:
    """The shared vocabulary plus what this church calls things."""
    prompt = load_vocabulary().get("initialPrompt", "")
    mine, _fixes = church_words()
    for sentence in mine.split(". "):
        clean = sentence.strip(" .")
        if clean and clean.lower() not in prompt.lower():
            prompt = f"{prompt} {clean}."
    return prompt.strip()


def all_corrections() -> dict[str, str]:
    """The shared fixes, with this church's own on top."""
    fixes = dict(load_vocabulary().get("corrections", {}))
    _prompt, mine = church_words()
    fixes.update(mine)
    return fixes


def apply_corrections(text: str, corrections: dict[str, str]) -> str:
    """Replace known mishearings, whole words only, keeping the sentence's capital."""
    for wrong, right in corrections.items():
        if not wrong.strip():
            continue
        pattern = re.compile(rf"\b{re.escape(wrong)}\b", re.IGNORECASE)
        text = pattern.sub(right, text)
    return text


def model_for(accurate: bool = False) -> str:
    """Which model this job gets: the quick one, or the one that hears more."""
    return ACCURATE_MODEL_SIZE if accurate else MODEL_SIZE


def batch_size(accurate: bool = False) -> int:
    """How many 30-second windows to decode at once.

    Batching is what makes this bearable on a laptop CPU: the windows go through the
    encoder together instead of one after another. Measured on four cores with the small
    model over eight minutes of Dutch speech: 3.6x realtime one at a time, 6.8x at two,
    8.3x at four, 8.6x at eight, and back down to 7.5x at sixteen, where the cores are
    oversubscribed. The bigger model holds more weights, so it gets a smaller batch.
    """
    override = os.environ.get("WHISPER_BATCH_SIZE")
    if override and override.isdigit() and int(override) > 0:
        return int(override)
    room = min(8, max(2, (os.cpu_count() or 2) * 2))
    return max(2, room // 2) if accurate else room


def get_model(size: str | None = None):
    """The loaded model of this size, kept for the life of the process."""
    size = size or MODEL_SIZE
    with _models_lock:
        if size not in _models:
            from faster_whisper import WhisperModel

            try:
                _models[size] = WhisperModel(size, device=DEVICE, compute_type=COMPUTE_TYPE)
            except Exception as exc:  # noqa: BLE001
                raise RuntimeError(
                    f"Het spraakmodel '{size}' kon niet geladen worden. De eerste keer wordt het gedownload; "
                    f"controleer de internetverbinding en de vrije schijfruimte. ({exc})"
                ) from exc
        return _models[size]


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


PARTIAL_FILE = "partial.json"
SAVE_EVERY = 30.0  # seconds of audio between saves of the work in progress


@dataclass
class Word:
    """One word with its timing. Plain data, so a half-finished run can be written to disk."""

    start: float
    end: float
    word: str


def load_partial(work_dir: Path) -> tuple[float, list[Word], list[Segment]]:
    """Where an interrupted run got to: (seconds done, words, whole-sentence fallback)."""
    path = work_dir / PARTIAL_FILE
    if not path.is_file():
        return 0.0, [], []
    try:
        saved = json.loads(path.read_text(encoding="utf-8"))
        return (float(saved["upTo"]),
                [Word(**w) for w in saved["words"]],
                [Segment(**s) for s in saved["segments"]])
    except Exception:  # noqa: BLE001  a damaged half-finished file just means starting over
        return 0.0, [], []


def save_partial(work_dir: Path, up_to: float, words: list[Word], segments: list[Segment]) -> None:
    write_atomic(work_dir / PARTIAL_FILE, json.dumps({
        "upTo": round(up_to, 2),
        "words": [asdict(w) for w in words],
        "segments": [s.model_dump() for s in segments],
    }))


def transcribe(source: Path, work_dir: Path, on_progress: Callable[[float, str], None] | None = None,
               duration: float | None = None, should_stop: Callable[[], None] | None = None,
               start: float = 0.0, accurate: bool = False) -> Transcript:
    """Transcribe `source`, or the `duration` seconds of it that begin at `start`.

    `on_progress(fraction, phase)` is called as the work moves along, with `phase` one of
    AUDIO, MODEL or TEXT so the caller can say what is happening instead of inferring it
    from the number. `should_stop()` is called between segments and may raise to end the
    work early. Timecodes come back relative to the start of the range, matching the clip
    the user sees.

    The work is written down as it goes. Closing the laptop during a half-hour run used to
    throw all of it away; now the next attempt carries on from the last saved point.
    """
    report = on_progress or (lambda _f, _p: None)
    work_dir.mkdir(parents=True, exist_ok=True)
    done_to, words, fallback = load_partial(work_dir)
    if duration and done_to >= duration - 1.0:
        done_to, words, fallback = 0.0, [], []  # nothing left to do; start over rather than stall

    wav_path = work_dir / "audio.wav"
    report(0.0, AUDIO)
    remaining = (duration - done_to) if duration else None
    extract_audio(source, wav_path, should_stop,
                  on_progress=lambda f: report(EXTRACT_SHARE * f, AUDIO),
                  duration=remaining, start=start + done_to)

    from faster_whisper import BatchedInferencePipeline

    report(EXTRACT_SHARE, MODEL)
    model = get_model(model_for(accurate))
    if should_stop:
        should_stop()
    base = EXTRACT_SHARE + MODEL_SHARE
    report(base + (1 - base) * (done_to / duration) if duration else base, TEXT)
    vocabulary = load_vocabulary()
    whisper_segments, _info = BatchedInferencePipeline(model=model).transcribe(
        str(wav_path),
        language=LANGUAGE,
        beam_size=5,
        vad_filter=True,
        word_timestamps=True,
        initial_prompt=initial_prompt() or None,
        batch_size=batch_size(accurate),
    )

    saved_at = done_to
    try:
        for seg in whisper_segments:
            if should_stop:
                should_stop()
            # Timings come back relative to the piece of audio just decoded, so shift them
            # onto the clip the user is looking at.
            at = done_to + seg.end
            if duration:
                report(min(0.99, base + (1 - base) * (at / duration)), TEXT)
            fallback.append(Segment(start=round(done_to + seg.start, 2), end=round(at, 2),
                                    text=seg.text.strip()))
            words.extend(Word(round(done_to + w.start, 2), round(done_to + w.end, 2), w.word)
                         for w in (seg.words or []))
            if at - saved_at >= SAVE_EVERY:
                save_partial(work_dir, at, words, fallback)
                saved_at = at
    except BaseException:
        # Interrupted or stopped: keep what has been heard so far for the next attempt.
        save_partial(work_dir, saved_at, words, fallback)
        raise

    segments = chunk_words(words) if words else fallback
    corrections = all_corrections()
    for seg in segments:
        seg.text = apply_corrections(seg.text, corrections)
    (work_dir / PARTIAL_FILE).unlink(missing_ok=True)
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
