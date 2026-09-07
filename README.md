# Church Reel Maker

Turns a short Dutch church-service clip into a finished vertical video (1080×1920, H.264 + AAC, 30 fps) for Instagram Reels and YouTube Shorts. Everything runs locally.

```text
Upload video → Transcribe Dutch speech → Edit subtitles → Choose subtitle style
→ Preview 9:16 crop → Add church outro → Render final MP4
```

Part 1 uses a **static** centre crop. Person tracking and animated camera movement are reserved for Part 2 (see "Part 2 hooks" below).

There are two entry points on the page:

- **Full service**: upload a complete recording (60–120 minutes), let the AI suggest clip-worthy moments, review and adjust them, and send the ones you pick into the clip editor. See "Full service clip discovery" below.
- **Clip**: the single-clip editor described above.

## Quick start (no technical knowledge needed)

1. Download this project as a folder (green **Code** button → **Download ZIP** on GitHub, then unzip) or clone it.
2. Start it:
   - **Windows**: double-click `start.bat`.
   - **macOS**: double-click `start.command`. If macOS says the file cannot be opened, right-click it, choose **Open**, and confirm once.
3. The first start takes a few minutes: it installs Python packages and downloads FFmpeg into `tools/`. Python itself is installed automatically on Windows (through winget) and through Homebrew on macOS when available; otherwise the window tells you where to get it.
4. The browser opens at http://localhost:8000. Close the black window to stop the app.

Settings live in `config.env` next to `start.bat` (created on first start). Put your Claude API key there for the "Full service" clip suggestions, or set `LLM_PROVIDER=ollama` to keep everything local. The speech model (about 460 MB) is downloaded on the first transcription.

The built web interface is committed in `frontend/dist`, so Node.js is not needed to run the app. Developers who change the frontend run `npm run build` in `frontend/` and commit the result.

## Requirements

- Python 3.11+
- Node.js 20+
- FFmpeg with libass, libx264 and AAC (`ffmpeg` and `ffprobe` on `PATH`)
  - macOS: `brew install ffmpeg`
  - Ubuntu/Debian: `sudo apt install ffmpeg`
  - Windows: a full build from https://www.gyan.dev/ffmpeg/builds/ (added to `PATH`)

The first transcription downloads the faster-whisper model (default `small`, roughly 460 MB) into the Hugging Face cache. After that no network access is needed.

## Developer setup

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

## Full service clip discovery

```text
Upload service → Transcribing → Analyzing service → Suggestions ready → Review & select → Process selected clips → Clip editor
```

1. Open the **Full service** tab and drop the complete recording. Transcription starts automatically (the same faster-whisper setup as for clips, forced to `nl`) and shows progress; with the `small` model a 90-minute service takes about 20 to 40 minutes on a recent laptop CPU (`medium` takes several times longer). The black window may print warnings from the speech library while this runs; the progress bar in the browser is what counts.
2. Analysis starts when the transcript is ready. The transcript is cut into overlapping windows of about three minutes; each window goes to the LLM with per-sentence timecodes and comes back as structured JSON candidates (start, end, title, summary, reason, confidence). Progress shows "Analyzing transcript · Section 8 of 24".
3. Candidate boundaries are snapped to sentence boundaries, proposals that cover the same moment are merged (the extra boundaries stay available as alternatives), and the list is ranked with an internal score (confidence plus a preference for 30–60 seconds).
4. **Clip Suggestions** lists the ranked candidates with title, timecodes, duration, transcript excerpt, summary and reason. **Preview** plays just that range of the original recording; **Transcript & timecodes** opens the full excerpt and the boundary editor with direct `mm:ss.s` input and -5 / -1 / +1 / +5 second nudges. Selections and edits are saved automatically.
5. **Process selected clips** cuts each selected range out of the recording (frame-accurate, original resolution), creates a normal clip project with the matching part of the transcript already filled in, and lists them under "Processed clips". **Open in editor** switches to the Clip tab for subtitles, styling, framing and rendering. Nothing about rendering lives in the discovery layer.

### LLM configuration

| Variable | Default | Notes |
| --- | --- | --- |
| `LLM_PROVIDER` | `anthropic` | `anthropic` uses the Claude API (set `ANTHROPIC_API_KEY`); `ollama` uses a local Ollama server, so the whole pipeline stays on your machine. |
| `LLM_MODEL` | `claude-opus-5` / `llama3.1` | Model per provider. |
| `LLM_EFFORT` | `high` | Claude effort level (`low` … `max`). |
| `LLM_CONCURRENCY` | `3` | Windows analysed in parallel. |
| `OLLAMA_URL` | `http://localhost:11434` | |

Only transcript text is sent to the model, never video or audio. A 90-minute service is about 25 windows of roughly 2,000 tokens each.

### Discovery data

Services live in `services/<id>/` (ignored by git) next to the clip projects:

```text
services/service-954de789/
  service.json      title, status, candidates[], clips[]
  source.mp4        the full recording, never modified
  transcript.json   {"segments": [{"start", "end", "text"}, ...]}
  work/audio.wav
```

A **candidate** means "the AI thinks this range could work"; a **processed clip** means "the user approved it and a clip project was created". Both are kept on the service. Clip projects created this way carry `title` and `origin` (service id, candidate id, start, end) so later parts can trace a reel back to the recording.

The interface between discovery and production is one function, `create_clip(source, start, end)` in `backend/clips.py`, which builds a standard project for the existing pipeline. The candidate model has room for future fields (category, hook, keywords, thumbnail time) without changing the workflow.

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

POST /services                      create an empty service
POST /services/{id}/upload          multipart upload of the full recording
POST /services/{id}/transcribe      background transcription (status: transcribing -> transcribed)
POST /services/{id}/analyze         background LLM analysis (status: analyzing -> ready)
GET  /services/{id}                 service + transcript + running job progress
GET  /services/{id}/candidates      ranked candidates
PUT  /services/{id}/candidates      save selection and boundary edits
POST /services/{id}/process-selected  cut each selected candidate into a clip project (status: processing -> complete)
GET  /services/{id}/source          the recording (for candidate preview)
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
  discovery.py      transcript windows -> LLM analysis -> deduplicated, ranked ClipCandidates
  clips.py          create_clip(source, start, end): cuts a range into a regular clip project
frontend/src/
  App.tsx                      tab switch between Full service and Clip
  api.ts                       typed API client (projects + services)
  subtitleLayout.ts            layout constants shared with subtitles.py
  components/ClipEditor.tsx    single-clip editor: project state, API calls, auto-save, render polling
  components/ServiceView.tsx   full-service upload, states, progress, processed clips
  components/ClipSuggestions.tsx  ranked candidate list: preview, select, adjust boundaries
  components/VideoPreview.tsx  9:16 preview with subtitle overlay and outro
  components/SubtitleEditor.tsx
  components/StylePanel.tsx
  components/RenderControls.tsx
  components/ProgressIndicator.tsx
templates/
  outro.mp4, church.json, make_outro.py, fonts/
launcher.py         loads config.env, fetches FFmpeg when missing, starts the server, opens the browser
start.bat / start.command   one-click launchers for Windows and macOS (create .venv, install, run launcher.py)
config.example.env  template for config.env (API key, LLM provider, whisper model)
projects/           one directory per clip project (ignored by git)
services/           one directory per full service (ignored by git)
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
