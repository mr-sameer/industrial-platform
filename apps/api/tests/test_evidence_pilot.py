"""
Module 8B tests — Company Evidence & Verification (pilot phase). Covers
the four new ManualEntry extra_fields, apply_reviewed_field_to_company
(the one new path from a VERIFIED ProvenanceRecord to the canonical
Company row), attach_capability_evidence (the one new path from a
RawObservation to an OBSERVED GraphRelationship), and one end-to-end
scenario tying manual-entry submission -> entity resolution -> verify
-> apply-to-company -> capability evidence -> relationship verification
together.

No live website or external API is ever contacted here — every
RawObservation is created either directly via the service layer
(matching tests/test_usa_pilot.py's own established AsyncSessionLocal
pattern) or through the existing, already-real manual_entry acquisition
endpoint (POST /acquisition/jobs with collector_type="manual_entry" IS
the manual-entry submission path, per
app.collectors.manual_entry_adapter's own docstring — "collection" is
just echoing the submitted config back, no network call involved).
"""

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app.collectors.field_profiles import _MANUAL_ENTRY_PROFILE
from app.db.session import AsyncSessionLocal
from app.models.capability import Capability
from app.models.provenance_record import ProvenanceStatus
from app.models.source_registry import CollectionMethod, SourceClass
from app.schemas.provenance import RawObservationCreate, SourceRegistryCreate
from app.services import evidence_service, provenance_service
from tests.test_acquisition import _register_admin
from tests.test_companies import _auth_headers
from tests.test_data_quality import _create_provenance
from tests.test_graph import _create_company

_NEW_EVIDENCE_FIELDS = (
    "short_description",
    "claimed_industries",
    "claimed_certifications",
    "products_or_services_summary",
)


async def _create_manual_source(client, admin) -> dict:
    res = await client.post(
        "/api/v1/sources",
        json={
            "name": "Manual Entry (evidence pilot test)",
            "source_class": "user_contribution",
            "collection_method": "manual",
        },
        headers=_auth_headers(admin),
    )
    assert res.status_code == 201, res.text
    return res.json()["data"]


async def _verify_record(client, admin, record_id: str) -> dict:
    res = await client.post(
        f"/api/v1/provenance/records/{record_id}/verify", headers=_auth_headers(admin)
    )
    assert res.status_code == 200, res.text
    return res.json()["data"]


async def _apply_to_company(client, admin, record_id: str, company_id: str, *, overwrite: bool = False):
    return await client.post(
        f"/api/v1/provenance/records/{record_id}/apply-to-company",
        json={"company_id": company_id, "overwrite": overwrite},
        headers=_auth_headers(admin),
    )


async def _create_manual_raw_observation_id(company_name: str) -> uuid.UUID:
    """
    Creates a real SourceRegistry + RawObservation directly via the
    service layer — no HTTP client, no external call — matching
    tests/test_usa_pilot.py's own established AsyncSessionLocal
    pattern for tests that need a raw observation with no API route
    involved. Returns a plain uuid.UUID (not an ORM object bound to a
    now-closed session), so callers are free to open their own,
    separate AsyncSessionLocal session afterward.
    """
    async with AsyncSessionLocal() as db:
        source = await provenance_service.create_source(
            db,
            SourceRegistryCreate(
                name=f"Capability Evidence Test Source {uuid.uuid4().hex[:8]}",
                source_class=SourceClass.USER_CONTRIBUTION,
                collection_method=CollectionMethod.MANUAL,
            ),
        )
        observation = await provenance_service.create_raw_observation(
            db,
            RawObservationCreate(
                source_id=source.id,
                raw_content={"company_name": company_name},
                content_hash=uuid.uuid4().hex,
                collection_method_used=CollectionMethod.MANUAL,
                collected_at=datetime(2026, 8, 16, tzinfo=UTC),
            ),
        )
        return observation.id


# --------------------------------------------------------------------------
# ManualEntry field_profiles extension
# --------------------------------------------------------------------------


