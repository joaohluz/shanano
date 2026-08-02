"""Internet Archive catalog ingestion service.

Queries the Internet Archive advanced search API for items in a collection,
fetches per-item metadata (creator/title/date/subject + cover art), downloads
the item's audio into ``UPLOAD_DIR``, and inserts
``Song(status=pending, source="internet_archive")`` rows, deduping on each
track's download ``source_url``. A multi-track item (an album) becomes one
pending song per distinct track; a single-track item stays one song.

Two entrypoints are deliberately structured as self-contained async functions
so they can later be reused as Airflow tasks / K8s CronJobs:

* ``fetch_catalog_batch`` — search a collection and ingest up to N items.
* ``ingest_links`` — ingest a hand-picked list of IA links/identifiers (the
  seed pipeline's source of new data).
"""
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional
from urllib.parse import quote

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import (
    CATALOG_AUDIO_EXTENSIONS,
    CATALOG_COLLECTION,
    CATALOG_MAX_ITEMS,
    IA_ADVANCED_SEARCH_URL,
    IA_DETAILS_URL,
    IA_DOWNLOAD_URL,
    IA_IMG_URL,
    IA_METADATA_URL,
    UPLOAD_DIR,
)
from core.logging import get_logger
from core.models import ProcessingStatus, Song

logger = get_logger("catalog_service")

SOURCE_NAME = "internet_archive"

_YEAR_RE = re.compile(r"\b(?:19|20)\d{2}\b")
_BITRATE_RE = re.compile(r"_(?:\d+kb|vbr)$")


@dataclass
class CatalogMetadata:
    """Normalized metadata extracted from an Internet Archive item."""

    title: Optional[str] = None
    artist: Optional[str] = None
    album: Optional[str] = None
    year: Optional[int] = None
    genre: Optional[str] = None
    cover_art_url: Optional[str] = None


def build_details_url(identifier: str) -> str:
    """The archive.org details page URL for an item (used as ``source_url``)."""
    return f"{IA_DETAILS_URL}/{identifier}"


def build_cover_art_url(identifier: str) -> str:
    return f"{IA_IMG_URL}/{identifier}"


def build_download_url(identifier: str, file_name: str) -> str:
    return f"{IA_DOWNLOAD_URL}/{identifier}/{quote(file_name)}"


def _join_values(value: Any) -> Optional[str]:
    """IA metadata fields are often a list (multiple creators/subjects)."""
    if value is None:
        return None
    if isinstance(value, list):
        parts = [str(v).strip() for v in value if v is not None]
        return ", ".join(parts) if parts else None
    text = str(value).strip()
    return text or None


def _extract_year(value: Any) -> Optional[int]:
    """Pull a 4-digit year out of IA's free-form date field."""
    text = _join_values(value)
    if not text:
        return None
    match = _YEAR_RE.search(text)
    return int(match.group(0)) if match else None


def _track_key(file_name: str) -> str:
    """Normalized identity of a track: lowercased basename with derived
    ``_64kb``/``_128kb``/``_vbr`` transcode suffixes stripped, so an item's
    ``track.flac``, ``track.mp3`` and ``track_128kb.mp3`` all collapse to one."""
    stem = Path(file_name).stem.lower()
    return _BITRATE_RE.sub("", stem)


def select_tracks(files: list[dict[str, Any]]) -> list[str]:
    """Pick one preferred audio file per distinct track in an item's file list.

    Groups files by ``_track_key`` (so lossless + MP3 + bitrate-transcodes of
    the same track collapse to a single entry) and keeps the best-format
    member of each group (FLAC/OGG first, M4A/MP3 fallback). Returns the
    original file names in track order. An empty list means no usable audio.
    """
    candidates = [
        f["name"]
        for f in files
        if Path(f.get("name", "")).suffix.lower() in CATALOG_AUDIO_EXTENSIONS
    ]
    if not candidates:
        return []

    def sort_key(name: str) -> tuple:
        ext = Path(name).suffix.lower()
        stem = Path(name).stem.lower()
        bitrate_match = re.search(r"_(\d+)kb$", stem)
        derived = bool(bitrate_match or stem.endswith("_vbr"))
        bitrate = int(bitrate_match.group(1)) if bitrate_match else 0
        return (
            _track_key(name),
            CATALOG_AUDIO_EXTENSIONS.index(ext),
            derived,
            bitrate,
            name,
        )

    candidates.sort(key=sort_key)
    seen: set[str] = set()
    tracks: list[str] = []
    for name in candidates:
        key = _track_key(name)
        if key in seen:
            continue
        seen.add(key)
        tracks.append(name)
    return tracks


