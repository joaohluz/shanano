import io
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_db
from audio_processing.audio import load_audio
from audio_pipeline import AudioFingerprintPipeline
from config import SUPPORTED_AUDIO_EXTENSIONS
from core.logging import get_logger
from core.match_service import NoMatchFoundError, match_audio
from core.schemas import MatchResultOut

router = APIRouter()
pipeline = AudioFingerprintPipeline()
logger = get_logger("match")


@router.post("/", response_model=MatchResultOut)
async def match_audio_endpoint(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    """Fingerprint the uploaded audio and return the best catalog match.

    Public (no auth): the webapp records audio from a mic and matches it
    anonymously (see docs/webapp.md).
    """
    filename = file.filename or ""
    ext = Path(filename).suffix.lower()
    if ext not in SUPPORTED_AUDIO_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Unsupported audio format")

    # The client always sends WAV (ADR-0001), so decode from an in-memory
    # buffer instead of spooling the upload to a named temp file.
    buf = io.BytesIO(await file.read())
    buf.seek(0)
    try:
        y, sr = load_audio(buf)
        fingerprints = pipeline.run(y)
    except Exception:
        logger.warning("failed to decode or fingerprint audio", filename=filename)
        raise HTTPException(status_code=400, detail="Could not decode audio file")

    try:
        song, score, confidence = await match_audio(db, fingerprints)
        return MatchResultOut(
            song_name=song.name,
            score=score,
            id=song.id,
            status=song.status,
            artist=song.artist,
            album=song.album,
            year=song.year,
            genre=song.genre,
            cover_art_url=song.cover_art_url,
            source=song.source,
            source_url=song.source_url,
            confidence=confidence,
        )
    except NoMatchFoundError:
        raise HTTPException(status_code=404, detail="No match found")
