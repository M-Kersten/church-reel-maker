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

FONTS = ["Inter", "Montserrat", "Poppins", "Arial"]
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


class Project(BaseModel):
    id: str
    createdAt: str
    sourceVideo: str | None = None  # file name inside the project directory
    sourceInfo: VideoInfo | None = None
    transcript: str | None = None  # "transcript.json" once a transcript exists
    style: Style = Style()
    output: Output = Output()
    outro: str = "templates/outro.mp4"  # relative to the repository root
    cropStrategy: CropStrategy = "static"
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
