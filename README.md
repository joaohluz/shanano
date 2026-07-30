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

## Current Status (Iteration 1)

Core API infrastructure in progress. See the [iteration plan](AGENTS.md#iteration-plan) for what's next.

### What's set up

- **SQLAlchemy 2.x async models** (`core/models.py`) — `Song` and `Fingerprint` tables
- **Async database session** (`core/database.py`) — asyncpg engine with FastAPI-compatible `get_db` dependency
- **FastAPI** + **Alembic** — ready for routes and migrations
- **Docker Compose** — coming next (PostgreSQL + API containers)

## Dev Workflow

```bash
# 1. Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Start PostgreSQL + API (once Docker Compose is set up)
docker compose up -d

# 4. Run migrations
alembic upgrade head

# 5. Run tests
pytest

# 6. View logs
docker compose logs -f api
```

## CLI (original, still works)

The original CLI still works for local experiments with SQLite:

```bash
source .venv/bin/activate
python -m cli list
python -m cli add data/assets/clean_wavs/
python -m cli match
```

## Project Structure

```
shanano/
├── api/                    # FastAPI routes and app factory
├── core/                   # Business logic (models, services, pipeline)
├── infra/                  # Docker, K8s, Helm
├── observability/          # Grafana, Prometheus, OTel
├── airflow/                # DAG definitions
├── kafka/                  # Event schemas
├── tests/                  # Unit and integration tests
├── audio_processing/       # DSP modules (spectrogram, peaks, filtering)
├── controllers/            # Original CLI controllers (SQLite)
├── data/                   # Sample audio files
├── AGENTS.md               # Project context for AI assistants
├── config.py               # App-wide constants
└── requirements.txt
```

## Notebooks

Jupyter notebooks with detailed algorithm walkthroughs (from the original project):

- [`audio_fingerprinting_pipeline.ipynb`](audio_fingerprinting_pipeline.ipynb)
- [`Input_Audio_Pipeline.ipynb`](Input_Audio_Pipeline.ipynb)
- [`Input_Processing_Experiments.ipynb`](Input_Processing_Experiments.ipynb)
- [`perfect_match_histograms.ipynb`](perfect_match_histograms.ipynb)

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
