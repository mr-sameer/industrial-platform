"""
SourceRegistry — Module 5A. The concrete registry of known source
instances, per docs/product/phase-5-industrial-data-acquisition-architecture.md
Section 3 (Data Source Taxonomy) and Section 25's 5.1 sequencing.

Nothing collects from these sources yet — Module 5A builds the
registry and provenance foundation only, per that module's own
explicit scope ("Do NOT build web crawlers yet"). A SourceRegistry row
existing does not imply anything has been collected from it; it is the
prerequisite structure for recording *how* something was collected,
once collection exists.
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.enum_utils import str_enum_values
from app.db.session import Base


class SourceClass(str, enum.Enum):
    """The six source classes from the architecture doc's Section 3."""

    COMPANY_OWNED = "company_owned"
    PUBLIC_GOVERNMENT = "public_government"
    THIRD_PARTY_STRUCTURED = "third_party_structured"
    NEWS_PUBLICATION = "news_publication"
    ASSOCIATION_DIRECTORY = "association_directory"
    USER_CONTRIBUTION = "user_contribution"


class CollectionMethod(str, enum.Enum):
    MANUAL = "manual"
    API = "api"
    STRUCTURED_FILE = "structured_file"
    USER_SUBMISSION = "user_submission"
    OTHER = "other"


class CollectionPolicyStatus(str, enum.Enum):
    """
    Section 21 (Legal / Compliance Boundaries) made concrete and
    actionable: a source can be marked ineligible for collection
    entirely, independent of any code change, once legal review
    (never performed by this system) reaches a conclusion.
    """

    ALLOWED = "allowed"
    RESTRICTED = "restricted"
    BLOCKED = "blocked"
    PENDING_LEGAL_REVIEW = "pending_legal_review"


class SourceRegistry(Base):
    __tablename__ = "source_registry"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    source_class: Mapped[SourceClass] = mapped_column(
        Enum(SourceClass, name="source_class", native_enum=True, values_callable=str_enum_values),
        nullable=False,
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    base_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    # 0.0-1.0 — a per-instance reliability weight informed by, but not
    # identical to, the source class's general reliability assessment
    # in Section 3 (an individual source within a class can be more or
    # less reliable than that class's typical case).
    reliability_weight: Mapped[float] = mapped_column(
        nullable=False, default=0.5, server_default="0.5"
    )
    collection_method: Mapped[CollectionMethod] = mapped_column(
        Enum(
            CollectionMethod,
            name="collection_method",
            native_enum=True,
            values_callable=str_enum_values,
        ),
        nullable=False,
    )
    collection_policy_status: Mapped[CollectionPolicyStatus] = mapped_column(
        Enum(
            CollectionPolicyStatus,
            name="collection_policy_status",
            native_enum=True,
            values_callable=str_enum_values,
        ),
        nullable=False,
        default=CollectionPolicyStatus.PENDING_LEGAL_REVIEW,
        server_default=CollectionPolicyStatus.PENDING_LEGAL_REVIEW.value,
    )
    # ISO 3166 country code, or "global" — Section 3's geographic
    # coverage dimension. Free text, not an enum: matches Section 9's
    # extensibility principle (a normalization table, not hardcoded
    # logic) rather than a closed country-code enum baked into DDL.
    geographic_scope: Mapped[str | None] = mapped_column(String(32), nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
