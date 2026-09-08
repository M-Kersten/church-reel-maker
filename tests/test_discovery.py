"""Windowing, boundary snapping, scoring and dedupe: how candidates get ranked."""

import pytest

from backend.discovery import (MAX_CLIP, MIN_CLIP, OVERLAP_DUPLICATE, PREFERRED, WINDOW_OVERLAP,
                               WINDOW_SECONDS, LlmCandidate, build_windows, dedupe_and_rank,
                               estimate, overlap_fraction, score, snap)
from backend.models import ClipCandidate, Segment, Transcript


def talk(count: int, step: float = 4.0) -> list[Segment]:
    """A transcript of `count` sentences, `step` seconds apart."""
    return [Segment(start=i * step, end=i * step + step - 0.4, text=f"Zin nummer {i} van de dienst.")
            for i in range(count)]


def test_no_segments_gives_no_windows():
    assert build_windows([]) == []
    assert build_windows([Segment(start=0, end=1, text="   ")]) == []


def test_windows_cover_every_segment():
    segments = talk(200)
    windows = build_windows(segments)
    covered = {id(s) for w in windows for s in w.segments}
    assert len(covered) == len(segments)


def test_windows_are_about_the_configured_length():
    windows = build_windows(talk(200))
    assert all(w.end - w.start <= WINDOW_SECONDS + 10 for w in windows)
    assert len(windows) > 1


def test_windows_overlap_so_a_moment_on_a_seam_is_still_seen():
    windows = build_windows(talk(200))
    for before, after in zip(windows, windows[1:]):
        assert after.start < before.end, "consecutive windows must share some transcript"
        assert before.end - after.start <= WINDOW_OVERLAP + 10


def test_windowing_always_makes_progress():
    """A pathological transcript must not spin forever or repeat a window."""
    segments = [Segment(start=0.0, end=600.0, text="Een hele lange zin."),
                Segment(start=1.0, end=2.0, text="Kort."),
                Segment(start=1.5, end=900.0, text="Nog een lange.")]
    windows = build_windows(segments)
    assert windows
    assert len({(w.start, w.end) for w in windows}) == len(windows)


def test_windows_are_numbered_in_order():
    windows = build_windows(talk(120))
    assert [w.index for w in windows] == list(range(len(windows)))


def test_snap_moves_boundaries_onto_sentences():
    window = build_windows(talk(40))[0]
    first, second = window.segments[2], window.segments[6]
    proposal = LlmCandidate(start=first.start + 1.5, end=second.end - 1.2, title="t", summary="s",
                            reason="r", confidence=0.8)
    assert snap(proposal, window) == (round(first.start, 2), round(second.end, 2))


def test_snap_leaves_a_boundary_alone_when_no_sentence_is_near():
    """Sentences 30 s apart: a boundary in the middle of one has nothing to snap to."""
    window = build_windows(talk(6, step=30.0))[0]
    proposal = LlmCandidate(start=15.5, end=101.3, title="t", summary="s", reason="r", confidence=0.8)
    start, end = snap(proposal, window)
    assert (start, end) == (15.5, 101.3)


def test_snap_stays_inside_the_window():
    window = build_windows(talk(40))[0]
    proposal = LlmCandidate(start=-500, end=99999, title="t", summary="s", reason="r", confidence=0.5)
    start, end = snap(proposal, window)
    assert window.start <= start <= end <= window.end


def candidate(**kwargs) -> LlmCandidate:
    base = dict(start=0.0, end=45.0, title="t", summary="s", reason="r", confidence=0.8)
    return LlmCandidate(**{**base, **kwargs})


def test_score_prefers_the_useful_length():
    good = score(candidate(), (PREFERRED[0] + PREFERRED[1]) / 2)
    short = score(candidate(), MIN_CLIP + 1)
    long = score(candidate(), MAX_CLIP - 1)
    assert good > short and good > long


def test_score_stays_in_range():
    for confidence in (0.0, 0.5, 1.0, 2.0, -1.0):
        for duration in (5, 20, 45, 90, 200):
            assert -0.2 <= score(candidate(confidence=confidence), duration) <= 1.1


def test_confidence_still_decides_between_equal_lengths():
    assert score(candidate(confidence=0.9), 45) > score(candidate(confidence=0.4), 45)


def clip(start: float, end: float, score_: float = 0.8, id_: str = "") -> ClipCandidate:
    return ClipCandidate(id=id_, start=start, end=end, title="t", summary="s", reason="r",
                         confidence=score_, score=score_)


def test_overlap_fraction_is_relative_to_the_shorter_one():
    assert overlap_fraction(clip(0, 100), clip(0, 10)) == pytest.approx(1.0)
    assert overlap_fraction(clip(0, 10), clip(20, 30)) == 0.0
    assert overlap_fraction(clip(0, 20), clip(10, 30)) == pytest.approx(0.5)


def test_dedupe_keeps_the_best_of_an_overlapping_pair():
    kept = dedupe_and_rank([clip(0, 40, 0.5), clip(2, 42, 0.9)])
    assert len(kept) == 1
    assert kept[0].start == 2 and kept[0].score == 0.9


def test_dedupe_keeps_the_loser_as_an_alternative_boundary():
    kept = dedupe_and_rank([clip(0, 40, 0.5), clip(2, 42, 0.9)])
    assert [(b.start, b.end) for b in kept[0].alternateBoundaries] == [(0, 40)]


def test_dedupe_leaves_separate_moments_alone():
    kept = dedupe_and_rank([clip(0, 40, 0.9), clip(200, 240, 0.7)])
    assert len(kept) == 2


def test_dedupe_ranks_best_first_and_numbers_them():
    kept = dedupe_and_rank([clip(0, 40, 0.4), clip(200, 240, 0.9), clip(400, 440, 0.6)])
    assert [c.score for c in kept] == [0.9, 0.6, 0.4]
    assert [c.id for c in kept] == ["candidate-01", "candidate-02", "candidate-03"]


def test_dedupe_of_nothing_is_nothing():
    assert dedupe_and_rank([]) == []


def test_an_identical_duplicate_adds_no_alternative():
    kept = dedupe_and_rank([clip(0, 40, 0.9), clip(0, 40, 0.8)])
    assert len(kept) == 1 and kept[0].alternateBoundaries == []


def test_overlap_threshold_is_the_line_between_one_moment_and_two():
    share = 100 * OVERLAP_DUPLICATE
    under = dedupe_and_rank([clip(0, 100, 0.9), clip(100 - share + 10, 200 - share + 10, 0.8)])
    over = dedupe_and_rank([clip(0, 100, 0.9), clip(100 - share - 10, 200 - share - 10, 0.8)])
    assert len(under) == 2, "a small overlap is two moments"
    assert len(over) == 1, "a large overlap is one moment proposed twice"


def test_a_candidate_inside_another_is_the_same_moment():
    assert len(dedupe_and_rank([clip(0, 100, 0.9), clip(20, 60, 0.8)])) == 1


def test_estimate_grows_with_the_transcript():
    small = estimate(Transcript(language="nl", segments=talk(50)))
    large = estimate(Transcript(language="nl", segments=talk(500)))
    assert large["windows"] > small["windows"]
    assert large["tokens"] > small["tokens"]
    assert large["costUsd"] >= small["costUsd"]
    assert small["model"] and small["provider"]


def test_estimate_of_an_empty_transcript_costs_nothing():
    empty = estimate(Transcript(language="nl", segments=[]))
    assert empty["windows"] == 0 and empty["costUsd"] == 0.0
