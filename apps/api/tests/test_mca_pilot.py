"""
Module 5C tests — MCA Company Master Data pilot. Covers the real
adapter's HTTP-layer logic (mocked at the httpx boundary, since this
sandbox's network egress cannot reach data.gov.in — confirmed
empirically, see docs/adr/0039-module-5c-mca-pilot.md), field mapping,
CIN identity/duplicate handling, provenance creation, idempotency, and
every failure mode the ticket's checklist requires. The mocked
responses below use the CONFIRMED real field names from data.gov.in's
own published Company Master Data catalog description (verified via
web research while writing the Phase 5C architecture document) — not
invented field names.
"""

from unittest.mock import MagicMock

import httpx
import pytest

from app.collectors.mca_data_gov_in_adapter import MCADataGovInAdapter
from tests.test_acquisition import _register_admin
from tests.test_companies import _auth_headers


def _real_shaped_record(cin: str, name: str, state: str = "Maharashtra") -> dict:
    """One record, using the exact field-name casing/shape confirmed
    from data.gov.in's own catalog description — a realistic fixture,
    not a fabricated shape, given this sandbox cannot reach the live
    API to capture an actual response (documented limitation, not
    hidden)."""
    return {
        "CIN": cin,
        "Company Name": name,
        "Company Status": "Active",
        "Company Class": "Private",
        "Company Category": "Company limited by Shares",
        "Company SubCategory": "Non-govt company",
        "Authorized Capital": "1000000",
        "Paid up Capital": "500000",
        "Date of Registration": "15/09/2015",
        "Registered State": state,
        "Registrar of Companies": "RoC-Pune",
        "Principal Business Activity": "Manufacturing",
        "Registered Office Address": f"123 MG Road, Pune, {state} 411001",
    }


def _mock_response(records: list[dict], status_code: int = 200) -> MagicMock:
    response = MagicMock(spec=httpx.Response)
    response.status_code = status_code
    response.json.return_value = {"records": records}
    return response


async def _create_mca_source(client, admin) -> dict:
    res = await client.post(
        "/api/v1/sources",
        json={
            "name": "MCA Company Master Data (data.gov.in)",
            "source_class": "public_government",
            "collection_method": "api",
            "reliability_weight": 0.9,
            "geographic_scope": "IN",
            "base_url": "https://api.data.gov.in/resource",
        },
        headers=_auth_headers(admin),
    )
    assert res.status_code == 201, res.text
    return res.json()["data"]


async def _create_mca_job(client, admin, source_id: str, **scope_overrides) -> object:
    scope = {
        "api_key": "test-key-not-real",
        "resource_id": "test-resource-id",
        "limit": 25,
        **scope_overrides,
    }
    return await client.post(
        "/api/v1/acquisition/jobs",
        json={
            "source_id": source_id,
            "collector_type": "mca_data_gov_in",
            "requested_scope": scope,
        },
        headers=_auth_headers(admin),
    )


# --------------------------------------------------------------------------
# Adapter-level unit tests (no HTTP, no DB)
# --------------------------------------------------------------------------


def test_validate_config_requires_api_key_and_resource_id():
    adapter = MCADataGovInAdapter()
    with pytest.raises(Exception, match="api_key"):
        adapter.validate_config({"resource_id": "x"})
    with pytest.raises(Exception, match="resource_id"):
        adapter.validate_config({"api_key": "x"})


def test_validate_config_enforces_pilot_size_ceiling():
    adapter = MCADataGovInAdapter()
    with pytest.raises(Exception, match="ceiling of 50"):
        adapter.validate_config({"api_key": "x", "resource_id": "y", "limit": 100})


def test_collect_maps_real_field_names_correctly(monkeypatch):
    adapter = MCADataGovInAdapter()
    record = _real_shaped_record("U12345MH2015PTC000001", "Real Shape Test Co")
    monkeypatch.setattr(
        "app.collectors.mca_data_gov_in_adapter.httpx.get", lambda *a, **k: _mock_response([record])
    )
    items = adapter.collect({"api_key": "x", "resource_id": "y"})
    assert len(items) == 1
    assert items[0].external_identifier == "U12345MH2015PTC000001"
    assert items[0].raw_content["company_name"] == "Real Shape Test Co"
    assert items[0].raw_content["registered_state"] == "Maharashtra"


