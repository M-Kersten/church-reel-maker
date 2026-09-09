"""The end screen: the logo has to arrive with the text, not before it."""

import os
from pathlib import Path

import pytest

from backend import outro
from backend.models import OutroConfig


def config(**kwargs) -> OutroConfig:
    kwargs = {"duration": 4.0, "fade": 0.6, **kwargs}
    cfg = OutroConfig(**kwargs)
    cfg.logo.file = ""
    return cfg


def graph(command: list[str]) -> str:
    return command[command.index("-filter_complex") + 1]


def with_logo(tmp_path: Path, **kwargs) -> tuple[OutroConfig, Path]:
    logo = outro.TEMPLATES_DIR / "logos" / "testlogo.png"
    if not logo.is_file():
        pytest.skip("templates/logos/testlogo.png is er niet")
    cfg = config(**kwargs)
    cfg.logo.file = logo.name
    return cfg, tmp_path


def test_logo_fades_over_the_same_seconds_as_the_text():
    cfg = config()
    cfg.logo.file = "whatever.png"
    chain = outro.logo_chain(cfg, 1.0)
    assert "fade=t=in:st=0:d=0.6:alpha=1" in chain
    assert "fade=t=out:st=3.4:d=0.6:alpha=1" in chain
    # Without alpha there is nothing to fade.
    assert chain.index("format=rgba") < chain.index("fade=t=in")


def test_a_fade_of_nothing_leaves_the_logo_alone():
    cfg = config(fade=0.0)
    cfg.logo.file = "whatever.png"
    assert "fade" not in outro.logo_chain(cfg, 1.0)


def test_logo_is_scaled_with_the_oversized_background():
    cfg = config()
    cfg.logo.file = "whatever.png"
    cfg.logo.width = 420
    assert "scale=420:-1" in outro.logo_chain(cfg, 1.0)
    assert f"scale={420 * outro.SUPER}:-1" in outro.logo_chain(cfg, float(outro.SUPER))


def test_the_camera_carries_the_logo(tmp_path):
    """The logo is composited before the move, so it travels with the background."""
    cfg, _ = with_logo(tmp_path, motion="in")
    steps = graph(outro.build_command(cfg, tmp_path / "bg.png", tmp_path / "o.ass", outro.BIG_W, tmp_path / "o.mp4"))
    assert steps.index("overlay") < steps.index("zoompan")
    # And the text is drawn after it, on the finished frame.
    assert steps.index("zoompan") < steps.index("ass=filename=")


def test_without_a_logo_nothing_is_overlaid(tmp_path):
    steps = graph(outro.build_command(config(), tmp_path / "bg.png", tmp_path / "o.ass", outro.WIDTH, tmp_path / "o.mp4"))
    assert "overlay" not in steps
    assert "[0:v]null[card]" in steps


def test_the_silent_track_is_mapped_whether_or_not_there_is_a_logo(tmp_path):
    plain = outro.build_command(config(), tmp_path / "bg.png", tmp_path / "o.ass", outro.WIDTH, tmp_path / "o.mp4")
    assert plain[plain.index("-map") + 3] == "1:a"
    cfg, _ = with_logo(tmp_path)
    logo = outro.build_command(cfg, tmp_path / "bg.png", tmp_path / "o.ass", outro.WIDTH, tmp_path / "o.mp4")
    assert logo[logo.index("-map") + 3] == "2:a"


def test_the_background_still_no_longer_holds_the_logo(tmp_path, monkeypatch):
    """A still cannot fade, so the logo must not be baked into it."""
    seen: list[list[str]] = []

    class Done:
        returncode = 0
        stderr = ""

    monkeypatch.setattr(outro.subprocess, "run", lambda cmd, **kw: seen.append(cmd) or Done())
    cfg, _ = with_logo(tmp_path)
    outro.background_still(cfg, outro.WIDTH, outro.HEIGHT, tmp_path / "bg.png")
    assert "overlay" not in " ".join(seen[0])


def test_a_changed_way_of_drawing_rebuilds_the_end_screen(monkeypatch, tmp_path):
    """A pull changes outro.py, not the brand file; the video must still be made again."""
    built: list[str] = []
    video = tmp_path / "outro.mp4"
    video.write_bytes(b"old")
    monkeypatch.setattr(outro, "OUTRO_PATH", video)
    monkeypatch.setattr(outro, "build", lambda *a, **k: built.append("built") or video)
    monkeypatch.setattr(outro.brands, "migrate", lambda: None)

    # The video is younger than the brand, so nothing but the code can ask for a rebuild.
    old = video.stat().st_mtime
    for source in (outro.brands.ACTIVE_FILE, outro.brands.path_for(outro.brands.active().id)):
        if source.is_file():
            os.utime(source, (old - 100, old - 100))
    outro.ensure_outro()
    assert built == [], "nothing changed, nothing is remade"

    os.utime(video, (old - 100, old - 100))  # this file is now older than backend/outro.py
    outro.ensure_outro()
    assert built == ["built"]
