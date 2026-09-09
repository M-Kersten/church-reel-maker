"""The two things the clip page asks for: look for the speaker, and follow them or not."""

import pytest
from fastapi.testclient import TestClient

from backend import main, models, tracking
from backend.models import Output, Project, Track, VideoInfo


@pytest.fixture
def client(tmp_path, monkeypatch):
    folder = tmp_path / "projects"
    folder.mkdir()
    monkeypatch.setattr(models, "PROJECTS_DIR", folder)
    with TestClient(main.app) as running:
        yield running


def a_project(pid: str = "clip", track: Track | None = None) -> Project:
    models.project_dir(pid).mkdir(parents=True, exist_ok=True)
    project = Project(
        id=pid, createdAt="2026-01-01T10:00:00", title="Fragment",
        sourceVideo="source.mp4", output=Output(),
        sourceInfo=VideoInfo(width=1920, height=1080, duration=30.0, fps=25.0, videoCodec="h264",
                             hasAudio=True, audioCodec="aac", audioSampleRate=48000,
                             audioChannels=2),
        track=track)
    (models.project_dir(pid) / "source.mp4").write_bytes(b"not really a video")
    models.save_project(project)
    return project


def a_track(count: int = 30) -> Track:
    return Track(fps=12.5, x=[0.5] * count, coverage=0.9, subject="face", cuts=[], jumps=[],
                 enough=True)


# --- following or not -------------------------------------------------------------


def test_a_clip_with_a_path_can_be_told_to_follow(client):
    a_project(track=a_track())
    answer = client.put("/projects/clip/framing", json={"follow": True})
    assert answer.status_code == 200
    assert answer.json()["cropStrategy"] == "tracked"
    assert models.load_project("clip").cropStrategy == "tracked"


def test_going_back_to_framing_by_hand_keeps_the_path(client):
    a_project(track=a_track())
    client.put("/projects/clip/framing", json={"follow": True})
    answer = client.put("/projects/clip/framing", json={"follow": False})
    assert answer.json()["cropStrategy"] == "static"
    kept = models.load_project("clip")
    assert kept.track is not None and len(kept.track.x) == 30, "it can be switched back on"


def test_a_clip_without_a_path_cannot_be_told_to_follow(client):
    a_project()
    answer = client.put("/projects/clip/framing", json={"follow": True})
    assert answer.status_code == 400
    assert "pad" in answer.json()["detail"]


def test_framing_a_clip_that_is_not_there(client):
    assert client.put("/projects/nope/framing", json={"follow": False}).status_code == 404


# --- looking for the speaker ------------------------------------------------------


def test_the_path_comes_back_with_its_job(client):
    a_project(track=a_track())
    answer = client.get("/projects/clip/track").json()
    assert answer["job"]["status"] == "idle"
    assert answer["cropStrategy"] == "static"
    assert len(answer["track"]["x"]) == 30


def test_a_clip_that_was_never_looked_at_says_so(client):
    a_project()
    answer = client.get("/projects/clip/track").json()
    assert answer["track"] is None


def test_looking_for_the_speaker_stores_what_it_finds(client, monkeypatch):
    a_project()
    monkeypatch.setattr(tracking, "build", lambda *a, **k: a_track())
    assert client.post("/projects/clip/track").status_code == 200
    answer = client.get("/projects/clip/track").json()
    assert answer["job"]["status"] == "done"
    assert answer["cropStrategy"] == "tracked", "a clip it can follow opens following"
    assert len(answer["track"]["x"]) == 30


def test_a_path_too_thin_to_trust_is_kept_but_not_switched_on(client, monkeypatch):
    a_project()
    thin = Track(fps=12.5, x=[0.5] * 30, coverage=0.2, subject="face", cuts=[], jumps=[],
                 enough=False)
    monkeypatch.setattr(tracking, "build", lambda *a, **k: thin)
    client.post("/projects/clip/track")
    answer = client.get("/projects/clip/track").json()
    assert answer["cropStrategy"] == "static"
    assert answer["track"]["coverage"] == 0.2, "the user can still turn it on and look"


def test_a_search_that_fails_says_why_rather_than_going_quiet(client, monkeypatch):
    a_project()

    def cross(*a, **k):
        raise RuntimeError("Het herkenningsmodel kon niet opgehaald worden")

    monkeypatch.setattr(tracking, "build", cross)
    client.post("/projects/clip/track")
    job = client.get("/projects/clip/track").json()["job"]
    assert job["status"] == "error"
    assert "herkenningsmodel" in job["error"]


def test_cutting_a_service_up_is_not_held_back_by_a_clip_that_will_not_follow(monkeypatch):
    """The same failure, on the batch path, leaves the clip alone and carries on."""
    project = Project(id="x", createdAt="2026-01-01T10:00:00", output=Output())

    def cross(*a, **k):
        raise RuntimeError("geen model")

    monkeypatch.setattr(tracking, "build", cross)
    assert main.follow_speaker(project) is project
    assert project.track is None and project.cropStrategy == "static"


def test_looking_twice_at_once_is_refused(client, monkeypatch):
    a_project()
    monkeypatch.setattr(main.jobs, "is_running", lambda key: key.endswith(":track"))
    assert client.post("/projects/clip/track").status_code == 409


def test_the_search_has_its_own_progress_apart_from_the_render(client):
    a_project()
    assert main.track_key("clip") != "clip", "a render and a search must not share a job"


def test_looking_at_a_clip_that_is_not_there(client):
    assert client.post("/projects/nope/track").status_code == 404
    assert client.get("/projects/nope/track").status_code == 404
