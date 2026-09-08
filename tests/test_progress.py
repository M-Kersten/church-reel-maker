"""Time estimates: what the person waiting is told."""

import time

import pytest

from backend.jobs import Estimator, human_remaining
from backend.transcription import batch_size, model_for


@pytest.mark.parametrize("seconds,expected", [
    (5, "nog geen minuut"),
    (44, "nog geen minuut"),
    (60, "nog ongeveer een minuut"),
    (150, "nog ongeveer 3 minuten"),
    (1800, "nog ongeveer 30 minuten"),
    (3600, "nog ongeveer een uur"),
    (7800, "nog ongeveer 2 uur en 10 minuten"),
])
def test_remaining_time_reads_like_a_person_said_it(seconds, expected):
    assert human_remaining(seconds) == expected


def test_no_estimate_before_there_is_anything_to_go_on():
    left = Estimator(settle=10.0)
    assert left.remaining(0.1) is None, "the first reading is the baseline, not an estimate"
    assert left.remaining(0.2) is None, "too soon to say"


def test_an_estimate_appears_once_the_work_has_settled():
    left = Estimator(settle=0.0)
    left.remaining(0.01)  # the first real reading is the baseline
    time.sleep(0.05)
    guess = left.remaining(0.5)
    assert guess is not None and guess > 0


def test_the_estimate_is_roughly_right():
    """Half done after a known time means about that long to go."""
    left = Estimator(settle=0.0)
    left.remaining(0.001)
    time.sleep(0.2)
    assert left.remaining(0.5) == pytest.approx(0.2, rel=0.5)


def test_the_clock_starts_when_the_work_does():
    """The opening reading is the baseline, so a burst of readings is measured from the start."""
    left = Estimator(settle=0.0)
    assert left.remaining(0.0) is None, "nothing to estimate from yet"
    time.sleep(0.05)
    assert left.remaining(0.5) == pytest.approx(0.05, rel=0.6)


def test_work_reported_in_bursts_is_still_timed_from_the_phase_start():
    """Batched transcription hands back many segments at once, microseconds apart."""
    left = Estimator(after=0.1, settle=0.0)
    left.remaining(0.1)          # the phase opens here
    time.sleep(0.1)
    left.remaining(0.5)          # first burst arrives
    assert left.remaining(0.52) is not None, "a burst must not look like instant work"


def test_a_phase_that_runs_at_another_speed_is_left_out():
    """Pulling the audio out is quick; it must not make the writing-out look quick too."""
    left = Estimator(after=0.08, settle=0.0)
    assert left.remaining(0.05) is None, "still in the first phase"
    left.remaining(0.1)
    time.sleep(0.05)
    assert left.remaining(0.2) is not None


def test_nothing_is_said_when_the_work_is_done():
    left = Estimator(settle=0.0)
    left.remaining(0.1)
    assert left.remaining(1.0) is None


def test_the_message_carries_the_estimate_only_when_there_is_one():
    left = Estimator(settle=0.0)
    assert left.note(0.1, "Bezig") == "Bezig"
    time.sleep(0.05)
    assert left.note(0.5, "Bezig").startswith("Bezig · nog ")


def test_the_batch_fits_the_machine_and_the_model():
    quick, accurate = batch_size(False), batch_size(True)
    assert 2 <= quick <= 8
    assert 2 <= accurate <= quick, "the bigger model holds more, so it takes a smaller batch"


def test_the_accurate_switch_picks_a_different_model():
    assert model_for(False) != model_for(True)


def test_the_bar_carries_on_between_readings():
    """Batched work reports in big steps; the bar must not stand still in between."""
    from backend.jobs import Job
    job = Job(status="running")
    job.start_phase()
    job.advance(0.2)
    first = job.shown()
    time.sleep(0.1)
    assert job.shown() > first, "no reading arrived, but time passed and work is being done"


def test_the_bar_never_runs_past_the_end():
    from backend.jobs import Job
    job = Job(status="running")
    job.start_phase()
    job.advance(0.98)
    time.sleep(0.2)
    assert job.shown() <= 0.99


def test_a_finished_job_reports_exactly_what_it_reached():
    from backend.jobs import Job
    job = Job(status="done", progress=1.0)
    assert job.shown() == 1.0
    assert job.to_dict()["progress"] == 1.0


def test_a_job_that_has_not_moved_does_not_invent_progress():
    from backend.jobs import Job
    job = Job(status="running")
    job.start_phase()
    time.sleep(0.05)
    assert job.shown() == 0.0


def test_a_new_phase_measures_its_own_speed():
    """A quick first phase must not make a slow second phase look quick."""
    from backend.jobs import Job
    job = Job(status="running")
    job.start_phase()
    job.advance(0.5)          # fast phase: half the work in almost no time
    job.start_phase()
    job.advance(0.51)
    time.sleep(0.05)
    assert job.shown() < 0.6, "the new phase sets the pace, not the old one"


def test_the_reported_dict_hides_the_bookkeeping():
    from backend.jobs import Job
    keys = set(Job(status="running").to_dict())
    assert keys == {"status", "progress", "message", "error", "canStop"}
