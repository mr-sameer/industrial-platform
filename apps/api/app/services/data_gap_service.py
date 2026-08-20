"""
Data Gap Intelligence — Module 7C. Read-only analysis over what
Module 7B already persisted (SearchEvent/SearchResultCandidate) and
what Modules 4A/4B already model (ProductSpecification/ProductAttribute/
Product/Offering). This file issues SELECT statements only — no
INSERT, UPDATE, DELETE, flush, or commit anywhere in it, and no new
table backs it. Every number below is either read directly off an
existing persisted row or a plain aggregate (count/sum/average) over
those rows; nothing here recomputes 7A-2 scoring or re-derives trust
from live Company/VerificationDocument state.

WHY NO RE-DERIVATION OF TRUST: SearchResultCandidate.result_snapshot
already contains the exact signals.trust_tier the matching engine
computed and returned at search time (verification_score_service.calculate
was already called once, by requirement_matching_service, when the
search ran). Calling it again here would show TODAY's trust for a
HISTORICAL search — exactly the "destroy the historical meaning of the
7B snapshot" mistake Module 7B's own design was built to prevent. So
this file reads the snapshot's own trust_tier numbers, never
app.services.verification_score_service, and never app.models.company
directly.

NO INVENTED THRESHOLDS: per this module's approved design, "low",
"weak", or "insufficient" are never hardcoded cutoffs baked into a
boolean. Every metric below is either a genuinely non-arbitrary
structural boolean (a requested certification/location dimension
either got full credit or it didn't — see _has_certification_gap /
_has_location_gap) or a raw rate/average exposed as-is for the caller
to threshold. Where a metric has no defined denominator for a given
category (e.g. certifications were never once requested in that
category), the rate is None — "not enough signal to measure", never a
silently-fabricated 0.0.

NO COMPOSITE GAP SCORE: CategoryCoverageGap/SpecificationCoverageGap
carry independent metrics, not a single blended score — no such
formula exists anywhere else in this repository (7A-2's own scoring
weights are a matching formula, not a data-completeness formula, and
are not reused here). `categories`/`specifications` in DataGapReport
are sorted by real, already-computed demand-volume fields
(search_count / times_used_as_criterion) purely for readability, with
a UUID tiebreak for determinism — this is an ordering choice, not a
scoring decision.

INDIA / MCA / data.gov.in: deliberately absent from this file. A gap
finding here is expressed only in terms of product_category_id/
specification_id/rates — it says nothing about which real-world source
would address it. That mapping is a human (or later, a separate
milestone's) decision that creates/activates an ordinary
app.models.source_registry.SourceRegistry row and collector, per the
existing Module 5/6 pipeline — this file has no knowledge of
SourceRegistry, CIN, NIC codes, or any country at all.
"""

import uuid
from dataclasses import dataclass

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.offering import Offering, OfferingStatus
from app.models.product import Product, ProductStatus
from app.models.product_attribute import ProductAttribute
from app.models.product_specification import ProductSpecification
from app.models.requirement import Requirement, RequirementSpecificationCriterion
from app.models.search_event import SearchEvent, SearchResultCandidate


