"""
Tests for Auth endpoints: register, login, refresh, logout.
"""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_register_success(client: AsyncClient):
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "newuser@test.com",
            "password": "SecurePass123",
            "display_name": "New User",
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert data["email"] == "newuser@test.com"
    assert data["display_name"] == "New User"
    assert data["role"] == "learner"
    assert data["xp_balance"] == 0
    assert "hashed_password" not in data


@pytest.mark.asyncio
async def test_register_duplicate_email(client: AsyncClient):
    # First registration
    await client.post(
        "/api/v1/auth/register",
        json={
            "email": "dup@test.com",
            "password": "SecurePass123",
            "display_name": "User 1",
        },
    )
    # Second registration with same email
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "dup@test.com",
            "password": "SecurePass123",
            "display_name": "User 2",
        },
    )
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_register_weak_password(client: AsyncClient):
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "weak@test.com",
            "password": "weakpass",  # No uppercase, no digit
            "display_name": "Weak User",
        },
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_login_success(client: AsyncClient, learner_user):
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "learner@test.com", "password": "TestPass123"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_login_wrong_password(client: AsyncClient, learner_user):
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "learner@test.com", "password": "WrongPass123"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_login_nonexistent_email(client: AsyncClient):
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "nobody@test.com", "password": "SomePass123"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_refresh_token(client: AsyncClient, learner_user):
    # Login to get tokens
    login_response = await client.post(
        "/api/v1/auth/login",
        json={"email": "learner@test.com", "password": "TestPass123"},
    )
    refresh_token = login_response.json()["refresh_token"]

    # Use refresh token
    response = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh_token},
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data


@pytest.mark.asyncio
async def test_logout(client: AsyncClient, learner_user):
    login_response = await client.post(
        "/api/v1/auth/login",
        json={"email": "learner@test.com", "password": "TestPass123"},
    )
    refresh_token = login_response.json()["refresh_token"]

    response = await client.post(
        "/api/v1/auth/logout",
        json={"refresh_token": refresh_token},
    )
    assert response.status_code == 200

    # Revoked token should no longer work
    response2 = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh_token},
    )
    assert response2.status_code == 401


@pytest.mark.asyncio
async def test_get_me_authenticated(client: AsyncClient, learner_token: str):
    response = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {learner_token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == "learner@test.com"


@pytest.mark.asyncio
async def test_get_me_unauthenticated(client: AsyncClient):
    response = await client.get("/api/v1/auth/me")
    assert response.status_code == 401
