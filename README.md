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
3. The first start takes a few minutes: it installs Python packages and downloads FFmpeg into `tools/`. After an update, the next start installs any new packages by itself. Python itself is installed automatically on Windows (through winget) and through Homebrew on macOS when available; otherwise the window tells you where to get it.
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

Dutch church words are fed to the speech model through `templates/woordenlijst.json`: an `initialPrompt` with the vocabulary (Bible books, "gemeente", "Opwekking", "avondmaal") and a `corrections` map that repairs mistakes the model keeps making, such as "Lee 302" for "Lied 302". That file is shared by every church; `templates/woordenlijst.example.json` is the shipped copy.

On top of it, each brand keeps **its own words**, edited under **Merk en afsluiter**: who preaches here, the series that are running, the hymnals they sing from, the locations. Those go into the prompt in front of the audio, which is where names are won or lost.

And the app learns. When you correct a subtitle line, it compares your version with the machine's and works out which words actually changed. A word that sounds like what it replaced ("brie" for "Bree") or that only gained a capital in the middle of a line ("heilige geest" for "Heilige Geest") is offered back: **Zal ik dit onthouden?** Say yes and it goes in the church's list, so next Sunday it comes out right. A rewritten sentence, an added or dropped word, and sentence case at the start of a line are all left alone, because none of them teaches the model to hear.

Filling in **waar gaat het over** and **serie** on a service before transcribing helps twice: the speech model gets the words, and both analysis passes know what the preaching is about.

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
| `WHISPER_MODEL` | `small` | `tiny`, `base`, `small`, `medium`, `large-v3`. `small` is a good CPU trade-off. |
| `WHISPER_MODEL_ACCURATE` | `medium` | Used for a service with **Nauwkeuriger uitschrijven** ticked. |
| `WHISPER_DEVICE` | `cpu` | `cuda` when a GPU with CUDA is available. |
| `WHISPER_COMPUTE_TYPE` | `int8` on CPU, `float16` on GPU | |
| `WHISPER_BATCH_SIZE` | twice the core count, at most 8 | How many 30-second windows are decoded together. |

Transcription runs through faster-whisper's batched pipeline: windows go through the encoder
together instead of one after another. Measured on four cores with the `small` model over eight
minutes of Dutch speech, with identical output either way:

| batch | wall clock | speed |
| --- | --- | --- |
| one at a time | 139 s | 3.6× realtime |
| 2 | 72 s | 6.8× |
| 4 | 60 s | 8.3× |
| 8 | 58 s | 8.6× |
| 16 | 66 s | 7.5× (the cores are oversubscribed) |

That puts a 90-minute service at roughly ten minutes instead of twenty-five. The interface says
which phase it is in (pulling the audio out, loading the model, writing the text out) and, once it
has measured the speed of the current phase, how long is left. Batched decoding hands back several
minutes of text at a time, so the bar is carried forward at the measured rate between readings
rather than standing still and then jumping.

## Using the app

1. Drop a clip on the page. The original is stored under `projects/<id>/` and its metadata (size, duration, frame rate, audio) is read with ffprobe. The 9:16 preview appears right away.
2. Click **Transcribe**. Audio is extracted with FFmpeg and transcribed with faster-whisper, language forced to `nl`. Words are grouped into short caption-sized segments. This runs as a background job with a progress bar, so you can keep working and even reload the page while it runs.
3. Correct the subtitles. Each segment has editable start/end times (`mm:ss.s`) and text, plus **Split**, **Merge ↓** and delete. Click ▶ on a segment to jump the preview there. Edits are saved automatically.
4. Set the framing. The **Framing** panel shows the whole source with the 9:16 output frame drawn on it: drag the frame (or drag the preview itself) to choose which part of the picture ends up in the reel, and use the zoom slider to crop in further or, at the low end, to fit the whole picture with black bars. Landscape clips start centred and filling the frame; portrait clips start with the whole picture visible. **Reset** returns to that default.
5. Pick a style: font, weight, size (24–200), text colour, outline size and colour, optional dark translucent background, and how a line appears. Subtitles always sit bottom-centre, above the safe margin that Reels and Shorts overlay with UI. A bigger font spreads over more lines (up to three) before anything is scaled down, so turning the size up really does make the text bigger on screen.
6. Put the church logo in a corner if you want one. The **Logo in beeld** panel picks the corner, the width as a share of the frame, the opacity and the margin, and draws it straight into the preview. Files live in `templates/logos/` and are shared with the end screen.
7. Click **Render video**. Rendering runs as a background job with a progress bar; when it finishes a download link for `final.mp4` appears.

