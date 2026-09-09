"""FFmpeg rendering: 9:16 crop -> burned-in subtitles -> outro -> H.264/AAC MP4.

The crop is a pluggable "strategy". Part 1 only implements "static"; Part 2 can
add a "tracked" strategy that turns tracking data into an animated crop path
without touching the rest of the pipeline.
"""

import json
import math
import subprocess
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Callable

from .models import FONTS_DIR, TEMPLATES_DIR, CropWindow, MusicSettings, Output, Track, VideoInfo, Watermark

ProgressCallback = Callable[[float, str], None]


def ffmpeg_message(stderr: str) -> str:
    """Turn FFmpeg output into something a user can act on."""
    text = stderr.strip()
    lowered = text.lower()
    if "no space left" in lowered:
        return "Er is geen ruimte meer op de schijf. Maak ruimte vrij en probeer het opnieuw."
    if "permission denied" in lowered:
        return "De app mag niet naar deze map schrijven. Controleer de rechten van de projectmap."
    if "invalid data found" in lowered or "moov atom not found" in lowered:
        return "Het videobestand lijkt beschadigd of onvolledig. Probeer het opnieuw te exporteren of te uploaden."
    return "Het maken van de video is mislukt: " + text[-600:]


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


def build_crop_filter(info: VideoInfo, output: Output, crop_strategy: str = "static",
                      track: Track | None = None, crop: CropWindow | None = None,
                      commands: Path | None = None) -> str:
    """Return the FFmpeg filter chain that turns the source frame into output.width x output.height.

    A track without a path, or one asked for without somewhere to write its commands, falls
    back to the static window rather than failing: a clip must always be renderable.
    """
    if crop_strategy == "tracked" and track and track.x and commands is not None:
        return tracked_crop_filter(info, output, crop, track, commands)
    if crop_strategy in {"static", "tracked"}:
        return static_crop_filter(info, output, crop)
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


def half_up(value: float) -> int:
    """Round .5 upwards, the way JavaScript's Math.round does.

    Python's round() sends .5 to the nearest even number, so the two languages disagree
    by a pixel on exact halves. The preview and the render have to land on the same one.
    """
    return math.floor(value + 0.5)


def crop_geometry(info: VideoInfo, output: Output, crop: CropWindow | None) -> CropGeometry:
    """Pixel geometry for a crop window (mirrored in frontend/src/crop.ts)."""
    crop = crop or default_crop(info, output)
    zoom = max(min_zoom(info, output), min(4.0, crop.zoom))
    scale = cover_scale(info, output) * zoom
    scaled_w = max(2, half_up(info.width * scale / 2) * 2)
    scaled_h = max(2, half_up(info.height * scale / 2) * 2)
    crop_w = min(scaled_w, output.width)
    crop_h = min(scaled_h, output.height)
    return CropGeometry(scaled_w, scaled_h, crop_w, crop_h,
                        edge_for(crop.x, scaled_w, crop_w), edge_for(crop.y, scaled_h, crop_h))


def edge_for(centre: float, scaled: int, window: int) -> int:
    """Where a window of `window` pixels starts when it is centred on `centre`, kept inside."""
    return half_up(min(max(centre * scaled - window / 2, 0), scaled - window))


def static_crop_filter(info: VideoInfo, output: Output, crop: CropWindow | None = None) -> str:
    g = crop_geometry(info, output, crop)
    return (f"scale={g.scaled_w}:{g.scaled_h},crop={g.crop_w}:{g.crop_h}:{g.left}:{g.top},"
            f"pad={output.width}:{output.height}:(ow-iw)/2:(oh-ih)/2:color=black")


COMMAND_FPS = 50.0  # how finely the path is handed to FFmpeg, whatever rate it was stored at


def track_at(track: Track, seconds: float) -> float | None:
    """Where the frame sits at `seconds`. Mirrored in frontend/src/track.ts.

    The path is evenly spaced from the start of the clip, so the sample is found by dividing
    rather than searching, and the two nearest are mixed. Before the first and after the last
    it holds still.
    """
    if not track.x:
        return None
    place = max(0.0, seconds) * track.fps
    first = int(math.floor(place))
    if first >= len(track.x) - 1:
        return track.x[-1]
    if first + 1 in set(track.jumps):
        return track.x[first]  # the frame jumped here; sliding into it would undo the cut
    return track.x[first] + (track.x[first + 1] - track.x[first]) * (place - first)


