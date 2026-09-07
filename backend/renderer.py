"""FFmpeg rendering: 9:16 crop -> burned-in subtitles -> outro -> H.264/AAC MP4.

The crop is a pluggable "strategy". Part 1 only implements "static"; Part 2 can
add a "tracked" strategy that turns tracking data into an animated crop path
without touching the rest of the pipeline.
"""

import json
import subprocess
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Callable

from .models import FONTS_DIR, CropWindow, Output, VideoInfo

ProgressCallback = Callable[[float, str], None]


def probe(path: Path) -> VideoInfo:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)],
        capture_output=True, text=True, check=True,
    ).stdout
    data = json.loads(out)
    video = next((s for s in data["streams"] if s.get("codec_type") == "video"), None)
    if video is None:
        raise ValueError("file contains no video stream")
    audio = next((s for s in data["streams"] if s.get("codec_type") == "audio"), None)

    fps = float(Fraction(video.get("avg_frame_rate") or video.get("r_frame_rate") or "30")) or 30.0
    duration = float(data.get("format", {}).get("duration") or video.get("duration") or 0.0)
    width, height = int(video["width"]), int(video["height"])
    rotation = _rotation(video)
    if rotation in (90, 270):  # phone footage stored sideways is displayed rotated
        width, height = height, width
    return VideoInfo(
        width=width,
        height=height,
        duration=round(duration, 3),
        fps=round(fps, 3),
        videoCodec=video.get("codec_name"),
        hasAudio=audio is not None,
        audioCodec=audio.get("codec_name") if audio else None,
        audioSampleRate=int(audio["sample_rate"]) if audio and audio.get("sample_rate") else None,
        audioChannels=int(audio["channels"]) if audio and audio.get("channels") else None,
    )


def _rotation(stream: dict) -> int:
    for side in stream.get("side_data_list", []):
        if "rotation" in side:
            return abs(int(side["rotation"])) % 360
    return abs(int(stream.get("tags", {}).get("rotate", 0))) % 360


# --- crop strategies ----------------------------------------------------------


def build_crop_filter(info: VideoInfo, output: Output, crop_strategy: str = "static", tracking=None,
                      crop: CropWindow | None = None) -> str:
    """Return the FFmpeg filter chain that turns the source frame into output.width x output.height."""
    if crop_strategy == "static":
        return static_crop_filter(info, output, crop)
    if crop_strategy == "tracked":
        raise NotImplementedError("tracked crop arrives in Part 2")
    raise ValueError(f"unknown crop strategy: {crop_strategy}")


def cover_scale(info: VideoInfo, output: Output) -> float:
    return max(output.width / info.width, output.height / info.height)


def min_zoom(info: VideoInfo, output: Output) -> float:
    """Zoom at which the whole source fits inside the frame (letterboxed)."""
    return min(output.width / info.width, output.height / info.height) / cover_scale(info, output)


def default_crop(info: VideoInfo, output: Output) -> CropWindow:
    """Landscape: fill the frame and centre. Portrait: keep the whole frame, padded."""
    if info.height > info.width:
        return CropWindow(zoom=round(min_zoom(info, output), 4))
    return CropWindow()


@dataclass
class CropGeometry:
    scaled_w: int  # source size after scaling
    scaled_h: int
    crop_w: int  # part of the scaled source that ends up in the frame
    crop_h: int
    left: int
    top: int


def crop_geometry(info: VideoInfo, output: Output, crop: CropWindow | None) -> CropGeometry:
    """Pixel geometry for a crop window (mirrored in frontend/src/crop.ts)."""
    crop = crop or default_crop(info, output)
    zoom = max(min_zoom(info, output), min(4.0, crop.zoom))
    scale = cover_scale(info, output) * zoom
    scaled_w = max(2, int(round(info.width * scale / 2)) * 2)
    scaled_h = max(2, int(round(info.height * scale / 2)) * 2)
    crop_w = min(scaled_w, output.width)
    crop_h = min(scaled_h, output.height)
    left = int(round(min(max(crop.x * scaled_w - crop_w / 2, 0), scaled_w - crop_w)))
    top = int(round(min(max(crop.y * scaled_h - crop_h / 2, 0), scaled_h - crop_h)))
    return CropGeometry(scaled_w, scaled_h, crop_w, crop_h, left, top)


