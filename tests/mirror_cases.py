"""Write the shared cases and the Python results to JSON, for the TypeScript side to diff."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.models import CropWindow, Output, Style, VideoInfo  # noqa: E402
from backend.models import Track  # noqa: E402
from backend.renderer import crop_geometry, track_at  # noqa: E402
from backend.subtitles import layout_text  # noqa: E402
from tests.cases import (CROP_SOURCES, CROP_WINDOWS, LAYOUT_SIZES, LAYOUT_TEXTS, OUTPUT,  # noqa: E402
                         TRACKS, TRACK_TIMES)


def build() -> dict:
    output = Output(width=OUTPUT[0], height=OUTPUT[1], fps=OUTPUT[2])
    layout = []
    for text in LAYOUT_TEXTS:
        for size in LAYOUT_SIZES:
            lines, chosen = layout_text(text, Style(fontSize=size), output)
            layout.append({"text": text, "size": size, "lines": lines, "fontSize": chosen})

    crop = []
    for width, height in CROP_SOURCES:
        info = VideoInfo(width=width, height=height, duration=30.0, fps=30.0, videoCodec="h264",
                         hasAudio=True, audioCodec="aac", audioSampleRate=48000, audioChannels=2)
        for x, y, zoom in CROP_WINDOWS:
            g = crop_geometry(info, output, CropWindow(x=x, y=y, zoom=zoom))
            crop.append({"source": [width, height], "window": [x, y, zoom],
                         "scaledW": g.scaled_w, "scaledH": g.scaled_h,
                         "cropW": g.crop_w, "cropH": g.crop_h, "left": g.left, "top": g.top})
    track = []
    for fps, xs, jumps in TRACKS:
        path = Track(fps=fps, x=xs, jumps=jumps)
        track.append({"track": {"fps": fps, "x": xs, "jumps": jumps},
                      "at": [{"seconds": t, "x": track_at(path, t)} for t in TRACK_TIMES]})

    return {"output": {"width": output.width, "height": output.height, "fps": output.fps},
            "layout": layout, "crop": crop, "track": track}


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent / "fixtures" / "mirror.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(build(), indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {target}")
