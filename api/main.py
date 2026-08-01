import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import Response
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
from sqlalchemy import select, func

from core.database import engine, async_session
from core.logging import setup_logging, get_logger
from core.models import Base, ProcessingStatus, Song
from core.metrics import (
    http_requests,
    http_request_duration,
    songs_by_status,
)
from api.routes import auth, songs, match
from core.user_service import seed_users

setup_logging("api")
logger = get_logger("api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with async_session() as db:
        created = await seed_users(db)
        if created:
            logger.info("seeded bootstrap users", created=created)
    yield
    await engine.dispose()


app = FastAPI(title="Shanano", version="0.1.0", lifespan=lifespan)

app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(songs.router, prefix="/songs", tags=["songs"])
app.include_router(match.router, prefix="/match", tags=["match"])


@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    start = time.monotonic()
    response: Response = await call_next(request)
    duration = time.monotonic() - start
    http_requests.labels(
        method=request.method,
        endpoint=request.url.path,
        status_code=response.status_code,
    ).inc()
    http_request_duration.labels(
        method=request.method,
        endpoint=request.url.path,
    ).observe(duration)
    return response


@app.get("/metrics")
async def metrics():
    async with async_session() as db:
        for status in ProcessingStatus:
            count_result = await db.execute(
                select(func.count(Song.id)).where(Song.status == status)
            )
            count = count_result.scalar() or 0
            songs_by_status.labels(status=status.value).set(count)

    data = generate_latest()
    return Response(content=data, media_type=CONTENT_TYPE_LATEST)


@app.get("/health")
async def health():
    return {"status": "ok"}