The preview is an HTML `<video>` with `object-fit` mimicking the static crop and an HTML overlay for subtitles; it uses the same fonts and layout rules as the renderer. When the clip ends, the outro plays in the preview as well. Nothing is rendered until you click **Render video**.

### Subtitle animation

Each line can appear in one of four ways, with the speed (60–600 ms) set alongside it. The preview replays the animation on every line, using CSS keyframes that mirror the ASS tags in the render:

| Setting | What it does | ASS |
| --- | --- | --- |
| `none` | the line is simply there | no tags |
| `fade` | fades in and out | `\fad` |
| `pop` | starts at 72% and springs to full size | `\fscx`/`\fscy` with `\t` |
| `slide` | rises 40 px into place | `\move` |

## Full service clip discovery

```text
Upload service → Transcribing → Analyzing service → Suggestions ready → Review & select → Process selected clips → Clip editor
```

1. Open the **Full service** tab and drop the complete recording. Transcription starts automatically (the same faster-whisper setup as for clips, forced to `nl`) and shows progress; with the `small` model a 90-minute service takes about 20 to 40 minutes on a recent laptop CPU (`medium` takes several times longer). The black window may print warnings from the speech library while this runs; the progress bar in the browser is what counts.
2. The transcript is labelled into the parts of a service before anything is sent: welcome, songs, reading, prayer, sermon, notices, blessing. No model is involved; it is the words a Dutch service uses, plus where in the hour a part falls and how much silence it leaves. See **Reading the shape of a service** below.
3. Analysis runs in two passes. The **first** cuts the preaching into overlapping windows of about three minutes and sends each one, told which part of the service it is in, coming back as structured JSON candidates (start, end, title, summary, reason, confidence). Windows that sit wholly in the singing or the notices are never sent, which is a little under half of a normal service.
4. Candidate boundaries are snapped to sentence boundaries and proposals covering the same moment are merged (the extra boundaries stay available as alternatives).
5. The **second** pass reads every surviving proposal at once, with the shape of the service and an excerpt of what is actually said, and picks the five to ten this service is worth posting. This is the pass that makes the order mean something: a per-window confidence is not comparable between windows, because the best moment of a dull three minutes scores the same as the best moment of the service. Every proposal comes back with a one-line verdict, including the ones passed over.
6. **Clip Suggestions** lists the chosen moments best first, with the shape of the service drawn behind them on the timeline. The ones that were found but passed over sit behind **Ook gevonden, niet gekozen** with the reason they lost. **Preview** plays just that range of the original recording; **Transcript & timecodes** opens the full excerpt and the boundary editor with direct `mm:ss.s` input and -5 / -1 / +1 / +5 second nudges. Selections and edits are saved automatically.
7. **Process selected clips** creates a normal clip project per selected range, with the matching part of the transcript already filled in, and lists them in the bar at the bottom of the screen. **Open in editor** switches to the Clip tab for subtitles, styling, framing and rendering. Nothing about rendering lives in the discovery layer.

   Nothing is cut at this point. A clip records which recording it came from and which seconds it covers, and the renderer seeks into the original, so a finished clip is one encode away from the camera instead of two and processing eight moments takes a moment rather than several minutes. `clips.source_of()` answers where a clip's footage is; `clips.materialise()` gives a clip its own copy, which only happens when the recording is about to be removed.

### Reading the shape of a service

`backend/structure.py` labels every sentence with the part of the service it belongs to, using
three kinds of evidence and no model at all:

- **The words.** Weighted phrases per part: "de collecte" and "koffie na de dienst" are notices,
  "laten we bidden" and "hemelse Vader" are prayer, a Bible book with a chapter is a reading,
  "we zingen" and a hymn number are singing.
- **The silence.** A stretch with nothing transcribed is nearly always music. How long a silence
  has to be depends on the transcript: a thinly written one has long gaps everywhere, so the
  threshold is three times its own median gap, never below 25 seconds.