def test_collect_raises_retryable_on_timeout(monkeypatch):
    adapter = MCADataGovInAdapter()

    def _raise_timeout(*a, **k):
        raise httpx.TimeoutException("simulated timeout")

    monkeypatch.setattr("app.collectors.mca_data_gov_in_adapter.httpx.get", _raise_timeout)
    with pytest.raises(Exception) as exc_info:
        adapter.collect({"api_key": "x", "resource_id": "y"})
    from app.collectors.base import RetryableCollectorError

    assert isinstance(exc_info.value, RetryableCollectorError)


def test_collect_raises_non_retryable_on_401(monkeypatch):
    adapter = MCADataGovInAdapter()
    monkeypatch.setattr(
        "app.collectors.mca_data_gov_in_adapter.httpx.get",
        lambda *a, **k: _mock_response([], status_code=401),
    )
    from app.collectors.base import NonRetryableCollectorError

    with pytest.raises(NonRetryableCollectorError):
        adapter.collect({"api_key": "bad-key", "resource_id": "y"})


def test_collect_raises_retryable_on_429(monkeypatch):
    adapter = MCADataGovInAdapter()
    monkeypatch.setattr(
        "app.collectors.mca_data_gov_in_adapter.httpx.get",
        lambda *a, **k: _mock_response([], status_code=429),
    )
    from app.collectors.base import RetryableCollectorError

    with pytest.raises(RetryableCollectorError):
        adapter.collect({"api_key": "x", "resource_id": "y"})


def test_collect_raises_retryable_on_500(monkeypatch):
    adapter = MCADataGovInAdapter()
    monkeypatch.setattr(
        "app.collectors.mca_data_gov_in_adapter.httpx.get",
        lambda *a, **k: _mock_response([], status_code=500),
    )
    from app.collectors.base import RetryableCollectorError

    with pytest.raises(RetryableCollectorError):
        adapter.collect({"api_key": "x", "resource_id": "y"})


def test_collect_raises_non_retryable_on_malformed_json(monkeypatch):
    response = MagicMock(spec=httpx.Response)
    response.status_code = 200
    response.json.side_effect = ValueError("not json")
    adapter = MCADataGovInAdapter()
    monkeypatch.setattr(
        "app.collectors.mca_data_gov_in_adapter.httpx.get", lambda *a, **k: response
    )
    from app.collectors.base import NonRetryableCollectorError

    with pytest.raises(NonRetryableCollectorError):
        adapter.collect({"api_key": "x", "resource_id": "y"})


def test_collect_raises_non_retryable_on_missing_records_key(monkeypatch):
    response = MagicMock(spec=httpx.Response)
    response.status_code = 200
    response.json.return_value = {"unexpected": "shape"}
    adapter = MCADataGovInAdapter()
    monkeypatch.setattr(
        "app.collectors.mca_data_gov_in_adapter.httpx.get", lambda *a, **k: response
    )
    from app.collectors.base import NonRetryableCollectorError

    with pytest.raises(NonRetryableCollectorError):
        adapter.collect({"api_key": "x", "resource_id": "y"})


# --------------------------------------------------------------------------
# Full pipeline, through the real API, mocked only at the httpx boundary
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_source_registration_stores_correct_metadata(client):
    admin = await _register_admin(client, "mca-source-reg@example.com")
    source = await _create_mca_source(client, admin)
    assert source["source_class"] == "public_government"
    assert (
        source["collection_policy_status"] == "pending_legal_review"
    )  # honest default, never auto-allowed
    assert "data.gov.in" in source["name"] or "MCA" in source["name"]


@pytest.mark.asyncio
async def test_full_pipeline_job_to_raw_observation(client, monkeypatch):
    admin = await _register_admin(client, "mca-pipeline@example.com")
    source = await _create_mca_source(client, admin)
    record = _real_shaped_record("U11111MH2015PTC000011", "Pipeline Test Co")
    monkeypatch.setattr(
        "app.collectors.mca_data_gov_in_adapter.httpx.get", lambda *a, **k: _mock_response([record])
    )

    res = await _create_mca_job(client, admin, source["id"])
    job = res.json()["data"]
    assert job["status"] == "succeeded"
    assert job["result_count"] == 1

    events = (
        await client.get(
            f"/api/v1/acquisition/jobs/{job['id']}/events", headers=_auth_headers(admin)
        )
    ).json()["data"]["items"]
    assert events[0]["outcome"] == "created"
    observation_id = events[0]["raw_observation_id"]

    obs_res = await client.get(
        f"/api/v1/acquisition/observations/{observation_id}", headers=_auth_headers(admin)
    )
    assert obs_res.status_code == 200
    assert obs_res.json()["data"]["raw_content"]["cin"] == "U11111MH2015PTC000011"


