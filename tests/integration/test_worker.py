import pytest
from sqlalchemy import select

from core.models import ProcessingStatus


class TestPollPendingSongs:
    async def test_returns_only_pending_songs(self, db_engine, db_session):
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
        from core.models import Song
        from worker import poll_pending_songs

        maker = async_sessionmaker(
            db_engine, class_=AsyncSession, expire_on_commit=False
        )

        async with maker() as session:
            session.add_all([
                Song(name="pending1.wav", status=ProcessingStatus.pending),
                Song(name="completed.wav", status=ProcessingStatus.completed),
                Song(name="pending2.wav", status=ProcessingStatus.pending),
                Song(name="failed.wav", status=ProcessingStatus.failed),
            ])
            await session.commit()

        async with maker() as session:
            pending = await poll_pending_songs(session)
            names = [s.name for s in pending]
            assert "pending1.wav" in names
            assert "pending2.wav" in names
            assert "completed.wav" not in names
            assert "failed.wav" not in names

    async def test_returns_empty_when_none_pending(self, db_engine):
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
        from core.models import Song
        from worker import poll_pending_songs

        maker = async_sessionmaker(
            db_engine, class_=AsyncSession, expire_on_commit=False
        )
        async with maker() as session:
            session.add(Song(name="done.wav", status=ProcessingStatus.completed))
            await session.commit()

        async with maker() as session:
            pending = await poll_pending_songs(session)
            assert pending == []

    async def test_returns_empty_list_when_no_songs(self, db_engine):
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
        from worker import poll_pending_songs

        maker = async_sessionmaker(
            db_engine, class_=AsyncSession, expire_on_commit=False
        )
        async with maker() as session:
            pending = await poll_pending_songs(session)
            assert pending == []


class TestWorkerIntegration:
    async def test_worker_processes_pending_songs(self, db_engine, monkeypatch):
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
        from core.models import Song, ProcessingStatus

        maker = async_sessionmaker(
            db_engine, class_=AsyncSession, expire_on_commit=False
        )
        async with maker() as session:
            song = Song(name="worker_test.wav", file_path="/fake/path.wav")
            session.add(song)
            await session.commit()
            song_id = song.id

        from unittest.mock import patch
        import numpy as np

        fake_audio = np.sin(np.linspace(0, 2 * np.pi * 440 * 2, 44100))

        from worker import poll_pending_songs
        pending = await poll_pending_songs(
            async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)()
        )

        assert any(s.id == song_id for s in pending)
