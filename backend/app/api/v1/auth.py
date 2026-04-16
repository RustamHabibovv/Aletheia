"""Authentication endpoints — register and login."""

import logging

from fastapi import APIRouter, HTTPException, status
from sqlmodel import select

from app.api.deps import DBSession
from app.core.security import hash_password, verify_password
from app.models import User
from app.schemas.user import AuthUserResponse, LoginRequest, RegisterRequest

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=AuthUserResponse, status_code=status.HTTP_201_CREATED)
async def register(body: RegisterRequest, session: DBSession) -> AuthUserResponse:
    """Create a new user account with email + password."""
    result = await session.execute(select(User).where(User.email == body.email))
    if result.scalar_one_or_none() is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

    user = User(
        email=body.email,
        name=body.name or body.email.split("@")[0],
        hashed_password=hash_password(body.password),
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    logger.info("Registered new user: %s", user.email)
    return AuthUserResponse(id=user.id, email=user.email, name=user.name, image=user.image, tier=user.tier)


@router.post("/login", response_model=AuthUserResponse)
async def login(body: LoginRequest, session: DBSession) -> AuthUserResponse:
    """Validate email + password and return user data (NextAuth issues the session JWT)."""
    result = await session.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()

    if user is None or user.hashed_password is None or not verify_password(body.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")

    return AuthUserResponse(id=user.id, email=user.email, name=user.name, image=user.image, tier=user.tier)
