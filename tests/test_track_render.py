"""Turning a path into something FFmpeg will follow, and proving it actually moves.

track_at is mirrored in frontend/src/track.ts (see tests/mirror_cases.py); the commands and
the filter chain below are what the render itself hangs on.
"""

import shutil
import subprocess

import pytest

from backend import renderer
from backend.models import CropWindow, Output, Track, VideoInfo
from backend.renderer import COMMAND_FPS, edge_for, track_at, track_commands

OUT = Output(width=1080, height=1920, fps=30)
WIDE = VideoInfo(width=1920, height=1080, duration=6.0, fps=30.0, videoCodec="h264",
                 hasAudio=True, audioCodec="aac", audioSampleRate=48000, audioChannels=2)
MIDDLE = CropWindow(x=0.5, y=0.5, zoom=1.0)


def path(x: list[float], fps: float = 12.5, jumps: list[int] | None = None) -> Track:
    return Track(fps=fps, x=x, coverage=1.0, subject="face", cuts=[], jumps=jumps or [], enough=True)


# --- reading the path -------------------------------------------------------------


def test_a_moment_between_two_samples_is_mixed():
    assert track_at(path([0.0, 1.0]), 0.04) == pytest.approx(0.5)


def test_a_moment_on_a_sample_is_that_sample():
    assert track_at(path([0.2, 0.8, 0.4]), 0.08) == pytest.approx(0.8)


def test_before_the_start_and_after_the_end_it_holds_still():
    track = path([0.3, 0.4, 0.5])
    assert track_at(track, -5.0) == pytest.approx(0.3)
    assert track_at(track, 900.0) == pytest.approx(0.5)


def test_an_empty_path_says_nothing():
    assert track_at(path([]), 1.0) is None


def test_a_jump_is_not_slid_into():
    # Sample 1 is where the frame jumped to, so the whole of sample 0's frame stays put.
    track = path([0.2, 0.9], jumps=[1])
    assert track_at(track, 0.0) == pytest.approx(0.2)
    assert track_at(track, 0.079) == pytest.approx(0.2)
    assert track_at(track, 0.08) == pytest.approx(0.9)


def test_without_the_jump_the_same_step_would_smear():
    assert track_at(path([0.2, 0.9]), 0.04) == pytest.approx(0.55)


# --- the commands -----------------------------------------------------------------


def test_a_still_path_costs_a_single_command():
    lines = track_commands(WIDE, OUT, MIDDLE, path([0.5] * 40)).strip().splitlines()
    assert len(lines) == 1
    assert lines[0].startswith("0.0000 crop@track x ")


def test_a_moving_path_is_read_finer_than_it_was_stored():
    moving = path([0.2 + i * 0.01 for i in range(40)])
    lines = track_commands(WIDE, OUT, MIDDLE, moving).strip().splitlines()
    stamps = [float(line.split(" ", 1)[0]) for line in lines]
    steps = [round(b - a, 4) for a, b in zip(stamps, stamps[1:])]
    assert min(steps) == pytest.approx(1 / COMMAND_FPS, abs=1e-4), "50 a second, not 12.5"


def test_every_command_lands_on_a_different_pixel():
    moving = path([0.2 + i * 0.01 for i in range(40)])
    xs = [int(line.rsplit(" ", 1)[1].rstrip(";"))
          for line in track_commands(WIDE, OUT, MIDDLE, moving).strip().splitlines()]
    assert len(set(xs)) == len(xs)


def test_the_commands_never_send_the_window_outside_the_picture():
    g = renderer.crop_geometry(WIDE, OUT, MIDDLE)
    wild = path([1.9, -1.4] * 20)
    for line in track_commands(WIDE, OUT, MIDDLE, wild).strip().splitlines():
        x = int(line.rsplit(" ", 1)[1].rstrip(";"))
        assert 0 <= x <= g.scaled_w - g.crop_w


def test_the_commands_run_to_the_end_of_the_path():
    track = path([0.3 + (i % 7) * 0.02 for i in range(50)])
    last = float(track_commands(WIDE, OUT, MIDDLE, track).strip().splitlines()[-1].split(" ", 1)[0])
    assert last <= (len(track.x) - 1) / track.fps + 1e-6
    assert last > (len(track.x) - 1) / track.fps - 0.5


def test_the_window_starts_where_the_static_one_would_when_centred():
    g = renderer.crop_geometry(WIDE, OUT, MIDDLE)
    assert edge_for(0.5, g.scaled_w, g.crop_w) == g.left


# --- the filter chain -------------------------------------------------------------


def test_a_tracked_clip_gets_a_labelled_crop_and_a_command_file(tmp_path):
    commands = tmp_path / "track.cmd"
    chain = renderer.build_crop_filter(WIDE, OUT, "tracked", path([0.4, 0.6, 0.5]), MIDDLE, commands)
    assert "sendcmd=f=" in chain and "crop@track=" in chain
    assert commands.is_file() and commands.read_text().strip()


def test_a_clip_with_no_path_falls_back_to_a_still_window(tmp_path):
    chain = renderer.build_crop_filter(WIDE, OUT, "tracked", path([]), MIDDLE, tmp_path / "t.cmd")
    assert chain == renderer.static_crop_filter(WIDE, OUT, MIDDLE)
    assert not (tmp_path / "t.cmd").exists()


def test_a_track_with_nowhere_to_write_falls_back_too():
    chain = renderer.build_crop_filter(WIDE, OUT, "tracked", path([0.4, 0.6]), MIDDLE, None)
    assert chain == renderer.static_crop_filter(WIDE, OUT, MIDDLE)


def test_asking_for_a_strategy_that_does_not_exist_is_an_error():
    with pytest.raises(ValueError):
        renderer.build_crop_filter(WIDE, OUT, "magic")


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="needs FFmpeg")
def test_the_window_really_moves_in_the_finished_video(tmp_path):
    """A marker sits on the right of a wide frame; the path walks the window onto it."""
    source = tmp_path / "wide.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "color=c=black:s=1920x1080:r=25:d=4",
         "-vf", "drawbox=x=1500:y=0:w=300:h=1080:color=white:t=fill",
         "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", str(source)],
        check=True)
    info = renderer.probe(source)
    subs = tmp_path / "subs.ass"
    from backend.models import Style, Transcript
    from backend.subtitles import write_ass
    write_ass(Transcript(language="nl", segments=[]), Style(), OUT, subs)

    walking = path([0.5 + min(0.35, i * 0.02) for i in range(50)])
    out = tmp_path / "moved.mp4"
    renderer.render_video(source, info, subs, OUT, out, crop_strategy="tracked",
                          track=walking, crop=MIDDLE)

    def brightness(at: float) -> float:
        frame = tmp_path / f"f{at}.pgm"
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", str(at), "-i", str(out),
                        "-frames:v", "1", "-update", "1", str(frame)], check=True)
        raw = frame.read_bytes()
        body = raw.split(b"255\n", 1)[1]
        return sum(body) / len(body)

    assert brightness(0.1) < brightness(3.5), "the white bar never came into frame"
