# ADR-0001 — Match clients always send WAV (PCM)

- **Status**: Decided (implementation pending)
- **Date**: 2026-08-02
- **Scope**: client → `POST /match/` query path only. Catalog ingestion and
  `POST /songs/` uploads are unaffected (they may still be WAV/MP3/FLAC/OGG/M4A).

## Context

`POST /match/` (`api/routes/match.py`) currently saves the uploaded clip to a
named temp file (with the client-supplied extension), then runs
`load_audio(temp) → AudioFingerprintPipeline.run(y) → match_audio(db, fps)`.

Why the temp file exists:

- `load_audio` (`audio_processing/audio.py:8`) is a thin `librosa.load` wrapper.
- `librosa` decodes **WAV/FLAC/OGG via `soundfile`**, which accepts file-like
  objects (`io.BytesIO`).
- **MP3/M4A go through `audioread`**, whose backends (incl. the `ffmpeg`
  subprocess used in the container) require a real **file path**, not a buffer.

So any query format other than WAV/FLAC/OGG forces a temp file purely to satisfy
the MP3/M4A decode path.

We build the client, so we control what it sends.

## Decision

The client **always sends WAV (16-bit PCM, mono)** as the match query. The match
endpoint can then decode from an **in-memory buffer** (`io.BytesIO`) and drop its
named-temp-file step entirely.

## Rationale

- **Matching is format-agnostic.** Both catalog and query are normalized by
  `load_audio` to mono float32 @ 22050 Hz before fingerprinting, and fingerprints
  are codec-robust spectral-peak hashes (see `docs/fingerprinting.md`). A WAV
  query matches an MP3/FLAC catalog entry (the IA catalog) with no loss of
  fidelity that matters to the hash lookup + offset voting.
- **Removes the only reason the endpoint needs a temp file.**
- **WAV is trivial to produce client-side** (uncompressed PCM) — no lossy encoder
  dependency in the client.

## Consequences

### Matching pipeline (`api/routes/match.py`)

Planned change:

1. Read the request body into an `io.BytesIO` (client-sent WAV).
2. `buf.seek(0)`, then `y, sr = load_audio(buf)` → `pipeline.run(y)` →
   `match_audio(db, fingerprints)`.
3. Delete the `tempfile.NamedTemporaryFile` + `finally` unlink logic.
4. Keep the `SUPPORTED_AUDIO_EXTENSIONS` gate server-side (defense in depth);
   in practice the client only ever sends `.wav`.

Notes:

- `BytesIO` must be rewound to position 0 before passing to `soundfile`.
- FastAPI's `UploadFile` itself may spool >1 MB to a temp file on disk; a fully
  disk-free path would read raw via `Request.stream()` into a buffer. Nice-to-have,
  not required.
- `core/match_service.py`, `core/song_service.py`, `audio_pipeline.py` are
  **unchanged** — they already operate on fingerprints/numpy, never on files.

### Client

- Encode every query clip as WAV (16-bit PCM mono, any sample rate — `load_audio`
  resamples to 22050).
- Send as multipart `file` with filename `query.wav` (or raw body).

### Loadgen

- Already uploads/matchs synthetic chirp WAVs — no change.

### Tests

- `tests/integration/test_match_api.py` should gain a test that posts a WAV and
  hits the buffer path (no temp file), plus keep the negative cases
  (no-match, bad format, decode error).

## References

- `api/routes/match.py` — endpoint to change
- `audio_processing/audio.py` — `load_audio`
- `audio_pipeline.py` — `AudioFingerprintPipeline`
- `core/match_service.py` — `match_audio`
- `config.py` — `SUPPORTED_AUDIO_EXTENSIONS`
- `docs/matching.md`, `docs/fingerprinting.md`
