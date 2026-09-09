"""The second pass: weighing every proposal against all the others."""

import pytest

from backend import discovery, structure
from backend.discovery import LlmCandidate, LlmShortlist, Verdict
from backend.models import ClipCandidate, Segment, Transcript
from tests.service_text import transcript_segments


def clip(id_: str, start: float, title: str, score: float = 0.8) -> ClipCandidate:
    return ClipCandidate(id=id_, start=start, end=start + 40, title=title, summary=f"over {title}",
                         reason="staat op zichzelf", confidence=score, score=score)


def a_few(n: int) -> list[ClipCandidate]:
    return [clip(f"candidate-{i + 1:02d}", i * 200.0, f"Moment {i + 1}", 0.5 + i * 0.02) for i in range(n)]


@pytest.fixture
def service():
    return transcript_segments()


@pytest.fixture
def shape(service):
    return structure.blocks(service)


def test_a_handful_of_proposals_is_not_worth_choosing_between(service, shape, monkeypatch):
    """With three moments there is nothing to weigh; do not spend a call on it."""
    called = []
    monkeypatch.setattr(discovery, "ask", lambda *a, **k: called.append(1))
    out = discovery.shortlist(a_few(3), service, shape)
    assert called == []
    assert all(c.shortlisted for c in out)


def test_four_proposals_are_already_worth_thinning_out(service, shape, monkeypatch):
    """Fewer moments is the point, so the editor gets to say no from four onwards."""
    monkeypatch.setattr(discovery, "ask", lambda *a, **k: LlmShortlist(verdicts=[
        Verdict(id="candidate-02", keep=True, rank=1, verdict="deze wel"),
        Verdict(id="candidate-01", keep=False, rank=0, verdict="opent op een terugverwijzing"),
    ]))
    out = discovery.shortlist(a_few(4), service, shape)
    assert sum(1 for c in out if c.shortlisted) == 1


def test_the_editor_decides_the_order(service, shape, monkeypatch):
    found = a_few(8)
    monkeypatch.setattr(discovery, "ask", lambda *a, **k: LlmShortlist(verdicts=[
        Verdict(id="candidate-08", keep=True, rank=1, verdict="sterkste moment van de dienst"),
        Verdict(id="candidate-03", keep=True, rank=2, verdict="mooi persoonlijk verhaal"),
        Verdict(id="candidate-01", keep=False, rank=0, verdict="te veel aanloop"),
    ]))
    out = discovery.shortlist(found, service, shape)
    assert [c.id for c in out[:2]] == ["candidate-08", "candidate-03"]
    assert out[0].verdict == "sterkste moment van de dienst"


def test_the_ones_that_lose_are_kept_behind_the_ones_that_win(service, shape, monkeypatch):
    found = a_few(8)
    monkeypatch.setattr(discovery, "ask", lambda *a, **k: LlmShortlist(verdicts=[
        Verdict(id="candidate-02", keep=True, rank=1, verdict="dit is hem"),
    ]))
    out = discovery.shortlist(found, service, shape)
    assert len(out) == 8, "nothing is thrown away"
    assert out[0].id == "candidate-02" and out[0].shortlisted
    assert all(not c.shortlisted for c in out[1:])


def test_only_the_chosen_ones_start_out_ticked(service, shape, monkeypatch):
    found = a_few(8)
    monkeypatch.setattr(discovery, "ask", lambda *a, **k: LlmShortlist(verdicts=[
        Verdict(id="candidate-05", keep=True, rank=1, verdict="ja"),
        Verdict(id="candidate-06", keep=True, rank=2, verdict="ja"),
    ]))
    out = discovery.shortlist(found, service, shape)
    assert [c.id for c in out if c.selected] == ["candidate-05", "candidate-06"]


def test_a_rejected_moment_says_why(service, shape, monkeypatch):
    found = a_few(6)
    monkeypatch.setattr(discovery, "ask", lambda *a, **k: LlmShortlist(verdicts=[
        Verdict(id="candidate-01", keep=True, rank=1, verdict="beste van de dienst"),
        Verdict(id="candidate-02", keep=False, rank=0, verdict="zegt hetzelfde als moment 1"),
    ]))
    out = discovery.shortlist(found, service, shape)
    passed_over = next(c for c in out if c.id == "candidate-02")
    assert passed_over.verdict == "zegt hetzelfde als moment 1"


def test_an_answer_that_keeps_nothing_is_ignored(service, shape, monkeypatch):
    """A model that rejects everything has not chosen; it has failed."""
    found = a_few(6)
    monkeypatch.setattr(discovery, "ask", lambda *a, **k: LlmShortlist(verdicts=[
        Verdict(id=c.id, keep=False, rank=0, verdict="nee") for c in found
    ]))
    out = discovery.shortlist(found, service, shape)
    assert all(c.shortlisted for c in out), "the first pass's order is better than nothing"


