"""Fake user traffic generator for Shanano.

Simulates a population of users hitting the API so Prometheus metrics
visibly go up and down. The aggregate request rate follows a sine wave
between LOADGEN_MIN_RPS and LOADGEN_MAX_RPS over LOADGEN_WAVE_PERIOD
seconds, so dashboards show a breathing pattern instead of a flat line.

Endpoints exercised (weighted random mix):
    GET    /health        health checks
    GET    /songs/        browse catalog
    GET    /songs/{id}    song details
    POST   /songs/        upload a synthetic chirp WAV
    DELETE /songs/{id}    remove songs
    POST   /match/        match attempts against the catalog

Run standalone:
    python loadgen.py

Configuration via CLI flags or LOADGEN_* env vars (see --help).
"""

from __future__ import annotations

import argparse
import asyncio
import io
import math
import os
import random
import time
import wave
from collections import Counter
from dataclasses import dataclass

import httpx
import numpy as np

from core.logging import get_logger, setup_logging

setup_logging("loadgen")
logger = get_logger("loadgen")

REPORT_INTERVAL = 10.0
SAMPLE_RATE = 22050
UPLOAD_DURATIONS = (4.0, 8.0, 12.0)

ENDPOINT_WEIGHTS = [
    ("health", 0.30),
    ("list", 0.30),
    ("get", 0.15),
    ("upload", 0.10),
    ("delete", 0.10),
    ("match", 0.05),
]


@dataclass
class LoadgenConfig:
    target: str = "http://localhost:8000"
    workers: int = 8
    min_rps: float = 1.0
    max_rps: float = 20.0
    wave_period: float = 120.0
    duration: float = 0.0
    seed: int | None = None

    @classmethod
    def from_env(cls) -> "LoadgenConfig":
        return cls(
            target=os.getenv("LOADGEN_TARGET", "http://localhost:8000"),
            workers=int(os.getenv("LOADGEN_WORKERS", "8")),
            min_rps=float(os.getenv("LOADGEN_MIN_RPS", "1")),
            max_rps=float(os.getenv("LOADGEN_MAX_RPS", "20")),
            wave_period=float(os.getenv("LOADGEN_WAVE_PERIOD", "120")),
            duration=float(os.getenv("LOADGEN_DURATION", "0")),
            seed=int(os.getenv("LOADGEN_SEED", "0")) or None,
        )


def target_rps(t: float, min_rps: float, max_rps: float, period: float) -> float:
    """Aggregate requests/second at time t, oscillating like a sine wave."""
    midpoint = (min_rps + max_rps) / 2.0
    amplitude = (max_rps - min_rps) / 2.0
    return midpoint + amplitude * math.sin(2.0 * math.pi * t / period)


def generate_chirp_wav(duration_seconds: float = 8.0, sample_rate: int = SAMPLE_RATE) -> bytes:
    """Build a synthetic frequency-swept WAV file as bytes (no audio assets needed)."""
    n = int(duration_seconds * sample_rate)
    freq = np.linspace(300.0, 3000.0, n)
    phase = 2.0 * np.pi * np.cumsum(freq) / sample_rate
    y = 0.5 * np.sin(phase)
    pcm = (y * 32767.0).astype(np.int16)

    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(pcm.tobytes())
    return buffer.getvalue()


def pick_endpoint(rng: random.Random, known_song_ids: list[int]) -> str:
    """Pick a weighted-random endpoint, falling back to list when no songs exist."""
    r = rng.random()
    cumulative = 0.0
    for endpoint, weight in ENDPOINT_WEIGHTS:
        cumulative += weight
        if r <= cumulative:
            if endpoint in ("get", "delete") and not known_song_ids:
                return "list"
            return endpoint
    return "list"


class SongRegistry:
    """Thread-safe-ish registry of known song ids so get/delete target real rows."""

    def __init__(self) -> None:
        self._ids: list[int] = []
        self._lock = asyncio.Lock()

    async def ids(self) -> list[int]:
        async with self._lock:
            return list(self._ids)

    async def add(self, song_id: int) -> None:
        async with self._lock:
            if song_id not in self._ids:
                self._ids.append(song_id)

    async def discard(self, song_id: int) -> None:
        async with self._lock:
            if song_id in self._ids:
                self._ids.remove(song_id)

    async def refresh(self, song_ids: list[int]) -> None:
        async with self._lock:
            self._ids = song_ids


class Stats:
    """Request counters shared across workers."""

    def __init__(self) -> None:
        self._counts: Counter = Counter()
        self._lock = asyncio.Lock()

    async def record(self, endpoint: str) -> None:
        async with self._lock:
            self._counts[endpoint] += 1

    async def snapshot(self) -> dict[str, int]:
        async with self._lock:
            return dict(self._counts)


