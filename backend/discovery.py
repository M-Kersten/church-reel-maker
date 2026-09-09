"""AI clip discovery: transcript windows -> LLM analysis -> ranked, deduplicated ClipCandidates.

This layer only knows what the service contains and where good moments are.
It never renders video; selected candidates go through backend/clips.py into
the existing clip-production pipeline.
"""

import hashlib
import json
import os
import random
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from pydantic import BaseModel

from .jobs import Cancelled
from . import structure
from .models import ClipCandidate, Segment, TimeRange, Transcript, write_atomic
from .structure import Block

LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "anthropic")  # anthropic | ollama
LLM_MODEL = os.environ.get("LLM_MODEL")  # defaults per provider below
LLM_EFFORT = os.environ.get("LLM_EFFORT", "high")
LLM_CONCURRENCY = int(os.environ.get("LLM_CONCURRENCY", "3"))
LLM_ATTEMPTS = int(os.environ.get("LLM_ATTEMPTS", "3"))  # tries per window before giving up on it
LLM_TIMEOUT = float(os.environ.get("LLM_TIMEOUT", "180"))
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


class Verdict(BaseModel):
    """The second pass's judgement on one proposal."""

    id: str
    keep: bool
    rank: int  # 1 is the best of the service; 0 for a moment that is not shortlisted
    verdict: str  # one line: why it was picked, or why another moment beat it


class LlmShortlist(BaseModel):
    verdicts: list[Verdict]


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


SHORTLIST_PROMPT = """Je bent eindredacteur voor de social-media kanalen van een kerk. Een collega \
heeft de hele dienst doorgelezen in losse stukken en per stuk voorstellen gedaan. Die collega zag steeds \
maar een paar minuten tegelijk en kon de voorstellen dus niet met elkaar vergelijken. Dat is jouw werk.

Je krijgt de opbouw van de dienst en alle voorgestelde momenten met hun tijd, titel, samenvatting, \
reden en een stuk van het transcript. Kies welke momenten deze week daadwerkelijk gepost worden.

Kies op:
- staat het op zichzelf, zonder dat je de rest van de dienst gehoord hebt
- is het de moeite waard voor iemand die de kerk niet kent
- zegt het iets anders dan de andere gekozen momenten; twee keer dezelfde gedachte is een keer te veel
- komt het uit de kern van de preek, niet uit een aankondiging of een terzijde

Regels:
- kies er 5 tot 10, minder als de dienst niet meer te bieden heeft; liever vier goede dan acht matige
- rank 1 is het sterkste moment van de dienst, daarna aflopend
- geef ieder voorstel een verdict van een zin, ook de afvallers: waarom het het niet werd
- verzin geen momenten en verander geen tijden; je kiest alleen uit wat je krijgt"""


# --- windows -----------------------------------------------------------------


@dataclass
class Window:
    index: int
    start: float
    end: float
    segments: list[Segment]
    part: str = "preek"  # which part of the service this window falls in


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


def sermon_windows(segments: list[Segment], duration: float | None = None) -> tuple[list[Window], list[Block], int]:
    """The windows worth sending, each told which part of the service it sits in.

    Roughly half a service is welcome, songs, notices and blessing. Sending those costs
    money and puts moments in the list that nobody would post, so they are dropped here
    rather than argued away in the prompt. Returns (windows, the shape of the service,
    how many windows were left out).
    """
    shape = structure.blocks(segments, duration)
    everything = build_windows(segments)
    keeping = []
    for window in everything:
        if not structure.worth_analysing(shape, window.start, window.end):
            continue
        window.part = structure.PART_LABEL[structure.part_at(shape, (window.start + window.end) / 2)]
        window.index = len(keeping)
        keeping.append(window)
    return keeping, shape, len(everything) - len(keeping)


# --- LLM call ----------------------------------------------------------------


class Retryable(RuntimeError):
    """A failure that is worth trying again: rate limit, server error, network hiccup."""


def window_file(cache_dir: Path, window: Window) -> Path:
    """Where one window's answer is kept.

    The name carries the text and the settings that produced the answer, so a
    re-transcription, a different model or an edited prompt all miss the cache instead of
    handing back something that no longer matches.
    """
    recipe = f"{format_window(window)}\n{LLM_PROVIDER}\n{LLM_MODEL}\n{SYSTEM_PROMPT}"
    digest = hashlib.sha1(recipe.encode("utf-8")).hexdigest()[:16]
    return cache_dir / f"{window.index:03d}-{digest}.json"