def select_audio_file(files: list[dict[str, Any]]) -> Optional[str]:
    """Pick the single preferred audio file from an IA item's file list.

    Returns the first track chosen by ``select_tracks`` — the best-format
    member of the first distinct track — or ``None`` when there is no audio.
    """
    tracks = select_tracks(files)
    return tracks[0] if tracks else None


def extract_metadata(metadata_json: dict[str, Any], identifier: str) -> CatalogMetadata:
    """Normalize an IA metadata payload into our catalog metadata fields."""
    metadata = metadata_json.get("metadata", {})
    return CatalogMetadata(
        title=_join_values(metadata.get("title")),
        artist=_join_values(metadata.get("creator")),
        album=_join_values(metadata.get("album")),
        year=_extract_year(metadata.get("date")),
        genre=_join_values(metadata.get("subject")),
        cover_art_url=build_cover_art_url(identifier),
    )


async def search_catalog(
    client: httpx.AsyncClient,
    collection: Optional[str] = None,
    max_items: Optional[int] = None,
) -> list[str]:
    """Query advancedsearch.php and return up to ``max_items`` identifiers."""
    collection = collection or CATALOG_COLLECTION
    max_items = max_items or CATALOG_MAX_ITEMS
    params = {
        "q": f"collection:{collection}",
        "fl[]": "identifier",
        "rows": max_items,
        "page": 1,
        "output": "json",
    }
    response = await client.get(IA_ADVANCED_SEARCH_URL, params=params)
    response.raise_for_status()
    data = response.json()
    docs = data.get("response", {}).get("docs", [])
    return [doc["identifier"] for doc in docs if doc.get("identifier")]


async def fetch_metadata(
    client: httpx.AsyncClient, identifier: str
) -> dict[str, Any]:
    """Fetch the raw IA metadata JSON payload for an item."""
    response = await client.get(f"{IA_METADATA_URL}/{identifier}")
    response.raise_for_status()
    return response.json()


def parse_ia_link(link: str) -> Optional[str]:
    """Extract an Internet Archive item identifier from a link or bare id.

    Accepts details/metadata/download URLs and plain identifiers::

        https://archive.org/details/gd1990-07-08.sbd.miller.12345
        https://archive.org/metadata/gd1990-07-08.sbd.miller.12345
        https://archive.org/download/gd1990-07-08.sbd.miller.12345/track.flac
        gd1990-07-08.sbd.miller.12345

    Returns ``None`` for empty lines and URLs that don't look like an IA item.
    """
    text = link.strip()
    if not text:
        return None
    # Drop query strings / fragments before parsing the path.
    text = text.split("?")[0].split("#")[0]
    if "archive.org/" in text.lower():
        parts = text.split("/")
        # parts: [scheme, "", host, kind, identifier, ...]
        if len(parts) >= 5 and parts[3] in ("details", "metadata", "download"):
            return parts[4] or None
        return None
    # A URL pointing at anything other than archive.org is not an identifier.
    if "://" in text:
        return None
    return text