async def execute_request(
    client: httpx.AsyncClient,
    cfg: LoadgenConfig,
    rng: random.Random,
    registry: SongRegistry,
    wavs: list[bytes],
) -> tuple[str, int | None]:
    """Perform one request and return (endpoint, status_code or None on error)."""
    ids = await registry.ids()
    endpoint = pick_endpoint(rng, ids)
    url = f"{cfg.target}"

    try:
        if endpoint == "health":
            resp = await client.get(f"{url}/health")
        elif endpoint == "list":
            resp = await client.get(f"{url}/songs/")
            if resp.status_code == 200:
                await registry.refresh([row["id"] for row in resp.json()])
        elif endpoint == "get":
            resp = await client.get(f"{url}/songs/{rng.choice(ids)}")
        elif endpoint == "upload":
            wav = rng.choice(wavs)
            name = f"loadgen-{rng.randint(0, 10**9)}.wav"
            files = {"file": (name, wav, "audio/wav")}
            resp = await client.post(f"{url}/songs/", files=files)
            if resp.status_code == 201:
                await registry.add(resp.json()["id"])
        elif endpoint == "delete":
            song_id = rng.choice(ids)
            resp = await client.delete(f"{url}/songs/{song_id}")
            if resp.status_code == 204:
                await registry.discard(song_id)
        elif endpoint == "match":
            files = {"file": ("query.wav", rng.choice(wavs), "audio/wav")}
            resp = await client.post(f"{url}/match/", files=files)
        else:
            resp = await client.get(f"{url}/health")
    except httpx.HTTPError as exc:
        logger.warning("request failed", endpoint=endpoint, error=str(exc))
        return endpoint, None

    return endpoint, resp.status_code


async def worker(
    worker_id: int,
    client: httpx.AsyncClient,
    cfg: LoadgenConfig,
    rng: random.Random,
    registry: SongRegistry,
    wavs: list[bytes],
    stats: Stats,
    stop_event: asyncio.Event,
) -> None:
    logger.info("loadgen worker started", worker_id=worker_id)
    while not stop_event.is_set():
        endpoint, status = await execute_request(client, cfg, rng, registry, wavs)
        await stats.record(endpoint)
        if status is not None and status >= 400:
            logger.debug("request non-2xx", endpoint=endpoint, status=status)

        current_rps = target_rps(time.monotonic(), cfg.min_rps, cfg.max_rps, cfg.wave_period)
        delay = rng.uniform(0.5, 1.5) * cfg.workers / max(current_rps, 0.01)
        await asyncio.sleep(delay)


async def reporter(cfg: LoadgenConfig, stats: Stats, stop_event: asyncio.Event) -> None:
    previous = await stats.snapshot()
    while not stop_event.is_set():
        await asyncio.sleep(REPORT_INTERVAL)
        snapshot = await stats.snapshot()
        interval_counts = {
            endpoint: snapshot[endpoint] - previous.get(endpoint, 0)
            for endpoint in snapshot
        }
        previous = snapshot
        observed_rps = sum(interval_counts.values()) / REPORT_INTERVAL
        target = target_rps(time.monotonic(), cfg.min_rps, cfg.max_rps, cfg.wave_period)
        logger.info(
            "loadgen stats",
            observed_rps=round(observed_rps, 2),
            target_rps=round(target, 2),
            requests=interval_counts,
        )


async def run(cfg: LoadgenConfig) -> None:
    rng = random.Random(cfg.seed)
    registry = SongRegistry()
    stats = Stats()
    stop_event = asyncio.Event()
    wavs = [generate_chirp_wav(d) for d in UPLOAD_DURATIONS]

    async with httpx.AsyncClient(timeout=30.0) as client:
        logger.info(
            "loadgen started",
            target=cfg.target,
            workers=cfg.workers,
            min_rps=cfg.min_rps,
            max_rps=cfg.max_rps,
            wave_period=cfg.wave_period,
        )
        tasks = [
            asyncio.create_task(
                worker(i, client, cfg, rng, registry, wavs, stats, stop_event)
            )
            for i in range(cfg.workers)
        ]
        report_task = asyncio.create_task(reporter(cfg, stats, stop_event))

        if cfg.duration > 0:
            await asyncio.sleep(cfg.duration)
            stop_event.set()
        else:
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                stop_event.set()

        await asyncio.gather(*tasks, return_exceptions=True)
        report_task.cancel()
        try:
            await report_task
        except asyncio.CancelledError:
            pass

    logger.info("loadgen stopped", total_requests=await stats.snapshot())


def parse_args() -> LoadgenConfig:
    parser = argparse.ArgumentParser(
        description="Generate fake user traffic against the Shanano API"
    )
    parser.add_argument("--target", default=None, help="API base URL (env LOADGEN_TARGET)")
    parser.add_argument("--workers", type=int, default=None, help="Virtual users (env LOADGEN_WORKERS)")
    parser.add_argument("--min-rps", type=float, default=None, help="Min aggregate req/s (env LOADGEN_MIN_RPS)")
    parser.add_argument("--max-rps", type=float, default=None, help="Peak aggregate req/s (env LOADGEN_MAX_RPS)")
    parser.add_argument("--wave-period", type=float, default=None, help="Seconds per wave (env LOADGEN_WAVE_PERIOD)")
    parser.add_argument("--duration", type=float, default=None, help="Run for N seconds, 0 = forever (env LOADGEN_DURATION)")
    parser.add_argument("--seed", type=int, default=None, help="Random seed (env LOADGEN_SEED)")
    args = parser.parse_args()

    cfg = LoadgenConfig.from_env()
    if args.target is not None:
        cfg.target = args.target
    if args.workers is not None:
        cfg.workers = args.workers
    if args.min_rps is not None:
        cfg.min_rps = args.min_rps
    if args.max_rps is not None:
        cfg.max_rps = args.max_rps
    if args.wave_period is not None:
        cfg.wave_period = args.wave_period
    if args.duration is not None:
        cfg.duration = args.duration
    if args.seed is not None:
        cfg.seed = args.seed
    return cfg


def main() -> None:
    cfg = parse_args()
    asyncio.run(run(cfg))


if __name__ == "__main__":
    main()
