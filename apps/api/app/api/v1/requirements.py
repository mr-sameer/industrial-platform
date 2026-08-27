"""
Requirement routes — Module 7A-1 (Requirement Intelligence foundation).
A new router file, mounted under /api/v1, separate from every existing
router — matching this phase's own instruction not to modify Consult,
Discover, or any previous module's routes.

Authenticated-only, ownership-scoped (CurrentUser required for both
routes; GET is scoped to the requirement's own creator). This is a
narrower policy than app.api.v1.products' public-read model — a
Requirement carries a user's own procurement intent, not shared/public
taxonomy data, so the closer precedent is session ownership
(app.api.v1.auth's revoke_session, 404-not-403-if-not-yours), not
Product's public GET. See this module's own completion report for why
anonymous submission was considered and deliberately not built here.

GET /{requirement_id}/matches (Module 7A-2, additive) is ownership-scoped
identically to GET /{requirement_id} — same 404-not-403 policy, same
CurrentUser gate. See app.services.requirement_matching_service for the
actual scoring/ranking logic; this route only translates its dataclasses
into the approved response contract
(docs/product/phase-7a-requirement-intelligence-architecture.md Section 13).

Module 7B (Search Telemetry), additive: GET /{requirement_id}/matches
also persists the execution via app.services.search_telemetry_service
before returning — see that module's own docstring for the
fail-loud transaction behavior. No other route in this file changes.
"""

import uuid
from typing import cast

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import CurrentUser
from app.core.responses import ApiSuccess, success_response
from app.db.session import DbSession
from app.models.provenance_record import ProvenanceRecord
from app.models.raw_observation import RawObservation
from app.models.requirement import Requirement
from app.schemas.requirement import (
    CriterionValue,
    RequirementCreate,
    RequirementDetail,
    RequirementMatchCandidate,
    RequirementMatchCategorySignal,
    RequirementMatchCertificationSignal,
    RequirementMatchCompanySummary,
    RequirementMatchCriterionSignal,
    RequirementMatchEvidenceItem,
    RequirementMatchesResponse,
    RequirementMatchLocationSignal,
    RequirementMatchOfferingDetails,
    RequirementMatchProductSummary,
    RequirementMatchScoreBreakdownEntry,
    RequirementMatchSignals,
    RequirementMatchTrustSignal,
    RequirementSpecificationCriterionPublic,
)
from app.services import requirement_matching_service, requirement_service, search_telemetry_service
from app.services.requirement_matching_service import MatchCandidate
from app.services.requirement_service import (
    CategoryNotFoundError,
    CategoryRequiredForCriteriaError,
    InvalidCriterionValueError,
    InvalidSpecificationError,
)

router = APIRouter(prefix="/requirements", tags=["requirements"])


def _to_detail(requirement: Requirement) -> RequirementDetail:
    """
    Builds RequirementDetail explicitly rather than a blind
    RequirementDetail.model_validate(requirement) — mirrors
    app.api.v1.products._to_detail's own reasoning exactly:
    RequirementSpecificationCriterionPublic's `specification_name`
    isn't a direct attribute on the ORM row, only reachable via its
    `.specification` relationship, so Pydantic's from_attributes
    auto-mapping can't resolve it alone.
    """
    return RequirementDetail(
        id=requirement.id,
        created_by=requirement.created_by,
        raw_query=requirement.raw_query,
        product_category_id=requirement.product_category_id,
        industry=requirement.industry,
        country=requirement.country,
        state=requirement.state,
        city=requirement.city,
        certifications=requirement.certifications,
        quantity=requirement.quantity,
        budget=requirement.budget,
        timeline=requirement.timeline,
        status=requirement.status,
        extraction_confidence=requirement.extraction_confidence,
        criteria=[
            RequirementSpecificationCriterionPublic(
                id=criterion.id,
                specification_id=criterion.specification_id,
                specification_name=criterion.specification.name,
                operator=criterion.operator,
                value=criterion.value,
            )
            for criterion in requirement.criteria
        ],
        created_at=requirement.created_at,
        updated_at=requirement.updated_at,
    )


