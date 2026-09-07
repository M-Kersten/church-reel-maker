"""Generate templates/outro.mp4 from templates/church.json with FFmpeg.

Run from the repository root:  python templates/make_outro.py
Replace outro.mp4 with your own clip any time; the renderer normalises it to 1080x1920.
"""

import json
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
TOOLS = HERE.parent / "tools" / "ffmpeg"
DURATION = 5
BG = "0x1b2432"


def find_ffmpeg() -> str:
    """ffmpeg from PATH, or the copy the launcher downloaded into tools/ffmpeg."""
    for candidate in (shutil.which("ffmpeg"), TOOLS / "ffmpeg.exe", TOOLS / "ffmpeg"):
        if candidate and Path(candidate).is_file():
            return str(candidate)
    sys.exit("FFmpeg is niet gevonden. Start de app eerst één keer met start.bat of start.command "
             "(die haalt FFmpeg op), of installeer FFmpeg en zet het in PATH.")


def filter_path(path: Path) -> str:
    """Escape a path for use inside an FFmpeg filter option (drive-letter colons, backslashes)."""
    return path.as_posix().replace(":", "\\:").replace("'", "\\'")

church = json.loads((HERE / "church.json").read_text(encoding="utf-8"))
times = "  ·  ".join(church["serviceTimes"])
ass = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Title,Montserrat,88,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,0,0,5,80,80,0,1
Style: Sub,Montserrat SemiBold,48,&H00D8E0EA,&H00FFFFFF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,0,0,5,80,80,0,1
Style: Handle,Montserrat,52,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,0,0,5,80,80,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:00:00.00,0:00:{DURATION:02d}.00,Title,,0,0,0,,{{\\fad(400,400)\\pos(540,820)}}{church["churchName"]}
Dialogue: 0,0:00:00.30,0:00:{DURATION:02d}.00,Sub,,0,0,0,,{{\\fad(400,400)\\pos(540,960)}}Welkom, elke zondag
Dialogue: 0,0:00:00.30,0:00:{DURATION:02d}.00,Sub,,0,0,0,,{{\\fad(400,400)\\pos(540,1030)}}{times}
Dialogue: 0,0:00:00.60,0:00:{DURATION:02d}.00,Handle,,0,0,0,,{{\\fad(400,400)\\pos(540,1200)}}{church["instagram"]}
"""
ass_path = HERE / "outro.ass"
ass_path.write_text(ass, encoding="utf-8")
subprocess.run([
    find_ffmpeg(), "-y", "-hide_banner", "-loglevel", "error",
    "-f", "lavfi", "-i", f"color=c={BG}:s=1080x1920:r=30:d={DURATION}",
    "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
    "-vf", f"ass=filename='{filter_path(ass_path)}':fontsdir='{filter_path(HERE / 'fonts')}',format=yuv420p",
    "-t", str(DURATION), "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-c:a", "aac", "-b:a", "96k",
    "-movflags", "+faststart", str(HERE / "outro.mp4"),
], check=True)
ass_path.unlink()
print("wrote", HERE / "outro.mp4")