- **The hour.** Where a sentence falls is a tie-breaker only, and the longest unbroken stretch of
  talking is taken as the sermon whatever the words said, so a preacher who opens with a reading
  does not lose those minutes.

Single sentences do not make a part: a label spreads to its quiet neighbours and runs shorter than
twenty seconds are folded into what surrounds them. A window is skipped only when it lies wholly
inside a part a clip never comes from (welcome, songs, notices, blessing), so a moment that starts
during the singing and runs into the sermon is still seen. Prayer and readings are kept: churches
do post those.

Measured on the service in `tests/service_text.py`, 52 of 52 sentences are labelled correctly and
11 of 24 windows are never sent.

### LLM configuration

| Variable | Default | Notes |
| --- | --- | --- |
| `LLM_PROVIDER` | `anthropic` | `anthropic` uses the Claude API (set `ANTHROPIC_API_KEY`); `ollama` uses a local Ollama server, so the whole pipeline stays on your machine. |
| `LLM_MODEL` | `claude-opus-5` / `llama3.1` | Model per provider. |
| `LLM_EFFORT` | `high` | Claude effort level (`low` … `max`). |
| `LLM_CONCURRENCY` | `3` | Windows analysed in parallel. |
| `OLLAMA_URL` | `http://localhost:11434` | |

Only transcript text is sent to the model, never video or audio. Before you press **Beste momenten zoeken**, the interface says how many pieces of text go out, roughly how many tokens that is and what it costs at list price: about 45,000 tokens and $0.75 for a 90-minute service with Claude Opus 5. With `LLM_PROVIDER=ollama` it says the run is free and stays on the machine.

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

## Disk space

A 90-minute service is a few GB in, so a church doing this every week fills a laptop inside a
couple of months. **Opruimen** in the app bar shows what is taking up room and what letting go of
it would give back.

- Working audio (a 170 MB wav per service) is thrown away on every start, as soon as there is a
  transcript to show for it. It takes a second to make again.
- A recording can be cleared once every fragment cut from it has been rendered. The transcript,
  the found moments and the finished videos stay; the panel says so on each row. A fragment that
  has not been rendered yet is given its own copy of its seconds first, so nothing is left
  pointing at a file that is gone, and rows that are not ready to go say why.
- Recordings older than `KEEP_WEEKS` (four by default, `0` turns it off) are cleared on start,
  again only when nothing is waiting on them.
- A clip that owns a copy of its footage lets go of it once its video has been made.

When free space drops below 3 GB the readiness check says so and names how much Opruimen could
give back.

## When something goes wrong

- The app bar shows a check of everything the app needs: FFmpeg, the speech model, the analysis model, free disk space and writable folders. It opens by itself when a check fails and says what to do.
- Long jobs can be stopped. Transcribing, analysing, cutting and rendering all have a **Stoppen** button; the job ends at its next checkpoint, which takes a few seconds for a render and up to half a minute for a transcription.
- Interrupted work carries on rather than starting over. Transcription writes down what it has heard every half minute, so closing the laptop half way through a 90-minute service costs the last thirty seconds, not the last twenty minutes. Analysis keeps each window's answer, so a run that lost a few windows to a rate limit only pays for those few the next time. After a restart the service goes back to the step before with a line saying which button carries on; pressing it continues where it stopped.
- Project and service files are written through a temporary file and renamed, so a crash or a power cut cannot leave half a file behind.
- One difficult piece of transcript no longer costs you the whole analysis. Each window is retried with growing pauses on a rate limit, server error or dropped connection, and a window that keeps failing is counted and skipped. You get the moments that were found plus a note saying how many pieces failed and why.
- The interface tells the difference between "the app is not answering" and "this went wrong". Losing the connection shows a calm banner and keeps polling; the work in the black window carries on.
- FFmpeg failures are translated: no space left, no permission, a damaged video file. A missing speech model or a rejected API key says which file to edit.

## Brands: one setup per church

Everything that makes a video belong to a church lives in a **brand**: the church details, the end screen, the default subtitle style and the default background music. Work for two locations or two churches and you make a brand for each, then switch between them in the **Merk en afsluiter** panel. New clips take the settings of the brand that is active, and the end screen is rebuilt when you switch.

Brands are stored as `templates/brands/<id>.json`, with `templates/brands/actief.json` naming the active one. On the first start the old `church.json` and `outro.json` are folded into one brand automatically, so nothing is lost.

