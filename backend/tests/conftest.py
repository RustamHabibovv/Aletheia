"""Shared test fixtures."""

import pytest
from fastapi.testclient import TestClient
from jose import jwt

from app.core.config import get_settings
from app.main import app


@pytest.fixture
def settings():
    return get_settings()


@pytest.fixture
def test_jwt(settings) -> str:
    """Generate a valid JWT for testing."""
    payload = {
        "sub": "test-user-id",
        "email": "test@example.com",
        "name": "Test User",
        "picture": None,
    }
    return jwt.encode(payload, settings.nextauth_secret, algorithm="HS256")


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def auth_headers(test_jwt) -> dict[str, str]:
    return {"Authorization": f"Bearer {test_jwt}"}
