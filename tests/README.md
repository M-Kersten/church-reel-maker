# Tests

```bash
.venv/bin/python -m pytest          # the backend
cd frontend && npm test             # the preview against the renderer
```

`mirror.json` holds the answers Python gives for a fixed set of subtitle and crop cases.
`npm test` runs the same cases through `subtitleLayout.ts` and `crop.ts` and fails on any
difference, because those two files are hand-kept copies of `subtitles.py` and
`renderer.py`. When you change either side on purpose, regenerate the fixture:

```bash
.venv/bin/python tests/mirror_cases.py
```

`fixtures/subtitles.ass` is the same idea for the whole subtitle path: a frozen transcript
whose generated ASS is compared byte for byte. Delete it to record a new baseline.
