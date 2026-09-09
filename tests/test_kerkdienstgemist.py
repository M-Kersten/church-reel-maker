"""Kerkdienstgemist: the page holds no video, so its own player is asked where one is.

Every case here runs against a saved copy of what the API really answered for a real
service, so the shape being parsed is the shape that was there.
"""

import copy
import json
import urllib.error
from pathlib import Path

import pytest

from backend import fetch
from backend import kerkdienstgemist as kdg

PAGE = "https://kerkdienstgemist.nl/stations/1341/events/recording/178807680001341"
ANSWER = json.loads((Path(__file__).parent / "fixtures" / "kerkdienstgemist-recording.json")
                    .read_text(encoding="utf-8"))


@pytest.fixture
def answered(monkeypatch):
    """Answer every API call with the saved response, and record what was asked."""
    asked: list[str] = []

    def reply(url, timeout=kdg.TIMEOUT):
        asked.append(url)
        return copy.deepcopy(ANSWER)

    monkeypatch.setattr(kdg, "ask", reply)
    return asked


@pytest.mark.parametrize("url, yes", [
    (PAGE, True),
    ("https://www.kerkdienstgemist.nl/stations/1341", True),
    ("https://unsergottesdienst.de/stations/9/events/recording/1", True),
    ("https://www.youtube.com/watch?v=abc", False),
    ("https://kerkomroep.nl/#/kerken/1", False),
])
def test_only_this_platform_is_claimed(url, yes):
    assert kdg.handles(url) is yes


def test_both_ids_come_out_of_the_address():
    assert kdg.ids(PAGE) == ("1341", "178807680001341")
    assert kdg.ids("https://kerkdienstgemist.nl/stations/1341") is None


def test_the_api_sits_on_the_domain_you_are_looking_at():
    assert kdg.api_for(PAGE) == "https://api.kerkdienstgemist.nl/api/v2"
    assert kdg.api_for("https://www.unsergottesdienst.ch/stations/9") == "https://api.unsergottesdienst.ch/api/v2"


def test_the_download_link_behind_the_button_comes_back(answered):
    found = kdg.resolve(PAGE)
    assert found is not None
    assert found.url.startswith("https://s3.eu-west-1.amazonaws.com/media.kerkdienstgemist.nl/")
    assert found.url.split("?")[0].endswith(".mp4"), "a plain mp4, so the downloader needs no help"
    assert answered == ["https://api.kerkdienstgemist.nl/api/v2/stations/1341/recordings/"
                        "178807680001341?include=media"]


def test_the_recording_brings_the_name_the_church_gave_it(answered):
    assert kdg.resolve(PAGE).title == "Kerkdienst ochtend · 30 augustus 2026"


def test_what_the_platform_already_knows_is_kept(answered):
    found = kdg.resolve(PAGE)
    assert found.duration == 5753
    assert found.sermon_starts == 2822


@pytest.mark.parametrize("stamp, want", [
    ("2026-08-30T10:00:00+02:00", "30 augustus 2026"),
    ("2026-01-04T09:30:00+01:00", "4 januari 2026"),
    ("", ""),
    ("nonsense", ""),
])
def test_the_date_is_written_the_way_a_dutch_reader_writes_it(stamp, want):
    assert kdg.dutch_date(stamp) == want


@pytest.mark.parametrize("flag", ["locked", "private"])
def test_a_recording_the_church_shut_off_is_not_handed_out(monkeypatch, flag):
    shut = copy.deepcopy(ANSWER)
    shut["included"][0]["attributes"][flag] = True
    monkeypatch.setattr(kdg, "ask", lambda url, timeout=30: shut)
    assert kdg.resolve(PAGE) is None


def test_a_page_without_a_recording_in_it_is_not_asked_about(monkeypatch):
    monkeypatch.setattr(kdg, "ask", lambda *a, **k: pytest.fail("should not have asked"))
    assert kdg.resolve("https://kerkdienstgemist.nl/stations/1341") is None


