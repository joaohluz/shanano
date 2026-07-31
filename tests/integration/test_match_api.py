class TestMatchEndpoint:
    async def test_match_returns_501(self, client):
        response = await client.post(
            "/match/",
            files={"file": ("test.wav", b"fake-wav-content", "audio/wav")},
        )
        assert response.status_code == 501
        assert response.json()["detail"] == "Matching not yet implemented"

    async def test_match_rejects_non_wav(self, client):
        response = await client.post(
            "/match/",
            files={"file": ("test.mp3", b"fake-content", "audio/mpeg")},
        )
        assert response.status_code == 400

    async def test_match_rejects_empty_filename(self, client):
        response = await client.post(
            "/match/",
            files={"file": ("", b"content", "audio/wav")},
        )
        assert response.status_code == 422
