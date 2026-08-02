"""Real audio matching: async SQLAlchemy port of controllers/match_service.py.

The matching algorithm is kept identical to the SQLite reference:

1. **Hash lookup** — for every query fingerprint, find catalog fingerprints
   with the same hash (Fingerprint joined to Song).
2. **Offset voting** — tally ``db_anchor_time - query_anchor_time`` per
   candidate song; the correct song peaks at a single offset.
3. **Best candidate** — pick the song with the highest offset count, breaking
   ties by total matching fingerprints.

Only the storage layer changes: async SQLAlchemy queries instead of a
``sqlite3`` cursor.
"""

from collections import defaultdict
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import MATCH_MIN_CONFIDENCE, MATCH_MIN_SCORE
from core.models import Fingerprint, Song

# A fingerprint is a 5-tuple: (hash, anchor_time, anchor_freq, target_time, target_freq).
FingerprintTuple = tuple[str, int, int, int, int]


class NoMatchFoundError(Exception):
    """Raised when no catalog song matches the submitted fingerprints."""


async def match_fingerprints(
    db: AsyncSession, fingerprints: list[FingerprintTuple]
) -> tuple[Optional[str], Optional[int], Optional[dict[int, int]]]:
    """Hash lookup -> offset voting -> best candidate.

    Returns ``(best_song_name, score, offset_histogram)`` or
    ``(None, None, None)`` when nothing in the catalog matches.
    """
    matches: dict[str, list[int]] = defaultdict(list)
    for h, anchor_time, anchor_freq, target_time, target_freq in fingerprints:
        result = await db.execute(
            select(Fingerprint.anchor_time, Song.name)
            .join(Song, Song.id == Fingerprint.song_id)
            .where(Fingerprint.hash == h)
        )
        for db_anchor_time, song_name in result.all():
            matches[song_name].append(int(db_anchor_time) - anchor_time)

    song_candidates = []
    offset_count_per_song: dict[str, dict[int, int]] = {}
    for song_name, offsets in matches.items():
        hist = defaultdict(int)
        for o in offsets:
            hist[o] += 1
        score = max(hist.values())
        total_matches = sum(hist.values())
        song_candidates.append((song_name, score, total_matches))
        offset_count_per_song[song_name] = hist

    if not song_candidates:
        return None, None, None

    chosen = sorted(song_candidates, key=lambda x: (x[1], x[2]), reverse=True)
    best_song = chosen[0]
    return best_song[0], best_song[1], offset_count_per_song[best_song[0]]


async def match_audio(
    db: AsyncSession, fingerprints: list[FingerprintTuple]
) -> tuple[Song, int, Optional[float]]:
    """Match query fingerprints against the catalog.

    Returns ``(best_song, score, confidence)`` where confidence is the fraction
    of matched fingerprints that voted for the winning offset (0..1). Raises
    :class:`NoMatchFoundError` when nothing matches.
    """
    best_song_name, score, offset_hist = await match_fingerprints(db, fingerprints)
    if best_song_name is None:
        raise NoMatchFoundError("No matching song found")

    total_matches = sum(offset_hist.values()) if offset_hist else 0
    confidence = score / total_matches if total_matches else None

    if score < MATCH_MIN_SCORE or confidence is None or confidence < MATCH_MIN_CONFIDENCE:
        raise NoMatchFoundError("No matching song found")

    result = await db.execute(select(Song).where(Song.name == best_song_name))
    song = result.scalar_one()

    return song, score, confidence


async def get_matching_fingerprints_in_song(
    db: AsyncSession, song_name: str, fingerprints: list[FingerprintTuple]
) -> list[Fingerprint]:
    """Catalog fingerprints of ``song_name`` whose hash appears in the query."""
    hashes = [h for h, _, _, _, _ in fingerprints]
    if not hashes:
        return []
    result = await db.execute(
        select(Fingerprint)
        .join(Song, Song.id == Fingerprint.song_id)
        .where(Song.name == song_name, Fingerprint.hash.in_(hashes))
    )
    return list(result.scalars().all())
