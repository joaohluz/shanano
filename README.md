# Shanano — Scalable Audio Fingerprinting

Learning project: turning a minimal Shazam clone into a distributed, observable, production-ish system.

## How It Works

The system processes audio through several steps:

1. **Audio Loading**: Load WAV files and normalize them
2. **Spectrogram Generation**: Convert audio to time-frequency representation using STFT
3. **Peak Detection**: Find prominent spectral peaks above a threshold
4. **Fingerprint Generation**: Create unique hashes from peak pairs within time windows
5. **Database Storage**: Store fingerprints with song metadata
6. **Matching**: Compare query fingerprints against database to find matches

## Current Status (Iterations 1–3 — complete)

### 🔜 Iteration 4 (planned): Catalog Ingestion, Auth, Webapp & Matching

Goals: populate the catalog automatically from a safe open-source source, secure the API for a future hosted deployment, and give users a web UI to upload songs and match audio with full metadata. Full spec lives in `AGENTS.md` under *Iteration 4*. Key decisions:

- **Catalog source**: Internet Archive (keyless, public domain / CC), default collection `etree` (Live Music Archive) — fetches artist, album, year, genre, and cover art per item.
- **Scheduler**: Kubernetes CronJob runs `catalog_fetch.py` on a schedule. Airflow is not deployed this iteration, but the fetch script is written to be reusable as an Airflow task later.
- **Auth**: JWT (HS256) + roles (`admin`/`user`); registration is admin-only; `admin` + `loadgen` users seeded via env.
- **Non-WAV audio**: add `ffmpeg` to the Docker image and relax `.wav`-only upload/match checks to `.wav .mp3 .flac .ogg .m4a`.
- **Endpoints**: upload requires auth, delete is admin-only; song listing, `/match/`, `/health`, `/metrics` are public.
- **Webapp**: static mic-only SPA served by FastAPI — record ~5–15 s from the mic, match anonymously, result card with cover art + full metadata.

### What's built

| Component | What it does |
|---|---|
| **FastAPI app** (`api/main.py`) | REST API with endpoints for songs CRUD, matching, and Prometheus `/metrics` |
| **SQLAlchemy models** (`core/models.py`) | `Song` (with status tracking) and `Fingerprint` tables |
| **Async PostgreSQL** (`core/database.py`) | asyncpg engine with FastAPI dependency injection |
| **Alembic** (`migrations/`) | Schema versioning — 2 migrations applied |
| **Async Worker** (`worker.py`) | Background service that polls for pending songs, fingerprints them via the audio pipeline, stores results |
| **Prometheus Metrics** (`core/metrics.py`) | Custom metrics: songs uploaded/processed, processing duration, HTTP request rate/duration, songs by status, worker poll cycles |
| **Structured Logging** (`core/logging.py`) | JSON-format logging via `structlog` with ISO timestamps, service name context |
| **Prometheus** | Scrapes `/metrics` from API (`:8000`) and Worker (`:8001`) every 10s |
| **Grafana** | Pre-provisioned datasource + dashboard (6 panels) — auto-deployed |
| **Docker Compose** (`infra/docker-compose.yml`) | 7 containers: API, Worker, PostgreSQL, pgAdmin, Prometheus, Grafana, loadgen |
| **Load Generator** (`loadgen.py`) | Fakes user traffic against the API so metrics visibly go up and down; request rate follows a sine wave between `LOADGEN_MIN_RPS` and `LOADGEN_MAX_RPS`, uploads synthetic chirp WAVs so the worker has real work |
| **Kubernetes** (`k8s/`) | Plain manifests: API ×2, Worker, PostgreSQL (StatefulSet), loadgen, Prometheus, Grafana, all on kind (see `k8s/README.md`) |

