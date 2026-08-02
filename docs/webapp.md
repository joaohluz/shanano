# Webapp — Mic-only Match Client

- **Status**: Spec (implementation pending)
- **Date**: 2026-08-02
- **Scope**: a minimal, same-origin web client for matching recorded audio against
  the catalog. Mic-only; no login; no file upload.

## Goal

Anyone opens the app, records ~5–15 s of music from their microphone, and gets the
matching catalog song with full metadata — like Shazam, but without an account.
Matching must work anonymously. The only server-side change required is making
`POST /match/` public (plus serving the static app).

## Design decisions

- **Same-origin, no build step.** The app is static HTML/CSS/vanilla JS served by
  FastAPI itself via `StaticFiles`. No npm, no bundler, no CORS (same origin).
- **Mic-only (no file upload).** The webapp never accepts files from the user; the
  only audio source is `getUserMedia`. This keeps the abuse surface small and
  matches "ask the server to match".
- **WAV queries (ADR-0001).** The browser always sends 16-bit PCM mono WAV named
  `query.wav`, because the server decodes match queries from an in-memory
  `io.BytesIO` (no temp file) — raw MP3/M4A bodies would fail to decode.
- **Public matching.** `POST /match/` no longer requires auth. No other endpoint
  changes. Auth stays in place for everything else.

## Server-side changes (do these first)

### 1. Make `POST /match/` public

`api/routes/match.py`:

- Remove the `_current_user: User = Depends(get_current_user)` parameter from
  `match_audio_endpoint` (line 26).
- Remove the now-unused imports: `User` from `core.models` and `get_current_user`
  from `api.deps`. Keep `get_db`.
- Keep the `SUPPORTED_AUDIO_EXTENSIONS` gate and the 400/404 error behavior exactly
  as-is.

### 2. Serve the static app

`api/main.py`:

- After the `include_router` calls (registered **last**, so API routes win), mount
  the app:

```python
from pathlib import Path
from fastapi.staticfiles import StaticFiles

WEBAPP_DIR = Path(__file__).resolve().parent.parent / "webapp"
app.mount("/", StaticFiles(directory=WEBAPP_DIR, html=True), name="webapp")
```

- `html=True` makes `/` serve `index.html`.
- Because the mount is registered last, `/docs`, `/openapi.json`, `/health`,
  `/metrics`, `/auth/*`, `/songs/*`, `/match/*` keep priority.
- Resolve the path relative to `api/main.py` (not CWD) so it works regardless of
  where uvicorn is started.

### 3. Tests affected

`tests/integration/test_match_api.py::test_match_requires_auth`:

- Rename to `test_match_allows_anonymous` and drop the `auth_headers` fixture.
- Post `("test.wav", b"fake-wav-content", "audio/wav")` with **no** headers; assert
  `400` and that the detail mentions "decode" — this proves the endpoint is
  reachable without a token (it returned 401 before).
- The other match tests keep their `auth_headers`; sending a token to a now-public
  endpoint is harmless, so leave them as-is.

## Webapp — files to create

```
webapp/
├── index.html   # single page: record control + result card + error area
├── styles.css   # simple, clean, responsive
├── app.js       # mic lifecycle, fetch to /match/, render result/errors
└── audio.js     # MediaRecorder capture + decode + WAV encoding
```

All plain ES modules — `index.html` loads `app.js` with
`<script type="module" src="app.js">`. No build step, no dependencies.

## Behavior spec

### Page layout (`index.html`)

- Title: **Shanano** with a one-line subtitle ("Record audio to find its match").
- Record control: a single **Record** button that toggles to **Stop** while
  recording; a duration picker (5 / 10 / 15 s, default 10); a status line
  ("Recording…" with an optional live countdown).
- Result card (hidden until a match): cover art thumbnail, song name,
  artist · album · year, genre, score + confidence, and a link to `source_url` (if
  present). When `cover_art_url` is present render an `<img>`; on load error or
  when absent show a placeholder.
- Error area (hidden by default): a short human-readable message per the error
  cases below.
- No login, no file input, no navigation — one screen.

### Recording & matching flow (`app.js` + `audio.js`)

1. Click **Record** → `navigator.mediaDevices.getUserMedia({ audio: true })` →
   `MediaRecorder(stream)` (prefer `audio/webm;codecs=opus`, fall back to the
   default mime type).
2. Collect `dataavailable` chunks; auto-stop after the chosen duration, or on
   **Stop**.
3. On `stop`:
   - `stream.getTracks().forEach(t => t.stop())` — always release the mic.
   - Concatenate chunks → `new Blob(chunks, { type: recorder.mimeType })`.
   - `audioBuffer = await audioCtx.decodeAudioData(await blob.arrayBuffer())`
     (create/reuse one `AudioContext`; `resume()` it first if suspended).
   - Mix down to a mono `Float32Array` (average channel samples when
     `numberOfChannels > 1`).
   - Encode to 16-bit PCM mono WAV via `encodeWav(mono, audioBuffer.sampleRate)`.
