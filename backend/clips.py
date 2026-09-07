"""Entry point from discovery into the existing clip-production pipeline.

create_clip(source, start, end) cuts the range out of a long recording into a
brand-new Project, which then goes through the unchanged Part 1 workflow
(subtitles, style, 9:16 crop, outro, render).
"""

import subprocess
from pathlib import Path

from . import renderer
from .models import ClipOrigin, Project, Segment, Transcript, new_project, project_dir, save_project, save_transcript


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


def create_clip(
    source: Path,
    start: float,
    end: float,
    transcript: Transcript | None = None,
    title: str | None = None,
    origin: ClipOrigin | None = None,
) -> Project:
    """Create a regular clip Project from a time range of a longer source video."""
    if end <= start:
        raise ValueError("end must be after start")
    project = new_project()
    target = project_dir(project.id) / "source.mp4"
    try:
        extract_range(source, start, end, target)
        project.sourceVideo = target.name
        project.sourceInfo = renderer.probe(target)
        project.title = title
        project.origin = origin
        save_project(project)
        if transcript is not None:
            save_transcript(project, slice_transcript(transcript, start, end))
    except Exception:
        target.unlink(missing_ok=True)
        raise
    return project
