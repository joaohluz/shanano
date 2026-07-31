from pydantic import BaseModel

from core.models import ProcessingStatus


class SongOut(BaseModel):
    id: int
    name: str
    status: ProcessingStatus

    model_config = {"from_attributes": True}


class SongListOut(BaseModel):
    id: int
    name: str
    status: ProcessingStatus
    fingerprint_count: int


class MatchResultOut(BaseModel):
    song_name: str
    score: int
