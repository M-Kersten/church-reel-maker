"""Project data model and on-disk storage.

Layout of a project directory (projects/<id>/):
    project.json      project metadata (this model)
    source.<ext>      the uploaded clip, never modified
    transcript.json   editable subtitle segments
    work/             derived files (audio.wav, subtitles.ass)
    output/final.mp4  the rendered reel
"""

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parent.parent
PROJECTS_DIR = ROOT / "projects"
TEMPLATES_DIR = ROOT / "templates"
FONTS_DIR = TEMPLATES_DIR / "fonts"

FontWeight = Literal["regular", "medium", "semibold", "bold", "extrabold"]
CropStrategy = Literal["static", "tracked"]  # "tracked" is reserved for Part 2


class Style(BaseModel):
    font: str = "Montserrat"
    fontSize: int = Field(default=64, ge=24, le=120)
    fontWeight: FontWeight = "bold"
    color: str = "#FFFFFF"
    outline: int = Field(default=4, ge=0, le=12)
    outlineColor: str = "#000000"
    background: bool = False


class Output(BaseModel):
    width: int = 1080
    height: int = 1920
    fps: int = 30


class Segment(BaseModel):
    start: float
    end: float
    text: str


class Transcript(BaseModel):
    language: str = "nl"
    segments: list[Segment] = []


class VideoInfo(BaseModel):
    width: int
    height: int
    duration: float
    fps: float
    videoCodec: str | None = None
    hasAudio: bool = False
    audioCodec: str | None = None
    audioSampleRate: int | None = None
    audioChannels: int | None = None


class ClipOrigin(BaseModel):
    """Where a clip project was cut from (set by the service discovery layer)."""

    serviceId: str
    candidateId: str | None = None
    start: float
    end: float


class CropWindow(BaseModel):
    """Where the 9:16 output frame sits on the source.

    x, y: centre of the frame as a fraction of the scaled source (0.5 = centred).
    zoom: relative to the scale that exactly fills the frame; 1.0 fills it, smaller values
          letterbox the source, larger values crop in further. Part 2 can animate these.
    """

    x: float = Field(default=0.5, ge=0.0, le=1.0)
    y: float = Field(default=0.5, ge=0.0, le=1.0)
    zoom: float = Field(default=1.0, gt=0.0, le=4.0)


class Project(BaseModel):
    id: str
    createdAt: str
    title: str | None = None
    origin: ClipOrigin | None = None
    sourceVideo: str | None = None  # file name inside the project directory
    sourceInfo: VideoInfo | None = None
    transcript: str | None = None  # "transcript.json" once a transcript exists
    style: Style = Style()
    output: Output = Output()
    outro: str = "templates/outro.mp4"  # relative to the repository root
    cropStrategy: CropStrategy = "static"
    crop: CropWindow | None = None  # None = default framing for the source (see renderer.default_crop)
    tracking: str | None = None  # Part 2: file with the tracked crop path


class ProjectDetail(Project):
    """Project plus its transcript, as returned by GET /projects/{id}."""

    transcriptData: Transcript | None = None


class ChurchInfo(BaseModel):
    churchName: str = "Example Church"
    serviceTimes: list[str] = ["09:30", "11:30"]
    instagram: str = "@examplechurch"


# --- storage -----------------------------------------------------------------


def project_dir(project_id: str) -> Path:
    return PROJECTS_DIR / project_id


def new_project() -> Project:
    project = Project(
        id="project-" + uuid.uuid4().hex[:8],
        createdAt=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )
    (project_dir(project.id) / "work").mkdir(parents=True)
    (project_dir(project.id) / "output").mkdir()
    save_project(project)
    return project


def load_project(project_id: str) -> Project | None:
    path = project_dir(project_id) / "project.json"
    if not path.is_file():
        return None
    return Project.model_validate_json(path.read_text(encoding="utf-8"))


def save_project(project: Project) -> None:
    path = project_dir(project.id) / "project.json"
    path.write_text(project.model_dump_json(indent=2), encoding="utf-8")


def load_transcript(project: Project) -> Transcript | None:
    if not project.transcript:
        return None
    path = project_dir(project.id) / project.transcript
    if not path.is_file():
        return None
    return Transcript.model_validate_json(path.read_text(encoding="utf-8"))


def save_transcript(project: Project, transcript: Transcript) -> None:
    project.transcript = "transcript.json"
    path = project_dir(project.id) / project.transcript
    path.write_text(json.dumps(transcript.model_dump(), indent=2, ensure_ascii=False), encoding="utf-8")
    save_project(project)


def load_church_info() -> ChurchInfo:
    path = TEMPLATES_DIR / "church.json"
    if path.is_file():
        return ChurchInfo.model_validate_json(path.read_text(encoding="utf-8"))
    return ChurchInfo()


# --- full-service discovery -------------------------------------------------
#
# A Service is a complete recording. Discovery produces ClipCandidates (the AI
# thinks this range could work); processing a candidate creates a regular
# Project through backend/clips.py and is recorded as a ProcessedClip.

SERVICES_DIR = ROOT / "services"

ServiceStatus = Literal[
    "created", "uploaded", "transcribing", "transcribed", "analyzing", "ready", "processing", "complete", "error"
]


class TimeRange(BaseModel):
    start: float
    end: float


class ClipCandidate(BaseModel):
    id: str
    start: float
    end: float
    title: str
    summary: str = ""
    reason: str = ""
    confidence: float = 0.5
    selected: bool = False
    score: float = 0.0  # internal sort key, not shown as a number in the UI
    alternateBoundaries: list[TimeRange] = []


class ProcessedClip(BaseModel):
    candidateId: str
    projectId: str
    title: str
    start: float
    end: float
    createdAt: str


class Service(BaseModel):
    id: str
    createdAt: str
    title: str = "Service"
    sourceVideo: str | None = None
    sourceInfo: VideoInfo | None = None
    transcript: str | None = None
    status: ServiceStatus = "created"
    error: str | None = None
    candidates: list[ClipCandidate] = []
    clips: list[ProcessedClip] = []


class ServiceDetail(Service):
    transcriptData: Transcript | None = None
    job: dict | None = None


def service_dir(service_id: str) -> Path:
    return SERVICES_DIR / service_id


def new_service() -> Service:
    service = Service(
        id="service-" + uuid.uuid4().hex[:8],
        createdAt=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )
    (service_dir(service.id) / "work").mkdir(parents=True)
    save_service(service)
    return service


def load_service(service_id: str) -> Service | None:
    path = service_dir(service_id) / "service.json"
    if not path.is_file():
        return None
    return Service.model_validate_json(path.read_text(encoding="utf-8"))


def save_service(service: Service) -> None:
    path = service_dir(service.id) / "service.json"
    path.write_text(service.model_dump_json(indent=2), encoding="utf-8")


def load_service_transcript(service: Service) -> Transcript | None:
    if not service.transcript:
        return None
    path = service_dir(service.id) / service.transcript
    if not path.is_file():
        return None
    return Transcript.model_validate_json(path.read_text(encoding="utf-8"))


def save_service_transcript(service: Service, transcript: Transcript) -> None:
    service.transcript = "transcript.json"
    path = service_dir(service.id) / service.transcript
    path.write_text(json.dumps(transcript.model_dump(), indent=2, ensure_ascii=False), encoding="utf-8")
    save_service(service)
