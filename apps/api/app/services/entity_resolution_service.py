"""
Entity resolution service — Module 5D, field extraction generalized in
Module 6D. Orchestrates candidate generation (persisting
app.entity_resolution.matching's output) and human decisions. Reuses
Module 5A's provenance_service and Module 5C's company_promotion_service
— no Company-domain or provenance logic is duplicated here. Field
extraction from a raw observation now goes through
app.collectors.field_profiles.resolve_profile_for_content (lineage-
first, one profile per collector_type) instead of the MCA-only
hardcoded keys this file used before Module 6D.

DATA TRUST / SAFETY RULE, enforced directly: `decide()` is the ONLY
function in this file that touches canonical data, and it only ever
does so in response to an explicit, already-recorded human decision —
never automatically, regardless of resolution_state (including
AUTO_MATCH). A candidate that's never decided has zero effect on any
Company or ProvenanceRecord.
"""

import math
import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.collectors.field_profiles import resolve_profile_for_content
from app.entity_resolution.matching import generate_candidate
from app.models.company import Company
from app.models.entity_resolution_candidate import (
    EntityResolutionCandidate,
    ResolutionDecision,
    ResolutionState,
)
from app.models.provenance_record import EntityType, ExtractionMethod, ProvenanceStatus
from app.schemas.provenance import ProvenanceRecordCreate
from app.services import company_promotion_service, provenance_service


class RawObservationNotFoundError(Exception):
    pass


class AlreadyDecidedError(Exception):
    """A candidate's decision is recorded exactly once — re-deciding an
    already-decided candidate is refused, matching this codebase's
    established pattern (provenance_service's AlreadyVerifiedError) for
    keeping consequential state transitions auditable and non-repeatable."""


class InvalidDecisionError(Exception):
    """Raised when the requested decision doesn't make sense for this
    candidate's resolution_state — e.g. CONFIRM_MATCH on a candidate
    with no candidate_company_id at all."""


async def generate_candidate_for_observation(
    db: AsyncSession, raw_observation_id: uuid.UUID
) -> EntityResolutionCandidate:
    """
    Idempotent: a raw observation that already has a candidate returns
    that existing row rather than creating a second one — matching
    this module's own idempotency requirement (Phase 8, Case 5) and
    the same principle Module 5B's acquisition idempotency already
    established for raw observations themselves.
    """
    existing_result = await db.execute(
        select(EntityResolutionCandidate).where(
            EntityResolutionCandidate.raw_observation_id == raw_observation_id
        )
    )
    existing = existing_result.scalar_one_or_none()
    if existing is not None:
        return existing

    observation = await provenance_service.get_raw_observation(db, raw_observation_id)
    if observation is None:
        raise RawObservationNotFoundError(str(raw_observation_id))

    # Module 6D: field extraction is now per-collector_type (see
    # app.collectors.field_profiles) rather than the MCA-only hardcoded
    # keys this function used before Module 6D existed. A source with
    # no registered profile (Census CBP, USITC DataWeb — aggregate/trade
    # data, never company identity) correctly raises here rather than
    # being silently misread as company fields — see
    # field_profiles.resolve_profile_for_content's own docstring for
    # the lineage-first resolution rule (and its narrow legacy-test
    # compatibility shim).
    profile = await resolve_profile_for_content(db, raw_observation_id, observation.raw_content)
    identity = profile.extract(observation.raw_content)

    result = await generate_candidate(
        db,
        cin=identity.strong_id,
        company_name=identity.name,
        city=identity.city,
        state=identity.state,
        website=identity.website,
        external_identifier=observation.external_reference,
    )

    candidate = EntityResolutionCandidate(
        raw_observation_id=raw_observation_id,
        candidate_company_id=result.candidate_company_id,
        resolution_state=result.resolution_state,
        match_signals=[s.to_dict() for s in result.signals],
        explanation=result.explanation,
    )
    db.add(candidate)
    await db.commit()
    await db.refresh(candidate)
    return candidate


def _get_str(content: dict[str, object], key: str) -> str | None:
    value = content.get(key)
    return str(value) if value is not None else None