def test_a_moment_the_editor_never_mentions_is_not_shortlisted(service, shape, monkeypatch):
    found = a_few(6)
    monkeypatch.setattr(discovery, "ask", lambda *a, **k: LlmShortlist(verdicts=[
        Verdict(id="candidate-01", keep=True, rank=1, verdict="ja"),
    ]))
    out = discovery.shortlist(found, service, shape)
    assert [c.shortlisted for c in out] == [True] + [False] * 5


def test_the_editor_is_shown_the_shape_of_the_service(service, shape):
    asked = discovery.shortlist_request(a_few(6), service, shape)
    assert "preek" in asked and "mededelingen" in asked
    assert "minuten en is opgebouwd" in asked


def test_the_editor_is_shown_what_is_actually_said(service, shape):
    sermon = next(b for b in shape if b.part == "preek")
    said = next(s for s in service if s.start >= sermon.start)
    found = [ClipCandidate(id="candidate-01", start=said.start, end=said.end, title="Rust")]
    asked = discovery.shortlist_request(found, service, shape)
    assert "transcript:" in asked
    assert said.text in asked, "the editor reads the moment, not only its title"


def test_every_proposal_is_identified_so_the_verdict_can_be_matched_back(service, shape):
    found = a_few(6)
    asked = discovery.shortlist_request(found, service, shape)
    assert all(f"[{c.id}]" in asked for c in found)


def test_the_excerpt_stays_readable(service):
    long_one = discovery.excerpt(service, 600.0, 1400.0)
    assert len(long_one) <= discovery.EXCERPT_CHARS
    assert long_one.endswith("…")


def test_an_excerpt_of_nothing_is_empty(service):
    assert discovery.excerpt(service, 99999.0, 99999.0) == ""


# --- the whole run, with the model stubbed out ---------------------------------

def test_a_run_reports_what_it_skipped_and_what_it_chose(service, monkeypatch):
    transcript = Transcript(language="nl", segments=service)
    monkeypatch.setattr(discovery, "check_provider", lambda: None)
    monkeypatch.setattr(discovery, "analyze_window", lambda w, about="": [
        LlmCandidate(start=w.start + 5, end=w.start + 45, title=f"Uit venster {w.index}",
                     summary="s", reason="r", confidence=0.8)])

    def judge(user, system, schema):
        ids = [line.split("]")[0][1:] for line in user.splitlines() if line.startswith("[candidate-")]
        return LlmShortlist(verdicts=[
            Verdict(id=cid, keep=i < 3, rank=i + 1 if i < 3 else 0, verdict="oordeel")
            for i, cid in enumerate(ids)])

    monkeypatch.setattr(discovery, "ask", judge)
    result = discovery.discover(transcript)

    assert result.skipped > 0, "the parts that are not preaching were left out"
    assert result.windows > 0
    assert result.shortlisted == 3
    assert result.shape and result.shape[0]["part"] == "welkom"
    assert [c.shortlisted for c in result.candidates[:3]] == [True, True, True]
    assert not result.candidates[3].shortlisted


def test_a_failing_editor_leaves_the_moments_alone(service, monkeypatch):
    transcript = Transcript(language="nl", segments=service)
    monkeypatch.setattr(discovery, "check_provider", lambda: None)
    monkeypatch.setattr(discovery, "analyze_window", lambda w, about="": [
        LlmCandidate(start=w.start + 5, end=w.start + 45, title="Moment", summary="s", reason="r",
                     confidence=0.8)])

    def refuse(user, system, schema):
        if schema is LlmShortlist:
            raise RuntimeError("de modelaanbieder deed even niet mee")
        raise AssertionError("unexpected call")

    monkeypatch.setattr(discovery, "ask", refuse)
    result = discovery.discover(transcript)
    assert result.candidates, "the moments found are worth having even unranked"
    assert "vergeleken" in (result.warning or "")


def test_the_editor_reads_the_opening_line(service, shape):
    """What a scrolling stranger sees first is the thing to judge, so it is put up front."""
    first = next(s for s in service if s.text.strip())
    found = [clip("candidate-01", first.start, "Moment")]
    request = discovery.shortlist_request(found, service, shape)
    assert f"opent met: {first.text.strip()}" in request


def test_an_opening_that_leans_backwards_is_flagged_for_the_editor(service, shape):
    cold = Segment(start=10.0, end=18.0, text="Dat is precies waar het om gaat.")
    warm = Segment(start=30.0, end=38.0, text="God vraagt niet dat je perfect bent.")
    found = [clip("candidate-01", 10.0, "koud"), clip("candidate-02", 30.0, "warm")]
    request = discovery.shortlist_request(found, [cold, warm], shape)
    before, after = request.split("[candidate-02]")
    assert "opent op een terugverwijzing" in before
    assert "opent op een terugverwijzing" not in after


def test_the_editor_is_asked_for_a_handful_not_a_list(service, shape, monkeypatch):
    seen = {}
    monkeypatch.setattr(discovery, "ask",
                        lambda user, system, schema: seen.update(system=system) or LlmShortlist(
                            verdicts=[Verdict(id="candidate-01", keep=True, rank=1, verdict="ja")]))
    discovery.shortlist(a_few(6), service, shape)
    assert "kies er 3 tot 6" in seen["system"]
