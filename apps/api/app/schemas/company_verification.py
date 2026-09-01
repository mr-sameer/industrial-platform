"""Pydantic schemas — Module 3B (Company Verification & Industrial Identity),
extended in Phase 1 of the admin document-verification review workflow."""

import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, HttpUrl

from app.core.verification_rules import VerificationLevel
from app.models.company import BusinessType, LegalEntityType
from app.models.company_social_link import SocialPlatform
from app.models.verification_document import DocumentFileType, DocumentStatus, DocumentType


class BusinessInfoUpdate(BaseModel):
    """
    PATCH body for /companies/{id}/business-info. All fields optional
    (partial update). `gst_number` (Module 3A's existing field) is
    updatable here too, since it's conceptually part of business info —
    see docs/adr/0029.
    """

    legal_entity_type: LegalEntityType | None = None
    business_type: BusinessType | None = None
    export_capable: bool | None = None
    gst_number: str | None = Field(default=None, max_length=32)
    pan: str | None = Field(default=None, max_length=16)
    cin: str | None = Field(default=None, max_length=32)
    msme_number: str | None = Field(default=None, max_length=32)
    iec_number: str | None = Field(default=None, max_length=32)
    tax_registration: str | None = Field(default=None, max_length=64)
    business_registration_date: date | None = None

    short_description: str | None = Field(default=None, max_length=500)
    description: str | None = Field(
        default=None, max_length=5000
    )  # Module 3A's field — the "long description"
    mission: str | None = Field(default=None, max_length=2000)
    vision: str | None = Field(default=None, max_length=2000)
    core_values: list[str] | None = Field(default=None, max_length=20)
    capabilities: list[str] | None = Field(default=None, max_length=30)
    manufacturing_expertise: list[str] | None = Field(default=None, max_length=30)

    secondary_industries: list[str] | None = Field(default=None, max_length=20)
    product_categories: list[str] | None = Field(default=None, max_length=30)
    manufacturing_categories: list[str] | None = Field(default=None, max_length=30)
    export_categories: list[str] | None = Field(default=None, max_length=30)
    naics_sic_code: str | None = Field(default=None, max_length=16)


class BusinessInfoDetail(BaseModel):
    """
    GET .../business-info response — the read-side counterpart to
    BusinessInfoUpdate, since Module 3A's CompanyDetail (deliberately
    untouched — see docs/adr/0029) doesn't expose any Module 3B field.
    Every field here mirrors BusinessInfoUpdate's field set exactly.
    """

    legal_entity_type: LegalEntityType | None
    business_type: BusinessType | None
    export_capable: bool
    gst_number: str | None
    pan: str | None
    cin: str | None
    msme_number: str | None
    iec_number: str | None
    tax_registration: str | None
    business_registration_date: date | None

    short_description: str | None
    description: str | None
    mission: str | None
    vision: str | None
    core_values: list[str] | None
    capabilities: list[str] | None
    manufacturing_expertise: list[str] | None

    secondary_industries: list[str] | None
    product_categories: list[str] | None
    manufacturing_categories: list[str] | None
    export_categories: list[str] | None
    naics_sic_code: str | None

    model_config = {"from_attributes": True}


class SocialLinkUpsert(BaseModel):
    platform: SocialPlatform
    url: HttpUrl


class SocialLinkPublic(BaseModel):
    platform: SocialPlatform
    url: str

    model_config = {"from_attributes": True}


class VerificationDocumentPublic(BaseModel):
    id: uuid.UUID
    document_type: DocumentType
    file_type: DocumentFileType
    file_url: str
    status: DocumentStatus
    uploaded_at: datetime
    verified_at: datetime | None
    # The reviewer's rejection reason (None on approval or before review)
    # — see document_service.review_document. Deliberately no
    # `verified_by` here: this is a public-facing shape (the company's
    # own Documents page), and exposing which platform admin reviewed a
    # document isn't needed by any consumer today — see who set it via
    # the DB column directly if that's ever needed.
    review_note: str | None
    expiry_date: date | None
    version: int
    is_expired: bool

    model_config = {"from_attributes": True}


class DocumentReviewRequest(BaseModel):
    """POST body for /companies/{id}/documents/{document_id}/review — platform-admin-only, see
    app.core.dependencies.require_role(Role.ADMIN) at the router layer, never CompanyRole."""

    decision: Literal["approve", "reject"]
    note: str | None = Field(default=None, max_length=2000)


class MissingRequirementPublic(BaseModel):
    key: str
    label: str
    weight: int
    level: VerificationLevel


class VerificationScorePublic(BaseModel):
    """
    Response shape for GET /companies/{id}/verification — and embedded
    in the public profile (a subset — see CompanyPublicWithVerification
    in app.api.v1.company_verification). Always computed live; see
    app.services.verification_score_service's module docstring for why
    there is no corresponding write endpoint anywhere.
    """

    percentage: int
    level: VerificationLevel
    readiness_score: int
    next_level: VerificationLevel | None
    missing_requirements: list[MissingRequirementPublic]
    satisfied_requirement_keys: list[str]


class CompanyBrandingPublic(BaseModel):
    logo_url: str | None
    logo_thumbnail_url: str | None
    cover_image_url: str | None
