"""Work that survives a closed laptop: half a transcript, and answers already paid for."""

import json
from pathlib import Path

import pytest

from backend import discovery, models, transcription
from backend.discovery import LlmCandidate, build_windows
from backend.models import Segment, Service, Transcript


# --- half a transcript ---------------------------------------------------------

def test_nothing_saved_means_starting_at_the_beginning(tmp_path):
    assert transcription.load_partial(tmp_path) == (0.0, [], [])


def test_what_was_heard_is_written_down_and_read_back(tmp_path):
    words = [transcription.Word(1.0, 1.4, "Genade"), transcription.Word(1.5, 2.0, "is")]
    segments = [Segment(start=1.0, end=2.0, text="Genade is")]
    transcription.save_partial(tmp_path, 2.0, words, segments)

    up_to, again, back = transcription.load_partial(tmp_path)
    assert up_to == 2.0
    assert [w.word for w in again] == ["Genade", "is"]
    assert [s.text for s in back] == ["Genade is"]


def test_a_damaged_half_finished_file_just_starts_over(tmp_path):
    (tmp_path / transcription.PARTIAL_FILE).write_text("{ not json", encoding="utf-8")
    assert transcription.load_partial(tmp_path) == (0.0, [], [])


def test_saving_is_atomic(tmp_path):
    transcription.save_partial(tmp_path, 5.0, [], [])
    assert [p.name for p in tmp_path.iterdir()] == [transcription.PARTIAL_FILE]


def test_the_saved_point_is_where_the_next_run_picks_up(tmp_path):
    """The whole point: the seconds already heard are not listened to again."""
    transcription.save_partial(tmp_path, 420.0, [transcription.Word(1.0, 1.2, "een")], [])
    up_to, words, _ = transcription.load_partial(tmp_path)
    assert up_to == 420.0 and len(words) == 1


# --- answers already paid for ---------------------------------------------------

def talk(count: int) -> list[Segment]:
    return [Segment(start=i * 4.0, end=i * 4.0 + 3.6, text=f"Zin nummer {i} van de dienst.")
            for i in range(count)]


def a_candidate() -> LlmCandidate:
    return LlmCandidate(start=0.0, end=40.0, title="Titel", summary="s", reason="r", confidence=0.8)


def test_an_answer_is_kept_and_read_back(tmp_path):
    window = build_windows(talk(60))[0]
    discovery.remember_window(tmp_path, window, [a_candidate()])
    again = discovery.cached_window(tmp_path, window)
    assert again is not None and again[0].title == "Titel"


def test_a_window_that_was_never_answered_is_not_in_there(tmp_path):
    windows = build_windows(talk(120))
    discovery.remember_window(tmp_path, windows[0], [a_candidate()])
    assert discovery.cached_window(tmp_path, windows[1]) is None


def test_changing_the_text_means_asking_again(tmp_path):
    """A re-transcription must not be answered with the answers to the old text."""
    window = build_windows(talk(60))[0]
    discovery.remember_window(tmp_path, window, [a_candidate()])
    other = build_windows([Segment(start=s.start, end=s.end, text=s.text + " Anders.") for s in talk(60)])[0]
    assert discovery.cached_window(tmp_path, other) is None


def test_changing_the_model_means_asking_again(tmp_path, monkeypatch):
    window = build_windows(talk(60))[0]
    discovery.remember_window(tmp_path, window, [a_candidate()])
    monkeypatch.setattr(discovery, "LLM_MODEL", "some-other-model")
    assert discovery.cached_window(tmp_path, window) is None


def test_changing_the_instructions_means_asking_again(tmp_path, monkeypatch):
    window = build_windows(talk(60))[0]
    discovery.remember_window(tmp_path, window, [a_candidate()])
    monkeypatch.setattr(discovery, "SYSTEM_PROMPT", discovery.SYSTEM_PROMPT + " En let ook op humor.")
    assert discovery.cached_window(tmp_path, window) is None


