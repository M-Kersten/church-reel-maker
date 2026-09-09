"""The end screen (outro): its look comes from templates/outro.json.

The config holds background, fonts, colours and the text lines; the church name,
service times and Instagram handle come from templates/church.json and are filled
into the text with {churchName}, {serviceTimes} and {instagram}.

The video is rebuilt automatically whenever the config is newer than outro.mp4,
so editing the JSON is enough. Dropping in your own outro.mp4 keeps it: its file
date is then newer than the config and nothing is regenerated.
"""

import json
import math
import shutil
import subprocess
import threading
from pathlib import Path
from typing import Literal

from . import brands
from .models import FONTS_DIR, TEMPLATES_DIR, ChurchInfo, OutroBackground, OutroConfig
from .subtitles import ass_color, family_for

CONFIG_PATH = TEMPLATES_DIR / "outro.json"
CHURCH_PATH = TEMPLATES_DIR / "church.json"
OUTRO_PATH = TEMPLATES_DIR / "outro.mp4"
WIDTH, HEIGHT, FPS = 1080, 1920, 30
MARGIN = 60  # safe space left and right
ZOOM = 1.12  # how far a dolly travels
DRIFT = 1.08  # the fixed crop the upward drift moves within
# The background is drawn larger only when it has to move, so a pixel of rounding in the
# zoom lands well inside one pixel of the finished frame.
SUPER = 3
BIG_W, BIG_H = WIDTH * SUPER, HEIGHT * SUPER
CENTRE_X, CENTRE_Y = WIDTH / 2, HEIGHT / 2

_lock = threading.Lock()

DEFAULT_CONFIG = OutroConfig()


def load_config() -> OutroConfig:
    """The end screen of the brand that is active."""
    return brands.active().outro


def save_config(config: OutroConfig) -> None:
    brand = brands.active()
    brand.outro = config
    brands.save(brand)


def save_default_config() -> None:
    brands.migrate()


# --- building -------------------------------------------------------------------


def fill(text: str, church: ChurchInfo) -> str:
    return (text.replace("{churchName}", church.churchName)
                .replace("{serviceTimes}", "  ·  ".join(church.serviceTimes))
                .replace("{instagram}", church.instagram))


def ass_seconds(seconds: float) -> str:
    seconds = max(0.0, seconds)
    return f"{int(seconds // 3600)}:{int(seconds % 3600 // 60):02d}:{seconds % 60:05.2f}"


def zoom_at(motion: str, moment: float, duration: float) -> float:
    """How far the camera has pushed in at `moment`."""
    part = 0.0 if duration <= 0 else max(0.0, min(1.0, moment / duration))
    if motion == "in":
        return 1 + (ZOOM - 1) * part
    if motion == "out":
        return ZOOM - (ZOOM - 1) * part
    if motion == "up":
        return DRIFT
    return 1.0


def drift_at(motion: str, moment: float, duration: float) -> float:
    """Vertical offset of the whole card at `moment`, for the upward drift."""
    if motion != "up":
        return 0.0
    part = 0.0 if duration <= 0 else max(0.0, min(1.0, moment / duration))
    # How far the crop window's view travels on screen: the extra height the zoom bought.
    travel = HEIGHT * (DRIFT - 1)
    return travel * (0.5 - part)


def place(anchor: tuple[float, float], motion: str, moment: float, duration: float) -> tuple[float, float]:
    """Where an anchor point sits once the camera has moved."""
    zoom = zoom_at(motion, moment, duration)
    x = CENTRE_X + (anchor[0] - CENTRE_X) * zoom
    y = CENTRE_Y + (anchor[1] - CENTRE_Y) * zoom + drift_at(motion, moment, duration)
    return x, y