@router.post("", response_model=ApiSuccess[RequirementDetail], status_code=status.HTTP_201_CREATED)
async def create_requirement(
    payload: RequirementCreate, db: DbSession, current_user: CurrentUser
) -> ApiSuccess[RequirementDetail]:
    """
    Any authenticated user may submit a Requirement — mirrors
    app.api.v1.products.create_product's own precedent (any
    authenticated user may create a Product; no finer-grained RBAC
    exists for this kind of shared-vocabulary-referencing action yet).
    Always created as SUBMITTED — there is no draft-editing flow in
    this phase (see app.models.requirement.RequirementStatus's own
    docstring).
    """
    try:
        requirement = await requirement_service.create_requirement(
            db, payload, created_by=current_user.id
        )
    except CategoryNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "CATEGORY_NOT_FOUND",
                "message": "No product category with that ID exists.",
            },
        ) from exc
    except CategoryRequiredForCriteriaError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "CATEGORY_REQUIRED_FOR_CRITERIA",
                "message": "product_category_id is required when criteria are given.",
            },
        ) from exc
    except InvalidSpecificationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "INVALID_SPECIFICATION",
                "message": "One or more criteria reference a specification that doesn't exist or "
                "doesn't belong to the given product category.",
            },
        ) from exc
    except InvalidCriterionValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "INVALID_CRITERION_VALUE", "message": str(exc)},
        ) from exc
    return success_response(_to_detail(requirement))


@router.get("/{requirement_id}", response_model=ApiSuccess[RequirementDetail])
async def get_requirement(
    requirement_id: uuid.UUID, db: DbSession, current_user: CurrentUser
) -> ApiSuccess[RequirementDetail]:
    requirement = await requirement_service.get_requirement_for_user(
        db, requirement_id, current_user.id
    )
    if requirement is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "REQUIREMENT_NOT_FOUND",
                "message": "No requirement with that ID exists.",
            },
        )
    return success_response(_to_detail(requirement))


async def _fetch_product_evidence(
    db: AsyncSession, product_ids: set[uuid.UUID]
) -> dict[uuid.UUID, list[RequirementMatchEvidenceItem]]:
    """
    One batched, read-only query for the real provenance trail behind
    each candidate's Product — never per-candidate (avoids N+1 the same
    way every other batched fetch in this file's sibling services
    does). Company-level provenance is deliberately out of scope here
    (see RequirementMatchEvidenceItem's own docstring) — this only
    answers "what evidence backs this specific product," which is what
    a buyer deciding whether to trust *this offering* actually needs.
    Status is reported exactly as stored — never upgraded, never
    inferred as VERIFIED.
    """
    if not product_ids:
        return {}
    result = await db.execute(
        select(ProvenanceRecord, RawObservation.external_reference)
        .join(RawObservation, RawObservation.id == ProvenanceRecord.raw_observation_id)
        .where(ProvenanceRecord.product_id.in_(product_ids))
        .order_by(ProvenanceRecord.field_name)
    )
    by_product: dict[uuid.UUID, list[RequirementMatchEvidenceItem]] = {}
    for record, external_reference in result.all():
        assert record.product_id is not None  # this query only ever selects product-entity rows
        by_product.setdefault(record.product_id, []).append(
            RequirementMatchEvidenceItem(
                field_name=record.field_name,
                value_observed=record.value_observed,
                status=record.status.value,
                source_url=external_reference,
            )
        )
    return by_product