def test_manual_entry_profile_includes_four_new_evidence_fields():
    for field in _NEW_EVIDENCE_FIELDS:
        assert field in _MANUAL_ENTRY_PROFILE.extra_fields
        # Never direct_fields — must stay provenance-only, never
        # auto-written to a Company column at creation time either.
        assert field not in _MANUAL_ENTRY_PROFILE.direct_fields


@pytest.mark.asyncio
async def test_manual_entry_new_fields_produce_observed_manual_provenance(client):
    """Through the real, unmodified manual_entry acquisition endpoint:
    all 4 new fields become ProvenanceRecords, extraction_method=manual,
    status=observed — never touching any Company column directly."""
    admin = await _register_admin(client, "me-newfields@example.com")
    source = await _create_manual_source(client, admin)

    job_res = await client.post(
        "/api/v1/acquisition/jobs",
        json={
            "source_id": source["id"],
            "collector_type": "manual_entry",
            "requested_scope": {
                "company_name": "Field Test Manufacturing Co",
                "entered_by": admin["user"]["id"],
                "short_description": "A short evidence-sourced description.",
                "claimed_industries": "Textiles, Packaging",
                "claimed_certifications": "ISO 9001 (claimed on website)",
                "products_or_services_summary": "Woven bags, industrial packaging.",
            },
        },
        headers=_auth_headers(admin),
    )
    assert job_res.status_code == 201, job_res.text
    job = job_res.json()["data"]
    assert job["status"] == "succeeded"

    events = (
        await client.get(
            f"/api/v1/acquisition/jobs/{job['id']}/events", headers=_auth_headers(admin)
        )
    ).json()["data"]["items"]
    obs_id = events[0]["raw_observation_id"]

    candidate_res = await client.post(
        "/api/v1/entity-resolution/candidates",
        json={"raw_observation_id": obs_id},
        headers=_auth_headers(admin),
    )
    assert candidate_res.status_code == 201, candidate_res.text
    candidate = candidate_res.json()["data"]

    decide_res = await client.post(
        f"/api/v1/entity-resolution/candidates/{candidate['id']}/decide",
        json={"decision": "create_new"},
        headers=_auth_headers(admin),
    )
    assert decide_res.status_code == 200, decide_res.text

    company_res = await client.get(
        f"/api/v1/entity-resolution/candidates/{candidate['id']}/company",
        headers=_auth_headers(admin),
    )
    company = company_res.json()["data"]
    # description is an extra_field for manual_entry — never
    # auto-written to the Company row at CREATE_NEW time either.
    assert company["description"] is None

    prov_res = await client.get(
        "/api/v1/provenance",
        params={"entity_type": "company", "entity_id": company["id"], "page_size": 50},
        headers=_auth_headers(admin),
    )
    records = prov_res.json()["data"]["items"]
    by_field = {r["field_name"]: r for r in records}
    for field in _NEW_EVIDENCE_FIELDS:
        assert field in by_field, by_field.keys()
        assert by_field[field]["extraction_method"] == "manual"
        assert by_field[field]["status"] == "observed"


# --------------------------------------------------------------------------
# apply_reviewed_field_to_company — via POST /provenance/records/{id}/apply-to-company
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_apply_to_company_requires_verified_status(client):
    admin = await _register_admin(client, "apply-notverified@example.com")
    company = await _create_company(client, admin, name="Apply NotVerified Co")
    record = await _create_provenance(
        client,
        admin,
        entity_type="company",
        entity_id=company["id"],
        field_name="description",
        value="Observed, not yet verified.",
        status_value="observed",
    )

    res = await _apply_to_company(client, admin, record["id"], company["id"])
    assert res.status_code == 422, res.text
    assert res.json()["error"]["code"] == "NOT_VERIFIED"


@pytest.mark.asyncio
async def test_apply_to_company_rejects_company_mismatch(client):
    admin = await _register_admin(client, "apply-mismatch@example.com")
    company_a = await _create_company(client, admin, name="Apply Mismatch Co A")
    company_b = await _create_company(client, admin, name="Apply Mismatch Co B")
    record = await _create_provenance(
        client,
        admin,
        entity_type="company",
        entity_id=company_a["id"],
        field_name="description",
        value="Evidence about company A.",
    )
    await _verify_record(client, admin, record["id"])

    res = await _apply_to_company(client, admin, record["id"], company_b["id"])
    assert res.status_code == 422, res.text
    assert res.json()["error"]["code"] == "COMPANY_MISMATCH"


