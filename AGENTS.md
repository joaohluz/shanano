# Shanano — Scalable Audio Fingerprinting

Learning project: turning a minimal Shazam clone into a distributed, observable, production-ish system.

## Tech Stack

- **Language**: Python 3.12
- **API**: FastAPI (async)
- **ORM**: SQLAlchemy 2.x (async with asyncpg)
- **Migrations**: Alembic
- **Database**: PostgreSQL
- **Containerization**: Docker + Docker Compose
- **Orchestration**: Kubernetes (kind), Helm
- **Observability**: Prometheus, Grafana, OpenTelemetry
- **Scheduling**: Apache Airflow
- **Messaging**: Apache Kafka

## Relevant Files

- `AGENTS.md` — this file. Preserves project context across opencode sessions.
- `config.py` — app-wide constants (FAN_OUT, sample rate, UPLOAD_DIR)
- `api/main.py` — FastAPI app factory with lifespan, /metrics endpoint, HTTP middleware
- `api/deps.py` — DB session dependency injection
- `api/routes/songs.py` — song CRUD + WAV upload endpoint
- `api/routes/match.py` — match endpoint (stub, returns 501)
- `core/models.py` — SQLAlchemy models (Song with status tracking, Fingerprint)
- `core/schemas.py` — Pydantic schemas for request/response
- `core/database.py` — async engine + session factory (reads DATABASE_URL env var)
- `core/metrics.py` — Prometheus custom metrics (counters, histograms, gauges)
- `core/logging.py` — structured JSON logging via structlog
- `core/song_service.py` — async song fingerprinting (load audio, run pipeline, persist)
- `worker.py` — background worker: polls DB for pending songs every 5s, exposes /metrics on :8001
- `audio_pipeline.py` — AudioFingerprintPipeline class
- `audio_processing/` — DSP modules (spectrogram, peaks, filters)
- `controllers/` — original SQLite-based CLI controllers
- `infra/Dockerfile` — multi-stage Docker build (python:3.12-slim)
- `infra/docker-compose.yml` — 6 services: api, worker, db (PostgreSQL), pgadmin, prometheus, grafana
- `migrations/` — Alembic migrations (versions: initial schema, status+file_path columns)
- `observability/prometheus/prometheus.yml` — scrape config for api (:8000) and worker (:8001)
- `observability/grafana/` — provisioned datasource + dashboard config
- `cli.py` — original Typer CLI (SQLite, still works independently)
- `tests/` — pytest test suite (unit + integration) + legacy scripts
- `tests/conftest.py` — async SQLite engine + TestClient fixtures
- `tests/unit/` — unit tests (config, schemas, audio pipeline)
- `tests/integration/` — integration tests (API routes, song service, worker)
- `requirements-dev.txt` — test dependencies (pytest, httpx, aiosqlite, pytest-cov)
- `pytest.ini` — pytest configuration (asyncio_mode=auto)
- `.github/workflows/test.yml` — CI on push/PR to scalable-shazam
- `data/` — sample audio files

## Communication

- **Ask before running commands** — unless the user explicitly says "run free" or "you have permission to run commands freely", always ask for approval before executing anything that creates, modifies, or deletes files, installs dependencies, or starts/stops containers. This is a learning project and the user wants to understand each step.

## Conventions

- Type hints everywhere
- Async FastAPI + asyncpg for DB
- SQLAlchemy models in `core/models.py`
- Business logic in `core/`, never in routes
- Routes thin — parse request, call service, return response
- Dependency injection for DB sessions
- Metrics exported on `/metrics` (Prometheus format)
- Alembic migrations in `migrations/`
- Tests mirror the `core/` structure
- README.md updated as each iteration adds new capabilities

## Dev Workflow

```bash
# Start everything
docker compose -f infra/docker-compose.yml up -d

# Apply migrations
alembic upgrade head

# Install test dependencies
pip install -r requirements-dev.txt

# Run tests (local SQLite, no Docker needed)
pytest

# Run with coverage
pytest --cov=. --cov-report=term-missing

# View logs
docker compose -f infra/docker-compose.yml logs -f api
docker compose -f infra/docker-compose.yml logs -f worker

# View raw metrics
curl http://localhost:8000/metrics

# Grafana dashboard (admin / shanano)
open http://localhost:3000

# Upload a song to test the pipeline
curl -X POST -F "file=@data/assets/clean_wavs/music-hd-0001.wav" http://localhost:8000/songs/

# List songs
curl http://localhost:8000/songs/
```

