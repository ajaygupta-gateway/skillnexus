"""
Shared pytest fixtures for SkillNexus test suite.
Uses SQLite in-memory for fast, isolated tests (no PostgreSQL required for unit tests).
"""

import asyncio
import os
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import JSON
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

# Set test env vars BEFORE importing anything from app (config is loaded at import time)
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-that-is-long-enough-32-chars!!")
os.environ.setdefault("JWT_REFRESH_SECRET_KEY", "test-refresh-secret-32chars!!!!!!!!!!!")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("DATABASE_URL_SYNC", "sqlite:///:memory:")
os.environ.setdefault("GEMINI_API_KEY", "test-key")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")

from app.core.database import Base, get_db
from app.core.security import hash_password
from app.models.models import User, UserRole

# Use SQLite in-memory for tests
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


def _patch_jsonb_for_sqlite():
    """
    SQLite doesn't support JSONB. Replace all JSONB columns in models with JSON
    before creating the test schema. This only affects the in-memory test SQLite DB.
    """
    from sqlalchemy.dialects.postgresql import JSONB

    for table in Base.metadata.tables.values():
        for column in table.columns:
            if isinstance(column.type, JSONB):
                column.type = JSON()


@pytest_asyncio.fixture(scope="function")
async def db_engine():
    """Create a fresh in-memory SQLite engine for each test."""
    _patch_jsonb_for_sqlite()

    engine = create_async_engine(
        TEST_DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        echo=False,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def db_session(db_engine) -> AsyncGenerator[AsyncSession, None]:
    """Provide an async DB session for each test."""
    session_factory = async_sessionmaker(
        bind=db_engine,
        class_=AsyncSession,
        autocommit=False,
        autoflush=False,
        expire_on_commit=False,
    )
    async with session_factory() as session:
        yield session


@pytest_asyncio.fixture(scope="function")
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """Provide a test HTTP client with the DB dependency overridden."""
    from app.main import create_app

    app = create_app()

    # Override DB dependency to use the test session
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac


# ── Test Data Factories ────────────────────────────────────────────────────────
@pytest_asyncio.fixture
async def learner_user(db_session: AsyncSession) -> User:
    user = User(
        email="learner@test.com",
        hashed_password=hash_password("TestPass123"),
        display_name="Test Learner",
        role=UserRole.learner,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def admin_user(db_session: AsyncSession) -> User:
    user = User(
        email="admin@test.com",
        hashed_password=hash_password("AdminPass123"),
        display_name="Test Admin",
        role=UserRole.admin,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


async def get_auth_token(client: AsyncClient, email: str, password: str) -> str:
    """Helper to get JWT access token for tests."""
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert response.status_code == 200, f"Login failed: {response.json()}"
    return response.json()["access_token"]


@pytest_asyncio.fixture
async def learner_token(client: AsyncClient, learner_user: User) -> str:
    return await get_auth_token(client, "learner@test.com", "TestPass123")


@pytest_asyncio.fixture
async def admin_token(client: AsyncClient, admin_user: User) -> str:
    return await get_auth_token(client, "admin@test.com", "AdminPass123")
