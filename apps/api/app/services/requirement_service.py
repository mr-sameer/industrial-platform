"""
Requirement service layer — Module 7A-1 (Requirement Intelligence
foundation). Persistence and validation ONLY — this file contains NO
product-matching/ranking logic and must not gain any in this phase.

THE BOUNDARY THIS FILE MAINTAINS (per this module's own architecture
review): a future app.services.requirement_matching_service will read
Requirement/RequirementSpecificationCriterion rows and evaluate them
against Product/ProductAttribute/Offering data — that is a distinct,
not-yet-built module. Nothing here loops over ProductAttribute, scores
a candidate, or ranks anything; this file's only job is "does this
Requirement/criterion reference real, valid taxonomy entries, and can
it be persisted." Keeping that boundary now means the future matching
service can be added, or its retrieval strategy swapped later, without
touching this file, app.api.v1.requirements, or the response contract.

Mirrors app/services/product_service.py's conventions exactly
(selectinload eager-loading, commit-then-refetch pattern, category/
specification validation shape) — reusing the same patterns rather
than inventing new ones for a structurally similar problem.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.product_category import ProductCategory
from app.models.product_specification import ProductSpecification, SpecificationDataType
from app.models.requirement import (
    CriterionOperator,
    Requirement,
    RequirementSpecificationCriterion,
    RequirementStatus,
)
from app.schemas.requirement import RequirementCreate, RequirementSpecificationCriterionInput


class CategoryNotFoundError(Exception):
    pass


class CategoryRequiredForCriteriaError(Exception):
    """Raised when criteria are submitted but no product_category_id was
    given — a specification is always category-scoped (Phase 4B), so a
    criterion referencing one is meaningless without a category to
    validate it against."""


class InvalidSpecificationError(Exception):
    """Raised when a criterion references a specification that doesn't
    exist, or doesn't belong to the requirement's own category — mirrors
    app.services.product_service's own InvalidSpecificationError."""


class InvalidCriterionValueError(Exception):
    """Raised when a criterion's operator is structurally incompatible
    with its specification's datatype (e.g. 'gte' against a TEXT spec)."""


_NUMERIC_OPERATORS = frozenset(
    {CriterionOperator.GTE, CriterionOperator.LTE, CriterionOperator.RANGE}
)
_NUMERIC_DATATYPES = frozenset({SpecificationDataType.NUMBER, SpecificationDataType.RANGE})


async def _get_category(db: AsyncSession, category_id: uuid.UUID) -> ProductCategory | None:
    result = await db.execute(select(ProductCategory).where(ProductCategory.id == category_id))
    return result.scalar_one_or_none()


async def _get_specification(
    db: AsyncSession, specification_id: uuid.UUID
) -> ProductSpecification | None:
    result = await db.execute(
        select(ProductSpecification).where(ProductSpecification.id == specification_id)
    )
    return result.scalar_one_or_none()


def _validate_operator_datatype_compatibility(
    operator: CriterionOperator, datatype: SpecificationDataType
) -> None:
    if operator in _NUMERIC_OPERATORS and datatype not in _NUMERIC_DATATYPES:
        raise InvalidCriterionValueError(
            f"operator {operator.value!r} is not valid for a {datatype.value!r} specification "
            f"(requires 'number' or 'range')"
        )


async def _validate_criteria(
    db: AsyncSession,
    category_id: uuid.UUID | None,
    criteria: list[RequirementSpecificationCriterionInput],
) -> None:
    if not criteria:
        return
    if category_id is None:
        raise CategoryRequiredForCriteriaError(
            "product_category_id is required when criteria are given — a specification is "
            "always scoped to a category."
        )
    seen_specification_ids: set[uuid.UUID] = set()
    for criterion in criteria:
        if criterion.specification_id in seen_specification_ids:
            raise InvalidSpecificationError(
                f"duplicate specification_id in criteria: {criterion.specification_id}"
            )
        seen_specification_ids.add(criterion.specification_id)

        spec = await _get_specification(db, criterion.specification_id)
        if spec is None or spec.category_id != category_id:
            raise InvalidSpecificationError(str(criterion.specification_id))
        _validate_operator_datatype_compatibility(criterion.operator, spec.datatype)


async def get_requirement(db: AsyncSession, requirement_id: uuid.UUID) -> Requirement | None:
    result = await db.execute(
        select(Requirement)
        .where(Requirement.id == requirement_id)
        .options(
            selectinload(Requirement.criteria).selectinload(
                RequirementSpecificationCriterion.specification
            )
        )
    )
    return result.scalar_one_or_none()


async def get_requirement_for_user(
    db: AsyncSession, requirement_id: uuid.UUID, user_id: uuid.UUID
) -> Requirement | None:
    """
    Ownership-scoped — returns None (never the row) if the requirement
    exists but belongs to someone else, matching this codebase's
    established session-ownership pattern
    (app.services.session_service.revoke_session_for_user): a personal
    resource's ownership check happens at the query itself, not as a
    separate 403 branch, so a non-owner gets the identical "not found"
    outcome as a truly nonexistent ID (no existence leak).
    """
    result = await db.execute(
        select(Requirement)
        .where(Requirement.id == requirement_id, Requirement.created_by == user_id)
        .options(
            selectinload(Requirement.criteria).selectinload(
                RequirementSpecificationCriterion.specification
            )
        )
    )
    return result.scalar_one_or_none()


async def create_requirement(
    db: AsyncSession, payload: RequirementCreate, *, created_by: uuid.UUID
) -> Requirement:
    if payload.product_category_id is not None:
        category = await _get_category(db, payload.product_category_id)
        if category is None:
            raise CategoryNotFoundError(str(payload.product_category_id))

    await _validate_criteria(db, payload.product_category_id, payload.criteria)

    requirement = Requirement(
        created_by=created_by,
        raw_query=payload.raw_query,
        product_category_id=payload.product_category_id,
        industry=payload.industry,
        country=payload.country,
        state=payload.state,
        city=payload.city,
        certifications=payload.certifications,
        quantity=payload.quantity,
        budget=payload.budget,
        timeline=payload.timeline,
        status=RequirementStatus.SUBMITTED,
        extraction_confidence=payload.extraction_confidence,
    )
    db.add(requirement)
    await db.flush()  # requirement.id is needed before criterion rows can reference it

    # Direct db.add(), never requirement.criteria.append(...) — appending
    # to an unloaded relationship on a just-flushed row is exactly the
    # async-session MissingGreenlet trap app.services.product_service's
    # own _set_attributes docstring documents hitting; direct add() with
    # requirement_id set explicitly never touches that relationship at all.
    for criterion in payload.criteria:
        db.add(
            RequirementSpecificationCriterion(
                requirement_id=requirement.id,
                specification_id=criterion.specification_id,
                operator=criterion.operator,
                value=criterion.value,
            )
        )

    await db.commit()

    refreshed = await get_requirement(db, requirement.id)
    assert refreshed is not None  # just committed — always exists
    return refreshed
