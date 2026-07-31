# Shanano — Scalable Audio Fingerprinting

Learning project: turning a minimal Shazam clone into a distributed, observable, production-ish system.

## How It Works

The system processes audio through several steps:

1. **Audio Loading**: Load WAV files and normalize them
2. **Spectrogram Generation**: Convert audio to time-frequency representation using STFT
3. **Peak Detection**: Find prominent spectral peaks above a threshold
4. **Fingerprint Generation**: Create unique hashes from peak pairs within time windows
5. **Database Storage**: Store fingerprints with song metadata
6. **Matching**: Compare query fingerprints against database to find matches (not yet wired)

## Current Status (Iteration 1 — complete)

### What's built

| Component | What it does |
|---|---|
| **FastAPI app** (`api/main.py`) | REST API with endpoints for songs CRUD and matching |
| **SQLAlchemy models** (`core/models.py`) | `Song` (with status tracking) and `Fingerprint` tables |
| **Async PostgreSQL** (`core/database.py`) | asyncpg engine with FastAPI dependency injection |
| **Alembic** (`migrations/`) | Schema versioning — 2 migrations applied |
| **Async Worker** (`worker.py`) | Background service that polls for pending songs, fingerprints them via the audio pipeline, stores results |
| **Docker Compose** (`infra/docker-compose.yml`) | 4 containers: API, Worker, PostgreSQL, pgAdmin |

### API Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Health check |
| `GET` | `/songs/` | List all songs with fingerprint counts |
| `GET` | `/songs/{id}` | Get song details |
| `POST` | `/songs/` | Upload a WAV file (saves to volume, queues for processing) |
| `DELETE` | `/songs/{id}` | Delete a song and its fingerprints |
| `POST` | `/match/` | Match audio (not yet implemented — returns 501) |

### Processing Flow

1. `POST /songs/` — saves WAV to shared uploads volume, creates `Song` row with `status: pending`
2. **Worker** polls DB every 5s, picks up pending songs
3. Worker runs `AudioFingerprintPipeline` (normalize → lowpass → spectrogram → peaks → hashes)
4. Fingerprints stored in `fingerprints` table, song status updated to `completed`
5. `GET /songs/` shows fingerprint count

### Quick Start

```bash
# Start everything (requires Docker)
docker compose -f infra/docker-compose.yml up -d

# Apply any pending migrations
alembic upgrade head

# Upload a song
curl -X POST -F "file=@data/assets/clean_wavs/music-hd-0001.wav" http://localhost:8000/songs/

# Watch it get processed
docker compose -f infra/docker-compose.yml logs -f worker

# List songs (see fingerprint count increase)
curl http://localhost:8000/songs/

# OpenAPI docs
open http://localhost:8000/docs
```

### Services

| Service | URL | Credentials |
|---|---|---|
| API | `http://localhost:8000` | — |
| OpenAPI docs | `http://localhost:8000/docs` | — |
| pgAdmin | `http://localhost:5050` | `admin@shanano.dev` / `shanano` |
| PostgreSQL | `localhost:5432` | `shanano` / `shanano` / `shanano` |

## Project Structure

```
shanano/
├── api/                    # FastAPI routes and app factory
│   ├── main.py             # App factory with lifespan (auto-creates tables)
│   ├── deps.py             # DI: get_db session dependency
│   └── routes/
│       ├── songs.py        # Song CRUD + upload
│       └── match.py        # Match endpoint (stub)
├── core/                   # Business logic
│   ├── database.py         # Async engine + session factory (reads DATABASE_URL from env)
│   ├── models.py           # SQLAlchemy models (Song, Fingerprint, ProcessingStatus)
│   ├── schemas.py          # Pydantic request/response schemas
│   └── song_service.py     # Async song processing (load audio, pipeline, persist)
├── infra/                  # Containerization
│   ├── Dockerfile          # Multi-stage build (python:3.12-slim + librosa deps)
│   └── docker-compose.yml  # API + Worker + PostgreSQL + pgAdmin
├── migrations/             # Alembic
│   ├── env.py              # Async-compatible Alembic env
│   └── versions/           # Migration scripts (2 so far)
├── worker.py               # Background worker: polls for pending songs, fingerprints them
├── audio_processing/       # Original DSP modules (spectrogram, peaks, filters)
│   ├── audio.py            # load_audio, record_audio (lazy sounddevice import)
│   └── spectrogram.py      # STFT, peak detection via maximum_filter
├── controllers/            # Original CLI controllers (SQLite-based, still works)
│   ├── database.py         # SQLite connection
│   ├── fingerprint.py      # SHA-1 hash generation
│   ├── match_service.py    # Offset histogram matching
│   └── song_manager.py     # SQLite song CRUD
├── audio_pipeline.py       # AudioFingerprintPipeline class
├── cli.py                  # Original Typer CLI
├── config.py               # App-wide constants (FAN_OUT, sample rate, etc.)
├── data/                   # Sample audio files
├── AGENTS.md               # Project context for AI assistants
├── alembic.ini             # Alembic configuration
└── requirements.txt
```

## CLI (Original — Still Works)

The original CLI uses SQLite and can still be used for local experiments:

```bash
source .venv/bin/activate
pip install -r requirements.txt
python -m cli list
python -m cli add data/assets/clean_wavs/
python -m cli match
```

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | `postgresql+asyncpg://shanano:shanano@localhost:5432/shanano` | PostgreSQL connection string |
| `UPLOAD_DIR` | `data/uploads` | Directory for uploaded WAV files |

## Notebooks

Jupyter notebooks with detailed algorithm walkthroughs (from the original project):

- `audio_fingerprinting_pipeline.ipynb`
- `Input_Audio_Pipeline.ipynb`
- `Input_Processing_Experiments.ipynb`
- `perfect_match_histograms.ipynb`

## License

Educational project. Audio files from the [MUSAN](https://openslr.org/17/) corpus.

```LaTeX
@misc{musan2015,
  author = {David Snyder and Guoguo Chen and Daniel Povey},
  title = {{MUSAN}: {A} {M}usic, {S}peech, and {N}oise {C}orpus},
  year = {2015},
  eprint = {1510.08484},
  note = {arXiv:1510.08484v1}
}
```
