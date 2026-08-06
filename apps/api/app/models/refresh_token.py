"""
RefreshToken ORM model — the rotation history for a Session. The value
handed to a client is never stored; only a SHA-256 hash of its secret
half is (see app.core.opaque_tokens). Exactly one row per session should
have `used_at IS NULL` at any time — that row is the currently valid
token. See docs/adr/0014-refresh-token-and-session-model.md for the full
rotation/reuse-detection design.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    token_hash: Mapped[str] = mapped_column(
        String(64), nullable=False, index=True
    )  # sha256 hex digest

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    replaced_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("refresh_tokens.id"), nullable=True
    )

    def __repr__(self) -> str:  # pragma: no cover — debug convenience only
        return f"<RefreshToken id={self.id} session_id={self.session_id} used={self.used_at is not None}>"
