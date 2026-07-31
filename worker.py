import asyncio
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from threading import Thread

from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import async_session
from core.logging import setup_logging, get_logger
from core.models import ProcessingStatus, Song
from core.metrics import (
    songs_processed,
    processing_duration,
    worker_poll_cycles,
    worker_poll_duration,
    songs_by_status,
)
from core.song_service import process_song

setup_logging("worker")
logger = get_logger("worker")

POLL_INTERVAL = 5
METRICS_PORT = 8001


class MetricsHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/metrics":
            data = generate_latest()
            self.send_response(200)
            self.send_header("Content-Type", CONTENT_TYPE_LATEST)
            self.end_headers()
            self.wfile.write(data)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, fmt, *args):
        logger.debug("http log", fmt=fmt, args=args)


def start_metrics_server():
    server = HTTPServer(("0.0.0.0", METRICS_PORT), MetricsHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    logger.info("metrics server started", port=METRICS_PORT)


async def poll_pending_songs(db: AsyncSession) -> list[Song]:
    result = await db.execute(
        select(Song).where(Song.status == ProcessingStatus.pending)
    )
    return list(result.scalars().all())


async def update_songs_by_status_gauge(db: AsyncSession):
    for status in ProcessingStatus:
        count_result = await db.execute(
            select(Song.id).where(Song.status == status)
        )
        count = len(count_result.scalars().all())
        songs_by_status.labels(status=status.value).set(count)


async def run_worker():
    logger.info("worker started", poll_interval=POLL_INTERVAL)
    while True:
        poll_start = time.monotonic()
        try:
            async with async_session() as db:
                pending = await poll_pending_songs(db)
                if pending:
                    logger.info("found pending songs", count=len(pending))
                for song in pending:
                    logger.info("processing song", song_id=song.id, name=song.name)
                    proc_start = time.monotonic()
                    try:
                        await process_song(song.id, db)
                        await db.commit()
                        proc_dur = time.monotonic() - proc_start
                        processing_duration.observe(proc_dur)
                        songs_processed.labels(status="completed").inc()
                        logger.info(
                            "song completed",
                            song_id=song.id,
                            duration_seconds=round(proc_dur, 3),
                        )
                    except Exception as exc:
                        await db.rollback()
                        proc_dur = time.monotonic() - proc_start
                        processing_duration.observe(proc_dur)
                        songs_processed.labels(status="failed").inc()
                        logger.error(
                            "song failed",
                            song_id=song.id,
                            error=str(exc),
                            duration_seconds=round(proc_dur, 3),
                        )
                await update_songs_by_status_gauge(db)
        except Exception as exc:
            logger.error("worker error", error=str(exc))

        poll_duration = time.monotonic() - poll_start
        worker_poll_duration.observe(poll_duration)
        worker_poll_cycles.inc()

        await asyncio.sleep(POLL_INTERVAL)


def main():
    start_metrics_server()
    asyncio.run(run_worker())


if __name__ == "__main__":
    main()
