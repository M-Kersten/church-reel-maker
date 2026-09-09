"""The church's own words: what is offered to be learned, and what is left alone."""

import pytest

from backend import brands, models, transcription, wordlearn
from backend.models import Segment, Vocabulary


def line(start: float, text: str) -> Segment:
    return Segment(start=start, end=start + 3.0, text=text)


# --- spotting a misheard word ---------------------------------------------------

def test_a_misheard_word_is_spotted():
    found = wordlearn.suggestions([line(0, "we zingen lie 302 samen")],
                                  [line(0, "we zingen Lied 302 samen")])
    assert found == {"lie": "Lied"}


def test_a_misheard_name_is_spotted():
    found = wordlearn.suggestions([line(0, "vorige week sprak dirk de brie hier")],
                                  [line(0, "vorige week sprak Dirk de Bree hier")])
    assert found == {"dirk": "Dirk", "brie": "Bree"}


def test_an_untouched_line_offers_nothing():
    same = [line(0, "God vraagt niet dat je perfect bent")]
    assert wordlearn.suggestions(same, list(same)) == {}


def test_a_capital_at_the_start_of_a_line_is_only_sentence_case():
    found = wordlearn.suggestions([line(0, "genade is geen beloning")],
                                  [line(0, "Genade is geen beloning")])
    assert found == {}


def test_a_capital_in_the_middle_of_a_line_is_a_name():
    """Two words fixed together are learned as the phrase they are."""
    found = wordlearn.suggestions([line(0, "dat zegt de heilige geest hier")],
                                  [line(0, "dat zegt de Heilige Geest hier")])
    assert found == {"heilige geest": "Heilige Geest"}


def test_a_line_that_was_rewritten_is_not_a_misheard_word():
    """Someone tidying a sentence is not teaching the model to hear."""
    found = wordlearn.suggestions([line(0, "en toen zei ze dat het goed was")],
                                  [line(0, "en toen zei ze dat alles uiteindelijk in orde kwam")])
    assert found == {}


def test_a_word_that_was_only_added_teaches_nothing():
    found = wordlearn.suggestions([line(0, "we zingen samen")], [line(0, "we zingen nu samen")])
    assert found == {}


def test_a_word_that_was_only_removed_teaches_nothing():
    found = wordlearn.suggestions([line(0, "we zingen nu samen")], [line(0, "we zingen samen")])
    assert found == {}


@pytest.mark.parametrize("heard,meant,expected", [
    ("lie", "Lied", True),
    ("brie", "Bree", True),
    ("heiligegeest", "Heilige Geest", True),
    ("de", "die", False),          # too short to be a name
    ("honden", "katten", False),   # a different word, not a misheard one
    ("lied", "Lied", True),        # a capital on a word that is not a sentence opener
    ("we", "We", False),           # sentence case on an ordinary word
    ("heer", "Heer", True),
])
def test_what_is_worth_remembering(heard, meant, expected):
    assert wordlearn.worth_learning(heard, meant) is expected


def test_lines_are_matched_by_their_time_not_their_order():
    original = [line(0, "eerste regel"), line(10, "we zingen lie 302")]
    edited = [line(10, "we zingen Lied 302"), line(0, "eerste regel")]
    assert wordlearn.suggestions(original, edited) == {"lie": "Lied"}


def test_a_line_that_was_split_or_moved_is_skipped():
    """A segment that no longer starts where it did cannot be compared word for word."""
    assert wordlearn.suggestions([line(0, "we zingen lie 302")], [line(4.5, "we zingen Lied 302")]) == {}


# --- the church's word list ------------------------------------------------------

@pytest.fixture
def brand_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(brands, "BRANDS_DIR", tmp_path)
    monkeypatch.setattr(brands, "ACTIVE_FILE", tmp_path / "actief.json")
    return tmp_path


def test_a_correction_is_remembered_for_next_time(brand_dir):
    brands.save(brands.Brand(id="kerk", name="Kerk"))
    brands.set_active("kerk")
    brands.learn_corrections({"Lie": "Lied", "brie": "Bree"})
    again = brands.active().vocabulary.corrections
    assert again["lie"] == "Lied", "keyed on what the model hears, in lower case"
    assert again["brie"] == "Bree"


def test_learning_the_same_thing_twice_changes_nothing(brand_dir):
    brands.save(brands.Brand(id="kerk", name="Kerk"))
    brands.set_active("kerk")
    brands.learn_corrections({"lie": "Lied"})
    brands.learn_corrections({"lie": "Lied"})
    assert brands.active().vocabulary.corrections == {"lie": "Lied"}


def test_an_empty_correction_is_not_learned(brand_dir):
    brands.save(brands.Brand(id="kerk", name="Kerk"))
    brands.set_active("kerk")
    brands.learn_corrections({"lied": "lied", "": "iets", "iets": ""})
    assert brands.active().vocabulary.corrections == {}


def test_a_correction_that_only_adds_capitals_is_learned(brand_dir):
    """Corrections match without case and are written back with it."""
    brands.save(brands.Brand(id="kerk", name="Kerk"))
    brands.set_active("kerk")
    brands.learn_corrections({"heilige geest": "Heilige Geest"})
    fixes = brands.active().vocabulary.corrections
    assert fixes == {"heilige geest": "Heilige Geest"}
    assert transcription.apply_corrections("de heilige geest werkt", fixes) == "de Heilige Geest werkt"


def test_a_new_brand_starts_with_the_word_list_it_was_copied_from(brand_dir):
    first = brands.Brand(id="een", name="Een", vocabulary=Vocabulary(preachers=["Dirk de Bree"]))
    brands.save(first)
    brands.set_active("een")
    second = brands.create("Twee", copy_from="een")
    assert second.vocabulary.preachers == ["Dirk de Bree"]


# --- what the speech model is told ------------------------------------------------

def test_the_church_names_reach_the_speech_model(brand_dir, monkeypatch):
    brands.save(brands.Brand(id="kerk", name="Kerk",
                             church=models.ChurchInfo(churchName="Nieuwe Kerk"),
                             vocabulary=Vocabulary(preachers=["Dirk de Bree"], series=["Onderweg"],
                                                   songbooks=["Opwekking"], places=["Wittevrouwen"])))
    brands.set_active("kerk")
    prompt = transcription.initial_prompt()
    for word in ("Nieuwe Kerk", "Dirk de Bree", "Onderweg", "Opwekking", "Wittevrouwen"):
        assert word in prompt


def test_the_church_corrections_are_applied_on_top_of_the_shared_ones(brand_dir):
    brands.save(brands.Brand(id="kerk", name="Kerk",
                             vocabulary=Vocabulary(corrections={"brie": "Bree"})))
    brands.set_active("kerk")
    fixes = transcription.all_corrections()
    assert fixes["brie"] == "Bree"
    assert "lee" in fixes, "the shared word list is still there underneath"


def test_a_church_with_nothing_of_its_own_still_gets_the_shared_list(brand_dir):
    brands.save(brands.Brand(id="kerk", name="Kerk"))
    brands.set_active("kerk")
    assert transcription.initial_prompt()
    assert transcription.all_corrections()
