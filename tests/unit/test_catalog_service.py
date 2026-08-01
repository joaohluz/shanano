"""Unit tests for the Internet Archive catalog ingestion service.

The httpx client is mocked with ``httpx.MockTransport`` so no network access
is required.
"""
import httpx
from sqlalchemy import select

from config import CATALOG_COLLECTION, CATALOG_MAX_ITEMS
from core.catalog_service import (
    SOURCE_NAME,
    build_cover_art_url,
    build_details_url,
    build_download_url,
    extract_metadata,
    fetch_catalog_batch,
    search_catalog,
    select_audio_file,
)
from core.models import ProcessingStatus, Song


def make_mock_client(
    identifiers: list[str],
    metadata_by_id: dict[str, dict],
    audio_bytes: bytes = b"fake-flac-bytes",
) -> httpx.AsyncClient:
    """Build an AsyncClient whose transport answers IA endpoints from dicts."""

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "advancedsearch.php" in url:
            docs = [{"identifier": i} for i in identifiers]
            return httpx.Response(
                200,
                json={"response": {"numFound": len(docs), "docs": docs}},
            )
        if url.startswith("https://archive.org/metadata/"):
            identifier = url.rsplit("/", 1)[1]
            return httpx.Response(200, json=metadata_by_id[identifier])
        if url.startswith("https://archive.org/download/"):
            return httpx.Response(200, content=audio_bytes)
        return httpx.Response(404, text="not found")

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def sample_metadata(identifier: str = "gd1990-07-08.sbd.miller.12345") -> dict:
    return {
        "metadata": {
            "identifier": identifier,
            "title": "Grateful Dead Live at RFK Stadium on 1990-07-08",
            "creator": ["Grateful Dead"],
            "album": "Live at RFK Stadium",
            "date": "1990-07-08",
            "subject": ["rock", "jam band", "live concert"],
        },
        "files": [
            {"name": "gd1990-07-08d1t01.flac", "format": "Flac"},
            {"name": "gd1990-07-08d1t01.mp3", "format": "VBR MP3"},
        ],
    }


class TestSearchCatalog:
    async def test_queries_advanced_search_with_defaults(self):
        captured = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["params"] = dict(request.url.params)
            return httpx.Response(
                200, json={"response": {"numFound": 0, "docs": []}}
            )

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        identifiers = await search_catalog(client)
        assert identifiers == []
        assert captured["params"]["q"] == f"collection:{CATALOG_COLLECTION}"
        assert captured["params"]["fl[]"] == "identifier"
        assert int(captured["params"]["rows"]) == CATALOG_MAX_ITEMS

    async def test_returns_identifiers_from_docs(self):
        client = make_mock_client(
            identifiers=["item-a", "item-b"],
            metadata_by_id={},
        )
        identifiers = await search_catalog(client, collection="etree", max_items=2)
        assert identifiers == ["item-a", "item-b"]

    async def test_skips_docs_without_identifier(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "response": {
                        "numFound": 3,
                        "docs": [
                            {"identifier": "item-a"},
                            {"foo": "no identifier here"},
                            {"identifier": "item-b"},
                        ],
                    }
                },
            )

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        identifiers = await search_catalog(client, max_items=5)
        assert identifiers == ["item-a", "item-b"]


class TestSelectAudioFile:
    def test_prefers_flac_over_mp3(self):
        files = [
            {"name": "cover.jpg", "format": "JPEG"},
            {"name": "track.mp3", "format": "VBR MP3"},
            {"name": "track.flac", "format": "Flac"},
        ]
        assert select_audio_file(files) == "track.flac"

    def test_prefers_ogg_over_mp3(self):
        files = [
            {"name": "track.ogg", "format": "Ogg Vorbis"},
            {"name": "track.mp3", "format": "128Kbps MP3"},
        ]
        assert select_audio_file(files) == "track.ogg"

    def test_falls_back_to_mp3(self):
        files = [{"name": "track.mp3", "format": "VBR MP3"}]
        assert select_audio_file(files) == "track.mp3"

    def test_returns_none_when_no_audio(self):
        files = [{"name": "cover.jpg", "format": "JPEG"}, {"name": "notes.txt", "format": "Text"}]
        assert select_audio_file(files) is None

    def test_returns_none_on_empty_list(self):
        assert select_audio_file([]) is None


class TestExtractMetadata:
    def test_extracts_all_fields(self):
        metadata = extract_metadata(sample_metadata(), identifier="gd1990")
        assert metadata.title == "Grateful Dead Live at RFK Stadium on 1990-07-08"
        assert metadata.artist == "Grateful Dead"
        assert metadata.album == "Live at RFK Stadium"
        assert metadata.year == 1990
        assert metadata.genre == "rock, jam band, live concert"
        assert metadata.cover_art_url == "https://archive.org/services/img/gd1990"

    def test_handles_missing_fields(self):
        metadata = extract_metadata({"metadata": {}}, identifier="empty")
        assert metadata.title is None
        assert metadata.artist is None
        assert metadata.year is None
        assert metadata.genre is None

    def test_handles_string_date_with_year(self):
        metadata = extract_metadata(
            {"metadata": {"date": "2005"}}, identifier="x"
        )
        assert metadata.year == 2005

    def test_handles_date_without_four_digit_year(self):
        metadata = extract_metadata(
            {"metadata": {"date": "unknown"}}, identifier="x"
        )
        assert metadata.year is None


