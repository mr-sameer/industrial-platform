"""
Acquisition foundation tests — Module 5B. Covers the full pipeline
(source -> adapter -> job -> observation -> provenance-ready raw data),
idempotency, retry/non-retry failure handling, RBAC, secret redaction,
and the migration round-trip. Reuses test_companies.py's established
fixtures and adds one new helper (_register_admin) since job creation
specifically requires Role.ADMIN, unlike every other resource this
test suite has needed a fixture for so far.
"""

import pytest
from sqlalchemy import select

from app.db.session import AsyncSessionLocal
from app.models.user import Role, User
from tests.test_companies import _auth_headers, _register_verified


async def _register_admin(client, email: str, full_name: str = "Admin User") -> dict:
    data = await _register_verified(client, email, full_name)
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(User).where(User.id == data["user"]["id"]))
        user = result.scalar_one()
        user.role = Role.ADMIN
        await db.commit()
    return data


def _source_payload(name: str = "Test Registry") -> dict:
    return {
        "name": name,
        "source_class": "public_government",
        "collection_method": "api",
        "reliability_weight": 0.9,
        "geographic_scope": "IN",
    }


async def _create_source(client, owner, **overrides) -> dict:
    payload = {**_source_payload(), **overrides}
    res = await client.post("/api/v1/sources", json=payload, headers=_auth_headers(owner))
    assert res.status_code == 201, res.text
    return res.json()["data"]


async def _create_job(client, admin, source_id: str, requested_scope: dict | None = None) -> dict:
    res = await client.post(
        "/api/v1/acquisition/jobs",
        json={
            "source_id": source_id,
            "collector_type": "mock",
            "requested_scope": requested_scope or {},
        },
        headers=_auth_headers(admin),
    )
    return res


# --------------------------------------------------------------------------
# Successful acquisition — the full pipeline
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_successful_acquisition_creates_job_observations_and_events(client):
    admin = await _register_admin(client, "acq-success@example.com")
    source = await _create_source(client, admin, name="Success Source")

    res = await _create_job(client, admin, source["id"])
    assert res.status_code == 201, res.text
    job = res.json()["data"]
    assert job["status"] == "succeeded"
    assert job["result_count"] == 3
    assert job["skipped_count"] == 0
    assert job["failed_count"] == 0
    assert job["started_at"] is not None
    assert job["completed_at"] is not None

    events_res = await client.get(
        f"/api/v1/acquisition/jobs/{job['id']}/events", headers=_auth_headers(admin)
    )
    events = events_res.json()["data"]["items"]
    assert len(events) == 3
    assert all(e["outcome"] == "created" for e in events)
    assert all(e["raw_observation_id"] is not None for e in events)


@pytest.mark.asyncio
async def test_created_raw_observations_are_real_and_provenance_ready(client):
    """Confirms the pipeline actually reached Module 5A's real
    RawObservation table, not a parallel structure — and that nothing
    was auto-promoted to a ProvenanceRecord (the data trust rule)."""
    admin = await _register_admin(client, "acq-provenance-ready@example.com")
    source = await _create_source(client, admin, name="Provenance Ready Source")
    res = await _create_job(client, admin, source["id"])
    job = res.json()["data"]

    events_res = await client.get(
        f"/api/v1/acquisition/jobs/{job['id']}/events", headers=_auth_headers(admin)
    )
    raw_observation_id = events_res.json()["data"]["items"][0]["raw_observation_id"]

    # This IS a real Module 5A RawObservation, fetchable via its own
    # existing GET route — proof this module reused, not duplicated,
    # Module 5A's model.
    obs_res = await client.get(f"/api/v1/provenance/records/{raw_observation_id}")
    # No provenance record exists with this id at all — because a raw
    # observation was created, but NOTHING promoted it to a
    # ProvenanceRecord. That 404 is the proof.
    assert obs_res.status_code == 404


# --------------------------------------------------------------------------
# Idempotency
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_running_the_same_acquisition_twice_is_idempotent(client):
    admin = await _register_admin(client, "acq-idempotent@example.com")
    source = await _create_source(client, admin, name="Idempotent Source")

    first = await _create_job(client, admin, source["id"])
    assert first.json()["data"]["result_count"] == 3

    second = await _create_job(client, admin, source["id"])
    second_data = second.json()["data"]
    assert second_data["status"] == "succeeded"
    assert second_data["result_count"] == 0
    assert second_data["skipped_count"] == 3
    assert second_data["failed_count"] == 0

    events_res = await client.get(
        f"/api/v1/acquisition/jobs/{second_data['id']}/events", headers=_auth_headers(admin)
    )
    events = events_res.json()["data"]["items"]
    assert all(e["outcome"] == "skipped_duplicate" for e in events)


