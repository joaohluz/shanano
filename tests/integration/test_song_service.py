import pytest
from unittest.mock import patch, AsyncMock
import numpy as np

from sqlalchemy import select

from core.models import ProcessingStatus


class TestProcessSong:
    async def test_processes_song_successfully(self, db_engine, db_session):
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
        from core.models import Song
        from core.song_service import process_song

        maker = async_sessionmaker(
            db_engine, class_=AsyncSession, expire_on_commit=False
        )
        async with maker() as session:
            song = Song(name="test.wav", file_path="/fake/path.wav")
            session.add(song)
            await session.commit()
            song_id = song.id

        fake_audio = np.sin(np.linspace(0, 2 * np.pi * 440 * 2, 44100))
        fake_sr = 22050

        with patch("core.song_service.load_audio", return_value=(fake_audio, fake_sr)):
            async with maker() as session:
                await process_song(song_id, session)
                await session.commit()

            async with maker() as session:
                result = await session.execute(select(Song).where(Song.id == song_id))
                updated = result.scalar_one()
                assert updated.status == ProcessingStatus.completed

                from core.models import Fingerprint
                fp_result = await session.execute(
                    select(Fingerprint).where(Fingerprint.song_id == song_id)
                )
                fingerprints = fp_result.scalars().all()
                assert len(fingerprints) > 0

    async def test_reverts_to_pending_on_error(self, db_engine):
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
        from core.models import Song, ProcessingStatus
        from core.song_service import process_song

        maker = async_sessionmaker(
            db_engine, class_=AsyncSession, expire_on_commit=False
        )
        async with maker() as session:
            song = Song(name="broken.wav", file_path="/fake/path.wav")
            session.add(song)
            await session.commit()
            song_id = song.id

        with patch(
            "core.song_service.load_audio",
            side_effect=RuntimeError("audio load failed"),
        ):
            async with maker() as session:
                with pytest.raises(RuntimeError, match="audio load failed"):
                    await process_song(song_id, session)
                await session.rollback()

            async with maker() as session:
                result = await session.execute(select(Song).where(Song.id == song_id))
                updated = result.scalar_one()
                assert updated.status == ProcessingStatus.pending

    async def test_skips_song_without_file_path(self, db_engine):
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
        from core.models import Song, ProcessingStatus
        from core.song_service import process_song

        maker = async_sessionmaker(
            db_engine, class_=AsyncSession, expire_on_commit=False
        )
        async with maker() as session:
            song = Song(name="nopath.wav")
            session.add(song)
            await session.commit()
            song_id = song.id

        async with maker() as session:
            await process_song(song_id, session)
            result = await session.execute(select(Song).where(Song.id == song_id))
            updated = result.scalar_one()
            assert updated.status == ProcessingStatus.pending

    async def test_skips_nonexistent_song(self, db_engine):
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
        from core.song_service import process_song

        maker = async_sessionmaker(
            db_engine, class_=AsyncSession, expire_on_commit=False
        )
        async with maker() as session:
            await process_song(9999, session)

    async def test_deduplicates_fingerprints(self, db_engine):
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
        from core.models import Song
        from core.song_service import process_song
        from unittest.mock import patch

        maker = async_sessionmaker(
            db_engine, class_=AsyncSession, expire_on_commit=False
        )
        async with maker() as session:
            song = Song(name="dedup.wav", file_path="/fake.wav")
            session.add(song)
            await session.commit()
            song_id = song.id

        fake_audio = np.sin(np.linspace(0, 2 * np.pi * 440 * 2, 44100))
        fake_sr = 22050

        with patch("core.song_service.load_audio", return_value=(fake_audio, fake_sr)):
            async with maker() as session:
                await process_song(song_id, session)
                await session.commit()

            async with maker() as session:
                from sqlalchemy import select, func
                from core.models import Fingerprint
                result = await session.execute(
                    select(func.count(Fingerprint.hash.distinct()))
                    .where(Fingerprint.song_id == song_id)
                )
                distinct_count = result.scalar()
                result_all = await session.execute(
                    select(Fingerprint).where(Fingerprint.song_id == song_id)
                )
                total_count = len(result_all.scalars().all())
                assert distinct_count == total_count


class TestPipelineSingleton:
    async def test_pipeline_is_singleton(self):
        from core.song_service import pipeline
        from audio_pipeline import AudioFingerprintPipeline
        assert isinstance(pipeline, AudioFingerprintPipeline)


class TestProcessPendingSongs:
    async def test_processes_all_pending_in_one_shot(self, db_engine):
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
        from core.models import Song, ProcessingStatus
        from core.song_service import process_pending_songs

        maker = async_sessionmaker(
            db_engine, class_=AsyncSession, expire_on_commit=False
        )
        async with maker() as session:
            session.add_all(
                [
                    Song(name="one.wav", file_path="/fake/one.wav"),
                    Song(name="two.wav", file_path="/fake/two.wav"),
                ]
            )
            await session.commit()

        fake_audio = np.sin(np.linspace(0, 2 * np.pi * 440 * 2, 44100))
        fake_sr = 22050
        with patch("core.song_service.load_audio", return_value=(fake_audio, fake_sr)):
            async with maker() as session:
                completed, failed = await process_pending_songs(session)

        assert (completed, failed) == (2, 0)

        async with maker() as session:
            result = await session.execute(select(Song).order_by(Song.id))
            songs = result.scalars().all()
            assert all(s.status == ProcessingStatus.completed for s in songs)

    async def test_returns_failed_count_for_broken_songs(self, db_engine):
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
        from core.models import Song, ProcessingStatus
        from core.song_service import process_pending_songs

        maker = async_sessionmaker(
            db_engine, class_=AsyncSession, expire_on_commit=False
        )
        async with maker() as session:
            session.add_all(
                [
                    Song(name="good.wav", file_path="/fake/good.wav"),
                    Song(name="bad.wav", file_path="/fake/bad.wav"),
                ]
            )
            await session.commit()

        fake_audio = np.sin(np.linspace(0, 2 * np.pi * 440 * 2, 44100))

        def fake_load(path):
            if path.endswith("bad.wav"):
                raise RuntimeError("decode failed")
            return fake_audio, 22050

        with patch("core.song_service.load_audio", side_effect=fake_load):
            async with maker() as session:
                completed, failed = await process_pending_songs(session)

        assert (completed, failed) == (1, 1)

        async with maker() as session:
            result = await session.execute(
                select(Song).order_by(Song.id)
            )
            songs = result.scalars().all()
            assert songs[0].status == ProcessingStatus.completed
            assert songs[1].status == ProcessingStatus.pending