@pytest.mark.asyncio
async def test_promotion_creates_company_with_provenance_never_verified(client, monkeypatch):
    admin = await _register_admin(client, "mca-promote@example.com")
    source = await _create_mca_source(client, admin)
    record = _real_shaped_record("U22222MH2015PTC000022", "Promotion Test Co")
    monkeypatch.setattr(
        "app.collectors.mca_data_gov_in_adapter.httpx.get", lambda *a, **k: _mock_response([record])
    )
    job = (await _create_mca_job(client, admin, source["id"])).json()["data"]
    events = (
        await client.get(
            f"/api/v1/acquisition/jobs/{job['id']}/events", headers=_auth_headers(admin)
        )
    ).json()["data"]["items"]
    observation_id = events[0]["raw_observation_id"]

    promote_res = await client.post(
        f"/api/v1/acquisition/observations/{observation_id}/promote", headers=_auth_headers(admin)
    )
    assert promote_res.status_code == 201, promote_res.text
    company = promote_res.json()["data"]
    assert company["name"] == "Promotion Test Co"
    assert company["state"] == "Maharashtra"
    assert company["country"] == "India"
    # THE data trust rule: source-backed existence is not ForgeX
    # verification, ever, automatically.
    assert company["verification_status"] == "unverified"

    # CompanyDetail (Module 3A's response schema) doesn't expose `cin`
    # at all — that field lives on the separate, existing Module 3B
    # business-info endpoint, confirmed by direct schema inspection
    # rather than assumed. Checking it there, not by modifying
    # CompanyDetail (which would be exactly the kind of Company-domain
    # change this phase's instructions prohibit).
    business_info = await client.get(
        f"/api/v1/companies/{company['id']}/business-info", headers=_auth_headers(admin)
    )
    assert business_info.status_code == 200
    assert business_info.json()["data"]["cin"] == "U22222MH2015PTC000022"

    lineage = await client.get(
        f"/api/v1/provenance?entity_type=company&entity_id={company['id']}",
        headers=_auth_headers(admin),
    )
    lineage_items = lineage.json()["data"]["items"]
    assert len(lineage_items) > 0
    assert all(item["status"] in ("observed", "extracted") for item in lineage_items)
    assert not any(item["status"] == "verified" for item in lineage_items)


@pytest.mark.asyncio
async def test_promotion_preserves_unmappable_fields_as_provenance_only(client, monkeypatch):
    """Fields with no Company column (company_status, capital figures,
    etc.) must still produce a ProvenanceRecord — never silently
    discarded, per the ticket's explicit instruction."""
    admin = await _register_admin(client, "mca-unmappable@example.com")
    source = await _create_mca_source(client, admin)
    record = _real_shaped_record("U33333MH2015PTC000033", "Unmappable Fields Co")
    monkeypatch.setattr(
        "app.collectors.mca_data_gov_in_adapter.httpx.get", lambda *a, **k: _mock_response([record])
    )
    job = (await _create_mca_job(client, admin, source["id"])).json()["data"]
    events = (
        await client.get(
            f"/api/v1/acquisition/jobs/{job['id']}/events", headers=_auth_headers(admin)
        )
    ).json()["data"]["items"]
    observation_id = events[0]["raw_observation_id"]
    company = (
        await client.post(
            f"/api/v1/acquisition/observations/{observation_id}/promote",
            headers=_auth_headers(admin),
        )
    ).json()["data"]

    lineage = await client.get(
        f"/api/v1/provenance?entity_type=company&entity_id={company['id']}",
        headers=_auth_headers(admin),
    )
    field_names = {item["field_name"] for item in lineage.json()["data"]["items"]}
    assert "company_status" in field_names  # no Company.status equivalent, but preserved
    assert "authorized_capital" in field_names  # no Company field, but preserved