@pytest.mark.parametrize("blow_up", [
    urllib.error.URLError("no route"),
    urllib.error.HTTPError("u", 500, "boom", {}, None),
    ValueError("not json"),
    TimeoutError("too slow"),
])
def test_the_api_falling_over_is_not_a_crash(monkeypatch, blow_up):
    def fail(*a, **k):
        raise blow_up

    monkeypatch.setattr(kdg, "ask", fail)
    assert kdg.resolve(PAGE) is None, "None means: try the ordinary route instead"


def test_a_shape_we_no_longer_recognise_is_not_a_crash(monkeypatch):
    monkeypatch.setattr(kdg, "ask", lambda *a, **k: {"data": "this used to be an object"})
    assert kdg.resolve(PAGE) is None


def test_an_answer_holding_no_video_file_gives_nothing(monkeypatch):
    monkeypatch.setattr(kdg, "ask", lambda *a, **k: {"data": {"attributes": {"title": "x"}}, "included": []})
    assert kdg.resolve(PAGE) is None


# --- how fetch.py uses it ------------------------------------------------------


def test_fetch_asks_the_resolver_before_the_downloader(answered):
    url, title = fetch.resolve(PAGE)
    assert url.split("?")[0].endswith(".mp4")
    assert title == "Kerkdienst ochtend · 30 augustus 2026"


def test_a_link_this_platform_does_not_own_is_left_alone():
    assert fetch.resolve("https://www.youtube.com/watch?v=abc") is None


def test_when_the_resolver_gives_up_the_reader_is_told_what_to_do_instead(monkeypatch):
    """The route can stop working; the note has to survive it."""
    monkeypatch.setattr(kdg, "resolve", lambda url, timeout=30: None)
    assert fetch.resolve(PAGE) is None
    said = fetch.readable("ERROR: Unsupported URL: " + PAGE, PAGE)
    assert "Downloaden" in said and "plak die link hier" in said


def test_a_failure_after_resolving_still_names_the_site_you_pasted(tmp_path, monkeypatch, answered):
    """The download link lives on amazonaws.com; the advice is about Kerkdienstgemist."""
    import yt_dlp

    def refuse(self, url, download=True):
        raise yt_dlp.utils.DownloadError("ERROR: Unsupported URL: " + url)

    monkeypatch.setattr(yt_dlp.YoutubeDL, "extract_info", refuse)
    with pytest.raises(fetch.LinkNotUsable) as caught:
        fetch.fetch(PAGE, tmp_path)
    assert "Kerkdienstgemist" in str(caught.value)
    assert "amazonaws" not in str(caught.value)


# --- the church's own list of services ------------------------------------------

ABOUT = json.loads((Path(__file__).parent / "fixtures" / "kerkdienstgemist-station.json")
                   .read_text(encoding="utf-8"))
LISTING = json.loads((Path(__file__).parent / "fixtures" / "kerkdienstgemist-recordings.json")
                     .read_text(encoding="utf-8"))


@pytest.fixture
def listed(monkeypatch):
    """Answer the two calls a listing takes, and record what was asked."""
    asked: list[str] = []

    def reply(url, timeout=kdg.TIMEOUT):
        asked.append(url)
        return copy.deepcopy(LISTING if url.endswith("/recordings?include=media") else ABOUT)

    monkeypatch.setattr(kdg, "ask", reply)
    return asked


def test_a_station_number_brings_back_the_church_and_its_services(listed):
    found = kdg.station("1341")
    assert found.name == "Nieuwe Kerk Utrecht (Wittevrouwen)"
    assert found.url == "https://kerkdienstgemist.nl/stations/1341"
    assert len(found.services) == 10
    assert listed == ["https://api.kerkdienstgemist.nl/api/v2/stations/1341",
                      "https://api.kerkdienstgemist.nl/api/v2/stations/1341/recordings?include=media"]


