"""Entry point from discovery into the existing clip-production pipeline.

create_clip(source, start, end) cuts the range out of a long recording into a
brand-new Project, which then goes through the unchanged Part 1 workflow
(subtitles, style, 9:16 crop, outro, render).
"""

import subprocess
from pathlib import Path

from . import renderer
from .models import (ClipOrigin, Project, Segment, Transcript, VideoInfo, load_service, new_project,
                     project_dir, save_project, save_transcript, service_dir)


def extract_range(source: Path, start: float, end: float, destination: Path) -> None:
    """Cut [start, end] from `source` with frame-accurate seeking (re-encoded, original resolution)."""
    subprocess.run(
        ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
         "-ss", f"{start:.3f}", "-i", str(source), "-t", f"{end - start:.3f}",
         "-c:v", "libx264", "-preset", "fast", "-crf", "18", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", "-avoid_negative_ts", "make_zero",
         str(destination)],
        check=True,
    )


def slice_transcript(transcript: Transcript, start: float, end: float) -> Transcript:
    """Segments that fall inside [start, end], re-based so the clip starts at 0."""
    segments = []
    for seg in transcript.segments:
        if seg.end <= start or seg.start >= end:
            continue
        segments.append(Segment(
            start=round(max(0.0, seg.start - start), 2),
            end=round(min(end - start, seg.end - start), 2),
            text=seg.text,
        ))
    return Transcript(language=transcript.language, segments=[s for s in segments if s.end > s.start])


def clip_info(source_info: VideoInfo, start: float, end: float) -> VideoInfo:
    """The source's properties, but only as long as the clip."""
    return source_info.model_copy(update={"duration": round(max(0.0, end - start), 3)})


def create_clip(
    source: Path,
    start: float,
    end: float,
    transcript: Transcript | None = None,
    title: str | None = None,
    origin: ClipOrigin | None = None,
    source_info: VideoInfo | None = None,
) -> Project:
    """Create a clip Project for a time range of a longer recording.

    Nothing is cut here. The project keeps a pointer to the recording and the range, and
    the renderer reads that range straight from the original, so a finished clip is one
    encode away from the camera instead of two. Everything downstream asks source_of()
    where the footage is.
    """
    if end <= start:
        raise ValueError("end must be after start")
    if origin is None:
        raise ValueError("a clip cut from a recording needs its origin")
    project = new_project()
    project.sourceInfo = clip_info(source_info or renderer.probe(source), start, end)
    project.crop = renderer.default_crop(project.sourceInfo, project.output)
    project.title = title
    project.origin = origin
    save_project(project)
    if transcript is not None:
        save_transcript(project, slice_transcript(transcript, start, end))
    return project


class MissingFootage(RuntimeError):
    """The recording a clip points at is not on disk any more."""


def source_of(project: Project) -> tuple[Path, float, float]:
    """Where this clip's footage lives: (file, seconds to skip, seconds to use).

    A clip that owns its file starts at 0 and runs the whole length. A clip cut from a
    service points into that recording, so the renderer seeks instead of reading a copy.
    """
    if project.sourceVideo:
        path = project_dir(project.id) / project.sourceVideo
        if not path.is_file():
            raise MissingFootage("Het videobestand van dit fragment is niet meer gevonden.")
        return path, 0.0, project.sourceInfo.duration if project.sourceInfo else 0.0
    if project.origin:
        gone = MissingFootage(
            "De opname waar dit fragment uit komt is opgeruimd. Upload de dienst opnieuw, "
            "of maak het fragment opnieuw aan.")
        service = load_service(project.origin.serviceId)
        if service is None or not service.sourceVideo:
            raise gone
        path = service_dir(project.origin.serviceId) / service.sourceVideo
        if not path.is_file():
            raise gone
        return path, project.origin.start, project.origin.end - project.origin.start
    raise MissingFootage("Upload eerst een video")


def has_footage(project: Project) -> bool:
    try:
        source_of(project)
    except MissingFootage:
        return False
    return True


def materialise(project: Project) -> Project:
    """Give a clip its own copy of the footage, so the recording can be thrown away.

    This is the one place a clip gets re-encoded, and it only happens when the original
    is about to disappear.
    """
    if project.sourceVideo:
        return project
    source, start, length = source_of(project)
    target = project_dir(project.id) / "source.mp4"
    try:
        extract_range(source, start, start + length, target)
        project.sourceVideo = target.name
        project.sourceInfo = renderer.probe(target)
        save_project(project)
    except Exception:
        target.unlink(missing_ok=True)
        raise
    return project
