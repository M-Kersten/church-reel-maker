"""Where you are in the service, from the transcript alone.

Roughly half of a Sunday morning is not sermon: welcome, songs, readings, prayer, notices,
blessing. Sending all of it to the model costs money and fills the suggestion list with
moments nobody would post, and asking the model to ignore notices in a prompt only half
works. This labels the transcript first, so the notices are never sent at all and the
model is told which part of the service it is looking at.

No model is involved. The labels come from the words a Dutch service actually uses, plus
where in the hour a part tends to fall and how densely people speak during it.
"""

import re
from dataclasses import dataclass
from typing import Literal

from .models import Segment

Part = Literal["welkom", "zang", "lezing", "gebed", "preek", "mededelingen", "zegen"]

# What each part is called when the interface or a prompt has to name it.
PART_LABEL: dict[Part, str] = {
    "welkom": "welkom en opening",
    "zang": "zang en aanbidding",
    "lezing": "Bijbellezing",
    "gebed": "gebed",
    "preek": "preek",
    "mededelingen": "mededelingen",
    "zegen": "zegen en afsluiting",
}

# Parts a clip is never cut from. The reading and the prayer stay in: a church does
# sometimes post those, and a reading usually runs straight into the preaching anyway.
SKIP: set[Part] = {"welkom", "mededelingen", "zang", "zegen"}

BIBLE_BOOKS = (
    "genesis|exodus|leviticus|numeri|deuteronomium|jozua|richteren|ruth|samu[eë]l|koningen|kronieken|"
    "ezra|nehemia|ester|job|psalm(?:en)?|spreuken|prediker|hooglied|jesaja|jeremia|klaagliederen|"
    "ezechi[eë]l|dani[eë]l|hosea|jo[eë]l|amos|obadja|jona|micha|nahum|habakuk|sefanja|haggai|zacharia|"
    "maleachi|matthe[uü]s|matte[uü]s|marcus|markus|lucas|lukas|johannes|handelingen|romeinen|"
    "korint[hi][eë]rs|galaten|efezi[eë]rs|filippenzen|kolossenzen|tessalonicenzen|timote[uü]s|titus|"
    "filemon|hebree[eë]n|jakobus|petrus|judas|openbaring"
)

# Phrases that give a part away. Weighted, because "amen" says less than "de collecte".
CUES: dict[Part, list[tuple[str, float]]] = {
    "welkom": [
        (r"\b(goedemorgen|goedemiddag|goedenavond)\b", 3.0),
        (r"\bwelkom\b", 2.5),
        (r"\bfijn dat (je|jullie|u) er (is|bent|zijn)\b", 3.0),
        (r"\bhartelijk welkom\b", 3.0),
        (r"\bwe (beginnen|openen) (deze|de) dienst\b", 3.0),
    ],
    "zang": [
        (r"\b(zingen|zingt|gezongen|meezingen)\b", 2.0),
        (r"\b(lied|liederen|psalm|gezang|opwekking|loflied|refrein|couplet)\b", 2.0),
        (r"\bstaan (we|jullie) op\b", 1.5),
        (r"\bwe zingen (nu|samen|straks)?\b", 3.0),
        (r"\bde band\b|\bhet orgel\b", 1.5),
    ],
    "lezing": [
        (rf"\b(?:{BIBLE_BOOKS})\b", 2.0),
        (r"\b(?:hoofdstuk|vers)\s+\w+", 2.0),
        (r"\b(de|onze) (bijbellezing|schriftlezing|lezing)\b", 3.5),
        (r"\bwe lezen (uit|vandaag|samen)\b", 3.5),
        (r"\bhet woord van (de|onze) heer\b", 2.5),
    ],
    "gebed": [
        (r"\b(laten we|laat ons) bidden\b", 3.5),
        (r"\b(gebed|voorbede|bidden we|wij bidden)\b", 2.0),
        (r"\b(hemelse vader|onze vader)\b", 2.5),
        (r"\bamen\b", 1.0),
        (r"\bheer, (ontferm|wij)\b", 2.5),
    ],
    "preek": [
        (r"\b(vandaag wil ik|ik wil (het )?(met (jullie|u) )?(hebben|praten) over)\b", 3.5),
        (r"\b(misschien herken je|stel je voor|denk (eens|even) aan)\b", 2.0),
        (r"\b(wat betekent dat|wat als|de vraag is)\b", 1.5),
        (r"\b(ik wil afsluiten|tot slot|samengevat)\b", 1.5),
    ],
    "mededelingen": [
        (r"\b(mededeling|mededelingen|agenda|aankondiging)\b", 3.5),
        (r"\bde collecte\b|\bcollecteren\b|\bgeven (we|jullie) voor\b", 3.5),
        (r"\b(koffie|thee) (na|in|drinken)\b", 3.0),
        (r"\bvolgende (week|zondag)\b", 2.5),
        (r"\b(aanvangstijd|opgeven|aanmelden|inschrijven)\b", 2.5),
        (r"\b(de grote zaal|de bovenzaal|de kerkzaal)\b", 1.5),
    ],
    "zegen": [
        (r"\b(de zegen|zegene|zegent) (van|jullie|u)\b", 3.5),
        (r"\bga (heen )?in vrede\b", 3.5),
        (r"\b(de genade van onze heer|de vrede van god)\b", 3.0),
        (r"\bwel thuis\b", 2.0),
    ],
}

