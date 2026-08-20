"""
Data Gap Intelligence tests — Module 7C. Exercises data_gap_service
against real SearchEvent/SearchResultCandidate/RequirementSpecificationCriterion/
ProductAttribute rows produced through the real API (matches.py's
compute_matches + search_telemetry_service.record_search — Modules
7A-2/7B, unmodified), plus a small amount of direct-DB setup for
scenarios (more_candidates_may_exist) that would otherwise require an
impractically large fixture (500+ offerings) to trigger for real —
same direct-mutation technique test_search_telemetry.py already uses.

No test here exercises a "low_trust_rate" or similar hardcoded-cutoff
field, because data_gap_service deliberately doesn't have one — see
that module's own docstring. Trust is asserted via the raw
avg_trust_points_earned/avg_trust_points_possible numbers instead.

Reuses test_companies.py's/test_product_graph.py's/
test_requirement_matching.py's established fixtures, same pattern
test_search_telemetry.py itself uses.
"""

import uuid

import pytest
from sqlalchemy import func, select

from app.db.session import AsyncSessionLocal
from app.models.offering import Offering
from app.models.product import Product
from app.models.product_attribute import ProductAttribute
from app.models.product_specification import ProductSpecification
from app.models.requirement import Requirement, RequirementSpecificationCriterion
from app.models.search_event import SearchEvent, SearchResultCandidate
from app.services.data_gap_service import (
    build_category_coverage_gaps,
    build_data_gap_report,
    build_specification_coverage_gaps,
)
from tests.test_companies import _register_verified
from tests.test_product_graph import (
    _create_category,
    _create_product,
    _create_specification,
    _create_verified_company,
    _publish,
)
from tests.test_requirement_matching import (
    _create_company_at,
    _create_requirement,
    _get_matches,
    _offer,
)


def _category_gap(gaps, category_id: str):
    return next((g for g in gaps if str(g.product_category_id) == category_id), None)


# --------------------------------------------------------------------------
# A/B — zero-offering / fully-excluded coverage
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_zero_offering_category_is_reported(client):
    user = await _register_verified(client, "gap-zero@example.com")
    category = await _create_category(client, user, "Gap Zero Offering Category")
    requirement = await _create_requirement(client, user, product_category_id=category["id"])
    data = await _get_matches(client, user, requirement["id"])
    assert data["total_candidates_considered"] == 0

    async with AsyncSessionLocal() as db:
        gaps = await build_category_coverage_gaps(db)
    gap = _category_gap(gaps, category["id"])
    assert gap is not None
    assert gap.search_count == 1
    assert gap.zero_offering_search_count == 1
    assert gap.fully_excluded_search_count == 0
    assert gap.avg_candidates_considered == 0.0
    assert gap.avg_returned_count == 0.0


@pytest.mark.asyncio
async def test_fully_excluded_category_is_reported(client):
    user = await _register_verified(client, "gap-excluded@example.com")
    category = await _create_category(client, user, "Gap Fully Excluded Category")
    power = await _create_specification(
        client, user, category["id"], name="Power", datatype="number"
    )
    below_threshold_product = await _create_product(
        client,
        user,
        category["id"],
        name="Gap Below Threshold Product",
        attributes=[{"specification_id": power["id"], "value": "2"}],
    )
    await _publish(client, user, below_threshold_product["id"])
    owner, company = await _create_verified_company(
        client, "gap-excluded-co@example.com", "Gap Excluded Co"
    )
    await _offer(client, owner, company, below_threshold_product)

    requirement = await _create_requirement(
        client,
        user,
        product_category_id=category["id"],
        criteria=[{"specification_id": power["id"], "operator": "gte", "value": 5.0}],
    )
    data = await _get_matches(client, user, requirement["id"])
    assert data["total_candidates_considered"] == 1
    assert data["returned_count"] == 0

    async with AsyncSessionLocal() as db:
        gaps = await build_category_coverage_gaps(db)
    gap = _category_gap(gaps, category["id"])
    assert gap is not None
    assert gap.zero_offering_search_count == 0
    assert gap.fully_excluded_search_count == 1
    assert gap.avg_excluded_for_hard_criteria == 1.0


