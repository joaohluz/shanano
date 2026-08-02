import pytest

from core.match_service import (
    NoMatchFoundError,
    get_matching_fingerprints_in_song,
    match_audio,
    match_fingerprints,
)
from core.models import Fingerprint, ProcessingStatus, Song


def _add_fingerprint(db, song_id, hash_, anchor_time, anchor_freq=1, target_time=0, target_freq=2):
    db.add(
        Fingerprint(
            hash=hash_,
            song_id=song_id,
            anchor_time=anchor_time,
            anchor_freq=anchor_freq,
            target_time=target_time,
            target_freq=target_freq,
        )
    )


class TestMatchFingerprints:
    async def test_returns_none_with_empty_db(self, db_session):
        best_name, score, hist = await match_fingerprints(
            db_session,
            [("h1", 10, 1, 20, 2), ("h2", 11, 1, 21, 2)],
        )
        assert best_name is None
        assert score is None
        assert hist is None

    async def test_returns_none_without_candidates(self, db_session):
        best_name, score, hist = await match_fingerprints(
            db_session,
            [("nohash", 10, 1, 20, 2)],
        )
        assert best_name is None

    async def test_picks_song_with_highest_offset_vote(self, db_session):
        song_a = Song(name="song_a.wav")
        song_b = Song(name="song_b.wav")
        db_session.add_all([song_a, song_b])
        await db_session.flush()

        # Song A matches all three query hashes at a consistent offset (5).
        _add_fingerprint(db_session, song_a.id, "h1", anchor_time=15)
        _add_fingerprint(db_session, song_a.id, "h2", anchor_time=25)
        _add_fingerprint(db_session, song_a.id, "h3", anchor_time=35)
        # Song B matches one query hash, but at a different offset.
        _add_fingerprint(db_session, song_b.id, "h1", anchor_time=100)
        await db_session.flush()

        query_fps = [
            ("h1", 10, 1, 11, 2),  # song A offset 5, song B offset 90
            ("h2", 20, 1, 21, 2),  # song A offset 5
            ("h3", 30, 1, 31, 2),  # song A offset 5
            ("h4", 40, 1, 41, 2),  # no catalog hit
        ]
        best_name, score, hist = await match_fingerprints(db_session, query_fps)
        assert best_name == "song_a.wav"
        assert score == 3
        assert dict(hist) == {5: 3}

    async def test_breaks_ties_by_total_matches(self, db_session):
        song_a = Song(name="song_a.wav")
        song_b = Song(name="song_b.wav")
        db_session.add_all([song_a, song_b])
        await db_session.flush()

        # Song A matches two query hashes but at different offsets (peak score 1).
        _add_fingerprint(db_session, song_a.id, "h1", anchor_time=15)
        _add_fingerprint(db_session, song_a.id, "h2", anchor_time=35)
        # Song B matches one query hash (peak score 1).
        _add_fingerprint(db_session, song_b.id, "h3", anchor_time=35)
        await db_session.flush()

        query_fps = [
            ("h1", 10, 1, 11, 2),  # song A offset 5
            ("h2", 20, 1, 21, 2),  # song A offset 15
            ("h3", 30, 1, 31, 2),  # song B offset 5
        ]
        best_name, score, hist = await match_fingerprints(db_session, query_fps)
        # Both peak at score 1; song A wins on total matches (2 vs 1).
        assert best_name == "song_a.wav"
        assert score == 1


class TestMatchAudio:
    async def test_returns_full_song_with_confidence(self, db_session):
        song = Song(
            name="song.wav",
            status=ProcessingStatus.completed,
            artist="Test Artist",
        )
        db_session.add(song)
        await db_session.flush()
        _add_fingerprint(db_session, song.id, "h1", anchor_time=15)
        _add_fingerprint(db_session, song.id, "h2", anchor_time=25)
        _add_fingerprint(db_session, song.id, "h3", anchor_time=35)
        await db_session.flush()

        matched, score, confidence = await match_audio(
            db_session,
            [
                ("h1", 10, 1, 11, 2),
                ("h2", 20, 1, 21, 2),
                ("h3", 30, 1, 31, 2),
            ],
        )
        assert matched.id == song.id
        assert matched.name == "song.wav"
        assert matched.artist == "Test Artist"
        assert score == 3
        assert confidence == 1.0

    async def test_raises_no_match(self, db_session):
        with pytest.raises(NoMatchFoundError):
            await match_audio(db_session, [("nohash", 10, 1, 20, 2)])

    async def test_rejects_match_below_min_score(self, db_session):
        """A single spurious hash collision (score 1) must not match."""
        song = Song(name="song.wav", status=ProcessingStatus.completed)
        db_session.add(song)
        await db_session.flush()
        _add_fingerprint(db_session, song.id, "h1", anchor_time=15)
        await db_session.flush()

        with pytest.raises(NoMatchFoundError):
            await match_audio(db_session, [("h1", 10, 1, 11, 2)])

    async def test_rejects_match_below_min_confidence(self, db_session):
        """High score but scattered offsets (low confidence) must not match."""
        song = Song(name="song.wav", status=ProcessingStatus.completed)
        db_session.add(song)
        await db_session.flush()
        # 2 votes at offset 5, but 9 more at different offsets: peak score 2,
        # total 11 -> confidence 0.18, below the 0.2 floor.
        for i in range(11):
            anchor = 15 if i < 2 else 15 + (i + 1) * 10
            _add_fingerprint(db_session, song.id, f"h{i}", anchor_time=anchor)
        await db_session.flush()

        query_fps = [(f"h{i}", 10, 1, 11, 2) for i in range(11)]
        with pytest.raises(NoMatchFoundError):
            await match_audio(db_session, query_fps)

    async def test_accepts_match_above_thresholds(self, db_session):
        """score >= 2 and confidence >= 0.2 returns the song."""
        song = Song(name="song.wav", status=ProcessingStatus.completed)
        db_session.add(song)
        await db_session.flush()
        # 8 votes at the same offset: peak score 8, total 8 -> confidence 1.0.
        for i in range(8):
            _add_fingerprint(db_session, song.id, f"h{i}", anchor_time=15)
        await db_session.flush()

        query_fps = [(f"h{i}", 10, 1, 11, 2) for i in range(8)]
        matched, score, confidence = await match_audio(db_session, query_fps)
        assert matched.id == song.id
        assert score == 8
        assert confidence == 1.0


class TestGetMatchingFingerprintsInSong:
    async def test_returns_only_matching_hashes(self, db_session):
        song = Song(name="song.wav")
        db_session.add(song)
        await db_session.flush()
        _add_fingerprint(db_session, song.id, "h1", anchor_time=1)
        _add_fingerprint(db_session, song.id, "h2", anchor_time=5)
        await db_session.flush()

        rows = await get_matching_fingerprints_in_song(
            db_session,
            "song.wav",
            [("h1", 0, 0, 0, 0), ("hX", 0, 0, 0, 0)],
        )
        assert len(rows) == 1
        assert rows[0].hash == "h1"
