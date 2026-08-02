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
- `api/routes/match.py` — match endpoint (public, no auth; WAV query decoded from in-memory BytesIO per ADR-0001)
- `api/routes/auth.py` — register (admin-only), login, /me
- `core/catalog_service.py` — Internet Archive catalog ingestion: search a collection (`fetch_catalog_batch`) or ingest a hand-picked list of links (`ingest_links`); a multi-track item becomes one song per track, deduped per-track by download URL
- `core/match_service.py` — async fingerprint matching ported from `controllers/match_service.py` (hash lookup → offset voting → best candidate)
- `core/security.py` — bcrypt hashing + JWT create/verify (HS256)
- `catalog_fetch.py` — CLI entrypoint for one IA fetch batch
- `seed.py` — seed pipeline CLI: `ingest` (links file → pending songs), `process` (one-shot fingerprinting), `dump` (songs+fingerprints+audio → compressed tar.gz), `restore`, `build` (all four)
- `core/seed_service.py` — portable, engine-agnostic catalog dump/load (`dump_seed` / `load_seed`); the seed is the offline demo data source
- `webapp/` — static mic-only SPA (record ~5–15 s → match anonymously), no build step; served by FastAPI via `StaticFiles` (docs: `docs/webapp.md`)
- `core/models.py` — SQLAlchemy models (Song with status tracking, Fingerprint, User)
- `core/schemas.py` — Pydantic schemas for request/response
- `core/database.py` — async engine + session factory (reads DATABASE_URL env var)
- `core/metrics.py` — Prometheus custom metrics (counters, histograms, gauges)
- `core/logging.py` — structured JSON logging via structlog
- `core/song_service.py` — async song fingerprinting (load audio, run pipeline, persist)
- `worker.py` — background worker: polls DB for pending songs every 5s, exposes /metrics on :8001
- `loadgen.py` — fake user traffic generator: sine-wave request rate between min/max RPS, uploads synthetic chirp WAVs; configurable via LOADGEN_* env vars
- `k8s/` — Kubernetes manifests for kind (namespace, configmap, postgres StatefulSet, api/worker/loadgen Deployments, prometheus, grafana) + `k8s/README.md` deploy walkthrough
- `audio_pipeline.py` — AudioFingerprintPipeline class
- `audio_processing/` — DSP modules (spectrogram, peaks, filters)
- `controllers/` — original SQLite-based CLI controllers (incl. `match_service.py` — the reference matching algorithm `core/match_service.py` was ported from)
- `infra/Dockerfile` — multi-stage Docker build (python:3.12-slim, includes `ffmpeg` for MP3 decode)
- `infra/docker-compose.yml` — 7 services: api, worker, db (PostgreSQL), pgadmin, prometheus, grafana, loadgen
- `migrations/` — Alembic migrations (versions: initial schema, status+file_path, catalog metadata, users)
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
- Docker Compose now runs 7 services (added loadgen)

### ✅ Iteration 3: Kubernetes + Fake Traffic — COMPLETE

- `loadgen.py` — fake user traffic generator that makes metrics visibly go up and down (sine-wave RPS between `LOADGEN_MIN_RPS`/`LOADGEN_MAX_RPS`, weighted endpoint mix incl. uploads of synthetic chirp WAVs so the worker has real work)
- `k8s/` — plain manifests for kind: namespace, configmap, uploads PVC, postgres StatefulSet, api Deployment ×2 + NodePort (:30000), worker + metrics NodePort (:30001), loadgen Deployment, prometheus NodePort (:30900), grafana NodePort (:30030)
- `k8s/README.md` — deploy walkthrough (build image, kind create, kind load docker-image, kubectl apply)
- loadgen wired into docker-compose too (`docker compose up -d loadgen`)
- Tests: `tests/unit/test_loadgen.py`

### ✅ Iteration 4: Catalog Ingestion, Auth, Webapp & Matching — COMPLETE

Goals: populate the catalog automatically from a safe open-source source, secure the API for a future hosted deployment, and give users a web UI to upload songs and match audio with full metadata.

#### Design decisions

