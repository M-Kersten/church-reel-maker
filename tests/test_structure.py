"""Reading the shape of a service, so half of it is never sent to the model."""

import pytest

from backend import discovery, structure
from backend.models import Segment
from tests.service_text import SERVICE, expected_parts, transcript_segments


@pytest.fixture(scope="module")
def service():
    return transcript_segments()


def test_every_segment_gets_the_part_it_belongs_to(service):
    got, want = structure.label_segments(service), expected_parts()
    wrong = [(s.start, w, g, s.text) for s, g, w in zip(service, got, want) if g != w]
    assert not wrong, "mislabelled: " + "; ".join(f"{t:.0f}s wanted {w} got {g}" for t, w, g, _ in wrong)


def test_nothing_is_left_unlabelled(service):
    assert all(structure.label_segments(service))


def test_an_empty_transcript_has_no_shape():
    assert structure.label_segments([]) == []
    assert structure.blocks([]) == []


def test_the_service_comes_out_as_blocks_in_order(service):
    found = structure.blocks(service)
    assert [b.part for b in found] == [part for part, _s, _l in SERVICE]
    assert all(a.end <= b.start for a, b in zip(found, found[1:]))


def test_the_sermon_is_the_longest_block(service):
    found = structure.blocks(service)
    assert max(found, key=lambda b: b.seconds).part == "preek"


def test_a_service_with_no_cues_at_all_still_finds_its_sermon():
    """No recognisable words anywhere: the long stretch of talking is the sermon."""
    plain = [Segment(start=i * 20.0, end=i * 20.0 + 18.0, text=f"Zin {i} zonder herkenbare woorden.")
             for i in range(40)]
    found = structure.blocks(plain)
    assert any(b.part == "preek" for b in found)


def test_singing_is_recognised_by_the_silence_it_leaves():
    """Four minutes with nothing said, half way through a service, is a song."""
    spoken = [Segment(start=i * 12.0, end=i * 12.0 + 10.0, text="Zo gaat dat verder in de dienst.")
              for i in range(30)]
    quiet_from = spoken[14].end
    for i in range(15, 30):
        spoken[i] = Segment(start=spoken[i].start + 240.0, end=spoken[i].end + 240.0, text=spoken[i].text)
    assert spoken[15].start - quiet_from > 240
    assert "zang" in structure.label_segments(spoken)


def test_a_thinly_written_transcript_is_not_one_long_song():
    """When every sentence is a minute apart, a minute of silence means nothing."""
    sparse = [Segment(start=i * 60.0, end=i * 60.0 + 6.0,
                      text="Vandaag wil ik met jullie praten over vertrouwen.") for i in range(20)]
    assert "zang" not in structure.label_segments(sparse)


def test_the_gap_that_counts_as_music_follows_the_transcript(service):
    dense = [Segment(start=i * 4.0, end=i * 4.0 + 3.5, text="Kort.") for i in range(20)]
    sparse = [Segment(start=i * 90.0, end=i * 90.0 + 6.0, text="Ver uit elkaar.") for i in range(20)]
    assert structure.song_gap(dense) == structure.SONG_GAP
    assert structure.song_gap(sparse) > structure.SONG_GAP


def test_two_stray_sentences_are_not_a_part_of_the_service():
    """One passing mention of the collection does not make a notices block."""
    lines = ["Vandaag wil ik met jullie praten over geven."] * 6
    lines.insert(3, "Dat heeft niets met de collecte te maken.")
    segments = [Segment(start=i * 10.0, end=i * 10.0 + 9.0, text=t) for i, t in enumerate(lines)]
    assert structure.label_segments(segments).count("mededelingen") == 0


@pytest.mark.parametrize("part", ["mededelingen", "zang", "zegen", "welkom"])
def test_the_parts_a_clip_never_comes_from(part):
    assert part in structure.SKIP


@pytest.mark.parametrize("part", ["preek", "lezing", "gebed"])
def test_the_parts_worth_looking_at(part):
    assert part not in structure.SKIP


def test_a_window_inside_the_notices_is_not_sent(service):
    found = structure.blocks(service)
    notices = next(b for b in found if b.part == "mededelingen")
    assert not structure.worth_analysing(found, notices.start + 1, notices.end - 1)


