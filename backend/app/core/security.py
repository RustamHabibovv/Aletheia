"""JWT security utilities for verifying Auth.js (NextAuth v5) tokens."""

import logging
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.core.config import Settings, get_settings
from app.db.session import get_session
from app.models import User

logger = logging.getLogger(__name__)

bearer_scheme = HTTPBearer(auto_error=False)


class TokenPayload(BaseModel):
    """Expected claims from Auth.js JWT."""

    sub: str  # user id or email
    email: str | None = None
    name: str | None = None
    picture: str | None = None


def decode_jwt(token: str, settings: Settings) -> TokenPayload:
    """Decode and verify a JWT issued by Auth.js."""
    try:
        payload = jwt.decode(
            token,
            settings.nextauth_secret,
            algorithms=["HS256"],
            options={"verify_aud": False},
        )
        return TokenPayload(**payload)
    except JWTError as e:
        logger.warning("JWT verification failed: %s", e)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from e


async def get_or_create_user(
    token_data: TokenPayload,
    session: AsyncSession,
) -> User:
    """Look up user by email, or create on first API call."""
    email = token_data.email
    if not email:
        logger.warning("JWT missing required 'email' claim for sub %s", token_data.sub)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token missing required email claim",
            headers={"WWW-Authenticate": "Bearer"},
        )
    stmt = select(User).where(User.email == email)
    result = await session.execute(stmt)
    user = result.scalar_one_or_none()

    if user is None:
        user = User(
            email=email,
            name=token_data.name,
            image=token_data.picture,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        logger.info("Created new user: %s", email)

    return user


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    settings: Annotated[Settings, Depends(get_settings)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> User:
    """FastAPI dependency: extract and verify JWT, return the User."""
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token_data = decode_jwt(credentials.credentials, settings)
    return await get_or_create_user(token_data, session)
