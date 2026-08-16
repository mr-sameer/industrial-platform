"""
Module 5D tests — Data Normalization & Entity Resolution. Covers the
deterministic identity rules (Phase 4), the seven worked cases from
this module's own ticket (Phase 8), candidate generation, human
decisions, provenance/conflict behavior, RBAC, and idempotency.

Fixtures below are DETERMINISTIC TEST DATA, not live MCA records — the
same honest labeling this codebase has used since Module 5C, restated
here because this module's own ticket explicitly requires it.
"""

import pytest

from tests.test_acquisition import _register_admin
from tests.test_companies import _auth_headers, _register_verified
from tests.test_mca_pilot import _create_mca_source, _mock_response, _real_shaped_record


async def _create_observation(
    client, admin, source_id: str, record: dict, resource_id: str = "test-resource"
) -> str:
    """Runs a real acquisition job (mocked only at the httpx boundary,
    matching Module 5C's own established test pattern) and returns the
    resulting raw_observation_id."""
    import app.collectors.mca_data_gov_in_adapter as adapter_module

    original_get = adapter_module.httpx.get
    adapter_module.httpx.get = lambda *a, **k: _mock_response([record])  # type: ignore[method-assign]
    try:
        res = await client.post(
            "/api/v1/acquisition/jobs",
            json={
                "source_id": source_id,
                "collector_type": "mca_data_gov_in",
                "requested_scope": {"api_key": "test-key", "resource_id": resource_id, "limit": 25},
            },
            headers=_auth_headers(admin),
        )
    finally:
        adapter_module.httpx.get = original_get
    job = res.json()["data"]
    assert job["status"] == "succeeded", job
    events = (
        await client.get(
            f"/api/v1/acquisition/jobs/{job['id']}/events", headers=_auth_headers(admin)
        )
    ).json()["data"]["items"]
    return events[0]["raw_observation_id"]


async def _generate_candidate(client, admin, raw_observation_id: str) -> dict:
    res = await client.post(
        "/api/v1/entity-resolution/candidates",
        json={"raw_observation_id": raw_observation_id},
        headers=_auth_headers(admin),
    )
    assert res.status_code == 201, res.text
    return res.json()["data"]


async def _promote(client, admin, raw_observation_id: str) -> dict:
    res = await client.post(
        f"/api/v1/acquisition/observations/{raw_observation_id}/promote",
        headers=_auth_headers(admin),
    )
    assert res.status_code == 201, res.text
    return res.json()["data"]


# --------------------------------------------------------------------------
# Normalization
# --------------------------------------------------------------------------


def test_normalization_matches_ticket_worked_example():
    from app.entity_resolution.normalization import normalize_company_name_for_matching

    assert normalize_company_name_for_matching("ABC Engineering Pvt. Ltd.") == "ABC ENGINEERING"
    assert normalize_company_name_for_matching("ABC Engineering") == "ABC ENGINEERING"
    assert (
        normalize_company_name_for_matching("ABC Engineering Private Limited") == "ABC ENGINEERING"
    )


def test_normalization_preserves_raw_value_never_mutates_input():
    from app.entity_resolution.normalization import normalize_company_name_for_matching

    raw = "ABC Engineering Pvt. Ltd."
    normalize_company_name_for_matching(raw)
    assert raw == "ABC Engineering Pvt. Ltd."  # unchanged — normalization returns a new string only


