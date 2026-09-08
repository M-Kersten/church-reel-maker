"""Clips cut from a service point at the recording instead of copying it."""

import shutil
import subprocess

import pytest

from backend import clips, renderer
from backend.models import ClipOrigin, Output, Segment, Style, Transcript
from backend.subtitles import write_ass

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="needs FFmpeg")

OUT = Output()


@pytest.fixture(scope="module")
def recording(tmp_path_factory):
    """30 seconds whose colour tells you the time: the hue turns once over the recording.

    Colour survives cropping and scaling, so a frame of the finished clip can be matched
    against the second of the recording it should have come from.
    """
    path = tmp_path_factory.mktemp("service") / "source.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "color=c=red:s=1280x720:r=30:d=30",
         "-f", "lavfi", "-i", "sine=frequency=440:duration=30",
         "-vf", "hue=H=2*PI*t/30", "-c:v", "libx264", "-preset", "ultrafast", "-g", "15",
         "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(path)], check=True)
    return path


def average_colour(source, at: float) -> tuple[float, float, float]:
    """Mean red, green and blue of one frame, read straight out of ffmpeg."""
    raw = subprocess.run(
        ["ffmpeg", "-v", "error", "-ss", str(at), "-i", str(source), "-frames:v", "1",
         "-vf", "scale=8:8", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
        capture_output=True).stdout
    pixels = list(raw)
    return tuple(sum(pixels[c::3]) / max(1, len(pixels) // 3) for c in range(3))


def colour_gap(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    return sum(abs(x - y) for x, y in zip(a, b))


def test_clip_info_shortens_the_duration_and_keeps_the_rest(recording):
    full = renderer.probe(recording)
    part = clips.clip_info(full, 10.0, 25.0)
    assert part.duration == 15.0
    assert (part.width, part.height) == (full.width, full.height)
    assert part.hasAudio == full.hasAudio


def test_a_range_renders_the_right_part_of_the_recording(recording, tmp_path):
    """The rendered clip must start where the range starts, not at the recording's start."""
    info = clips.clip_info(renderer.probe(recording), 12.0, 20.0)
    subs = tmp_path / "subs.ass"
    write_ass(Transcript(language="nl", segments=[]), Style(), OUT, subs)
    out = tmp_path / "range.mp4"
    renderer.render_video(recording, info, subs, OUT, out, source_start=12.0)

    made = renderer.probe(out)
    assert made.duration == pytest.approx(8.0, abs=0.3), "only the range, not the whole recording"

    # Half a second into the clip is 12.5 s into the recording, not 0.5 s.
    from_clip = average_colour(out, 0.5)
    assert colour_gap(from_clip, average_colour(recording, 12.5)) < 30
    assert colour_gap(from_clip, average_colour(recording, 0.5)) > 60


def test_subtitles_stay_in_step_with_the_range(recording, tmp_path):
    """Seeking must rebase the timestamps, or every burned-in line drifts by the offset."""
    info = clips.clip_info(renderer.probe(recording), 18.0, 24.0)
    subs = tmp_path / "subs.ass"
    write_ass(Transcript(language="nl", segments=[
        Segment(start=0.0, end=2.0, text="EERSTE"),
    ]), Style(fontSize=120, background=True), OUT, subs)
    out = tmp_path / "timed.mp4"
    renderer.render_video(recording, info, subs, OUT, out, source_start=18.0)

    def brightness(at: float) -> float:
        target = tmp_path / f"f{at}.png"
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", str(at), "-i", str(out),
                        "-vf", "crop=1080:400:0:1300,scale=100:40", "-frames:v", "1", "-update", "1",
                        str(target)], check=True)
        raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(target), "-f", "rawvideo",
                              "-pix_fmt", "gray", "-"], capture_output=True).stdout
        return sum(raw) / max(1, len(raw))

    assert brightness(1.0) != pytest.approx(brightness(4.0), abs=1.0), \
        "the subtitle should be on screen at 1 s and gone by 4 s"


def a_service(models, tmp_path, recording, name="source.mp4"):
    """A stored service whose recording keeps the extension it was uploaded with."""
    folder = tmp_path / "services" / "service-x"
    folder.mkdir(parents=True, exist_ok=True)
    shutil.copy(recording, folder / name)
    service = models.Service(id="service-x", createdAt="2026-01-01T00:00:00+00:00", title="Dienst",
                             sourceVideo=name, sourceInfo=renderer.probe(folder / name))
    models.save_service(service)
    return folder / name


def test_materialising_gives_the_clip_its_own_file(recording, tmp_path, monkeypatch):
    from backend import models
    monkeypatch.setattr(models, "PROJECTS_DIR", tmp_path / "projects")
    monkeypatch.setattr(models, "SERVICES_DIR", tmp_path / "services")
    source = a_service(models, tmp_path, recording)

    project = clips.create_clip(
        source, 5.0, 11.0, title="Test",
        origin=ClipOrigin(serviceId="service-x", candidateId="c1", start=5.0, end=11.0),
    )
    assert project.sourceVideo is None, "a fresh clip points at the recording"
    assert clips.source_of(project) == (source, 5.0, 6.0)

    clips.materialise(project)
    assert project.sourceVideo == "source.mp4"
    own, start, length = clips.source_of(project)
    assert start == 0.0 and length == pytest.approx(6.0, abs=0.3)
    assert own.is_file() and own != source


def test_the_recording_is_found_whatever_it_was_uploaded_as(recording, tmp_path, monkeypatch):
    """A service keeps the extension it was given, so nothing may assume .mp4."""
    from backend import models
    monkeypatch.setattr(models, "PROJECTS_DIR", tmp_path / "projects")
    monkeypatch.setattr(models, "SERVICES_DIR", tmp_path / "services")
    source = a_service(models, tmp_path, recording, name="source.webm")
    project = clips.create_clip(
        source, 2.0, 8.0, origin=ClipOrigin(serviceId="service-x", candidateId="c1", start=2.0, end=8.0))
    assert clips.source_of(project) == (source, 2.0, 6.0)


def test_a_clip_says_so_when_its_recording_is_gone(tmp_path, monkeypatch):
    from backend import models
    monkeypatch.setattr(models, "PROJECTS_DIR", tmp_path / "projects")
    monkeypatch.setattr(models, "SERVICES_DIR", tmp_path / "services")
    project = models.Project(id="project-x", createdAt="2026-01-01T00:00:00+00:00",
                             origin=ClipOrigin(serviceId="gone", candidateId=None, start=0, end=5))
    assert not clips.has_footage(project)
    with pytest.raises(clips.MissingFootage) as exc:
        clips.source_of(project)
    assert "opgeruimd" in str(exc.value)