## Logos

Logo files live in `templates/logos/` (ignored by git) and are used in two places: the corner of the clip (per project, in the **Logo in beeld** panel) and the end screen (per brand, in **Merk en afsluiter**). Upload once from either panel; png with transparency looks best. The corner logo is composited by FFmpeg with `overlay` at the chosen opacity and margin.

## Background music

The **Muziek** panel puts a track under the clip. Upload an mp3, m4a, wav, aac or ogg file once and it stays available for every clip; files live in `templates/music/`.

- **Volume** sets the level of the bed.
- **Onder de stem** turns on side-chain ducking: the music drops automatically while someone is speaking and comes back in the pauses. This is what makes a bed sound deliberate rather than loud.
- **Uitfaden** fades the music out at the end. The music runs under the end screen as well.

Speech is levelled to -14 LUFS with `loudnorm` before the music is mixed in, and the mix passes through a limiter, so clips from different services sound equally loud on Instagram and YouTube. You hear the music in the rendered video, not in the preview.

## Church outro (end screen)

`templates/outro.mp4` is appended after every clip, normalised to 1080×1920 during rendering. It is generated with FFmpeg (no AI) from two files:

- `templates/church.json` holds the church data. The `churchName` is also the small label above the wordmark in the interface.

  ```json
  {
    "churchName": "Example Church",
    "serviceTimes": ["09:30", "11:30"],
    "instagram": "@examplechurch"
  }
  ```

- `templates/outro.json` holds the look. **The Afsluiter panel in the Clip tab edits all of it**: background (solid colour, gradient with up to four colours and a direction, or an uploaded image with a darkening slider), font, duration, and the text lines with their size, colour, weight, font, letter spacing and capitals. Placement is direct: drag a line in the preview to move it up or down, drag it to the left or right third to align it there, or use **Zet alles boven / midden / onder** to move the whole block at once. The panel draws the end screen live while you type and rebuilds the video when you press **Opslaan en vernieuwen**. The file is created on the first start from the defaults; `templates/outro.example.json` is the copy in the repository. Every field:

  | Field | Meaning |
  | --- | --- |
  | `generate` | `false` keeps your own `outro.mp4` and never regenerates it |
  | `duration` | length in seconds (1–30) |
  | `font` | `Inter`, `Montserrat`, `Poppins` or `Arial`, used by every line without its own `font` |
  | `fade` | fade in and out, in seconds |
  | `background.type` | `solid`, `gradient` or `image` |
  | `background.color` | the colour for `solid` |
  | `background.colors` | 2 to 8 hex colours for `gradient` |
  | `background.angle` | gradient direction in degrees; 0 is left to right, 90 top to bottom |
  | `background.image` | file name in `templates/` for `image` |
  | `background.darken` | 0–1, a black veil over the image so text stays readable |
  | `motion` | `none`, `in` (slow dolly in), `out` (dolly out) or `up` (drift upwards) |

  | `logo.file` | optional PNG in `templates/logos/` (transparency supported) |
  | `logo.width`, `logo.y` | logo width and its vertical centre, in pixels of the 1080×1920 frame |
  | `lines[]` | the text lines, top to bottom |
  | `lines[].text` | the text; `{churchName}`, `{serviceTimes}` and `{instagram}` are filled in from `church.json` |
  | `lines[].y` | vertical centre in pixels (0 is the top, 1920 the bottom) |
| `lines[].align` | `left`, `center` or `right`, within a 60 px margin |
  | `lines[].size`, `weight`, `color` | font size, `regular`…`extrabold`, hex colour |
  | `lines[].font` | override the main font for this line |
  | `lines[].spacing` | extra letter spacing, for small uppercase labels |
  | `lines[].uppercase` | render the text in capitals |
  | `lines[].delay` | seconds before this line appears |

A line that is too wide is wrapped over two lines automatically, inside a 60 px margin on each side, so long church names and service times stay in frame. Move a line with its `y` when the wrapped text ends up too close to the next one. With a camera move the wrap point sits at the frame edge instead, so a line that fits at rest cannot suddenly break in two while it grows.

