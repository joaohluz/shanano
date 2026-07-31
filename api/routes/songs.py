import aiofiles
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_db
from config import UPLOAD_DIR
from core.models import Fingerprint, Song
from core.schemas import SongOut, SongListOut

router = APIRouter()


@router.get("/", response_model=list[SongListOut])
async def list_songs(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(
            Song.id,
            Song.name,
            Song.status,
            func.count(Fingerprint.hash).label("fingerprint_count"),
        )
        .outerjoin(Fingerprint, Song.id == Fingerprint.song_id)
        .group_by(Song.id)
    )
    rows = result.all()
    return [
        SongListOut(
            id=row.id, name=row.name, status=row.status,
            fingerprint_count=row.fingerprint_count,
        )
        for row in rows
    ]


@router.get("/{song_id}", response_model=SongOut)
async def get_song(song_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Song).where(Song.id == song_id))
    song = result.scalar_one_or_none()
    if not song:
        raise HTTPException(status_code=404, detail="Song not found")
    return song


@router.post("/", response_model=SongOut, status_code=201)
async def add_song(file: UploadFile = File(...), db: AsyncSession = Depends(get_db)):
    if not file.filename or not file.filename.endswith(".wav"):
        raise HTTPException(status_code=400, detail="Only WAV files are supported")

    upload_dir = Path(UPLOAD_DIR)
    upload_dir.mkdir(parents=True, exist_ok=True)
    file_path = upload_dir / file.filename

    async with aiofiles.open(file_path, "wb") as f:
        content = await file.read()
        await f.write(content)

    song = Song(name=file.filename, file_path=str(file_path))
    db.add(song)
    await db.flush()

    return SongOut(id=song.id, name=song.name, status=song.status)


@router.delete("/{song_id}", status_code=204)
async def delete_song(song_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Song).where(Song.id == song_id))
    song = result.scalar_one_or_none()
    if not song:
        raise HTTPException(status_code=404, detail="Song not found")
    await db.delete(song)