@dataclass(frozen=True)
class CategoryCoverageGap:
    product_category_id: uuid.UUID

    # Section A/B — zero and fully-excluded coverage. Both are hard,
    # non-arbitrary zero boundaries; there is no "low" bucket here (see
    # avg_returned_count below instead — deliberately not thresholded).
    search_count: int
    zero_offering_search_count: int  # total_candidates_considered == 0
    fully_excluded_search_count: int  # total_candidates_considered > 0, returned_count == 0
    avg_candidates_considered: float
    avg_excluded_for_hard_criteria: float
    avg_returned_count: float  # raw metric — caller decides what "low" means

    # Section G — operational ceiling signal. Kept structurally
    # separate from every metric above/below: a high rate here means
    # "the 500-candidate retrieval ceiling was hit often", a supply/
    # scale signal, never evidence that supplier data is missing.
    more_candidates_may_exist_rate: float

    # Denominator for every *_gap_rate/avg_trust_* field below —
    # returned (surviving) candidates only, matching
    # SearchResultCandidate's own scope (excluded candidates are not
    # persisted individually — see app.services.search_telemetry_service).
    returned_candidate_count: int

    # Section C — certification evidence gaps. certification_requested_count
    # is how many returned candidates belonged to a search that actually
    # requested at least one certification (points_possible > 0); rate
    # is None, not 0.0, when that count is 0 — "never requested" is not
    # "no gap".
    certification_requested_count: int
    certification_gap_count: int
    certification_gap_rate: float | None

    # Section D — geographic gaps. Same None-vs-0.0 discipline as certifications.
    location_requested_count: int
    location_gap_count: int
    location_gap_rate: float | None

    # Section E — trust/evidence. Raw averages, not a "low_trust_rate"
    # with a hidden cutoff — see module docstring.
    avg_trust_points_earned: float | None
    avg_trust_points_possible: float | None


@dataclass(frozen=True)
class SpecificationCoverageGap:
    specification_id: uuid.UUID
    specification_name: str
    product_category_id: uuid.UUID
    # How many times a buyer has actually written a criterion against
    # this specification (RequirementSpecificationCriterion rows) — the
    # existence filter this module's approved design requires: a
    # specification with 0 here is never analyzed or returned at all
    # (see build_specification_coverage_gaps).
    times_used_as_criterion: int
    # Published-Product + ACTIVE-Offering scope — identical filter to
    # requirement_matching_service._retrieve_candidates, so "coverage"
    # means coverage among offerings that could actually ever be
    # returned as a match, not raw inventory.
    offerings_in_category: int
    offerings_with_attribute_value: int
    coverage_rate: float | None  # None when offerings_in_category == 0


@dataclass(frozen=True)
class DataGapReport:
    categories: list[CategoryCoverageGap]
    specifications: list[SpecificationCoverageGap]


@dataclass
class _CategoryAccumulator:
    search_count: int = 0
    zero_offering_search_count: int = 0
    fully_excluded_search_count: int = 0
    candidates_considered_sum: int = 0
    excluded_for_hard_criteria_sum: int = 0
    returned_count_sum: int = 0
    more_candidates_may_exist_count: int = 0
    returned_candidate_count: int = 0
    certification_requested_count: int = 0
    certification_gap_count: int = 0
    location_requested_count: int = 0
    location_gap_count: int = 0
    trust_points_earned_sum: float = 0.0
    trust_points_possible_sum: float = 0.0


def _resolve_category_id(
    event: SearchEvent, joined_category_id: uuid.UUID | None
) -> uuid.UUID | None:
    """
    Category grouping key for one SearchEvent — normal relational join
    when the Requirement still exists (even if its category is
    genuinely None, e.g. a category_required search: that's the live,
    authoritative answer, not a fallback case). Only when
    event.requirement_id is None (the Requirement row was deleted,
    ON DELETE SET NULL) does this fall back to the immutable
    requirement_snapshot, per this module's approved design.
    """
    if event.requirement_id is not None:
        return joined_category_id
    snapshot_value = event.requirement_snapshot.get("product_category_id")
    return uuid.UUID(snapshot_value) if snapshot_value else None


def _has_certification_gap(certifications_signal: dict[str, object]) -> bool:
    """
    True only when this candidate's search requested at least one
    certification (points_possible > 0) AND at least one requested
    certification has no VERIFIED evidence (evidence_found is a strict
    subset of requested) — a structural fact already computed by
    requirement_matching_service._score_certifications, not a new
    threshold.
    """
    points_possible = certifications_signal["points_possible"]
    if not isinstance(points_possible, int | float) or points_possible <= 0:
        return False
    requested = certifications_signal["requested"]
    evidence_found = certifications_signal["evidence_found"]
    assert isinstance(requested, list) and isinstance(evidence_found, list)
    return len(evidence_found) < len(requested)