The camera move is drawn in two layers. Text is moved and scaled by libass, which works in floating point, so it glides instead of snapping to whole pixels; the background is a single still that an FFmpeg crop travels over, which is invisible on a gradient or a photograph. Both follow the same straight line, so the layers stay together. Measured on the default end screen, this brings the frame-to-frame wobble of the text down from 0.76 px to 0.02 px.

The end screen is rebuilt automatically whenever `outro.json` or `church.json` is newer than `outro.mp4`: on start and before every render. In the Clip tab, the **Afsluiter** panel shows the result and has a **Vernieuwen** button, so you can try colours without restarting. `python templates/make_outro.py` does the same from the command line.

Prefer your own video? Put it in `templates/outro.mp4`. Because its file date is then newer than the config, nothing overwrites it; set `"generate": false` to be certain.

The interface is in Dutch and carries the Nieuwe Kerk Utrecht colours: a deep purple app bar, display-size page titles, quiet numbered sections, and a dark stage panel that holds the preview and the one gold call to action. Gold carries meaning rather than decoration: the active tab, the crop frame, the fragment that is playing. Flat surfaces, hairline borders, Poppins throughout. No gradients in the interface itself. The colour tokens live at the top of `frontend/src/index.css`.

## Fonts

`templates/fonts/` holds the families the app offers, subset to the Latin characters Dutch needs (SIL Open Font License, licence texts included):

| Family | Character |
| --- | --- |
| Inter, Roboto, Open Sans | neutral sans, easy to read at any size |
| Montserrat, Poppins, Nunito | geometric and friendly |
| Oswald, Barlow Condensed | condensed, fits more words per line |
| Bebas Neue, Anton | heavy display, one weight, all caps feel |
| Lora, Playfair Display | serif, calmer and more formal |

Arial comes from the operating system. The backend scans the folder on request, so **dropping a pair of files named `{Family}-{Weight}.ttf` into `templates/fonts/` adds that font to both the subtitle and end-screen pickers** with no code change. Weights are `Regular`, `Medium`, `SemiBold`, `Bold` and `ExtraBold`; the family name inside the file must be `Family` for Regular and Bold and `Family Weight` for the rest, which is how Google Fonts static instances are built. A family that lacks the chosen weight falls back to its nearest one, so single-weight fonts work everywhere.

The renderer passes this directory to libass and the browser loads the same files, so the preview matches the output.

## API

