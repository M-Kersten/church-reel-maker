"""Finding the people in a frame.

Two small models, both run through onnxruntime, which is already here as a dependency of
the speech recogniser. Neither needs a graphics card.

  face.onnx    YuNet, 227 KB, shipped with the app. Gives the head, which is the thing you
               actually want to frame, and it is cheap enough to run on every sample.
  person.onnx  YOLOv10n, 9 MB, fetched on first use the way FFmpeg already is. Finds the
               speaker when the face is turned away, in shadow, or simply too small.

They are used together: the person box says who is on stage and holds that identity across
the clip, the face says where the head is inside it. When the face is gone the body carries
on alone, which is the whole reason for having both.
"""

import math
import subprocess
import threading
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

import numpy as np

from .models import ROOT

VISION_DIR = ROOT / "vision"
FACE_MODEL = VISION_DIR / "face.onnx"
PERSON_MODEL = VISION_DIR / "person.onnx"
PERSON_URL = "https://huggingface.co/onnx-community/yolov10n/resolve/main/onnx/model.onnx"
PERSON_BYTES = 9_386_116  # what a complete download weighs, so half a one is not kept

SIDE = 640  # both models take a square 640 frame
FACE_SCORE = 0.5
PERSON_SCORE = 0.35
PERSON_CLASS = 0  # COCO: person

_lock = threading.Lock()


class NoModel(RuntimeError):
    """A model is missing and could not be fetched, with a reason worth reading."""


@dataclass
class Box:
    """A detection, in the pixels of the source frame."""

    x: float  # centre
    y: float
    w: float
    h: float
    score: float

    @property
    def left(self) -> float:
        return self.x - self.w / 2

    @property
    def right(self) -> float:
        return self.x + self.w / 2

    def holds(self, other: "Box") -> bool:
        """Is the centre of `other` inside this box? Used to pair a face with a body."""
        return self.left <= other.x <= self.right and abs(other.y - self.y) <= self.h


# --- getting the models ---------------------------------------------------------


def have_models() -> bool:
    return FACE_MODEL.is_file() and PERSON_MODEL.is_file()


def ensure_models(on_progress=None) -> None:
    """Fetch what is missing. Only the person model is ever missing; the face ships with us."""
    if not FACE_MODEL.is_file():
        raise NoModel(f"Het herkenningsmodel {FACE_MODEL.name} ontbreekt in de map vision/. "
                      "Haal de app opnieuw op; dit bestand hoort erbij.")
    if PERSON_MODEL.is_file() and PERSON_MODEL.stat().st_size == PERSON_BYTES:
        return
    with _lock:
        if PERSON_MODEL.is_file() and PERSON_MODEL.stat().st_size == PERSON_BYTES:
            return
        VISION_DIR.mkdir(parents=True, exist_ok=True)
        part = PERSON_MODEL.with_suffix(".part")
        try:
            if on_progress:
                on_progress(0.0, "Het herkenningsmodel wordt eenmalig opgehaald (9 MB)")
            with urllib.request.urlopen(PERSON_URL, timeout=120) as answer, part.open("wb") as out:
                got = 0
                while chunk := answer.read(256 * 1024):
                    out.write(chunk)
                    got += len(chunk)
                    if on_progress:
                        on_progress(min(0.99, got / PERSON_BYTES),
                                    f"Het herkenningsmodel wordt opgehaald · {got // 1_000_000} van 9 MB")
            if part.stat().st_size != PERSON_BYTES:
                raise NoModel("Het herkenningsmodel kwam maar half binnen. Probeer het opnieuw.")
            part.replace(PERSON_MODEL)
        except NoModel:
            part.unlink(missing_ok=True)
            raise
        except Exception as exc:  # noqa: BLE001  no connection, a proxy, a moved file
            part.unlink(missing_ok=True)
            raise NoModel("Het herkenningsmodel kon niet opgehaald worden, dus de spreker "
                          f"volgen lukt nu niet. Kader het beeld zelf. ({exc})") from exc


# --- frames ---------------------------------------------------------------------


@dataclass
class Fit:
    """How a source frame is placed inside the square the models want."""

    scale: float
    width: int  # the scaled picture inside the square
    height: int
    pad_x: int
    pad_y: int

    def to_source(self, x: float, y: float) -> tuple[float, float]:
        return (x - self.pad_x) / self.scale, (y - self.pad_y) / self.scale

    def length(self, value: float) -> float:
        return value / self.scale


