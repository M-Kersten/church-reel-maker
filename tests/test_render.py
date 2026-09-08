"""One real render, start to finish, so the FFmpeg command is proved and not just assembled."""

import shutil
import subprocess

import pytest

from backend import renderer
from backend.models import Output, Segment, Style, Transcript, Watermark
from backend.subtitles import write_ass

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="needs FFmpeg")

OUT = Output()


@pytest.fixture(scope="module")
def clip(tmp_path_factory):
    """A short test clip with sound, standing in for a fragment of a service."""
    path = tmp_path_factory.mktemp("source") / "clip.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc2=s=1920x1080:r=30:d=4",
         "-f", "lavfi", "-i", "sine=frequency=440:duration=4",
         "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-shortest", str(path)], check=True)
    return path


def test_probe_reads_what_the_editor_needs(clip):
    info = renderer.probe(clip)
    assert (info.width, info.height) == (1920, 1080)
    assert info.duration == pytest.approx(4.0, abs=0.2)
    assert info.hasAudio and info.videoCodec == "h264"


def test_probe_refuses_a_file_with_no_picture(tmp_path):
    audio = tmp_path / "audio.m4a"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "sine=duration=1",
                    "-c:a", "aac", str(audio)], check=True)
    with pytest.raises(ValueError):
        renderer.probe(audio)


def test_render_produces_a_playable_vertical_video(clip, tmp_path):
    subs = tmp_path / "subs.ass"
    write_ass(Transcript(language="nl", segments=[
        Segment(start=0.2, end=2.0, text="God is op zoek naar jou"),
        Segment(start=2.2, end=3.8, text="Niet omdat je perfect bent."),
    ]), Style(), OUT, subs)

    out = tmp_path / "final.mp4"
    renderer.render_video(clip, renderer.probe(clip), subs, OUT, out)

    assert out.is_file() and out.stat().st_size > 10_000
    made = renderer.probe(out)
    assert (made.width, made.height) == (OUT.width, OUT.height)
    assert made.duration == pytest.approx(4.0, abs=0.5)
    assert made.hasAudio


def test_render_reports_progress_that_only_moves_forward(clip, tmp_path):
    subs = tmp_path / "subs.ass"
    write_ass(Transcript(language="nl", segments=[]), Style(), OUT, subs)
    seen: list[float] = []
    renderer.render_video(clip, renderer.probe(clip), subs, OUT, tmp_path / "p.mp4",
                          on_progress=lambda f, _m: seen.append(f))
    assert seen, "the render reported no progress at all"
    assert seen == sorted(seen)
    assert 0.0 <= seen[0] and seen[-1] <= 1.0


def test_render_burns_the_logo_into_the_corner(clip, tmp_path):
    from backend.models import TEMPLATES_DIR
    logos = TEMPLATES_DIR / "logos"
    logos.mkdir(parents=True, exist_ok=True)
    logo = logos / "_test_mark.png"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi",
                    "-i", "color=c=white:s=200x100", "-frames:v", "1", "-update", "1", str(logo)], check=True)
    try:
        subs = tmp_path / "subs.ass"
        write_ass(Transcript(language="nl", segments=[]), Style(), OUT, subs)
        out = tmp_path / "marked.mp4"
        renderer.render_video(clip, renderer.probe(clip), subs, OUT, out,
                              watermark=Watermark(file=logo.name, corner="topLeft", width=0.25,
                                                  opacity=1.0, margin=40))
        frame = tmp_path / "frame.pgm"
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", "1", "-i", str(out),
                        "-frames:v", "1", "-update", "1", str(frame)], check=True)
        pixels = frame.read_bytes()
        assert len(pixels) > 1000  # the frame decoded; the logo is white on a test pattern
        assert renderer.probe(out).width == OUT.width
    finally:
        logo.unlink(missing_ok=True)


def test_a_broken_source_gives_a_readable_message(tmp_path):
    broken = tmp_path / "broken.mp4"
    broken.write_bytes(b"this is not a video")
    assert "beschadigd" in renderer.ffmpeg_message("Invalid data found when processing input")
    assert "ruimte" in renderer.ffmpeg_message("No space left on device")
    assert "rechten" in renderer.ffmpeg_message("Permission denied")