def test_a_damaged_answer_is_simply_asked_again(tmp_path):
    window = build_windows(talk(60))[0]
    discovery.remember_window(tmp_path, window, [a_candidate()])
    discovery.window_file(tmp_path, window).write_text("{ not json", encoding="utf-8")
    assert discovery.cached_window(tmp_path, window) is None


def test_without_a_cache_nothing_is_remembered(tmp_path):
    window = build_windows(talk(60))[0]
    discovery.remember_window(None, window, [a_candidate()])
    assert discovery.cached_window(None, window) is None
    assert list(tmp_path.iterdir()) == []


def test_a_second_run_asks_only_about_what_failed(tmp_path, monkeypatch):
    """The point of the cache: a run that lost two windows costs two windows to finish."""
    transcript = Transcript(language="nl", segments=talk(300))
    windows = build_windows(transcript.segments)
    assert len(windows) > 4

    asked: list[int] = []
    failing = {windows[1].index, windows[3].index}

    def flaky(window):
        asked.append(window.index)
        if window.index in failing:
            raise RuntimeError("de modelaanbieder deed even niet mee")
        return [a_candidate()]

    monkeypatch.setattr(discovery, "check_provider", lambda: None)
    monkeypatch.setattr(discovery, "analyze_window", flaky)
    first = discovery.discover(transcript, cache_dir=tmp_path)
    assert first.failed == 2
    assert len(asked) == len(windows)

    asked.clear()
    failing.clear()
    second = discovery.discover(transcript, cache_dir=tmp_path)
    assert second.failed == 0
    assert sorted(asked) == [1, 3], "everything else was already answered"


# --- what the user is told after a restart --------------------------------------

@pytest.mark.parametrize("interrupted,back_to", [
    ("transcribing", "uploaded"),
    ("analyzing", "transcribed"),
    ("processing", "ready"),
])
def test_an_interrupted_step_goes_back_one_and_says_how_to_carry_on(tmp_path, monkeypatch, interrupted, back_to):
    monkeypatch.setattr(models, "SERVICES_DIR", tmp_path)
    models.service_dir("service-1").mkdir(parents=True)
    models.save_service(Service(id="service-1", createdAt="2026-01-01T00:00:00+00:00", status=interrupted))

    assert models.recover_services() == ["service-1"]
    service = models.load_service("service-1")
    assert service.status == back_to
    assert service.error is None, "an interruption is not a failure"
    assert "verder" in service.warning or "opnieuw" in service.warning


def test_a_service_that_was_not_busy_is_left_alone(tmp_path, monkeypatch):
    monkeypatch.setattr(models, "SERVICES_DIR", tmp_path)
    models.service_dir("service-1").mkdir(parents=True)
    models.save_service(Service(id="service-1", createdAt="2026-01-01T00:00:00+00:00", status="ready"))
    assert models.recover_services() == []
    assert models.load_service("service-1").status == "ready"


# --- carrying on where it stopped ------------------------------------------------

class FakeWord:
    def __init__(self, start, end, word):
        self.start, self.end, self.word = start, end, word


class FakeSegment:
    def __init__(self, start, end, text, words):
        self.start, self.end, self.text, self.words = start, end, text, words


class FakePipeline:
    """Stands in for faster-whisper, so the resume arithmetic can be tested in milliseconds."""

    produced: list[FakeSegment] = []

    def __init__(self, model=None):
        pass

    def transcribe(self, audio, **kwargs):
        return iter(FakePipeline.produced), None


@pytest.fixture
def fake_whisper(monkeypatch):
    """Whisper replaced by a stub, and the audio extraction recorded rather than run."""
    import faster_whisper

    monkeypatch.setattr(faster_whisper, "BatchedInferencePipeline", FakePipeline)
    monkeypatch.setattr(transcription, "get_model", lambda size=None: object())
    monkeypatch.setattr(transcription, "initial_prompt", lambda: "")
    monkeypatch.setattr(transcription, "load_vocabulary", lambda: {"corrections": {}})
    asked: list[dict] = []

    def fake_extract(source, wav, should_stop=None, on_progress=None, duration=None, start=0.0):
        asked.append({"start": start, "duration": duration})
        wav.parent.mkdir(parents=True, exist_ok=True)
        wav.write_bytes(b"audio")

    monkeypatch.setattr(transcription, "extract_audio", fake_extract)
    return asked


