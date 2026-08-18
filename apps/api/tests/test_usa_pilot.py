"""
Module 6D tests — USA functional industrial data pilot (SEC EDGAR,
Census CBP, USITC DataWeb, manual entry). Adapter-level unit tests here
are mocked at the httpx boundary — never counted as live validation.
Real live validation (real SEC EDGAR/Census CBP/USITC DataWeb calls,
real credentials) was performed separately during Module 6D's
implementation via ad-hoc validation scripts, not as a committed pytest
file — see the module's completion report for those results. Field-
profile and pilot-orchestration tests below exercise the real database
via the full HTTP pipeline, matching tests/test_mca_pilot.py's own
established convention.
"""

from datetime import UTC, datetime
from unittest.mock import MagicMock

import httpx
import pytest

from app.collectors.census_cbp_adapter import CensusCBPAdapter
from app.collectors.field_profiles import (
    UnknownSourceProfileError,
    resolve_profile_for_content,
)
from app.collectors.manual_entry_adapter import ManualEntryAdapter
from app.collectors.sec_edgar_adapter import SECEdgarAdapter
from app.collectors.usitc_dataweb_adapter import USITCDataWebAdapter
from app.db.session import AsyncSessionLocal
from app.models.source_registry import CollectionMethod, SourceClass
from app.schemas.provenance import RawObservationCreate, SourceRegistryCreate
from app.services import acquisition_service, pilot_service, provenance_service
from tests.test_acquisition import _register_admin
from tests.test_companies import _auth_headers


def _mock_response(json_body, status_code: int = 200) -> MagicMock:
    response = MagicMock(spec=httpx.Response)
    response.status_code = status_code
    response.json.return_value = json_body
    response.text = str(json_body)[:200]
    return response


# --------------------------------------------------------------------------
# SEC EDGAR adapter — unit tests, mocked httpx boundary
# --------------------------------------------------------------------------


def test_sec_validate_config_requires_user_agent_and_sic_code():
    adapter = SECEdgarAdapter()
    with pytest.raises(Exception, match="user_agent"):
        adapter.validate_config({"sic_code": "3559"})
    with pytest.raises(Exception, match="sic_code"):
        adapter.validate_config({"user_agent": "ForgeX test@example.com"})


def test_sec_validate_config_enforces_pilot_size_ceiling():
    adapter = SECEdgarAdapter()
    with pytest.raises(Exception, match="ceiling of 25"):
        adapter.validate_config(
            {"user_agent": "ForgeX test@example.com", "sic_code": "3559", "limit": 100}
        )


def test_sec_discovery_and_detail_fetch_maps_real_field_names(monkeypatch):
    adapter = SECEdgarAdapter()
    discovery_xml = "<feed><entry><content><company-info><cik>0000320193</cik></company-info></content></entry></feed>"
    detail_body = {
        "cik": "320193",
        "name": "Apple Inc.",
        "entityType": "operating",
        "sic": "3571",
        "sicDescription": "Electronic Computers",
        "tickers": ["AAPL"],
        "exchanges": ["Nasdaq"],
        "addresses": {"business": {"city": "Cupertino", "stateOrCountry": "CA"}},
        "formerNames": [{"name": "APPLE COMPUTER INC"}],
    }

    def _fake_get(url, params=None, headers=None, timeout=None):
        if "browse-edgar" in url:
            resp = MagicMock(spec=httpx.Response)
            resp.status_code = 200
            resp.text = discovery_xml
            return resp
        return _mock_response(detail_body)

    monkeypatch.setattr("app.collectors.sec_edgar_adapter.httpx.get", _fake_get)
    monkeypatch.setattr("app.collectors.sec_edgar_adapter.time.sleep", lambda *_: None)

    items = adapter.collect(
        {"user_agent": "ForgeX test@example.com", "sic_code": "3559", "limit": 5}
    )
    assert len(items) == 1
    assert items[0].external_identifier == "0000320193"
    assert items[0].raw_content["name"] == "Apple Inc."
    assert items[0].raw_content["sic_description"] == "Electronic Computers"
    assert items[0].raw_content["business_address_city"] == "Cupertino"
    assert items[0].raw_content["business_address_state"] == "CA"
    assert items[0].raw_content["cik"] == "0000320193"


