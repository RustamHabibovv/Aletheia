"""User-related schemas."""

import uuid

from pydantic import BaseModel

from app.models import UserTier


class UserResponse(BaseModel):
    id: uuid.UUID
    email: str
    name: str | None
    image: str | None
    tier: UserTier