@pytest.mark.asyncio
async def test_apply_to_company_rejects_non_allowlisted_field(client):
    admin = await _register_admin(client, "apply-notallowed@example.com")
    company = await _create_company(client, admin, name="Apply NotAllowed Co")
    record = await _create_provenance(
        client,
        admin,
        entity_type="company",
        entity_id=company["id"],
        field_name="cin",  # a real field_name this codebase uses, but never applyable
        value="U12345MH2020PTC000001",
    )
    await _verify_record(client, admin, record["id"])

    res = await _apply_to_company(client, admin, record["id"], company["id"])
    assert res.status_code == 422, res.text
    assert res.json()["error"]["code"] == "FIELD_NOT_ALLOWLISTED"


@pytest.mark.asyncio
async def test_apply_to_company_rejects_empty_value(client):
    admin = await _register_admin(client, "apply-empty@example.com")
    company = await _create_company(client, admin, name="Apply Empty Co")
    # Schema requires min_length=1, so this is whitespace-only rather
    # than a literal empty string — value_observed.strip() still
    # yields "" inside the service, which is exactly what's under test.
    record = await _create_provenance(
        client,
        admin,
        entity_type="company",
        entity_id=company["id"],
        field_name="short_description",
        value="   ",
    )
    await _verify_record(client, admin, record["id"])

    res = await _apply_to_company(client, admin, record["id"], company["id"])
    assert res.status_code == 422, res.text
    assert res.json()["error"]["code"] == "EMPTY_VALUE"


@pytest.mark.asyncio
async def test_apply_to_company_rejects_value_exceeding_column_length(client):
    admin = await _register_admin(client, "apply-toolong@example.com")
    company = await _create_company(client, admin, name="Apply TooLong Co")
    record = await _create_provenance(
        client,
        admin,
        entity_type="company",
        entity_id=company["id"],
        field_name="industry",  # Company.industry is String(120)
        value="X" * 121,
    )
    await _verify_record(client, admin, record["id"])

    res = await _apply_to_company(client, admin, record["id"], company["id"])
    assert res.status_code == 422, res.text
    assert res.json()["error"]["code"] == "VALUE_TOO_LONG"


@pytest.mark.asyncio
async def test_apply_to_company_conflict_requires_explicit_overwrite(client):
    admin = await _register_admin(client, "apply-conflict@example.com")
    # _company_payload sets description="We make things." and
    # industry="Manufacturing" — real, pre-existing values this new
    # evidence will disagree with (description) or must leave
    # untouched (industry).
    company = await _create_company(client, admin, name="Apply Conflict Co")
    assert company["description"] == "We make things."
    assert company["industry"] == "Manufacturing"

    record = await _create_provenance(
        client,
        admin,
        entity_type="company",
        entity_id=company["id"],
        field_name="description",
        value="A newer, website-sourced description.",
    )
    await _verify_record(client, admin, record["id"])

    rejected = await _apply_to_company(client, admin, record["id"], company["id"], overwrite=False)
    assert rejected.status_code == 409, rejected.text
    assert rejected.json()["error"]["code"] == "CONFLICTING_VALUE"

    # Confirm the reject was truly a no-op — canonical value unchanged.
    unchanged_res = await client.get(
        f"/api/v1/companies/{company['id']}", headers=_auth_headers(admin)
    )
    assert unchanged_res.json()["data"]["description"] == "We make things."

    accepted = await _apply_to_company(client, admin, record["id"], company["id"], overwrite=True)
    assert accepted.status_code == 200, accepted.text
    body = accepted.json()["data"]
    assert body["company_id"] == company["id"]
    assert body["field_name"] == "description"
    assert body["provenance_record"]["review_note"] is not None
    assert str(admin["user"]["id"]) in body["provenance_record"]["review_note"]

    company_res = await client.get(
        f"/api/v1/companies/{company['id']}", headers=_auth_headers(admin)
    )
    updated = company_res.json()["data"]
    assert updated["description"] == "A newer, website-sourced description."
    # Only the allowlisted, targeted field changed — nothing else did.
    assert updated["industry"] == "Manufacturing"


