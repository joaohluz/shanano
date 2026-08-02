import os
from collections.abc import AsyncGenerator

os.environ["DATABASE_URL"] = "sqlite+aiosqlite://"
os.environ["JWT_SECRET"] = "test-secret-0123456789abcdef0123456789abcdef"

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from core.models import Base, User, UserRole
from core.security import create_token
from core.user_service import create_user
from api.main import app
from api.deps import get_db


@pytest_asyncio.fixture
async def db_engine():
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(db_engine) -> AsyncGenerator[AsyncSession, None]:
    session = async_sessionmaker(
        db_engine, class_=AsyncSession, expire_on_commit=False
    )()
    try:
        yield session
    finally:
        await session.close()


@pytest_asyncio.fixture
async def client(db_engine) -> AsyncGenerator[AsyncClient, None]:
    session = async_sessionmaker(
        db_engine, class_=AsyncSession, expire_on_commit=False
    )()

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield session

    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()
    await session.close()


@pytest_asyncio.fixture
async def admin_user(db_engine) -> User:
    """An admin user persisted directly via the user service (no HTTP)."""
    maker = async_sessionmaker(
        db_engine, class_=AsyncSession, expire_on_commit=False
    )
    async with maker() as session:
        user = await create_user(
            session, username="admin", password="adminpass123", role=UserRole.admin
        )
        await session.commit()
        return user


@pytest_asyncio.fixture
async def user_user(db_engine) -> User:
    """A regular (non-admin) user persisted directly via the user service."""
    maker = async_sessionmaker(
        db_engine, class_=AsyncSession, expire_on_commit=False
    )
    async with maker() as session:
        user = await create_user(
            session, username="alice", password="alicepass123", role=UserRole.user
        )
        await session.commit()
        return user


@pytest_asyncio.fixture
async def admin_token(admin_user) -> str:
    return create_token(
        subject=admin_user.id, username=admin_user.username, role=admin_user.role.value
    )


@pytest_asyncio.fixture
async def user_token(user_user) -> str:
    return create_token(
        subject=user_user.id, username=user_user.username, role=user_user.role.value
    )


@pytest_asyncio.fixture
def auth_headers(user_token) -> dict[str, str]:
    """Bearer header for a regular authenticated user."""
    return {"Authorization": f"Bearer {user_token}"}


@pytest_asyncio.fixture
def admin_headers(admin_token) -> dict[str, str]:
    """Bearer header for an admin user."""
    return {"Authorization": f"Bearer {admin_token}"}



