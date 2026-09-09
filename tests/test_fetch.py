"""Bringing a service in from a link: which links are worth trying, and what to say when not."""

from pathlib import Path

import pytest

from backend import fetch
from backend.jobs import Cancelled


@pytest.mark.parametrize("typed, want", [
    ("https://youtu.be/abc", "https://youtu.be/abc"),
    ("  https://youtu.be/abc  ", "https://youtu.be/abc"),
    ("<https://youtu.be/abc>", "https://youtu.be/abc"),
    ('"https://youtu.be/abc"', "https://youtu.be/abc"),
    # Pasted from a browser's address bar, which hides the scheme.
    ("youtube.com/watch?v=abc", "https://youtube.com/watch?v=abc"),
    ("www.kerk.nl/dienst.mp4", "https://www.kerk.nl/dienst.mp4"),
])
def test_a_pasted_address_is_taken_as_meant(typed, want):
    assert fetch.tidy(typed) == want


@pytest.mark.parametrize("typed", ["", "   ", "de dienst van vorige week", "file:///C:/dienst.mp4",
                                   "javascript:alert(1)", "ftp://kerk.nl/dienst.mp4"])
def test_something_that_is_not_a_web_address_is_refused(typed):
    with pytest.raises(fetch.LinkNotUsable) as caught:
        fetch.tidy(typed)
    assert "webadres" in str(caught.value)


def test_a_link_straight_to_a_video_is_recognised():
    assert fetch.is_direct_media("https://kerk.nl/media/dienst.mp4")
    assert fetch.is_direct_media("https://kerk.nl/live/index.m3u8?token=x")
    assert not fetch.is_direct_media("https://www.youtube.com/watch?v=abc")


def test_the_host_is_read_without_its_www():
    assert fetch.host("https://www.kerkdienstgemist.nl/stations/1") == "kerkdienstgemist.nl"


@pytest.mark.parametrize("url", [
    "https://kerkdienstgemist.nl/stations/1341/events/recording/178807680001341",
    "https://www.kerkdienstgemist.nl/stations/1341",
    "https://media.kerkdienstgemist.nl/x",
])
def test_a_site_that_hides_its_video_gets_told_what_does_work(url):
    """Its player fetches a signed address of its own, so the page address holds no video."""
    said = fetch.readable("ERROR: Unsupported URL: " + url, url)
    assert "Downloaden" in said or "Download" in said
    assert "unsupported" not in said.lower()


def test_an_unknown_site_without_a_video_says_what_to_try_instead():
    said = fetch.readable("ERROR: Unsupported URL: https://kerk.nl/dienst", "https://kerk.nl/dienst")
    assert "kerk.nl" in said and "YouTube" in said


@pytest.mark.parametrize("complaint, expect", [
    ("ERROR: Private video. Sign in if you've been granted access", "niet openbaar"),
    ("ERROR: unable to download video data: HTTP Error 404: Not Found", "niets (meer)"),
    ("ERROR: File is larger than max-filesize", "groter dan"),
    ("ERROR: The uploader has not made this video available in your country (geo block)", "Nederland"),
])
def test_the_common_complaints_are_said_in_dutch(complaint, expect):
    said = fetch.readable(complaint, "https://youtu.be/abc")
    assert expect in said
    assert not said.startswith("ERROR")


def test_a_complaint_we_have_no_words_for_is_still_passed_on():
    said = fetch.readable("ERROR: something we never thought of", "https://kerk.nl/x")
    assert "something we never thought of" in said


def test_the_report_this_issue_boilerplate_is_left_off():
    said = fetch.readable("ERROR: Unable to extract player; please report this issue on https://github.com/...",
                          "https://kerk.nl/x")
    assert "github" not in said


def test_a_title_is_trimmed_to_something_that_fits():
    assert fetch.safe_title("  Kerkdienst   ochtend \n 30 augustus ") == "Kerkdienst ochtend 30 augustus"
    assert fetch.safe_title("") == "Dienst"
    assert len(fetch.safe_title("x" * 300)) == 80


def test_half_downloaded_pieces_are_cleaned_up(tmp_path: Path):
    for name in ["source.mp4.part", "source.mp4.ytdl", "source.mp4.part-Frag1.part", "source.mp4"]:
        (tmp_path / name).write_bytes(b"x")
    fetch.sweep(tmp_path)
    assert [p.name for p in tmp_path.iterdir()] == ["source.mp4"]


def test_without_the_downloader_the_message_says_how_to_get_it(tmp_path, monkeypatch):
    import builtins
    real = builtins.__import__

    def missing(name, *args, **kwargs):
        if name == "yt_dlp":
            raise ImportError("no yt_dlp")
        return real(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", missing)
    with pytest.raises(fetch.LinkNotUsable) as caught:
        fetch.fetch("https://youtu.be/abc", tmp_path)
    assert "start.bat" in str(caught.value)


def test_stopping_is_a_cancellation_and_not_a_broken_link(tmp_path, monkeypatch):
    """The stop button must not read as "this link does not work"."""
    import yt_dlp

    def refuse(self, url, download=True):
        raise yt_dlp.utils.DownloadCancelled("stopped")

    monkeypatch.setattr(yt_dlp.YoutubeDL, "extract_info", refuse)
    with pytest.raises(Cancelled):
        fetch.fetch("https://youtu.be/abc", tmp_path)