def _has_location_gap(location_signal: dict[str, object]) -> bool:
    """
    True only when this candidate's search requested at least one
    location dimension (points_possible > 0) AND full credit wasn't
    earned — mirrors _has_certification_gap's reasoning exactly.
    """
    points_possible = location_signal["points_possible"]
    points_earned = location_signal["points_earned"]
    if not isinstance(points_possible, int | float) or points_possible <= 0:
        return False
    assert isinstance(points_earned, int | float)
    return points_earned < points_possible


def _finalize_category(
    product_category_id: uuid.UUID, acc: _CategoryAccumulator
) -> CategoryCoverageGap:
    search_count = acc.search_count
    returned = acc.returned_candidate_count
    return CategoryCoverageGap(
        product_category_id=product_category_id,
        search_count=search_count,
        zero_offering_search_count=acc.zero_offering_search_count,
        fully_excluded_search_count=acc.fully_excluded_search_count,
        avg_candidates_considered=acc.candidates_considered_sum / search_count,
        avg_excluded_for_hard_criteria=acc.excluded_for_hard_criteria_sum / search_count,
        avg_returned_count=acc.returned_count_sum / search_count,
        more_candidates_may_exist_rate=acc.more_candidates_may_exist_count / search_count,
        returned_candidate_count=returned,
        certification_requested_count=acc.certification_requested_count,
        certification_gap_count=acc.certification_gap_count,
        certification_gap_rate=(
            acc.certification_gap_count / acc.certification_requested_count
            if acc.certification_requested_count > 0
            else None
        ),
        location_requested_count=acc.location_requested_count,
        location_gap_count=acc.location_gap_count,
        location_gap_rate=(
            acc.location_gap_count / acc.location_requested_count
            if acc.location_requested_count > 0
            else None
        ),
        avg_trust_points_earned=(acc.trust_points_earned_sum / returned if returned > 0 else None),
        avg_trust_points_possible=(
            acc.trust_points_possible_sum / returned if returned > 0 else None
        ),
    )


async def build_category_coverage_gaps(db: AsyncSession) -> list[CategoryCoverageGap]:
    """
    One CategoryCoverageGap per product_category_id that has at least
    one resolvable SearchEvent — a category never searched simply never
    appears in the result (never a fabricated zero-row entry).

    Sorted by search_count descending, product_category_id ascending
    as a deterministic tiebreak — a demand-volume ordering for
    readability, not a computed gap score (see module docstring).
    """
    event_rows = (
        await db.execute(
            select(SearchEvent, Requirement.product_category_id).outerjoin(
                Requirement, SearchEvent.requirement_id == Requirement.id
            )
        )
    ).all()

    accumulators: dict[uuid.UUID, _CategoryAccumulator] = {}
    event_id_to_category: dict[uuid.UUID, uuid.UUID] = {}

    for event, joined_category_id in event_rows:
        category_id = _resolve_category_id(event, joined_category_id)
        if category_id is None:
            continue
        event_id_to_category[event.id] = category_id
        acc = accumulators.setdefault(category_id, _CategoryAccumulator())
        acc.search_count += 1
        acc.candidates_considered_sum += event.total_candidates_considered
        acc.excluded_for_hard_criteria_sum += event.excluded_for_hard_criteria
        acc.returned_count_sum += event.returned_count
        if event.total_candidates_considered == 0:
            acc.zero_offering_search_count += 1
        elif event.returned_count == 0:
            acc.fully_excluded_search_count += 1
        if event.more_candidates_may_exist:
            acc.more_candidates_may_exist_count += 1

    if event_id_to_category:
        candidates = (
            (
                await db.execute(
                    select(SearchResultCandidate).where(
                        SearchResultCandidate.search_event_id.in_(event_id_to_category.keys())
                    )
                )
            )
            .scalars()
            .all()
        )
        for candidate in candidates:
            category_id = event_id_to_category.get(candidate.search_event_id)
            if category_id is None:
                continue  # pragma: no cover — every fetched candidate's event was just grouped above
            acc = accumulators[category_id]
            acc.returned_candidate_count += 1
            signals = candidate.result_snapshot["signals"]

            if _has_certification_gap(signals["certifications"]):
                acc.certification_requested_count += 1
                acc.certification_gap_count += 1
            elif signals["certifications"]["points_possible"] > 0:
                acc.certification_requested_count += 1

            if _has_location_gap(signals["location"]):
                acc.location_requested_count += 1
                acc.location_gap_count += 1
            elif signals["location"]["points_possible"] > 0:
                acc.location_requested_count += 1

            trust = signals["trust_tier"]
            acc.trust_points_earned_sum += trust["points_earned"]
            acc.trust_points_possible_sum += trust["points_possible"]

    gaps = [_finalize_category(category_id, acc) for category_id, acc in accumulators.items()]
    gaps.sort(key=lambda g: (-g.search_count, str(g.product_category_id)))
    return gaps


