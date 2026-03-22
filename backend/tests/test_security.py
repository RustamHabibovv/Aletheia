"""Tests for JWT security utilities."""

from jose import jwt

from app.core.config import get_settings
from app.core.security import TokenPayload, decode_jwt


def test_decode_valid_jwt():
    settings = get_settings()
    payload = {"sub": "user-123", "email": "test@example.com", "name": "Test"}
    token = jwt.encode(payload, settings.nextauth_secret, algorithm="HS256")

    result = decode_jwt(token, settings)
    assert isinstance(result, TokenPayload)
    assert result.sub == "user-123"
    assert result.email == "test@example.com"
    assert result.name == "Test"


def test_decode_invalid_jwt():
    settings = get_settings()
    import pytest
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        decode_jwt("invalid-token", settings)
    assert exc_info.value.status_code == 401
