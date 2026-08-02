import io

import numpy as np
import soundfile as sf
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from audio_processing.audio import load_audio
from audio_pipeline import AudioFingerprintPipeline
from core.models import Fingerprint, ProcessingStatus, Song

SAMPLE_RATE = 22050


def _synthetic_audio(duration_seconds: float) -> np.ndarray:
    """A deterministic multi-tone signal with enough spectral peaks to fingerprint."""
    t = np.arange(int(duration_seconds * SAMPLE_RATE)) / SAMPLE_RATE
    return (
        0.5 * np.sin(2 * np.pi * 400 * t)
        + 0.3 * np.sin(2 * np.pi * 800 * t)
        + 0.2 * np.sin(2 * np.pi * 1600 * t)
        + 0.15 * np.sin(2 * np.pi * 2400 * t)
        + 0.1 * np.sin(2 * np.pi * 100 * t * np.sin(2 * np.pi * 0.3 * t))
    )


def _write_wav(samples: np.ndarray, path) -> None:
    sf.write(str(path), samples, SAMPLE_RATE)


async def _seed_catalog_song(db_engine, samples: np.ndarray, name: str = "sample_full.wav") -> int:
    """Persist a catalog song + its fingerprints so a query clip can match it."""
    pipeline = AudioFingerprintPipeline()

    # Round-trip through a WAV buffer so fingerprints come from the exact
    # PCM quantization a query clip will pass through.
    buf = io.BytesIO()
    sf.write(buf, samples, SAMPLE_RATE, format="WAV")
    buf.seek(0)
    y, _ = load_audio(buf)

    maker = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as session:
        song = Song(
            name=name,
            status=ProcessingStatus.completed,
            artist="Test Artist",
            album="Test Album",
            year=2024,
            genre="electronic",
            cover_art_url="http://example.com/cover.jpg",
            source="test",
            source_url="http://example.com/song",
        )
        session.add(song)
        await session.flush()

        seen = set()
        for h, t1, f1, t2, f2 in pipeline.run(y):
            if h in seen:
                continue
            seen.add(h)
            session.add(
                Fingerprint(
                    hash=h,
                    song_id=song.id,
                    anchor_time=int(t1),
                    anchor_freq=int(f1),
                    target_time=int(t2),
                    target_freq=int(f2),
                )
            )
        await session.commit()
        return song.id


class TestMatchEndpoint:
    async def test_match_allows_anonymous(self, client):
        """POST /match/ is public (no auth): undecodable body → 400, not 401."""
        response = await client.post(
            "/match/",
            files={"file": ("test.wav", b"fake-wav-content", "audio/wav")},
        )
        assert response.status_code == 400
        assert "decode" in response.json()["detail"].lower()

    async def test_match_rejects_unsupported_format(self, client, auth_headers):
        response = await client.post(
            "/match/",
            files={"file": ("test.txt", b"content", "text/plain")},
            headers=auth_headers,
        )
        assert response.status_code == 400
        assert "Unsupported" in response.json()["detail"]

    async def test_match_accepts_mp3_extension(self, client, auth_headers):
        # mp3 is now an allowed extension; an undecodable body is a decode error (400),
        # not a "unsupported format" rejection.
        response = await client.post(
            "/match/",
            files={"file": ("test.mp3", b"not-a-real-mp3", "audio/mpeg")},
            headers=auth_headers,
        )
        assert response.status_code == 400
        assert "decode" in response.json()["detail"].lower()

    async def test_match_rejects_empty_filename(self, client, auth_headers):
        response = await client.post(
            "/match/",
            files={"file": ("", b"content", "audio/wav")},
            headers=auth_headers,
        )
        assert response.status_code == 422

    async def test_match_returns_no_match_for_unknown_audio(self, client, auth_headers, tmp_path):
        rng = np.random.default_rng(42)
        noise = rng.standard_normal(int(5.0 * SAMPLE_RATE))
        wav_path = tmp_path / "unknown.wav"
        _write_wav(noise, wav_path)
        with wav_path.open("rb") as f:
            response = await client.post(
                "/match/",
                files={"file": ("unknown.wav", f.read(), "audio/wav")},
                headers=auth_headers,
            )
        assert response.status_code == 404
        assert response.json()["detail"] == "No match found"

    async def test_match_decodes_from_in_memory_buffer(
        self, client, db_engine, auth_headers, tmp_path, monkeypatch
    ):
        """ADR-0001: a WAV query is decoded from an in-memory BytesIO, never a temp file."""
        import api.routes.match as match_route

        def assert_buffer(path):
            assert isinstance(path, io.BytesIO), f"expected BytesIO, got {type(path)}"
            return load_audio(path)

        monkeypatch.setattr(match_route, "load_audio", assert_buffer)

        full_audio = _synthetic_audio(8.0)
        song_id = await _seed_catalog_song(db_engine, full_audio)

        clip_audio = full_audio[: int(4.0 * SAMPLE_RATE)]
        clip_path = tmp_path / "clip.wav"
        _write_wav(clip_audio, clip_path)
        with clip_path.open("rb") as f:
            response = await client.post(
                "/match/",
                files={"file": ("clip.wav", f.read(), "audio/wav")},
                headers=auth_headers,
            )

        assert response.status_code == 200, response.text
        assert response.json()["id"] == song_id

    async def test_match_real_song(self, client, db_engine, auth_headers, tmp_path):
        """Fingerprint a known sample into the test DB, then match a clip of it."""
        full_audio = _synthetic_audio(8.0)
        song_id = await _seed_catalog_song(db_engine, full_audio)

        # Upload the first 4 seconds as a query clip and match it.
        clip_audio = full_audio[: int(4.0 * SAMPLE_RATE)]
        clip_path = tmp_path / "clip.wav"
        _write_wav(clip_audio, clip_path)
        with clip_path.open("rb") as f:
            response = await client.post(
                "/match/",
                files={"file": ("clip.wav", f.read(), "audio/wav")},
                headers=auth_headers,
            )

        assert response.status_code == 200, response.text
        data = response.json()
        assert data["song_name"] == "sample_full.wav"
        assert data["score"] > 0
        assert data["id"] == song_id
        assert data["status"] == "completed"
        assert data["artist"] == "Test Artist"
        assert data["album"] == "Test Album"
        assert data["year"] == 2024
        assert data["genre"] == "electronic"
        assert data["cover_art_url"] == "http://example.com/cover.jpg"
        assert data["source"] == "test"
        assert data["source_url"] == "http://example.com/song"
        assert data["confidence"] is not None
        assert 0 < data["confidence"] <= 1.0
