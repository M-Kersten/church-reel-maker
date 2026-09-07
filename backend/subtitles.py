"""Convert transcript segments into an ASS subtitle file.

The layout rules here (safe margins, two-line wrapping, font shrinking) are
mirrored in frontend/src/subtitleLayout.ts so the preview matches the render.
"""

from pathlib import Path

from . import fonts
from .models import Output, Segment, Style, Transcript

SAFE_MARGIN_BOTTOM = 320  # px from the bottom edge at 1080x1920 (clear of the Reels UI)
SAFE_MARGIN_SIDE = 90  # px from the left/right edges
CHAR_WIDTH_RATIO = 0.58  # average glyph width relative to font size (bold sans-serif)
MIN_FONT_SCALE = 0.6  # never shrink a line below this fraction of the chosen size
BACKGROUND_ALPHA = 0x80  # 50% translucent box

# Font family names as libass finds them in templates/fonts (and system fonts for Arial).
# Non-bold/regular weights ship as their own family name ("Montserrat SemiBold").
WEIGHT_SUFFIX = {"regular": "", "medium": " Medium", "semibold": " SemiBold", "bold": "", "extrabold": " ExtraBold"}


def family_for(font: str, weight: str) -> tuple[str, bool]:
    """Return (ASS Fontname, bold flag) for a font family and weight.

    Families that do not have the asked-for weight fall back to their nearest one,
    so a single-weight display font like Bebas Neue still renders.
    """
    if font == fonts.SYSTEM_FONT:
        return fonts.SYSTEM_FONT, weight in ("semibold", "bold", "extrabold")
    weight = fonts.resolve_weight(font, weight)
    return font + WEIGHT_SUFFIX.get(weight, ""), weight == "bold"


def font_name(style: Style) -> tuple[str, bool]:
    """Return (ASS Fontname, bold flag) for a subtitle style."""
    return family_for(style.font, style.fontWeight)


def layout_text(text: str, style: Style, output: Output) -> tuple[list[str], int]:
    """Wrap text to at most two lines; shrink the font if two lines are not enough.

    Returns (lines, font_size).
    """
    text = " ".join(text.split())
    available = output.width - 2 * SAFE_MARGIN_SIDE
    max_chars = max(8, int(available / (style.fontSize * CHAR_WIDTH_RATIO)))
    if len(text) <= max_chars:
        return [text], style.fontSize

    words = text.split(" ")
    if len(words) == 1:
        return [text], style.fontSize
    best: tuple[int, str, str] | None = None
    for i in range(1, len(words)):
        first, second = " ".join(words[:i]), " ".join(words[i:])
        longest = max(len(first), len(second))
        if best is None or longest < best[0]:
            best = (longest, first, second)
    longest, first, second = best
    if longest <= max_chars:
        return [first, second], style.fontSize
    scale = max(MIN_FONT_SCALE, max_chars / longest)
    return [first, second], int(round(style.fontSize * scale))


def ass_color(hex_color: str, alpha: int = 0) -> str:
    """'#RRGGBB' -> '&HAABBGGRR'."""
    hex_color = hex_color.lstrip("#")
    if len(hex_color) != 6:
        hex_color = "FFFFFF"
    r, g, b = hex_color[0:2], hex_color[2:4], hex_color[4:6]
    return f"&H{alpha:02X}{b}{g}{r}".upper()


def ass_time(seconds: float) -> str:
    seconds = max(0.0, seconds)
    h = int(seconds // 3600)
    m = int(seconds % 3600 // 60)
    s = seconds % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def escape_text(text: str) -> str:
    return text.replace("{", "(").replace("}", ")").replace("\n", " ")


def build_ass(transcript: Transcript, style: Style, output: Output) -> str:
    name, bold = font_name(style)
    border_style = 4 if style.background else 1  # 4 = libass: box behind each line, outline kept
    lines = [
        "[Script Info]",
        "ScriptType: v4.00+",
        f"PlayResX: {output.width}",
        f"PlayResY: {output.height}",
        "WrapStyle: 0",
        "ScaledBorderAndShadow: yes",
        "YCbCr Matrix: TV.709",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
        "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding",
        f"Style: Default,{name},{style.fontSize},{ass_color(style.color)},{ass_color(style.color)},"
        f"{ass_color(style.outlineColor)},{ass_color('#000000', BACKGROUND_ALPHA)},"
        f"{-1 if bold else 0},0,0,0,100,100,0,0,{border_style},{style.outline},0,2,"
        f"{SAFE_MARGIN_SIDE},{SAFE_MARGIN_SIDE},{SAFE_MARGIN_BOTTOM},1",
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    for seg in sorted(transcript.segments, key=lambda s: s.start):
        if not seg.text.strip() or seg.end <= seg.start:
            continue
        wrapped, size = layout_text(seg.text, style, output)
        text = "\\N".join(escape_text(line) for line in wrapped)
        if size != style.fontSize:
            text = f"{{\\fs{size}}}" + text
        lines.append(f"Dialogue: 0,{ass_time(seg.start)},{ass_time(seg.end)},Default,,0,0,0,,{text}")
    return "\n".join(lines) + "\n"


def write_ass(transcript: Transcript, style: Style, output: Output, path: Path) -> Path:
    path.write_text(build_ass(transcript, style, output), encoding="utf-8")
    return path