### API Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Health check |
| `GET` | `/songs/` | List all songs with fingerprint counts |
| `GET` | `/songs/{id}` | Get song details |
| `POST` | `/songs/` | Upload a WAV file (saves to volume, queues for processing) |
| `DELETE` | `/songs/{id}` | Delete a song and its fingerprints |
| `POST` | `/match/` | Match an uploaded audio clip (public, no auth) — returns the best catalog song with full metadata |

### Processing Flow

```mermaid
graph TB
    USER([Client])

    API[FastAPI :8000<br/>songs / match / metrics]
    WORKER[Worker :8001<br/>/metrics]

    PG[(PostgreSQL :5432)]
    VOL[(Uploads Volume)]

    PROM[Prometheus :9090]
    GRAF[Grafana :3000]

    USER -->|upload / list| API
    USER -->|dashboards| GRAF

    API -->|save WAV| VOL
    API -->|CRUD| PG

    WORKER -->|poll pending| PG
    WORKER -->|read WAV| VOL
    WORKER -->|store fingerprints| PG

    API -->|scrape :8000/metrics| PROM
    WORKER -->|scrape :8001/metrics| PROM
    PROM -->|datasource| GRAF
```

1. `POST /songs/` — saves WAV to shared uploads volume, creates `Song` row with `status: pending`
2. **Worker** polls DB every 5s, picks up pending songs
3. Worker runs `AudioFingerprintPipeline` (normalize → lowpass → spectrogram → peaks → hashes)
4. Fingerprints stored in `fingerprints` table, song status updated to `completed`
5. `GET /songs/` shows fingerprint count
6. **Observability** — Prometheus scrapes `/metrics` from API and Worker; Grafana renders pre-built dashboard with 6 panels (songs uploaded, songs by status, processing rate, p99 duration, HTTP rate, HTTP p99)

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

# View metrics
curl http://localhost:8000/metrics

# OpenAPI docs
open http://localhost:8000/docs

# Grafana dashboard
open http://localhost:3000
```

### Web Client (mic-only matching)

A static, same-origin web app (`webapp/`, served by FastAPI at `/`) lets anyone
record ~5–15 s of music from their microphone and match it against the catalog —
no login, no file upload. `POST /match/` is public so matching works
anonymously.

```bash
# With the API running (uvicorn api.main:app or docker compose up):
open http://localhost:8000
```

Allow the mic, pick a duration (5/10/15 s), press **Record**, and a result card
shows the matching song's cover art, artist/album/year, genre, score +
confidence, and a link to the source. Silence or unknown audio shows "No match
found"; denying the mic shows a permission message. See `docs/webapp.md` for the
full spec.

### Running Tests

Tests use SQLite+aiosqlite (no Docker needed):

```bash
pip install -r requirements-dev.txt
pytest
pytest --cov=. --cov-report=term-missing
```

CI runs automatically via GitHub Actions on push/PR.

### Generating Fake Traffic

To see the dashboards move, run the load generator against the API. The request rate breathes between `LOADGEN_MIN_RPS` and `LOADGEN_MAX_RPS` over a `LOADGEN_WAVE_PERIOD`-second sine wave, and it uploads synthetic chirp WAVs so the worker actually fingerprints songs.

```bash
# Point at the Docker-Compose API
docker compose -f infra/docker-compose.yml up -d loadgen

# Or run it directly against a local dev server
python loadgen.py --target http://localhost:8000 --duration 300

# Bigger waves, faster cycle
python loadgen.py --min-rps 2 --max-rps 40 --wave-period 60
```

Env vars (also used by the `loadgen` k8s Deployment): `LOADGEN_TARGET`, `LOADGEN_WORKERS`, `LOADGEN_MIN_RPS`, `LOADGEN_MAX_RPS`, `LOADGEN_WAVE_PERIOD`, `LOADGEN_DURATION`, `LOADGEN_SEED`.

### Kubernetes (Stage 3)

Deploys the whole stack on a local kind cluster. See `k8s/README.md` for the full walkthrough. Summary:

```bash
docker build -f infra/Dockerfile -t shanano-api:latest .
kind create cluster --name shanano --config k8s/kind-config.yaml
kind load docker-image shanano-api:latest --name shanano
kubectl apply -f k8s/
```

Then open the dashboard at `http://localhost:30030` (admin / shanano) and watch the loadgen waves roll through.

