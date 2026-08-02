"""Ad-hoc user creation for the Shanano API.

Registration is admin-only (no public signup), so this script is the way to
create users outside the API — e.g. the first admin, or test accounts.

Usage:
    python scripts/create_user.py <username> <password> [--role admin|user]

Reads the same DATABASE_URL env var as the API (defaults to local postgres)
and stores only a bcrypt hash of the password, never the plaintext.
"""

import argparse
import asyncio
import os
import sys
from pathlib import Path

# Make the project root importable when run as `python scripts/create_user.py`.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from core.models import Base, UserRole
from core.user_service import UsernameTakenError, create_user


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create a Shanano user")
    parser.add_argument("username", help="Unique username (3-64 chars)")
    parser.add_argument("password", help="Password (min 8 chars)")
    parser.add_argument(
        "--role",
        choices=[r.value for r in UserRole],
        default=UserRole.user.value,
        help="Role: admin or user (default: user)",
    )
    return parser.parse_args()


async def run(username: str, password: str, role: str) -> int:
    database_url = os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://shanano:shanano@localhost:5432/shanano",
    )
    engine = create_async_engine(database_url)
    # Same bootstrap the API runs at startup: create tables if they don't exist
    # (normal deployments keep schema in sync via `alembic upgrade head`).
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with maker() as session:
            try:
                user = await create_user(
                    session,
                    username=username,
                    password=password,
                    role=UserRole(role),
                )
                await session.commit()
            except UsernameTakenError:
                print(f"error: user '{username}' already exists")
                return 1
        print(f"created user '{username}' with role '{role}' (id={user.id})")
        return 0
    finally:
        await engine.dispose()


def main() -> None:
    args = parse_args()
    sys.exit(asyncio.run(run(args.username, args.password, args.role)))


if __name__ == "__main__":
    main()
