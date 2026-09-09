"""Fitting a frame into the square the models want, and thinning out what comes back.

The detector itself needs onnxruntime and a model file; these are the parts around it that
decide where a detection lands in the source picture, and they are wrong silently.
"""

import pytest

from backend import vision
from backend.vision import Box, fit_for, overlap, thin_out

SIZES = [(1920, 1080), (1280, 720), (3840, 2160), (1080, 1920), (1440, 1080), (640, 640),
         (2560, 1080), (720, 576)]


@pytest.mark.parametrize("size", SIZES)
def test_the_whole_picture_fits_inside_the_square(size):
    fit = fit_for(*size)
    assert fit.width <= vision.SIDE and fit.height <= vision.SIDE
    assert fit.pad_x >= 0 and fit.pad_y >= 0
    assert fit.pad_x * 2 + fit.width <= vision.SIDE
    assert fit.pad_y * 2 + fit.height <= vision.SIDE


@pytest.mark.parametrize("size", SIZES)
def test_one_side_of_the_picture_touches_the_square(size):
    fit = fit_for(*size)
    assert max(fit.width, fit.height) >= vision.SIDE - 1, "scaled down further than it had to be"


@pytest.mark.parametrize("size", SIZES)
def test_the_aspect_ratio_survives_the_fit(size):
    width, height = size
    fit = fit_for(width, height)
    assert fit.width / fit.height == pytest.approx(width / height, rel=0.01)


@pytest.mark.parametrize("size", SIZES)
def test_the_centre_of_the_square_is_the_centre_of_the_picture(size):
    width, height = size
    fit = fit_for(width, height)
    x, y = fit.to_source(vision.SIDE / 2, vision.SIDE / 2)
    assert x == pytest.approx(width / 2, abs=2)
    assert y == pytest.approx(height / 2, abs=2)


@pytest.mark.parametrize("size", SIZES)
def test_the_corners_map_back_to_the_corners(size):
    width, height = size
    fit = fit_for(width, height)
    left, top = fit.to_source(fit.pad_x, fit.pad_y)
    right, bottom = fit.to_source(fit.pad_x + fit.width, fit.pad_y + fit.height)
    assert (left, top) == pytest.approx((0, 0), abs=2)
    assert (right, bottom) == pytest.approx((width, height), abs=2)


def test_scaled_sizes_stay_even():
    for size in SIZES:
        fit = fit_for(*size)
        assert fit.width % 2 == 0 and fit.height % 2 == 0, "FFmpeg pads to even numbers"


def test_a_length_comes_back_in_source_pixels():
    fit = fit_for(1920, 1080)
    assert fit.length(fit.scale * 200) == pytest.approx(200)


# --- boxes ------------------------------------------------------------------------


def test_a_box_knows_its_own_edges():
    box = Box(x=100, y=50, w=40, h=60, score=0.9)
    assert (box.left, box.right) == (80, 120)


def test_a_face_inside_a_body_belongs_to_it():
    body = Box(x=100, y=200, w=80, h=300, score=0.8)
    face = Box(x=105, y=120, w=30, h=40, score=0.9)
    assert body.holds(face)


def test_a_face_beside_a_body_does_not():
    body = Box(x=100, y=200, w=80, h=300, score=0.8)
    assert not body.holds(Box(x=400, y=120, w=30, h=40, score=0.9))


def test_a_face_far_above_a_body_does_not():
    body = Box(x=100, y=200, w=80, h=100, score=0.8)
    assert not body.holds(Box(x=100, y=900, w=30, h=40, score=0.9))


def test_two_boxes_on_top_of_each_other_overlap_completely():
    box = Box(x=100, y=100, w=50, h=50, score=0.5)
    assert overlap(box, box) == pytest.approx(1.0)


def test_boxes_that_miss_each_other_do_not_overlap():
    assert overlap(Box(x=0, y=0, w=10, h=10, score=0.5),
                   Box(x=100, y=100, w=10, h=10, score=0.5)) == 0.0


def test_the_best_of_a_pile_of_boxes_survives():
    best = Box(x=100, y=100, w=50, h=50, score=0.9)
    kept = thin_out([Box(x=104, y=100, w=50, h=50, score=0.6), best,
                     Box(x=96, y=102, w=52, h=48, score=0.7)])
    assert kept == [best]


def test_two_people_apart_are_both_kept():
    left = Box(x=100, y=100, w=50, h=50, score=0.9)
    right = Box(x=900, y=100, w=50, h=50, score=0.8)
    assert thin_out([left, right]) == [left, right]


def test_nothing_in_nothing_out():
    assert thin_out([]) == []


# --- the models -------------------------------------------------------------------


def test_the_face_model_ships_with_the_app():
    assert vision.FACE_MODEL.is_file(), "vision/face.onnx belongs in the repository"


def test_a_missing_face_model_is_fatal_rather_than_silent(tmp_path, monkeypatch):
    monkeypatch.setattr(vision, "FACE_MODEL", tmp_path / "gone.onnx")
    with pytest.raises(vision.NoModel):
        vision.ensure_models()


def test_a_person_model_that_arrived_half_way_is_not_kept(tmp_path, monkeypatch):
    monkeypatch.setattr(vision, "VISION_DIR", tmp_path)
    monkeypatch.setattr(vision, "PERSON_MODEL", tmp_path / "person.onnx")

    class Half:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def read(self, _size):
            if getattr(self, "done", False):
                return b""
            self.done = True
            return b"x" * 1000

    monkeypatch.setattr(vision.urllib.request, "urlopen", lambda *a, **k: Half())
    with pytest.raises(vision.NoModel):
        vision.ensure_models()
    assert not (tmp_path / "person.onnx").exists()
    assert not list(tmp_path.glob("*.part")), "the half download is cleaned up"