## Testing

- **pytest** with `pytest-asyncio` (auto mode) — no decorators needed for async tests
- **Test DB**: SQLite+aiosqlite in-memory (set via `DATABASE_URL` env var in `conftest.py`)
- **FastAPI TestClient**: via `httpx.AsyncClient` with `get_db` dependency override
- **Test isolation**: each test gets a fresh DB engine + session (function-scoped fixtures)
- **Markers**: `unit` (no external deps) and `integration` (DB, API)
- **CI**: GitHub Actions on push/PR to `scalable-shazam` (`.github/workflows/test.yml`)

## Iteration Status

### ✅ Iteration 1: FastAPI + Docker — COMPLETE

- REST API with song CRUD and match endpoints
- SQLAlchemy async models (Song with status tracking, Fingerprint)
- Alembic migrations for schema versioning
- Async worker that polls for pending songs and fingerprints them
- Docker Compose with 4 services

### ✅ Iteration 2: Observability — COMPLETE

- Prometheus custom metrics (songs uploaded/processed, processing duration, HTTP request rate/duration, songs by status, worker poll cycles)
- `/metrics` endpoint on API (:8000) and worker HTTP server (:8001)
- Structured JSON logging via structlog (ISO timestamps, service context)
- Prometheus + Grafana containers with auto-provisioned datasource and 6-panel dashboard
- Docker Compose now runs 6 services

### 🔜 Upcoming Iterations

3. **Kubernetes** — manifests/Helm charts, deploy on kind
4. **Job Scheduling (Airflow)** — batch re-indexing, data retention DAGs
5. **Event-Driven (Kafka)** — async fingerprint processing pipeline
6. **Advanced Scalability** — HPA, Redis caching, read replicas, S3 audio storage, load testing

## Directory Layout (current)

```
shanano/
├── api/
│   ├── __init__.py
│   ├── main.py              # FastAPI app factory + /metrics + HTTP middleware
│   ├── deps.py              # DI (DB sessions)
│   └── routes/
│       ├── __init__.py
│       ├── songs.py         # Song CRUD + WAV upload
│       └── match.py         # Match endpoint (stub)
├── core/
│   ├── __init__.py
│   ├── database.py          # Async engine + session factory
│   ├── logging.py           # Structured JSON logging via structlog
│   ├── metrics.py           # Prometheus custom metrics
│   ├── models.py            # SQLAlchemy models + ProcessingStatus enum
│   ├── schemas.py           # Pydantic schemas
│   └── song_service.py      # Async song fingerprinting
├── infra/
│   ├── __init__.py
│   ├── Dockerfile           # Multi-stage python:3.12-slim
│   └── docker-compose.yml   # API + Worker + PostgreSQL + pgAdmin + Prometheus + Grafana
├── migrations/
│   ├── env.py               # Async Alembic env
│   ├── script.py.mako
│   └── versions/
│       ├── 8213ee7ae066_create_songs_and_fingerprints_tables.py
│       └── f8aa4bb84303_add_status_and_file_path_to_songs.py
├── observability/           # Prometheus scrape config + Grafana provisioning
│   ├── prometheus/
│   │   └── prometheus.yml   # Scrapes api (:8000) and worker (:8001)
│   └── grafana/
│       ├── datasources/     # Auto-provisioned Prometheus datasource
│       └── dashboards/      # Pre-built 6-panel dashboard
├── airflow/                 # Placeholder for Iteration 4
├── kafka/                   # Placeholder for Iteration 5
├── tests/
│   ├── __init__.py
│   ├── conftest.py           # Async SQLite engine + fixtures
│   ├── unit/
│   │   ├── __init__.py
│   │   ├── test_config.py
│   │   ├── test_schemas.py
│   │   └── test_audio_pipeline.py
│   └── integration/
│       ├── __init__.py
│       ├── test_songs_api.py
│       ├── test_match_api.py
│       ├── test_song_service.py
│       └── test_worker.py
├── audio_processing/        # DSP modules (existing)
├── controllers/             # SQLite controllers (existing)
├── data/                    # Sample audio
├── worker.py                # Background fingerprinting worker + /metrics on :8001
├── audio_pipeline.py        # AudioFingerprintPipeline class
├── cli.py                   # Original Typer CLI
├── config.py                # App-wide constants
├── requirements.txt
├── alembic.ini
└── AGENTS.md
```
