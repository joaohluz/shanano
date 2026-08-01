from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_current_user, get_db
from core.models import User
from core.schemas import MatchResultOut

router = APIRouter()


@router.post("/", response_model=MatchResultOut)
async def match_audio(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    if not file.filename or not file.filename.endswith(".wav"):
        raise HTTPException(status_code=400, detail="Only WAV files are supported")

    raise HTTPException(status_code=501, detail="Matching not yet implemented")
