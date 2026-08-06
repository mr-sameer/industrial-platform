"""
Session ORM model — one row per login (i.e. per device/browser). A
session's lifetime is tracked independently of any single refresh token:
`refresh_tokens` (see refresh_token.py) holds the rotation history for a
session, but revoking/expiring/inspecting a session is a first-class,
directly queryable operation. See docs/adr/0014-refresh-token-and-session-model.md.
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.enum_utils import str_enum_values
from app.db.session import Base


class SessionRevokedReason(str, enum.Enum):
    LOGOUT = "logout"
    LOGOUT_ALL = "logout_all"
    REUSE_DETECTED = "reuse_detected"
    PASSWORD_RESET = "password_reset"
    ADMIN_REVOKED = "admin_revoked"


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Populated from the client-supplied device_name (optional) and a
    # best-effort parse of the User-Agent header (see app.core.user_agent).
    # None of this is a security boundary — it's for the "your active
    # sessions" UI, so a spoofed User-Agent only affects display, never
    # authorization.
    device_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    browser: Mapped[str | None] = mapped_column(String(100), nullable=True)
    platform: Mapped[str | None] = mapped_column(String(100), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(
        String(45), nullable=True
    )  # long enough for IPv6

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_active_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )

    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_reason: Mapped[SessionRevokedReason | None] = mapped_column(
        Enum(
            SessionRevokedReason,
            name="session_revoked_reason",
            native_enum=True,
            values_callable=str_enum_values,
        ),
        nullable=True,
    )

    @property
    def is_active(self) -> bool:
        return self.revoked_at is None

    def __repr__(self) -> str:  # pragma: no cover — debug convenience only
        return f"<Session id={self.id} user_id={self.user_id} active={self.is_active}>"
