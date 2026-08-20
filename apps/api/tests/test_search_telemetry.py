"""
Search telemetry tests — Module 7B. Covers SearchEvent/
SearchResultCandidate persistence, historical-snapshot independence
from later live-data mutation, ownership scoping, the fail-loud
transaction behavior, and a regression check that 7A-1/7A-2 request
handling (auth, ownership, response contract) is unchanged.

No test exists here for "no fabricated UserAction is created" as a
standalone assertion — per the approved Module 7B design, UserAction
was NOT built in this milestone (no existing application flow has a
legitimate emission point for it), so there is no model/table that
could be fabricated into in the first place. This is a deliberate
deferral, not an oversight — see search_telemetry_service.py's module
docstring.

Reuses test_companies.py's, test_product_graph.py's, and
test_requirement_matching.py's established fixtures — same pattern
test_requirement_matching.py itself uses against test_companies.py/
test_product_graph.py.
"""

import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.db.session import AsyncSessionLocal
from app.main import app as fastapi_app
from app.models.company import Company
from app.models.requirement import Requirement
from app.models.search_event import SearchEvent, SearchResultCandidate
from app.services import search_telemetry_service
from tests.test_companies import _auth_headers, _register_verified
from tests.test_product_graph import (
    _create_category,
    _create_product,
    _create_specification,
    _create_verified_company,
    _publish,
)
from tests.test_requirement_matching import _create_requirement, _get_matches, _offer


async def _fetch_search_events(requirement_id: str) -> list[SearchEvent]:
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(SearchEvent)
            .where(SearchEvent.requirement_id == uuid.UUID(requirement_id))
            .order_by(SearchEvent.searched_at.asc())
        )
        return list(result.scalars().all())


async def _fetch_candidates(search_event_id: uuid.UUID) -> list[SearchResultCandidate]:
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(SearchResultCandidate)
            .where(SearchResultCandidate.search_event_id == search_event_id)
            .order_by(SearchResultCandidate.rank.asc())
        )
        return list(result.scalars().all())


# --------------------------------------------------------------------------
# Persistence of a real execution
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_successful_search_creates_search_event_and_candidate(client):
    user = await _register_verified(client, "tel-success@example.com")
    category = await _create_category(client, user, "Telemetry Success Category")
    product = await _create_product(client, user, category["id"], name="Telemetry Success Product")
    await _publish(client, user, product["id"])
    owner, company = await _create_verified_company(
        client, "tel-success-co@example.com", "Telemetry Success Co"
    )
    offering = await _offer(client, owner, company, product)

    requirement = await _create_requirement(client, user, product_category_id=category["id"])
    data = await _get_matches(client, user, requirement["id"])
    assert data["returned_count"] == 1

    events = await _fetch_search_events(requirement["id"])
    assert len(events) == 1
    event = events[0]
    assert str(event.requirement_id) == requirement["id"]
    assert event.status == "computed"
    assert event.total_candidates_considered == 1
    assert event.excluded_for_hard_criteria == 0
    assert event.returned_count == 1
    assert event.raw_query_text == requirement["raw_query"]

    candidates = await _fetch_candidates(event.id)
    assert len(candidates) == 1
    assert str(candidates[0].offering_id) == offering["id"]
    assert candidates[0].rank == data["matches"][0]["rank"]
    assert candidates[0].score == data["matches"][0]["score"]


@pytest.mark.asyncio
async def test_zero_candidate_search_creates_search_event(client):
    user = await _register_verified(client, "tel-empty@example.com")
    category = await _create_category(client, user, "Telemetry Empty Category")
    requirement = await _create_requirement(client, user, product_category_id=category["id"])

    data = await _get_matches(client, user, requirement["id"])
    assert data["returned_count"] == 0

    events = await _fetch_search_events(requirement["id"])
    assert len(events) == 1
    assert events[0].status == "computed"
    assert events[0].total_candidates_considered == 0
    assert events[0].returned_count == 0
    assert await _fetch_candidates(events[0].id) == []


@pytest.mark.asyncio
async def test_category_required_search_is_recorded(client):
    user = await _register_verified(client, "tel-nocat@example.com")
    requirement = await _create_requirement(client, user)

    data = await _get_matches(client, user, requirement["id"])
    assert data["status"] == "category_required"

    events = await _fetch_search_events(requirement["id"])
    assert len(events) == 1
    event = events[0]
    assert event.status == "category_required"
    assert event.total_candidates_considered == 0
    assert event.returned_count == 0
    assert event.requirement_snapshot["product_category_id"] is None
    assert await _fetch_candidates(event.id) == []