def test_a_window_that_runs_from_the_singing_into_the_sermon_is_still_sent(service):
    """A moment on a seam must not be lost because it starts during a song."""
    found = structure.blocks(service)
    sermon = next(b for b in found if b.part == "preek")
    assert structure.worth_analysing(found, sermon.start - 120, sermon.start + 120)


def test_the_sermon_is_always_worth_looking_at(service):
    found = structure.blocks(service)
    sermon = next(b for b in found if b.part == "preek")
    assert structure.worth_analysing(found, sermon.start, sermon.end)


def test_roughly_half_the_service_is_never_sent(service):
    everything = discovery.build_windows(service)
    keeping, _shape, dropped = discovery.sermon_windows(service)
    assert len(keeping) + dropped == len(everything)
    assert dropped / len(everything) >= 0.4, "a service is about half sermon; the rest should not be sent"


def test_no_window_that_is_sent_sits_wholly_in_a_skipped_part(service):
    keeping, shape, _dropped = discovery.sermon_windows(service)
    for window in keeping:
        assert structure.worth_analysing(shape, window.start, window.end)


def test_every_window_sent_knows_which_part_it_is_in(service):
    keeping, _shape, _dropped = discovery.sermon_windows(service)
    assert all(w.part in structure.PART_LABEL.values() for w in keeping)
    assert any(w.part == structure.PART_LABEL["preek"] for w in keeping)


def test_the_windows_sent_are_numbered_from_one_again(service):
    keeping, _shape, _dropped = discovery.sermon_windows(service)
    assert [w.index for w in keeping] == list(range(len(keeping)))


def sent(window, about="", monkeypatch=None) -> str:
    """The user message analyze_window actually puts on the wire."""
    seen = {}

    def catch(user, system, schema):
        seen["user"] = user
        return schema(candidates=[])

    monkeypatch.setattr(discovery, "ask", catch)
    discovery.analyze_window(window, about)
    return seen["user"]


def test_the_part_is_put_in_front_of_the_model(service, monkeypatch):
    keeping, _shape, _dropped = discovery.sermon_windows(service)
    sermon = next(w for w in keeping if w.part == structure.PART_LABEL["preek"])
    message = sent(sermon, monkeypatch=monkeypatch)
    assert f"Dit deel van de dienst is: {sermon.part}." in message
    assert "minuten na het begin" in message, "where in the service it sits"


def test_what_came_before_is_sent_along_but_marked_off_limits(service, monkeypatch):
    keeping, _shape, _dropped = discovery.sermon_windows(service)
    later = next(w for w in keeping if w.lead)
    message = sent(later, monkeypatch=monkeypatch)
    assert "Wat hieraan voorafging" in message
    assert "kies hier niets uit" in message
    assert later.lead[-1].text.strip() in message


def test_the_summary_names_the_parts_and_when_they_are(service):
    line = structure.summary(structure.blocks(service))
    assert "preek" in line and "mededelingen" in line
    assert ":" in line, "the times are there for the model to place a moment"


def test_a_stray_sentence_does_not_split_the_sermon_in_two(service):
    """One mention of the collection in the middle of the preaching is a sentence."""
    from backend.models import Segment as Seg

    lines = list(service)
    sermon_at = next(i for i, s in enumerate(lines) if "praten over rust" in s.text)
    stray = lines[sermon_at + 3]
    lines[sermon_at + 3] = Seg(start=stray.start, end=stray.end,
                               text="En dat heeft niets met de collecte te maken.")
    found = structure.blocks(lines)
    sermon_blocks = [b for b in found if b.part == "preek"]
    assert len(sermon_blocks) == 1, "the preaching stays one block"
    assert not any(b.part == "mededelingen" and b.seconds < 20 for b in found)


def test_short_islands_are_folded_into_the_longer_neighbour():
    from backend.models import Segment as Seg

    long_before = [Seg(start=i * 10.0, end=i * 10.0 + 9.0, text="Vandaag wil ik praten over rust.")
                   for i in range(20)]
    island = [Seg(start=200.0, end=205.0, text="De collecte is voor de diaconie.")]
    short_after = [Seg(start=210.0, end=219.0, text="Laten we bidden.")]
    labels = structure.label_segments(long_before + island + short_after)
    assert labels[20] == labels[19], "the island joined the long stretch, not the short one"
