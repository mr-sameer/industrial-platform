"""
CompanySocialLink — Module 3B. Deliberately does NOT include "website" as
a platform — Module 3A's `Company.website` column already covers that
(see docs/adr/0029). Covers exactly the remaining platforms the module
brief lists: LinkedIn, YouTube, Facebook, Instagram, X.
"""

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.enum_utils import str_enum_values
from app.db.session import Base

if TYPE_CHECKING:
    from app.models.company import Company


class SocialPlatform(str, enum.Enum):
    LINKEDIN = "linkedin"
    YOUTUBE = "youtube"
    FACEBOOK = "facebook"
    INSTAGRAM = "instagram"
    X = "x"


class CompanySocialLink(Base):
    __tablename__ = "company_social_links"
    __table_args__ = (
        # One link per platform per company — updating re-uses the row
        # rather than accumulating duplicates.
        UniqueConstraint("company_id", "platform", name="uq_company_social_links_company_platform"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )
    platform: Mapped[SocialPlatform] = mapped_column(
        Enum(
            SocialPlatform,
            name="social_platform",
            native_enum=True,
            values_callable=str_enum_values,
        ),
        nullable=False,
    )
    url: Mapped[str] = mapped_column(String(2048), nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    company: Mapped["Company"] = relationship("Company", back_populates="social_links")

    def __repr__(self) -> str:  # pragma: no cover — debug convenience only
        return f"<CompanySocialLink company_id={self.company_id} platform={self.platform}>"
