# Observability (Metrics + Logging)

Prometheus custom metrics and structured JSON logging so the system's health and
behavior are visible. This is what makes the "observable" part of the learning
project work.

## Flow

```mermaid
graph LR
    subgraph API (:8000)
        MW[http metrics middleware]
        M[/metrics endpoint/]
    end
    subgraph Worker (:8001)
        WPOLL[poll cycle metrics]
        WM[/metrics handler/]
    end
    subgraph Core
        LOG[structlog JSON<br/>ISO timestamps, service context]
        MET[core/metrics.py<br/>counters, histograms, gauges]
    end

    HTTP[HTTP request] --> MW --> MET
    PENDING[pending songs] --> WPOLL --> MET
    MW --> LOG
    WPOLL --> LOG

    PROM[Prometheus<br/>scrape :8000 & :8001 /metrics] --> M
    PROM --> WM
    M --> MET
    WM --> MET
    PROM --> GRAF[Grafana dashboard<br/>6 panels]
```

## Metrics (`core/metrics.py`)

| Metric | Type | Labels | Where it's updated |
|---|---|---|---|
| `shanano_songs_uploaded_total` | Counter | — | `POST /songs/` (`songs.py:78`) |
| `shanano_songs_processed_total` | Counter | `status` (completed/failed) | worker per song |
| `shanano_processing_duration_seconds` | Histogram | — | worker per song |
| `shanano_songs_by_status` | Gauge | `status` | recomputed on each `/metrics` scrape (API) and each poll (worker) |
| `shanano_http_requests_total` | Counter | `method`, `endpoint`, `status_code` | HTTP middleware |
| `shanano_http_request_duration_seconds` | Histogram | `method`, `endpoint` | HTTP middleware |
| `shanano_worker_poll_cycles_total` | Counter | — | worker poll loop |
| `shanano_worker_poll_duration_seconds` | Histogram | — | worker poll loop |

## How the pieces fit

- **HTTP middleware** (`api/main.py:43`) wraps every request: records method,
  path, status code, and duration via Prometheus client.
- **API `/metrics`** (`api/main.py:60`) first refreshes the `songs_by_status`
  gauge from the DB, then emits all registered metrics. Public — Prometheus needs
  no auth to scrape.
- **Worker metrics** (`worker.py`) — the worker isn't a web app, so it runs a
  tiny stdlib `HTTPServer` in a daemon thread on `:8001` serving `/metrics`. The
  poll loop records cycle count/duration and per-song processing metrics.
- **Logging** (`core/logging.py`) — structlog with ISO timestamps, logger name,
  level; JSON output when running under a server (plain console in dev shells).
  Each service calls `setup_logging("api"|"worker"|"loadgen"|...)` to tag its logs.
- **Prometheus** (`observability/prometheus/prometheus.yml`) scrapes `:8000` and
  `:8001` every 10 s.
- **Grafana** — auto-provisioned datasource + a 6-panel dashboard: songs
  uploaded, songs by status, processing rate, p99 duration, HTTP request rate,
  HTTP p99.

## Triggers

- A scrape of `/metrics` (API or worker) — recomputes the status gauge.
- Every HTTP request — middleware counters/histograms.
- Every worker poll cycle and every processed song — poll/processing metrics.

## Design choices

- **Standard Prometheus client + exporter model.** Custom metrics defined once in
  `core/metrics.py` and mutated at the point of the event (upload, process, poll)
  — no plumbing of state between services.
- **Gauge refreshed lazily on scrape.** `songs_by_status` is a DB query, so it's
  computed *at scrape time* rather than maintained incrementally — always correct,
  cheap at catalog scale.
- **Histograms over summaries** for durations → enables PromQL quantile queries
  (p99) in Grafana.
- **Structured logs everywhere.** JSON + ISO timestamps + service context make
  cross-service debugging greppable and feed tools like Loki later.
- **Worker exposes its own exporter** because it has no web framework — a 30-line
  stdlib HTTP server keeps the dependency footprint zero while still letting
  Prometheus see it.
