"""Lightweight, dependency-free connectivity probes used by the health endpoint."""

import time

from sqlalchemy import text

from app.core.logging import get_logger
from app.db.session import get_engine

logger = get_logger(__name__)


async def check_database() -> tuple[str, float | None, str | None]:
    """Returns (status, latency_ms, message)."""
    start = time.perf_counter()
    try:
        engine = get_engine()
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        latency_ms = round((time.perf_counter() - start) * 1000, 2)
        return "ok", latency_ms, None
    except Exception as exc:  # noqa: BLE001 — deliberately broad: this is a probe, not business logic
        logger.warning("database_health_check_failed", error=str(exc))
        return "down", None, "Database unreachable"