def cached_window(cache_dir: Path | None, window: Window) -> list[LlmCandidate] | None:
    if cache_dir is None:
        return None
    path = window_file(cache_dir, window)
    if not path.is_file():
        return None
    try:
        return [LlmCandidate(**c) for c in json.loads(path.read_text(encoding="utf-8"))]
    except Exception:  # noqa: BLE001  a damaged answer is simply asked again
        return None


def remember_window(cache_dir: Path | None, window: Window, found: list[LlmCandidate]) -> None:
    if cache_dir is None:
        return
    cache_dir.mkdir(parents=True, exist_ok=True)
    write_atomic(window_file(cache_dir, window), json.dumps([c.model_dump() for c in found]))


def analyze_window(window: Window) -> list[LlmCandidate]:
    user = (
        f"Fragment {window.index + 1}, van {window.start:.1f}s tot {window.end:.1f}s in de dienst. "
        f"Dit deel van de dienst is: {window.part}.\n\n"
        f"{format_window(window)}"
    )
    return ask(user, SYSTEM_PROMPT, LlmAnalysis).candidates


def ask(user: str, system: str, schema):
    """One call to the model, retried on the failures that are worth retrying."""
    last: Exception | None = None
    for attempt in range(LLM_ATTEMPTS):
        try:
            return _ollama(user, system, schema) if LLM_PROVIDER == "ollama" else _anthropic(user, system, schema)
        except Retryable as exc:
            last = exc
            if attempt < LLM_ATTEMPTS - 1:
                # Wait a bit longer every time, with a little spread so parallel windows do not sync up.
                time.sleep((2 ** attempt) * 3 + random.uniform(0, 1.5))
        except Exception:  # noqa: BLE001  a bad answer for one window should not stop the rest
            raise
    raise last if last else RuntimeError("Onbekende fout bij het analyseren")


NO_KEY_MESSAGE = ("Er is geen Claude API-sleutel ingesteld. Zet ANTHROPIC_API_KEY=... in config.env en start de app "
                  "opnieuw, of kies LLM_PROVIDER=ollama voor een lokaal model.")


def check_provider() -> None:
    """Fail early with a readable message instead of after the first window."""
    if LLM_PROVIDER == "ollama":
        return
    try:
        import anthropic  # noqa: F401
    except ImportError as exc:
        raise RuntimeError("Het onderdeel 'anthropic' ontbreekt. Sluit de app en start opnieuw met start.bat of "
                           "start.command; de ontbrekende onderdelen worden dan geïnstalleerd.") from exc
    if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
        raise RuntimeError(NO_KEY_MESSAGE)


def _anthropic(user: str, system: str = SYSTEM_PROMPT, schema=LlmAnalysis):
    import anthropic

    client = anthropic.Anthropic(timeout=LLM_TIMEOUT, max_retries=0)  # retries are handled per window
    try:
        response = _anthropic_request(client, user, system, schema)
    except anthropic.AuthenticationError as exc:
        raise RuntimeError("De Claude API-sleutel wordt niet geaccepteerd. Controleer ANTHROPIC_API_KEY in config.env.") from exc
    except anthropic.RateLimitError as exc:
        raise Retryable("De Claude API is even vol (limiet bereikt).") from exc
    except anthropic.APIStatusError as exc:
        if exc.status_code >= 500:
            raise Retryable(f"De Claude API gaf een serverfout ({exc.status_code}).") from exc
        raise RuntimeError(f"De Claude API gaf een fout ({exc.status_code}): {exc.message}") from exc
    except anthropic.APIConnectionError as exc:
        raise Retryable("Geen verbinding met de Claude API.") from exc
    if response.stop_reason == "refusal" or response.parsed_output is None:
        return schema()
    return response.parsed_output


def _anthropic_request(client, user: str, system: str, schema):
    return client.messages.parse(
        model=LLM_MODEL or "claude-opus-5",
        max_tokens=16000,
        system=system,
        output_config={"effort": LLM_EFFORT},
        messages=[{"role": "user", "content": user}],
        output_format=schema,
    )