def test_each_service_carries_what_it_takes_to_choose_and_to_fetch(listed):
    first = kdg.station("1341").services[0]
    assert first.title == "Kerkdienst ochtend"
    assert first.when.startswith("2026-09-06T10:00")
    assert first.duration == 5398
    # The page address, which is the one thing the app already knows how to fetch.
    assert first.url == f"https://kerkdienstgemist.nl/stations/1341/events/recording/{first.id}"


def test_the_newest_service_is_at_the_top(listed):
    when = [s.when for s in kdg.station("1341").services]
    assert when == sorted(when, reverse=True)


@pytest.mark.parametrize("where, flag", [
    ("recording", "private"), ("video", "locked"), ("video", "private"),
])
def test_a_service_that_cannot_be_had_is_left_out(monkeypatch, where, flag):
    shut = copy.deepcopy(LISTING)
    if where == "recording":
        shut["data"][0]["attributes"][flag] = True
    else:
        held = shut["data"][0]["relationships"]["media"]["data"][0]["id"]
        next(m for m in shut["included"] if m["id"] == held)["attributes"][flag] = True

    monkeypatch.setattr(kdg, "ask",
                        lambda url, timeout=30: copy.deepcopy(shut if "recordings" in url else ABOUT))
    left = kdg.station("1341").services
    assert len(left) == 9
    assert LISTING["data"][0]["id"] not in [s.id for s in left]


@pytest.mark.parametrize("typed", ["", "  ", "abc", "13 41", "1341x", "-1"])
def test_a_number_that_is_not_a_number_never_reaches_the_platform(monkeypatch, typed):
    monkeypatch.setattr(kdg, "ask", lambda *a, **k: pytest.fail("should not have asked"))
    with pytest.raises(kdg.NotFound) as caught:
        kdg.station(typed)
    assert "cijfers" in str(caught.value)


def test_a_church_that_is_not_there_says_so_with_the_number_in_it(monkeypatch):
    def gone(url, timeout=30):
        raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)

    monkeypatch.setattr(kdg, "ask", gone)
    with pytest.raises(kdg.NotFound) as caught:
        kdg.station("999999")
    assert "999999" in str(caught.value)


def test_no_connection_says_so_rather_than_blaming_the_number(monkeypatch):
    def down(url, timeout=30):
        raise urllib.error.URLError("no route to host")

    monkeypatch.setattr(kdg, "ask", down)
    with pytest.raises(kdg.NotFound) as caught:
        kdg.station("1341")
    assert "verbinding" in str(caught.value)


def test_a_shape_we_no_longer_recognise_points_at_pasting_the_address(monkeypatch):
    monkeypatch.setattr(kdg, "ask", lambda url, timeout=30: {"data": "not an object any more"})
    with pytest.raises(kdg.NotFound) as caught:
        kdg.station("1341")
    assert "adres van de dienst" in str(caught.value)


def test_the_endpoint_hands_the_page_what_it_needs(listed):
    from fastapi.testclient import TestClient

    from backend.main import app

    with TestClient(app) as client:
        answer = client.get("/kerkdienstgemist/stations/1341")
    assert answer.status_code == 200
    said = answer.json()
    assert said["name"] == "Nieuwe Kerk Utrecht (Wittevrouwen)"
    assert len(said["services"]) == 10
    assert set(said["services"][0]) == {"id", "title", "when", "url", "duration"}


def test_a_number_the_platform_will_not_talk_about_is_a_400_with_the_reason(monkeypatch):
    from fastapi.testclient import TestClient

    from backend.main import app

    monkeypatch.setattr(kdg, "ask", lambda *a, **k: pytest.fail("should not have asked"))
    with TestClient(app) as client:
        answer = client.get("/kerkdienstgemist/stations/nope")
    assert answer.status_code == 400
    assert "cijfers" in answer.json()["detail"]