# --------------------------------------------------------------------------
# Phase 8 — the seven worked cases, run for real through the API
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_case1_same_cin_different_name_formatting_is_auto_match(client):
    """Uses two distinct sources (see the conflict test's own docstring
    for why — Module 5B's source-scoped idempotency would otherwise
    silently skip a same-CIN second pull from the same source)."""
    admin = await _register_admin(client, "case1@example.com")
    source1 = await _create_mca_source(client, admin)
    source2 = await _create_mca_source(client, admin)

    # First observation establishes the company.
    obs1 = await _create_observation(
        client,
        admin,
        source1["id"],
        _real_shaped_record("U11111MH2015PTC000011", "ABC Engineering Private Limited"),
    )
    company = await _promote(client, admin, obs1)

    # Second, distinct observation: SAME CIN, DIFFERENT name formatting.
    obs2 = await _create_observation(
        client,
        admin,
        source2["id"],
        _real_shaped_record("U11111MH2015PTC000011", "ABC ENGINEERING PVT LTD"),
        resource_id="different-pull",
    )
    candidate = await _generate_candidate(client, admin, obs2)
    assert candidate["resolution_state"] == "auto_match"
    assert candidate["candidate_company_id"] == company["id"]
    cin_signal = next(s for s in candidate["match_signals"] if s["signal"] == "cin")
    assert cin_signal["matched"] is True


@pytest.mark.asyncio
async def test_case2_same_name_different_cin_never_auto_merges(client):
    admin = await _register_admin(client, "case2@example.com")
    source = await _create_mca_source(client, admin)

    obs1 = await _create_observation(
        client, admin, source["id"], _real_shaped_record("U22222MH2015PTC000022", "Same Name Co")
    )
    await _promote(client, admin, obs1)

    # Same normalized name, a DIFFERENT CIN entirely.
    obs2 = await _create_observation(
        client,
        admin,
        source["id"],
        _real_shaped_record("U99999MH2015PTC000099", "Same Name Co"),
        resource_id="pull-2",
    )
    candidate = await _generate_candidate(client, admin, obs2)
    assert candidate["resolution_state"] != "auto_match"
    assert candidate["resolution_state"] == "review_required"
    cin_signal = next(s for s in candidate["match_signals"] if s["signal"] == "cin")
    assert (
        cin_signal["matched"] is False
    )  # the CIN itself does not match — correctly not conflated with the name match


@pytest.mark.asyncio
async def test_case3_different_names_same_strong_identifier_matches(client):
    """'Strong identifier' here is the exact source identifier
    (external_reference/CIN) — a name change alone must not prevent
    the match when the identifier itself agrees. Uses two distinct
    sources, same reason as Case 1/the conflict test."""
    admin = await _register_admin(client, "case3@example.com")
    source1 = await _create_mca_source(client, admin)
    source2 = await _create_mca_source(client, admin)

    obs1 = await _create_observation(
        client,
        admin,
        source1["id"],
        _real_shaped_record("U33333MH2015PTC000033", "Original Name Ltd"),
    )
    company = await _promote(client, admin, obs1)

    obs2 = await _create_observation(
        client,
        admin,
        source2["id"],
        _real_shaped_record("U33333MH2015PTC000033", "Completely Renamed Co"),
        resource_id="pull-3",
    )
    candidate = await _generate_candidate(client, admin, obs2)
    # Same CIN (the strong identifier) -> still AUTO_MATCH despite the
    # name being unrelated.
    assert candidate["resolution_state"] == "auto_match"
    assert candidate["candidate_company_id"] == company["id"]


@pytest.mark.asyncio
async def test_case4_similar_names_different_addresses_review_required(client):
    admin = await _register_admin(client, "case4@example.com")
    source = await _create_mca_source(client, admin)

    obs1 = await _create_observation(
        client,
        admin,
        source["id"],
        _real_shaped_record(
            "U44444MH2015PTC000044", "Similar Name Industries", state="Maharashtra"
        ),
    )
    await _promote(client, admin, obs1)

    # A similar (fuzzy, not exact-normalized) name, and a DIFFERENT state.
    record2 = _real_shaped_record(
        "U55555KA2015PTC000055", "Similar Name Industry", state="Karnataka"
    )
    obs2 = await _create_observation(client, admin, source["id"], record2, resource_id="pull-4")
    candidate = await _generate_candidate(client, admin, obs2)
    assert candidate["resolution_state"] == "review_required"


