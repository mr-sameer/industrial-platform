"""
Durable audit trail — see app.models.audit_log and docs/adr/0017-audit-logging.md.
Deliberately a "fire and forget, best-effort" write: a failure to write
an audit row must never block or fail the underlying user-facing
operation, so callers should treat this as non-critical (it commits
independently and swallows nothing silently — errors still propagate to
structlog — but the caller's own transaction/response is not coupled to
audit-log success).
"""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.audit_log import AuditLog

logger = get_logger(__name__)


async def log_event(
    db: AsyncSession,
    event: str,
    *,
    user_id: str | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
    device: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    entry = AuditLog(
        user_id=user_id,
        event=event,
        ip_address=ip_address,
        user_agent=user_agent[:512] if user_agent else None,
        device=device,
        event_metadata=metadata,
    )
    db.add(entry)
    try:
        await db.commit()
    except Exception:  # noqa: BLE001 — audit logging must never break the request
        await db.rollback()
        logger.error("audit_log_write_failed", audit_event=event, user_id=user_id, exc_info=True)
