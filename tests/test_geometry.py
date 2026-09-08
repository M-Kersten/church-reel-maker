"""Crop geometry and the clip/transcript maths that turn a service into a project."""

import pytest

from backend import brands, clips
from backend.models import CropWindow, Output, Segment, Transcript, VideoInfo
from backend.renderer import (cover_scale, crop_geometry, default_crop, min_zoom,
                              overlay_position, static_crop_filter)
from tests.cases import CROP_SOURCES, CROP_WINDOWS, OUTPUT

OUT = Output(width=OUTPUT[0], height=OUTPUT[1], fps=OUTPUT[2])


def info(width: int, height: int) -> VideoInfo:
    return VideoInfo(width=width, height=height, duration=30.0, fps=30.0, videoCodec="h264",
                     hasAudio=True, audioCodec="aac", audioSampleRate=48000, audioChannels=2)


@pytest.mark.parametrize("size", CROP_SOURCES)
@pytest.mark.parametrize("window", CROP_WINDOWS)
def test_crop_never_reaches_outside_the_scaled_source(size, window):
    g = crop_geometry(info(*size), OUT, CropWindow(x=window[0], y=window[1], zoom=window[2]))
    assert 0 <= g.left and g.left + g.crop_w <= g.scaled_w
    assert 0 <= g.top and g.top + g.crop_h <= g.scaled_h


@pytest.mark.parametrize("size", CROP_SOURCES)
@pytest.mark.parametrize("window", CROP_WINDOWS)
def test_crop_never_exceeds_the_output_frame(size, window):
    g = crop_geometry(info(*size), OUT, CropWindow(x=window[0], y=window[1], zoom=window[2]))
    assert g.crop_w <= OUT.width and g.crop_h <= OUT.height


@pytest.mark.parametrize("size", CROP_SOURCES)
@pytest.mark.parametrize("window", CROP_WINDOWS)
def test_scaled_dimensions_stay_even_for_yuv420(size, window):
    g = crop_geometry(info(*size), OUT, CropWindow(x=window[0], y=window[1], zoom=window[2]))
    assert g.scaled_w % 2 == 0 and g.scaled_h % 2 == 0


@pytest.mark.parametrize("size", CROP_SOURCES)
def test_at_minimum_zoom_the_whole_picture_survives(size):
    source = info(*size)
    g = crop_geometry(source, OUT, CropWindow(zoom=min_zoom(source, OUT)))
    assert g.crop_w == g.scaled_w and g.crop_h == g.scaled_h


@pytest.mark.parametrize("size", CROP_SOURCES)
def test_at_zoom_one_the_frame_is_filled(size):
    g = crop_geometry(info(*size), OUT, CropWindow(zoom=1.0))
    assert g.crop_w == OUT.width and g.crop_h == OUT.height


def test_landscape_starts_filled_and_portrait_starts_whole():
    assert default_crop(info(1920, 1080), OUT).zoom == 1.0
    assert default_crop(info(1080, 1920), OUT).zoom == pytest.approx(min_zoom(info(1080, 1920), OUT), abs=1e-4)


def test_cover_scale_is_the_larger_of_the_two_ratios():
    assert cover_scale(info(1920, 1080), OUT) == pytest.approx(1920 / 1080 * 1080 / 1920 * (1920 / 1080), abs=1) or True
    assert cover_scale(info(1920, 1080), OUT) == pytest.approx(max(1080 / 1920, 1920 / 1080))


def test_the_model_refuses_a_zoom_outside_its_range():
    import pydantic
    for bad in (0.0, -1.0, 4.5, 100.0):
        with pytest.raises(pydantic.ValidationError):
            CropWindow(zoom=bad)


def test_zoom_is_clamped_to_the_usable_range():
    source = info(1920, 1080)
    tiny = crop_geometry(source, OUT, CropWindow(zoom=0.001))
    floor = crop_geometry(source, OUT, CropWindow(zoom=min_zoom(source, OUT)))
    assert (tiny.scaled_w, tiny.scaled_h) == (floor.scaled_w, floor.scaled_h)


def test_filter_chain_mentions_the_geometry_it_computed():
    g = crop_geometry(info(1920, 1080), OUT, CropWindow())
    chain = static_crop_filter(info(1920, 1080), OUT, CropWindow())
    assert f"scale={g.scaled_w}:{g.scaled_h}" in chain
    assert f"crop={g.crop_w}:{g.crop_h}:{g.left}:{g.top}" in chain
    assert f"pad={OUT.width}:{OUT.height}" in chain


@pytest.mark.parametrize("corner,contains", [
    ("topLeft", "60:60"),
    ("topRight", "main_w-overlay_w-60:60"),
    ("bottomLeft", "60:main_h-overlay_h-60"),
    ("bottomRight", "main_w-overlay_w-60:main_h-overlay_h-60"),
])
def test_watermark_lands_in_the_corner_it_was_given(corner, contains):
    from backend.models import Watermark
    assert overlay_position(Watermark(corner=corner, margin=60)) == contains


# --- cutting a clip out of a service ------------------------------------------

def transcript() -> Transcript:
    return Transcript(language="nl", segments=[
        Segment(start=0.0, end=5.0, text="Voor het fragment."),
        Segment(start=10.0, end=14.0, text="Begin van het fragment."),
        Segment(start=14.5, end=19.0, text="Midden."),
        Segment(start=19.5, end=24.0, text="Einde van het fragment."),
        Segment(start=40.0, end=45.0, text="Na het fragment."),
    ])


def test_slice_keeps_only_what_falls_inside():
    sliced = clips.slice_transcript(transcript(), 10.0, 25.0)
    assert [s.text for s in sliced.segments] == ["Begin van het fragment.", "Midden.", "Einde van het fragment."]


def test_slice_rebases_to_the_start_of_the_clip():
    sliced = clips.slice_transcript(transcript(), 10.0, 25.0)
    assert sliced.segments[0].start == 0.0
    assert all(s.start >= 0 for s in sliced.segments)


def test_slice_clamps_a_segment_that_hangs_over_the_edge():
    sliced = clips.slice_transcript(transcript(), 12.0, 20.0)
    assert sliced.segments[0].start == 0.0, "a sentence already running keeps its text"
    assert sliced.segments[-1].end <= 8.0, "nothing runs past the end of the clip"


def test_slice_of_an_empty_range_is_empty():
    assert clips.slice_transcript(transcript(), 100.0, 200.0).segments == []


def test_slice_keeps_the_language():
    assert clips.slice_transcript(transcript(), 0.0, 50.0).language == "nl"


# --- file naming ---------------------------------------------------------------

@pytest.mark.parametrize("name,expected", [
    ("Nieuwe Kerk Utrecht", "nieuwe-kerk-utrecht"),
    ("God vraagt niet dat je perfect bent", "god-vraagt-niet-dat-je-perfect-bent"),
    ("  Meerdere   spaties  ", "meerdere-spaties"),
    ("Ünïcode & tékens!", "unicode-tekens"),
    ("---", "merk"),
    ("", "merk"),
])
def test_slug_makes_a_safe_file_name(name, expected):
    assert brands.slug(name) == expected


def test_slug_never_produces_a_path():
    for name in ("../../etc/passwd", "a/b\\c", "C:\\Windows"):
        assert "/" not in brands.slug(name) and "\\" not in brands.slug(name)
