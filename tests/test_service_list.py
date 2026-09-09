"""What there is to go back to.

Putting a service away to start another must not mean losing it: the text took half an hour
and the found moments cost money. This is the list that keeps them one click away.
"""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from backend import main, models
from backend.models import ClipCandidate, ProcessedClip, Service, VideoInfo


@pytest.fixture
def client(tmp_path, monkeypatch):
    folder = tmp_path / "services"
    folder.mkdir()
    monkeypatch.setattr(models, "SERVICES_DIR", folder)
    monkeypatch.setattr(main, "SERVICES_DIR", folder)
    with TestClient(main.app) as running:
        yield running


def when(days_ago: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat(timespec="seconds")


def a_service(sid: str, days_ago: float = 0, *, recording: bool = True, on_disk: bool = True,
              status: str = "uploaded", clips: int = 0, moments: int = 0,
              title: str = "Kerkdienst") -> Service:
    folder = models.service_dir(sid)
    folder.mkdir(parents=True, exist_ok=True)
    service = Service(id=sid, createdAt=when(days_ago), title=title, status=status)
    if recording:
        service.sourceVideo = "source.mp4"
        service.sourceInfo = VideoInfo(width=1280, height=720, duration=5400, fps=25,
                                       videoCodec="h264", hasAudio=True, audioCodec="aac",
                                       audioSampleRate=48000, audioChannels=2)
        if on_disk:
            (folder / "source.mp4").write_bytes(b"x")
    service.candidates = [ClipCandidate(id=f"c{i}", start=i * 10, end=i * 10 + 40, title="m")
                          for i in range(moments)]
    service.clips = [ProcessedClip(candidateId=f"c{i}", projectId=f"p{i}", title="c",
                                   start=0, end=40, createdAt=when(days_ago)) for i in range(clips)]
    models.save_service(service)
    return service


def test_nothing_worked_on_yet_is_an_empty_list(client):
    assert client.get("/services").json() == []


def test_the_services_worked_on_come_back_newest_first(client):
    a_service("service-old", days_ago=21, title="Oud")
    a_service("service-new", days_ago=1, title="Nieuw")
    a_service("service-mid", days_ago=7, title="Midden")
    assert [s["title"] for s in client.get("/services").json()] == ["Nieuw", "Midden", "Oud"]


def test_a_service_that_never_got_a_recording_is_not_listed(client):
    """Pressing Ophalen and changing your mind should not leave a stub in the list."""
    a_service("service-real")
    a_service("service-stub", recording=False)
    assert [s["id"] for s in client.get("/services").json()] == ["service-real"]


def test_a_recording_that_was_cleaned_up_is_still_worth_coming_back_to(client):
    """The text and the clips are the part that took the time; they are still there."""
    a_service("service-gone", on_disk=False, status="complete", clips=3)
    only = client.get("/services").json()[0]
    assert only["hasFootage"] is False
    assert only["clips"] == 3


def test_each_entry_says_what_it_is_worth_opening_for(client):
    a_service("service-1", status="ready", moments=6, clips=2)
    only = client.get("/services").json()[0]
    assert only == {"id": "service-1", "title": "Kerkdienst", "status": "ready",
                    "createdAt": only["createdAt"], "duration": 5400.0,
                    "hasFootage": True, "clips": 2, "moments": 6}


def test_a_damaged_service_file_does_not_empty_the_list(client):
    a_service("service-fine")
    broken = models.service_dir("service-broken")
    broken.mkdir(parents=True)
    (broken / "service.json").write_text("{ this is not json", encoding="utf-8")
    assert [s["id"] for s in client.get("/services").json()] == ["service-fine"]


def test_the_list_stays_short_enough_to_read(client):
    for i in range(20):
        a_service(f"service-{i:02d}", days_ago=i)
    assert len(client.get("/services").json()) == 12
    assert len(client.get("/services?limit=3").json()) == 3
    assert len(client.get("/services?limit=999").json()) == 20, "capped at 50, and there are 20"
    assert len(client.get("/services?limit=0").json()) == 1, "never nothing"
