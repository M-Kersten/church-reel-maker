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
SUPER = 1.5  # the end screen is drawn larger, so a slow dolly stays sharp
BIG_W, BIG_H = int(WIDTH * SUPER), int(HEIGHT * SUPER)

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


def build_ass(config: OutroConfig, church: ChurchInfo) -> str:
    fade_ms = int(config.fade * 1000)
    styles, events = [], []
    for i, line in enumerate(config.lines):
        family, bold = family_for(line.font or config.font, line.weight)
        styles.append(
            f"Style: L{i},{family},{line.size},{ass_color(line.color)},{ass_color(line.color)},"
            f"&H00000000,&H00000000,{-1 if bold else 0},0,0,0,100,100,{line.spacing},0,1,0,0,5,{MARGIN},{MARGIN},0,1"
        )
        text = fill(line.text, church).replace("{", "(").replace("}", ")").strip()
        if line.uppercase:
            text = text.upper()
        if not text:
            continue
        anchor = {"left": (4, MARGIN), "center": (5, WIDTH // 2), "right": (6, WIDTH - MARGIN)}[line.align]
        events.append(
            f"Dialogue: 0,{ass_seconds(min(line.delay, config.duration))},{ass_seconds(config.duration)},L{i},,0,0,0,,"
            f"{{\\fad({fade_ms},{fade_ms})\\an{anchor[0]}\\pos({anchor[1]},{line.y})}}{text}"
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
    """Turn the still end screen into a slow camera move, or scale it down when there is none."""
    frames = max(2, int(duration * FPS))
    centre = "x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
    if motion == "in":
        step = 0.12 / frames
        return f"zoompan=z='min(1+{step:.6f}*on,1.12)':d=1:{centre}:s={WIDTH}x{HEIGHT}:fps={FPS}"
    if motion == "out":
        step = 0.12 / frames
        return f"zoompan=z='max(1.12-{step:.6f}*on,1.0)':d=1:{centre}:s={WIDTH}x{HEIGHT}:fps={FPS}"
    if motion == "up":
        # A fixed slight crop that drifts from the bottom of the frame to the top.
        return (f"zoompan=z=1.08:d=1:x='iw/2-(iw/zoom/2)':y='(ih-ih/zoom)*(1-on/{frames})'"
                f":s={WIDTH}x{HEIGHT}:fps={FPS}")
    return f"scale={WIDTH}:{HEIGHT}"


def gradient_source(background: OutroBackground, duration: float) -> str:
    colors = [c for c in background.colors if c.strip()][:8] or ["#4B1E78", "#9B1B3A"]
    if len(colors) == 1:
        colors = colors * 2
    radians = math.radians(background.angle)
    dx, dy = math.cos(radians), math.sin(radians)
    half = (BIG_W * abs(dx) + BIG_H * abs(dy)) / 2
    points = [max(0, round(BIG_W / 2 - dx * half)), max(0, round(BIG_H / 2 - dy * half)),
              max(0, round(BIG_W / 2 + dx * half)), max(0, round(BIG_H / 2 + dy * half))]
    args = ":".join(f"c{i}=0x{c.lstrip('#')}" for i, c in enumerate(colors))
    # speed at its minimum keeps the gradient still instead of rotating.
    return (f"gradients=s={BIG_W}x{BIG_H}:r={FPS}:d={duration}:n={len(colors)}:{args}"
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


def build(config: OutroConfig | None = None, church: ChurchInfo | None = None) -> Path:
    """Render templates/outro.mp4 from the config. Returns the path."""
    brand = brands.active()
    config = config or brand.outro
    church = church or brand.church
    ass_path = TEMPLATES_DIR / "outro.ass"
    ass_path.write_text(build_ass(config, church), encoding="utf-8")

    background = config.background
    inputs: list[str] = []
    chain: list[str] = []
    if background.type == "image":
        image = TEMPLATES_DIR / background.image
        if not image.is_file():
            raise RuntimeError(f"De achtergrondafbeelding templates/{background.image} bestaat niet.")
        inputs += ["-loop", "1", "-t", f"{config.duration}", "-r", str(FPS), "-i", str(image)]
        chain.append(f"scale={BIG_W}:{BIG_H}:force_original_aspect_ratio=increase,crop={BIG_W}:{BIG_H}")
        if background.darken > 0:
            chain.append(f"drawbox=x=0:y=0:w=iw:h=ih:color=black@{background.darken}:t=fill")
    elif background.type == "gradient":
        inputs += ["-f", "lavfi", "-i", gradient_source(background, config.duration)]
    else:
        color = background.color.lstrip("#")
        inputs += ["-f", "lavfi", "-i", f"color=c=0x{color}:s={BIG_W}x{BIG_H}:r={FPS}:d={config.duration}"]

    logo_input: list[str] = []
    if config.logo.file:
        logo = TEMPLATES_DIR / "logos" / config.logo.file
        if not logo.is_file():
            logo = TEMPLATES_DIR / config.logo.file  # older configs pointed straight at templates/
        if not logo.is_file():
            raise RuntimeError(f"Het logobestand {config.logo.file} staat niet in templates/logos.")
        logo_input = ["-i", str(logo)]

    filters = [f"[0:v]{','.join(chain)}[bg]" if chain else "[0:v]null[bg]"]
    if logo_input:
        filters.append(f"[2:v]scale={int(config.logo.width * SUPER)}:-1[logo]")
        filters.append(f"[bg][logo]overlay=x=(W-w)/2:y={int(config.logo.y * SUPER)}-h/2[withlogo]")
        last = "withlogo"
    else:
        last = "bg"
    # The text is drawn at the larger size (libass scales from PlayRes), then the whole
    # card is moved and brought back to 1080x1920, so nothing looks soft.
    filters.append(f"[{last}]ass=filename='{filter_path(ass_path)}':fontsdir='{filter_path(FONTS_DIR)}',"
                   f"{motion_filter(config.motion, config.duration)},format=yuv420p[v]")

    temp = OUTRO_PATH.with_suffix(".part.mp4")
    command = [ffmpeg_binary(), "-y", "-hide_banner", "-loglevel", "error", *inputs,
               "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", *logo_input,
               "-filter_complex", ";".join(filters), "-map", "[v]", "-map", "1:a",
               "-t", f"{config.duration}", "-c:v", "libx264", "-preset", "medium", "-crf", "20",
               "-pix_fmt", "yuv420p", "-r", str(FPS), "-c:a", "aac", "-b:a", "96k", "-ar", "48000",
               "-movflags", "+faststart", str(temp)]
    result = subprocess.run(command, capture_output=True, text=True)
    ass_path.unlink(missing_ok=True)
    if result.returncode != 0:
        temp.unlink(missing_ok=True)
        raise RuntimeError("De afsluiter kon niet gemaakt worden: " + result.stderr.strip()[-800:])
    temp.replace(OUTRO_PATH)
    return OUTRO_PATH


def ensure_outro() -> None:
    """Rebuild outro.mp4 when the active brand changed. Never overwrites a newer hand-made video."""
    with _lock:
        brands.migrate()
        brand = brands.active()
        if not brand.outro.generate:
            return
        sources = [brands.path_for(brand.id), brands.ACTIVE_FILE]
        newest = max((p.stat().st_mtime for p in sources if p.is_file()), default=0.0)
        if OUTRO_PATH.is_file() and OUTRO_PATH.stat().st_mtime >= newest:
            return
        build(brand.outro, brand.church)