async def download_audio(
    client: httpx.AsyncClient,
    identifier: str,
    file_name: str,
    upload_dir: str = UPLOAD_DIR,
) -> Path:
    """Stream an item's audio file from the IA download endpoint to disk."""
    url = build_download_url(identifier, file_name)
    dest_dir = Path(upload_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    # IA file names are the basename; guard against any nested paths.
    dest_path = dest_dir / Path(file_name).name
    async with client.stream("GET", url) as response:
        response.raise_for_status()
        with open(dest_path, "wb") as fh:
            async for chunk in response.aiter_bytes():
                fh.write(chunk)
    return dest_path


async def _ingest_item(
    client: httpx.AsyncClient,
    db: AsyncSession,
    identifier: str,
    upload_dir: str,
) -> int:
    """Fetch metadata, download each track, and insert pending Song rows.

    A multi-track item (an album) becomes one pending song per distinct track;
    a single-track item stays one song named from the item metadata. Returns
    the number of newly ingested tracks (already-imported tracks are skipped).
    Each track's ``source_url`` is its unique download URL, which is also the
    dedupe key.
    """
    metadata_json = await fetch_metadata(client, identifier)
    file_names = select_tracks(metadata_json.get("files", []))
    if not file_names:
        logger.info("catalog item has no audio file, skipping", identifier=identifier)
        return 0

    metadata = extract_metadata(metadata_json, identifier)
    multi = len(file_names) > 1
    ingested = 0
    for file_name in file_names:
        source_url = build_download_url(identifier, file_name)
        existing = await db.execute(
            select(Song.id).where(Song.source_url == source_url)
        )
        if existing.scalar_one_or_none() is not None:
            logger.info(
                "catalog track already ingested, skipping",
                identifier=identifier,
                file_name=file_name,
            )
            continue

        file_path = await download_audio(client, identifier, file_name, upload_dir)
        song = Song(
            name=Path(file_name).stem if multi else (metadata.title or Path(file_name).stem),
            status=ProcessingStatus.pending,
            file_path=str(file_path),
            artist=metadata.artist,
            album=metadata.album if not multi else (metadata.album or metadata.title),
            year=metadata.year,
            genre=metadata.genre,
            cover_art_url=metadata.cover_art_url,
            source=SOURCE_NAME,
            source_url=source_url,
        )
        db.add(song)
        ingested += 1

    await db.commit()
    logger.info(
        "catalog item ingested",
        identifier=identifier,
        tracks=len(file_names),
        ingested=ingested,
    )
    return ingested


async def _ingest_many(
    aclient: httpx.AsyncClient,
    db: AsyncSession,
    identifiers: list[str],
    upload_dir: str,
) -> int:
    """Ingest a list of identifiers. One failure must not abort the rest."""
    ingested = 0
    for identifier in identifiers:
        try:
            ingested += await _ingest_item(aclient, db, identifier, upload_dir)
        except Exception as exc:
            logger.error("catalog item failed", identifier=identifier, error=str(exc))
            await db.rollback()
            continue
    return ingested


async def ingest_links(
    db: AsyncSession,
    links: list[str],
    client: Optional[httpx.AsyncClient] = None,
    upload_dir: str = UPLOAD_DIR,
) -> int:
    """Ingest a hand-picked list of IA links/identifiers as pending songs.

    Each entry may be a details/metadata/download URL or a bare identifier
    (see ``parse_ia_link``). Duplicates are dropped before fetching. This is
    the entrypoint the seed pipeline uses to build a catalog from a curated
    list of links instead of a collection search.
    """
    identifiers: list[str] = []
    seen: set[str] = set()
    for link in links:
        parsed = parse_ia_link(link)
        if parsed is None or parsed in seen:
            continue
        seen.add(parsed)
        identifiers.append(parsed)

    if not identifiers:
        return 0

    async def _run(aclient: httpx.AsyncClient) -> int:
        return await _ingest_many(aclient, db, identifiers, upload_dir)

    if client is not None:
        return await _run(client)
    async with httpx.AsyncClient(follow_redirects=True) as aclient:
        return await _run(aclient)


async def fetch_catalog_batch(
    db: AsyncSession,
    collection: Optional[str] = None,
    max_items: Optional[int] = None,
    client: Optional[httpx.AsyncClient] = None,
    upload_dir: str = UPLOAD_DIR,
) -> int:
    """Fetch one batch of items from the IA catalog and persist pending songs.

    Returns the number of newly ingested songs (already-imported and
    audio-less items are skipped, not counted). This is the reusable unit for
    the ``catalog_fetch`` CLI and, later, an Airflow task / K8s CronJob.

    ``client`` and ``upload_dir`` are injectable for testing.
    """
    collection = collection or CATALOG_COLLECTION
    max_items = max_items or CATALOG_MAX_ITEMS

    async def _run(aclient: httpx.AsyncClient) -> int:
        identifiers = await search_catalog(aclient, collection, max_items)
        logger.info(
            "catalog search returned",
            collection=collection,
            identifiers=len(identifiers),
        )
        return await _ingest_many(aclient, db, identifiers, upload_dir)

    if client is not None:
        return await _run(client)
    async with httpx.AsyncClient(follow_redirects=True) as aclient:
        return await _run(aclient)