def test_sec_missing_user_agent_is_non_retryable(monkeypatch):
    from app.collectors.base import NonRetryableCollectorError

    adapter = SECEdgarAdapter()
    monkeypatch.setattr(
        "app.collectors.sec_edgar_adapter.httpx.get", lambda *a, **k: _mock_response({}, 403)
    )
    with pytest.raises(NonRetryableCollectorError):
        adapter.collect({"user_agent": "ForgeX test@example.com", "sic_code": "3559"})


def test_sec_one_bad_detail_fetch_does_not_abort_the_whole_batch(monkeypatch):
    adapter = SECEdgarAdapter()
    discovery_xml = (
        "<feed><entry><content><company-info><cik>1</cik></company-info></content></entry>"
        "<entry><content><company-info><cik>2</cik></company-info></content></entry></feed>"
    )
    calls = {"n": 0}

    def _fake_get(url, params=None, headers=None, timeout=None):
        if "browse-edgar" in url:
            resp = MagicMock(spec=httpx.Response)
            resp.status_code = 200
            resp.text = discovery_xml
            return resp
        calls["n"] += 1
        if calls["n"] == 1:
            return _mock_response({}, 500)
        return _mock_response({"cik": "2", "name": "Second Co", "sicDescription": "Test"})

    monkeypatch.setattr("app.collectors.sec_edgar_adapter.httpx.get", _fake_get)
    monkeypatch.setattr("app.collectors.sec_edgar_adapter.time.sleep", lambda *_: None)

    items = adapter.collect({"user_agent": "ForgeX test@example.com", "sic_code": "3559"})
    assert len(items) == 1
    assert items[0].raw_content["name"] == "Second Co"


# --------------------------------------------------------------------------
# Census CBP adapter — unit tests, mocked httpx boundary
# --------------------------------------------------------------------------


def test_census_validate_config_requires_fields():
    adapter = CensusCBPAdapter()
    with pytest.raises(Exception, match="api_key"):
        adapter.validate_config({"year": "2023", "queries": [{"state_fips": "06", "naics": "333"}]})
    with pytest.raises(Exception, match="queries"):
        adapter.validate_config({"api_key": "x", "year": "2023"})


def test_census_validate_config_enforces_pilot_size_ceiling():
    adapter = CensusCBPAdapter()
    with pytest.raises(Exception, match="ceiling of 10"):
        adapter.validate_config(
            {
                "api_key": "x",
                "year": "2023",
                "queries": [{"state_fips": "06", "naics": str(n)} for n in range(11)],
            }
        )


def test_census_collect_produces_aggregate_never_company_shaped_output(monkeypatch):
    adapter = CensusCBPAdapter()
    rows = [
        [
            "ESTAB",
            "EMP",
            "PAYANN",
            "PAYQTR1",
            "LFO",
            "NAICS2017",
            "NAICS2017_LABEL",
            "NAME",
            "state",
        ],
        [
            "2094",
            "68874",
            "7296051",
            "1700000",
            "00",
            "333",
            "Machinery Manufacturing",
            "California",
            "06",
        ],
    ]
    monkeypatch.setattr(
        "app.collectors.census_cbp_adapter.httpx.get", lambda *a, **k: _mock_response(rows)
    )
    items = adapter.collect(
        {"api_key": "x", "year": "2023", "queries": [{"state_fips": "06", "naics": "333"}]}
    )
    assert len(items) == 1
    content = items[0].raw_content
    assert content["establishments"] == "2094"
    assert content["naics2017_label"] == "Machinery Manufacturing"
    # Absolute rule (Module 6D Section 25): never a company name or
    # entity identifier field anywhere in the output.
    assert "company_name" not in content
    assert "name" not in content
    assert items[0].external_identifier == "cbp:2023:state:06:naics:333"


def test_census_disclosure_suppressed_zero_rows_is_a_real_none_not_an_error(monkeypatch):
    """Header row only, no data row — a real, valid Census outcome
    (Section 9's disclosure-avoidance rule), not a failure."""
    adapter = CensusCBPAdapter()
    monkeypatch.setattr(
        "app.collectors.census_cbp_adapter.httpx.get",
        lambda *a, **k: _mock_response([["ESTAB", "NAICS2017"]]),
    )
    items = adapter.collect(
        {"api_key": "x", "year": "2023", "queries": [{"state_fips": "99", "naics": "999"}]}
    )
    assert items == []