- **Audio source**: Internet Archive (keyless, public domain / CC). Default collection `etree` (Live Music Archive — rich metadata: artist, album, year, genre, cover art). Collection is configurable via `CATALOG_COLLECTION` env.
- **Scheduler**: Kubernetes CronJob (native pod scheduling). Airflow is *not* deployed this iteration; `catalog_fetch.py` is deliberately written to be reusable as an Airflow task later (the CronJob is the plain-k8s version of the same DAG step).
- **Auth**: JWT (HS256) + roles (`admin`/`user`). **Registration is admin-only** — no public register endpoint. Seed `admin` and `loadgen` users via env at startup, plus `scripts/create_user.py` for ad-hoc users.
- **Non-WAV audio**: `load_audio` uses `librosa.load`, which decodes WAV/FLAC/OGG via soundfile and MP3 via audioread. No functional blocker. Two changes needed:
  1. Add `ffmpeg` to `infra/Dockerfile` so MP3s decode reliably in the container.
  2. Relax `.wav`-only checks in `POST /songs/` and `POST /match/` to accept `.wav .mp3 .flac .ogg .m4a`.
- **Endpoint protection**: `POST /songs/` any authed user, `DELETE /songs/{id}` admin-only, `POST /match/` **public** (anonymous — the mic-only webapp matches without an account, see `docs/webapp.md`). `GET /songs*`, `/health`, `/metrics` stay public (loadgen + Prometheus need them).
- **Client match queries are always WAV (ADR-0001)**: since we build the client, it always sends WAV (16-bit PCM) for `POST /match/`. Matching is format-agnostic (both sides normalize to mono 22050 Hz, codec-robust peak hashes), so WAV queries match MP3/FLAC catalog entries fine. This lets `POST /match/` decode from an in-memory `BytesIO` and drop its temp-file step (the temp file only existed because `audioread` needs a path for MP3/M4A). Server-side decode of catalog audio (FLAC/OGG/MP3/M4A) is unaffected. Full writeup: `docs/decisions/0001-client-sends-wav-for-match.md`.

#### Phases

1. **Metadata model** — migration adding to `songs`: `artist`, `album`, `year`, `genre`, `cover_art_url`, `source`, `source_url`. Update `core/schemas.py` (SongOut/SongListOut/MatchResultOut gain metadata) + new `User`-related schemas.
2. **IA catalog job** — `core/catalog_service.py`: query `https://archive.org/advancedsearch.php` (configurable collection), fetch `https://archive.org/metadata/{identifier}` (extract creator/title/date/subject, cover art via `https://archive.org/services/img/{identifier}`), download audio from `https://archive.org/download/{identifier}/{file}` to `UPLOAD_DIR`, insert `Song(status=pending, ..., source="internet_archive")`, dedupe per-track by download URL. A multi-track item (album) becomes one pending song per distinct track (formats/bitrate-transcodes of the same track collapse to the best format); a single-track item stays one song. `catalog_fetch.py` = CLI for one batch (`CATALOG_MAX_ITEMS`, default 5). Unit tests with mocked httpx.
3. **Auth** — deps `PyJWT` + `bcrypt`; `core/security.py` (hash/verify + token create/decode); `User` model + migration (`id`, `username` unique, `hashed_password`, `role`, `created_at`); `api/routes/auth.py`: `POST /auth/register` (admin-only), `POST /auth/login` (OAuth2PasswordRequestForm → JWT), `GET /auth/me`; `api/deps.py`: `get_current_user`, `require_admin` (OAuth2PasswordBearer).
4. **Real matching** — port `controllers/match_service.py` (SQLite) to async SQLAlchemy in `core/match_service.py`: hash lookup → offset voting → best candidate → full Song. `POST /match/` runs `load_audio → pipeline.run → match`, returns `MatchResultOut` with all metadata.
5. **Webapp** — `webapp/` static mic-only SPA (no build step): record from the mic → encode WAV in the browser → `POST /match/` anonymously → result card with cover art + full metadata. Mounted via FastAPI `StaticFiles`. Spec: `docs/webapp.md`.
6. **K8s** — `k8s/10-catalog-cronjob.yaml` (mounts `uploads-pvc`, env from configmap + secret), `k8s/secret.yaml` (JWT secret, admin creds), configmap keys (`CATALOG_COLLECTION`, `CATALOG_MAX_ITEMS`, `JWT_*`). Update docker-compose (ffmpeg, auth env, catalog service), `k8s/README.md`, `README.md`, AGENTS.md.
7. **Tests** — update `test_songs_api.py`/`test_worker.py` for auth (admin + user token fixtures); new `test_catalog_service.py`, `test_auth.py`, `test_match_api.py`.

#### Remaining items (post-Iteration-4 gaps)

- **K8s catalog CronJob + secret** — `k8s/10-catalog-cronjob.yaml` and `k8s/secret.yaml` are still not written; the catalog runs via the CLI/`make catalog` only (see `k8s/README.md` → "Planned").
- **Compose/K8s auth env** — `docker-compose.yml` and the k8s manifests don't set `JWT_SECRET` / `ADMIN_*` / `LOADGEN_*`, so the auth-protected endpoints aren't usable in those deployments yet.
- **loadgen auth** — `loadgen.py` doesn't log in or attach a `Bearer` header, so its upload/delete requests currently return 401 (it logs them and keeps running).

