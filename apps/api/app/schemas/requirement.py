"""
Pydantic schemas — Module 7A-1 (Requirement Intelligence foundation) and
Module 7A-2 (Requirement Matching & Ranking Engine, additive — see the
"---- Matches (Module 7A-2) ----" section below). Mirrors
app/schemas/product.py's conventions (from_attributes=True for
ORM-backed read models, a manually-built response for fields not
directly on the ORM row — see app.api.v1.requirements._to_detail for
why, same reason as product.py's own _to_detail).
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field, model_validator

from app.models.requirement import CriterionOperator, RequirementStatus

# A scalar for eq/gte/lte, a 2-element list for range, an N-element
# list for in — see app.models.requirement's own docstring for why
# this shape (not a delimited string) was chosen.
CriterionValue = float | str | list[float | str]


# ---- RequirementSpecificationCriterion ----


class RequirementSpecificationCriterionInput(BaseModel):
    specification_id: uuid.UUID
    operator: CriterionOperator
    value: CriterionValue

    @model_validator(mode="after")
    def _validate_value_shape(self) -> "RequirementSpecificationCriterionInput":
        """
        Structural validation only (is the shape right for this
        operator?) — whether the specification itself supports this
        operator (e.g. `gte` against a TEXT spec) requires a DB lookup
        and is checked at the service layer
        (app.services.requirement_service), not here.
        """
        if self.operator == CriterionOperator.RANGE:
            if not isinstance(self.value, list) or len(self.value) != 2:
                raise ValueError(
                    "operator 'range' requires a value of exactly two numbers [min, max]"
                )
            low, high = self.value
            if isinstance(low, str) or isinstance(high, str):
                raise ValueError("operator 'range' requires both bounds to be numeric")
            if low > high:
                raise ValueError("operator 'range' requires min <= max")
        elif self.operator == CriterionOperator.IN:
            if not isinstance(self.value, list) or len(self.value) < 1:
                raise ValueError("operator 'in' requires a non-empty list of values")
        elif self.operator in (CriterionOperator.GTE, CriterionOperator.LTE):
            if isinstance(self.value, list | str):
                raise ValueError(
                    f"operator {self.operator.value!r} requires a single numeric value"
                )
        else:  # EQ — any single scalar (string or number) is valid
            if isinstance(self.value, list):
                raise ValueError("operator 'eq' requires a single scalar value")
        return self


class RequirementSpecificationCriterionPublic(BaseModel):
    id: uuid.UUID
    specification_id: uuid.UUID
    specification_name: str
    operator: CriterionOperator
    value: CriterionValue

    model_config = {"from_attributes": True}


# ---- Requirement ----


class RequirementCreate(BaseModel):
    raw_query: str = Field(min_length=1, max_length=5000)
    product_category_id: uuid.UUID | None = None
    industry: str | None = Field(default=None, max_length=120)
    country: str | None = Field(default=None, max_length=120)
    state: str | None = Field(default=None, max_length=120)
    city: str | None = Field(default=None, max_length=120)
    certifications: list[str] | None = None
    # Captured, not matched on, in this phase — see app.models.requirement.
    quantity: str | None = Field(default=None, max_length=120)
    budget: str | None = Field(default=None, max_length=120)
    timeline: str | None = Field(default=None, max_length=120)
    extraction_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    criteria: list[RequirementSpecificationCriterionInput] = Field(default_factory=list)


class RequirementDetail(BaseModel):
    id: uuid.UUID
    created_by: uuid.UUID
    raw_query: str
    product_category_id: uuid.UUID | None
    industry: str | None
    country: str | None
    state: str | None
    city: str | None
    certifications: list[str] | None
    quantity: str | None
    budget: str | None
    timeline: str | None
    status: RequirementStatus
    extraction_confidence: float | None
    criteria: list[RequirementSpecificationCriterionPublic]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ---- Matches (Module 7A-2) ----
# Every class below is constructed explicitly from
# app.services.requirement_matching_service's dataclasses by
# app.api.v1.requirements._to_match_dto — never from_attributes=True
# over the ORM directly, matching this file's own established pattern.
# Field shapes mirror
# docs/product/phase-7a-requirement-intelligence-architecture.md
# Section 13 exactly, resolved with the Option B decision: NO
# pagination, NO output cap beyond the existing 500-candidate
# retrieval ceiling — `matches` is every surviving candidate from the
# bounded working set, and `returned_count == len(matches)`.


class RequirementMatchCategorySignal(BaseModel):
    matched: bool


class RequirementMatchCriterionSignal(BaseModel):
    specification_id: uuid.UUID
    specification_name: str
    operator: CriterionOperator
    requirement_value: CriterionValue
    # ProductAttribute.value is genuinely a plain string in the
    # database (app.models.product_attribute's own EAV design,
    # app.schemas.product.ProductAttributePublic's own precedent) —
    # this is the real canonical type, not a convenience stringification.
    candidate_value: str | None
    status: str


class RequirementMatchLocationSignal(BaseModel):
    requested: dict[str, str | None]
    candidate: dict[str, str | None]
    points_earned: float
    points_possible: float


class RequirementMatchCertificationSignal(BaseModel):
    requested: list[str]
    evidence_found: list[str]
    points_earned: float
    points_possible: float
    confidence: str
    note: str | None


class RequirementMatchTrustSignal(BaseModel):
    level: str
    points_earned: float
    points_possible: float


class RequirementMatchSignals(BaseModel):
    category: RequirementMatchCategorySignal
    criteria: list[RequirementMatchCriterionSignal]
    location: RequirementMatchLocationSignal
    certifications: RequirementMatchCertificationSignal
    trust_tier: RequirementMatchTrustSignal


class RequirementMatchOfferingDetails(BaseModel):
    """
    The real Offering fields (role/MOQ/lead_time/capacity) already
    exist on `candidate.offering` inside requirement_matching_service —
    this is purely a response-contract addition, never a new query and
    never a new scored signal. `moq`/`lead_time`/`capacity` are the
    same free-text, possibly-null columns app.models.offering.Offering
    always had; a `None` here means the fact is genuinely unknown, not
    that this schema failed to find it.
    """

    role: str
    # Offering.verification_status (app.models.offering) — a real, honest
    # column with no scoring logic behind it yet (no admin-review workflow
    # sets it to "verified" today, see that model's docstring). Exposed so
    # the client can distinguish a role claim from a role ForgeX has
    # actually checked, instead of rendering every role with equal
    # confidence — see the audit's "Manufacturer... no verified evidence"
    # finding.
    verification_status: str
    moq: str | None
    lead_time: str | None
    capacity: str | None


class RequirementMatchEvidenceItem(BaseModel):
    """
    One real, VERIFIED-and-applied ProductAttributeEvidence row for the
    candidate's Product (via ProductAttribute.latest_evidence_id), with
    its backing RawObservation's external_reference — never anything
    about the Company (Module 8C's provenance-application UI already
    covers that separately; adding it here would duplicate, not
    extend, an existing surface). `status` reports the real stored
    column value (see app.api.v1.requirements._fetch_product_evidence)
    — always `verified` today, since that is the only status this
    query's join can ever reach, never upgraded/inferred here.
    """

    field_name: str
    value_observed: str
    status: str
    source_url: str | None


class RequirementMatchScoreBreakdownEntry(BaseModel):
    signal: str
    weight: float
    points_earned: float


class RequirementMatchCompanySummary(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    verification_level: str


class RequirementMatchProductSummary(BaseModel):
    id: uuid.UUID
    name: str
    slug: str


class RequirementMatchCandidate(BaseModel):
    offering_id: uuid.UUID
    rank: int
    score: float
    company: RequirementMatchCompanySummary
    product: RequirementMatchProductSummary
    signals: RequirementMatchSignals
    score_breakdown: list[RequirementMatchScoreBreakdownEntry]
    offering: RequirementMatchOfferingDetails
    evidence: list[RequirementMatchEvidenceItem]


class RequirementMatchesResponse(BaseModel):
    requirement_id: uuid.UUID
    status: str  # "computed" | "category_required"
    total_candidates_considered: int
    more_candidates_may_exist: bool
    excluded_for_hard_criteria: int
    returned_count: int
    matches: list[RequirementMatchCandidate]
