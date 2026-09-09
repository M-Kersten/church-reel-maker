# Evaluation set

Prompt changes feel better and get worse all the time. This is the fixed set they are
measured on, so "better" is a number rather than an impression.

## Adding a service

One folder per service, named however you like:

```text
evaluation/2026-03-08-rust/
  service.json      what this is, and which moments were actually posted
  transcript.json   {"language": "nl", "segments": [{"start", "end", "text"}, ...]}
```

`service.json`:

```json
{
  "title": "Rust in een druk leven",
  "duration": 4500,
  "sermonTitle": "Rust in een druk leven",
  "series": "Onderweg",
  "posted": [
    {"start": 1820, "end": 1868, "note": "rust is geen zwakte"},
    {"start": 2410, "end": 2455, "note": "je hoeft dit niet alleen te dragen"}
  ]
}
```

`posted` is the ground truth: the moments the church actually put out. Rough boundaries are
fine, a proposal counts as a hit when it overlaps half of one.

The transcript is the one the app produced, so the run measures the analysis and not the
transcription. Export it from a service folder (`services/<id>/transcript.json`).

Real services are not in git: they are the church's own recordings and the transcripts hold
what people said. Keep them here locally, or in a private folder pointed at with
`--set`. `voorbeeld-dienst/` is a made-up service so the tool runs out of the box.

## Running it

```bash
.venv/bin/python -m tools.evaluate                # every service in evaluation/
.venv/bin/python -m tools.evaluate --dry-run      # what it would cost, without spending it
.venv/bin/python -m tools.evaluate --set ~/diensten --save baseline.json
.venv/bin/python -m tools.evaluate --compare baseline.json
```

Write down the baseline before changing a prompt, and compare after.
