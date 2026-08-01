from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from core.models import ProcessingStatus, UserRole


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


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=8, max_length=128)
    role: UserRole = UserRole.user


class UserOut(BaseModel):
    id: int
    username: str
    role: UserRole
    created_at: datetime

    model_config = {"from_attributes": True}


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
