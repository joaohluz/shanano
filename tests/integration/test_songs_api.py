class TestListSongs:
    async def test_empty_list(self, client):
        response = await client.get("/songs/")
        assert response.status_code == 200
        assert response.json() == []

    async def test_returns_list_of_songs(self, client, auth_headers):
        response = await client.post(
            "/songs/",
            files={"file": ("test.wav", b"content", "audio/wav")},
            headers=auth_headers,
        )
        assert response.status_code == 201
        song_id = response.json()["id"]

        response = await client.get("/songs/")
        data = response.json()
        assert len(data) == 1
        assert data[0]["name"] == "test.wav"
        assert data[0]["id"] == song_id

    async def test_fingerprint_count(self, client, db_engine, auth_headers):
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
        from core.models import Song, Fingerprint
        from sqlalchemy import select

        maker = async_sessionmaker(
            db_engine, class_=AsyncSession, expire_on_commit=False
        )

        response = await client.post(
            "/songs/",
            files={"file": ("test.wav", b"content", "audio/wav")},
            headers=auth_headers,
        )
        assert response.status_code == 201
        song_id = response.json()["id"]

        async with maker() as session:
            song = await session.get(Song, song_id)
            session.add(
                Fingerprint(
                    hash="abc", song_id=song.id,
                    anchor_time=0, anchor_freq=100,
                    target_time=5, target_freq=200,
                )
            )
            await session.commit()

        # Re-query via client (separate session) to test the join
        response = await client.get("/songs/")
        data = response.json()
        song_data = next(s for s in data if s["id"] == song_id)
        assert song_data["fingerprint_count"] == 1


class TestGetSong:
    async def test_get_existing_song(self, client, auth_headers):
        response = await client.post(
            "/songs/",
            files={"file": ("test.wav", b"content", "audio/wav")},
            headers=auth_headers,
        )
        song_id = response.json()["id"]

        response = await client.get(f"/songs/{song_id}")
        assert response.status_code == 200
        assert response.json()["name"] == "test.wav"
        assert response.json()["id"] == song_id

    async def test_get_nonexistent_song(self, client):
        response = await client.get("/songs/999")
        assert response.status_code == 404
        assert response.json()["detail"] == "Song not found"


class TestAddSong:
    async def test_upload_wav_file(self, client, monkeypatch, auth_headers):
        import tempfile
        tmp = tempfile.mkdtemp()
        monkeypatch.setattr("api.routes.songs.UPLOAD_DIR", tmp)

        response = await client.post(
            "/songs/",
            files={"file": ("test.wav", b"fake-wav-content", "audio/wav")},
            headers=auth_headers,
        )
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "test.wav"
        assert data["status"] == "pending"
        assert isinstance(data["id"], int)

        from pathlib import Path
        assert (Path(tmp) / "test.wav").exists()

    async def test_upload_mp3_accepted(self, client, monkeypatch, auth_headers):
        import tempfile
        tmp = tempfile.mkdtemp()
        monkeypatch.setattr("api.routes.songs.UPLOAD_DIR", tmp)

        response = await client.post(
            "/songs/",
            files={"file": ("song.mp3", b"fake-mp3-content", "audio/mpeg")},
            headers=auth_headers,
        )
        assert response.status_code == 201
        assert response.json()["name"] == "song.mp3"

        from pathlib import Path
        assert (Path(tmp) / "song.mp3").exists()

    async def test_rejects_unsupported_format(self, client, auth_headers):
        response = await client.post(
            "/songs/",
            files={"file": ("test.txt", b"fake-content", "text/plain")},
            headers=auth_headers,
        )
        assert response.status_code == 400
        assert "Unsupported" in response.json()["detail"]

    async def test_rejects_no_filename(self, client, auth_headers):
        response = await client.post(
            "/songs/",
            files={"file": ("", b"content", "audio/wav")},
            headers=auth_headers,
        )
        assert response.status_code == 422

    async def test_requires_auth(self, client):
        response = await client.post(
            "/songs/",
            files={"file": ("test.wav", b"content", "audio/wav")},
        )
        assert response.status_code == 401


class TestDeleteSong:
    async def test_delete_existing(self, client, admin_headers):
        response = await client.post(
            "/songs/",
            files={"file": ("delete_me.wav", b"content", "audio/wav")},
            headers=admin_headers,
        )
        song_id = response.json()["id"]

        response = await client.delete(f"/songs/{song_id}", headers=admin_headers)
        assert response.status_code == 204

        response = await client.get(f"/songs/{song_id}")
        assert response.status_code == 404

    async def test_delete_nonexistent(self, client, admin_headers):
        response = await client.delete("/songs/999", headers=admin_headers)
        assert response.status_code == 404

    async def test_delete_requires_admin(self, client, auth_headers):
        response = await client.post(
            "/songs/",
            files={"file": ("delete_me.wav", b"content", "audio/wav")},
            headers=auth_headers,
        )
        song_id = response.json()["id"]

        response = await client.delete(f"/songs/{song_id}", headers=auth_headers)
        assert response.status_code == 403

    async def test_delete_requires_auth(self, client):
        response = await client.delete("/songs/999")
        assert response.status_code == 401
