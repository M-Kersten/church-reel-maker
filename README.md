# Church Reel Maker

Turns a short Dutch church-service clip into a finished vertical video (1080×1920, H.264 + AAC, 30 fps) for Instagram Reels and YouTube Shorts. Everything runs locally.

```text
Upload video → Transcribe Dutch speech → Edit subtitles → Choose subtitle style
→ Preview 9:16 crop → Add church outro → Render final MP4
```

Part 1 uses a **static** centre crop. Person tracking and animated camera movement are reserved for Part 2 (see "Part 2 hooks" below).

## Requirements

- Python 3.11+
- Node.js 20+
- FFmpeg with libass, libx264 and AAC (`ffmpeg` and `ffprobe` on `PATH`)
  - macOS: `brew install ffmpeg`
  - Ubuntu/Debian: `sudo apt install ffmpeg`
  - Windows: a full build from https://www.gyan.dev/ffmpeg/builds/ (added to `PATH`)

The first transcription downloads the faster-whisper model (default `small`, roughly 460 MB) into the Hugging Face cache. After that no network access is needed.

## Setup

```bash
# backend
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r backend/requirements.txt

# frontend
cd frontend && npm install && cd ..
```

## Run

Development, two processes:

```bash
uvicorn backend.main:app --reload --port 8000     # from the repository root
cd frontend && npm run dev                        # http://localhost:5173
```

Single process, after building the frontend:

```bash
cd frontend && npm run build && cd ..
uvicorn backend.main:app --port 8000              # http://localhost:8000
```

Environment variables for transcription:

| Variable | Default | Notes |
| --- | --- | --- |
| `WHISPER_MODEL` | `small` | `tiny`, `base`, `small`, `medium`, `large-v3`. `small` is a good CPU trade-off; `medium` is noticeably better for Dutch if you can wait. |
| `WHISPER_DEVICE` | `cpu` | `cuda` when a GPU with CUDA is available. |
| `WHISPER_COMPUTE_TYPE` | `int8` on CPU, `float16` on GPU | |

## Using the app

1. Drop a clip on the page. The original is stored under `projects/<id>/` and its metadata (size, duration, frame rate, audio) is read with ffprobe. The 9:16 preview appears right away.
2. Click **Transcribe**. Audio is extracted with FFmpeg and transcribed with faster-whisper, language forced to `nl`. Words are grouped into short caption-sized segments.
3. Correct the subtitles. Each segment has editable start/end times (`mm:ss.s`) and text, plus **Split**, **Merge ↓** and delete. Click ▶ on a segment to jump the preview there. Edits are saved automatically.
4. Pick a style: font (Inter, Montserrat, Poppins, Arial), weight, size, text colour, outline size and colour, optional dark translucent background. Subtitles always sit bottom-centre, above the safe margin that Reels and Shorts overlay with UI. Text wraps to at most two lines; longer segments are scaled down to fit.
5. Click **Render video**. Rendering runs as a background job with a progress bar; when it finishes a download link for `final.mp4` appears.

The preview is an HTML `<video>` with `object-fit` mimicking the static crop and an HTML overlay for subtitles; it uses the same fonts and layout rules as the renderer. When the clip ends, the outro plays in the preview as well. Nothing is rendered until you click **Render video**.

## Church outro

`templates/outro.mp4` is appended after every clip. It is a static video template, normalised to 1080×1920 during rendering, so any 9:16 (or other) clip works: replace the file to use your own outro.

The bundled outro is generated from `templates/church.json` with FFmpeg (no AI):

```json
{
  "churchName": "Example Church",
  "serviceTimes": ["09:30", "11:30"],
  "instagram": "@examplechurch"
}
```

Edit that file and run `python templates/make_outro.py` to regenerate `outro.mp4`.

## Fonts

`templates/fonts/` contains Inter, Montserrat and Poppins (SIL Open Font License, licence texts included) in the weights the app offers. The renderer passes this directory to libass and the frontend loads the same files, so the preview matches the output. Arial comes from the operating system (libass falls back to a similar sans-serif when it is missing, for example on Linux without `ttf-mscorefonts-installer`).

## API

```text
POST /projects                      create an empty project
POST /projects/{id}/upload          multipart upload (field "file"); probes the video
POST /projects/{id}/transcribe      Dutch transcription, returns the segments
GET  /projects/{id}                 project + transcript
PUT  /projects/{id}/transcript      save edited segments
PUT  /projects/{id}/style           save subtitle style
POST /projects/{id}/render          start the background render job
GET  /projects/{id}/render-status   {status, progress, message, error}
GET  /projects/{id}/output          the rendered final.mp4
GET  /projects/{id}/source          the uploaded clip (for the preview)
GET  /church                        contents of templates/church.json
GET  /templates/...                 fonts and outro.mp4 (for the preview)
```

Rendering uses an in-process job manager (`backend/jobs.py`), one thread per render. There is no Redis or Celery.

## Project layout

```text
backend/
  main.py           FastAPI routes
  models.py         Pydantic models + project storage (projects/<id>/project.json)
  transcription.py  FFmpeg audio extraction + faster-whisper (nl)
  subtitles.py      transcript → ASS (fonts, outline, box, margins, two-line wrapping)
  renderer.py       ffprobe metadata, crop strategies, FFmpeg render with progress
  jobs.py           in-process background jobs
frontend/src/
  App.tsx                      page state, API calls, auto-save, render polling
  api.ts                       typed API client
  subtitleLayout.ts            layout constants shared with subtitles.py
  components/VideoPreview.tsx  9:16 preview with subtitle overlay and outro
  components/SubtitleEditor.tsx
  components/StylePanel.tsx
  components/RenderControls.tsx
  components/ProgressIndicator.tsx
templates/
  outro.mp4, church.json, make_outro.py, fonts/
projects/           one directory per project (ignored by git)
```

A project directory keeps the source clip untouched next to derived data:

```text
projects/project-3d25a7a1/
  project.json      metadata, style, output settings, crop strategy
  source.mp4        original upload
  transcript.json   {"segments": [{"start", "end", "text"}, ...]}
  work/             audio.wav, subtitles.ass
  output/final.mp4
```

## Render pipeline

```text
source.mp4 → static 9:16 crop → fps 30 → burn subtitles.ass (libass) → concat outro → libx264 crf 20 + AAC 160k → final.mp4
```

Landscape and square sources are scaled to 1920 px high and centre-cropped to 1080 px wide. Portrait sources are scaled to fit inside 1080×1920 and padded, so nothing is cropped away. The outro is normalised the same way. Output is `yuv420p`, High profile, `+faststart`, which uploads directly to Instagram and YouTube.

## Part 2 hooks

- `renderer.build_crop_filter(info, output, crop_strategy, tracking)` is the only place that decides how the source frame becomes 9:16. `crop_strategy="static"` is implemented; `"tracked"` raises `NotImplementedError` and is where a tracking-driven crop path goes.
- `render_video(..., crop_strategy=project.cropStrategy, tracking=project.tracking)` already passes the strategy and tracking data through from the project.
- `Project.cropStrategy` and `Project.tracking` exist in the project model, so tracking results can be stored per project without changing the API shape.
