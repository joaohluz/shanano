import asyncio
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import async_session
from core.models import ProcessingStatus, Song
from core.song_service import process_song

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("worker")

POLL_INTERVAL = 5


async def poll_pending_songs(db: AsyncSession) -> list[Song]:
    result = await db.execute(
        select(Song).where(Song.status == ProcessingStatus.pending)
    )
    return list(result.scalars().all())


async def run_worker():
    logger.info("Worker started, polling every %ds", POLL_INTERVAL)
    while True:
        try:
            async with async_session() as db:
                pending = await poll_pending_songs(db)
                for song in pending:
                    logger.info("Processing song %d: %s", song.id, song.name)
                    try:
                        await process_song(song.id, db)
                        await db.commit()
                        logger.info("Song %d completed", song.id)
                    except Exception as exc:
                        await db.rollback()
                        logger.error("Song %d failed: %s", song.id, exc)
        except Exception as exc:
            logger.error("Worker error: %s", exc)

        await asyncio.sleep(POLL_INTERVAL)


def main():
    asyncio.run(run_worker())


if __name__ == "__main__":
    main()
