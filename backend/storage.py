"""What the app keeps on disk, and what it lets go of.

A church that does this every week fills a laptop: a service recording is a few GB, its
working audio another 170 MB, and every rendered clip sits next to them. The failure this
prevents is FFmpeg dying half way through a render because the disk ran out, which is
both the most annoying moment for it to happen and the hardest one to explain.

Nothing here deletes a transcript, a candidate list or a finished video. It removes the
big files that can be produced again from something the user still has.
"""

import os
import shutil
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import clips
from .models import (PROJECTS_DIR, ROOT, SERVICES_DIR, Project, Service, load_service, save_project,
                     save_service, service_dir, project_dir)

# How long a recording is kept before it is offered for cleanup. A month covers a church
# that only gets round to its clips a few weeks later.
KEEP_WEEKS = int(os.environ.get("KEEP_WEEKS", "4"))  # 0 turns automatic cleaning off
LOW_DISK_GB = 5.0  # below this the interface stops suggesting and starts warning


def folder_size(path: Path) -> int:
    if not path.is_dir():
        return 0
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())


def age_days(created_at: str) -> float:
    try:
        made = datetime.fromisoformat(created_at)
    except ValueError:
        return 0.0
    if made.tzinfo is None:
        made = made.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - made).total_seconds() / 86400


@dataclass
class Item:
    """One thing that could be cleaned up, and what it would give back."""

    kind: str  # "service" | "project"
    id: str
    title: str
    createdAt: str
    days: float
    bytes: int  # what removing the big files would free
    keeps: str  # what stays behind afterwards
    blocked: str = ""  # why it cannot go yet

    def as_dict(self) -> dict:
        return {"kind": self.kind, "id": self.id, "title": self.title, "createdAt": self.createdAt,
                "days": round(self.days, 1), "mb": round(self.bytes / 1e6, 1), "keeps": self.keeps,
                "blocked": self.blocked}


