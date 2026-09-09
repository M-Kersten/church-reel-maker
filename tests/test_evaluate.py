"""The measuring tool itself: it has to be right before its numbers mean anything."""

import json

import pytest

from backend import discovery
from backend.discovery import LlmCandidate, LlmShortlist, Verdict
from backend.models import ClipCandidate
from tools import evaluate


def posted(start: float, end: float, note: str = "") -> evaluate.Posted:
    return evaluate.Posted(start=start, end=end, note=note)


def proposal(start: float, end: float, id_: str = "candidate-01") -> ClipCandidate:
    return ClipCandidate(id=id_, start=start, end=end, title="t", shortlisted=True)


# --- what counts as finding a moment -------------------------------------------

def test_the_same_range_is_a_hit():
    assert evaluate.overlap(posted(100, 140), proposal(100, 140)) == pytest.approx(1.0)


def test_a_proposal_somewhere_else_is_not():
    assert evaluate.overlap(posted(100, 140), proposal(600, 640)) == 0.0


def test_half_a_moment_is_the_line():
    assert evaluate.overlap(posted(100, 140), proposal(120, 200)) == pytest.approx(0.5)
    assert evaluate.overlap(posted(100, 140), proposal(121, 200)) < evaluate.HIT


def test_a_longer_proposal_that_contains_the_moment_is_a_hit():
    assert evaluate.overlap(posted(100, 140), proposal(60, 200)) == pytest.approx(1.0)


# --- the numbers ---------------------------------------------------------------

def test_finding_everything_scores_perfectly():
    score = evaluate.Score(name="x", posted=3, found=8, shortlisted=5, hits_at_5=3, hits_total=3)
    assert score.precision_at_5 == pytest.approx(0.6)
    assert score.recall == pytest.approx(1.0)


def test_finding_nothing_scores_zero():
    score = evaluate.Score(name="x", posted=3, found=8, shortlisted=5)
    assert score.precision_at_5 == 0.0 and score.recall == 0.0


def test_a_service_with_nothing_posted_does_not_divide_by_zero():
    score = evaluate.Score(name="x", posted=0, found=4, shortlisted=0)
    assert score.recall == 0.0 and score.precision_at_5 == 0.0


def test_precision_is_over_five_at_most():
    """Ten shortlisted and three hits is three out of five, not three out of ten."""
    score = evaluate.Score(name="x", posted=3, found=20, shortlisted=10, hits_at_5=3, hits_total=3)
    assert score.precision_at_5 == pytest.approx(0.6)


# --- a whole run, with the model stubbed out ------------------------------------

@pytest.fixture
def case():
    return evaluate.load_cases(evaluate.DEFAULT_SET)[0]


def test_the_example_service_loads(case):
    assert case.posted, "the shipped example has moments marked as posted"
    assert case.transcript.segments
    assert "Rust" in case.about, "the sermon title reaches the prompt"


def test_a_run_finds_the_moments_that_were_posted(case, monkeypatch):
    """A model that proposes exactly the posted moments must score a clean sweep."""
    monkeypatch.setattr(discovery, "check_provider", lambda: None)

    def propose(window, about=""):
        out = []
        for moment in case.posted:
            if window.start <= moment.start <= window.end:
                out.append(LlmCandidate(start=moment.start, end=moment.end, title=moment.note,
                                        summary="s", reason="r", confidence=0.9))
        return out

    monkeypatch.setattr(discovery, "analyze_window", propose)
    monkeypatch.setattr(discovery, "shortlist", lambda found, *a, **k: found)
    score = evaluate.run_case(case)
    assert score.hits_total == len(case.posted)
    assert score.recall == pytest.approx(1.0)
    assert score.misses == []


def test_a_run_that_finds_nothing_useful_says_which_moments_it_missed(case, monkeypatch):
    monkeypatch.setattr(discovery, "check_provider", lambda: None)
    # Short proposals, so none of them can cover half of a posted moment by accident.
    monkeypatch.setattr(discovery, "analyze_window", lambda w, about="": [
        LlmCandidate(start=w.start, end=w.start + 16, title="iets anders", summary="s", reason="r",
                     confidence=0.5)])
    monkeypatch.setattr(discovery, "shortlist", lambda found, *a, **k: found)
    score = evaluate.run_case(case)
    assert score.recall < 1.0
    assert len(score.misses) == len(case.posted) - score.hits_total
    assert any("rust" in m.lower() for m in score.misses)


def test_only_the_shortlisted_moments_count(case, monkeypatch):
    """Finding a moment and then not choosing it is not finding it."""
    monkeypatch.setattr(discovery, "check_provider", lambda: None)

    def propose(window, about=""):
        return [LlmCandidate(start=m.start, end=m.end, title=m.note, summary="s", reason="r",
                             confidence=0.9)
                for m in case.posted if window.start <= m.start <= window.end]

    monkeypatch.setattr(discovery, "analyze_window", propose)

    def reject_everything(found, *a, **k):
        for c in found:
            c.shortlisted = False
        found[0].shortlisted = True
        return found

    monkeypatch.setattr(discovery, "shortlist", reject_everything)
    score = evaluate.run_case(case)
    assert score.shortlisted == 1
    assert score.hits_total <= 1


# --- the output ------------------------------------------------------------------

def test_the_table_has_a_row_per_service_and_a_total():
    scores = [evaluate.Score(name="een", posted=3, found=8, shortlisted=5, hits_at_5=2, hits_total=3, cost=0.5),
              evaluate.Score(name="twee", posted=2, found=6, shortlisted=5, hits_at_5=2, hits_total=2, cost=0.4)]
    out = evaluate.table(scores)
    assert "een" in out and "twee" in out and "samen" in out
    assert "0.90" in out or "0.9" in out, "the costs are added up"


def test_comparing_shows_which_way_it_moved(tmp_path):
    before = {"services": [{"name": "een", "precisionAt5": 0.40, "recall": 0.50, "cost": 0.60}]}
    now = [evaluate.Score(name="een", posted=2, found=6, shortlisted=5, hits_at_5=3, hits_total=2, cost=0.50)]
    out = evaluate.compare(now, before)
    assert "0.40→0.60 +" in out, "precision went up"
    assert "0.60→0.50 +" in out, "cost went down, which is also better"


def test_a_service_that_was_not_in_the_baseline_is_marked_new():
    out = evaluate.compare([evaluate.Score(name="nieuw", posted=1, found=1, shortlisted=1)], {"services": []})
    assert "nieuw" in out


def test_an_unchanged_number_is_shown_as_unchanged():
    before = {"services": [{"name": "een", "precisionAt5": 0.4, "recall": 0.5, "cost": 0.6}]}
    now = [evaluate.Score(name="een", posted=2, found=5, shortlisted=5, hits_at_5=2, hits_total=1, cost=0.6)]
    assert "=" in evaluate.compare(now, before)


def test_the_dry_run_costs_nothing_and_says_what_a_real_one_would(case):
    out = evaluate.dry_run([case])
    assert case.name in out and "samen" in out


def test_a_saved_run_can_be_read_back(tmp_path):
    scores = [evaluate.Score(name="een", posted=3, found=8, shortlisted=5, hits_at_5=2, hits_total=3)]
    target = tmp_path / "baseline.json"
    target.write_text(json.dumps({"services": [s.as_dict() for s in scores]}), encoding="utf-8")
    again = json.loads(target.read_text(encoding="utf-8"))
    assert again["services"][0]["precisionAt5"] == pytest.approx(0.4)
