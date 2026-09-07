"""AI clip discovery: transcript windows -> LLM analysis -> ranked, deduplicated ClipCandidates.

This layer only knows what the service contains and where good moments are.
It never renders video; selected candidates go through backend/clips.py into
the existing clip-production pipeline.
"""

import json
import os
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Callable

from pydantic import BaseModel

from .models import ClipCandidate, Segment, TimeRange, Transcript

LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "anthropic")  # anthropic | ollama
LLM_MODEL = os.environ.get("LLM_MODEL")  # defaults per provider below
LLM_EFFORT = os.environ.get("LLM_EFFORT", "high")
LLM_CONCURRENCY = int(os.environ.get("LLM_CONCURRENCY", "3"))
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")

WINDOW_SECONDS = 180.0  # analysis window length (2-5 minutes gives enough context)
WINDOW_OVERLAP = 30.0
MIN_CLIP = 15.0  # hard limits: shorter/longer proposals are dropped
MAX_CLIP = 150.0
PREFERRED = (30.0, 60.0)
SNAP_TOLERANCE = 4.0  # seconds: snap proposed boundaries to the nearest sentence boundary
OVERLAP_DUPLICATE = 0.5  # fraction of the shorter candidate that overlaps -> same moment

ProgressCallback = Callable[[float, str], None]


# --- LLM output schema --------------------------------------------------------


class LlmCandidate(BaseModel):
    start: float
    end: float
    title: str
    summary: str
    reason: str
    confidence: float


class LlmAnalysis(BaseModel):
    candidates: list[LlmCandidate]


SYSTEM_PROMPT = """Je bent redacteur voor de social-media kanalen van een kerk. Je krijgt een fragment van het transcript \
van een Nederlandse kerkdienst, met tijdcodes per zin. Zoek momenten die als zelfstandige korte video (Instagram Reel, \
YouTube Short) werken.

Goede momenten:
- een sterke openingszin, een heldere op zichzelf staande gedachte
- een gedenkwaardige of verrassende uitspraak, een praktisch inzicht
- een emotioneel moment, een vraag gevolgd door een bruikbaar antwoord
- een sterke conclusie, iets dat begrijpelijk is zonder veel context

Vermijd:
- onafgemaakte gedachten, lange aanlopen, herhaling
- verwijzingen naar iets van veel eerder ("zoals ik net zei")
- mededelingen, collecte, agenda, administratieve informatie, liedaankondigingen
- fragmenten waarin de interessante uitspraak pas na een lange opbouw komt

Grenzen:
- start en end zijn tijden in seconden en moeten samenvallen met het begin en het einde van zinnen uit het fragment
- begin nooit midden in een zin en stop niet als de spreker dezelfde gedachte duidelijk nog afmaakt
- richt op 30-60 seconden; 20-90 seconden is acceptabel als de gedachte dat vraagt
- geef per fragment 0 tot 3 kandidaten; een lege lijst is prima als er niets geschikts is
- kandidaten mogen elkaar niet overlappen

Geef per kandidaat: start, end, een korte pakkende Nederlandse titel (max 60 tekens, geen aanhalingstekens), \
een samenvatting van één zin, de reden waarom het als losse clip werkt, en confidence tussen 0 en 1. \
Optimaliseer niet voor "viraal" maar voor heldere, interessante, zelfstandige preekmomenten."""


# --- windows -----------------------------------------------------------------


@dataclass
class Window:
    index: int
    start: float
    end: float
    segments: list[Segment]


def build_windows(segments: list[Segment], length: float = WINDOW_SECONDS, overlap: float = WINDOW_OVERLAP) -> list[Window]:
    """Split timestamped segments into overlapping analysis windows (not clip boundaries)."""
    segments = [s for s in sorted(segments, key=lambda s: s.start) if s.text.strip()]
    windows: list[Window] = []
    i = 0
    while i < len(segments):
        t0 = segments[i].start
        j = i
        while j < len(segments) and (segments[j].start < t0 + length or j == i):
            j += 1
        chunk = segments[i:j]
        windows.append(Window(len(windows), chunk[0].start, chunk[-1].end, chunk))
        if j >= len(segments):
            break
        # Next window starts `overlap` seconds before this one ends, but always makes progress.
        next_i = i + 1
        for k in range(i + 1, j):
            if segments[k].start >= chunk[-1].end - overlap:
                next_i = k
                break
        else:
            next_i = j
        i = max(next_i, i + 1)
    return windows


def format_window(window: Window) -> str:
    lines = [f"[{s.start:.1f}-{s.end:.1f}] {s.text.strip()}" for s in window.segments]
    return "\n".join(lines)


# --- LLM call ----------------------------------------------------------------


