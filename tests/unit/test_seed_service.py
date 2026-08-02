"""Unit tests for the portable seed dump/restore service.

Uses file-based SQLite so dump and load run against a real, persistent DB
(the way the demo does) rather than an in-memory one.
"""
import json
import tarfile

import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from core.models import Base, Fingerprint, ProcessingStatus, Song
from core.seed_service import SEED_SCHEMA_VERSION, dump_seed, load_seed


@pytest_asyncio.fixture
async def db_factory(tmp_path):
    """Build fresh file-backed engines per test."""

    async def _make(name: str):
        engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/{name}.db")
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        return engine, maker

    return _make


async def _insert_catalog(maker, upload_dir, songs=(("song-a.flac", "Artist A"), ("song-b.ogg", "Artist B"))):
    async with maker() as session:
        created = []
        for idx, (file_name, artist) in enumerate(songs, start=1):
            song = Song(
                id=idx,
                name=f"Song {idx}",
                status=ProcessingStatus.completed,
                file_path=f"{upload_dir}/{file_name}",
                artist=artist,
                album=f"Album {idx}",
                year=1990 + idx,
                genre="rock",
                cover_art_url=f"https://archive.org/services/img/{idx}",
                source="internet_archive",
                source_url=f"https://archive.org/details/{idx}",
            )
            session.add(song)
            await session.flush()
            for h in (f"hash-{idx}-a", f"hash-{idx}-b"):
                session.add(
                    Fingerprint(
                        hash=h,
                        song_id=song.id,
                        anchor_time=10 + idx,
                        anchor_freq=100 + idx,
                        target_time=20 + idx,
                        target_freq=200 + idx,
                    )
                )
            created.append(song)
        await session.commit()
        return created


async def test_dump_and_load_roundtrip(db_factory, tmp_path):
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()
    (upload_dir / "song-a.flac").write_bytes(b"audio-a")
    (upload_dir / "song-b.ogg").write_bytes(b"audio-b")

    engine, maker = await db_factory("source")
    await _insert_catalog(maker, str(upload_dir))

    seed_path = tmp_path / "seed.tar.gz"
    async with maker() as session:
        await dump_seed(session, out_path=str(seed_path), upload_dir=str(upload_dir))

    assert seed_path.is_file()

    with tarfile.open(seed_path, "r:gz") as tar:
        names = tar.getnames()
        assert "manifest.json" in names
        assert "songs.json" in names
        assert "fingerprints.json" in names
        assert "audio/song-a.flac" in names
        assert "audio/song-b.ogg" in names

        manifest = json.loads(tar.extractfile("manifest.json").read())
        assert manifest["schema_version"] == SEED_SCHEMA_VERSION
        assert manifest["songs"] == 2
        assert manifest["fingerprints"] == 4

    await engine.dispose()

    # Restore into a fresh DB.
    restore_uploads = tmp_path / "restore_uploads"
    engine2, maker2 = await db_factory("dest")
    async with maker2() as session:
        summary = await load_seed(session, str(seed_path), upload_dir=str(restore_uploads))
    assert summary == {"songs": 2, "fingerprints": 4, "audio": 2}

    assert (restore_uploads / "song-a.flac").read_bytes() == b"audio-a"

    async with maker2() as session:
        songs = (await session.execute(select(Song).order_by(Song.id))).scalars().all()
        assert len(songs) == 2
        assert songs[0].name == "Song 1"
        assert songs[0].artist == "Artist A"
        assert songs[0].status == ProcessingStatus.completed
        assert songs[0].file_path == str(restore_uploads / "song-a.flac")

        fps = (await session.execute(select(Fingerprint).order_by(Fingerprint.song_id))).scalars().all()
        assert len(fps) == 4
        assert {fp.hash for fp in fps} == {"hash-1-a", "hash-1-b", "hash-2-a", "hash-2-b"}
        assert all(fp.song_id in (1, 2) for fp in fps)
    await engine2.dispose()


async def test_load_is_idempotent(db_factory, tmp_path):
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()
    (upload_dir / "song-a.flac").write_bytes(b"audio-a")

    engine, maker = await db_factory("source")
    await _insert_catalog(maker, str(upload_dir), songs=(("song-a.flac", "Artist A"),))
    seed_path = tmp_path / "seed.tar.gz"
    async with maker() as session:
        await dump_seed(session, out_path=str(seed_path), upload_dir=str(upload_dir))
    await engine.dispose()

    engine2, maker2 = await db_factory("dest")
    for _ in range(2):
        async with maker2() as session:
            await load_seed(session, str(seed_path), upload_dir=str(upload_dir))
        async with maker2() as session:
            songs = (await session.execute(select(Song))).scalars().all()
            fps = (await session.execute(select(Fingerprint))).scalars().all()
            assert len(songs) == 1
            assert len(fps) == 2
    await engine2.dispose()


async def test_dump_skips_missing_audio(db_factory, tmp_path):
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()
    engine, maker = await db_factory("source")
    # file_path points at a file that does not exist on disk
    await _insert_catalog(maker, str(upload_dir), songs=(("missing.flac", "Ghost"),))

    seed_path = tmp_path / "seed.tar.gz"
    async with maker() as session:
        await dump_seed(session, out_path=str(seed_path), upload_dir=str(upload_dir))

    with tarfile.open(seed_path, "r:gz") as tar:
        names = tar.getnames()
        assert "songs.json" in names
        assert not any(n.startswith("audio/") for n in names)
    await engine.dispose()


async def test_load_rejects_unsupported_schema(db_factory, tmp_path):
    seed_path = tmp_path / "bad.tar.gz"
    with tarfile.open(seed_path, "w:gz") as tar:
        payload = json.dumps({"schema_version": 99}).encode()
        info = tarfile.TarInfo("manifest.json")
        info.size = len(payload)
        tar.addfile(info, __import__("io").BytesIO(payload))

    engine, maker = await db_factory("dest")
    async with maker() as session:
        try:
            await load_seed(session, str(seed_path))
            raise AssertionError("expected ValueError")
        except ValueError as exc:
            assert "schema_version" in str(exc)
    await engine.dispose()


async def test_dump_default_path_uses_seed_dir(db_factory, tmp_path):
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()
    engine, maker = await db_factory("source")
    await _insert_catalog(maker, str(upload_dir), songs=(("song-a.flac", "A"),))

    seed_dir = tmp_path / "seeds"
    async with maker() as session:
        path = await dump_seed(session, seed_dir=str(seed_dir), upload_dir=str(upload_dir))
    assert path.parent == seed_dir
    assert path.name.startswith("shanano_seed_")
    assert path.name.endswith(".tar.gz")
    assert path.is_file()
    await engine.dispose()