@pytest.mark.asyncio
async def test_hard_filter_exclusion_count_persisted(client):
    user = await _register_verified(client, "tel-hardfilter@example.com")
    category = await _create_category(client, user, "Telemetry Hard Filter Category")
    power = await _create_specification(
        client, user, category["id"], name="Power", datatype="number"
    )

    matching_product = await _create_product(
        client,
        user,
        category["id"],
        name="Telemetry Matching Product",
        attributes=[{"specification_id": power["id"], "value": "10"}],
    )
    below_threshold_product = await _create_product(
        client,
        user,
        category["id"],
        name="Telemetry Below Threshold Product",
        attributes=[{"specification_id": power["id"], "value": "2"}],
    )
    for p in (matching_product, below_threshold_product):
        await _publish(client, user, p["id"])

    owner, company = await _create_verified_company(
        client, "tel-hardfilter-co@example.com", "Telemetry Hard Filter Co"
    )
    await _offer(client, owner, company, matching_product, role="manufacturer")
    await _offer(client, owner, company, below_threshold_product, role="supplier")

    requirement = await _create_requirement(
        client,
        user,
        product_category_id=category["id"],
        criteria=[{"specification_id": power["id"], "operator": "gte", "value": 5.0}],
    )
    data = await _get_matches(client, user, requirement["id"])
    assert data["excluded_for_hard_criteria"] == 1
    assert data["returned_count"] == 1

    events = await _fetch_search_events(requirement["id"])
    assert events[0].total_candidates_considered == 2
    assert events[0].excluded_for_hard_criteria == 1
    assert events[0].returned_count == 1


@pytest.mark.asyncio
async def test_result_snapshot_matches_api_response_exactly(client):
    user = await _register_verified(client, "tel-snapshot@example.com")
    category = await _create_category(client, user, "Telemetry Snapshot Category")
    product = await _create_product(client, user, category["id"], name="Telemetry Snapshot Product")
    await _publish(client, user, product["id"])
    owner, company = await _create_verified_company(
        client, "tel-snapshot-co@example.com", "Telemetry Snapshot Co"
    )
    await _offer(client, owner, company, product)

    requirement = await _create_requirement(client, user, product_category_id=category["id"])
    data = await _get_matches(client, user, requirement["id"])
    api_match = data["matches"][0]

    events = await _fetch_search_events(requirement["id"])
    candidates = await _fetch_candidates(events[0].id)
    stored = candidates[0]

    assert stored.rank == api_match["rank"]
    assert stored.score == api_match["score"]
    assert stored.result_snapshot["score_breakdown"] == api_match["score_breakdown"]
    assert stored.result_snapshot["signals"] == api_match["signals"]
    assert stored.result_snapshot["company"]["id"] == api_match["company"]["id"]
    assert stored.result_snapshot["product"]["id"] == api_match["product"]["id"]


# --------------------------------------------------------------------------
# Historical independence — snapshots must not move when live data does
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_requirement_snapshot_immutable_to_later_mutation(client):
    user = await _register_verified(client, "tel-reqmut@example.com")
    category = await _create_category(client, user, "Telemetry Req Mutation Category")
    requirement = await _create_requirement(
        client, user, product_category_id=category["id"], city="Mumbai"
    )
    data = await _get_matches(client, user, requirement["id"])
    assert data["status"] == "computed"

    events = await _fetch_search_events(requirement["id"])
    event_id = events[0].id
    assert events[0].requirement_snapshot["city"] == "Mumbai"

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Requirement).where(Requirement.id == uuid.UUID(requirement["id"]))
        )
        req_row = result.scalar_one()
        req_row.city = "Delhi"
        await db.commit()

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(SearchEvent).where(SearchEvent.id == event_id))
        reloaded = result.scalar_one()
        assert reloaded.requirement_snapshot["city"] == "Mumbai"


