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

from pydantic import BaseModel, Field

from .models import FONTS_DIR, TEMPLATES_DIR, ChurchInfo, load_church_info
from .subtitles import ass_color, family_for

CONFIG_PATH = TEMPLATES_DIR / "outro.json"
CHURCH_PATH = TEMPLATES_DIR / "church.json"
OUTRO_PATH = TEMPLATES_DIR / "outro.mp4"
WIDTH, HEIGHT, FPS = 1080, 1920, 30

_lock = threading.Lock()

FontWeight = Literal["regular", "medium", "semibold", "bold", "extrabold"]


class OutroBackground(BaseModel):
    type: Literal["solid", "gradient", "image"] = "gradient"
    color: str = "#4B1E78"  # used when type is "solid"
    colors: list[str] = ["#C8801B", "#9B1B3A", "#5B1B6E"]  # used when type is "gradient", 2 to 8 colours
    angle: float = 115  # gradient direction in degrees; 0 = left to right, 90 = top to bottom
    image: str = ""  # file name in templates/, used when type is "image"
    darken: float = Field(default=0.35, ge=0.0, le=1.0)  # black veil over the image, for readable text


class OutroLogo(BaseModel):
    file: str = ""  # png (transparency supported) in templates/
    width: int = 420
    y: int = 600  # centre of the logo, in pixels from the top of the 1080x1920 frame


class OutroLine(BaseModel):
    text: str
    y: int = 960  # centre of the line, in pixels from the top
    size: int = 56
    weight: FontWeight = "bold"
    color: str = "#FFFFFF"
    font: str = ""  # empty = the config's main font
    spacing: float = 0  # extra letter spacing in pixels
    uppercase: bool = False
    delay: float = 0.0  # seconds before this line appears


class OutroConfig(BaseModel):
    generate: bool = True  # false: never touch outro.mp4 (you supply your own video)
    duration: float = Field(default=5.0, ge=1.0, le=30.0)
    font: str = "Poppins"  # Inter, Montserrat, Poppins or Arial
    fade: float = Field(default=0.4, ge=0.0, le=3.0)  # fade in and out, in seconds
    background: OutroBackground = OutroBackground()
    logo: OutroLogo = OutroLogo()
    lines: list[OutroLine] = [
        OutroLine(text="Welkom", y=760, size=34, weight="bold", color="#F0C862", spacing=8, uppercase=True),
        OutroLine(text="{churchName}", y=860, size=92, weight="extrabold", delay=0.1),
        OutroLine(text="Elke zondag {serviceTimes}", y=1000, size=46, weight="medium", color="#E7DEF2", delay=0.25),
        OutroLine(text="{instagram}", y=1180, size=52, weight="bold", delay=0.4),
    ]


DEFAULT_CONFIG = OutroConfig()


def load_config() -> OutroConfig:
    if CONFIG_PATH.is_file():
        return OutroConfig.model_validate_json(CONFIG_PATH.read_text(encoding="utf-8"))
    return OutroConfig()


def save_config(config: OutroConfig) -> None:
    CONFIG_PATH.write_text(json.dumps(config.model_dump(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def save_default_config() -> None:
    """Write templates/outro.json the first time, so there is something to edit."""
    if not CONFIG_PATH.is_file():
        CONFIG_PATH.write_text(json.dumps(DEFAULT_CONFIG.model_dump(), indent=2, ensure_ascii=False) + "\n",
                               encoding="utf-8")


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
            f"&H00000000,&H00000000,{-1 if bold else 0},0,0,0,100,100,{line.spacing},0,1,0,0,5,60,60,0,1"
        )
        text = fill(line.text, church).replace("{", "(").replace("}", ")").strip()
        if line.uppercase:
            text = text.upper()
        if not text:
            continue
        events.append(
            f"Dialogue: 0,{ass_seconds(min(line.delay, config.duration))},{ass_seconds(config.duration)},L{i},,0,0,0,,"
            f"{{\\fad({fade_ms},{fade_ms})\\pos({WIDTH // 2},{line.y})}}{text}"
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


def gradient_source(background: OutroBackground, duration: float) -> str:
    colors = [c for c in background.colors if c.strip()][:8] or ["#4B1E78", "#9B1B3A"]
    if len(colors) == 1:
        colors = colors * 2
    radians = math.radians(background.angle)
    dx, dy = math.cos(radians), math.sin(radians)
    half = (WIDTH * abs(dx) + HEIGHT * abs(dy)) / 2
    points = [max(0, round(WIDTH / 2 - dx * half)), max(0, round(HEIGHT / 2 - dy * half)),
              max(0, round(WIDTH / 2 + dx * half)), max(0, round(HEIGHT / 2 + dy * half))]
    args = ":".join(f"c{i}=0x{c.lstrip('#')}" for i, c in enumerate(colors))
    # speed at its minimum keeps the gradient still instead of rotating.
    return (f"gradients=s={WIDTH}x{HEIGHT}:r={FPS}:d={duration}:n={len(colors)}:{args}"
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
    config = config or load_config()
    church = church or load_church_info()
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
        chain.append(f"scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=increase,crop={WIDTH}:{HEIGHT}")
        if background.darken > 0:
            chain.append(f"drawbox=x=0:y=0:w=iw:h=ih:color=black@{background.darken}:t=fill")
    elif background.type == "gradient":
        inputs += ["-f", "lavfi", "-i", gradient_source(background, config.duration)]
    else:
        color = background.color.lstrip("#")
        inputs += ["-f", "lavfi", "-i", f"color=c=0x{color}:s={WIDTH}x{HEIGHT}:r={FPS}:d={config.duration}"]

    logo_input: list[str] = []
    if config.logo.file:
        logo = TEMPLATES_DIR / config.logo.file
        if not logo.is_file():
            raise RuntimeError(f"Het logobestand templates/{config.logo.file} bestaat niet.")
        logo_input = ["-i", str(logo)]

    filters = [f"[0:v]{','.join(chain)}[bg]" if chain else "[0:v]null[bg]"]
    if logo_input:
        filters.append(f"[2:v]scale={config.logo.width}:-1[logo]")
        filters.append(f"[bg][logo]overlay=x=(W-w)/2:y={config.logo.y}-h/2[withlogo]")
        last = "withlogo"
    else:
        last = "bg"
    filters.append(f"[{last}]ass=filename='{filter_path(ass_path)}':fontsdir='{filter_path(FONTS_DIR)}',"
                   f"format=yuv420p[v]")

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
    """Rebuild outro.mp4 when the config changed. Never overwrites a newer hand-made video."""
    with _lock:
        save_default_config()
        config = load_config()
        if not config.generate:
            return
        newest_config = max((p.stat().st_mtime for p in (CONFIG_PATH, CHURCH_PATH) if p.is_file()), default=0.0)
        if OUTRO_PATH.is_file() and OUTRO_PATH.stat().st_mtime >= newest_config:
            return
        build(config)
