"""
Pydantic schemas — Module 7A-1 (Requirement Intelligence foundation).
Mirrors app/schemas/product.py's conventions (from_attributes=True for
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
