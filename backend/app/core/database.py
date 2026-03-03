from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings

# ── Async Engine ───────────────────────────────────────────────────────────────
# SQLite (used in tests) does not support pool_size / max_overflow args
_is_sqlite = settings.DATABASE_URL.startswith("sqlite")

_engine_kwargs = {
    "pool_pre_ping": True,
    "echo": settings.APP_DEBUG,
}

if not _is_sqlite:
    _engine_kwargs.update(
        {
            "pool_size": settings.DB_POOL_SIZE,
            "max_overflow": settings.DB_MAX_OVERFLOW,
            "pool_timeout": settings.DB_POOL_TIMEOUT,
        }
    )

engine = create_async_engine(settings.DATABASE_URL, **_engine_kwargs)

# ── Session Factory ────────────────────────────────────────────────────────────
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
)


# ── Base Declarative Class ─────────────────────────────────────────────────────
class Base(DeclarativeBase):
    pass


# ── Dependency: Get DB Session ─────────────────────────────────────────────────
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