def static_crop_filter(info: VideoInfo, output: Output, crop: CropWindow | None = None) -> str:
    g = crop_geometry(info, output, crop)
    return (f"scale={g.scaled_w}:{g.scaled_h},crop={g.crop_w}:{g.crop_h}:{g.left}:{g.top},"
            f"pad={output.width}:{output.height}:(ow-iw)/2:(oh-ih)/2:color=black")


# --- rendering ----------------------------------------------------------------


def _ffpath(path: Path) -> str:
    """Escape a path for use inside a filter option value."""
    return str(path).replace("\\", "/").replace(":", "\\:").replace("'", "\\'")


def build_command(
    source: Path,
    source_info: VideoInfo,
    subtitles: Path,
    outro: Path | None,
    outro_info: VideoInfo | None,
    output: Output,
    destination: Path,
    crop_strategy: str = "static",
    tracking=None,
    crop: CropWindow | None = None,
) -> tuple[list[str], float]:
    """Build the ffmpeg command line. Returns (argv, total output duration)."""
    w, h, fps = output.width, output.height, output.fps
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-nostats", "-progress", "pipe:1"]
    inputs = [source]
    filters: list[str] = []
    audio_norm = "aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo"

    crop_chain = build_crop_filter(source_info, output, crop_strategy, tracking, crop)
    filters.append(
        f"[0:v]{crop_chain},fps={fps},setsar=1,format=yuv420p,"
        f"ass=filename='{_ffpath(subtitles)}':fontsdir='{_ffpath(FONTS_DIR)}'[v0]"
    )
    filters.append(_audio_filter(0, source_info, audio_norm, inputs, filters, "a0"))

    total = source_info.duration
    if outro is not None and outro_info is not None:
        inputs.append(outro)
        idx = len(inputs) - 1
        filters.append(
            f"[{idx}:v]scale={w}:{h}:force_original_aspect_ratio=decrease,"
            f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=black,fps={fps},setsar=1,format=yuv420p[v1]"
        )
        filters.append(_audio_filter(idx, outro_info, audio_norm, inputs, filters, "a1"))
        filters.append("[v0][a0][v1][a1]concat=n=2:v=1:a=1[v][a]")
        total += outro_info.duration
    else:
        filters.append("[v0]null[v]")
        filters.append("[a0]anull[a]")

    for path in inputs:
        cmd += ["-i", str(path)]
    cmd += ["-filter_complex", ";".join(filters), "-map", "[v]", "-map", "[a]"]
    cmd += [
        "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-profile:v", "high", "-level", "4.1",
        "-pix_fmt", "yuv420p", "-r", str(fps), "-g", str(fps * 2),
        "-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-ac", "2",
        "-movflags", "+faststart", str(destination),
    ]
    return cmd, total


def _audio_filter(idx: int, info: VideoInfo, norm: str, inputs: list, filters: list, label: str) -> str:
    if info.hasAudio:
        return f"[{idx}:a]{norm}[{label}]"
    # Silent clip: synthesise silence of the same length so concat has an audio stream.
    return f"anullsrc=r=48000:cl=stereo,atrim=duration={info.duration:.3f}[{label}]"


def render_video(
    source: Path,
    source_info: VideoInfo,
    subtitles: Path,
    output: Output,
    destination: Path,
    outro: Path | None = None,
    crop_strategy: str = "static",
    tracking=None,
    crop: CropWindow | None = None,
    on_progress: ProgressCallback | None = None,
) -> Path:
    outro_info = probe(outro) if outro is not None and outro.is_file() else None
    if outro_info is None:
        outro = None
    cmd, total = build_command(
        source, source_info, subtitles, outro, outro_info, output, destination, crop_strategy, tracking, crop
    )
    tmp = destination.with_suffix(".part.mp4")
    cmd[-1] = str(tmp)

    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    assert proc.stdout is not None
    for line in proc.stdout:
        key, _, value = line.strip().partition("=")
        if key in ("out_time_us", "out_time_ms") and value.lstrip("-").isdigit() and on_progress:
            done = int(value) / 1_000_000
            on_progress(min(0.99, done / total) if total else 0.0, f"Video wordt gemaakt · {done:.0f} van {total:.0f} seconden")
    stderr = proc.stderr.read() if proc.stderr else ""
    if proc.wait() != 0:
        tmp.unlink(missing_ok=True)
        raise RuntimeError("FFmpeg is mislukt: " + stderr.strip()[-2000:])
    tmp.replace(destination)
    return destination