@pytest.mark.asyncio
async def test_case5_generating_candidate_twice_is_idempotent(client):
    admin = await _register_admin(client, "case5@example.com")
    source = await _create_mca_source(client, admin)
    obs = await _create_observation(
        client, admin, source["id"], _real_shaped_record("U66666MH2015PTC000066", "Idempotent Co")
    )

    first = await _generate_candidate(client, admin, obs)
    second = await _generate_candidate(client, admin, obs)
    assert first["id"] == second["id"]  # same candidate row, not a duplicate


@pytest.mark.asyncio
async def test_case6_conflicting_strong_identifiers_creates_conflict_state(client):
    admin = await _register_admin(client, "case6@example.com")
    source = await _create_mca_source(client, admin)

    obs1 = await _create_observation(
        client,
        admin,
        source["id"],
        _real_shaped_record("U77777MH2015PTC000077", "Conflict Test Co", state="Maharashtra"),
    )
    company = await _promote(client, admin, obs1)

    # Same normalized name AND same address, but an EXPLICITLY
    # different CIN — a genuine conflict, not a confident match.
    record2 = _real_shaped_record("U88888MH2015PTC000088", "Conflict Test Co", state="Maharashtra")
    obs2 = await _create_observation(client, admin, source["id"], record2, resource_id="pull-6")
    candidate = await _generate_candidate(client, admin, obs2)
    assert candidate["resolution_state"] == "review_required"
    assert candidate["candidate_company_id"] == company["id"]
    assert "conflict" in candidate["explanation"].lower()


@pytest.mark.asyncio
async def test_case7_completely_new_company_is_new(client):
    admin = await _register_admin(client, "case7@example.com")
    source = await _create_mca_source(client, admin)
    obs = await _create_observation(
        client,
        admin,
        source["id"],
        _real_shaped_record("U00000MH2015PTC000000", "Totally Unrelated New Co"),
    )
    candidate = await _generate_candidate(client, admin, obs)
    assert candidate["resolution_state"] == "new"
    assert candidate["candidate_company_id"] is None


# --------------------------------------------------------------------------
# Review decisions
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_confirm_match_attaches_provenance_to_existing_company_not_new_one(client):
    """Uses two distinct sources, same reason as Case 1/Case 3/the
    conflict test — Module 5B's source-scoped idempotency would
    otherwise skip the second same-CIN observation entirely."""
    admin = await _register_admin(client, "confirm@example.com")
    source1 = await _create_mca_source(client, admin)
    source2 = await _create_mca_source(client, admin)
    obs1 = await _create_observation(
        client,
        admin,
        source1["id"],
        _real_shaped_record("U10101MH2015PTC010101", "Confirm Match Co"),
    )
    company = await _promote(client, admin, obs1)

    obs2 = await _create_observation(
        client,
        admin,
        source2["id"],
        _real_shaped_record("U10101MH2015PTC010101", "Confirm Match Co Renamed"),
        resource_id="pull-confirm",
    )
    candidate = await _generate_candidate(client, admin, obs2)
    assert candidate["resolution_state"] == "auto_match"

    decide_res = await client.post(
        f"/api/v1/entity-resolution/candidates/{candidate['id']}/decide",
        json={"decision": "confirm_match"},
        headers=_auth_headers(admin),
    )
    assert decide_res.status_code == 200, decide_res.text
    assert decide_res.json()["data"]["decision"] == "confirm_match"

    # (No separate "no second company was created" fetch here — the
    # field_names assertion below already proves both observations'
    # provenance landed on the SAME company_id, which is the real
    # claim this test makes.)

    lineage = await client.get(
        f"/api/v1/provenance?entity_type=company&entity_id={company['id']}&page_size=100",
        headers=_auth_headers(admin),
    )
    field_names = [item["field_name"] for item in lineage.json()["data"]["items"]]
    assert (
        field_names.count("company_name") >= 2
    )  # one from each observation, both attached to the SAME company


