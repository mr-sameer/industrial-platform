"""
Async SQLAlchemy engine/session wiring.

Module 1 ships no ORM models yet — Base is exported so future modules can
declare models against a single shared metadata object, and get_db is
wired up as a FastAPI dependency so routers can start depending on it
without any code changes when real models land.
"""

from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.core.config import get_settings

settings = get_settings()


class Base(DeclarativeBase):
    """Shared declarative base for all future ORM models."""


_engine: AsyncEngine = create_async_engine(
    settings.database_url,
    pool_size=settings.db_pool_size,
    max_overflow=settings.db_max_overflow,
    pool_pre_ping=True,
    echo=False,
)

AsyncSessionLocal = async_sessionmaker(bind=_engine, expire_on_commit=False, autoflush=False)


def get_engine() -> AsyncEngine:
    return _engine


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency yielding a request-scoped session."""
    async with AsyncSessionLocal() as session:
        yield session


# Annotated alias — use this in route signatures (`db: DbSession`) instead
# of `db: AsyncSession = Depends(get_db)`, which ruff/bugbear (B008) flags
# as a function call in a default argument. Matches the CurrentUser
# pattern in app.core.dependencies.
DbSession = Annotated[AsyncSession, Depends(get_db)]
