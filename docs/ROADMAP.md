# Roadmap: from working pipeline to weekly production tool

The pipeline runs end to end: service in, ranked moments out, 9:16 clip with subtitles and end
screen. What it is not yet is something a volunteer can run every Monday without a developer
nearby, and the moments it proposes are not yet reliably the ones a church would post.

Three phases. Phase 1 removes what will break or exhaust someone on a real weekly run. Phase 2
makes the selection worth trusting. Phase 3 makes the output look produced.

Each step lists the priority it serves, using the numbering from the request:
(1) selection and ranking, (2) stability and performance, (3) review UX,
(4) tracking and framing, (5) captions and clip quality, (6) church-specific analysis.

---

## Phase 1 · Survive weekly use

Two to three weeks. Nothing here is glamorous and all of it is load-bearing.

### Step 1 · A regression net, before anything else
Serves (2)

**Build.** A `tests/` package with pytest covering the pure functions that carry the quality of the
product: `subtitles.layout_text`, `discovery.build_windows/snap/score/dedupe_and_rank`,
`clips.slice_transcript`, `renderer.cropGeometry`, `brands.slug`. A fixed 3-minute transcript
fixture whose ASS output is asserted byte for byte. A node test that runs the same fixtures
through `subtitleLayout.ts` and `crop.ts` and diffs against the Python results. One end-to-end
test that pushes a 20-second fixture video through upload, a stubbed transcript and a render,
asserting 1080×1920 and the expected duration.

**Why.** 5,959 lines of code and zero automated tests. Every step below touches wrapping, ranking
or the FFmpeg filter chain, and today the only way to learn that something broke is to render a
video and look at it. Worse, `subtitles.py` ↔ `subtitleLayout.ts` and `renderer.py` ↔ `crop.ts`
are hand-maintained mirrors: when they drift, the preview quietly lies about the render, and
nobody notices until a church posts a clip whose subtitles sit somewhere else.

**Done.** `pytest` green in under 30 seconds, `npm test` runs the mirror comparison on the same
fixtures, both wired into CI and the session-start hook. A deliberate one-character change to
`CHAR_WIDTH_RATIO` in either language turns the suite red.

### Step 2 · Stop encoding every clip twice
Serves (2) and (5)

**Build.** Remove the intermediate cut. `clips.create_clip` re-encodes each selected range at CRF
18 full resolution (`backend/clips.py:15`), and the renderer then encodes that result again. The
range is already recorded on the project as `origin.start/end`, so the render can read the service
recording directly with `-ss`/`-t` on the input. Keep `extract_range` behind a flag for the case
where someone wants to delete the recording and keep the clips.

**Why.** Two generations of H.264 on every clip, visible as mush on skin tones and gradients, and
roughly double the CPU per clip. Processing eight moments from a 90-minute service means eight
full re-encodes before any subtitle work starts.

**Done.** "Verwerk gekozen fragmenten" finishes in seconds instead of minutes. A rendered clip is
one encode away from the camera original. A side-by-side of the same moment, old against new,
shows less blocking in the background.

### Step 3 · Batched transcription with a real ETA
Serves (2)

**Build.** Move to faster-whisper's `BatchedInferencePipeline` with the batch size chosen from
available cores and memory. Let model size follow the job: `small` for clips, an explicit
"nauwkeuriger, duurt langer" switch for `medium` on full services. Derive an ETA from the
throughput of the first two minutes and show it as time remaining, not only a percentage.

**Why.** 20 to 40 minutes for a 90-minute service on a laptop CPU is the longest wait in the
product by a wide margin. Batching typically gives two to four times on CPU. The person running
this on Monday morning wants to start it and walk away with a number they can plan around.

**Done.** A 90-minute recording transcribes in under 15 minutes on a mid-range laptop, and the
remaining-time estimate is within 20% for the whole second half of the run.

### Step 4 · Retention and disk hygiene
Serves (2)

