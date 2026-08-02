from pydantic import ValidationError
import pytest

from core.schemas import SongOut, SongListOut, MatchResultOut
from core.models import ProcessingStatus


class TestSongOut:
    def test_create_valid(self):
        song = SongOut(id=1, name="test.wav", status=ProcessingStatus.pending)
        assert song.id == 1
        assert song.name == "test.wav"
        assert song.status == ProcessingStatus.pending

    def test_from_attributes_enabled(self):
        assert SongOut.model_config.get("from_attributes") is True

    def test_rejects_invalid_status(self):
        with pytest.raises(ValidationError):
            SongOut(id=1, name="test.wav", status="invalid_status")

    def test_rejects_missing_id(self):
        with pytest.raises(ValidationError):
            SongOut(name="test.wav", status=ProcessingStatus.pending)


class TestSongListOut:
    def test_create_valid(self):
        song = SongListOut(
            id=1, name="test.wav", status=ProcessingStatus.completed, fingerprint_count=42
        )
        assert song.fingerprint_count == 42

    def test_fingerprint_count_defaults_to_zero(self):
        song = SongListOut(
            id=1, name="test.wav", status=ProcessingStatus.pending, fingerprint_count=0
        )
        assert song.fingerprint_count == 0

class TestMatchResultOut:
    def test_create_valid(self):
        result = MatchResultOut(song_name="test.wav", score=95)
        assert result.song_name == "test.wav"
        assert result.score == 95

    def test_accepts_any_integer_score(self):
        result = MatchResultOut(song_name="test.wav", score=-1)
        assert result.score == -1
