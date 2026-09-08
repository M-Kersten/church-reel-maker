"""Storage, brands and the word list: the pieces that hold a church's own settings."""

import json

import pytest

from backend import brands, models, transcription


def test_write_atomic_leaves_no_half_file(tmp_path):
    target = tmp_path / "thing.json"
    models.write_atomic(target, json.dumps({"a": 1}))
    assert json.loads(target.read_text()) == {"a": 1}
    assert list(tmp_path.iterdir()) == [target], "no temporary file left behind"


def test_write_atomic_replaces_the_old_content(tmp_path):
    target = tmp_path / "thing.json"
    models.write_atomic(target, "first")
    models.write_atomic(target, "second")
    assert target.read_text() == "second"


def test_new_project_has_workable_defaults():
    project = models.Project(id="project-test", createdAt="2026-09-08T10:00:00+00:00")
    assert project.output.width == 1080 and project.output.height == 1920
    assert project.style.fontSize >= 24
    assert project.crop is None, "the crop is chosen once the video has been probed"
    assert project.cropStrategy == "static"


def test_a_brand_round_trips_through_json():
    brand = brands.Brand(id="test", name="Test", church=models.ChurchInfo(churchName="Test"))
    again = brands.Brand.model_validate_json(brand.model_dump_json())
    assert again == brand


@pytest.mark.parametrize("text,corrections,expected", [
    ("lee 302 zingen we", {"lee": "Lied"}, "Lied 302 zingen we"),
    ("Lee is een naam", {"lee": "Lied"}, "Lied is een naam"),
    ("bevrijding", {"lee": "Lied"}, "bevrijding"),
    ("here jezus", {"here jezus": "Here Jezus"}, "Here Jezus"),
    ("", {"lee": "Lied"}, ""),
    ("niets te doen", {}, "niets te doen"),
])
def test_corrections_replace_whole_words_only(text, corrections, expected):
    assert transcription.apply_corrections(text, corrections) == expected


def test_corrections_keep_the_rest_of_the_sentence():
    out = transcription.apply_corrections("we zingen lee 302 samen", {"lee": "Lied"})
    assert out == "we zingen Lied 302 samen"


def test_the_word_list_is_readable_and_has_both_halves():
    vocabulary = transcription.load_vocabulary()
    assert isinstance(vocabulary.get("initialPrompt", ""), str)
    assert isinstance(vocabulary.get("corrections", {}), dict)


def test_the_initial_prompt_mentions_the_church():
    prompt = transcription.initial_prompt()
    assert brands.active().church.churchName in prompt
