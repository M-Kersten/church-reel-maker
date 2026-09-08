"""Subtitle wrapping and ASS generation: what the viewer actually reads."""

import pytest

from backend.models import Output, Segment, Style, Transcript
from backend.subtitles import (MAX_LINES, MIN_FONT_SCALE, SAFE_MARGIN_SIDE, animation_tags,
                               ass_color, ass_time, escape_text, family_for, layout_text,
                               wrap_words, write_ass)
from tests.cases import LAYOUT_SIZES, LAYOUT_TEXTS

OUT = Output()


@pytest.mark.parametrize("size", LAYOUT_SIZES)
@pytest.mark.parametrize("text", LAYOUT_TEXTS)
def test_layout_never_exceeds_max_lines(text, size):
    lines, _ = layout_text(text, Style(fontSize=size), OUT)
    assert 1 <= len(lines) <= MAX_LINES


@pytest.mark.parametrize("size", LAYOUT_SIZES)
@pytest.mark.parametrize("text", LAYOUT_TEXTS)
def test_layout_keeps_every_word_in_order(text, size):
    lines, _ = layout_text(text, Style(fontSize=size), OUT)
    assert " ".join(lines).split() == text.split()


@pytest.mark.parametrize("size", LAYOUT_SIZES)
@pytest.mark.parametrize("text", LAYOUT_TEXTS)
def test_layout_shrinks_only_within_bounds(text, size):
    _, chosen = layout_text(text, Style(fontSize=size), OUT)
    assert int(size * MIN_FONT_SCALE) - 1 <= chosen <= size


def test_a_bigger_font_is_never_rendered_smaller_than_a_smaller_one():
    """Turning the size up must not turn the text on screen down."""
    text = "Niet omdat je perfect bent, maar omdat hij van je houdt."
    previous = 0
    for size in LAYOUT_SIZES:
        _, chosen = layout_text(text, Style(fontSize=size), OUT)
        assert chosen >= previous, f"{size} rendered smaller than the size before it"
        previous = chosen


def test_short_text_is_left_alone():
    lines, size = layout_text("Genade", Style(fontSize=64), OUT)
    assert lines == ["Genade"] and size == 64


def test_lines_fit_the_safe_width_when_the_font_is_not_shrunk():
    style = Style(fontSize=48)
    for text in LAYOUT_TEXTS:
        lines, chosen = layout_text(text, style, OUT)
        if chosen < style.fontSize:
            continue  # already shrunk: the width is as close as it can get
        available = OUT.width - 2 * SAFE_MARGIN_SIDE
        assert max(len(line) for line in lines) * chosen * 0.58 <= available + 1


def test_wrap_words_respects_the_width_it_can():
    lines = wrap_words("een twee drie vier vijf zes".split(), 10)
    assert all(len(line) <= 10 for line in lines)
    assert " ".join(lines) == "een twee drie vier vijf zes"


def test_single_long_word_is_never_broken():
    lines, _ = layout_text("Onvoorstelbaarheid", Style(fontSize=200), OUT)
    assert lines == ["Onvoorstelbaarheid"]


def test_ass_color_is_bgr_with_alpha():
    assert ass_color("#FFFFFF") == "&H00FFFFFF"
    assert ass_color("#4B1E78") == "&H00781E4B"
    assert ass_color("bogus") == "&H00FFFFFF"
    assert ass_color("#000000", 0x80) == "&H80000000"


def test_ass_time_format():
    assert ass_time(0) == "0:00:00.00"
    assert ass_time(61.5) == "0:01:01.50"
    assert ass_time(3661.25) == "1:01:01.25"
    assert ass_time(-5) == "0:00:00.00"


def test_escape_text_neutralises_override_blocks():
    assert escape_text("een {\\fs99} twee") == "een (\\fs99) twee"
    assert "\n" not in escape_text("een\ntwee")


@pytest.mark.parametrize("weight,expected", [
    ("regular", ("Montserrat", False)),
    ("bold", ("Montserrat", True)),
    ("medium", ("Montserrat Medium", False)),
    ("semibold", ("Montserrat SemiBold", False)),
    ("extrabold", ("Montserrat ExtraBold", False)),
])
def test_family_naming_matches_what_libass_finds(weight, expected):
    assert family_for("Montserrat", weight) == expected


@pytest.mark.parametrize("animation,marker", [
    ("none", ""),
    ("fade", "\\fad"),
    ("pop", "\\fscx"),
    ("slide", "\\move"),
])
def test_animation_tags(animation, marker):
    tags = animation_tags(Style(animation=animation, animationSpeed=200), OUT)
    assert marker in tags if marker else tags == ""


def test_ass_file_is_stable(tmp_path):
    """A frozen transcript renders a byte-identical ASS file.

    This is the canary for the whole subtitle path: wrapping, sizing, colours, timing
    and animation all end up in these bytes.
    """
    transcript = Transcript(language="nl", segments=[
        Segment(start=0.0, end=2.16, text="God is op zoek naar jou"),
        Segment(start=2.6, end=5.08, text="Hij wil dat je dichter bij hem komt."),
        Segment(start=5.48, end=9.52, text="Niet omdat je perfect bent, maar omdat hij van je houdt."),
    ])
    style = Style(font="Montserrat", fontSize=64, fontWeight="bold", outline=4, animation="fade",
                  animationSpeed=180)
    written = tmp_path / "subs.ass"
    write_ass(transcript, style, Output(), written)
    expected = (__import__("pathlib").Path(__file__).parent / "fixtures" / "subtitles.ass")
    if not expected.is_file():  # first run records the baseline
        expected.write_text(written.read_text(encoding="utf-8"), encoding="utf-8")
    assert written.read_text(encoding="utf-8") == expected.read_text(encoding="utf-8")