@pytest.mark.asyncio
async def test_result_snapshot_immutable_to_later_company_change(client):
    user = await _register_verified(client, "tel-offmut@example.com")
    category = await _create_category(client, user, "Telemetry Offering Mutation Category")
    product = await _create_product(
        client, user, category["id"], name="Telemetry Offering Mutation Product"
    )
    await _publish(client, user, product["id"])
    owner, company = await _create_verified_company(
        client, "tel-offmut-co@example.com", "Telemetry Offering Mutation Co"
    )
    await _offer(client, owner, company, product)

    requirement = await _create_requirement(client, user, product_category_id=category["id"])
    data = await _get_matches(client, user, requirement["id"])
    original_name = data["matches"][0]["company"]["name"]

    events = await _fetch_search_events(requirement["id"])
    candidates = await _fetch_candidates(events[0].id)
    candidate_id = candidates[0].id

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Company).where(Company.id == uuid.UUID(company["id"])))
        company_row = result.scalar_one()
        company_row.name = "Renamed After Search"
        await db.commit()

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(SearchResultCandidate).where(SearchResultCandidate.id == candidate_id)
        )
        reloaded = result.scalar_one()
        assert reloaded.result_snapshot["company"]["name"] == original_name
        assert reloaded.result_snapshot["company"]["name"] != "Renamed After Search"


# --------------------------------------------------------------------------
# Repeated searches / ownership / auth regression
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_repeated_identical_searches_create_separate_events(client):
    user = await _register_verified(client, "tel-repeat@example.com")
    category = await _create_category(client, user, "Telemetry Repeat Category")
    requirement = await _create_requirement(client, user, product_category_id=category["id"])

    await _get_matches(client, user, requirement["id"])
    await _get_matches(client, user, requirement["id"])

    events = await _fetch_search_events(requirement["id"])
    assert len(events) == 2
    assert events[0].id != events[1].id


@pytest.mark.asyncio
async def test_search_events_scoped_by_owner_and_cross_user_access_denied(client):
    user_a = await _register_verified(client, "tel-owner-a@example.com")
    user_b = await _register_verified(client, "tel-owner-b@example.com")
    category = await _create_category(client, user_a, "Telemetry Owner Category")
    requirement = await _create_requirement(client, user_a, product_category_id=category["id"])
    await _get_matches(client, user_a, requirement["id"])

    async with AsyncSessionLocal() as db:
        a_events = (
            (
                await db.execute(
                    select(SearchEvent).where(
                        SearchEvent.created_by == uuid.UUID(requirement["created_by"])
                    )
                )
            )
            .scalars()
            .all()
        )
    assert len(a_events) == 1

    # Existing 7A-1/7A-2 ownership behavior (404-not-403) must be
    # unchanged by adding telemetry, and a rejected cross-user request
    # must never reach search_telemetry_service.record_search at all.
    res = await client.get(
        f"/api/v1/requirements/{requirement['id']}/matches", headers=_auth_headers(user_b)
    )
    assert res.status_code == 404

    events_after = await _fetch_search_events(requirement["id"])
    assert len(events_after) == 1  # unchanged — user_b's rejected attempt recorded nothing


@pytest.mark.asyncio
async def test_matches_endpoint_requires_auth(client):
    user = await _register_verified(client, "tel-noauth@example.com")
    category = await _create_category(client, user, "Telemetry No Auth Category")
    requirement = await _create_requirement(client, user, product_category_id=category["id"])

    res = await client.get(f"/api/v1/requirements/{requirement['id']}/matches")
    assert res.status_code == 401
    assert await _fetch_search_events(requirement["id"]) == []


# --------------------------------------------------------------------------
# Fail-loud transaction behavior
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_telemetry_persistence_failure_is_not_silently_swallowed(client, monkeypatch):
    user = await _register_verified(client, "tel-failure@example.com")
    category = await _create_category(client, user, "Telemetry Failure Category")
    requirement = await _create_requirement(client, user, product_category_id=category["id"])

    async def _failing_record_search(*args, **kwargs):
        raise RuntimeError("simulated telemetry persistence failure")

    monkeypatch.setattr(search_telemetry_service, "record_search", _failing_record_search)

    # A dedicated client with raise_app_exceptions=False, not the shared
    # `client` fixture — Starlette's ServerErrorMiddleware re-raises an
    # unhandled exception after sending its 500 response (so a real ASGI
    # server can log it); over a genuine HTTP connection only the 500
    # response is visible to the caller, which is exactly what this test
    # verifies actually happened.
    transport = ASGITransport(app=fastapi_app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as raw_client:
        res = await raw_client.get(
            f"/api/v1/requirements/{requirement['id']}/matches", headers=_auth_headers(user)
        )
    assert res.status_code == 500
    assert res.json()["success"] is False

    # The failure must not have produced a silently-partial write either.
    assert await _fetch_search_events(requirement["id"]) == []