def track_commands(info: VideoInfo, output: Output, crop: CropWindow | None, track: Track) -> str:
    """The script that walks the crop window along the path, one line per move.

    Read finer than it was stored: sendcmd sets a value and leaves it there, so a path
    handed over at its own twelve-and-a-half samples a second would step visibly on a fast
    pan. Fifty a second is below what a pixel of movement can show. A line is only written
    when the window would actually land on a different pixel, so a speaker standing still
    still costs a handful of lines rather than one per frame.
    """
    g = crop_geometry(info, output, crop)
    span = (len(track.x) - 1) / max(1e-6, track.fps)
    lines, before = [], None
    for step in range(int(span * COMMAND_FPS) + 1):
        moment = step / COMMAND_FPS
        x = track_at(track, moment)
        if x is None:
            break
        edge = edge_for(x, g.scaled_w, g.crop_w)
        if edge == before:
            continue
        lines.append(f"{moment:.4f} crop@track x {edge};")
        before = edge
    return "\n".join(lines) + "\n"


def tracked_crop_filter(info: VideoInfo, output: Output, crop: CropWindow | None,
                        track: Track, commands: Path) -> str:
    """The same window as a static crop, told where to be as the clip plays.

    sendcmd hands the crop a new x at each moment the path calls for one. Everything about
    how that path was arrived at (dead zone, easing, cuts) lives in tracking.py; by the time
    it gets here it is a list of positions and nothing else.
    """
    g = crop_geometry(info, output, crop)
    commands.parent.mkdir(parents=True, exist_ok=True)
    commands.write_text(track_commands(info, output, crop, track), encoding="utf-8")
    start = edge_for(track.x[0], g.scaled_w, g.crop_w) if track.x else g.left
    return (f"scale={g.scaled_w}:{g.scaled_h},sendcmd=f='{_ffpath(commands)}',"
            f"crop@track={g.crop_w}:{g.crop_h}:{start}:{g.top},"
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
    track: Track | None = None,
    crop: CropWindow | None = None,
    music: MusicSettings | None = None,
    watermark: Watermark | None = None,
    source_start: float | None = None,
) -> tuple[list[str], float]:
    """Build the ffmpeg command line. Returns (argv, total output duration).

    `source_start` set means the clip is a range of a longer recording: seek there and take
    source_info.duration seconds, instead of reading a separately cut copy. Input-side -ss
    rebases the timestamps to zero, so the subtitles still line up with the clip.
    """
    w, h, fps = output.width, output.height, output.fps
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-nostats", "-progress", "pipe:1"]
    inputs = [source]
    # Per-input options, by input index. Only the clip itself is ever trimmed.
    trim = {0: ["-ss", f"{source_start:.3f}", "-t", f"{source_info.duration:.3f}"]} if source_start is not None else {}
    filters: list[str] = []
    # Speech is levelled to what social platforms expect, so clips from different services
    # sound equally loud next to each other.
    audio_norm = "loudnorm=I=-14:TP=-1.5:LRA=11,aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo"
    music_path = music_file(music)
    speech = "aall" if music_path else "a"
    logo_path = watermark_file(watermark)

    if logo_path is not None:
        inputs.append(logo_path)  # a still image; overlay repeats its single frame

    crop_chain = build_crop_filter(source_info, output, crop_strategy, track, crop,
                                   commands=subtitles.with_name('track.cmd'))
    clip_label = "v0raw" if logo_path is not None else "v0"
    filters.append(
        f"[0:v]{crop_chain},fps={fps},setsar=1,format=yuv420p,"
        f"ass=filename='{_ffpath(subtitles)}':fontsdir='{_ffpath(FONTS_DIR)}'[{clip_label}]"
    )
    if logo_path is not None and watermark is not None:
        filters.append(
            f"[1:v]format=rgba,colorchannelmixer=aa={watermark.opacity:.2f},"
            f"scale={max(16, int(w * watermark.width))}:-1[wm]"
        )
        filters.append(f"[{clip_label}][wm]overlay={overlay_position(watermark)}:format=auto[v0]")
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
        filters.append(f"[v0][a0][v1][a1]concat=n=2:v=1:a=1[v][{speech}]")
        total += outro_info.duration
    else:
        filters.append("[v0]null[v]")
        filters.append(f"[a0]anull[{speech}]")

    if music_path is not None and music is not None:
        index = len(inputs)  # the music is the last input
        filters.append(music_filter(music, total, index))
        if music.duck:
            # The speech is needed twice: once to mix, once to tell the music when to step back.
            filters.append(f"[{speech}]asplit=2[sp_mix][sp_key]")
            filters.append("[mus][sp_key]sidechaincompress=threshold=0.045:ratio=6:attack=15:release=350[bed]")
            speech_mix = "sp_mix"
        else:
            filters.append("[mus]anull[bed]")
            speech_mix = speech
        filters.append(f"[{speech_mix}][bed]amix=inputs=2:normalize=0:duration=first,alimiter=limit=0.95[a]")

    for index, path in enumerate(inputs):
        cmd += trim.get(index, []) + ["-i", str(path)]
    if music_path is not None:
        cmd += ["-stream_loop", "-1", "-i", str(music_path)]
    cmd += ["-filter_complex", ";".join(filters), "-map", "[v]", "-map", "[a]"]
    cmd += [
        "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-profile:v", "high", "-level", "4.1",
        "-pix_fmt", "yuv420p", "-r", str(fps), "-g", str(fps * 2),
        "-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-ac", "2",
        "-movflags", "+faststart", str(destination),
    ]
    return cmd, total


