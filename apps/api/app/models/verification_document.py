"""
VerificationDocument — Module 3B. Evidence a Company uploads toward
verification (GST certificate, ISO/CE/BIS certs, factory license, etc.).
See docs/domain/03-core-entities.md's `Certificate`/`Document` entries
for the long-term domain model this is a scoped implementation of, and
docs/adr/0029-module-3b-verification-and-identity.md for what's
deliberately simplified here (no admin-approval workflow yet —
`verified_by`/`verified_at` are placeholder fields nothing sets today,
exactly as the module brief specifies).
"""

import enum
import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Date, DateTime, Enum, ForeignKey, Index, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.enum_utils import str_enum_values
from app.db.session import Base

if TYPE_CHECKING:
    from app.models.company import Company


class DocumentType(str, enum.Enum):
    GST_CERTIFICATE = "gst_certificate"
    MSME = "msme"
    ISO = "iso"
    CE = "ce"
    BIS = "bis"
    FACTORY_LICENSE = "factory_license"
    IMPORT_EXPORT_CODE = "import_export_code"
    BUSINESS_REGISTRATION = "business_registration"
    OTHER = "other"


class DocumentFileType(str, enum.Enum):
    PDF = "pdf"
    IMAGE = "image"


class DocumentStatus(str, enum.Enum):
    """
    No status here is ever set by the uploader themselves — `pending` is
    the only status this module's endpoints can produce. `verified` and
    `rejected` are reachable only through the (placeholder, unbuilt)
    admin-review workflow; `expired` is derived from `expiry_date`, not
    manually set. See VerificationScoreService for how `status` and
    `expiry_date` both feed into scoring.
    """

    PENDING = "pending"
    VERIFIED = "verified"
    REJECTED = "rejected"
    EXPIRED = "expired"


class VerificationDocument(Base):
    __tablename__ = "verification_documents"
    __table_args__ = (
        Index("ix_verification_documents_company_id", "company_id"),
        Index("ix_verification_documents_document_type", "document_type"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )

    document_type: Mapped[DocumentType] = mapped_column(
        Enum(DocumentType, name="document_type", native_enum=True, values_callable=str_enum_values),
        nullable=False,
    )
    file_type: Mapped[DocumentFileType] = mapped_column(
        Enum(
            DocumentFileType,
            name="document_file_type",
            native_enum=True,
            values_callable=str_enum_values,
        ),
        nullable=False,
    )
    file_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    status: Mapped[DocumentStatus] = mapped_column(
        Enum(
            DocumentStatus,
            name="document_status",
            native_enum=True,
            values_callable=str_enum_values,
        ),
        default=DocumentStatus.PENDING,
        nullable=False,
    )

    uploaded_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    verified_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    expiry_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    # Versioning: "replace" creates a new row (version = old.version + 1,
    # same document_type) and soft-deletes the old one, pointing forward
    # via superseded_by_id — see docs/architecture/company-verification-sequences.md.
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    superseded_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("verification_documents.id"), nullable=True
    )

    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deleted_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    company: Mapped["Company"] = relationship("Company", back_populates="documents")

    @property
    def is_expired(self) -> bool:
        from datetime import UTC

        return self.expiry_date is not None and self.expiry_date < datetime.now(UTC).date()

    def __repr__(self) -> str:  # pragma: no cover — debug convenience only
        return f"<VerificationDocument id={self.id} type={self.document_type} status={self.status}>"