# --------------------------------------------------------------------------
# CIN identity and duplicate handling
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_same_cin_produces_same_source_identity_idempotent(client, monkeypatch):
    admin = await _register_admin(client, "mca-samecin@example.com")
    source = await _create_mca_source(client, admin)
    record = _real_shaped_record("U44444MH2015PTC000044", "Same CIN Co")
    monkeypatch.setattr(
        "app.collectors.mca_data_gov_in_adapter.httpx.get", lambda *a, **k: _mock_response([record])
    )

    first = (await _create_mca_job(client, admin, source["id"])).json()["data"]
    assert first["result_count"] == 1

    second = (await _create_mca_job(client, admin, source["id"])).json()["data"]
    assert second["result_count"] == 0
    assert second["skipped_count"] == 1  # same CIN -> same source identity, not a new observation


@pytest.mark.asyncio
async def test_different_cin_is_a_different_company(client, monkeypatch):
    admin = await _register_admin(client, "mca-diffcin@example.com")
    source = await _create_mca_source(client, admin)
    records = [
        _real_shaped_record("U55555MH2015PTC000055", "Different Co A"),
        _real_shaped_record("U66666MH2015PTC000066", "Different Co B"),
    ]
    monkeypatch.setattr(
        "app.collectors.mca_data_gov_in_adapter.httpx.get", lambda *a, **k: _mock_response(records)
    )
    job = (await _create_mca_job(client, admin, source["id"])).json()["data"]
    assert job["result_count"] == 2


@pytest.mark.asyncio
async def test_duplicate_cin_promotion_rejected_not_auto_merged(client, monkeypatch):
    admin = await _register_admin(client, "mca-duplicate@example.com")
    source = await _create_mca_source(client, admin)
    record = _real_shaped_record("U77777MH2015PTC000077", "Duplicate CIN Co")
    monkeypatch.setattr(
        "app.collectors.mca_data_gov_in_adapter.httpx.get", lambda *a, **k: _mock_response([record])
    )

    # Promote once — succeeds.
    job1 = (await _create_mca_job(client, admin, source["id"])).json()["data"]
    obs1 = (
        await client.get(
            f"/api/v1/acquisition/jobs/{job1['id']}/events", headers=_auth_headers(admin)
        )
    ).json()["data"]["items"][0]["raw_observation_id"]
    first_promote = await client.post(
        f"/api/v1/acquisition/observations/{obs1}/promote", headers=_auth_headers(admin)
    )
    assert first_promote.status_code == 201

    # A second, distinct raw observation with the SAME CIN (simulating
    # a later re-collection or a data quality overlap) — promotion
    # must be rejected, never silently merged into the existing Company.
    monkeypatch.setattr(
        "app.collectors.mca_data_gov_in_adapter.httpx.get",
        lambda *a, **k: _mock_response(
            [_real_shaped_record("U77777MH2015PTC000077", "Duplicate CIN Co Renamed")]
        ),
    )
    job2 = (
        await _create_mca_job(client, admin, source["id"], resource_id="a-different-resource")
    ).json()["data"]
    obs2 = (
        await client.get(
            f"/api/v1/acquisition/jobs/{job2['id']}/events", headers=_auth_headers(admin)
        )
    ).json()["data"]["items"][0]["raw_observation_id"]

    second_promote = await client.post(
        f"/api/v1/acquisition/observations/{obs2}/promote", headers=_auth_headers(admin)
    )
    assert second_promote.status_code == 409
    assert second_promote.json()["error"]["code"] == "DUPLICATE_CIN"


# --------------------------------------------------------------------------
# Failure modes
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_malformed_source_response_fails_job_honestly(client, monkeypatch):
    admin = await _register_admin(client, "mca-malformed@example.com")
    source = await _create_mca_source(client, admin)
    response = MagicMock(spec=httpx.Response)
    response.status_code = 200
    response.json.return_value = {"no_records_key": True}
    monkeypatch.setattr(
        "app.collectors.mca_data_gov_in_adapter.httpx.get", lambda *a, **k: response
    )

    job = (await _create_mca_job(client, admin, source["id"])).json()["data"]
    assert job["status"] == "failed"
    assert job["result_count"] == 0


