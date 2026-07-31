from prometheus_client import Counter, Histogram, Gauge

songs_uploaded = Counter(
    "shanano_songs_uploaded_total",
    "Total songs uploaded",
)

songs_processed = Counter(
    "shanano_songs_processed_total",
    "Total songs processed by worker",
    ["status"],
)

processing_duration = Histogram(
    "shanano_processing_duration_seconds",
    "Time spent processing a song",
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0, 120.0],
)

songs_by_status = Gauge(
    "shanano_songs_by_status",
    "Current count of songs by processing status",
    ["status"],
)

http_requests = Counter(
    "shanano_http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status_code"],
)

http_request_duration = Histogram(
    "shanano_http_request_duration_seconds",
    "HTTP request duration",
    ["method", "endpoint"],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0],
)

worker_poll_cycles = Counter(
    "shanano_worker_poll_cycles_total",
    "Total worker poll cycles",
)

worker_poll_duration = Histogram(
    "shanano_worker_poll_duration_seconds",
    "Duration of a single worker poll cycle",
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0],
)
