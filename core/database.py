import os

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine, AsyncSession

from core.models import Base

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://shanano:shanano@localhost:5432/shanano",
)

engine = create_async_engine(DATABASE_URL, echo=False)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