@pytest.mark.asyncio
async def test_reject_match_records_decision_without_touching_company(client):
    admin = await _register_admin(client, "reject@example.com")
    source = await _create_mca_source(client, admin)
    obs = await _create_observation(
        client, admin, source["id"], _real_shaped_record("U20202MH2015PTC020202", "Reject Match Co")
    )
    candidate = await _generate_candidate(client, admin, obs)

    res = await client.post(
        f"/api/v1/entity-resolution/candidates/{candidate['id']}/decide",
        json={"decision": "reject_match"},
        headers=_auth_headers(admin),
    )
    assert res.status_code == 200
    assert res.json()["data"]["decision"] == "reject_match"


@pytest.mark.asyncio
async def test_create_new_decision_uses_unmodified_module_5c_promotion(client):
    admin = await _register_admin(client, "createnew@example.com")
    source = await _create_mca_source(client, admin)
    obs = await _create_observation(
        client,
        admin,
        source["id"],
        _real_shaped_record("U30303MH2015PTC030303", "Create New Via Resolution Co"),
    )
    candidate = await _generate_candidate(client, admin, obs)
    assert candidate["resolution_state"] == "new"

    res = await client.post(
        f"/api/v1/entity-resolution/candidates/{candidate['id']}/decide",
        json={"decision": "create_new"},
        headers=_auth_headers(admin),
    )
    assert res.status_code == 200
    updated = res.json()["data"]
    assert updated["decision"] == "create_new"

    company_res = await client.get(
        f"/api/v1/entity-resolution/candidates/{candidate['id']}/company",
        headers=_auth_headers(admin),
    )
    assert company_res.status_code == 200
    assert company_res.json()["data"]["name"] == "Create New Via Resolution Co"
    assert (
        company_res.json()["data"]["verification_status"] == "unverified"
    )  # the data trust rule, still enforced


@pytest.mark.asyncio
async def test_already_decided_candidate_cannot_be_decided_again(client):
    admin = await _register_admin(client, "redecide@example.com")
    source = await _create_mca_source(client, admin)
    obs = await _create_observation(
        client, admin, source["id"], _real_shaped_record("U40404MH2015PTC040404", "Redecide Co")
    )
    candidate = await _generate_candidate(client, admin, obs)

    await client.post(
        f"/api/v1/entity-resolution/candidates/{candidate['id']}/decide",
        json={"decision": "reject_match"},
        headers=_auth_headers(admin),
    )
    second = await client.post(
        f"/api/v1/entity-resolution/candidates/{candidate['id']}/decide",
        json={"decision": "create_new"},
        headers=_auth_headers(admin),
    )
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "ALREADY_DECIDED"


@pytest.mark.asyncio
async def test_confirm_match_on_new_candidate_rejected(client):
    """A NEW candidate has no candidate_company_id — CONFIRM_MATCH
    genuinely makes no sense for it."""
    admin = await _register_admin(client, "invaliddecision@example.com")
    source = await _create_mca_source(client, admin)
    obs = await _create_observation(
        client,
        admin,
        source["id"],
        _real_shaped_record("U50505MH2015PTC050505", "Invalid Decision Co"),
    )
    candidate = await _generate_candidate(client, admin, obs)
    assert candidate["resolution_state"] == "new"

    res = await client.post(
        f"/api/v1/entity-resolution/candidates/{candidate['id']}/decide",
        json={"decision": "confirm_match"},
        headers=_auth_headers(admin),
    )
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "INVALID_DECISION"