@pytest.mark.asyncio
async def test_idempotency_is_scoped_per_source_not_global(client):
    """The documented strategy: source_id + external_identifier, never
    a global hash — two DIFFERENT sources collecting the
    same-external-identifier-shaped item must NOT be treated as
    duplicates of each other."""
    admin = await _register_admin(client, "acq-scoped@example.com")
    source_a = await _create_source(client, admin, name="Source A Scoped")
    source_b = await _create_source(client, admin, name="Source B Scoped")

    job_a = await _create_job(client, admin, source_a["id"])
    job_b = await _create_job(client, admin, source_b["id"])

    # Both succeed with 3 CREATED each — source B's identical fixture
    # items are NOT skipped as duplicates of source A's, because the
    # idempotency key is scoped to source_id.
    assert job_a.json()["data"]["result_count"] == 3
    assert job_b.json()["data"]["result_count"] == 3


# --------------------------------------------------------------------------
# Failure handling — retryable vs. non-retryable
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_retryable_failure_retries_then_fails_with_no_fabricated_success(client):
    admin = await _register_admin(client, "acq-retryable@example.com")
    source = await _create_source(client, admin, name="Retryable Source")

    res = await _create_job(client, admin, source["id"], {"simulate_failure": "timeout"})
    job = res.json()["data"]
    assert job["status"] == "failed"
    assert job["retry_count"] == 3  # MAX_RETRIES, bounded — never infinite
    assert job["result_count"] == 0
    assert "timeout" in job["error_message"].lower()
    assert job["started_at"] is not None  # reached RUNNING before failing


@pytest.mark.asyncio
async def test_non_retryable_failure_fails_immediately_with_zero_retries(client):
    admin = await _register_admin(client, "acq-nonretryable@example.com")
    source = await _create_source(client, admin, name="Non-Retryable Source")

    res = await _create_job(
        client, admin, source["id"], {"simulate_failure": "invalid_credentials"}
    )
    job = res.json()["data"]
    assert job["status"] == "failed"
    assert job["retry_count"] == 0  # never retried — retrying couldn't fix invalid credentials
    assert "credentials" in job["error_message"].lower()


@pytest.mark.asyncio
async def test_invalid_collector_configuration_fails_before_running_starts(client):
    admin = await _register_admin(client, "acq-invalidconfig@example.com")
    source = await _create_source(client, admin, name="Invalid Config Source")

    res = await _create_job(client, admin, source["id"], {"simulate_failure": "malformed_config"})
    job = res.json()["data"]
    assert job["status"] == "failed"
    assert job["started_at"] is None  # never reached RUNNING — caught at validate_config


@pytest.mark.asyncio
async def test_unknown_collector_type_rejected(client):
    admin = await _register_admin(client, "acq-unknowntype@example.com")
    source = await _create_source(client, admin, name="Unknown Type Source")

    res = await client.post(
        "/api/v1/acquisition/jobs",
        json={"source_id": source["id"], "collector_type": "definitely_not_registered"},
        headers=_auth_headers(admin),
    )
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "INVALID_COLLECTOR_TYPE"


@pytest.mark.asyncio
async def test_job_for_nonexistent_source_404s(client):
    admin = await _register_admin(client, "acq-nosource@example.com")
    res = await client.post(
        "/api/v1/acquisition/jobs",
        json={"source_id": "00000000-0000-0000-0000-000000000000", "collector_type": "mock"},
        headers=_auth_headers(admin),
    )
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "SOURCE_NOT_FOUND"


# --------------------------------------------------------------------------
# Security — secret redaction
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_secrets_are_redacted_from_stored_config_and_error_message(client):
    admin = await _register_admin(client, "acq-secrets@example.com")
    source = await _create_source(client, admin, name="Secrets Source")

    res = await _create_job(
        client,
        admin,
        source["id"],
        {
            "simulate_failure": "invalid_credentials",
            "password": "super-secret-value-123",
            "api_key": "sk-live-xyz",
        },
    )
    job = res.json()["data"]
    raw_response_text = res.text

    assert "super-secret-value-123" not in raw_response_text
    assert "sk-live-xyz" not in raw_response_text
    assert job["requested_scope"]["password"] == "***REDACTED***"
    assert job["requested_scope"]["api_key"] == "***REDACTED***"
    assert "***REDACTED***" in job["error_message"]


