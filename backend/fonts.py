"""Which fonts are available, read from the files in templates/fonts.

Files follow {Stem}-{Weight}.ttf, and the family name inside the file is
"Family" for Regular and Bold and "Family Weight" for the rest. Drop another
pair of files in that folder and the font appears in the app.
"""

import re
from pathlib import Path

from pydantic import BaseModel

from .models import FONTS_DIR

WEIGHTS = ["regular", "medium", "semibold", "bold", "extrabold"]
FILE_WEIGHT = {"regular": "Regular", "medium": "Medium", "semibold": "SemiBold", "bold": "Bold", "extrabold": "ExtraBold"}
SYSTEM_FONT = "Arial"  # always offered; comes from the operating system


class FontFamily(BaseModel):
    name: str  # "Open Sans"
    stem: str  # "OpenSans", the file name prefix
    weights: list[str]


_cache: tuple[float, list[FontFamily]] | None = None


def _display_name(stem: str) -> str:
    return re.sub(r"(?<=[a-z])(?=[A-Z])", " ", stem)


def catalogue() -> list[FontFamily]:
    """Families in templates/fonts, refreshed when the folder changes."""
    global _cache
    directory = Path(FONTS_DIR)
    stamp = directory.stat().st_mtime if directory.is_dir() else 0.0
    if _cache and _cache[0] == stamp:
        return _cache[1]

    found: dict[str, list[str]] = {}
    for path in sorted(directory.glob("*.ttf")):
        stem, _, weight = path.stem.rpartition("-")
        if not stem or weight not in FILE_WEIGHT.values():
            continue
        name = next(w for w, f in FILE_WEIGHT.items() if f == weight)
        found.setdefault(stem, []).append(name)

    families = [FontFamily(name=_display_name(stem), stem=stem, weights=[w for w in WEIGHTS if w in weights])
                for stem, weights in sorted(found.items(), key=lambda kv: _display_name(kv[0]))]
    families.append(FontFamily(name=SYSTEM_FONT, stem="", weights=WEIGHTS))
    _cache = (stamp, families)
    return families


def names() -> list[str]:
    return [f.name for f in catalogue()]


def resolve_weight(font: str, weight: str) -> str:
    """The closest weight this family actually has (prefer heavier, then lighter)."""
    family = next((f for f in catalogue() if f.name == font), None)
    if family is None or weight in family.weights:
        return weight
    order = WEIGHTS[WEIGHTS.index(weight):] + WEIGHTS[: WEIGHTS.index(weight)][::-1]
    return next((w for w in order if w in family.weights), "regular")