# --------------------------------------------------------------------------
# C/D — certification and geographic gaps (returned candidates only)
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_certification_evidence_gap_is_reported(client):
    user = await _register_verified(client, "gap-cert@example.com")
    category = await _create_category(client, user, "Gap Certification Category")
    product = await _create_product(client, user, category["id"], name="Gap Certification Product")
    await _publish(client, user, product["id"])
    owner, company = await _create_verified_company(
        client, "gap-cert-co@example.com", "Gap Certification Co"
    )
    await _offer(client, owner, company, product)

    requirement = await _create_requirement(
        client, user, product_category_id=category["id"], certifications=["ISO"]
    )
    data = await _get_matches(client, user, requirement["id"])
    assert data["returned_count"] == 1
    assert data["matches"][0]["signals"]["certifications"]["evidence_found"] == []

    async with AsyncSessionLocal() as db:
        gaps = await build_category_coverage_gaps(db)
    gap = _category_gap(gaps, category["id"])
    assert gap.certification_requested_count == 1
    assert gap.certification_gap_count == 1
    assert gap.certification_gap_rate == 1.0
    # Never requested in this category, so location must stay unmeasured
    # (None), not silently 0.0.
    assert gap.location_requested_count == 0
    assert gap.location_gap_rate is None


@pytest.mark.asyncio
async def test_geographic_gap_is_reported(client):
    user = await _register_verified(client, "gap-geo@example.com")
    category = await _create_category(client, user, "Gap Geographic Category")
    product = await _create_product(client, user, category["id"], name="Gap Geographic Product")
    await _publish(client, user, product["id"])
    owner, company = await _create_company_at(
        client,
        "gap-geo-co@example.com",
        "Gap Geographic Co",
        country="USA",
        state="California",
        city="San Jose",
    )
    await _offer(client, owner, company, product)

    requirement = await _create_requirement(
        client,
        user,
        product_category_id=category["id"],
        country="India",
        state="Maharashtra",
        city="Mumbai",
    )
    data = await _get_matches(client, user, requirement["id"])
    assert data["returned_count"] == 1
    assert data["matches"][0]["signals"]["location"]["points_earned"] == 0.0

    async with AsyncSessionLocal() as db:
        gaps = await build_category_coverage_gaps(db)
    gap = _category_gap(gaps, category["id"])
    assert gap.location_requested_count == 1
    assert gap.location_gap_count == 1
    assert gap.location_gap_rate == 1.0


# --------------------------------------------------------------------------
# E — trust/evidence (raw averages, no hidden cutoff)
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_trust_points_are_averaged_from_the_persisted_signal(client):
    user = await _register_verified(client, "gap-trust@example.com")
    category = await _create_category(client, user, "Gap Trust Category")
    product = await _create_product(client, user, category["id"], name="Gap Trust Product")
    await _publish(client, user, product["id"])
    owner, company = await _create_verified_company(
        client, "gap-trust-co@example.com", "Gap Trust Co"
    )
    await _offer(client, owner, company, product)

    requirement = await _create_requirement(client, user, product_category_id=category["id"])
    data = await _get_matches(client, user, requirement["id"])
    assert data["matches"][0]["signals"]["trust_tier"]["level"] == "email_verified"
    assert data["matches"][0]["signals"]["trust_tier"]["points_earned"] == 12.5

    async with AsyncSessionLocal() as db:
        gaps = await build_category_coverage_gaps(db)
    gap = _category_gap(gaps, category["id"])
    assert gap.avg_trust_points_earned == 12.5
    assert gap.avg_trust_points_possible == 50.0