def _to_match_dto(
    candidate: MatchCandidate,
    rank: int,
    evidence_by_product: dict[uuid.UUID, list[RequirementMatchEvidenceItem]],
) -> RequirementMatchCandidate:
    """
    Explicitly constructs a RequirementMatchCandidate from
    requirement_matching_service's dataclasses — mirrors _to_detail's
    own reasoning. `category` is always matched=True here: every
    candidate reaching this point was already retrieved by a
    category-filtered query (_retrieve_candidates), so category is a
    hard retrieval filter, not a scored signal — there is no case where
    a surviving candidate has matched=False.
    """
    return RequirementMatchCandidate(
        offering_id=candidate.offering.id,
        rank=rank,
        score=candidate.score,
        company=RequirementMatchCompanySummary(
            id=candidate.company.id,
            name=candidate.company.name,
            slug=candidate.company.slug,
            verification_level=candidate.trust.level.value,
        ),
        product=RequirementMatchProductSummary(
            id=candidate.product.id,
            name=candidate.product.name,
            slug=candidate.product.slug,
        ),
        signals=RequirementMatchSignals(
            category=RequirementMatchCategorySignal(matched=True),
            criteria=[
                RequirementMatchCriterionSignal(
                    specification_id=c.specification_id,
                    specification_name=c.specification_name,
                    operator=c.operator,
                    # CriterionSignal.requirement_value is typed `object` at
                    # the service layer (it passes through
                    # RequirementSpecificationCriterion.value, genuinely
                    # dynamic JSONB) — this cast only narrows the type for
                    # the response schema; the value itself was already
                    # validated into this exact shape by
                    # RequirementSpecificationCriterionInput at creation
                    # time (app.schemas.requirement), so no runtime check
                    # is being skipped here.
                    requirement_value=cast(CriterionValue, c.requirement_value),
                    candidate_value=c.candidate_value,
                    status=c.status,
                )
                for c in candidate.criteria
            ],
            location=RequirementMatchLocationSignal(
                requested=candidate.location.requested,
                candidate=candidate.location.candidate,
                points_earned=candidate.location.points_earned,
                points_possible=candidate.location.points_possible,
            ),
            certifications=RequirementMatchCertificationSignal(
                requested=candidate.certifications.requested,
                evidence_found=candidate.certifications.evidence_found,
                points_earned=candidate.certifications.points_earned,
                points_possible=candidate.certifications.points_possible,
                confidence=candidate.certifications.confidence,
                note=candidate.certifications.note,
            ),
            trust_tier=RequirementMatchTrustSignal(
                level=candidate.trust.level.value,
                points_earned=candidate.trust.points_earned,
                points_possible=candidate.trust.points_possible,
            ),
        ),
        score_breakdown=[
            RequirementMatchScoreBreakdownEntry(
                signal=entry.signal, weight=entry.weight, points_earned=entry.points_earned
            )
            for entry in candidate.score_breakdown
        ],
        offering=RequirementMatchOfferingDetails(
            role=candidate.offering.role.value,
            moq=candidate.offering.moq,
            lead_time=candidate.offering.lead_time,
            capacity=candidate.offering.capacity,
        ),
        evidence=evidence_by_product.get(candidate.product.id, []),
    )


@router.get("/{requirement_id}/matches", response_model=ApiSuccess[RequirementMatchesResponse])
async def get_requirement_matches(
    requirement_id: uuid.UUID, db: DbSession, current_user: CurrentUser
) -> ApiSuccess[RequirementMatchesResponse]:
    """
    Ownership-scoped identically to GET /{requirement_id} — same
    404-not-403 policy for a requirement that isn't the caller's own.
    No pagination params, no output cap beyond the 500-candidate
    retrieval ceiling — Option B, per the approved 7A-2 contract.

    Module 7B (Search Telemetry), additive: after the match result is
    computed and translated into response DTOs, the execution is
    persisted via search_telemetry_service.record_search before the
    response is returned. That call performs its own commit and, per
    the approved 7B design, is intentionally NOT wrapped in a
    try/except here — a telemetry write failure must fail this
    request rather than silently return matches that were never
    recorded. requirement_matching_service.compute_matches itself is
    untouched by this addition.
    """
    requirement = await requirement_service.get_requirement_for_user(
        db, requirement_id, current_user.id
    )
    if requirement is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "REQUIREMENT_NOT_FOUND",
                "message": "No requirement with that ID exists.",
            },
        )
    result = await requirement_matching_service.compute_matches(db, requirement)
    evidence_by_product = await _fetch_product_evidence(
        db, {candidate.product.id for candidate in result.candidates}
    )
    matches = [
        _to_match_dto(candidate, rank, evidence_by_product)
        for rank, candidate in enumerate(result.candidates, start=1)
    ]
    await search_telemetry_service.record_search(
        db, requirement, result, matches, user_id=current_user.id
    )
    return success_response(
        RequirementMatchesResponse(
            requirement_id=requirement.id,
            status=result.status,
            total_candidates_considered=result.total_candidates_considered,
            more_candidates_may_exist=result.more_candidates_may_exist,
            excluded_for_hard_criteria=result.excluded_for_hard_criteria,
            returned_count=len(matches),
            matches=matches,
        )
    )
