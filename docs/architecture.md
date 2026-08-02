# Architecture

The system is a classic "fingerprint everything once, match by hash lookup"
audio-recognition design. A single **catalog** of songs lives in PostgreSQL,
each song is fingerprinted into a set of hash/offset rows, and a **query** clip
is fingerprinted the same way and matched by hash lookup + offset voting.

## Components

| Component | Where | Role |
|---|---|---|
| **FastAPI app** | `api/main.py` | HTTP API: auth, songs CRUD, upload, match, `/metrics`, `/health`. Wires routers + HTTP metrics middleware. |
| **Routes** | `api/routes/` | Thin: parse request → call a `core/` service → return response. Never contains business logic. |
| **Dependencies** | `api/deps.py` | `get_db` (session), `get_current_user` (JWT → User), `require_admin` (role guard). |
| **Core services** | `core/` | Business logic: `song_service` (fingerprint a song), `catalog_service` (IA fetch), `match_service` (hash lookup + offset voting), `user_service` (user persistence + seeding), `security` (bcrypt + JWT). |
| **DSP pipeline** | `audio_pipeline.py`, `audio_processing/` | Turns a numpy audio array into a list of fingerprints (5-tuples). Pure, stateless, shared by worker and match endpoint. |
| **Worker** | `worker.py` | Background loop: polls PostgreSQL for `pending` songs every 5 s, fingerprints them via `song_service`, updates status. Exposes its own `/metrics` on `:8001`. |
| **Database** | `core/database.py` | Async SQLAlchemy engine + session factory. Reads `DATABASE_URL`. |
| **Migrations** | `migrations/` | Alembic, 4 versions: songs+fingerprints, status/file_path, catalog metadata, users. |
| **Catalog CLI** | `catalog_fetch.py` | Thin wrapper over `catalog_service.fetch_catalog_batch`; the reusable unit for a future Airflow task / K8s CronJob. |
| **Load generator** | `loadgen.py` | Fake traffic: sine-wave RPS, weighted endpoint mix, synthetic chirp uploads. |
| **Observability** | `core/metrics.py`, `core/logging.py`, `observability/` | Prometheus custom metrics + structlog JSON logging + Prometheus/Grafana config. |

## Data model

Three tables (`core/models.py`):

- **songs** — `id`, `name`, `status` (`pending|processing|completed|failed`),
  `file_path`, plus Iteration 4 metadata: `artist`, `album`, `year`, `genre`,
  `cover_art_url`, `source`, `source_url` (indexed, used for catalog dedupe).
- **fingerprints** — composite PK `(hash, song_id)` plus the peak-pair
  coordinates (`anchor_time`, `anchor_freq`, `target_time`, `target_freq`).
  `song_id` FK → songs with `ON DELETE CASCADE`.
- **users** — `id`, `username` (unique), `hashed_password`, `role`
  (`admin|user`), `created_at`.

The `status` column is the **job queue**: the API writes `pending`, the worker
flips it to `processing` → `completed` (or `failed`). No message broker is
involved; the DB itself is the queue.

## Triggers (what starts each flow)

| Flow | Trigger | Entry point |
|---|---|---|
| Upload a song | `POST /songs/` (any authed user) | `api/routes/songs.py:add_song` |
| Fingerprint a song | worker poll finds `status=pending` | `worker.py:run_worker` → `core/song_service.py:process_song` |
| Fetch catalog | `python catalog_fetch.py` (CLI/CronJob/Airflow later) | `catalog_fetch.py:main` → `core/catalog_service.py:fetch_catalog_batch` |
| Match a clip | `POST /match/` (any authed user) | `api/routes/match.py:match_audio_endpoint` |
| Login / register | `POST /auth/login`, `POST /auth/register` (admin-only) | `api/routes/auth.py` |
| Seed bootstrap users | API startup (`lifespan`) | `api/main.py:lifespan` → `core/user_service.py:seed_users` |
| Collect metrics | Prometheus scrape every 10 s; every HTTP request; every worker poll | `api/main.py` middleware + `worker.py` |
| Generate fake traffic | loadgen start | `loadgen.py:run` |

## Design choices

- **DB-as-queue.** Songs get a status column and the worker polls. This is the
  simplest reliable job model for a learning project — no extra infrastructure —
  and was deliberately chosen before moving to Kafka (Iteration 5).
- **Single fingerprinting pipeline.** The same `AudioFingerprintPipeline`
  instance is used by the worker (to index) and the match endpoint (to make a
  query). Same code path ⇒ a clip matches only if the catalog was fingerprinted
  the identical way.
- **Routes thin, logic in `core/`.** Routes parse the request and call services;
  all DB access and algorithm logic lives in `core/`. Keeps the API layer swappable.
- **Metadata travels with the song.** `Song` rows carry artist/album/year/genre/
  cover art, so the match response can return a rich result card without extra joins.
- **Async everywhere.** FastAPI + SQLAlchemy async + asyncpg; the worker uses the
  same `async_session`. One exception: the DSP pipeline itself is synchronous
  (numpy/librosa), so the worker processes songs serially.

## Deployment topologies

The same code runs in three ways:

1. **Local dev / tests** — SQLite+aiosqlite via `DATABASE_URL`, no Docker.
2. **Docker Compose** (`infra/docker-compose.yml`) — API, worker, PostgreSQL,
   pgAdmin, Prometheus, Grafana, loadgen, sharing an `uploads` volume.
3. **Kubernetes / kind** (`k8s/`) — API Deployment ×2, worker, PostgreSQL
   StatefulSet, loadgen, Prometheus, Grafana, pgAdmin, with an `uploads` PVC.

> Note: as of today Compose and K8s set `JWT_SECRET` and the
> `ADMIN_*`/`LOADGEN_*` seeding vars (Compose inline; K8s via
> `k8s/secret.yaml`), and loadgen authenticates, so the auth-protected
> endpoints work in both deployments. The only pending K8s item is the
> catalog CronJob. See [auth.md](auth.md) for the env vars the API needs.
