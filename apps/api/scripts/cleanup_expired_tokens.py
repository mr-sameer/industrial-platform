#!/usr/bin/env python3
"""
Deletes expired sessions (and, via ON DELETE CASCADE, their refresh
tokens) past a grace period. No task scheduler (Celery/APScheduler/etc.)
exists in this codebase yet (see docs/adr/0003's consequences), so this
ships as a standalone script rather than a registered periodic job —
run it via an external cron / CI scheduled workflow / k8s CronJob:

    cd apps/api && python scripts/cleanup_expired_tokens.py

Exits 0 and prints the number of sessions deleted. Safe to run
repeatedly — it only ever deletes rows that are already past their
grace period, and it does not touch anything else in the system.
"""

import asyncio
import sys
from pathlib import Path

# Allows running as `python scripts/cleanup_expired_tokens.py` directly
# from apps/api, without requiring PYTHONPATH to be set manually.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.logging import configure_logging, get_logger  # noqa: E402
from app.db.session import AsyncSessionLocal  # noqa: E402
from app.services.session_service import cleanup_expired_sessions  # noqa: E402


async def main() -> None:
    configure_logging()
    logger = get_logger(__name__)
    async with AsyncSessionLocal() as db:
        count = await cleanup_expired_sessions(db)
        logger.info("expired_sessions_cleaned_up", count=count)
    print(f"Deleted {count} expired session(s).")


if __name__ == "__main__":
    asyncio.run(main())
