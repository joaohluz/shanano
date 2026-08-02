import tempfile
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_current_user, get_db
from audio_processing.audio import load_audio
from audio_pipeline import AudioFingerprintPipeline
from config import SUPPORTED_AUDIO_EXTENSIONS
from core.logging import get_logger
from core.match_service import NoMatchFoundError, match_audio
from core.models import User
from core.schemas import MatchResultOut

router = APIRouter()
pipeline = AudioFingerprintPipeline()
logger = get_logger("match")


@router.post("/", response_model=MatchResultOut)
async def match_audio_endpoint(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    """Fingerprint the uploaded audio and return the best catalog match."""
    filename = file.filename or ""
    ext = Path(filename).suffix.lower()
    if ext not in SUPPORTED_AUDIO_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Unsupported audio format")

    tmp_path: Optional[Path] = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
            tmp.write(await file.read())
            tmp_path = Path(tmp.name)

        try:
            y, sr = load_audio(tmp_path)
            fingerprints = pipeline.run(y)
        except Exception:
            logger.warning("failed to decode or fingerprint audio", filename=filename)
            raise HTTPException(status_code=400, detail="Could not decode audio file")

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
    finally:
        if tmp_path is not None:
            tmp_path.unlink(missing_ok=True)