### 🔜 Upcoming Iterations (beyond 4)

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
│       ├── match.py         # Match endpoint (public, BytesIO decode)
│       └── auth.py          # Iteration 4: register (admin-only), login, /me
├── core/
│   ├── __init__.py
│   ├── database.py          # Async engine + session factory
│   ├── logging.py           # Structured JSON logging via structlog
│   ├── metrics.py           # Prometheus custom metrics
│   ├── models.py            # SQLAlchemy models + ProcessingStatus enum
│   ├── schemas.py           # Pydantic schemas
│   ├── song_service.py      # Async song fingerprinting
│   ├── catalog_service.py   # IA catalog fetch (search + links) + metadata
│   ├── seed_service.py      # Portable catalog dump/load (the offline demo seed)
│   ├── match_service.py     # Async fingerprint matching
│   └── security.py          # bcrypt + JWT
├── infra/
│   ├── __init__.py
│   ├── Dockerfile           # Multi-stage python:3.12-slim (adds ffmpeg in Iteration 4)
│   └── docker-compose.yml   # API + Worker + PostgreSQL + pgAdmin + Prometheus + Grafana + loadgen
├── k8s/                     # Kubernetes manifests (Iteration 3)
│   ├── 00-namespace.yaml
│   ├── 01-configmap.yaml
│   ├── 02-storage.yaml      # Uploads PVC
│   ├── 03-postgres.yaml     # StatefulSet + headless service
│   ├── 04-api.yaml          # Deployment ×2 + NodePort :30000
│   ├── 05-worker.yaml       # Deployment + metrics NodePort :30001
│   ├── 06-loadgen.yaml      # Fake traffic generator Deployment
│   ├── 07-prometheus.yaml   # ConfigMap + Deployment + NodePort :30900
│   ├── 08-grafana.yaml      # Provisioning ConfigMaps + Deployment + NodePort :30030
│   ├── 09-pgadmin.yaml      # pgAdmin Deployment + NodePort :30050
│   └── README.md            # kind deploy walkthrough
├── migrations/
│   ├── env.py               # Async Alembic env
│   ├── script.py.mako
│   └── versions/
│       ├── 8213ee7ae066_create_songs_and_fingerprints_tables.py
│       ├── f8aa4bb84303_add_status_and_file_path_to_songs.py
│       ├── a3f0d86e1588_add_catalog_metadata_to_songs.py
│       └── 8e8eef82eab6_create_users_table.py
├── observability/           # Prometheus scrape config + Grafana provisioning
│   ├── prometheus/
│   │   └── prometheus.yml   # Scrapes api (:8000) and worker (:8001)
│   └── grafana/
│       ├── datasources/     # Auto-provisioned Prometheus datasource
│       └── dashboards/      # Pre-built 6-panel dashboard
├── airflow/                 # Placeholder for Iteration 5
├── kafka/                   # Placeholder for Iteration 6
├── webapp/                  # Mic-only SPA: index.html, styles.css, app.js, audio.js
├── tests/
│   ├── __init__.py
│   ├── conftest.py           # Async SQLite engine + fixtures
│   ├── unit/
│   │   ├── __init__.py
│   │   ├── test_config.py
│   │   ├── test_schemas.py
│   │   ├── test_audio_pipeline.py
│   │   ├── test_catalog_service.py
│   │   ├── test_loadgen.py
│   │   ├── test_match_service.py
│   │   ├── test_seed_service.py
│   │   └── test_auth.py
│   └── integration/
│       ├── __init__.py
│       ├── test_songs_api.py
│       ├── test_match_api.py
│       ├── test_webapp.py
│       ├── test_song_service.py
│       ├── test_worker.py
│       └── test_auth.py
├── audio_processing/        # DSP modules (existing)
├── controllers/             # SQLite controllers (existing)
├── data/                    # Sample audio + data/seed/ (links file + built seeds)
├── worker.py                # Background fingerprinting worker + /metrics on :8001
├── seed.py                  # Seed pipeline CLI (ingest -> process -> dump -> compress)
├── loadgen.py               # Fake user traffic generator (sine-wave RPS, synthetic uploads)
├── audio_pipeline.py        # AudioFingerprintPipeline class
├── cli.py                   # Original Typer CLI
├── config.py                # App-wide constants
├── requirements.txt
├── alembic.ini
└── AGENTS.md
```