def test_census_bad_api_key_is_non_retryable(monkeypatch):
    from app.collectors.base import NonRetryableCollectorError

    adapter = CensusCBPAdapter()
    monkeypatch.setattr(
        "app.collectors.census_cbp_adapter.httpx.get", lambda *a, **k: _mock_response({}, 403)
    )
    with pytest.raises(NonRetryableCollectorError):
        adapter.collect(
            {"api_key": "bad", "year": "2023", "queries": [{"state_fips": "06", "naics": "333"}]}
        )


# --------------------------------------------------------------------------
# USITC DataWeb adapter — unit tests, mocked httpx boundary
# --------------------------------------------------------------------------


def test_usitc_validate_config_requires_token_and_saved_query_name():
    adapter = USITCDataWebAdapter()
    with pytest.raises(Exception, match="token"):
        adapter.validate_config({"saved_query_name": "x"})
    with pytest.raises(Exception, match="saved_query_name"):
        adapter.validate_config({"token": "x"})


def test_usitc_no_saved_query_found_is_a_real_honest_non_retryable_failure(monkeypatch):
    """Reproduces this module's own real, live-confirmed account state
    (zero saved queries) — must never be silently treated as success."""
    from app.collectors.base import NonRetryableCollectorError

    adapter = USITCDataWebAdapter()
    monkeypatch.setattr(
        "app.collectors.usitc_dataweb_adapter.httpx.get",
        lambda *a, **k: _mock_response({"list": []}),
    )
    with pytest.raises(NonRetryableCollectorError, match="No saved query named"):
        adapter.collect({"token": "x", "saved_query_name": "MachineryImports"})


def test_usitc_runs_report_from_the_matched_saved_query_object(monkeypatch):
    saved_query = {"savedQueryName": "MachineryImports", "savedQueryId": 42, "some": "definition"}
    report = {
        "dto": {
            "tables": [
                {
                    "column_groups": [{"label": "Country"}, {"label": "Value"}],
                    "row_groups": [
                        {"rowsNew": [{"rowEntries": [{"value": "Germany"}, {"value": "1000000"}]}]}
                    ],
                }
            ]
        }
    }
    captured_body = {}

    def _fake_get(url, headers=None, timeout=None):
        return _mock_response({"list": [saved_query]})

    def _fake_post(url, headers=None, json=None, timeout=None):
        captured_body.update(json)
        return _mock_response(report)

    monkeypatch.setattr("app.collectors.usitc_dataweb_adapter.httpx.get", _fake_get)
    monkeypatch.setattr("app.collectors.usitc_dataweb_adapter.httpx.post", _fake_post)

    adapter = USITCDataWebAdapter()
    items = adapter.collect({"token": "x", "saved_query_name": "MachineryImports"})

    # The ENTIRE matched saved-query object is sent as the runReport
    # body, unmodified — per the real, official API guide's own
    # example code (this adapter's own module docstring).
    assert captured_body == saved_query
    assert len(items) == 1
    assert items[0].raw_content["col:Country"] == "Germany"
    assert items[0].raw_content["col:Value"] == "1000000"
    assert "company_name" not in items[0].raw_content


# --------------------------------------------------------------------------
# Manual entry adapter — unit tests, no network
# --------------------------------------------------------------------------


def test_manual_validate_config_requires_company_name_and_entered_by():
    adapter = ManualEntryAdapter()
    with pytest.raises(Exception, match="company_name"):
        adapter.validate_config({"entered_by": "user-1"})
    with pytest.raises(Exception, match="entered_by"):
        adapter.validate_config({"company_name": "ABC Manufacturing"})


def test_manual_collect_preserves_submission_metadata():
    adapter = ManualEntryAdapter()
    items = adapter.collect(
        {
            "company_name": "ABC Manufacturing Inc.",
            "entered_by": "user-123",
            "evidence_url": "https://abc-manufacturing.example.com",
            "notes": "Found via trade show directory",
            "industry": "Machinery Manufacturing",
            "state": "Ohio",
        }
    )
    assert len(items) == 1
    assert items[0].raw_content["entered_by"] == "user-123"
    assert items[0].raw_content["evidence_url"] == "https://abc-manufacturing.example.com"
    assert items[0].external_identifier == "https://abc-manufacturing.example.com"