4. `const fd = new FormData(); fd.append("file", wavBlob, "query.wav");`
   `fetch("/match/", { method: "POST", body: fd })` — **no** `Authorization` header.
5. Show a "Matching…" state while awaiting the response.

The recording is lossy (opus/webm) but fingerprints are codec-robust (both catalog
and query are normalized to mono 22050 Hz float32 before fingerprinting), so
matching still works. Optional future note: a `ScriptProcessorNode`/`AudioWorklet`
PCM capture path would be lossless but is **not** required.

### WAV encoder contract (`audio.js`)

`encodeWav(samples: Float32Array, sampleRate: number) -> Blob` producing a standard
44-byte-header PCM WAV:

- `channels = 1`, `bitsPerSample = 16`, `blockAlign = 2`,
  `byteRate = sampleRate * 2`.
- Header chunks: `RIFF` → `fmt ` (audioFormat 1, PCM) → `data`.
- Sample conversion: clamp to [-1, 1], multiply by 32767, store as little-endian
  `Int16Array`.
- Return `new Blob([headerBytes, pcmBytes], { type: "audio/wav" })`.
- Sample rate may be the device rate (44.1/48 kHz); the server resamples to 22050,
  so no browser-side resampling is needed (ADR-0001: "any sample rate").

## API contract (what the webapp talks to)

| Endpoint | Method | Auth | Body | Success | Errors |
|---|---|---|---|---|---|
| `/match/` | POST | none | multipart `file=query.wav` (audio/wav) | 200 `MatchResultOut` | 400 "Unsupported audio format" / "Could not decode audio file"; 404 "No match found" |

`MatchResultOut` fields to render: `song_name`, `artist`, `album`, `year`, `genre`,
`cover_art_url`, `score`, `confidence`, `source`, `source_url`.

## Error handling

- **404** → show "No match found".
- **400** → show "Could not decode that recording (or unsupported format)".
- **Network error / fetch throws** → show "Could not reach the server".
- **`getUserMedia` denied** → show a message explaining mic permission is required.
- **`decodeAudioData` fails** → treat like the 400 case.
- Every failure resets the Record button to idle and re-enables recording.

## Tests

### New `tests/integration/test_webapp.py`

Use the existing `client` fixture (async SQLite + dependency override):

- `GET /` → 200, body contains the page title (`"Shanano"`) and a reference to
  `app.js`.
- `GET /app.js` → 200; `GET /audio.js` → 200; `GET /styles.css` → 200.
- `GET /health` → 200 (API routes still win over the mount).
- `GET /docs` → 200 (FastAPI docs still reachable).
- `GET /metrics` → 200.
- Anonymous `POST /match/` with `("query.wav", b"fake-wav", "audio/wav")` → 400
  (not 401) — proves public match end-to-end through the mounted app.

### Updated `tests/integration/test_match_api.py`

- Replace `test_match_requires_auth` with the anonymous-access test described under
  Server-side changes.

## Documentation updates

- `docs/matching.md`: mark the flow public; drop the stale "save to temp file"
  comment (ADR-0001 is implemented); add a pointer to `docs/webapp.md`.
- `docs/auth.md`: in the endpoint protection matrix, change `POST /match/` from
  "yes / any user" to "**no** (public)".
- `README.md`: add a "Web client" section — `open http://localhost:8000` after
  starting the API, describe mic matching.
- `AGENTS.md`: update the `webapp/` entry (exists now: mic-only SPA, no build
  step), the directory layout, and note `POST /match/` is public in the Iteration 4
  status / open questions.

## Out of scope (do NOT implement)

- Login / sign-up UI or any token handling in the webapp (auth endpoints stay
  server-side, unchanged).
- File upload in the webapp.
- Match history or any profile feature.
- Song upload UI / catalog browser.
- CORS middleware.
- loadgen changes (its `/match/` calls start working automatically once the
  endpoint is public).

## Verification checklist

1. `pytest tests/integration/test_webapp.py tests/integration/test_match_api.py` —
   all pass.
2. `pytest` — full suite green.
3. Manual: start the API (`uvicorn api.main:app` or `docker compose up`), open
   `http://localhost:8000`, allow the mic, record music, see a result card with
   metadata; record silence → "No match found"; deny the mic → friendly message.

## References

- `api/routes/match.py` — endpoint to make public
- `api/main.py` — mount point for the static app
- `config.py` — `SUPPORTED_AUDIO_EXTENSIONS`
- `core/schemas.py` — `MatchResultOut`
- `docs/decisions/0001-client-sends-wav-for-match.md` — why match queries are WAV
- `docs/matching.md`, `docs/auth.md` — docs to update