```text
POST /projects                      create an empty project
POST /projects/{id}/upload          multipart upload (field "file"); probes the video
POST /projects/{id}/transcribe      start the Dutch transcription as a background job
GET  /projects/{id}/transcribe-status  {status, progress, message, error, canStop}
POST /projects/{id}/transcribe/stop stop the transcription that is running
GET  /projects/{id}                 project + transcript
PUT  /projects/{id}/transcript      save edited segments
PUT  /projects/{id}/style           save subtitle style
PUT  /projects/{id}/crop            save the crop window {x, y, zoom}
PUT  /projects/{id}/music           save the background music for this clip
PUT  /projects/{id}/meta            save the title and the description for sharing
PUT  /projects/{id}/watermark       save the corner logo {file, corner, width, opacity, margin}
POST /projects/{id}/render          start the background render job
POST /projects/{id}/render/stop     stop the render that is running
GET  /projects/{id}/render-status   {status, progress, message, error, canStop}
GET  /projects/{id}/output          the rendered final.mp4, named after the clip's title
GET  /projects/{id}/source          the footage behind the clip; for a clip cut from a service
                                    that is the whole recording, and the interface skips to
                                    `sourceStart` and stops at the end of the range
GET  /church                        contents of templates/church.json
GET  /health                        FFmpeg, speech model, analysis model, disk space, folders
GET  /storage                       what is taking up room and what clearing it would give back
POST /storage/clean                 clear one recording or one clip {kind, id}
POST /storage/clean-old             clear everything past the keep-by date with nothing waiting
PUT  /services/{id}/accuracy        pick the quick model or the one that hears more
GET  /brands                        the brands, and which one is active
GET  /brands/{id}                   one brand: church, end screen, subtitle style, music
PUT  /brands/{id}                   save a brand (rebuilds the end screen when it is active)
POST /brands                        create a brand, optionally copied from another
POST /brands/{id}/activate          make a brand active
DELETE /brands/{id}                 remove a brand (never the last one)
GET  /logos                         the logo files for the corner and the end screen
POST /logos                         upload a logo (png, jpg, webp, svg)
DELETE /logos/{name}                remove a logo
GET  /music                         the music files that can go under a clip
POST /music                         upload a music file
DELETE /music/{name}                remove a music file
GET  /fonts                         font families found in templates/fonts
GET  /outro                         the end-screen config from templates/outro.json
PUT  /outro                         save the end-screen config and rebuild the video
POST /outro/background              upload a background image for the end screen
POST /outro/rebuild                 rebuild templates/outro.mp4 from the config on disk
GET  /templates/...                 fonts and outro.mp4 (for the preview)

POST /services                      create an empty service
POST /services/{id}/upload          multipart upload of the full recording
POST /services/{id}/transcribe      background transcription (status: transcribing -> transcribed)
POST /services/{id}/analyze         background LLM analysis (status: analyzing -> ready)
GET  /services/{id}                 service + transcript + running job progress
GET  /services/{id}/status          small payload for polling (status, job, counts)
GET  /services/{id}/candidates      ranked candidates
PUT  /services/{id}/candidates      save selection and boundary edits
POST /services/{id}/process-selected  cut each selected candidate into a clip project (status: processing -> complete)
POST /services/{id}/stop            stop the transcription, analysis or cutting that is running
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
  outro.py          end-screen config -> ASS + FFmpeg, rebuilt when the config changes
  fonts.py          which font families and weights templates/fonts holds
  brands.py         brand presets: church, end screen, subtitle style, music
  health.py         the checks the interface shows
  clips.py          create_clip(source, start, end): cuts a range into a regular clip project
frontend/src/
  App.tsx                      tab switch between Full service and Clip
  api.ts                       typed API client (projects + services)
  subtitleLayout.ts            layout constants shared with subtitles.py
  components/ClipEditor.tsx    single-clip editor: project state, API calls, auto-save, render polling
  components/ServiceView.tsx   full-service upload, states, progress, processed clips
  components/ClipSuggestions.tsx  ranked candidate list: preview, select, adjust boundaries
  components/BrandPanel.tsx    brand switch, church details and the end-screen editor
  components/MusicPanel.tsx    background music under the clip
  components/LogoPanel.tsx     the church logo in a corner of the clip
  components/SharePanel.tsx    title (file name) and description for the post
  components/SystemCheck.tsx   the readiness check in the app bar
  fonts.ts                     font catalogue: loads the faces and resolves weights
  components/VideoPreview.tsx  9:16 preview with subtitle overlay and outro
  components/SubtitleEditor.tsx
  components/StylePanel.tsx
  components/RenderControls.tsx
  components/ProgressIndicator.tsx
templates/
  church.json, outro.json (created on first start), outro.example.json, make_outro.py, outro.mp4
  fonts/  logos/  music/  brands/  woordenlijst.json
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
source.mp4 → static 9:16 crop → fps 30 → burn subtitles.ass (libass) → concat outro
speech → loudnorm -14 LUFS → (optional) mix with ducked music → limiter
→ libx264 crf 20 + AAC 160k → final.mp4
```

The crop window `{x, y, zoom}` on the project decides the framing: `x`/`y` are the frame centre as fractions of the scaled source, `zoom` is relative to the scale that exactly fills the frame (1 fills, smaller letterboxes, larger crops in). The renderer scales the source, crops the part inside the frame and pads whatever is left. Defaults: landscape sources fill the frame centred, portrait sources keep the whole picture. The outro is always scaled to fit. Output is `yuv420p`, High profile, `+faststart`, which uploads directly to Instagram and YouTube.

## Part 2 hooks

- `renderer.build_crop_filter(info, output, crop_strategy, tracking, crop)` is the only place that decides how the source frame becomes 9:16. `crop_strategy="static"` is implemented; `"tracked"` raises `NotImplementedError` and is where a tracking-driven crop path goes. `renderer.crop_geometry` turns one `{x, y, zoom}` window into pixel coordinates, so a tracked strategy can emit a window per keyframe and reuse the same maths (mirrored in `frontend/src/crop.ts` for the preview).
- `render_video(..., crop_strategy=project.cropStrategy, tracking=project.tracking)` already passes the strategy and tracking data through from the project.
- `Project.cropStrategy` and `Project.tracking` exist in the project model, so tracking results can be stored per project without changing the API shape.