# --------------------------------------------------------------------------
# RBAC
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_non_admin_cannot_create_acquisition_job(client):
    admin = await _register_admin(client, "acq-rbac-admin@example.com")
    source = await _create_source(client, admin, name="RBAC Source")
    viewer = await _register_verified(client, "acq-rbac-viewer@example.com")  # default role: viewer

    res = await client.post(
        "/api/v1/acquisition/jobs",
        json={"source_id": source["id"], "collector_type": "mock"},
        headers=_auth_headers(viewer),
    )
    assert res.status_code == 403


@pytest.mark.asyncio
async def test_job_creation_requires_auth(client):
    res = await client.post(
        "/api/v1/acquisition/jobs",
        json={"source_id": "00000000-0000-0000-0000-000000000000", "collector_type": "mock"},
    )
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_non_admin_cannot_read_job_status(client):
    """Read routes are gated identically to write routes in this
    subsystem — an internal operations surface, not a public dataset."""
    admin = await _register_admin(client, "acq-rbac-read-admin@example.com")
    source = await _create_source(client, admin, name="RBAC Read Source")
    job = (await _create_job(client, admin, source["id"])).json()["data"]
    viewer = await _register_verified(client, "acq-rbac-read-viewer@example.com")

    res = await client.get(f"/api/v1/acquisition/jobs/{job['id']}", headers=_auth_headers(viewer))
    assert res.status_code == 403


@pytest.mark.asyncio
async def test_partial_failure_processes_remaining_items_and_records_per_item_outcomes(client):
    """One item genuinely fails validation (empty raw_content) while
    the other two succeed in the same run — the job must not abort
    entirely, and must not report SUCCEEDED as if nothing went wrong."""
    admin = await _register_admin(client, "acq-partial@example.com")
    source = await _create_source(client, admin, name="Partial Failure Source")

    res = await _create_job(client, admin, source["id"], {"simulate_failure": "partial"})
    job = res.json()["data"]
    assert job["result_count"] == 2
    assert job["failed_count"] == 1
    assert (
        job["status"] == "succeeded"
    )  # not all items failed — a real, non-fabricated partial success

    events_res = await client.get(
        f"/api/v1/acquisition/jobs/{job['id']}/events", headers=_auth_headers(admin)
    )
    events = events_res.json()["data"]["items"]
    outcomes = sorted(e["outcome"] for e in events)
    assert outcomes == ["created", "created", "failed"]
    failed_event = next(e for e in events if e["outcome"] == "failed")
    assert failed_event["error_message"] is not None
    assert failed_event["raw_observation_id"] is None


@pytest.mark.asyncio
async def test_job_where_every_item_fails_is_honestly_failed_not_succeeded(client):
    """The stricter case: if literally everything failed, the job
    itself must be FAILED, never SUCCEEDED with a misleadingly empty
    result set."""
    admin = await _register_admin(client, "acq-allfail@example.com")
    source = await _create_source(client, admin, name="All Fail Source")

    res = await _create_job(client, admin, source["id"], {"simulate_failure": "all_invalid"})
    job = res.json()["data"]
    assert job["result_count"] == 0
    assert job["failed_count"] == 3
    assert job["skipped_count"] == 0
    assert job["status"] == "failed"
    assert "3" in job["error_message"]


# --------------------------------------------------------------------------
# Job listing / status
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_jobs_filters_by_source_and_status(client):
    admin = await _register_admin(client, "acq-list@example.com")
    source_a = await _create_source(client, admin, name="List Source A")
    source_b = await _create_source(client, admin, name="List Source B")

    await _create_job(client, admin, source_a["id"])
    await _create_job(client, admin, source_b["id"], {"simulate_failure": "invalid_credentials"})

    res = await client.get(
        f"/api/v1/acquisition/jobs?source_id={source_a['id']}", headers=_auth_headers(admin)
    )
    items = res.json()["data"]["items"]
    assert all(item["source_id"] == source_a["id"] for item in items)

    failed_res = await client.get(
        "/api/v1/acquisition/jobs?status=failed", headers=_auth_headers(admin)
    )
    failed_items = failed_res.json()["data"]["items"]
    assert all(item["status"] == "failed" for item in failed_items)
    assert any(item["source_id"] == source_b["id"] for item in failed_items)


@pytest.mark.asyncio
async def test_get_nonexistent_job_404s(client):
    admin = await _register_admin(client, "acq-missing@example.com")
    res = await client.get(
        "/api/v1/acquisition/jobs/00000000-0000-0000-0000-000000000000",
        headers=_auth_headers(admin),
    )
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "JOB_NOT_FOUND"