# --------------------------------------------------------------------------
# F — specification attribute coverage (buyer-used specs only)
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_partial_specification_attribute_coverage(client):
    user = await _register_verified(client, "gap-spec-partial@example.com")
    category = await _create_category(client, user, "Gap Spec Partial Category")
    material = await _create_specification(
        client, user, category["id"], name="Material", datatype="text", unit=None
    )
    with_value = await _create_product(
        client,
        user,
        category["id"],
        name="Gap Spec With Value Product",
        attributes=[{"specification_id": material["id"], "value": "Steel"}],
    )
    without_value = await _create_product(
        client, user, category["id"], name="Gap Spec Without Value Product"
    )
    for p in (with_value, without_value):
        await _publish(client, user, p["id"])
    owner, company = await _create_verified_company(
        client, "gap-spec-partial-co@example.com", "Gap Spec Partial Co"
    )
    await _offer(client, owner, company, with_value, role="manufacturer")
    await _offer(client, owner, company, without_value, role="supplier")

    # Registers times_used_as_criterion — coverage is never analyzed for
    # a specification no buyer has ever asked about.
    await _create_requirement(
        client,
        user,
        product_category_id=category["id"],
        criteria=[{"specification_id": material["id"], "operator": "eq", "value": "Steel"}],
    )

    async with AsyncSessionLocal() as db:
        gaps = await build_specification_coverage_gaps(db)
    gap = next(g for g in gaps if str(g.specification_id) == material["id"])
    assert gap.times_used_as_criterion == 1
    assert gap.offerings_in_category == 2
    assert gap.offerings_with_attribute_value == 1
    assert gap.coverage_rate == 0.5


@pytest.mark.asyncio
async def test_full_specification_attribute_coverage(client):
    user = await _register_verified(client, "gap-spec-full@example.com")
    category = await _create_category(client, user, "Gap Spec Full Category")
    material = await _create_specification(
        client, user, category["id"], name="Material", datatype="text", unit=None
    )
    product = await _create_product(
        client,
        user,
        category["id"],
        name="Gap Spec Full Product",
        attributes=[{"specification_id": material["id"], "value": "Aluminum"}],
    )
    await _publish(client, user, product["id"])
    owner, company = await _create_verified_company(
        client, "gap-spec-full-co@example.com", "Gap Spec Full Co"
    )
    await _offer(client, owner, company, product)

    await _create_requirement(
        client,
        user,
        product_category_id=category["id"],
        criteria=[{"specification_id": material["id"], "operator": "eq", "value": "Aluminum"}],
    )

    async with AsyncSessionLocal() as db:
        gaps = await build_specification_coverage_gaps(db)
    gap = next(g for g in gaps if str(g.specification_id) == material["id"])
    assert gap.offerings_in_category == 1
    assert gap.offerings_with_attribute_value == 1
    assert gap.coverage_rate == 1.0


# --------------------------------------------------------------------------
# Never-searched / never-used data must not be fabricated
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_never_searched_category_is_not_fabricated(client):
    user = await _register_verified(client, "gap-neversearched@example.com")
    category = await _create_category(client, user, "Gap Never Searched Category")
    product = await _create_product(client, user, category["id"], name="Gap Never Searched Product")
    await _publish(client, user, product["id"])
    owner, company = await _create_verified_company(
        client, "gap-neversearched-co@example.com", "Gap Never Searched Co"
    )
    await _offer(client, owner, company, product)
    # Deliberately never create a Requirement/search against this category.

    async with AsyncSessionLocal() as db:
        gaps = await build_category_coverage_gaps(db)
    assert _category_gap(gaps, category["id"]) is None