**Build.** A cleanup pass on startup plus an "Opruimen" panel. Services older than N weeks lose
`source.mp4` and `work/audio.wav` and keep `service.json` and the transcript. Rendered projects
lose `source.mp4` once the output has been downloaded. Show what is kept and what it costs in GB,
and let the church change N.

**Why.** A 90-minute service is 2 to 6 GB in, plus a 170 MB wav, plus a full-resolution copy per
selected clip. Weekly use fills a laptop inside two months, and today's failure mode is FFmpeg
dying halfway through a render with the disk full.

**Done.** Ten simulated weekly services leave the app under 10 GB. The health check warns while
there is still room to act, not after a render has already failed.

### Step 5 · Jobs that survive a closed laptop
Serves (2)

**Build.** Persist job state on each progress update. On startup, offer to resume instead of only
marking the work as failed, which is all `models.recover_services` does now. Transcription resumes
from the last completed segment. Analysis skips windows whose results are already on disk.

**Why.** Closing the lid during a 30-minute transcription currently loses all of it, and that is
the most expensive step in the product to redo. It will happen every week.

**Done.** Killing the process mid-transcription and restarting picks up where it stopped, with a
complete transcript and no duplicated segments.

---

## Phase 2 · Make the selection worth trusting

Three to four weeks. This is where the product either earns its place or does not.

### Step 6 · Two-pass analysis: read the windows, then choose like an editor
Serves (1)

**Build.** Keep the map step over 180-second windows. Add a reduce step: send every surviving
candidate back to the model in a single call, each with its title, summary, reason and excerpt,
together with a short summary of the whole service, and ask it to pick and rank the best five to
ten for this service. Require a one-line justification per pick and an explicit reason for each
rejection. Keep both layers so the reviewer can open "ook gevonden, niet gekozen".

**Why.** Ranking today is `confidence + duration bonus` (`backend/discovery.py`, `score`), where
confidence is self-reported per window by a model that has never seen the rest of the service.
Across 36 windows those numbers are not comparable, so the ordering is close to arbitrary. Nothing
in the pipeline ever compares the sermon's best moment against its second best. This is the single
biggest lever on whether the proposed clips are worth posting.

**Done.** On three real services, at least four of the top five after the reduce pass are moments
the church would actually post, judged blind against the current ranking by someone from that
church.

### Step 7 · Know which part of the service you are in
Serves (1) and (6)

**Build.** A cheap structural pass before analysis that labels the transcript into welcome, songs,
readings, prayer, sermon, notices and blessing, using the vocabulary already in
`templates/woordenlijst.json` plus timing heuristics: song blocks produce sparse transcript,
notices cluster at the end, readings carry book names. Feed the label into each window prompt and
drop notice and liturgy windows before they are sent at all.

**Why.** Roughly half of a 90-minute service is not sermon. Analysing it costs money, adds noise to
the candidate list, and the prompt currently has to fight it with a bullet point. Skipping it is
cheaper and produces a cleaner list.

**Done.** Analysis cost falls by 40% or more on a real service, no candidate lands inside a notices
block, and the review timeline shows the service structure as a background band.

### Step 8 · An evaluation set, so "better" means something
Serves (1)

**Build.** Ten real services with a human-marked list of the moments that were actually posted. A
script that runs the pipeline over them and reports precision at five, recall of the posted set,
and cost per service. Every prompt or scoring change is measured on it before it ships.

**Why.** Prompt changes feel better and get worse all the time. Without a fixed set the team tunes
by anecdote. This is also the first number a national tech partner will ask for, and the one that
turns "we built a tool" into "we measured it".

**Done.** `python -m tools.evaluate` prints the table, and today's pipeline has a baseline written
down next to the date.

### Step 9 · Church vocabulary that improves itself
Serves (6)

**Build.** Extend `templates/woordenlijst.json` per brand with preacher names, series titles,
recurring hymn collections and local place names. Add a light feedback loop: when someone corrects
a word in the subtitle editor, offer to add that correction to the church's list. Pass the sermon
title and series into the analysis prompt when the church fills them in.

**Why.** Whisper gets Dutch church language wrong in predictable, repeating ways, and every wrong
word costs the reviewer an edit. Names are the worst of it and the most damaging in a clip that
goes out in public.