def test_a_fresh_run_listens_to_the_whole_thing(tmp_path, fake_whisper):
    FakePipeline.produced = [FakeSegment(0.0, 4.0, "Genade", [FakeWord(0.0, 4.0, "Genade")])]
    transcription.transcribe(tmp_path / "in.mp4", tmp_path / "work", duration=600.0)
    assert fake_whisper == [{"start": 0.0, "duration": 600.0}]


def test_a_resumed_run_skips_the_seconds_already_heard(tmp_path, fake_whisper):
    work = tmp_path / "work"
    work.mkdir()
    transcription.save_partial(work, 283.0, [transcription.Word(1.0, 1.5, "Genade")],
                               [Segment(start=1.0, end=1.5, text="Genade")])
    FakePipeline.produced = [FakeSegment(0.0, 5.0, "verder", [FakeWord(0.0, 5.0, "verder")])]
    transcription.transcribe(tmp_path / "in.mp4", work, duration=600.0)
    assert fake_whisper == [{"start": 283.0, "duration": 317.0}], "only what is left is pulled out"


def test_a_resumed_run_puts_the_new_words_after_the_old_ones(tmp_path, fake_whisper):
    work = tmp_path / "work"
    work.mkdir()
    transcription.save_partial(work, 283.0, [transcription.Word(1.0, 1.5, "Genade")], [])
    FakePipeline.produced = [FakeSegment(0.0, 5.0, "verder", [FakeWord(0.0, 5.0, "verder")])]
    result = transcription.transcribe(tmp_path / "in.mp4", work, duration=600.0)
    text = " ".join(s.text for s in result.segments)
    assert text.startswith("Genade"), "what was already heard comes first"
    assert "verder" in text
    ends = [s.end for s in result.segments]
    assert max(ends) == pytest.approx(288.0), "the new part is placed where it belongs in the clip"


def test_the_half_finished_file_is_cleared_once_the_run_completes(tmp_path, fake_whisper):
    work = tmp_path / "work"
    work.mkdir()
    transcription.save_partial(work, 10.0, [], [])
    FakePipeline.produced = [FakeSegment(0.0, 5.0, "klaar", [FakeWord(0.0, 5.0, "klaar")])]
    transcription.transcribe(tmp_path / "in.mp4", work, duration=20.0)
    assert not (work / transcription.PARTIAL_FILE).exists()


def test_being_stopped_keeps_what_was_heard(tmp_path, fake_whisper):
    from backend.jobs import Cancelled

    work = tmp_path / "work"
    work.mkdir()
    FakePipeline.produced = [
        FakeSegment(i * 40.0, i * 40.0 + 39.0, f"deel {i}", [FakeWord(i * 40.0, i * 40.0 + 39.0, f"deel{i}")])
        for i in range(6)
    ]
    calls = {"n": 0}

    def stop_after_a_while():
        calls["n"] += 1
        if calls["n"] > 4:
            raise Cancelled

    with pytest.raises(Cancelled):
        transcription.transcribe(tmp_path / "in.mp4", work, duration=600.0,
                                 should_stop=stop_after_a_while)
    up_to, words, _ = transcription.load_partial(work)
    assert up_to > 0 and words, "the work done before stopping is kept for the next attempt"


def test_a_finished_recording_is_not_left_waiting_for_nothing(tmp_path, fake_whisper):
    """A saved point at the very end must start over rather than ask for zero seconds."""
    work = tmp_path / "work"
    work.mkdir()
    transcription.save_partial(work, 600.0, [], [])
    FakePipeline.produced = [FakeSegment(0.0, 5.0, "opnieuw", [FakeWord(0.0, 5.0, "opnieuw")])]
    transcription.transcribe(tmp_path / "in.mp4", work, duration=600.0)
    assert fake_whisper == [{"start": 0.0, "duration": 600.0}]
