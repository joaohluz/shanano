from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from audio_processing.audio import load_audio
from audio_pipeline import AudioFingerprintPipeline
from core.logging import get_logger
from core.models import Fingerprint, ProcessingStatus, Song

pipeline = AudioFingerprintPipeline()
logger = get_logger("song_service")


async def process_song(song_id: int, db: AsyncSession) -> None:
    result = await db.execute(select(Song).where(Song.id == song_id))
    song = result.scalar_one_or_none()
    if not song or not song.file_path:
        logger.warning("song not found or missing file_path", song_id=song_id)
        return

    song.status = ProcessingStatus.processing
    await db.flush()

    try:
        y, sr = load_audio(song.file_path)
        fingerprint_count_before = (
            await db.execute(
                select(Fingerprint).where(Fingerprint.song_id == song.id)
            )
        ).scalar()
        logger.info(
            "audio loaded",
            song_id=song.id,
            sample_rate=sr,
            samples=len(y),
        )

        fingerprints = pipeline.run(y)

        seen = set()
        for f in fingerprints:
            h, anchor_time, anchor_freq, target_time, target_freq = f
            if h in seen:
                continue
            seen.add(h)
            fp = Fingerprint(
                hash=h,
                song_id=song.id,
                anchor_time=int(anchor_time),
                anchor_freq=int(anchor_freq),
                target_time=int(target_time),
                target_freq=int(target_freq),
            )
            db.add(fp)

        song.status = ProcessingStatus.completed
        logger.info(
            "fingerprints generated",
            song_id=song.id,
            fingerprint_count=len(seen),
        )
    except Exception:
        song.status = ProcessingStatus.failed
        logger.error("fingerprinting failed", song_id=song.id)
        raise


async def process_pending_songs(db: AsyncSession) -> tuple[int, int]:
    """One-shot: fingerprint every pending song. Returns (completed, failed).

    Used by the seed pipeline (``seed.py process``) so the catalog can be
    processed in a single run instead of leaving a long-lived worker polling.
    """
    result = await db.execute(
        select(Song)
        .where(Song.status == ProcessingStatus.pending)
        .order_by(Song.id)
    )
    pending = list(result.scalars().all())
    completed = failed = 0
    for song in pending:
        # Snapshot before processing: rollback() expires the ORM objects, so
        # accessing attributes afterwards would trigger a lazy reload.
        song_id = song.id
        song_name = song.name
        try:
            await process_song(song_id, db)
            await db.commit()
            completed += 1
        except Exception as exc:
            await db.rollback()
            failed += 1
            logger.error(
                "song failed",
                song_id=song_id,
                name=song_name,
                error=str(exc),
            )
    return completed, failed
