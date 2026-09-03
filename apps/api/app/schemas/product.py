"""
Pydantic schemas — Phase 4B (Industrial Product Graph). Mirrors
app/schemas/company.py's conventions (from_attributes=True for
ORM-backed read models, separate Create/Update/Public shapes).
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.offering import OfferingRole, OfferingStatus, OfferingVerificationStatus
from app.models.product import ProductStatus
from app.models.product_specification import SpecificationDataType

# ---- ProductCategory ----


class ProductCategoryPublic(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    parent_id: uuid.UUID | None

    model_config = {"from_attributes": True}


class ProductCategoryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    parent_id: uuid.UUID | None = None


# ---- ProductSpecification ----


class ProductSpecificationPublic(BaseModel):
    id: uuid.UUID
    category_id: uuid.UUID
    name: str
    unit: str | None
    datatype: SpecificationDataType
    enum_options: list[str] | None
    required: bool

    model_config = {"from_attributes": True}


class ProductSpecificationCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    unit: str | None = Field(default=None, max_length=40)
    datatype: SpecificationDataType
    enum_options: list[str] | None = None
    required: bool = False


# ---- ProductAttribute ----


class ProductAttributePublic(BaseModel):
    specification_id: uuid.UUID
    specification_name: str
    unit: str | None
    value: str
    # Traceability pointer (additive) — see
    # app.models.product_attribute.ProductAttribute's own docstring:
    # which ProductAttributeEvidence row is currently backing this
    # value, or None if this attribute has no applied evidence trail.
    latest_evidence_id: uuid.UUID | None = None

    model_config = {"from_attributes": True}


class ProductAttributeInput(BaseModel):
    specification_id: uuid.UUID
    value: str = Field(min_length=1, max_length=500)


# ---- Product ----


class ProductCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    product_family: str | None = Field(default=None, max_length=255)
    category_id: uuid.UUID
    industry: str | None = Field(default=None, max_length=120)
    attributes: list[ProductAttributeInput] = Field(default_factory=list)


class ProductUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    product_family: str | None = Field(default=None, max_length=255)
    industry: str | None = Field(default=None, max_length=120)
    status: ProductStatus | None = None
    attributes: list[ProductAttributeInput] | None = None


class ProductSearchResult(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    product_family: str | None
    category_id: uuid.UUID
    industry: str | None
    status: ProductStatus
    offering_count: int = 0

    model_config = {"from_attributes": True}


class ProductDetail(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    description: str | None
    product_family: str | None
    category: ProductCategoryPublic
    industry: str | None
    status: ProductStatus
    attributes: list[ProductAttributePublic]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ProductSearchPage(BaseModel):
    items: list[ProductSearchResult]
    total: int
    page: int
    page_size: int
    total_pages: int


# ---- Offering ----


class OfferingCreate(BaseModel):
    product_id: uuid.UUID
    role: OfferingRole
    moq: str | None = Field(default=None, max_length=120)
    lead_time: str | None = Field(default=None, max_length=120)
    capacity: str | None = Field(default=None, max_length=120)
    country: str | None = Field(default=None, max_length=120)


class OfferingUpdate(BaseModel):
    role: OfferingRole | None = None
    moq: str | None = Field(default=None, max_length=120)
    lead_time: str | None = Field(default=None, max_length=120)
    capacity: str | None = Field(default=None, max_length=120)
    country: str | None = Field(default=None, max_length=120)
    status: OfferingStatus | None = None


class OfferingCompanySummary(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    verification_status: str

    model_config = {"from_attributes": True}


class OfferingProductSummary(BaseModel):
    id: uuid.UUID
    name: str
    slug: str

    model_config = {"from_attributes": True}


class OfferingPublic(BaseModel):
    id: uuid.UUID
    company: OfferingCompanySummary
    product: OfferingProductSummary
    role: OfferingRole
    moq: str | None
    lead_time: str | None
    capacity: str | None
    country: str | None
    verification_status: OfferingVerificationStatus
    status: OfferingStatus
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class OfferingPage(BaseModel):
    items: list[OfferingPublic]
    total: int
    page: int
    page_size: int
    total_pages: int
