"""Retention: what may be thrown away, and what must survive it."""

from datetime import datetime, timedelta, timezone

import pytest

from backend import models, storage
from backend.models import ClipOrigin, Project, Service


@pytest.fixture
def disk(tmp_path, monkeypatch):
    """A projects and services tree of its own, so a test never touches real recordings."""
    for name, path in (("PROJECTS_DIR", tmp_path / "projects"), ("SERVICES_DIR", tmp_path / "services")):
        path.mkdir(parents=True)
        monkeypatch.setattr(models, name, path)
        monkeypatch.setattr(storage, name, path)
    return tmp_path


def when(days_ago: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat(timespec="seconds")


def a_service(days_ago: float = 0.0, recording_mb: int = 3, work_mb: int = 1,
              transcript: bool = True, sid: str = "service-1") -> Service:
    folder = models.service_dir(sid)
    (folder / "work").mkdir(parents=True, exist_ok=True)
    (folder / "source.mp4").write_bytes(b"x" * recording_mb * 1_000_000)
    (folder / "work" / "audio.wav").write_bytes(b"y" * work_mb * 1_000_000)
    service = Service(id=sid, createdAt=when(days_ago), title="Dienst", sourceVideo="source.mp4",
                      transcript="transcript.json" if transcript else None)
    models.save_service(service)
    if transcript:
        (folder / "transcript.json").write_text('{"language":"nl","segments":[]}', encoding="utf-8")
    return service


def a_clip(service_id: str, rendered: bool, pid: str = "project-1", days_ago: float = 0.0) -> Project:
    folder = models.project_dir(pid)
    folder.mkdir(parents=True, exist_ok=True)
    project = Project(id=pid, createdAt=when(days_ago), title="Fragment",
                      origin=ClipOrigin(serviceId=service_id, candidateId="c1", start=1.0, end=5.0))
    models.save_project(project)
    if rendered:
        (folder / "output").mkdir(exist_ok=True)
        (folder / "output" / "final.mp4").write_bytes(b"z" * 500_000)
    return project


def test_a_survey_of_nothing_is_empty(disk):
    report = storage.survey()
    assert report["items"] == [] and report["usedMb"] == 0.0


def test_a_recording_shows_up_with_what_it_would_give_back(disk):
    a_service(recording_mb=3, work_mb=1)
    item = storage.survey()["items"][0]
    assert item["kind"] == "service"
    assert item["mb"] == pytest.approx(4.0, abs=0.2)
    assert "tekst" in item["keeps"]


def test_a_recording_with_an_unfinished_clip_is_held_back(disk):
    a_service()
    a_clip("service-1", rendered=False)
    assert "nog niet gemaakt" in storage.survey()["items"][0]["blocked"]


def test_a_recording_whose_clips_are_all_made_is_free_to_go(disk):
    a_service()
    a_clip("service-1", rendered=True)
    assert storage.survey()["items"][0]["blocked"] == ""


def test_cleaning_a_recording_keeps_the_transcript_and_the_candidates(disk):
    a_service()
    freed = storage.clean_service("service-1")
    assert freed > 3_000_000
    assert not (models.service_dir("service-1") / "source.mp4").exists()
    assert (models.service_dir("service-1") / "transcript.json").is_file()
    assert models.load_service("service-1") is not None
    assert models.load_service("service-1").sourceVideo is None


def test_an_unfinished_clip_gets_its_own_copy_before_the_recording_goes(disk, monkeypatch):
    a_service()
    a_clip("service-1", rendered=False)
    taken = []
    monkeypatch.setattr(storage.clips, "materialise", lambda p: taken.append(p.id) or p)
    storage.clean_service("service-1")
    assert taken == ["project-1"], "a clip nobody has rendered must not be left pointing at nothing"


def test_a_finished_clip_is_not_copied_needlessly(disk, monkeypatch):
    a_service()
    a_clip("service-1", rendered=True)
    taken = []
    monkeypatch.setattr(storage.clips, "materialise", lambda p: taken.append(p.id) or p)
    storage.clean_service("service-1")
    assert taken == [], "its video is already made; the footage is of no further use"


def test_working_audio_goes_as_soon_as_there_is_a_transcript(disk):
    a_service(work_mb=2)
    freed = storage.clean_work()
    assert freed >= 2_000_000
    assert not (models.service_dir("service-1") / "work").exists()
    assert (models.service_dir("service-1") / "source.mp4").is_file(), "the recording itself stays"


def test_working_audio_stays_while_there_is_no_transcript_yet(disk):
    a_service(transcript=False)
    assert storage.clean_work() == 0
    assert (models.service_dir("service-1") / "work").is_dir()


def test_nothing_old_enough_means_nothing_is_touched(disk):
    a_service(days_ago=3)
    count, freed = storage.clean_old()
    assert (count, freed) == (0, 0)
    assert (models.service_dir("service-1") / "source.mp4").is_file()


def test_a_recording_past_the_keep_by_date_is_cleaned_up(disk, monkeypatch):
    monkeypatch.setattr(storage, "KEEP_WEEKS", 4)
    a_service(days_ago=40)
    count, freed = storage.clean_old()
    assert count == 1 and freed > 0
    assert not (models.service_dir("service-1") / "source.mp4").exists()


def test_an_old_recording_with_work_left_to_do_is_still_held_back(disk, monkeypatch):
    monkeypatch.setattr(storage, "KEEP_WEEKS", 4)
    a_service(days_ago=90)
    a_clip("service-1", rendered=False)
    assert storage.clean_old() == (0, 0)
    assert (models.service_dir("service-1") / "source.mp4").is_file()


def test_automatic_cleaning_can_be_turned_off(disk, monkeypatch):
    monkeypatch.setattr(storage, "KEEP_WEEKS", 0)
    a_service(days_ago=400)
    assert storage.clean_old() == (0, 0)
    assert (models.service_dir("service-1") / "source.mp4").is_file()


def test_a_clip_keeps_its_footage_until_the_video_is_made(disk):
    a_service()
    project = a_clip("service-1", rendered=False)
    project.sourceVideo = "source.mp4"
    models.save_project(project)
    (models.project_dir(project.id) / "source.mp4").write_bytes(b"x" * 1_000_000)
    assert storage.clean_project(project.id) == 0
    assert (models.project_dir(project.id) / "source.mp4").is_file()


def test_a_clip_lets_go_of_its_footage_once_the_video_exists(disk):
    a_service()
    project = a_clip("service-1", rendered=True)
    project.sourceVideo = "source.mp4"
    models.save_project(project)
    (models.project_dir(project.id) / "source.mp4").write_bytes(b"x" * 1_000_000)
    assert storage.clean_project(project.id) >= 1_000_000
    assert (models.project_dir(project.id) / "output" / "final.mp4").is_file(), "the video stays"


def test_a_damaged_record_does_not_stop_the_survey(disk):
    a_service()
    (models.service_dir("service-2")).mkdir(parents=True)
    (models.service_dir("service-2") / "service.json").write_text("{not json", encoding="utf-8")
    assert len(storage.survey()["items"]) == 1


def test_the_sweep_says_what_it_did(disk):
    a_service(work_mb=2)
    said = storage.sweep()
    assert "werkbestanden" in said
    assert storage.sweep() == "", "nothing left to say the second time"
