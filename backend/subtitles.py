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
MAX_LINES = 3  # a bigger font spreads over more lines before it is shrunk
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


def wrap_words(words: list[str], width: int) -> list[str]:
    """Greedy fill: put as many words on a line as fit within `width` characters."""
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if current and len(candidate) > width:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines


def fit_lines(words: list[str], count: int, max_chars: int) -> list[str] | None:
    """Split the words over at most `count` lines, none wider than max_chars.

    Starts from evenly divided lines and widens until the greedy fill needs no
    extra line, so the lines come out roughly equal instead of one long, one short.
    """
    total = len(" ".join(words))
    start = max(max(len(w) for w in words), -(-total // count))
    for width in range(start, max_chars + 1):
        lines = wrap_words(words, width)
        if len(lines) <= count:
            return lines
    return None


def layout_text(text: str, style: Style, output: Output) -> tuple[list[str], int]:
    """Wrap text over as few lines as it needs; shrink the font only as a last resort.

    Returns (lines, font_size). A large font takes more lines, up to MAX_LINES, so
    the text really does get bigger on screen instead of being scaled straight back.
    """
    text = " ".join(text.split())
    available = output.width - 2 * SAFE_MARGIN_SIDE
    max_chars = max(8, int(available / (style.fontSize * CHAR_WIDTH_RATIO)))
    if len(text) <= max_chars:
        return [text], style.fontSize

    words = text.split(" ")
    if len(words) == 1:
        return [text], style.fontSize

    for count in range(2, MAX_LINES + 1):
        lines = fit_lines(words, count, max_chars)
        if lines is not None:
            return lines, style.fontSize

    # Still too wide: use MAX_LINES lines at the largest size those lines fit at.
    # Sizing from the lines rather than from a fraction of the asked-for size keeps this
    # monotonic, so turning the size up never renders the text smaller than before.
    lines = fit_lines(words, MAX_LINES, len(text)) or [text]
    longest = max(len(line) for line in lines)
    fitted = int(available / (longest * CHAR_WIDTH_RATIO))
    return lines, max(int(style.fontSize * MIN_FONT_SCALE), min(style.fontSize, fitted))


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


def animation_tags(style: Style, output: Output) -> str:
    """The ASS tags that make a line appear, in the style the user picked."""
    ms = style.animationSpeed
    if style.animation == "fade":
        return f"\\fad({ms},{min(ms, 200)})"
    if style.animation == "pop":
        # Start slightly small and settle: reads as a snap without moving the line.
        return f"\\fad(60,80)\\fscx72\\fscy72\\t(0,{ms},\\fscx100\\fscy100)"
    if style.animation == "slide":
        # Alignment 2 anchors the bottom centre of the block; slide it up into that spot.
        anchor_y = output.height - SAFE_MARGIN_BOTTOM
        return f"\\fad(60,80)\\move({output.width // 2},{anchor_y + 40},{output.width // 2},{anchor_y},0,{ms})"
    return ""


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
    tags = animation_tags(style, output)
    for seg in sorted(transcript.segments, key=lambda s: s.start):
        if not seg.text.strip() or seg.end <= seg.start:
            continue
        wrapped, size = layout_text(seg.text, style, output)
        text = "\\N".join(escape_text(line) for line in wrapped)
        prefix = tags + (f"\\fs{size}" if size != style.fontSize else "")
        if prefix:
            text = "{" + prefix + "}" + text
        lines.append(f"Dialogue: 0,{ass_time(seg.start)},{ass_time(seg.end)},Default,,0,0,0,,{text}")
    return "\n".join(lines) + "\n"


def write_ass(transcript: Transcript, style: Style, output: Output, path: Path) -> Path:
    path.write_text(build_ass(transcript, style, output), encoding="utf-8")
    return path