**Done.** After a month of use at one church, an unedited transcript from that church has fewer
than one name error per five minutes.

---

## Phase 3 · Make it look produced

Four to six weeks.

### Step 10 · Review in one screen, decided in five minutes
Serves (3)

**Build.** Rework `ClipSuggestions.tsx` from a scrolling article list into a triage view: compact
candidate rows on the left, one large 9:16 preview on the right playing the selected candidate
with live subtitles, and keyboard control (j/k to move, space to play, Enter to accept, x to
reject). A running count of what is selected, and bulk accept and reject. Boundary nudging stays,
behind a disclosure.

**Why.** The current screen asks the user to scroll a long list, open a disclosure, read an
excerpt and operate a separate player below. A volunteer with 20 minutes will not do that for 15
candidates. Selection is the only step in the product that genuinely needs human judgement, so it
deserves the best interface in it.

**Done.** Someone who has never seen the app reviews 15 candidates and produces four clips in
under five minutes without asking a question.

### Step 11 · Dynamic 9:16 framing
Serves (4)

**Built.** `backend/vision.py` looks at three frames a second with YuNet for faces and, every third
of those, YOLOv10n for people; the body says who is on stage and holds that identity, the face says
where the head is. `backend/tracking.py` turns the sightings into one x per 1/12.5 second through a
dead zone, an exponential ease with a speed cap, a keep-in line that lifts the cap when the speaker
is about to leave the picture, and a shot-cut detector that snaps rather than pans when a church
cuts to another camera. `renderer.track_commands` writes a `sendcmd` script read at 50 a second
against a labelled `crop@track` filter; `frontend/src/track.ts` mirrors the same lookup so the
preview shows where the render will put the frame. Cutting a service runs it per clip; a clip on
its own has a **Zoek de spreker** button. A path found in under 55% of a clip is kept but not
switched on, and **Zelf kaderen** is always one click away.

The timeline with draggable keyframes was dropped on purpose. Two buttons and a sentence about what
was found is the whole interface: a path that reads wrong is not worth editing keyframe by keyframe
when placing a static window by hand takes five seconds.

**Why.** A wide camera at the back of a church puts the preacher in a small part of a broad frame.
A static centre crop either loses them when they move or has to be pulled so far out that the clip
looks like security footage. This is the clearest visual difference between a clip cut from a
recording and a clip made for social.

**Done.** Measured on a 90-second sermon at 1280×720: detection runs at six times realtime, the
speaker is found in 100% of samples, the frame is perfectly still on 93% of steps, and the largest
single step is 1% of the width. Rendered both ways and measured on the finished videos, the head
sits 0.17 from the centre tracked against 0.49 static, and never against the edge against 15 of 68
samples. A staged two-camera cut jumps inside one frame.

### Step 12 · Captions that read like captions
Serves (5)

**Build.** Three changes. Split on phrase boundaries instead of character count:
`transcription.chunk_words` breaks at 60 characters, 6 seconds or a 0.7-second pause, which strands
prepositions and articles at the end of lines. Add optional word-level highlighting using the word
timings that are already collected and then discarded. Add a caption-quality pass in the editor
that flags any segment faster than 2.5 words per second, longer than 7 seconds, or containing a
word the vocabulary has a correction for.

**Why.** Captions are what the viewer actually reads, since most social viewing is muted. A line
break in the wrong place is the difference between a clip that looks made and one that looks
generated.

**Done.** Line breaks fall on phrase boundaries across a 20-segment sample, word highlighting
renders identically in the preview and the ASS output, and the editor surfaces every segment that
is too fast to read.

---

## Deliberately deferred

Multi-platform publishing, scheduling, an asset library, analytics, thumbnail generation, output
in other languages, multi-user accounts, and anything that needs a server.

All of it gets easier once four numbers are good: how long a service takes end to end, how many of
the top five proposals get posted, how long a review takes, and how the clip holds up next to one
a designer made. Until those are good, more features make a bigger tool, not a better one.
