import pytest
from config import SESSIONS


@pytest.mark.asyncio
async def test_health_check(client):
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


@pytest.mark.asyncio
async def test_root_endpoint(client):
    response = await client.get("/")
    assert response.status_code == 200
    assert response.json() == {"status": "online"}


@pytest.mark.asyncio
async def test_login_validation_rejects_empty_payload(client):
    response = await client.post("/login", json={})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_login_validation_rejects_short_email(client):
    response = await client.post("/login", json={"email": "a", "password": "valid_password"})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_session_status_404_for_unknown_token(client):
    response = await client.get("/session-status/unknown_token_12345")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_session_status_for_known_session(client):
    token = "test_known_session_token"
    SESSIONS[token] = {
        "token": token,
        "email": "user@example.com",
        "status": "initiating",
        "created_at": "2026-08-30T12:00:00+00:00",
        "expires_at": "2026-08-30T18:00:00+00:00",
    }
    response = await client.get(f"/session-status/{token}")
    assert response.status_code == 200
    data = response.json()
    assert data["token"] == token
    assert data["status"] == "initiating"
