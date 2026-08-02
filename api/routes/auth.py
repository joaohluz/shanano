from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_current_user, get_db, require_admin
from core.models import User, UserRole
from core.schemas import TokenOut, UserCreate, UserOut
from core.security import create_token, verify_password
from core.user_service import UsernameTakenError, create_user, get_user_by_username

router = APIRouter()


@router.post("/register", response_model=UserOut, status_code=201)
async def register(
    payload: UserCreate,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> User:
    """Admin-only: create a new user. There is deliberately no public signup."""
    try:
        return await create_user(
            db,
            username=payload.username,
            password=payload.password,
            role=payload.role,
        )
    except UsernameTakenError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username already registered",
        )


@router.post("/login", response_model=TokenOut)
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
) -> TokenOut:
    """OAuth2 password-form login: returns a short-lived bearer JWT."""
    user = await get_user_by_username(db, form_data.username)
    if user is None or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    role = user.role.value if isinstance(user.role, UserRole) else user.role
    token = create_token(
        subject=user.id,
        username=user.username,
        role=role,
    )
    return TokenOut(access_token=token, token_type="bearer")


@router.get("/me", response_model=UserOut)
async def me(current_user: User = Depends(get_current_user)) -> User:
    """Return the profile of the currently authenticated user."""
    return current_user