def analyze_window(window: Window) -> list[LlmCandidate]:
    user = (
        f"Fragment {window.index + 1}, van {window.start:.1f}s tot {window.end:.1f}s in de dienst.\n\n"
        f"{format_window(window)}"
    )
    if LLM_PROVIDER == "ollama":
        return _ollama(user).candidates
    return _anthropic(user).candidates


def _anthropic(user: str) -> LlmAnalysis:
    import anthropic

    client = anthropic.Anthropic()
    response = client.messages.parse(
        model=LLM_MODEL or "claude-opus-5",
        max_tokens=16000,
        system=SYSTEM_PROMPT,
        output_config={"effort": LLM_EFFORT},
        messages=[{"role": "user", "content": user}],
        output_format=LlmAnalysis,
    )
    if response.stop_reason == "refusal" or response.parsed_output is None:
        return LlmAnalysis(candidates=[])
    return response.parsed_output


def _ollama(user: str) -> LlmAnalysis:
    body = json.dumps({
        "model": LLM_MODEL or "llama3.1",
        "stream": False,
        "format": LlmAnalysis.model_json_schema(),
        "messages": [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user}],
    }).encode("utf-8")
    req = urllib.request.Request(f"{OLLAMA_URL}/api/chat", data=body, headers={"content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=600) as res:
        data = json.loads(res.read().decode("utf-8"))
    return LlmAnalysis.model_validate_json(data["message"]["content"])


# --- post-processing -----------------------------------------------------------


def snap(candidate: LlmCandidate, window: Window) -> tuple[float, float]:
    """Move boundaries onto the nearest sentence start/end so clips begin and end naturally."""
    starts = [s.start for s in window.segments]
    ends = [s.end for s in window.segments]
    start = min(starts, key=lambda t: abs(t - candidate.start))
    end = min(ends, key=lambda t: abs(t - candidate.end))
    if abs(start - candidate.start) > SNAP_TOLERANCE:
        start = candidate.start
    if abs(end - candidate.end) > SNAP_TOLERANCE:
        end = candidate.end
    return round(max(window.start, start), 2), round(min(window.end, end), 2)


def score(candidate: LlmCandidate, duration: float) -> float:
    s = max(0.0, min(1.0, candidate.confidence))
    if PREFERRED[0] <= duration <= PREFERRED[1]:
        s += 0.05
    elif duration < 20 or duration > 90:
        s -= 0.15
    return round(s, 4)


def overlap_fraction(a: ClipCandidate, b: ClipCandidate) -> float:
    inter = min(a.end, b.end) - max(a.start, b.start)
    if inter <= 0:
        return 0.0
    return inter / max(1e-6, min(a.end - a.start, b.end - b.start))


def dedupe_and_rank(raw: list[ClipCandidate]) -> list[ClipCandidate]:
    """Keep one primary candidate per moment; overlapping proposals become alternate boundaries."""
    kept: list[ClipCandidate] = []
    for cand in sorted(raw, key=lambda c: c.score, reverse=True):
        twin = next((k for k in kept if overlap_fraction(k, cand) >= OVERLAP_DUPLICATE), None)
        if twin is None:
            kept.append(cand)
        elif (cand.start, cand.end) != (twin.start, twin.end):
            twin.alternateBoundaries.append(TimeRange(start=cand.start, end=cand.end))
    for n, cand in enumerate(kept, start=1):
        cand.id = f"candidate-{n:02d}"
    return kept


def discover(transcript: Transcript, on_progress: ProgressCallback | None = None) -> list[ClipCandidate]:
    windows = build_windows(transcript.segments)
    total = len(windows)
    if total == 0:
        return []
    raw: list[ClipCandidate] = []
    done = 0

    def work(window: Window) -> list[ClipCandidate]:
        out = []
        for c in analyze_window(window):
            start, end = snap(c, window)
            duration = end - start
            if duration < MIN_CLIP or duration > MAX_CLIP or not c.title.strip():
                continue
            out.append(ClipCandidate(
                id="", start=start, end=end, title=c.title.strip()[:80], summary=c.summary.strip(),
                reason=c.reason.strip(), confidence=round(c.confidence, 3), score=score(c, duration),
            ))
        return out

    if on_progress:
        on_progress(0.0, f"Analyzing transcript · Section 1 of {total}")
    with ThreadPoolExecutor(max_workers=max(1, LLM_CONCURRENCY)) as pool:
        for result in pool.map(work, windows):
            raw.extend(result)
            done += 1
            if on_progress:
                on_progress(done / total, f"Analyzing transcript · Section {min(done + 1, total)} of {total}")
    return dedupe_and_rank(raw)