async def build_specification_coverage_gaps(db: AsyncSession) -> list[SpecificationCoverageGap]:
    """
    One SpecificationCoverageGap per ProductSpecification that has been
    used at least once as a RequirementSpecificationCriterion — per
    this module's approved design, the full specification taxonomy is
    never analyzed blindly.

    Sorted by times_used_as_criterion descending, specification_id
    ascending as a deterministic tiebreak — same readability-ordering
    reasoning as build_category_coverage_gaps.
    """
    usage_rows = (
        await db.execute(
            select(RequirementSpecificationCriterion.specification_id, func.count()).group_by(
                RequirementSpecificationCriterion.specification_id
            )
        )
    ).all()
    if not usage_rows:
        return []

    spec_ids = [row[0] for row in usage_rows]
    times_used_by_spec = {row[0]: row[1] for row in usage_rows}

    specifications = (
        (
            await db.execute(
                select(ProductSpecification).where(ProductSpecification.id.in_(spec_ids))
            )
        )
        .scalars()
        .all()
    )

    offerings_in_category_cache: dict[uuid.UUID, int] = {}

    async def _offerings_in_category(category_id: uuid.UUID) -> int:
        if category_id not in offerings_in_category_cache:
            result = await db.execute(
                select(func.count(Offering.id))
                .select_from(Offering)
                .join(Product, Offering.product_id == Product.id)
                .where(
                    Product.category_id == category_id,
                    Product.status == ProductStatus.PUBLISHED,
                    Offering.status == OfferingStatus.ACTIVE,
                )
            )
            offerings_in_category_cache[category_id] = result.scalar_one()
        return offerings_in_category_cache[category_id]

    gaps: list[SpecificationCoverageGap] = []
    for spec in specifications:
        offerings_in_category = await _offerings_in_category(spec.category_id)
        offerings_with_value_result = await db.execute(
            select(func.count(Offering.id))
            .select_from(Offering)
            .join(Product, Offering.product_id == Product.id)
            .join(
                ProductAttribute,
                and_(
                    ProductAttribute.product_id == Product.id,
                    ProductAttribute.specification_id == spec.id,
                ),
            )
            .where(
                Product.category_id == spec.category_id,
                Product.status == ProductStatus.PUBLISHED,
                Offering.status == OfferingStatus.ACTIVE,
            )
        )
        offerings_with_value = offerings_with_value_result.scalar_one()

        gaps.append(
            SpecificationCoverageGap(
                specification_id=spec.id,
                specification_name=spec.name,
                product_category_id=spec.category_id,
                times_used_as_criterion=times_used_by_spec[spec.id],
                offerings_in_category=offerings_in_category,
                offerings_with_attribute_value=offerings_with_value,
                coverage_rate=(
                    offerings_with_value / offerings_in_category
                    if offerings_in_category > 0
                    else None
                ),
            )
        )

    gaps.sort(key=lambda g: (-g.times_used_as_criterion, str(g.specification_id)))
    return gaps


async def build_data_gap_report(db: AsyncSession) -> DataGapReport:
    """The single composite entry point — no independent computation of
    its own, purely assembles the two builders above."""
    categories = await build_category_coverage_gaps(db)
    specifications = await build_specification_coverage_gaps(db)
    return DataGapReport(categories=categories, specifications=specifications)