def _ollama(user: str, system: str = SYSTEM_PROMPT, schema=LlmAnalysis):
    body = json.dumps({
        "model": LLM_MODEL or "llama3.1",
        "stream": False,
        "format": schema.model_json_schema(),
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
    }).encode("utf-8")
    req = urllib.request.Request(f"{OLLAMA_URL}/api/chat", data=body, headers={"content-type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=LLM_TIMEOUT * 4) as res:
            data = json.loads(res.read().decode("utf-8"))
    except OSError as exc:
        raise Retryable(f"Ollama antwoordde niet op {OLLAMA_URL}.") from exc
    return schema.model_validate_json(data["message"]["content"])


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


# --- the second pass: choosing between everything that was found -----------------

SHORTLIST_MIN = 5  # below this many proposals there is nothing to choose between
EXCERPT_CHARS = 400  # how much of each moment the editor gets to read


def excerpt(segments: list[Segment], start: float, end: float, limit: int = EXCERPT_CHARS) -> str:
    """What is actually said during a proposed moment, trimmed to something readable."""
    said = " ".join(s.text.strip() for s in segments if s.end > start and s.start < end)
    return said if len(said) <= limit else said[:limit - 1].rsplit(" ", 1)[0] + "…"


def shortlist_request(found: list[ClipCandidate], segments: list[Segment], shape: list[Block]) -> str:
    """Everything the editor needs to weigh the moments against each other."""
    lines = [f"De dienst duurt {int((segments[-1].end if segments else 0) // 60)} minuten en is opgebouwd als: "
             f"{structure.summary(shape)}.", "", f"Er zijn {len(found)} momenten voorgesteld:", ""]
    for candidate in found:
        lines.append(
            f"[{candidate.id}] {candidate.start:.0f}-{candidate.end:.0f}s "
            f"({candidate.end - candidate.start:.0f} sec, {candidate.part or 'preek'})\n"
            f"  titel: {candidate.title}\n"
            f"  samenvatting: {candidate.summary}\n"
            f"  reden van de collega: {candidate.reason}\n"
            f"  transcript: {excerpt(segments, candidate.start, candidate.end)}\n"
        )
    return "\n".join(lines)


def shortlist(found: list[ClipCandidate], segments: list[Segment], shape: list[Block]) -> list[ClipCandidate]:
    """Weigh every proposal against all the others and rank the ones worth posting.

    The first pass reads a few minutes at a time and scores its own confidence, which is
    not comparable between windows: the best moment of a dull three minutes gets the same
    0.9 as the best moment of the service. This pass sees them all at once, so the order
    means something. Everything is kept; the ones that lose are marked, not thrown away.
    """
    if len(found) < SHORTLIST_MIN:
        for candidate in found:
            candidate.shortlisted = True
        return found
    answer = ask(shortlist_request(found, segments, shape), SHORTLIST_PROMPT, LlmShortlist)
    judged = {v.id: v for v in answer.verdicts}
    if not any(v.keep for v in judged.values()):
        return found  # an answer that keeps nothing is not an answer; leave the order alone
    for candidate in found:
        verdict = judged.get(candidate.id)
        candidate.shortlisted = bool(verdict and verdict.keep)
        candidate.verdict = verdict.verdict.strip() if verdict else ""
        candidate.selected = candidate.shortlisted
    # Rank decides the order among the chosen; the rest keep their own order behind them.
    order = {v.id: v.rank if v.rank > 0 else 999 for v in answer.verdicts}
    found.sort(key=lambda c: (not c.shortlisted, order.get(c.id, 999), -c.score))
    return found


# Rough list price per million tokens (input, output), for the cost estimate shown before analysing.
PRICES = {"claude-opus-5": (5.0, 25.0), "claude-sonnet-5": (2.0, 10.0), "claude-haiku-4-5": (1.0, 5.0)}


def estimate(transcript: Transcript, duration: float | None = None) -> dict:
    """What a run would send and cost, so the interface can say so before spending anything.

    Only the windows that will actually be sent are counted, plus the one call at the end
    that weighs the proposals against each other.
    """
    windows, _shape, skipped = sermon_windows(transcript.segments, duration)
    characters = sum(len(w.text) + 16 for window in windows for w in window.segments)
    input_tokens = int(characters / 3.5) + len(windows) * 700  # transcript plus the instructions per window
    output_tokens = len(windows) * 500
    # The second pass reads a summary of every proposal once, and answers briefly.
    if windows:
        proposals = len(windows)  # roughly one surviving moment per window
        input_tokens += proposals * 220 + 500
        output_tokens += proposals * 60
    model = LLM_MODEL or ("llama3.1" if LLM_PROVIDER == "ollama" else "claude-opus-5")
    if LLM_PROVIDER == "ollama":
        cost = 0.0
    else:
        price_in, price_out = PRICES.get(model, PRICES["claude-opus-5"])
        cost = round(input_tokens * price_in / 1e6 + output_tokens * price_out / 1e6, 2)
    return {"provider": LLM_PROVIDER, "model": model, "windows": len(windows), "skipped": skipped,
            "tokens": input_tokens + output_tokens, "costUsd": cost}


class Result(BaseModel):
    """What one analysis run produced, including the windows that would not cooperate."""

    candidates: list[ClipCandidate] = []
    windows: int = 0  # windows actually sent to the model
    skipped: int = 0  # windows left out because they were not preaching
    failed: int = 0
    shortlisted: int = 0  # how many the second pass judged worth posting
    shape: list[dict] = []  # the parts of the service, for the timeline
    warning: str | None = None


def discover(transcript: Transcript, on_progress: ProgressCallback | None = None,
             should_stop: Callable[[], None] | None = None, cache_dir: Path | None = None,
             duration: float | None = None) -> Result:
    """Read the whole transcript and come back with ranked moments.

    Two passes. The first reads the service a few minutes at a time and proposes moments;
    the parts that are not preaching are never sent. The second reads all the proposals
    together and decides which of them this service is actually worth posting, which is
    something no single window could know.

    Windows that were already answered are read from `cache_dir` instead of being sent
    again, so a run that was interrupted or that lost a few windows to a rate limit picks
    up where it left off instead of paying for the whole service twice.
    """
    check_provider()
    windows, shape, skipped = sermon_windows(transcript.segments, duration)
    total = len(windows)
    if total == 0:
        return Result(shape=[b.as_dict() for b in shape], skipped=skipped)
    raw: list[ClipCandidate] = []
    failures: list[str] = []
    done = 0

    def work(window: Window) -> list[ClipCandidate]:
        if should_stop:
            should_stop()
        found = cached_window(cache_dir, window)
        if found is None:
            found = analyze_window(window)
            remember_window(cache_dir, window, found)
        out = []
        for c in found:
            start, end = snap(c, window)
            duration = end - start
            if duration < MIN_CLIP or duration > MAX_CLIP or not c.title.strip():
                continue
            out.append(ClipCandidate(
                id="", start=start, end=end, title=c.title.strip()[:80], summary=c.summary.strip(),
                reason=c.reason.strip(), confidence=round(c.confidence, 3), score=score(c, duration),
                part=window.part,
            ))
        return out

    def guarded(window: Window) -> list[ClipCandidate]:
        """One difficult window must not throw away the work done on all the others."""
        try:
            return work(window)
        except Cancelled:
            raise
        except Exception as exc:  # noqa: BLE001
            failures.append(str(exc))
            return []

    if on_progress:
        on_progress(0.0, f"Tekst wordt doorgelezen · deel 1 van {total}")
    with ThreadPoolExecutor(max_workers=max(1, LLM_CONCURRENCY)) as pool:
        for result in pool.map(guarded, windows):
            raw.extend(result)
            done += 1
            if on_progress:
                extra = f" · {len(failures)} niet gelukt" if failures else ""
                on_progress(done / total, f"Tekst wordt doorgelezen · deel {min(done + 1, total)} van {total}{extra}")

    if failures and len(failures) == total:
        raise RuntimeError("Geen enkel deel van de tekst kon geanalyseerd worden. " + failures[0])
    warning = None
    if failures:
        warning = (f"{len(failures)} van de {total} stukken tekst konden niet geanalyseerd worden, de rest wel. "
                   f"Reden: {failures[0]} Je kunt opnieuw zoeken om ze alsnog te proberen.")

    candidates = dedupe_and_rank(raw)
    chosen = 0
    if candidates:
        if on_progress:
            on_progress(0.97, "De gevonden momenten worden met elkaar vergeleken")
        if should_stop:
            should_stop()
        try:
            candidates = shortlist(candidates, transcript.segments, shape)
            chosen = sum(1 for c in candidates if c.shortlisted)
        except Cancelled:
            raise
        except Exception as exc:  # noqa: BLE001  the moments are worth having even unranked
            print(f"[analyse] kiezen mislukt, de volgorde van de eerste ronde blijft staan: {exc}")
            warning = (warning + " " if warning else "") + (
                "De momenten konden niet met elkaar vergeleken worden, dus de volgorde is die van de "
                "eerste ronde. Je kunt opnieuw zoeken om dat alsnog te proberen.")
    return Result(candidates=candidates, windows=total, failed=len(failures), warning=warning,
                  shape=[b.as_dict() for b in shape], skipped=skipped, shortlisted=chosen)
