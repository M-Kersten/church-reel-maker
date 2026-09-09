"""Following the speaker, calmly.

A wide camera at the back of a church puts the preacher in a small part of a broad frame. A
static 9:16 window either loses them when they move or has to be pulled so far out that the
clip looks like security footage. This turns detections into a path for the crop window to
walk, and almost all of the work here is about *not* moving:

  a dead zone   the speaker may drift around the middle of the frame without the camera
                reacting at all, so someone standing still gives a still frame
  a slow ease   when they do leave it, the frame glides back rather than snapping, at a
                speed low enough that you notice the speaker and not the camera
  one subject   whoever is most central on stage at the start is held for the rest of the
                clip, so a musician walking past does not steal the frame
  cuts          a church with several cameras cuts between them. There is nothing smooth
                about a cut, so the frame jumps with it instead of gliding across the room

Only x moves. The height and the zoom stay wherever the user put them: on a 9:16 window out
of a wide frame there is rarely anything above or below worth following, and vertical drift
is the first thing that reads as wobble.
"""

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from . import vision
from .models import CropWindow, Output, Track, VideoInfo
from .vision import Box

SAMPLE_FPS = 3.0  # how often a frame is looked at
PERSON_EVERY = 3  # ... and how often of those the slower person model is asked as well
PATH_FPS = 12.5  # how finely the finished path is written down

# Every distance below is a share of the crop's own width, so the same numbers behave the
# same way on a wide window and a tight one. The frame edge sits at 0.5 by that measure.
#
# Three zones. Inside the dead zone nothing happens at all, which is what makes a standing
# speaker give a still frame. Between it and the keep-in line the frame eases back, slowly
# enough to read as someone operating a camera. Past the keep-in line calm stops being the
# point: the speaker is about to walk out of the picture, so the frame goes as fast as it
# needs to until they are safely inside again.
DEAD_ZONE = 0.14  # ± this far from centre: no movement at all
KEEP_IN = 0.34  # ± this far: never mind smooth, catch up (the edge is at 0.5)
TAU = 0.45  # seconds for the frame to cover most of the distance back
MAX_PAN = 0.40  # crop widths per second, while easing
RESCUE_PAN = 1.10  # crop widths per second, while catching up
SNAP_AFTER = DEAD_ZONE  # a cut jumps only when the frame would have had to move anyway,
# so cutting back to a camera that already had the speaker in the middle stays perfectly still

# A cut is a spike against what this clip normally does, not an absolute number: two
# cameras in the same room differ far less than two rooms, and a dim church differs less
# than a bright one. The floor is what stops a quiet clip from inventing cuts out of noise.
CUT_FLOOR = 8.0
CUT_RATIO = 2.5
CUT_MEMORY = 12  # samples, so four seconds of "normal" to compare against
LOST_AFTER = 2.5  # seconds without a detection before the frame stops pretending to know
ENOUGH = 0.55  # less of the clip covered than this, and this is not worth offering

ProgressCallback = Callable[[float, str], None]


@dataclass
class Sighting:
    """Where the speaker was at one moment, and how sure we are."""

    at: float
    x: float | None  # centre of the head, in source pixels; None when nobody was found
    body: Box | None = None
    kind: str = ""  # "face" or "person", whichever gave the x
    cut: bool = False  # the picture changed completely just before this sample


@dataclass
class Watch:
    """The person being followed, and how fresh what we know about them is."""

    body: Box | None = None
    body_at: float = -99.0
    x: float | None = None
    x_at: float = -99.0

    def fresh(self, at: float) -> bool:
        return at - self.x_at <= LOST_AFTER


def centrality(box: Box, width: int) -> float:
    """1 in the middle of the frame, 0 at the edges."""
    return max(0.0, 1.0 - abs(box.x - width / 2) / (width / 2))


def prominence(box: Box, width: int, height: int) -> float:
    """How much this looks like the person the clip is about: central, large, confident."""
    size = min(1.0, (box.w * box.h) / (width * height * 0.08))
    return box.score * (0.55 + 0.45 * size) * (0.35 + 0.65 * centrality(box, width))


