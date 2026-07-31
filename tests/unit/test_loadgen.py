import io
import random
import wave

import pytest

from loadgen import (
    ENDPOINT_WEIGHTS,
    LoadgenConfig,
    generate_chirp_wav,
    pick_endpoint,
    target_rps,
)


class TestTargetRps:
    def test_stays_within_bounds(self):
        for t in range(0, 1000, 7):
            rps = target_rps(t, 2.0, 20.0, 120.0)
            assert 2.0 <= rps <= 20.0

    def test_waves_between_peak_and_trough(self):
        rps = target_rps(0, 1.0, 21.0, 120.0)
        assert rps == pytest.approx(11.0)
        peak = target_rps(30.0, 1.0, 21.0, 120.0)
        assert peak == pytest.approx(21.0)
        trough = target_rps(90.0, 1.0, 21.0, 120.0)
        assert trough == pytest.approx(1.0)

    def test_repeats_after_full_period(self):
        start = target_rps(10.0, 1.0, 21.0, 120.0)
        after_period = target_rps(130.0, 1.0, 21.0, 120.0)
        assert start == pytest.approx(after_period)

    def test_flat_when_min_equals_max(self):
        assert target_rps(0, 5.0, 5.0, 120.0) == 5.0


class TestGenerateChirpWav:
    def test_returns_valid_wav_bytes(self):
        data = generate_chirp_wav(duration_seconds=2.0, sample_rate=8000)
        assert data[:4] == b"RIFF"
        assert data[8:12] == b"WAVE"
        with wave.open(io.BytesIO(data), "rb") as wav_file:
            assert wav_file.getframerate() == 8000
            assert wav_file.getnchannels() == 1
            assert wav_file.getsampwidth() == 2
            assert wav_file.getnframes() == 16000

    def test_different_durations_give_different_sizes(self):
        short = generate_chirp_wav(duration_seconds=2.0, sample_rate=8000)
        long = generate_chirp_wav(duration_seconds=4.0, sample_rate=8000)
        assert len(long) > len(short)


class TestPickEndpoint:
    def test_weights_sum_to_one(self):
        assert sum(weight for _, weight in ENDPOINT_WEIGHTS) == pytest.approx(1.0)

    def test_returns_valid_endpoint(self):
        rng = random.Random(42)
        seen = {pick_endpoint(rng, [1, 2, 3]) for _ in range(1000)}
        assert seen <= {"health", "list", "get", "upload", "delete", "match"}

    def test_song_dependent_endpoints_fall_back_to_list(self):
        rng = random.Random(7)
        for _ in range(200):
            endpoint = pick_endpoint(rng, [])
            assert endpoint != "get"
            assert endpoint != "delete"

    def test_upload_and_health_always_possible(self):
        rng = random.Random(1)
        endpoints = [pick_endpoint(rng, []) for _ in range(500)]
        assert "upload" in endpoints
        assert "health" in endpoints


class TestLoadgenConfigFromEnv:
    def test_defaults(self, monkeypatch):
        for var in (
            "LOADGEN_TARGET",
            "LOADGEN_WORKERS",
            "LOADGEN_MIN_RPS",
            "LOADGEN_MAX_RPS",
            "LOADGEN_WAVE_PERIOD",
            "LOADGEN_DURATION",
            "LOADGEN_SEED",
        ):
            monkeypatch.delenv(var, raising=False)
        cfg = LoadgenConfig.from_env()
        assert cfg.target == "http://localhost:8000"
        assert cfg.workers == 8
        assert cfg.min_rps == 1.0
        assert cfg.max_rps == 20.0
        assert cfg.wave_period == 120.0
        assert cfg.duration == 0.0
        assert cfg.seed is None

    def test_reads_env(self, monkeypatch):
        monkeypatch.setenv("LOADGEN_TARGET", "http://api:8000")
        monkeypatch.setenv("LOADGEN_WORKERS", "4")
        monkeypatch.setenv("LOADGEN_MAX_RPS", "50")
        monkeypatch.setenv("LOADGEN_SEED", "7")
        cfg = LoadgenConfig.from_env()
        assert cfg.target == "http://api:8000"
        assert cfg.workers == 4
        assert cfg.max_rps == 50.0
        assert cfg.seed == 7