COMPILED = {part: [(re.compile(pattern, re.IGNORECASE), weight) for pattern, weight in cues]
            for part, cues in CUES.items()}

# The sermon is the long stretch in the middle; songs leave long gaps in the transcript.
SONG_GAP = 25.0  # seconds of silence that suggest music rather than speech
SERMON_MIN = 240.0  # a stretch of continuous talking this long is almost certainly the preach


@dataclass
class Block:
    """One stretch of the service, and what it appears to be."""

    part: Part
    start: float
    end: float
    confidence: float

    @property
    def seconds(self) -> float:
        return max(0.0, self.end - self.start)

    def as_dict(self) -> dict:
        return {"part": self.part, "label": PART_LABEL[self.part], "start": round(self.start, 1),
                "end": round(self.end, 1), "confidence": round(self.confidence, 2)}


def song_gap(segments: list[Segment]) -> float:
    """How long a silence has to be, in this transcript, before it means music.

    Well over the usual gap between two sentences here, and never less than SONG_GAP, so a
    thinly transcribed service does not read as one long song.
    """
    gaps = sorted(segments[i].start - segments[i - 1].end for i in range(1, len(segments)))
    if not gaps:
        return SONG_GAP
    middle = gaps[len(gaps) // 2]
    return max(SONG_GAP, middle * 3 + 5)


def cue_scores(text: str) -> dict[Part, float]:
    """How strongly one piece of text points at each part of the service."""
    scores: dict[Part, float] = {}
    for part, patterns in COMPILED.items():
        total = sum(weight for pattern, weight in patterns if pattern.search(text))
        if total:
            scores[part] = total
    return scores


def label_segments(segments: list[Segment], duration: float | None = None) -> list[Part]:
    """Give every segment its most likely part of the service.

    Two passes: the words first, then the shape of the recording. A sentence on its own
    says little, so a label spreads to its quiet neighbours and short islands are absorbed
    into what surrounds them.
    """
    if not segments:
        return []
    total = duration or segments[-1].end
    labels: list[Part | None] = [None] * len(segments)

    # A gap in the transcript during a service is nearly always music. What counts as a
    # gap depends on how densely this transcript is written: a sparse one, where the
    # speech model kept only the clearest sentences, has long gaps everywhere.
    quiet = song_gap(segments)
    silent = set()
    for i in range(1, len(segments)):
        if segments[i].start - segments[i - 1].end >= quiet:
            silent.update((i - 1, i))

    for i, segment in enumerate(segments):
        scores = cue_scores(segment.text)
        if i in silent:
            # Silence outweighs where in the hour we are, but not an announced song.
            scores["zang"] = scores.get("zang", 0.0) + 2.5
        # Where in the hour this falls is a weak hint, and only ever a tie-breaker.
        place = segment.start / total if total else 0.0
        if place < 0.08:
            scores["welkom"] = scores.get("welkom", 0.0) + 1.0
        if place > 0.93:
            scores["zegen"] = scores.get("zegen", 0.0) + 1.0
        if 0.25 < place < 0.8:
            scores["preek"] = scores.get("preek", 0.0) + 0.75
        if scores:
            labels[i] = max(scores, key=lambda part: scores[part])

    spread(labels)
    absorb_islands(labels, segments)
    return [label or "preek" for label in labels]


def spread(labels: list[Part | None]) -> None:
    """Carry each label forward until another one takes over, then fill the start."""
    current: Part | None = None
    for i, label in enumerate(labels):
        if label is not None:
            current = label
        elif current is not None:
            labels[i] = current
    first = next((label for label in labels if label is not None), None)
    for i, label in enumerate(labels):
        if label is None:
            labels[i] = first
        else:
            break


def absorb_islands(labels: list[Part | None], segments: list[Segment], shortest: float = 20.0) -> None:
    """A couple of sentences is not a part of the service. Fold short runs into their neighbours."""
    for start, end in runs(labels):
        length = segments[end].end - segments[start].start
        if length >= shortest:
            continue
        before = labels[start - 1] if start > 0 else None
        after = labels[end + 1] if end + 1 < len(labels) else None
        replacement = before or after
        if replacement is None or (before and after and before != after and labels[start] == "preek"):
            continue
        for i in range(start, end + 1):
            labels[i] = replacement


def runs(labels: list[Part | None]) -> list[tuple[int, int]]:
    """The index ranges over which the label stays the same."""
    out: list[tuple[int, int]] = []
    start = 0
    for i in range(1, len(labels) + 1):
        if i == len(labels) or labels[i] != labels[start]:
            out.append((start, i - 1))
            start = i
    return out


def blocks(segments: list[Segment], duration: float | None = None) -> list[Block]:
    """The service as a handful of labelled stretches, in order."""
    labels = label_segments(segments, duration)
    out: list[Block] = []
    for start, end in runs(labels):
        text = " ".join(s.text for s in segments[start:end + 1])
        scores = cue_scores(text)
        strength = scores.get(labels[start], 0.0)
        out.append(Block(part=labels[start], start=segments[start].start, end=segments[end].end,
                         confidence=min(1.0, strength / 6.0)))
    return promote_sermon(out)


def promote_sermon(found: list[Block]) -> list[Block]:
    """The longest uninterrupted stretch of talking is the sermon, whatever the words said.

    A preacher who opens with a Bible reading or prays half way through should not have
    those minutes taken out of the sermon, and a service with no obvious cue at all still
    has one long block in the middle that is worth looking at.
    """
    if not found:
        return found
    longest = max(found, key=lambda b: b.seconds)
    if longest.seconds >= SERMON_MIN and longest.part != "preek":
        longest.part = "preek"
        longest.confidence = max(longest.confidence, 0.5)
    return found


def part_at(found: list[Block], moment: float) -> Part:
    """Which part of the service a given second belongs to."""
    for block in found:
        if block.start <= moment <= block.end:
            return block.part
    return "preek"


def worth_analysing(found: list[Block], start: float, end: float) -> bool:
    """Whether a stretch of transcript is worth sending to the model.

    A window is skipped only when it lies wholly inside parts a clip never comes from,
    so a moment that starts during the singing and runs into the sermon still gets seen.
    """
    covered = 0.0
    for block in found:
        overlap = min(block.end, end) - max(block.start, start)
        if overlap > 0 and block.part not in SKIP:
            covered += overlap
    return covered >= 0.25 * max(1e-6, end - start)


def summary(found: list[Block]) -> str:
    """The shape of the service in one line, for the prompt that has to choose between moments."""
    return ", ".join(f"{PART_LABEL[b.part]} {int(b.start // 60)}:{int(b.start % 60):02d}"
                     f"-{int(b.end // 60)}:{int(b.end % 60):02d}" for b in found)