def choose(boxes: list[Box], width: int, height: int) -> Box | None:
    """Who to follow when nobody is being followed yet: the one holding the middle."""
    return max(boxes, key=lambda b: prominence(b, width, height)) if boxes else None


def again(boxes: list[Box], held: Box, width: int) -> Box | None:
    """The same person one sample later: the nearest box, if it is near enough to be them."""
    if not boxes:
        return None
    closest = min(boxes, key=lambda b: abs(b.x - held.x))
    return closest if abs(closest.x - held.x) <= width * 0.25 else None


def changed(before, after) -> float:
    """How different two sampled frames are, as a mean channel difference."""
    import numpy as np

    if before is None:
        return 0.0
    return float(np.abs(before[::8, ::8].astype(np.int16) - after[::8, ::8].astype(np.int16)).mean())


def is_cut(difference: float, recent: list[float]) -> bool:
    """Did the picture change more than this clip's own normal?"""
    if difference < CUT_FLOOR or not recent:
        return False
    usual = sorted(recent)[len(recent) // 2]
    return difference > max(CUT_FLOOR, CUT_RATIO * usual)


def look_once(eyes: "vision.Eyes", frame, held: Watch, at: float, info: VideoInfo,
              with_people: bool) -> tuple[float | None, str]:
    """Where the followed person's head is in this frame, and what said so.

    The body answers *who*, and it changes slowly enough to be asked about once a second.
    The face answers *where*, and is asked every time. When the face is gone the body
    carries the frame; when both are gone the last position stands for a moment and then
    the clip is simply admitted to be a gap.
    """
    faces, people = eyes.look(frame, with_people=with_people)
    if people:
        found = again(people, held.body, info.width) if held.body else choose(people, info.width, info.height)
        if found is not None:
            held.body, held.body_at = found, at

    body = held.body if at - held.body_at <= LOST_AFTER else None
    if body is not None:
        inside = [f for f in faces if body.holds(f)]
        if inside:
            return max(inside, key=lambda f: f.score).x, "face"
        return body.x, "person"
    if faces:
        return choose(faces, info.width, info.height).x, "face"
    return None, ""


def watch(source: Path, info: VideoInfo, start: float | None = None, length: float | None = None,
          on_progress: ProgressCallback | None = None,
          should_stop: Callable[[], None] | None = None) -> list[Sighting]:
    """Walk through the clip and note where the speaker is at every sample."""
    eyes = vision.Eyes(vision.fit_for(info.width, info.height))
    span = length or info.duration or 0.0
    held = Watch()
    seen: list[Sighting] = []
    previous = None

    recent: list[float] = []
    after_cut = False

    for index, frame in enumerate(vision.sample_frames(source, info.width, info.height,
                                                       SAMPLE_FPS, start, length)):
        if should_stop:
            should_stop()
        at = index / SAMPLE_FPS
        difference = changed(previous, frame)
        cut = is_cut(difference, recent)
        recent.append(difference)
        del recent[:-CUT_MEMORY]
        previous = frame
        if cut:
            held = Watch()  # another camera: nothing about the old frame carries over

        # Straight after a cut there is nobody being followed, so ask the model that can
        # find one rather than waiting for its turn to come round.
        ask_people = index % PERSON_EVERY == 0 or cut or after_cut
        after_cut = cut or (after_cut and held.body is None)
        x, kind = look_once(eyes, frame, held, at, info, with_people=ask_people)
        if x is not None:
            held.x, held.x_at = x, at
        seen.append(Sighting(at, x if x is not None else (held.x if held.fresh(at) else None),
                             held.body, kind, cut))

        if on_progress and span > 0 and index % 6 == 0:
            share = min(0.98, at / span)
            on_progress(share, f"De spreker wordt gevolgd · {int(share * 100)}%")
    return seen


# --- turning sightings into a path ------------------------------------------------


def half_width(info: VideoInfo, output: Output, crop: CropWindow) -> float:
    """Half the crop window, as a share of the source width. The dead zone is measured in it."""
    from .renderer import crop_geometry

    g = crop_geometry(info, output, crop)
    return (g.crop_w / g.scaled_w) / 2 if g.scaled_w else 0.5


def anchors(seen: list[Sighting], width: int) -> list[float | None]:
    """The sightings as fractions of the source width, holding through short gaps."""
    return [None if s.x is None else min(1.0, max(0.0, s.x / width)) for s in seen]


def glide(targets: list[float | None], cuts: list[bool], reach: float, start_at: float,
          fps: float = PATH_FPS, sample_fps: float = SAMPLE_FPS) -> tuple[list[float], list[int]]:
    """Walk the crop centre along the targets, and mostly stand still.

    `reach` is half the crop width; the dead zone and the speed limit are both measured in
    it, so the same numbers behave the same way on a wide crop and a tight one.
    """
    if not targets:
        return [], []
    span = (len(targets) - 1) / sample_fps
    steps = max(2, int(round(span * fps)) + 1)
    width = reach * 2
    dead, keep, snap = DEAD_ZONE * width, KEEP_IN * width, SNAP_AFTER * width
    limit, rescue = MAX_PAN * width / fps, RESCUE_PAN * width / fps
    ease = 1 - math.exp(-1 / (TAU * fps))

    # Start on the speaker rather than panning onto them: the first frame of a clip is not
    # the moment for a camera move, and the window the user set is only a fallback for a
    # clip where nobody was found at all.
    first = next((t for t in targets if t is not None), None)
    at = first if first is not None else start_at
    jumping = False  # a cut has happened and we are waiting to see where the speaker went
    seen_cut = -1
    path: list[float] = []
    jumps: list[int] = []
    for step in range(steps):
        moment = step / fps
        index = min(len(targets) - 1, int(moment * sample_fps))
        if cuts[index] and index != seen_cut:
            seen_cut, jumping = index, True
        target = targets[index]
        if jumping and target is not None:
            # A cut is not something to glide through: the room itself changed. Small
            # differences are left alone, or every cut back to the same camera would twitch.
            if abs(target - at) > snap:
                at = target
                jumps.append(step)
            jumping = False
        elif target is not None and abs(target - at) > keep:
            away = target - at
            at += max(-rescue, min(rescue, away))
        elif target is not None and abs(target - at) > dead:
            away = (target - at) * ease
            at += max(-limit, min(limit, away))
        path.append(round(min(1.0, max(0.0, at)), 5))
    return path, jumps


def coverage(seen: list[Sighting]) -> float:
    return sum(1 for s in seen if s.x is not None) / len(seen) if seen else 0.0


def build(source: Path, info: VideoInfo, output: Output, crop: CropWindow,
          start: float | None = None, length: float | None = None,
          on_progress: ProgressCallback | None = None,
          should_stop: Callable[[], None] | None = None) -> Track:
    """Look at the clip and come back with a path for the crop window to follow."""
    try:
        vision.ensure_models(on_progress)
    except vision.NoModel as exc:
        if not vision.FACE_MODEL.is_file():
            raise
        # Only the person model is missing. Faces alone find the speaker most of the time,
        # and a clip that follows him imperfectly beats one that cannot follow at all.
        print(f"[volgen] zonder het personenmodel, alleen op gezichten: {exc}")
    seen = watch(source, info, start, length, on_progress, should_stop)
    if should_stop:
        should_stop()
    found = coverage(seen)
    reach = half_width(info, output, crop)
    path, jumps = glide(anchors(seen, info.width), [s.cut for s in seen], reach, crop.x)
    faces = sum(1 for s in seen if s.kind == "face")
    bodies = sum(1 for s in seen if s.kind == "person")
    return Track(
        fps=PATH_FPS,
        x=path,
        coverage=round(found, 3),
        subject="face" if faces >= bodies and faces else ("person" if bodies else ""),
        cuts=[round(s.at, 2) for s in seen if s.cut],
        jumps=jumps,
        enough=found >= ENOUGH and len(path) > 1,
    )
