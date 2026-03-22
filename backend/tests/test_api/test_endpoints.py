"""Tests for core API endpoints."""


def test_health_check(client):
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "version" in data


def test_openapi_docs_available(client, settings):
    """Docs should be available when DEBUG=true."""
    if settings.debug:
        response = client.get("/docs")
        assert response.status_code == 200
    else:
        response = client.get("/docs")
        assert response.status_code == 404


def test_users_me_requires_auth(client):
    response = client.get("/api/v1/users/me")
    assert response.status_code == 401
