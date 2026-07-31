from contextlib import asynccontextmanager

from fastapi import FastAPI

from core.models import Base
from core.database import engine
from api.routes import songs, match


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()


app = FastAPI(title="Shanano", version="0.1.0", lifespan=lifespan)

app.include_router(songs.router, prefix="/songs", tags=["songs"])
app.include_router(match.router, prefix="/match", tags=["match"])


@app.get("/health")
async def health():
    return {"status": "ok"}