### Services

| Service | URL | Credentials |
|---|---|---|
| API | `http://localhost:8000` | — |
| OpenAPI docs | `http://localhost:8000/docs` | — |
| API metrics | `http://localhost:8000/metrics` | — |
| Worker metrics | `http://localhost:8001/metrics` | — |
| Prometheus | `http://localhost:9090` | — |
| Grafana | `http://localhost:3000` | `admin` / `shanano` |
| pgAdmin | `http://localhost:5050` | `admin@shanano.dev` / `shanano` |
| PostgreSQL | `localhost:5432` | `shanano` / `shanano` / `shanano` |

## Project Structure

```
shanano/
├── api/                    # FastAPI routes and app factory
│   ├── main.py             # App factory with lifespan, /metrics, HTTP middleware
│   ├── deps.py             # DI: get_db session dependency
│   └── routes/
│       ├── songs.py        # Song CRUD + upload
│       └── match.py        # Match endpoint (stub)
├── core/                   # Business logic
│   ├── database.py         # Async engine + session factory (reads DATABASE_URL from env)
│   ├── logging.py          # Structured JSON logging via structlog
│   ├── metrics.py          # Prometheus custom metrics (counters, histograms, gauges)
│   ├── models.py           # SQLAlchemy models (Song, Fingerprint, ProcessingStatus)
│   ├── schemas.py          # Pydantic request/response schemas
│   └── song_service.py     # Async song processing (load audio, pipeline, persist)
├── infra/                  # Containerization
│   ├── Dockerfile          # Multi-stage build (python:3.12-slim + librosa deps)
│   └── docker-compose.yml  # 7 services: API, Worker, PostgreSQL, pgAdmin, Prometheus, Grafana, loadgen
├── k8s/                    # Kubernetes manifests (Stage 3)
│   ├── 00-namespace.yaml   # shanano namespace
│   ├── 01-configmap.yaml   # Shared env (DATABASE_URL, UPLOAD_DIR)
│   ├── 02-storage.yaml     # Uploads PVC
│   ├── 03-postgres.yaml    # PostgreSQL StatefulSet + headless service
│   ├── 04-api.yaml         # API Deployment ×2 + NodePort service
│   ├── 05-worker.yaml      # Worker Deployment + metrics service
│   ├── 06-loadgen.yaml     # Fake traffic generator Deployment
│   ├── 07-prometheus.yaml  # Prometheus ConfigMap + Deployment + NodePort
│   ├── 08-grafana.yaml     # Grafana provisioning ConfigMaps + Deployment + NodePort
│   └── README.md           # kind deploy walkthrough
├── migrations/             # Alembic
│   ├── env.py              # Async-compatible Alembic env
│   └── versions/           # Migration scripts (2 so far)
├── observability/          # Prometheus & Grafana config
│   ├── prometheus/
│   │   └── prometheus.yml  # Scrape config for API (:8000) and Worker (:8001)
│   └── grafana/
│       ├── datasources/    # Auto-provisioned Prometheus datasource
│       └── dashboards/     # Pre-built dashboard with 6 panels
├── worker.py               # Background worker: polls for pending songs, fingerprints them
├── loadgen.py              # Fake user traffic generator (sine-wave RPS, synthetic uploads)
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
├── tests/                   # Pytest test suite (unit + integration)
│   ├── conftest.py          # Async SQLite fixtures, test client
│   ├── unit/                # Config, schemas, pipeline tests
│   └── integration/         # API, song service, worker tests
├── requirements-dev.txt    # Test dependencies (pytest, httpx, aiosqlite)
├── pytest.ini              # Pytest config (asyncio_mode=auto)
├── .github/workflows/      # CI (GitHub Actions)
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
