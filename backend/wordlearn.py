"""Spotting what the speech model got wrong, from the corrections a person makes.

The subtitle editor is where someone fixes "lie 302" into "Lied 302" and "Dirk de Bree"
out of whatever the model heard. Those fixes are thrown away today, and next Sunday the
same words come back wrong. This works out which words actually changed between the
machine's version and the corrected one, so the church can be offered them.
"""

import re
from difflib import SequenceMatcher

from .models import Segment

WORD = re.compile(r"[\w'’-]+", re.UNICODE)
MAX_RUN = 4  # a fix longer than a few words is a rewrite, not a misheard name


def words_of(text: str) -> list[str]:
    return WORD.findall(text)


def differences(heard: str, corrected: str) -> list[tuple[str, str]]:
    """The (what the model heard, what was meant) pairs between two versions of a line."""
    before, after = words_of(heard), words_of(corrected)
    if not before or not after:
        return []
    pairs = []
    for tag, i1, i2, j1, j2 in SequenceMatcher(a=before, b=after, autojunk=False).get_opcodes():
        if tag != "replace":
            continue  # a word added or dropped says nothing about what was misheard
        if i2 - i1 > MAX_RUN or j2 - j1 > MAX_RUN:
            continue
        was, meant = " ".join(before[i1:i2]), " ".join(after[j1:j2])
        # A capital on the first word of a line is sentence case, not a name.
        if i1 == 0 and was.lower() == meant.lower():
            continue
        pairs.append((was, meant))
    return pairs


def suggestions(original: list[Segment], edited: list[Segment]) -> dict[str, str]:
    """What is worth adding to the church's word list, after someone corrected the text.

    Only replacements are offered, and only where the correction looks like a spelling of
    the same thing rather than a different word: the model hears sounds, so a fix that
    keeps the sound is a fix it can be told about.
    """
    out: dict[str, str] = {}
    by_start = {round(s.start, 1): s for s in original}
    for segment in edited:
        was = by_start.get(round(segment.start, 1))
        if was is None or was.text.strip() == segment.text.strip():
            continue
        for heard, meant in differences(was.text, segment.text):
            if worth_learning(heard, meant):
                out[heard.lower()] = meant
    return out


# Words a capital would be wrong on: too common, and they start sentences all the time.
COMMON = {"de", "het", "een", "en", "we", "wij", "je", "jij", "ik", "hij", "zij", "dat", "die",
          "dit", "er", "maar", "want", "als", "dan", "ook", "niet", "wat", "hoe", "waar", "toen",
          "voor", "van", "met", "aan", "op", "in", "uit", "over", "door", "naar", "is", "was"}


def worth_learning(heard: str, meant: str) -> bool:
    """Whether a correction is likely to repeat, rather than a one-off rewrite."""
    if not heard or not meant or heard == meant:
        return False
    if len(meant) < 3 or len(heard) < 3:
        return False  # too short to be a name; "de" for "die" teaches nothing
    if heard.lower() == meant.lower():
        # Only the capitals changed, which is how a name is usually fixed. Worth keeping,
        # unless it is a word that starts an ordinary sentence.
        return meant != meant.lower() and heard.lower() not in COMMON
    if meant.lower() == heard.lower().replace(" ", ""):
        return True  # only the spacing changed
    # Sounding alike is the sign of a misheard word rather than a different one.
    return SequenceMatcher(a=heard.lower(), b=meant.lower()).ratio() >= 0.55
