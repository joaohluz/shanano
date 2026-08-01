from typing import Optional

from pydantic import BaseModel

from core.models import ProcessingStatus


class SongOut(BaseModel):
    id: int
    name: str
    status: ProcessingStatus
    artist: Optional[str] = None
    album: Optional[str] = None
    year: Optional[int] = None
    genre: Optional[str] = None
    cover_art_url: Optional[str] = None
    source: Optional[str] = None
    source_url: Optional[str] = None

    model_config = {"from_attributes": True}


class SongListOut(BaseModel):
    id: int
    name: str
    status: ProcessingStatus
    fingerprint_count: int
    artist: Optional[str] = None
    album: Optional[str] = None
    year: Optional[int] = None
    genre: Optional[str] = None
    cover_art_url: Optional[str] = None
    source: Optional[str] = None
    source_url: Optional[str] = None


class MatchResultOut(BaseModel):
    song_name: str
    score: int
