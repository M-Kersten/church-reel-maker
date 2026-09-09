"""Brand presets: everything that makes a video belong to one church.

A brand holds the church details, the end screen, the default subtitle style and the
default background music. Several churches (or several campaigns) can live side by side;
one of them is active and is used for new clips and for the end screen that gets appended.

Files: templates/brands/<id>.json, with templates/brands/actief.json naming the active one.
"""

import json
import re
import unicodedata
from pathlib import Path

from pydantic import BaseModel

from .models import (TEMPLATES_DIR, ChurchInfo, MusicSettings, OutroConfig, Style, Vocabulary, Watermark,
                     write_atomic)

BRANDS_DIR = TEMPLATES_DIR / "brands"
ACTIVE_FILE = BRANDS_DIR / "actief.json"


class Brand(BaseModel):
    id: str
    name: str
    church: ChurchInfo = ChurchInfo()
    outro: OutroConfig = OutroConfig()
    subtitleStyle: Style = Style()
    music: MusicSettings = MusicSettings()
    watermark: Watermark = Watermark()
    vocabulary: Vocabulary = Vocabulary()


class BrandSummary(BaseModel):
    id: str
    name: str
    active: bool


def slug(name: str) -> str:
    plain = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    cleaned = re.sub(r"[^a-z0-9]+", "-", plain.lower()).strip("-")
    return cleaned or "merk"


def path_for(brand_id: str) -> Path:
    return BRANDS_DIR / f"{brand_id}.json"


def migrate() -> None:
    """First run: turn the loose church.json and outro.json into one brand."""
    BRANDS_DIR.mkdir(parents=True, exist_ok=True)
    if any(BRANDS_DIR.glob("*.json")) and ACTIVE_FILE.is_file():
        return
    church = ChurchInfo()
    old_church = TEMPLATES_DIR / "church.json"
    if old_church.is_file():
        church = ChurchInfo.model_validate_json(old_church.read_text(encoding="utf-8"))
    outro = OutroConfig()
    old_outro = TEMPLATES_DIR / "outro.json"
    if old_outro.is_file():
        try:
            outro = OutroConfig.model_validate_json(old_outro.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001  fall back to the defaults if that file is unusable
            pass
    brand = Brand(id=slug(church.churchName), name=church.churchName, church=church, outro=outro)
    save(brand)
    set_active(brand.id)


def load(brand_id: str) -> Brand | None:
    path = path_for(brand_id)
    if not path.is_file():
        return None
    return Brand.model_validate_json(path.read_text(encoding="utf-8"))


def save(brand: Brand) -> Brand:
    BRANDS_DIR.mkdir(parents=True, exist_ok=True)
    write_atomic(path_for(brand.id), brand.model_dump_json(indent=2))
    return brand


def all_brands() -> list[Brand]:
    migrate()
    brands = []
    for path in sorted(BRANDS_DIR.glob("*.json")):
        if path.name == ACTIVE_FILE.name:
            continue
        try:
            brands.append(Brand.model_validate_json(path.read_text(encoding="utf-8")))
        except Exception:  # noqa: BLE001  skip a damaged file instead of breaking the list
            continue
    return brands


def active_id() -> str:
    migrate()
    if ACTIVE_FILE.is_file():
        try:
            chosen = json.loads(ACTIVE_FILE.read_text(encoding="utf-8")).get("active", "")
        except Exception:  # noqa: BLE001
            chosen = ""
        if chosen and path_for(chosen).is_file():
            return chosen
    first = all_brands()
    return first[0].id if first else ""


def active() -> Brand:
    brand = load(active_id())
    return brand or Brand(id="standaard", name="Standaard")


def set_active(brand_id: str) -> Brand:
    BRANDS_DIR.mkdir(parents=True, exist_ok=True)
    write_atomic(ACTIVE_FILE, json.dumps({"active": brand_id}, indent=2))
    return active()


def create(name: str, copy_from: str | None = None) -> Brand:
    base = load(copy_from) if copy_from else None
    brand_id = slug(name)
    n = 2
    while path_for(brand_id).is_file():
        brand_id = f"{slug(name)}-{n}"
        n += 1
    brand = Brand(id=brand_id, name=name,
                  church=base.church.model_copy(deep=True) if base else ChurchInfo(churchName=name),
                  outro=base.outro.model_copy(deep=True) if base else OutroConfig(),
                  subtitleStyle=base.subtitleStyle.model_copy(deep=True) if base else Style(),
                  music=base.music.model_copy(deep=True) if base else MusicSettings(),
                  watermark=base.watermark.model_copy(deep=True) if base else Watermark(),
                  vocabulary=base.vocabulary.model_copy(deep=True) if base else Vocabulary())
    if not base:
        brand.church.churchName = name
    return save(brand)


def delete(brand_id: str) -> None:
    path_for(brand_id).unlink(missing_ok=True)
    if active_id() == brand_id:
        remaining = all_brands()
        if remaining:
            set_active(remaining[0].id)


def summaries() -> list[BrandSummary]:
    current = active_id()
    return [BrandSummary(id=b.id, name=b.name, active=b.id == current) for b in all_brands()]


def learn_corrections(pairs: dict[str, str], brand_id: str | None = None) -> Brand:
    """Remember what this church actually says, so the next service gets it right.

    A correction is keyed on what the speech model heard, in lower case, because that is
    what it will hear again next week.
    """
    brand = (load(brand_id) if brand_id else None) or active()
    for heard, meant in pairs.items():
        heard, meant = heard.strip().lower(), meant.strip()
        # A fix that only adds capitals is still a fix: the correction is matched without
        # case and written back with it, which is how "heilige geest" becomes "Heilige Geest".
        if heard and meant and heard != meant:
            brand.vocabulary.corrections[heard] = meant
    return save(brand)
