"""FFmpeg rendering: 9:16 crop -> burned-in subtitles -> outro -> H.264/AAC MP4.

The crop is a pluggable "strategy". Part 1 only implements "static"; Part 2 can
add a "tracked" strategy that turns tracking data into an animated crop path
without touching the rest of the pipeline.
"""

import json
import subprocess
from fractions import Fraction
from pathlib import Path
from typing import Callable

from .models import FONTS_DIR, Output, VideoInfo

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


def build_crop_filter(info: VideoInfo, output: Output, crop_strategy: str = "static", tracking=None) -> str:
    """Return the FFmpeg filter chain that turns the source frame into output.width x output.height."""
    if crop_strategy == "static":
        return static_crop_filter(info, output)
    if crop_strategy == "tracked":
        raise NotImplementedError("tracked crop arrives in Part 2")
    raise ValueError(f"unknown crop strategy: {crop_strategy}")


def static_crop_filter(info: VideoInfo, output: Output) -> str:
    w, h = output.width, output.height
    if info.height > info.width:
        # Portrait: keep the whole frame, scale to fit and pad the remainder.
        return (f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
                f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=black")
    # Landscape or square: scale to the output height, then crop the centre.
    return f"scale=-2:{h},crop={w}:{h}"


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
) -> tuple[list[str], float]:
    """Build the ffmpeg command line. Returns (argv, total output duration)."""
    w, h, fps = output.width, output.height, output.fps
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-nostats", "-progress", "pipe:1"]
    inputs = [source]
    filters: list[str] = []
    audio_norm = "aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo"

    crop = build_crop_filter(source_info, output, crop_strategy, tracking)
    filters.append(
        f"[0:v]{crop},fps={fps},setsar=1,format=yuv420p,"
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
    on_progress: ProgressCallback | None = None,
) -> Path:
    outro_info = probe(outro) if outro is not None and outro.is_file() else None
    if outro_info is None:
        outro = None
    cmd, total = build_command(
        source, source_info, subtitles, outro, outro_info, output, destination, crop_strategy, tracking
    )
    tmp = destination.with_suffix(".part.mp4")
    cmd[-1] = str(tmp)

    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    assert proc.stdout is not None
    for line in proc.stdout:
        key, _, value = line.strip().partition("=")
        if key in ("out_time_us", "out_time_ms") and value.lstrip("-").isdigit() and on_progress:
            done = int(value) / 1_000_000
            on_progress(min(0.99, done / total) if total else 0.0, f"Encoding {done:.0f}s / {total:.0f}s")
    stderr = proc.stderr.read() if proc.stderr else ""
    if proc.wait() != 0:
        tmp.unlink(missing_ok=True)
        raise RuntimeError("ffmpeg failed: " + stderr.strip()[-2000:])
    tmp.replace(destination)
    return destination
