"""
Search telemetry service — Module 7B (Search Telemetry). Persistence
ONLY. Consumes the already-computed
requirement_matching_service.MatchesResult and the already-built
RequirementMatchCandidate response DTOs (app.api.v1.requirements'
_to_match_dto) — this file never retrieves candidates, evaluates
criteria, or scores anything itself. That boundary mirrors
requirement_service.py's own explicit boundary against
requirement_matching_service in Module 7A-1/7A-2.

TRANSACTION BEHAVIOR (fail loud, per this module's approved design):
record_search performs one flush (to obtain the new SearchEvent's id)
and one commit. If either raises, the exception propagates unhandled
to the caller (app.api.v1.requirements.get_requirement_matches) and
from there to FastAPI's default error handling — the request fails
and no partial/successful response is returned. This is a deliberate
choice: telemetry is meant to feed the future Data Gap Engine, so a
"matches were returned but never recorded" outcome would silently
corrupt that downstream analytics, which is worse than a visible 500.
No retry queue or background worker is introduced — the write happens
synchronously, in the same request, using the existing request-scoped
AsyncSession (app.db.session.get_db) exactly like every other write in
this codebase (e.g. requirement_service.create_requirement).
"""

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.requirement import Requirement
from app.models.search_event import SearchEvent, SearchResultCandidate
from app.schemas.requirement import RequirementMatchCandidate
from app.services.requirement_matching_service import MatchesResult


def _build_requirement_snapshot(requirement: Requirement) -> dict[str, Any]:
    """
    Immutable copy of the Requirement's structured state at search
    time. Requires `requirement.criteria` (and each criterion's
    `.specification`) already eager-loaded — the same precondition
    requirement_matching_service.compute_matches itself relies on, and
    already satisfied by every real caller via
    requirement_service.get_requirement_for_user.
    """
    return {
        "raw_query": requirement.raw_query,
        "product_category_id": (
            str(requirement.product_category_id) if requirement.product_category_id else None
        ),
        "industry": requirement.industry,
        "country": requirement.country,
        "state": requirement.state,
        "city": requirement.city,
        "certifications": requirement.certifications,
        "quantity": requirement.quantity,
        "budget": requirement.budget,
        "timeline": requirement.timeline,
        "extraction_confidence": requirement.extraction_confidence,
        "criteria": [
            {
                "specification_id": str(criterion.specification_id),
                "specification_name": criterion.specification.name,
                "operator": criterion.operator.value,
                "value": criterion.value,
            }
            for criterion in requirement.criteria
        ],
    }


async def record_search(
    db: AsyncSession,
    requirement: Requirement,
    result: MatchesResult,
    matches: list[RequirementMatchCandidate],
    *,
    user_id: uuid.UUID,
) -> SearchEvent:
    """
    Persists one SearchEvent plus one SearchResultCandidate per
    returned (surviving) match — never per excluded candidate, the
    same "counted, not detailed" boundary
    requirement_matching_service.MatchesResult.excluded_for_hard_criteria
    itself draws. `matches` must be the exact DTOs already returned to
    the caller, not re-derived here.
    """
    event = SearchEvent(
        requirement_id=requirement.id,
        created_by=user_id,
        raw_query_text=requirement.raw_query,
        requirement_snapshot=_build_requirement_snapshot(requirement),
        status=result.status,
        total_candidates_considered=result.total_candidates_considered,
        more_candidates_may_exist=result.more_candidates_may_exist,
        excluded_for_hard_criteria=result.excluded_for_hard_criteria,
        returned_count=len(matches),
    )
    db.add(event)
    await db.flush()  # event.id is needed before candidate rows can reference it

    # Direct db.add(), never event.candidates.append(...) — appending to
    # an unloaded relationship on a just-flushed row is exactly the
    # async-session MissingGreenlet trap app.services.product_service's
    # own _set_attributes docstring documents hitting (also cited in
    # requirement_service.create_requirement for the identical reason).
    for match in matches:
        db.add(
            SearchResultCandidate(
                search_event_id=event.id,
                offering_id=match.offering_id,
                rank=match.rank,
                score=match.score,
                result_snapshot=match.model_dump(mode="json"),
            )
        )

    await db.commit()
    return event
