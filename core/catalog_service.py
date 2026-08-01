"""Internet Archive catalog ingestion service.

Queries the Internet Archive advanced search API for items in a collection,
fetches per-item metadata (creator/title/date/subject + cover art), downloads
one audio file per item into ``UPLOAD_DIR``, and inserts
``Song(status=pending, source="internet_archive")`` rows, deduping on
``source_url``.

The entrypoint ``fetch_catalog_batch`` is deliberately structured as a
self-contained async function so it can later be reused as an Airflow task.
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


def select_audio_file(files: list[dict[str, Any]]) -> Optional[str]:
    """Pick the preferred audio file from an IA item's file list.

    Follows the Iteration 4 spec: lossless FLAC/OGG first, M4A/MP3 fallback.
    Returns ``None`` when the item has no audio files we can consume.
    """
    candidates = [
        f for f in files if Path(f.get("name", "")).suffix.lower() in CATALOG_AUDIO_EXTENSIONS
    ]
    if not candidates:
        return None
    candidates.sort(
        key=lambda f: CATALOG_AUDIO_EXTENSIONS.index(Path(f["name"]).suffix.lower())
    )
    return candidates[0]["name"]


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
    """Fetch, download, and insert one item. Returns 1 if ingested, else 0."""
    source_url = build_details_url(identifier)
    existing = await db.execute(select(Song.id).where(Song.source_url == source_url))
    if existing.scalar_one_or_none() is not None:
        logger.info("catalog item already ingested, skipping", identifier=identifier)
        return 0

    metadata_json = await fetch_metadata(client, identifier)
    file_name = select_audio_file(metadata_json.get("files", []))
    if not file_name:
        logger.info("catalog item has no audio file, skipping", identifier=identifier)
        return 0

    metadata = extract_metadata(metadata_json, identifier)
    file_path = await download_audio(client, identifier, file_name, upload_dir)

    song = Song(
        name=metadata.title or Path(file_name).name,
        status=ProcessingStatus.pending,
        file_path=str(file_path),
        artist=metadata.artist,
        album=metadata.album,
        year=metadata.year,
        genre=metadata.genre,
        cover_art_url=metadata.cover_art_url,
        source=SOURCE_NAME,
        source_url=source_url,
    )
    db.add(song)
    await db.commit()
    logger.info(
        "catalog item ingested",
        identifier=identifier,
        file_name=file_name,
        title=metadata.title,
    )
    return 1


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
        ingested = 0
        for identifier in identifiers:
            try:
                ingested += await _ingest_item(aclient, db, identifier, upload_dir)
            except Exception as exc:
                # One bad item must not abort the whole batch.
                logger.error(
                    "catalog item failed",
                    identifier=identifier,
                    error=str(exc),
                )
                await db.rollback()
                continue
        return ingested

    if client is not None:
        return await _run(client)
    async with httpx.AsyncClient(follow_redirects=True) as aclient:
        return await _run(aclient)