def fit_for(width: int, height: int) -> Fit:
    """Scale down to fit the square and centre it, the same arithmetic FFmpeg will do."""
    scale = min(SIDE / width, SIDE / height)
    inner_w = max(2, int(round(width * scale / 2)) * 2)
    inner_h = max(2, int(round(height * scale / 2)) * 2)
    return Fit(scale, inner_w, inner_h, (SIDE - inner_w) // 2, (SIDE - inner_h) // 2)


def sample_frames(source: Path, width: int, height: int, fps: float,
                  start: float | None = None, length: float | None = None) -> Iterator[np.ndarray]:
    """Decode the clip at `fps`, letterboxed into the square, one RGB array at a time."""
    fit = fit_for(width, height)
    seek = ["-ss", f"{start:.3f}"] if start else []
    take = ["-t", f"{length:.3f}"] if length else []
    command = ["ffmpeg", "-v", "error", *seek, "-i", str(source), *take,
               "-vf", (f"fps={fps},scale={fit.width}:{fit.height},"
                       f"pad={SIDE}:{SIDE}:{fit.pad_x}:{fit.pad_y}:color=black"),
               "-pix_fmt", "rgb24", "-f", "rawvideo", "-"]
    size = SIDE * SIDE * 3
    with subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL) as reading:
        while True:
            raw = reading.stdout.read(size)
            if len(raw) < size:
                break
            yield np.frombuffer(raw, np.uint8).reshape(SIDE, SIDE, 3)
        reading.stdout.close()
        reading.wait()


# --- detection ------------------------------------------------------------------


def overlap(a: Box, b: Box) -> float:
    wide = min(a.right, b.right) - max(a.left, b.left)
    tall = min(a.y + a.h / 2, b.y + b.h / 2) - max(a.y - a.h / 2, b.y - b.h / 2)
    if wide <= 0 or tall <= 0:
        return 0.0
    both = wide * tall
    return both / (a.w * a.h + b.w * b.h - both)


def thin_out(boxes: list[Box], limit: float = 0.35) -> list[Box]:
    """Keep the best of every pile of boxes that describe the same thing."""
    kept: list[Box] = []
    for box in sorted(boxes, key=lambda b: b.score, reverse=True):
        if all(overlap(box, other) < limit for other in kept):
            kept.append(box)
    return kept


class Eyes:
    """The two models, loaded once and asked about one frame at a time."""

    def __init__(self, fit: Fit, with_person: bool = True):
        import onnxruntime as ort

        quiet = ort.SessionOptions()
        quiet.log_severity_level = 3  # its warnings are about the model, not about us
        self.fit = fit
        self.face = ort.InferenceSession(str(FACE_MODEL), quiet, providers=["CPUExecutionProvider"])
        self.face_outputs = [o.name for o in self.face.get_outputs()]
        # Without the person model the faces carry the clip on their own. Worse when the
        # speaker turns away, and still better than a window that cannot move.
        self.person = (ort.InferenceSession(str(PERSON_MODEL), quiet, providers=["CPUExecutionProvider"])
                       if with_person and PERSON_MODEL.is_file() else None)

    def look(self, frame: np.ndarray, with_people: bool = True) -> tuple[list[Box], list[Box]]:
        """The faces and the people in one frame, in source pixels.

        The face model costs about 8 ms and the person model about 35, so the caller is
        allowed to ask for people less often. It loses nothing: a body says who is on stage
        and that changes slowly, while the head is what the frame is actually aimed at.
        """
        planes = frame.astype(np.float32).transpose(2, 0, 1)[None]
        looking = with_people and self.person is not None
        return self._faces(planes), self._people(planes / 255.0) if looking else []

    def _faces(self, planes: np.ndarray) -> list[Box]:
        got = dict(zip(self.face_outputs, self.face.run(None, {"input": planes})))
        found: list[Box] = []
        for stride in (8, 16, 32):
            cols = SIDE // stride
            score = np.sqrt(np.clip(got[f"cls_{stride}"][0][:, 0], 0, 1)
                            * np.clip(got[f"obj_{stride}"][0][:, 0], 0, 1))
            bbox = got[f"bbox_{stride}"][0]
            for i in np.where(score > FACE_SCORE)[0]:
                cx = (i % cols + bbox[i, 0]) * stride
                cy = (i // cols + bbox[i, 1]) * stride
                found.append(self._box(cx, cy, math.exp(bbox[i, 2]) * stride,
                                       math.exp(bbox[i, 3]) * stride, float(score[i])))
        return thin_out(found)

    def _people(self, planes: np.ndarray) -> list[Box]:
        # YOLOv10 answers with its own 300 best guesses, already thinned out.
        out = self.person.run(None, {"images": planes})[0][0]
        keep = (out[:, 4] > PERSON_SCORE) & (out[:, 5] == PERSON_CLASS)
        return [self._box((d[0] + d[2]) / 2, (d[1] + d[3]) / 2, d[2] - d[0], d[3] - d[1], float(d[4]))
                for d in out[keep]]

    def _box(self, cx: float, cy: float, w: float, h: float, score: float) -> Box:
        x, y = self.fit.to_source(cx, cy)
        return Box(x, y, self.fit.length(w), self.fit.length(h), score)