def clips_of(service_id: str) -> list[Project]:
    """Clip projects that still read their footage from this recording."""
    out = []
    for path in sorted(PROJECTS_DIR.glob("*/project.json")):
        try:
            project = Project.model_validate_json(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001  a damaged project must not block cleaning up
            continue
        if project.sourceVideo is None and project.origin and project.origin.serviceId == service_id:
            out.append(project)
    return out


def service_item(service: Service) -> Item | None:
    """What cleaning up this service would free, or None when there is nothing to free."""
    folder = service_dir(service.id)
    recording = folder / service.sourceVideo if service.sourceVideo else None
    work = folder / "work"
    size = (recording.stat().st_size if recording and recording.is_file() else 0) + folder_size(work)
    if size == 0:
        return None
    return Item(kind="service", id=service.id, title=service.title, createdAt=service.createdAt,
                days=age_days(service.createdAt), bytes=size,
                keeps="de tekst, de gevonden fragmenten en de video's die je al gemaakt hebt")


def project_item(project: Project) -> Item | None:
    """A rendered clip no longer needs the copy of the footage it was cut from."""
    if project.sourceVideo is None:
        return None  # points at a recording; nothing of its own to free
    folder = project_dir(project.id)
    source = folder / project.sourceVideo
    if not source.is_file():
        return None
    made = folder / "output" / "final.mp4"
    return Item(kind="project", id=project.id, title=project.title or project.id,
                createdAt=project.createdAt, days=age_days(project.createdAt),
                bytes=source.stat().st_size + folder_size(folder / "work"),
                keeps="de gemaakte video en de ondertitels",
                blocked="" if made.is_file() else "de video is nog niet gemaakt")


def survey() -> dict:
    """Everything that could be cleaned up, newest first, with what it would give back."""
    items: list[Item] = []
    for path in sorted(SERVICES_DIR.glob("*/service.json")):
        try:
            service = Service.model_validate_json(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        item = service_item(service)
        if item is None:
            continue
        waiting = [c for c in clips_of(service.id) if not (project_dir(c.id) / "output" / "final.mp4").is_file()]
        if waiting:
            item.blocked = (f"{len(waiting)} fragment{'en' if len(waiting) > 1 else ''} hieruit "
                            f"{'zijn' if len(waiting) > 1 else 'is'} nog niet gemaakt")
        items.append(item)
    for path in sorted(PROJECTS_DIR.glob("*/project.json")):
        try:
            project = Project.model_validate_json(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        item = project_item(project)
        if item is not None:
            items.append(item)

    items.sort(key=lambda i: i.createdAt, reverse=True)
    free = shutil.disk_usage(ROOT).free
    return {
        "keepWeeks": KEEP_WEEKS,
        "freeGb": round(free / 1e9, 1),
        "lowDisk": free / 1e9 < LOW_DISK_GB,
        "usedMb": round(sum(i.bytes for i in items) / 1e6, 1),
        "oldMb": round(sum(i.bytes for i in items if i.days >= KEEP_WEEKS * 7 and not i.blocked) / 1e6, 1),
        "items": [i.as_dict() for i in items],
    }


def clean_service(service_id: str) -> int:
    """Drop a recording and its working audio. Clips that still need it get their own copy first.

    Returns the bytes freed. The transcript, the candidates and the list of made clips stay.
    """
    service = load_service(service_id)
    if service is None:
        return 0
    folder = service_dir(service_id)
    before = folder_size(folder)
    for project in clips_of(service_id):
        # A clip nobody has rendered yet would be left pointing at nothing.
        if (project_dir(project.id) / "output" / "final.mp4").is_file():
            continue
        clips.materialise(project)
    if service.sourceVideo:
        (folder / service.sourceVideo).unlink(missing_ok=True)
        service.sourceVideo = None
        save_service(service)
    shutil.rmtree(folder / "work", ignore_errors=True)
    return before - folder_size(folder)


def clean_project(project_id: str) -> int:
    """Drop a clip's copy of the footage once its video has been made. Returns bytes freed."""
    path = PROJECTS_DIR / project_id / "project.json"
    if not path.is_file():
        return 0
    project = Project.model_validate_json(path.read_text(encoding="utf-8"))
    folder = project_dir(project.id)
    if not project.sourceVideo or not (folder / "output" / "final.mp4").is_file():
        return 0
    before = folder_size(folder)
    (folder / project.sourceVideo).unlink(missing_ok=True)
    project.sourceVideo = None
    save_project(project)
    shutil.rmtree(folder / "work", ignore_errors=True)
    return before - folder_size(folder)


def clean(kind: str, item_id: str) -> int:
    return clean_service(item_id) if kind == "service" else clean_project(item_id)


def clean_work() -> int:
    """Throw away the working audio of every service that has already been written out.

    A 90-minute service leaves a 170 MB wav behind, and once there is a transcript it is
    only in the way. It costs a second to make again. Always safe, so this runs unasked.
    """
    freed = 0
    for path in sorted(SERVICES_DIR.glob("*/work")):
        service = load_service(path.parent.name)
        if service is None or not service.transcript:
            continue
        freed += folder_size(path)
        shutil.rmtree(path, ignore_errors=True)
    return freed


def clean_old() -> tuple[int, int]:
    """Clean up everything past its keep-by date. Returns (things cleaned, bytes freed)."""
    if KEEP_WEEKS <= 0:
        return 0, 0
    freed = count = 0
    for item in survey()["items"]:
        if item["blocked"] or item["days"] < KEEP_WEEKS * 7:
            continue
        gained = clean(item["kind"], item["id"])
        if gained > 0:
            count += 1
            freed += gained
    return count, freed


def sweep() -> str:
    """The pass that runs at startup. Returns a line for the log, or an empty string."""
    said = []
    work = clean_work()
    if work > 0:
        said.append(f"{work / 1e6:.0f} MB werkbestanden")
    count, freed = clean_old()
    if count:
        said.append(f"{freed / 1e6:.0f} MB aan {count} opname(s) ouder dan {KEEP_WEEKS} weken")
    return "opgeruimd: " + " en ".join(said) if said else ""
