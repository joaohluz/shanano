"""Portable, compressed seed of the song catalog.

``dump_seed`` exports the songs and fingerprints tables — plus the audio files
the songs point at — into a single gzipped tarball; ``load_seed`` restores it
into a fresh database. The artifact is engine-agnostic (JSON, not SQL), so a
seed built on Postgres restores cleanly into the SQLite demo DB and vice
versa. It is the seed for the manual demo (see ``demo.md``) so matching works
fully offline: no Internet Archive access needed.

Layout::

    manifest.json         schema_version, created_at, row counts
    songs.json            [Song rows ...]
    fingerprints.json     [Fingerprint rows ...]
    audio/<basename>      the audio files referenced by songs

The seed pipeline (see ``seed.py``) is: link ingestion -> fingerprint
processing -> dump -> compress. ``load_seed`` is the restore half.
"""
import io
import json
import tarfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from config import UPLOAD_DIR
from core.logging import get_logger
from core.models import Fingerprint, Song

logger = get_logger("seed_service")

SEED_SCHEMA_VERSION = 1
SEED_DIR = Path("data/seed")

# Explicit column sets so a seed stays valid even if the models gain columns.
_SONG_FIELDS = (
    "id",
    "name",
    "status",
    "file_path",
    "artist",
    "album",
    "year",
    "genre",
    "cover_art_url",
    "source",
    "source_url",
)
_FINGERPRINT_FIELDS = (
    "hash",
    "song_id",
    "anchor_time",
    "anchor_freq",
    "target_time",
    "target_freq",
)


def default_seed_path(seed_dir: str = str(SEED_DIR)) -> Path:
    """``data/seed/shanano_seed_<UTC timestamp>.tar.gz``."""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return Path(seed_dir) / f"shanano_seed_{stamp}.tar.gz"


def _song_to_dict(song: Song) -> dict[str, Any]:
    return {field: getattr(song, field) for field in _SONG_FIELDS}


def _song_from_dict(data: dict[str, Any], upload_dir: str) -> dict[str, Any]:
    """Rebuild a Song row, normalizing ``file_path`` to the target upload dir."""
    row = {field: data.get(field) for field in _SONG_FIELDS}
    file_path = data.get("file_path")
    if file_path:
        row["file_path"] = str(Path(upload_dir) / Path(file_path).name)
    return row


def _add_bytes(tar: tarfile.TarFile, name: str, data: bytes) -> None:
    info = tarfile.TarInfo(name)
    info.size = len(data)
    tar.addfile(info, io.BytesIO(data))


def _read_tar(tar: tarfile.TarFile, name: str) -> str:
    member = tar.getmember(name)
    fh = tar.extractfile(member)
    if fh is None:
        raise ValueError(f"seed is missing {name}")
    return fh.read().decode("utf-8")


async def dump_seed(
    db: AsyncSession,
    out_path: Optional[str] = None,
    upload_dir: str = UPLOAD_DIR,
    seed_dir: str = str(SEED_DIR),
) -> Path:
    """Export songs + fingerprints (+ referenced audio) to a compressed seed.

    ``out_path`` defaults to ``data/seed/shanano_seed_<timestamp>.tar.gz``.
    Audio files referenced by ``file_path`` that are missing on disk are
    skipped with a warning (the seed still works, minus offline clips for
    those songs).
    """
    out_path = Path(out_path) if out_path else default_seed_path(seed_dir)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    songs_result = await db.execute(select(Song).order_by(Song.id))
    songs = list(songs_result.scalars().all())

    songs_json = json.dumps([_song_to_dict(s) for s in songs]).encode("utf-8")

    # Stream fingerprints so large catalogs don't all sit in memory at once.
    parts: list[str] = []
    count = 0
    stream = await db.stream(
        select(Fingerprint)
        .order_by(Fingerprint.song_id)
        .execution_options(yield_per=5000)
    )
    async for row in stream:
        fp = row[0]
        count += 1
        parts.append(json.dumps({f: getattr(fp, f) for f in _FINGERPRINT_FIELDS}))
    fingerprints_json = ("[" + ",".join(parts) + "]").encode("utf-8")

    manifest = {
        "schema_version": SEED_SCHEMA_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "songs": len(songs),
        "fingerprints": count,
    }

    with tarfile.open(out_path, "w:gz") as tar:
        _add_bytes(tar, "manifest.json", json.dumps(manifest).encode("utf-8"))
        _add_bytes(tar, "songs.json", songs_json)
        _add_bytes(tar, "fingerprints.json", fingerprints_json)
        for song in songs:
            if not song.file_path:
                continue
            src = Path(song.file_path)
            if not src.is_file():
                logger.warning("seed: audio file missing", file_path=song.file_path)
                continue
            tar.add(str(src), arcname=f"audio/{src.name}")

    logger.info(
        "seed dumped",
        path=str(out_path),
        songs=len(songs),
        fingerprints=count,
    )
    return out_path


async def load_seed(
    db: AsyncSession,
    seed_file: str,
    upload_dir: str = UPLOAD_DIR,
) -> dict[str, int]:
    """Restore a seed into the DB: songs + fingerprints, then audio files.

    Rebuilds the tables idempotently (delete existing songs/fingerprints,
    re-insert), so it works on a fresh DB or on a re-run. Audio files are
    written into ``upload_dir`` and ``file_path`` is normalized to point there.
    """
    seed_path = Path(seed_file)
    with tarfile.open(seed_path, "r:gz") as tar:
        manifest = json.loads(_read_tar(tar, "manifest.json"))
        if manifest.get("schema_version") != SEED_SCHEMA_VERSION:
            raise ValueError(
                "unsupported seed schema_version "
                f"{manifest.get('schema_version')} (expected {SEED_SCHEMA_VERSION})"
            )
        songs = json.loads(_read_tar(tar, "songs.json"))
        fingerprints = json.loads(_read_tar(tar, "fingerprints.json"))

        upload_path = Path(upload_dir)
        upload_path.mkdir(parents=True, exist_ok=True)
        audio_count = 0
        for member in tar.getmembers():
            if not member.name.startswith("audio/") or member.isdir():
                continue
            src = tar.extractfile(member)
            if src is None:
                continue
            with open(upload_path / Path(member.name).name, "wb") as fh:
                fh.write(src.read())
            audio_count += 1

    await db.execute(delete(Fingerprint))
    await db.execute(delete(Song))
    for data in songs:
        db.add(Song(**_song_from_dict(data, str(upload_path))))
    for fp in fingerprints:
        db.add(Fingerprint(**fp))
    await db.commit()

    logger.info(
        "seed loaded",
        seed=str(seed_path),
        songs=len(songs),
        fingerprints=len(fingerprints),
        audio=audio_count,
    )
    return {"songs": len(songs), "fingerprints": len(fingerprints), "audio": audio_count}
