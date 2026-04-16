"""User-related schemas."""

import uuid

from pydantic import BaseModel, EmailStr

from app.models import UserTier


class UserResponse(BaseModel):
    id: uuid.UUID
    email: str
    name: str | None
    image: str | None
    tier: UserTier


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    name: str | None = None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class AuthUserResponse(BaseModel):
    id: uuid.UUID
    email: str
    name: str | None
    image: str | None
    tier: UserTier
