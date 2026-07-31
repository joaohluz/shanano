from pydantic import BaseModel


class SongOut(BaseModel):
    id: int
    name: str

    model_config = {"from_attributes": True}


class SongListOut(BaseModel):
    id: int
    name: str
    fingerprint_count: int


class MatchResultOut(BaseModel):
    song_name: str
    score: int
