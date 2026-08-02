"""Integration tests for the auth API and route protection."""
from core.security import create_token


class TestRegister:
    async def test_admin_can_register_user(self, client, admin_headers):
        response = await client.post(
            "/auth/register",
            json={"username": "bob", "password": "bobpass123"},
            headers=admin_headers,
        )
        assert response.status_code == 201
        data = response.json()
        assert data["username"] == "bob"
        assert data["role"] == "user"
        assert isinstance(data["id"], int)
        assert "hashed_password" not in data

    async def test_admin_can_register_admin(self, client, admin_headers):
        response = await client.post(
            "/auth/register",
            json={"username": "bob", "password": "bobpass123", "role": "admin"},
            headers=admin_headers,
        )
        assert response.status_code == 201
        assert response.json()["role"] == "admin"

    async def test_regular_user_cannot_register(self, client, auth_headers):
        response = await client.post(
            "/auth/register",
            json={"username": "bob", "password": "bobpass123"},
            headers=auth_headers,
        )
        assert response.status_code == 403

    async def test_unauthenticated_cannot_register(self, client):
        response = await client.post(
            "/auth/register",
            json={"username": "bob", "password": "bobpass123"},
        )
        assert response.status_code == 401

    async def test_duplicate_username_conflict(self, client, admin_headers):
        response = await client.post(
            "/auth/register",
            json={"username": "bob", "password": "bobpass123"},
            headers=admin_headers,
        )
        assert response.status_code == 201

        response = await client.post(
            "/auth/register",
            json={"username": "bob", "password": "bobpass123"},
            headers=admin_headers,
        )
        assert response.status_code == 409

    async def test_short_password_rejected(self, client, admin_headers):
        response = await client.post(
            "/auth/register",
            json={"username": "bob", "password": "short"},
            headers=admin_headers,
        )
        assert response.status_code == 422


class TestLogin:
    async def test_login_success_returns_token(self, client, admin_user):
        response = await client.post(
            "/auth/login",
            data={"username": "admin", "password": "adminpass123"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["token_type"] == "bearer"
        assert data["access_token"]

    async def test_login_wrong_password(self, client, admin_user):
        response = await client.post(
            "/auth/login",
            data={"username": "admin", "password": "wrong-password"},
        )
        assert response.status_code == 401
        assert response.json()["detail"] == "Incorrect username or password"

    async def test_login_unknown_user(self, client):
        response = await client.post(
            "/auth/login",
            data={"username": "nobody", "password": "whatever123"},
        )
        assert response.status_code == 401


class TestMe:
    async def test_me_with_valid_token(self, client, admin_user, admin_token):
        response = await client.get(
            "/auth/me", headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["username"] == "admin"
        assert data["role"] == "admin"
        assert data["id"] == admin_user.id

    async def test_me_with_login_token(self, client, admin_user):
        login = await client.post(
            "/auth/login",
            data={"username": "admin", "password": "adminpass123"},
        )
        token = login.json()["access_token"]
        response = await client.get(
            "/auth/me", headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200
        assert response.json()["username"] == "admin"

    async def test_me_without_token(self, client):
        response = await client.get("/auth/me")
        assert response.status_code == 401

    async def test_me_with_garbage_token(self, client):
        response = await client.get(
            "/auth/me", headers={"Authorization": "Bearer not.a.jwt"}
        )
        assert response.status_code == 401

    async def test_me_with_expired_token(self, client, admin_user):
        token = create_token(
            subject=admin_user.id,
            username=admin_user.username,
            role=admin_user.role.value,
            expires_minutes=-1,
        )
        response = await client.get(
            "/auth/me", headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 401


class TestPublicEndpoints:
    async def test_health_is_public(self, client):
        response = await client.get("/health")
        assert response.status_code == 200

    async def test_list_songs_is_public(self, client):
        response = await client.get("/songs/")
        assert response.status_code == 200

    async def test_metrics_is_public(self, client):
        # /metrics reads songs_by_status through the app's own engine
        # (not the overridden get_db), so give that in-memory DB its tables.
        from core.database import engine
        from core.models import Base

        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        response = await client.get("/metrics")
        assert response.status_code == 200


class TestProtectedRoutes:
    async def test_upload_requires_auth(self, client):
        response = await client.post(
            "/songs/",
            files={"file": ("test.wav", b"content", "audio/wav")},
        )
        assert response.status_code == 401

    async def test_match_is_public(self, client):
        # POST /match/ is public (webapp matches anonymously); an undecodable
        # body is a 400 decode error, not a 401 auth rejection.
        response = await client.post(
            "/match/",
            files={"file": ("test.wav", b"content", "audio/wav")},
        )
        assert response.status_code == 400

    async def test_user_can_upload(self, client, auth_headers):
        response = await client.post(
            "/songs/",
            files={"file": ("test.wav", b"content", "audio/wav")},
            headers=auth_headers,
        )
        assert response.status_code == 201

    async def test_user_cannot_delete(self, client, auth_headers):
        response = await client.post(
            "/songs/",
            files={"file": ("test.wav", b"content", "audio/wav")},
            headers=auth_headers,
        )
        song_id = response.json()["id"]
        response = await client.delete(f"/songs/{song_id}", headers=auth_headers)
        assert response.status_code == 403

    async def test_admin_can_delete(self, client, admin_headers):
        response = await client.post(
            "/songs/",
            files={"file": ("test.wav", b"content", "audio/wav")},
            headers=admin_headers,
        )
        song_id = response.json()["id"]
        response = await client.delete(f"/songs/{song_id}", headers=admin_headers)
        assert response.status_code == 204


class TestSeedUsers:
    async def test_seed_creates_admin_and_loadgen(self, db_engine):
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
        from sqlalchemy import select

        from core.models import User
        from core.user_service import seed_users

        maker = async_sessionmaker(
            db_engine, class_=AsyncSession, expire_on_commit=False
        )
        async with maker() as session:
            created = await seed_users(session)
            assert created == 2

            result = await session.execute(
                select(User).where(User.username.in_(["admin", "loadgen"]))
            )
            users = result.scalars().all()
            by_name = {u.username: u for u in users}
            assert set(by_name) == {"admin", "loadgen"}
            assert by_name["admin"].role == "admin"
            assert by_name["loadgen"].role == "user"

    async def test_seed_is_idempotent(self, db_engine):
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

        from core.user_service import seed_users

        maker = async_sessionmaker(
            db_engine, class_=AsyncSession, expire_on_commit=False
        )
        async with maker() as session:
            assert await seed_users(session) == 2
            assert await seed_users(session) == 0

    async def test_seed_skips_missing_credentials(self, db_engine, monkeypatch):
        import core.user_service as user_service
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

        from core.user_service import seed_users

        monkeypatch.setattr(user_service, "ADMIN_PASSWORD", "")
        monkeypatch.setattr(user_service, "LOADGEN_PASSWORD", "")

        maker = async_sessionmaker(
            db_engine, class_=AsyncSession, expire_on_commit=False
        )
        async with maker() as session:
            assert await seed_users(session) == 0
