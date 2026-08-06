"""Pydantic schemas for Module 3A (Company Core). See docs/domain/03-core-entities.md."""

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.models.company import CompanySize, CompanyStatus, VerificationStatus
from app.models.company_member import CompanyMemberStatus, CompanyRole


class CompanyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    legal_name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=5000)
    industry: str | None = Field(default=None, max_length=120)
    website: str | None = Field(default=None, max_length=2048)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=32)
    year_established: int | None = Field(default=None, ge=1800, le=2100)
    company_size: CompanySize | None = None
    gst_number: str | None = Field(default=None, max_length=32)
    country: str | None = Field(default=None, max_length=120)
    state: str | None = Field(default=None, max_length=120)
    city: str | None = Field(default=None, max_length=120)


class CompanyUpdate(BaseModel):
    """
    All fields optional (PATCH semantics). Which fields a given caller may
    actually set is enforced by the service layer based on their
    CompanyRole (Editor cannot change legal_name/gst_number — see
    docs/domain/09-permission-matrix.md footnote 2 — Owner/Admin can
    change anything here), not by this schema.
    """

    name: str | None = Field(default=None, min_length=1, max_length=255)
    legal_name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=5000)
    industry: str | None = Field(default=None, max_length=120)
    website: str | None = Field(default=None, max_length=2048)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=32)
    year_established: int | None = Field(default=None, ge=1800, le=2100)
    company_size: CompanySize | None = None
    gst_number: str | None = Field(default=None, max_length=32)
    country: str | None = Field(default=None, max_length=120)
    state: str | None = Field(default=None, max_length=120)
    city: str | None = Field(default=None, max_length=120)


class CompanyPublic(BaseModel):
    """Public profile shape — GET /companies/{slug}. See docs/domain/03's Company entry / Section 7."""

    id: uuid.UUID
    name: str
    slug: str
    description: str | None
    industry: str | None
    website: str | None
    country: str | None
    city: str | None
    verification_status: VerificationStatus
    member_count: int
    created_at: datetime

    model_config = {"from_attributes": True}


class CompanyDetail(BaseModel):
    """Full profile shape for authenticated members — GET /companies/{id}."""

    id: uuid.UUID
    name: str
    legal_name: str
    slug: str
    description: str | None
    industry: str | None
    website: str | None
    email: str | None
    phone: str | None
    year_established: int | None
    company_size: CompanySize | None
    gst_number: str | None
    country: str | None
    state: str | None
    city: str | None
    status: CompanyStatus
    verification_status: VerificationStatus
    member_count: int
    my_role: CompanyRole
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class CompanySearchResult(BaseModel):
    """Row shape for GET /companies/search — intentionally narrower than CompanyPublic (no description)."""

    id: uuid.UUID
    name: str
    slug: str
    industry: str | None
    country: str | None
    city: str | None
    verification_status: VerificationStatus

    model_config = {"from_attributes": True}


class Page(BaseModel):
    items: list[CompanySearchResult]
    total: int
    page: int
    page_size: int
    total_pages: int


class CompanyMemberCreate(BaseModel):
    user_id: uuid.UUID
    role: CompanyRole = CompanyRole.VIEWER

    @field_validator("role")
    @classmethod
    def cannot_invite_as_owner(cls, v: CompanyRole) -> CompanyRole:
        if v == CompanyRole.OWNER:
            raise ValueError(
                "Cannot invite a member directly as Owner — use ownership transfer instead"
            )
        return v


class CompanyMemberUpdate(BaseModel):
    """
    PATCH body for /companies/{id}/members/{member}. Both fields optional;
    at least one should be set. Setting role=owner is how ownership
    transfer is performed (see app.services.company_service.update_member
    and docs/adr/0024-ownership-transfer-mechanism.md).
    """

    role: CompanyRole | None = None
    status: CompanyMemberStatus | None = None


class CompanyMemberPublic(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    full_name: str
    email: str
    role: CompanyRole
    status: CompanyMemberStatus
    joined_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}
