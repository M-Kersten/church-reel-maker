"""Dutch speech-to-text with faster-whisper."""

import os
import subprocess
from pathlib import Path
from typing import Callable

from .models import Segment, Transcript

LANGUAGE = "nl"
MODEL_SIZE = os.environ.get("WHISPER_MODEL", "small")
DEVICE = os.environ.get("WHISPER_DEVICE", "cpu")
COMPUTE_TYPE = os.environ.get("WHISPER_COMPUTE_TYPE", "int8" if DEVICE == "cpu" else "float16")

# Caption chunking: subtitles for reels read best as short phrases.
MAX_CHARS = 60  # roughly two lines of subtitle text
MAX_DURATION = 6.0  # seconds
PAUSE_SPLIT = 0.7  # a pause longer than this starts a new segment

_model = None


def get_model():
    global _model
    if _model is None:
        from faster_whisper import WhisperModel

        _model = WhisperModel(MODEL_SIZE, device=DEVICE, compute_type=COMPUTE_TYPE)
    return _model


def extract_audio(source: Path, wav_path: Path) -> None:
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", str(source), "-vn",
         "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(wav_path)],
        check=True,
    )


def transcribe(source: Path, work_dir: Path, on_progress: Callable[[float], None] | None = None,
               duration: float | None = None) -> Transcript:
    """Transcribe `source`. `on_progress(fraction)` is called as segments come in when `duration` is known."""
    wav_path = work_dir / "audio.wav"
    extract_audio(source, wav_path)

    model = get_model()
    whisper_segments, _info = model.transcribe(
        str(wav_path),
        language=LANGUAGE,
        beam_size=5,
        vad_filter=True,
        word_timestamps=True,
    )

    words = []
    fallback: list[Segment] = []
    for seg in whisper_segments:
        if on_progress and duration:
            on_progress(min(0.99, seg.end / duration))
        fallback.append(Segment(start=round(seg.start, 2), end=round(seg.end, 2), text=seg.text.strip()))
        if seg.words:
            words.extend(seg.words)

    segments = chunk_words(words) if words else fallback
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