async def get_candidate(
    db: AsyncSession, candidate_id: uuid.UUID
) -> EntityResolutionCandidate | None:
    result = await db.execute(
        select(EntityResolutionCandidate).where(EntityResolutionCandidate.id == candidate_id)
    )
    return result.scalar_one_or_none()


async def list_candidates(
    db: AsyncSession,
    *,
    resolution_state: ResolutionState | None,
    page: int,
    page_size: int,
) -> tuple[list[EntityResolutionCandidate], int]:
    query = select(EntityResolutionCandidate)
    if resolution_state is not None:
        query = query.where(EntityResolutionCandidate.resolution_state == resolution_state)

    count_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = int(count_result.scalar_one())

    query = (
        query.order_by(EntityResolutionCandidate.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    result = await db.execute(query)
    return list(result.scalars().all()), total


async def decide(
    db: AsyncSession,
    candidate: EntityResolutionCandidate,
    *,
    decision: ResolutionDecision,
    decided_by: uuid.UUID,
) -> tuple[EntityResolutionCandidate, Company | None]:
    """
    Returns (updated_candidate, affected_company_or_none). Exactly one
    of the three decision branches below runs; nothing here can touch
    canonical data outside of that one explicit branch.
    """
    if candidate.decision is not None:
        raise AlreadyDecidedError(str(candidate.id))

    company: Company | None = None

    if decision == ResolutionDecision.CONFIRM_MATCH:
        if candidate.candidate_company_id is None:
            raise InvalidDecisionError(
                "Cannot CONFIRM_MATCH — this candidate has no candidate_company_id."
            )
        company = await _attach_observation_to_existing_company(db, candidate)

    elif decision == ResolutionDecision.CREATE_NEW:
        # Reuses Module 5C's promotion service completely unchanged —
        # including its own CIN duplicate check, which is a real,
        # independent safety net even if entity resolution somehow
        # missed something.
        company = await company_promotion_service.promote_raw_observation_to_company(
            db, candidate.raw_observation_id, reviewer_id=decided_by
        )

    elif decision == ResolutionDecision.REJECT_MATCH:
        pass  # Records the decision only — no canonical data is touched.

    if company is not None and candidate.candidate_company_id is None:
        candidate.candidate_company_id = company.id
    candidate.decision = decision
    candidate.decided_by = decided_by
    candidate.decided_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(candidate)
    return candidate, company


async def _attach_observation_to_existing_company(
    db: AsyncSession, candidate: EntityResolutionCandidate
) -> Company:
    """
    The CONFIRM_MATCH action: the observation's fields become new
    ProvenanceRecords on the EXISTING candidate company — never a new
    Company row. Reuses provenance_service.create_provenance_record
    unchanged, including its own, already-built conflict detection
    (Module 5A) — if the new observation disagrees with an existing
    field value for this company, a real DataConflict is created
    automatically by that existing code path, satisfying this
    module's Phase 6 instruction ("Use the existing Module 5A conflict
    infrastructure") by construction, not by re-implementing it.
    """
    assert candidate.candidate_company_id is not None  # guarded by the caller
    observation = await provenance_service.get_raw_observation(db, candidate.raw_observation_id)
    assert observation is not None  # candidate creation already required this to exist

    company_result = await db.execute(
        select(Company).where(Company.id == candidate.candidate_company_id)
    )
    company = company_result.scalar_one()

    profile = await resolve_profile_for_content(
        db, candidate.raw_observation_id, observation.raw_content
    )

    content = observation.raw_content
    for field_name in (*profile.direct_fields, *profile.extra_fields):
        value = _get_str(content, field_name)
        if not value:
            continue
        is_direct = field_name in profile.direct_fields
        await provenance_service.create_provenance_record(
            db,
            ProvenanceRecordCreate(
                entity_type=EntityType.COMPANY,
                company_id=company.id,
                field_name=field_name,
                raw_observation_id=observation.id,
                value_observed=value,
                extraction_method=ExtractionMethod.RULE_BASED
                if is_direct
                else ExtractionMethod.MANUAL,
                confidence=0.8 if is_direct else 0.5,
                status=ProvenanceStatus.EXTRACTED if is_direct else ProvenanceStatus.OBSERVED,
            ),
        )
    return company


def total_pages(total: int, page_size: int) -> int:
    return max(1, math.ceil(total / page_size))