# --------------------------------------------------------------------------
# G — operational ceiling signal stays structurally separate
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_more_candidates_may_exist_is_a_separate_operational_signal(client):
    user = await _register_verified(client, "gap-ceiling@example.com")
    category = await _create_category(client, user, "Gap Ceiling Category")
    product = await _create_product(client, user, category["id"], name="Gap Ceiling Product")
    await _publish(client, user, product["id"])
    owner, company = await _create_verified_company(
        client, "gap-ceiling-co@example.com", "Gap Ceiling Co"
    )
    await _offer(client, owner, company, product)

    requirement = await _create_requirement(client, user, product_category_id=category["id"])
    await _get_matches(client, user, requirement["id"])

    # Triggering the real 500-candidate ceiling would need 501 offerings
    # — direct DB mutation of the already-persisted SearchEvent is the
    # same technique test_search_telemetry.py's own immutability tests
    # use, applied here to exercise this one boolean cheaply.
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(SearchEvent).where(SearchEvent.requirement_id == uuid.UUID(requirement["id"]))
        )
        event = result.scalar_one()
        event.more_candidates_may_exist = True
        await db.commit()

    async with AsyncSessionLocal() as db:
        gaps = await build_category_coverage_gaps(db)
    gap = _category_gap(gaps, category["id"])
    assert gap.more_candidates_may_exist_rate == 1.0
    # Unaffected by the ceiling flag — nothing was ever requested along
    # either dimension in this scenario, so both stay unmeasured (None),
    # never silently folded into the operational rate above.
    assert gap.certification_gap_rate is None
    assert gap.location_gap_rate is None


# --------------------------------------------------------------------------
# Deterministic ordering
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_category_ordering_is_deterministic_and_demand_sorted(client):
    user = await _register_verified(client, "gap-order@example.com")
    busy_category = await _create_category(client, user, "Gap Order Busy Category")
    quiet_category = await _create_category(client, user, "Gap Order Quiet Category")

    busy_requirement = await _create_requirement(
        client, user, product_category_id=busy_category["id"]
    )
    await _get_matches(client, user, busy_requirement["id"])
    await _get_matches(client, user, busy_requirement["id"])
    quiet_requirement = await _create_requirement(
        client, user, product_category_id=quiet_category["id"]
    )
    await _get_matches(client, user, quiet_requirement["id"])

    async with AsyncSessionLocal() as db:
        first_call = await build_category_coverage_gaps(db)
        second_call = await build_category_coverage_gaps(db)

    first_order = [str(g.product_category_id) for g in first_call]
    second_order = [str(g.product_category_id) for g in second_call]
    assert first_order == second_order

    busy_index = first_order.index(busy_category["id"])
    quiet_index = first_order.index(quiet_category["id"])
    assert busy_index < quiet_index


# --------------------------------------------------------------------------
# Read-only behavior
# --------------------------------------------------------------------------


async def _table_counts(db) -> dict:
    counts = {}
    for model in (
        SearchEvent,
        SearchResultCandidate,
        Requirement,
        RequirementSpecificationCriterion,
        ProductSpecification,
        ProductAttribute,
        Product,
        Offering,
    ):
        result = await db.execute(select(func.count()).select_from(model))
        counts[model.__tablename__] = result.scalar_one()
    return counts


@pytest.mark.asyncio
async def test_data_gap_report_is_completely_read_only(client):
    user = await _register_verified(client, "gap-readonly@example.com")
    category = await _create_category(client, user, "Gap Read Only Category")
    material = await _create_specification(
        client, user, category["id"], name="Material", datatype="text", unit=None
    )
    product = await _create_product(
        client,
        user,
        category["id"],
        name="Gap Read Only Product",
        attributes=[{"specification_id": material["id"], "value": "Steel"}],
    )
    await _publish(client, user, product["id"])
    owner, company = await _create_verified_company(
        client, "gap-readonly-co@example.com", "Gap Read Only Co"
    )
    await _offer(client, owner, company, product)
    requirement = await _create_requirement(
        client,
        user,
        product_category_id=category["id"],
        certifications=["ISO"],
        criteria=[{"specification_id": material["id"], "operator": "eq", "value": "Steel"}],
    )
    await _get_matches(client, user, requirement["id"])

    async with AsyncSessionLocal() as db:
        before = await _table_counts(db)
        report = await build_data_gap_report(db)
        after = await _table_counts(db)

    assert before == after
    assert len(report.categories) >= 1
    assert len(report.specifications) >= 1