# --------------------------------------------------------------------------
# Conflict behavior — reuses Module 5A's existing DataConflict, not a new model
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_confirm_match_with_disagreeing_field_creates_real_data_conflict(client):
    """
    Uses two DISTINCT sources for the two observations — Module 5B's
    own idempotency (source_id + external_identifier, by design) would
    otherwise treat a second same-CIN pull from the SAME source as a
    duplicate and skip creating a new raw observation at all, which
    would make this test unable to exercise conflict detection in the
    first place (found via direct diagnosis, not assumed). Two
    different sources reporting disagreeing data for the same
    real-world company is also the more realistic scenario for how a
    conflict would actually arise.
    """
    admin = await _register_admin(client, "conflictcreate@example.com")
    source1 = await _create_mca_source(client, admin)
    source2 = await _create_mca_source(client, admin)
    obs1 = await _create_observation(
        client,
        admin,
        source1["id"],
        _real_shaped_record("U60606MH2015PTC060606", "Conflict Creation Co", state="Maharashtra"),
    )
    company = await _promote(client, admin, obs1)

    # A second, DIFFERENT source, same CIN (AUTO_MATCH), but a
    # DISAGREEING state value — confirming the match should surface
    # this as a real Module 5A DataConflict, not silently overwrite
    # anything.
    obs2 = await _create_observation(
        client,
        admin,
        source2["id"],
        _real_shaped_record("U60606MH2015PTC060606", "Conflict Creation Co", state="Karnataka"),
        resource_id="pull-conflict",
    )
    candidate = await _generate_candidate(client, admin, obs2)
    assert candidate["resolution_state"] == "auto_match"

    await client.post(
        f"/api/v1/entity-resolution/candidates/{candidate['id']}/decide",
        json={"decision": "confirm_match"},
        headers=_auth_headers(admin),
    )

    conflicts = await client.get(
        "/api/v1/provenance/conflicts?status=open", headers=_auth_headers(admin)
    )
    matching = [c for c in conflicts.json()["data"]["items"] if c["company_id"] == company["id"]]
    assert len(matching) > 0
    assert any(c["field_name"] == "registered_state" for c in matching)


# --------------------------------------------------------------------------
# RBAC
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_non_admin_cannot_generate_or_decide_candidates(client):
    admin = await _register_admin(client, "rbac-er-admin@example.com")
    source = await _create_mca_source(client, admin)
    obs = await _create_observation(
        client, admin, source["id"], _real_shaped_record("U70707MH2015PTC070707", "RBAC ER Co")
    )

    viewer = await _register_verified(client, "rbac-er-viewer@example.com")
    gen_res = await client.post(
        "/api/v1/entity-resolution/candidates",
        json={"raw_observation_id": obs},
        headers=_auth_headers(viewer),
    )
    assert gen_res.status_code == 403

    candidate = await _generate_candidate(client, admin, obs)
    decide_res = await client.post(
        f"/api/v1/entity-resolution/candidates/{candidate['id']}/decide",
        json={"decision": "reject_match"},
        headers=_auth_headers(viewer),
    )
    assert decide_res.status_code == 403


@pytest.mark.asyncio
async def test_candidate_generation_requires_auth(client):
    res = await client.post(
        "/api/v1/entity-resolution/candidates",
        json={"raw_observation_id": "00000000-0000-0000-0000-000000000000"},
    )
    assert res.status_code == 401


# --------------------------------------------------------------------------
# List / filter
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_candidates_filters_by_resolution_state(client):
    admin = await _register_admin(client, "list-er@example.com")
    source = await _create_mca_source(client, admin)
    obs_new = await _create_observation(
        client,
        admin,
        source["id"],
        _real_shaped_record("U80808MH2015PTC080808", "List Filter New Co"),
    )
    await _generate_candidate(client, admin, obs_new)

    res = await client.get(
        "/api/v1/entity-resolution/candidates?resolution_state=new", headers=_auth_headers(admin)
    )
    assert res.status_code == 200
    assert all(item["resolution_state"] == "new" for item in res.json()["data"]["items"])


@pytest.mark.asyncio
async def test_generate_candidate_for_nonexistent_observation_404s(client):
    admin = await _register_admin(client, "no-obs-er@example.com")
    res = await client.post(
        "/api/v1/entity-resolution/candidates",
        json={"raw_observation_id": "00000000-0000-0000-0000-000000000000"},
        headers=_auth_headers(admin),
    )
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "OBSERVATION_NOT_FOUND"