class TestURLBuilders:
    def test_details_url(self):
        assert build_details_url("abc") == "https://archive.org/details/abc"

    def test_cover_art_url(self):
        assert build_cover_art_url("abc") == "https://archive.org/services/img/abc"

    def test_download_url_quotes_file_name(self):
        url = build_download_url("abc", "my file.flac")
        assert url == "https://archive.org/download/abc/my%20file.flac"


class TestFetchCatalogBatch:
    async def test_inserts_pending_song_with_metadata(self, db_session, tmp_path):
        client = make_mock_client(
            identifiers=["gd1990"],
            metadata_by_id={"gd1990": sample_metadata()},
        )
        ingested = await fetch_catalog_batch(
            db_session,
            collection="etree",
            max_items=1,
            client=client,
            upload_dir=str(tmp_path),
        )
        assert ingested == 1

        result = await db_session.execute(
            select(Song).where(Song.id == 1)
        )
        song = result.scalar_one()
        assert song.status == ProcessingStatus.pending
        assert song.source == SOURCE_NAME
        assert song.source_url == "https://archive.org/details/gd1990"
        assert song.artist == "Grateful Dead"
        assert song.album == "Live at RFK Stadium"
        assert song.year == 1990
        assert song.genre == "rock, jam band, live concert"
        assert song.cover_art_url == "https://archive.org/services/img/gd1990"
        assert song.name == "Grateful Dead Live at RFK Stadium on 1990-07-08"

        # Audio file downloaded into upload_dir
        assert (tmp_path / "gd1990-07-08d1t01.flac").read_bytes() == b"fake-flac-bytes"

    async def test_dedupes_by_source_url(self, db_session, tmp_path):
        client = make_mock_client(
            identifiers=["gd1990"],
            metadata_by_id={"gd1990": sample_metadata()},
        )
        first = await fetch_catalog_batch(
            db_session, max_items=1, client=client, upload_dir=str(tmp_path)
        )
        second = await fetch_catalog_batch(
            db_session, max_items=1, client=client, upload_dir=str(tmp_path)
        )
        assert first == 1
        assert second == 0

        result = await db_session.execute(
            select(Song)
        )
        songs = result.scalars().all()
        assert len(songs) == 1

    async def test_skips_item_without_audio_files(self, db_session, tmp_path):
        metadata = sample_metadata()
        metadata["files"] = [{"name": "cover.jpg", "format": "JPEG"}]
        client = make_mock_client(
            identifiers=["no-audio"], metadata_by_id={"no-audio": metadata}
        )
        ingested = await fetch_catalog_batch(
            db_session, max_items=1, client=client, upload_dir=str(tmp_path)
        )
        assert ingested == 0
        result = await db_session.execute(
            select(Song)
        )
        assert result.scalars().all() == []

    async def test_continues_when_item_errors(self, db_session, tmp_path):
        """A failing item (e.g. missing metadata) must not abort the batch."""

        def handler(request: httpx.Request) -> httpx.Response:
            url = str(request.url)
            if "advancedsearch.php" in url:
                docs = [{"identifier": "broken"}, {"identifier": "good"}]
                return httpx.Response(200, json={"response": {"docs": docs}})
            if url.startswith("https://archive.org/metadata/broken"):
                return httpx.Response(500, text="boom")
            if url.startswith("https://archive.org/metadata/good"):
                return httpx.Response(200, json=sample_metadata("good"))
            if url.startswith("https://archive.org/download/"):
                return httpx.Response(200, content=b"bytes")
            return httpx.Response(404)

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        ingested = await fetch_catalog_batch(
            db_session, max_items=2, client=client, upload_dir=str(tmp_path)
        )
        assert ingested == 1
        result = await db_session.execute(
            select(Song).where(Song.source_url == "https://archive.org/details/good")
        )
        assert result.scalar_one() is not None

    async def test_default_client_follows_download_redirects(
        self, db_session, tmp_path, monkeypatch
    ):
        """IA download URLs 302-redirect to a CDN; the internally-created
        client must follow them or every download fails (regression test)."""

        def handler(request: httpx.Request) -> httpx.Response:
            url = str(request.url)
            if "advancedsearch.php" in url:
                return httpx.Response(
                    200,
                    json={"response": {"docs": [{"identifier": "gd1990"}]}},
                )
            if url.startswith("https://archive.org/metadata/"):
                return httpx.Response(200, json=sample_metadata())
            if url.startswith("https://archive.org/download/"):
                return httpx.Response(
                    302,
                    headers={"Location": "https://cdn.archive.org/gd1990.flac"},
                )
            if url.startswith("https://cdn.archive.org/"):
                return httpx.Response(200, content=b"redirected-bytes")
            return httpx.Response(404)

        captured = {}
        real_client = httpx.AsyncClient(
            transport=httpx.MockTransport(handler), follow_redirects=True
        )

        def client_factory(**kwargs):
            captured["kwargs"] = kwargs
            return real_client

        monkeypatch.setattr("core.catalog_service.httpx.AsyncClient", client_factory)

        ingested = await fetch_catalog_batch(
            db_session, max_items=1, upload_dir=str(tmp_path)
        )
        assert ingested == 1
        assert captured["kwargs"].get("follow_redirects") is True
        assert (tmp_path / "gd1990-07-08d1t01.flac").read_bytes() == b"redirected-bytes"