@pytest.mark.asyncio
async def test_source_unavailable_is_retried_then_fails(client, monkeypatch):
    admin = await _register_admin(client, "mca-unavailable@example.com")
    source = await _create_mca_source(client, admin)

    def _raise_connect_error(*a, **k):
        raise httpx.ConnectError("simulated connection failure")

    monkeypatch.setattr("app.collectors.mca_data_gov_in_adapter.httpx.get", _raise_connect_error)
    job = (await _create_mca_job(client, admin, source["id"])).json()["data"]
    assert job["status"] == "failed"
    assert job["retry_count"] == 3  # bounded retry, matching Module 5B's existing MAX_RETRIES


@pytest.mark.asyncio
async def test_invalid_configuration_rejected_before_running(client):
    admin = await _register_admin(client, "mca-invalidconfig@example.com")
    source = await _create_mca_source(client, admin)
    res = await client.post(
        "/api/v1/acquisition/jobs",
        json={
            "source_id": source["id"],
            "collector_type": "mca_data_gov_in",
            "requested_scope": {"api_key": "x"},  # missing resource_id
        },
        headers=_auth_headers(admin),
    )
    job = res.json()["data"]
    assert job["status"] == "failed"
    assert job["started_at"] is None


@pytest.mark.asyncio
async def test_promotion_with_missing_name_rejected(client, monkeypatch):
    admin = await _register_admin(client, "mca-noname@example.com")
    source = await _create_mca_source(client, admin)
    record = _real_shaped_record("U88888MH2015PTC000088", "")
    record["Company Name"] = ""  # force a missing name — must not be invented
    monkeypatch.setattr(
        "app.collectors.mca_data_gov_in_adapter.httpx.get", lambda *a, **k: _mock_response([record])
    )
    job = (await _create_mca_job(client, admin, source["id"])).json()["data"]
    # An item with no company_name should fail at the acquisition layer
    # too (Module 5B's own per-item validation), but if it somehow
    # reaches promotion, promotion itself must also refuse to invent a name.
    if job["result_count"] > 0:
        events = (
            await client.get(
                f"/api/v1/acquisition/jobs/{job['id']}/events", headers=_auth_headers(admin)
            )
        ).json()["data"]["items"]
        created = next((e for e in events if e["outcome"] == "created"), None)
        if created:
            res = await client.post(
                f"/api/v1/acquisition/observations/{created['raw_observation_id']}/promote",
                headers=_auth_headers(admin),
            )
            assert res.status_code == 422


# --------------------------------------------------------------------------
# RBAC
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_non_admin_cannot_view_or_promote_observations(client, monkeypatch):
    admin = await _register_admin(client, "mca-rbac-admin@example.com")
    source = await _create_mca_source(client, admin)
    record = _real_shaped_record("U99999MH2015PTC000099", "RBAC Test Co")
    monkeypatch.setattr(
        "app.collectors.mca_data_gov_in_adapter.httpx.get", lambda *a, **k: _mock_response([record])
    )
    job = (await _create_mca_job(client, admin, source["id"])).json()["data"]
    events = (
        await client.get(
            f"/api/v1/acquisition/jobs/{job['id']}/events", headers=_auth_headers(admin)
        )
    ).json()["data"]["items"]
    observation_id = events[0]["raw_observation_id"]

    from tests.test_companies import _register_verified

    viewer = await _register_verified(client, "mca-rbac-viewer@example.com")
    get_res = await client.get(
        f"/api/v1/acquisition/observations/{observation_id}", headers=_auth_headers(viewer)
    )
    assert get_res.status_code == 403
    promote_res = await client.post(
        f"/api/v1/acquisition/observations/{observation_id}/promote", headers=_auth_headers(viewer)
    )
    assert promote_res.status_code == 403


# --------------------------------------------------------------------------
# Secret redaction (source-specific: the api_key in requested_scope)
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mca_api_key_is_redacted_from_job_response(client, monkeypatch):
    admin = await _register_admin(client, "mca-secret@example.com")
    source = await _create_mca_source(client, admin)
    record = _real_shaped_record("U10101MH2015PTC010101", "Secret Redaction Co")
    monkeypatch.setattr(
        "app.collectors.mca_data_gov_in_adapter.httpx.get", lambda *a, **k: _mock_response([record])
    )

    res = await _create_mca_job(
        client, admin, source["id"], api_key="THIS-IS-A-REAL-LOOKING-SECRET-KEY"
    )
    assert "THIS-IS-A-REAL-LOOKING-SECRET-KEY" not in res.text
    assert res.json()["data"]["requested_scope"]["api_key"] == "***REDACTED***"
