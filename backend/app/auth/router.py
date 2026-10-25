from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.auth.dependencies import get_current_user
from app.auth.schemas import (
    AuthResponse,
    LoginRequest,
    RegisterRequest,
    UserResponse,
)
from app.auth.security import create_access_token, hash_password, verify_password
from app.database import get_db_session
from app.models import User


router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post(
    "/register",
    response_model=AuthResponse,
    status_code=status.HTTP_201_CREATED,
)
async def register(
    payload: RegisterRequest,
    session: AsyncSession = Depends(get_db_session),
) -> AuthResponse:
    existing_user = await session.scalar(
        select(User).where(User.email == payload.email)
    )
    if existing_user is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User with this email already exists",
        )

    user = User(
        email=payload.email,
        password_hash=hash_password(payload.password),
        full_name=payload.full_name.strip(),
    )
    session.add(user)

    try:
        await session.flush()
        await session.commit()
    except IntegrityError as error:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User with this email already exists",
        ) from error

    return AuthResponse(
        user=UserResponse.model_validate(user),
        access_token=create_access_token(user.id),
    )


@router.post("/login", response_model=AuthResponse)
async def login(
    payload: LoginRequest,
    session: AsyncSession = Depends(get_db_session),
) -> AuthResponse:
    settings = get_settings()
    if settings.admin_email and payload.email == settings.admin_login.strip().lower():
        user = await session.scalar(select(User).where(
            User.email == settings.admin_email.strip().lower(), User.role == "ADMIN"))
    else:
        user = await session.scalar(select(User).where(User.email == payload.email))
    if user is None or not user.is_active or not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return AuthResponse(
        user=UserResponse.model_validate(user),
        access_token=create_access_token(user.id),
    )


@router.get("/me", response_model=UserResponse)
async def me(user: User = Depends(get_current_user)) -> UserResponse:
    return UserResponse.model_validate(user)