def test_manual_entry_resubmission_without_evidence_relies_on_content_hash():
    adapter = ManualEntryAdapter()
    items = adapter.collect({"company_name": "No Evidence Co", "entered_by": "user-1"})
    assert items[0].external_identifier is None


# --------------------------------------------------------------------------
# Field profile resolution — lineage-first, narrow legacy shim, fails closed
# --------------------------------------------------------------------------


async def _create_operator(db, email: str):
    from app.core.security import hash_password
    from app.models.user import Role, User

    user = User(
        email=email,
        hashed_password=hash_password("irrelevant"),
        full_name="Test Operator",
        role=Role.ADMIN,
        is_email_verified=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@pytest.mark.asyncio
async def test_profile_resolution_is_lineage_first_for_sec_edgar():
    async with AsyncSessionLocal() as db:
        operator = await _create_operator(db, "profile-lineage@forgex.internal")
        source = await provenance_service.create_source(
            db,
            SourceRegistryCreate(
                name="SEC Lineage Test",
                source_class=SourceClass.PUBLIC_GOVERNMENT,
                collection_method=CollectionMethod.API,
            ),
        )
        from app.schemas.acquisition import AcquisitionJobCreate

        job = await acquisition_service.create_and_run_job(
            db,
            AcquisitionJobCreate(source_id=source.id, collector_type="mock", requested_scope={}),
            created_by=operator.id,
        )
        events, _ = await acquisition_service.list_job_events(db, job.id, page=1, page_size=10)
        observation_id = next(e.raw_observation_id for e in events if e.raw_observation_id)
        observation = await provenance_service.get_raw_observation(db, observation_id)
        assert observation is not None

        profile = await resolve_profile_for_content(db, observation_id, observation.raw_content)
        # Real lineage (a real AcquisitionJob with collector_type="mock")
        # is authoritative — resolves to the registered mock profile,
        # never guessed from content shape.
        assert profile.collector_type == "mock"


@pytest.mark.asyncio
async def test_profile_resolution_legacy_shim_only_for_mca_shaped_lineage_less_content():
    async with AsyncSessionLocal() as db:
        source = await provenance_service.create_source(
            db,
            SourceRegistryCreate(
                name="Legacy Shim Test Source",
                source_class=SourceClass.PUBLIC_GOVERNMENT,
                collection_method=CollectionMethod.API,
            ),
        )
        # Constructed directly — no AcquisitionJob, no lineage. Matches
        # tests/test_pilot.py's own established pattern exactly.
        observation = await provenance_service.create_raw_observation(
            db,
            RawObservationCreate(
                source_id=source.id,
                external_reference="legacy-cin-1",
                raw_content={"cin": "U1", "company_name": "Legacy Co", "registered_state": "MH"},
                content_hash="legacy-hash-1",
                collection_method_used=CollectionMethod.API,
                collected_at=datetime.now(UTC),
            ),
        )
        profile = await resolve_profile_for_content(db, observation.id, observation.raw_content)
        assert profile.collector_type == "mca_data_gov_in"


@pytest.mark.asyncio
async def test_profile_resolution_fails_closed_for_unrecognized_lineage_less_content():
    async with AsyncSessionLocal() as db:
        source = await provenance_service.create_source(
            db,
            SourceRegistryCreate(
                name="Unknown Shape Source",
                source_class=SourceClass.PUBLIC_GOVERNMENT,
                collection_method=CollectionMethod.API,
            ),
        )
        observation = await provenance_service.create_raw_observation(
            db,
            RawObservationCreate(
                source_id=source.id,
                external_reference="cbp:2023:state:06:naics:333",
                raw_content={"establishments": "2094", "naics2017": "333"},
                content_hash="unknown-hash-1",
                collection_method_used=CollectionMethod.API,
                collected_at=datetime.now(UTC),
            ),
        )
        with pytest.raises(UnknownSourceProfileError):
            await resolve_profile_for_content(db, observation.id, observation.raw_content)


# --------------------------------------------------------------------------
# Pilot orchestration boundary — Census/USITC never enter entity resolution
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_census_job_never_triggers_entity_resolution(monkeypatch):
    monkeypatch.setattr(
        "app.collectors.census_cbp_adapter.httpx.get",
        lambda *a, **k: _mock_response(
            [
                ["ESTAB", "NAICS2017", "NAICS2017_LABEL", "NAME"],
                ["10", "333", "Machinery Manufacturing", "California"],
            ]
        ),
    )
    async with AsyncSessionLocal() as db:
        operator = await _create_operator(db, "census-pilot@forgex.internal")

        report = await pilot_service.run_pilot(
            db,
            source_payload=SourceRegistryCreate(
                name="Census CBP Pilot Test",
                source_class=SourceClass.PUBLIC_GOVERNMENT,
                collection_method=CollectionMethod.API,
                geographic_scope="US",
            ),
            collector_type="census_cbp",
            requested_scope={
                "api_key": "x",
                "year": "2023",
                "queries": [{"state_fips": "06", "naics": "333"}],
            },
            created_by=operator.id,
            dry_run=True,
        )
        assert report.records_discovered_or_created == 1
        # THE assertion this test exists for: entity resolution never
        # ran for this collector_type at all (Section 36) — not "ran
        # and found nothing," genuinely never invoked.
        assert report.entity_resolution.total == 0


# --------------------------------------------------------------------------
# Manual entry, end to end, through the REAL existing HTTP API — no new
# endpoint was added for this (see docs/adr/0043 and
# app.collectors.manual_entry_adapter's own docstring): the existing
# Module 5B POST /acquisition/jobs route, unmodified, IS the manual-entry
# submission path once collector_type="manual_entry" is registered.
# --------------------------------------------------------------------------


async def _create_manual_source(client, admin) -> dict:
    res = await client.post(
        "/api/v1/sources",
        json={
            "name": "Manual Entry (ForgeX users)",
            "source_class": "user_contribution",
            "collection_method": "manual",
            "reliability_weight": 0.3,
        },
        headers=_auth_headers(admin),
    )
    assert res.status_code == 201, res.text
    return res.json()["data"]


@pytest.mark.asyncio
async def test_manual_entry_end_to_end_through_existing_acquisition_endpoint(client):
    admin = await _register_admin(client, "manual-entry-e2e@example.com")
    source = await _create_manual_source(client, admin)

    res = await client.post(
        "/api/v1/acquisition/jobs",
        json={
            "source_id": source["id"],
            "collector_type": "manual_entry",
            "requested_scope": {
                "company_name": "ABC Manufacturing Inc.",
                "entered_by": admin["user"]["id"],
                "evidence_url": "https://abc-manufacturing.example.com",
                "industry": "Machinery Manufacturing",
                "state": "Ohio",
                "country": "United States",
            },
        },
        headers=_auth_headers(admin),
    )
    assert res.status_code == 201, res.text
    job = res.json()["data"]
    assert job["status"] == "succeeded"
    assert job["result_count"] == 1

    events = (
        await client.get(
            f"/api/v1/acquisition/jobs/{job['id']}/events", headers=_auth_headers(admin)
        )
    ).json()["data"]["items"]
    assert events[0]["outcome"] == "created"

    obs_res = await client.get(
        f"/api/v1/acquisition/observations/{events[0]['raw_observation_id']}",
        headers=_auth_headers(admin),
    )
    assert obs_res.status_code == 200
    # entered_by/evidence_url are preserved on the raw observation for
    # audit purposes — Module 6D Section 11.
    assert obs_res.json()["data"]["raw_content"]["entered_by"] == admin["user"]["id"]
    assert (
        obs_res.json()["data"]["raw_content"]["evidence_url"]
        == "https://abc-manufacturing.example.com"
    )

    # Promotion (human review) reuses the existing Module 5C endpoint,
    # unmodified — never auto-verified.
    promote_res = await client.post(
        f"/api/v1/acquisition/observations/{events[0]['raw_observation_id']}/promote",
        headers=_auth_headers(admin),
    )
    assert promote_res.status_code == 201, promote_res.text
    company = promote_res.json()["data"]
    assert company["name"] == "ABC Manufacturing Inc."
    assert company["verification_status"] == "unverified"