def watermark_file(watermark: Watermark | None) -> Path | None:
    """The logo to put in the corner, when one is chosen and still on disk."""
    if watermark is None or not watermark.file:
        return None
    path = TEMPLATES_DIR / "logos" / watermark.file
    return path if path.is_file() else None


def overlay_position(watermark: Watermark) -> str:
    """Where the logo sits, expressed the way the overlay filter wants it."""
    m = watermark.margin
    return {
        "topLeft": f"{m}:{m}",
        "topRight": f"main_w-overlay_w-{m}:{m}",
        "bottomLeft": f"{m}:main_h-overlay_h-{m}",
        "bottomRight": f"main_w-overlay_w-{m}:main_h-overlay_h-{m}",
    }[watermark.corner]


def music_file(music: MusicSettings | None) -> Path | None:
    """The music file to mix in, when one is chosen and still on disk."""
    if music is None or not music.file:
        return None
    path = TEMPLATES_DIR / "music" / music.file
    return path if path.is_file() else None


def music_filter(music: MusicSettings, total: float, index: int) -> str:
    """Cut the (looping) music to length, fade it in and out, and set its level."""
    fade_out = min(music.fadeOut, max(0.5, total / 3))
    start_out = max(0.0, total - fade_out)
    return (f"[{index}:a]atrim=0:{total:.3f},asetpts=N/SR/TB,volume={music.volume:.3f},"
            f"afade=t=in:st=0:d=1.2,afade=t=out:st={start_out:.3f}:d={fade_out:.3f},"
            f"aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo[mus]")


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
    track: Track | None = None,
    crop: CropWindow | None = None,
    music: MusicSettings | None = None,
    watermark: Watermark | None = None,
    source_start: float | None = None,
    on_progress: ProgressCallback | None = None,
    should_stop: Callable[[], None] | None = None,
) -> Path:
    outro_info = probe(outro) if outro is not None and outro.is_file() else None
    if outro_info is None:
        outro = None
    cmd, total = build_command(
        source, source_info, subtitles, outro, outro_info, output, destination, crop_strategy, track, crop, music,
        watermark, source_start
    )
    tmp = destination.with_suffix(".part.mp4")
    cmd[-1] = str(tmp)

    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    except FileNotFoundError as exc:
        raise RuntimeError("FFmpeg is niet gevonden. Sluit de app en start opnieuw met start.bat of start.command.") from exc
    assert proc.stdout is not None
    for line in proc.stdout:
        if should_stop:
            try:
                should_stop()
            except BaseException:
                proc.terminate()
                proc.wait(timeout=10)
                tmp.unlink(missing_ok=True)
                raise
        key, _, value = line.strip().partition("=")
        if key in ("out_time_us", "out_time_ms") and value.lstrip("-").isdigit() and on_progress:
            done = int(value) / 1_000_000
            on_progress(min(0.99, done / total) if total else 0.0, f"Video wordt gemaakt · {done:.0f} van {total:.0f} seconden")
    stderr = proc.stderr.read() if proc.stderr else ""
    if proc.wait() != 0:
        tmp.unlink(missing_ok=True)
        raise RuntimeError(ffmpeg_message(stderr))
    tmp.replace(destination)
    return destination