# --------------------------------------------------------------------------
# attach_capability_evidence — service-level (no API route exists yet, by design)
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_attach_capability_evidence_status_is_observed_not_verified(client):
    admin = await _register_admin(client, "cap-observed@example.com")
    company = await _create_company(client, admin, name="Capability Observed Co")
    obs_id = await _create_manual_raw_observation_id("Capability Observed Co")

    async with AsyncSessionLocal() as db:
        relationships = await evidence_service.attach_capability_evidence(
            db, obs_id, uuid.UUID(company["id"]), ["CNC Machining"], uuid.UUID(admin["user"]["id"])
        )
    assert len(relationships) == 1
    assert relationships[0].status == ProvenanceStatus.OBSERVED


@pytest.mark.asyncio
async def test_attach_capability_evidence_links_raw_observation_id(client):
    admin = await _register_admin(client, "cap-linked@example.com")
    company = await _create_company(client, admin, name="Capability Linked Co")
    obs_id = await _create_manual_raw_observation_id("Capability Linked Co")

    async with AsyncSessionLocal() as db:
        relationships = await evidence_service.attach_capability_evidence(
            db, obs_id, uuid.UUID(company["id"]), ["Forging"], uuid.UUID(admin["user"]["id"])
        )
    assert relationships[0].raw_observation_id == obs_id
    assert str(relationships[0].company_subject_id) == company["id"]


@pytest.mark.asyncio
async def test_attach_capability_evidence_repeated_call_is_idempotent(client):
    admin = await _register_admin(client, "cap-idempotent@example.com")
    company = await _create_company(client, admin, name="Capability Idempotent Co")
    obs_id = await _create_manual_raw_observation_id("Capability Idempotent Co")

    async with AsyncSessionLocal() as db:
        first = await evidence_service.attach_capability_evidence(
            db, obs_id, uuid.UUID(company["id"]), ["Casting"], uuid.UUID(admin["user"]["id"])
        )
        second = await evidence_service.attach_capability_evidence(
            db, obs_id, uuid.UUID(company["id"]), ["Casting"], uuid.UUID(admin["user"]["id"])
        )
        assert first[0].id == second[0].id

        capabilities = (
            (await db.execute(select(Capability).where(Capability.name == "Casting")))
            .scalars()
            .all()
        )
        assert len(capabilities) == 1


@pytest.mark.asyncio
async def test_attach_capability_evidence_raises_for_nonexistent_observation(client):
    admin = await _register_admin(client, "cap-noobs@example.com")
    company = await _create_company(client, admin, name="Capability NoObs Co")

    async with AsyncSessionLocal() as db:
        with pytest.raises(evidence_service.RawObservationNotFoundForEvidenceError):
            await evidence_service.attach_capability_evidence(
                db, uuid.uuid4(), uuid.UUID(company["id"]), ["Welding"], uuid.UUID(admin["user"]["id"])
            )


