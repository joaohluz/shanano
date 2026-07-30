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
- `config.py` — app-wide constants (FAN_OUT, sample rate, etc.)
- `core/` — fingerprinting pipeline (audio processing, peak detection, hashing)
- `api/` — FastAPI routes and app factory
- `infra/` — Docker, Compose, K8s, Helm
- `observability/` — Grafana dashboards, Prometheus rules, OTel config
- `airflow/` — DAG definitions
- `kafka/` — producer/consumer schemas
- `tests/` — test suite

## Communication

- **Ask before running commands** — unless the user explicitly says "run free" or "you have permission to run commands freely", always ask for approval before executing anything that creates, modifies, or deletes files, installs dependencies, or starts/stops containers. This is a learning project and the user wants to understand each step.

## Conventions

- Type hints everywhere
- Async FastAPI + asyncpg for DB
- SQLAlchemy models in `core/models.py`
- Business logic in `core/`, never in routes
- Routes thin — parse request, call service, return response
- Dependency injection for DB sessions
- Metrics exported on `/metrics`
- Alembic migrations in `migrations/`
- Tests mirror the `core/` structure
- README.md updated as each iteration adds new capabilities

## Dev Workflow

```bash
# Start everything
docker compose up -d

# Run migrations
alembic upgrade head

# Run tests
pytest

# View logs
docker compose logs -f api
```

## Iteration Plan

1. FastAPI + Docker — REST API, SQLAlchemy models, Alembic, PostgreSQL via Compose
2. Observability — structured logs, /metrics, Prometheus + Grafana, OpenTelemetry tracing
3. Kubernetes — manifests/Helm charts, deploy on kind
4. Job Scheduling (Airflow) — batch re-indexing, data retention DAGs
5. Event-Driven (Kafka) — async fingerprint processing pipeline
6. Advanced Scalability — HPA, Redis caching, read replicas, S3 audio storage, load testing

## Directory Layout (target)

```
shanano/
├── api/
│   ├── __init__.py
│   ├── main.py              # FastAPI app factory
│   ├── deps.py              # DI (DB sessions, etc.)
│   └── routes/
│       ├── songs.py
│       └── match.py
├── core/
│   ├── __init__.py
│   ├── models.py            # SQLAlchemy models
│   ├── schemas.py            # Pydantic schemas
│   ├── fingerprint.py        # hashing logic
│   ├── pipeline.py           # AudioFingerprintPipeline
│   ├── song_service.py
│   └── match_service.py
├── infra/
│   ├── Dockerfile
│   ├── docker-compose.yml
│   ├── k8s/
│   └── helm/
├── observability/
│   ├── prometheus/
│   └── grafana/
├── airflow/
│   └── dags/
├── kafka/
│   ├── schemas/
│   └── docker-compose.kafka.yml
├── tests/
│   ├── unit/
│   └── integration/
├── audio_processing/         # existing DSP modules
├── controllers/              # existing (will migrate to core/)
├── data/                     # existing sample audio
├── AGENTS.md
├── config.py
├── requirements.txt
├── alembic.ini
├── migrations/
└── pyproject.toml
```
