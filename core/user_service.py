"""User persistence and startup seeding.

Auth business logic lives here (not in routes): creating users, looking them
up by username, and seeding the bootstrap admin/loadgen accounts from env vars
at API startup. Passwords are hashed with bcrypt before touching the DB.
"""

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import (
    ADMIN_PASSWORD,
    ADMIN_USERNAME,
    LOADGEN_PASSWORD,
    LOADGEN_USERNAME,
)
from core.models import User, UserRole
from core.security import hash_password


class UsernameTakenError(Exception):
    """Raised when a user with the requested username already exists."""


async def get_user_by_username(db: AsyncSession, username: str) -> Optional[User]:
    result = await db.execute(select(User).where(User.username == username))
    return result.scalar_one_or_none()


async def create_user(
    db: AsyncSession,
    *,
    username: str,
    password: str,
    role: UserRole = UserRole.user,
) -> User:
    """Create a user (hashed password) and flush it to the DB.

    Raises UsernameTakenError if the username is already registered.
    """
    if await get_user_by_username(db, username) is not None:
        raise UsernameTakenError(f"username '{username}' is already registered")
    user = User(
        username=username,
        hashed_password=hash_password(password),
        role=role,
    )
    db.add(user)
    await db.flush()
    return user


async def seed_users(db: AsyncSession) -> int:
    """Create the bootstrap admin + loadgen users from env if missing.

    The loadgen account is created as an admin: DELETE /songs/{id} is
    admin-only and loadgen exercises it (fake traffic churn), so a plain
    user role would lock it out. Skips accounts whose env credentials are
    unset, and never overwrites an existing user's password. Returns the
    number of users created.
    """
    created = 0
    for username, password, role in (
        (ADMIN_USERNAME, ADMIN_PASSWORD, UserRole.admin),
        (LOADGEN_USERNAME, LOADGEN_PASSWORD, UserRole.admin),
    ):
        if not username or not password:
            continue
        if await get_user_by_username(db, username) is not None:
            continue
        await create_user(db, username=username, password=password, role=role)
        created += 1
    if created:
        await db.commit()
    return created