def motion_tags(motion: str, start: float, duration: float, anchor: tuple[float, float]) -> str:
    """Move and scale one line the way the camera does.

    libass interpolates positions and scales as floating point, so the text glides
    instead of snapping to whole pixels the way an FFmpeg crop would.
    """
    x0, y0 = place(anchor, motion, start, duration)
    if motion == "none":
        return f"\\pos({x0:.2f},{y0:.2f})"
    x1, y1 = place(anchor, motion, duration, duration)
    span = max(1, int((duration - start) * 1000))
    begin, end = zoom_at(motion, start, duration), zoom_at(motion, duration, duration)
    tags = f"\\move({x0:.2f},{y0:.2f},{x1:.2f},{y1:.2f},0,{span})\\fscx{begin * 100:.2f}\\fscy{begin * 100:.2f}"
    if abs(end - begin) > 1e-6:
        tags += f"\\t(0,{span},\\fscx{end * 100:.2f}\\fscy{end * 100:.2f})"
    return tags


def build_ass(config: OutroConfig, church: ChurchInfo) -> str:
    fade_ms = int(config.fade * 1000)
    # While the text scales, the wrap width has to leave room for it, or a line that just
    # fits at rest would suddenly break in two halfway through the move.
    wrap_margin = 0 if config.motion != "none" else MARGIN
    styles, events = [], []
    for i, line in enumerate(config.lines):
        family, bold = family_for(line.font or config.font, line.weight)
        styles.append(
            f"Style: L{i},{family},{line.size},{ass_color(line.color)},{ass_color(line.color)},"
            f"&H00000000,&H00000000,{-1 if bold else 0},0,0,0,100,100,{line.spacing},0,1,0,0,5,"
            f"{wrap_margin},{wrap_margin},0,1"
        )
        text = fill(line.text, church).replace("{", "(").replace("}", ")").strip()
        if line.uppercase:
            text = text.upper()
        if not text:
            continue
        align, anchor_x = {"left": (4, MARGIN), "center": (5, WIDTH // 2), "right": (6, WIDTH - MARGIN)}[line.align]
        start = min(line.delay, config.duration)
        moves = motion_tags(config.motion, start, config.duration, (anchor_x, line.y))
        events.append(
            f"Dialogue: 0,{ass_seconds(start)},{ass_seconds(config.duration)},L{i},,0,0,0,,"
            f"{{\\fad({fade_ms},{fade_ms})\\an{align}{moves}}}{text}"
        )
    return "\n".join([
        "[Script Info]", "ScriptType: v4.00+", f"PlayResX: {WIDTH}", f"PlayResY: {HEIGHT}",
        "WrapStyle: 0", "ScaledBorderAndShadow: yes", "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, "
        "Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, "
        "MarginR, MarginV, Encoding",
        *styles, "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
        *events,
    ]) + "\n"


def motion_filter(motion: str, duration: float) -> str:
    """Move the background the same way the text moves.

    A gradient or photograph has no fine detail, so the whole-pixel steps an FFmpeg
    crop takes are invisible here; the text, which does have fine detail, is moved by
    libass instead. Both follow the same straight line, so the two layers stay together.
    """
    if motion == "none":
        return f"scale={WIDTH}:{HEIGHT}"
    frames = max(2, int(duration * FPS))
    centre = "x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
    step = (ZOOM - 1) / frames
    if motion == "in":
        return f"zoompan=z='min(1+{step:.6f}*on,{ZOOM})':d=1:{centre}:s={WIDTH}x{HEIGHT}:fps={FPS}"
    if motion == "out":
        return f"zoompan=z='max({ZOOM}-{step:.6f}*on,1.0)':d=1:{centre}:s={WIDTH}x{HEIGHT}:fps={FPS}"
    # "up": a fixed slight crop that travels down the card, so the picture rises.
    # The window walks the same 1 - 1/DRIFT of the height that drift_at() moves the text.
    return (f"zoompan=z={DRIFT}:d=1:x='iw/2-(iw/zoom/2)':y='(ih-ih/zoom)*(on/{frames})'"
            f":s={WIDTH}x{HEIGHT}:fps={FPS}")


def gradient_source(background: OutroBackground, width: int, height: int) -> str:
    colors = [c for c in background.colors if c.strip()][:8] or ["#4B1E78", "#9B1B3A"]
    if len(colors) == 1:
        colors = colors * 2
    radians = math.radians(background.angle)
    dx, dy = math.cos(radians), math.sin(radians)
    half = (width * abs(dx) + height * abs(dy)) / 2
    points = [max(0, round(width / 2 - dx * half)), max(0, round(height / 2 - dy * half)),
              max(0, round(width / 2 + dx * half)), max(0, round(height / 2 + dy * half))]
    args = ":".join(f"c{i}=0x{c.lstrip('#')}" for i, c in enumerate(colors))
    # speed at its minimum keeps the gradient still instead of rotating.
    return (f"gradients=s={width}x{height}:r={FPS}:d=1:n={len(colors)}:{args}"
            f":x0={points[0]}:y0={points[1]}:x1={points[2]}:y1={points[3]}:speed=0.00001")


def filter_path(path: Path) -> str:
    """Escape a path for use inside an FFmpeg filter option (drive letters, quotes)."""
    return path.as_posix().replace("\\", "/").replace(":", "\\:").replace("'", "\\'")


def ffmpeg_binary() -> str:
    """ffmpeg from PATH, or the copy the launcher downloaded into tools/ffmpeg."""
    tools = TEMPLATES_DIR.parent / "tools" / "ffmpeg"
    for candidate in (shutil.which("ffmpeg"), tools / "ffmpeg.exe", tools / "ffmpeg"):
        if candidate and Path(candidate).is_file():
            return str(candidate)
    raise RuntimeError("FFmpeg is niet gevonden. Start de app een keer met start.bat of start.command, "
                       "of installeer FFmpeg en zet het in PATH.")


def logo_file(config: OutroConfig) -> Path | None:
    """The logo image on disk, or None when the end screen has no logo."""
    if not config.logo.file:
        return None
    logo = TEMPLATES_DIR / "logos" / config.logo.file
    if not logo.is_file():
        logo = TEMPLATES_DIR / config.logo.file  # older configs pointed straight at templates/
    if not logo.is_file():
        raise RuntimeError(f"Het logobestand {config.logo.file} staat niet in templates/logos.")
    return logo


def logo_chain(config: OutroConfig, scale: float) -> str:
    """Scale the logo and let it come up and go again with the text.

    The text fades because libass draws it with \\fad; the logo is a picture, so it needs
    its own fade over the alpha channel. Both use the same number of seconds, so the end
    screen arrives as one thing instead of a logo that is simply there from frame one.
    """
    steps = [f"scale={int(config.logo.width * scale)}:-1", "format=rgba"]
    if config.fade > 0:
        out = max(0.0, config.duration - config.fade)
        steps.append(f"fade=t=in:st=0:d={config.fade}:alpha=1")
        steps.append(f"fade=t=out:st={out}:d={config.fade}:alpha=1")
    return ",".join(steps)


def background_still(config: OutroConfig, width: int, height: int, destination: Path) -> None:
    """Draw the background once, as a single image the camera can move over.

    The logo is not in here: it has to fade, and a still cannot.
    """
    background = config.background
    inputs: list[str] = []
    chain: list[str] = []
    if background.type == "image":
        image = TEMPLATES_DIR / background.image
        if not image.is_file():
            raise RuntimeError(f"De achtergrondafbeelding templates/{background.image} bestaat niet.")
        inputs += ["-i", str(image)]
        chain.append(f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height}")
        if background.darken > 0:
            chain.append(f"drawbox=x=0:y=0:w=iw:h=ih:color=black@{background.darken}:t=fill")
    elif background.type == "gradient":
        inputs += ["-f", "lavfi", "-i", gradient_source(background, width, height)]
    else:
        color = background.color.lstrip("#")
        inputs += ["-f", "lavfi", "-i", f"color=c=0x{color}:s={width}x{height}:d=1"]

    filters = [f"[0:v]{','.join(chain)}[out]" if chain else "[0:v]null[out]"]

    command = [ffmpeg_binary(), "-y", "-hide_banner", "-loglevel", "error", *inputs,
               "-filter_complex", ";".join(filters), "-map", "[out]",
               "-frames:v", "1", "-update", "1", str(destination)]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError("De achtergrond van de afsluiter kon niet gemaakt worden: "
                           + result.stderr.strip()[-800:])


def build_command(config: OutroConfig, still: Path, ass: Path, width: int, destination: Path) -> list[str]:
    """The FFmpeg call that turns the background still into the end screen.

    Order matters. The logo is laid on the background first, so the camera carries it along
    exactly as it carries the background; the text comes last, drawn by libass at the size
    of the finished frame so it stays sharp.
    """
    inputs = ["-loop", "1", "-t", f"{config.duration}", "-r", str(FPS), "-i", str(still)]
    logo = logo_file(config)
    steps = ["[0:v]null[card]"]
    if logo:
        inputs += ["-loop", "1", "-t", f"{config.duration}", "-r", str(FPS), "-i", str(logo)]
        scale = width / WIDTH
        steps = [f"[1:v]{logo_chain(config, scale)}[logo]",
                 f"[0:v][logo]overlay=x=(W-w)/2:y={int(config.logo.y * scale)}-h/2:format=auto[card]"]
    audio = 2 if logo else 1  # the silent track comes after the picture inputs
    inputs += ["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo"]
    steps.append(f"[card]{motion_filter(config.motion, config.duration)},setsar=1,"
                 f"ass=filename='{filter_path(ass)}':fontsdir='{filter_path(FONTS_DIR)}',"
                 f"format=yuv420p[v]")
    return [ffmpeg_binary(), "-y", "-hide_banner", "-loglevel", "error", *inputs,
            "-filter_complex", ";".join(steps), "-map", "[v]", "-map", f"{audio}:a",
            "-t", f"{config.duration}", "-c:v", "libx264", "-preset", "medium", "-crf", "20",
            "-pix_fmt", "yuv420p", "-r", str(FPS), "-c:a", "aac", "-b:a", "96k", "-ar", "48000",
            "-movflags", "+faststart", str(destination)]


def build(config: OutroConfig | None = None, church: ChurchInfo | None = None) -> Path:
    """Render templates/outro.mp4 from the config. Returns the path."""
    brand = brands.active()
    config = config or brand.outro
    church = church or brand.church
    ass_path = TEMPLATES_DIR / "outro.ass"
    ass_path.write_text(build_ass(config, church), encoding="utf-8")

    # A moving background needs the extra pixels to move into; a still one does not.
    moving = config.motion != "none"
    still_path = OUTRO_PATH.with_suffix(".bg.png")
    temp = OUTRO_PATH.with_suffix(".part.mp4")
    try:
        width = BIG_W if moving else WIDTH
        background_still(config, width, BIG_H if moving else HEIGHT, still_path)
        command = build_command(config, still_path, ass_path, width, temp)
        result = subprocess.run(command, capture_output=True, text=True)
        if result.returncode != 0:
            temp.unlink(missing_ok=True)
            raise RuntimeError("De afsluiter kon niet gemaakt worden: " + result.stderr.strip()[-800:])
        temp.replace(OUTRO_PATH)
    finally:
        ass_path.unlink(missing_ok=True)
        still_path.unlink(missing_ok=True)
    return OUTRO_PATH


def ensure_outro() -> None:
    """Rebuild outro.mp4 when the active brand or the way it is drawn changed.

    Never overwrites a newer hand-made video. This file counts as a source: a pull that
    changes how the end screen is made would otherwise leave the old video in place until
    someone happened to edit the brand.
    """
    with _lock:
        brands.migrate()
        brand = brands.active()
        if not brand.outro.generate:
            return
        sources = [brands.path_for(brand.id), brands.ACTIVE_FILE, Path(__file__)]
        newest = max((p.stat().st_mtime for p in sources if p.is_file()), default=0.0)
        if OUTRO_PATH.is_file() and OUTRO_PATH.stat().st_mtime >= newest:
            return
        build(brand.outro, brand.church)
