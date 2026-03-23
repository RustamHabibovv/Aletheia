"""Tests for conversation and message endpoints."""

import pytest


@pytest.fixture
def auth_client(client, auth_headers):
    """Return a TestClient wrapper that always sends auth headers."""

    class AuthClient:
        def get(self, url, **kw):
            return client.get(url, headers=auth_headers, **kw)

        def post(self, url, **kw):
            return client.post(url, headers=auth_headers, **kw)

        def patch(self, url, **kw):
            return client.patch(url, headers=auth_headers, **kw)

        def delete(self, url, **kw):
            return client.delete(url, headers=auth_headers, **kw)

    return AuthClient()


# ── auth guard ─────────────────────────────────────────────────────


def test_list_conversations_requires_auth(client):
    assert client.get("/api/v1/conversations").status_code == 401


def test_create_conversation_requires_auth(client):
    assert client.post("/api/v1/conversations", json={}).status_code == 401


# ── create ─────────────────────────────────────────────────────────


def test_create_conversation_default_title(auth_client):
    r = auth_client.post("/api/v1/conversations", json={})
    assert r.status_code == 201
    data = r.json()
    assert data["title"] == "New Conversation"
    assert "id" in data


def test_create_conversation_custom_title(auth_client):
    r = auth_client.post("/api/v1/conversations", json={"title": "My Chat"})
    assert r.status_code == 201
    assert r.json()["title"] == "My Chat"


# ── list ───────────────────────────────────────────────────────────


def test_list_conversations_empty(auth_client):
    r = auth_client.get("/api/v1/conversations")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_list_conversations_returns_created(auth_client):
    auth_client.post("/api/v1/conversations", json={"title": "Chat A"})
    auth_client.post("/api/v1/conversations", json={"title": "Chat B"})
    r = auth_client.get("/api/v1/conversations")
    assert r.status_code == 200
    titles = [c["title"] for c in r.json()]
    assert "Chat A" in titles
    assert "Chat B" in titles


# ── get ────────────────────────────────────────────────────────────


def test_get_conversation_with_messages(auth_client):
    conv_id = auth_client.post("/api/v1/conversations", json={"title": "Q&A"}).json()["id"]
    auth_client.post(f"/api/v1/conversations/{conv_id}/messages", json={"content": "Hello"})
    r = auth_client.get(f"/api/v1/conversations/{conv_id}")
    assert r.status_code == 200
    data = r.json()
    assert data["title"] == "Q&A"
    assert len(data["messages"]) == 1
    assert data["messages"][0]["content"] == "Hello"


def test_get_conversation_not_found(auth_client):
    r = auth_client.get("/api/v1/conversations/00000000-0000-0000-0000-000000000000")
    assert r.status_code == 404


# ── rename ─────────────────────────────────────────────────────────


def test_rename_conversation(auth_client):
    conv_id = auth_client.post("/api/v1/conversations", json={"title": "Old"}).json()["id"]
    r = auth_client.patch(f"/api/v1/conversations/{conv_id}", json={"title": "New"})
    assert r.status_code == 200
    assert r.json()["title"] == "New"


# ── delete ─────────────────────────────────────────────────────────


def test_delete_conversation(auth_client):
    conv_id = auth_client.post("/api/v1/conversations", json={}).json()["id"]
    r = auth_client.delete(f"/api/v1/conversations/{conv_id}")
    assert r.status_code == 204
    assert auth_client.get(f"/api/v1/conversations/{conv_id}").status_code == 404


# ── messages ───────────────────────────────────────────────────────


def test_add_message(auth_client):
    conv_id = auth_client.post("/api/v1/conversations", json={}).json()["id"]
    r = auth_client.post(
        f"/api/v1/conversations/{conv_id}/messages",
        json={"role": "USER", "content": "What is 2+2?"},
    )
    assert r.status_code == 201
    data = r.json()
    assert data["content"] == "What is 2+2?"
    assert data["role"] == "USER"


def test_list_messages(auth_client):
    conv_id = auth_client.post("/api/v1/conversations", json={}).json()["id"]
    auth_client.post(f"/api/v1/conversations/{conv_id}/messages", json={"content": "First"})
    auth_client.post(f"/api/v1/conversations/{conv_id}/messages", json={"content": "Second"})
    r = auth_client.get(f"/api/v1/conversations/{conv_id}/messages")
    assert r.status_code == 200
    contents = [m["content"] for m in r.json()]
    assert contents == ["First", "Second"]


def test_add_message_to_missing_conversation(auth_client):
    r = auth_client.post(
        "/api/v1/conversations/00000000-0000-0000-0000-000000000000/messages",
        json={"content": "ghost"},
    )
    assert r.status_code == 404
