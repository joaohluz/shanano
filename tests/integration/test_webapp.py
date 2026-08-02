class TestWebapp:
    async def test_index_serves_page(self, client):
        response = await client.get("/")
        assert response.status_code == 200
        assert "Shanano" in response.text
        assert "app.js" in response.text

    async def test_static_assets_served(self, client):
        for path in ["/app.js", "/audio.js", "/styles.css"]:
            response = await client.get(path)
            assert response.status_code == 200, path

    async def test_api_routes_keep_priority(self, client):
        # The static mount is catch-all at "/", so registered API routes must
        # win over it.
        for path in ["/health", "/docs", "/openapi.json"]:
            response = await client.get(path)
            assert response.status_code == 200, path

    async def test_metrics_public(self, client):
        from core.database import engine
        from core.models import Base

        # /metrics reads songs_by_status through the app's own engine (not the
        # overridden get_db), so give that in-memory DB its tables first.
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        response = await client.get("/metrics")
        assert response.status_code == 200

    async def test_anonymous_match_end_to_end(self, client):
        """Public match end-to-end through the mounted app: 400, never 401."""
        response = await client.post(
            "/match/",
            files={"file": ("query.wav", b"fake-wav", "audio/wav")},
        )
        assert response.status_code == 400
        assert "decode" in response.json()["detail"].lower()