# --------------------------------------------------------------------------
# End-to-end: manual submission -> entity resolution -> verify ->
# apply-to-company -> capability evidence -> relationship verification
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_evidence_pilot_end_to_end(client):
    admin = await _register_admin(client, "evidence-e2e@example.com")
    source = await _create_manual_source(client, admin)

    job_res = await client.post(
        "/api/v1/acquisition/jobs",
        json={
            "source_id": source["id"],
            "collector_type": "manual_entry",
            "requested_scope": {
                "company_name": "End To End Evidence Manufacturing",
                "entered_by": admin["user"]["id"],
                "evidence_url": "https://e2e-evidence.example.com",
                "industry": "Industrial Machinery",
                "state": "Gujarat",
                "country": "India",
                "description": "Manufactures precision industrial components.",
                "short_description": "Precision components manufacturer.",
                "claimed_certifications": "ISO 9001 (as stated on website)",
            },
        },
        headers=_auth_headers(admin),
    )
    assert job_res.status_code == 201, job_res.text
    job = job_res.json()["data"]
    assert job["status"] == "succeeded"

    events = (
        await client.get(
            f"/api/v1/acquisition/jobs/{job['id']}/events", headers=_auth_headers(admin)
        )
    ).json()["data"]["items"]
    obs_id = events[0]["raw_observation_id"]

    candidate_res = await client.post(
        "/api/v1/entity-resolution/candidates",
        json={"raw_observation_id": obs_id},
        headers=_auth_headers(admin),
    )
    candidate = candidate_res.json()["data"]
    assert candidate["resolution_state"] == "new"

    decide_res = await client.post(
        f"/api/v1/entity-resolution/candidates/{candidate['id']}/decide",
        json={"decision": "create_new"},
        headers=_auth_headers(admin),
    )
    assert decide_res.status_code == 200, decide_res.text

    company_res = await client.get(
        f"/api/v1/entity-resolution/candidates/{candidate['id']}/company",
        headers=_auth_headers(admin),
    )
    company = company_res.json()["data"]
    assert company["verification_status"] == "unverified"
    # description/short_description are extra_fields for manual_entry —
    # never auto-written to the Company row at creation, exactly the
    # gap apply_reviewed_field_to_company exists to close.
    assert company["description"] is None

    prov_res = await client.get(
        "/api/v1/provenance",
        params={"entity_type": "company", "entity_id": company["id"], "page_size": 50},
        headers=_auth_headers(admin),
    )
    records = {r["field_name"]: r for r in prov_res.json()["data"]["items"]}
    assert records["description"]["status"] == "observed"
    assert records["short_description"]["status"] == "observed"
    assert records["claimed_certifications"]["status"] == "observed"

    # Verify, then apply, the two allowlisted fields.
    for field_name in ("description", "short_description"):
        verified = await _verify_record(client, admin, records[field_name]["id"])
        assert verified["status"] == "verified"
        applied = await _apply_to_company(client, admin, records[field_name]["id"], company["id"])
        assert applied.status_code == 200, applied.text

    # claimed_certifications is NOT allowlisted — verifying it is fine,
    # applying it must be refused (no Company column exists for it —
    # "ISO certificate mentioned" must never silently become "ISO
    # certified").
    cert_verified = await _verify_record(client, admin, records["claimed_certifications"]["id"])
    assert cert_verified["status"] == "verified"
    cert_apply = await _apply_to_company(
        client, admin, records["claimed_certifications"]["id"], company["id"]
    )
    assert cert_apply.status_code == 422
    assert cert_apply.json()["error"]["code"] == "FIELD_NOT_ALLOWLISTED"

    company_after = (
        await client.get(f"/api/v1/companies/{company['id']}", headers=_auth_headers(admin))
    ).json()["data"]
    assert company_after["description"] == "Manufactures precision industrial components."

    # Capability evidence — service-level (no route yet, by design).
    async with AsyncSessionLocal() as db:
        relationships = await evidence_service.attach_capability_evidence(
            db,
            uuid.UUID(obs_id),
            uuid.UUID(company["id"]),
            ["CNC Machining"],
            uuid.UUID(admin["user"]["id"]),
        )
    assert len(relationships) == 1
    relationship_id = str(relationships[0].id)
    assert relationships[0].status == ProvenanceStatus.OBSERVED
    assert str(relationships[0].raw_observation_id) == obs_id

    verify_res = await client.post(
        f"/api/v1/graph/relationships/{relationship_id}/verify", headers=_auth_headers(admin)
    )
    assert verify_res.status_code == 200, verify_res.text
    assert verify_res.json()["data"]["status"] == "verified"

    # verification_status is still the plain, unrelated Module 3B
    # placeholder — none of this pipeline ever touches it.
    company_final = (
        await client.get(f"/api/v1/companies/{company['id']}", headers=_auth_headers(admin))
    ).json()["data"]
    assert company_final["verification_status"] == "unverified"
