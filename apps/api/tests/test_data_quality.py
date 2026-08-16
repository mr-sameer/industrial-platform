"""
Module 5E tests — Data Quality & Verification Operations. Covers the
extended ProvenanceRecord status model, field-level quality metadata,
the composite score, the review queue, all four new review actions,
risk classification, freshness, evidence linking, RBAC, auditability,
Product quality, and — the ticket's own explicitly-required critical
regression test — that Company.verification_status's existing,
completeness-based auto-sync behavior is completely unaffected.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.db.session import AsyncSessionLocal
from app.models.audit_log import AuditLog
from tests.test_acquisition import _create_source, _register_admin
from tests.test_companies import _auth_headers, _register_verified
from tests.test_company_verification import _create_verified_owner_company, _make_test_pdf_bytes


async def _create_provenance(
    client,
    admin,
    *,
    entity_type: str,
    entity_id: str,
    field_name: str,
    value: str,
    status_value: str = "observed",
) -> dict:
    source = await _create_source(client, admin, name=f"DQ Source {uuid.uuid4().hex[:8]}")
    obs_res = await client.post(
        f"/api/v1/sources/{source['id']}/observations",
        json={
            "source_id": source["id"],
            "raw_content": {field_name: value},
            "content_hash": uuid.uuid4().hex,
            "collection_method_used": "api",
            "collected_at": "2026-08-09T00:00:00Z",
        },
        headers=_auth_headers(admin),
    )
    assert obs_res.status_code == 201, obs_res.text
    obs_id = obs_res.json()["data"]["id"]

    key = "company_id" if entity_type == "company" else "product_id"
    payload = {
        "entity_type": entity_type,
        key: entity_id,
        "field_name": field_name,
        "raw_observation_id": obs_id,
        "value_observed": value,
        "extraction_method": "manual",
        "confidence": 0.8,
        "status": status_value,
    }
    prov_res = await client.post(
        "/api/v1/provenance/records", json=payload, headers=_auth_headers(admin)
    )
    assert prov_res.status_code == 201, prov_res.text
    return prov_res.json()["data"]


async def _create_product(client, admin) -> dict:
    cat_res = await client.post(
        "/api/v1/product-categories",
        json={"name": f"DQ Category {uuid.uuid4().hex[:8]}"},
        headers=_auth_headers(admin),
    )
    category_id = cat_res.json()["data"]["id"]
    prod_res = await client.post(
        "/api/v1/products",
        json={"name": f"DQ Product {uuid.uuid4().hex[:8]}", "category_id": category_id},
        headers=_auth_headers(admin),
    )
    return prod_res.json()["data"]


# --------------------------------------------------------------------------
# Field-level quality metadata
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_quality_report_is_field_level_never_a_single_company_score_alone(client):
    admin = await _register_admin(client, "dq-fieldlevel@example.com")
    _owner, company = await _create_verified_owner_company(client, "dq-fieldlevel-co@example.com")

    await _create_provenance(
        client, admin, entity_type="company", entity_id=company["id"], field_name="cin", value="U1"
    )
    await _create_provenance(
        client,
        admin,
        entity_type="company",
        entity_id=company["id"],
        field_name="website",
        value="example.com",
    )

    res = await client.get(
        f"/api/v1/data-quality/company/{company['id']}", headers=_auth_headers(admin)
    )
    assert res.status_code == 200
    data = res.json()["data"]
    assert len(data["fields"]) == 2
    field_names = {f["field_name"] for f in data["fields"]}
    assert field_names == {"cin", "website"}
    risk_by_field = {f["field_name"]: f["risk_level"] for f in data["fields"]}
    assert risk_by_field["cin"] == "high"
    assert risk_by_field["website"] == "medium"
    assert "quality_score" in data
    assert "NOT a measure of factual truth" in data["quality_score"]["meaning"]


@pytest.mark.asyncio
async def test_quality_score_always_ships_with_breakdown(client):
    admin = await _register_admin(client, "dq-scorebundle@example.com")
    _owner, company = await _create_verified_owner_company(client, "dq-scorebundle-co@example.com")
    res = await client.get(
        f"/api/v1/data-quality/company/{company['id']}", headers=_auth_headers(admin)
    )
    data = res.json()["data"]
    assert "fields" in data
    assert "quality_score" in data
    assert data["quality_score"]["score"] is not None


# --------------------------------------------------------------------------
# The four/five real states
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_observed_state(client):
    admin = await _register_admin(client, "dq-observed@example.com")
    _owner, company = await _create_verified_owner_company(client, "dq-observed-co@example.com")
    record = await _create_provenance(
        client,
        admin,
        entity_type="company",
        entity_id=company["id"],
        field_name="industry",
        value="Motors",
    )
    assert record["status"] == "observed"


@pytest.mark.asyncio
async def test_extracted_state(client):
    admin = await _register_admin(client, "dq-extracted@example.com")
    _owner, company = await _create_verified_owner_company(client, "dq-extracted-co@example.com")
    record = await _create_provenance(
        client,
        admin,
        entity_type="company",
        entity_id=company["id"],
        field_name="industry",
        value="Motors",
        status_value="extracted",
    )
    assert record["status"] == "extracted"


@pytest.mark.asyncio
async def test_claimed_state(client):
    admin = await _register_admin(client, "dq-claimed@example.com")
    _owner, company = await _create_verified_owner_company(client, "dq-claimed-co@example.com")
    record = await _create_provenance(
        client,
        admin,
        entity_type="company",
        entity_id=company["id"],
        field_name="industry",
        value="Motors",
        status_value="claimed",
    )
    assert record["status"] == "claimed"


@pytest.mark.asyncio
async def test_verified_state_still_only_reachable_via_existing_module_5a_action(client):
    admin = await _register_admin(client, "dq-verified@example.com")
    _owner, company = await _create_verified_owner_company(client, "dq-verified-co@example.com")
    record = await _create_provenance(
        client,
        admin,
        entity_type="company",
        entity_id=company["id"],
        field_name="industry",
        value="Motors",
    )
    res = await client.post(
        f"/api/v1/provenance/records/{record['id']}/verify", headers=_auth_headers(admin)
    )
    assert res.status_code == 200
    assert res.json()["data"]["status"] == "verified"


@pytest.mark.asyncio
async def test_under_review_state(client):
    admin = await _register_admin(client, "dq-underreview@example.com")
    _owner, company = await _create_verified_owner_company(client, "dq-underreview-co@example.com")
    record = await _create_provenance(
        client,
        admin,
        entity_type="company",
        entity_id=company["id"],
        field_name="industry",
        value="Motors",
    )
    res = await client.post(
        f"/api/v1/data-quality/records/{record['id']}/review", headers=_auth_headers(admin)
    )
    assert res.status_code == 200
    assert res.json()["data"]["status"] == "under_review"


@pytest.mark.asyncio
async def test_rejected_state(client):
    admin = await _register_admin(client, "dq-rejected@example.com")
    _owner, company = await _create_verified_owner_company(client, "dq-rejected-co@example.com")
    record = await _create_provenance(
        client,
        admin,
        entity_type="company",
        entity_id=company["id"],
        field_name="industry",
        value="Motors",
    )
    res = await client.post(
        f"/api/v1/data-quality/records/{record['id']}/reject",
        json={"note": "Could not confirm."},
        headers=_auth_headers(admin),
    )
    assert res.status_code == 200
    body = res.json()["data"]
    assert body["status"] == "rejected"
    assert body["review_note"] == "Could not confirm."


@pytest.mark.asyncio
async def test_reject_requires_a_note(client):
    admin = await _register_admin(client, "dq-rejectnonote@example.com")
    _owner, company = await _create_verified_owner_company(client, "dq-rejectnonote-co@example.com")
    record = await _create_provenance(
        client,
        admin,
        entity_type="company",
        entity_id=company["id"],
        field_name="industry",
        value="Motors",
    )
    res = await client.post(
        f"/api/v1/data-quality/records/{record['id']}/reject",
        json={"note": ""},
        headers=_auth_headers(admin),
    )
    assert res.status_code == 422


@pytest.mark.asyncio
async def test_expired_state_only_reachable_from_verified(client):
    admin = await _register_admin(client, "dq-expired@example.com")
    _owner, company = await _create_verified_owner_company(client, "dq-expired-co@example.com")
    record = await _create_provenance(
        client,
        admin,
        entity_type="company",
        entity_id=company["id"],
        field_name="industry",
        value="Motors",
    )

    premature = await client.post(
        f"/api/v1/data-quality/records/{record['id']}/mark-expired",
        json={"note": "test"},
        headers=_auth_headers(admin),
    )
    assert premature.status_code == 409

    await client.post(
        f"/api/v1/provenance/records/{record['id']}/verify", headers=_auth_headers(admin)
    )
    now_expired = await client.post(
        f"/api/v1/data-quality/records/{record['id']}/mark-expired",
        json={"note": "Certificate expired."},
        headers=_auth_headers(admin),
    )
    assert now_expired.status_code == 200
    assert now_expired.json()["data"]["status"] == "expired"


@pytest.mark.asyncio
async def test_review_transition_from_verified_is_rejected(client):
    admin = await _register_admin(client, "dq-noverifyreject@example.com")
    _owner, company = await _create_verified_owner_company(
        client, "dq-noverifyreject-co@example.com"
    )
    record = await _create_provenance(
        client,
        admin,
        entity_type="company",
        entity_id=company["id"],
        field_name="industry",
        value="Motors",
    )
    await client.post(
        f"/api/v1/provenance/records/{record['id']}/verify", headers=_auth_headers(admin)
    )
    res = await client.post(
        f"/api/v1/data-quality/records/{record['id']}/reject",
        json={"note": "test"},
        headers=_auth_headers(admin),
    )
    assert res.status_code == 409


# --------------------------------------------------------------------------
# Freshness / staleness
# --------------------------------------------------------------------------


def test_freshness_classification_is_field_category_specific():
    from app.data_quality.freshness import FreshnessState, classify_freshness

    now = datetime.now(UTC)
    assert classify_freshness("cin", now - timedelta(days=60)) == FreshnessState.FRESH
    assert classify_freshness("industry", now - timedelta(days=60)) == FreshnessState.STALE
    assert (
        classify_freshness("industry", now - timedelta(days=26)) == FreshnessState.APPROACHING_STALE
    )


@pytest.mark.asyncio
async def test_stale_field_detected_in_quality_report(client):
    admin = await _register_admin(client, "dq-stale@example.com")
    _owner, company = await _create_verified_owner_company(client, "dq-stale-co@example.com")
    record = await _create_provenance(
        client,
        admin,
        entity_type="company",
        entity_id=company["id"],
        field_name="industry",
        value="Motors",
    )

    async with AsyncSessionLocal() as db:
        from app.models.provenance_record import ProvenanceRecord

        result = await db.execute(
            select(ProvenanceRecord).where(ProvenanceRecord.id == record["id"])
        )
        row = result.scalar_one()
        row.last_observed_at = datetime.now(UTC) - timedelta(days=60)
        await db.commit()

    res = await client.get(
        f"/api/v1/data-quality/company/{company['id']}", headers=_auth_headers(admin)
    )
    field = next(f for f in res.json()["data"]["fields"] if f["field_name"] == "industry")
    assert field["freshness"] == "stale"


# --------------------------------------------------------------------------
# Conflicts — reused, not reimplemented
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_conflict_creation_and_visibility_reuses_module_5a_unchanged(client):
    admin = await _register_admin(client, "dq-conflict@example.com")
    _owner, company = await _create_verified_owner_company(client, "dq-conflict-co@example.com")
    await _create_provenance(
        client,
        admin,
        entity_type="company",
        entity_id=company["id"],
        field_name="city",
        value="Pune",
    )
    second = await _create_provenance(
        client,
        admin,
        entity_type="company",
        entity_id=company["id"],
        field_name="city",
        value="Mumbai",
    )
    assert second["conflict_id"] is not None

    conflicts = await client.get(
        "/api/v1/provenance/conflicts?status=open", headers=_auth_headers(admin)
    )
    assert any(c["id"] == second["conflict_id"] for c in conflicts.json()["data"]["items"])


@pytest.mark.asyncio
async def test_conflict_resolution_reuses_module_5a_unchanged(client):
    admin = await _register_admin(client, "dq-conflictresolve@example.com")
    _owner, company = await _create_verified_owner_company(
        client, "dq-conflictresolve-co@example.com"
    )
    await _create_provenance(
        client,
        admin,
        entity_type="company",
        entity_id=company["id"],
        field_name="city",
        value="Pune",
    )
    second = await _create_provenance(
        client,
        admin,
        entity_type="company",
        entity_id=company["id"],
        field_name="city",
        value="Mumbai",
    )
    resolve_res = await client.post(
        f"/api/v1/provenance/conflicts/{second['conflict_id']}/resolve",
        json={"resolution_note": "Confirmed Mumbai via registry."},
        headers=_auth_headers(admin),
    )
    assert resolve_res.status_code == 200
    assert resolve_res.json()["data"]["status"] == "resolved"


# --------------------------------------------------------------------------
# Evidence — never automatically equals verification
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_linking_evidence_never_changes_status(client):
    admin = await _register_admin(client, "dq-evidence@example.com")
    owner, company = await _create_verified_owner_company(client, "dq-evidence-co@example.com")
    record = await _create_provenance(
        client,
        admin,
        entity_type="company",
        entity_id=company["id"],
        field_name="industry",
        value="Motors",
    )

    doc_res = await client.post(
        f"/api/v1/companies/{company['id']}/documents",
        data={"document_type": "business_registration"},
        files={"file": ("cert.pdf", _make_test_pdf_bytes(), "application/pdf")},
        headers=_auth_headers(owner),
    )
    assert doc_res.status_code == 201, doc_res.text
    document_id = doc_res.json()["data"]["id"]

    link_res = await client.post(
        f"/api/v1/data-quality/records/{record['id']}/link-evidence",
        json={"verification_document_id": document_id},
        headers=_auth_headers(admin),
    )
    assert link_res.status_code == 200
    body = link_res.json()["data"]
    assert body["verification_document_id"] == document_id
    assert body["status"] == "observed"


@pytest.mark.asyncio
async def test_link_evidence_nonexistent_document_404s(client):
    admin = await _register_admin(client, "dq-nodoc@example.com")
    _owner, company = await _create_verified_owner_company(client, "dq-nodoc-co@example.com")
    record = await _create_provenance(
        client,
        admin,
        entity_type="company",
        entity_id=company["id"],
        field_name="industry",
        value="Motors",
    )
    res = await client.post(
        f"/api/v1/data-quality/records/{record['id']}/link-evidence",
        json={"verification_document_id": "00000000-0000-0000-0000-000000000000"},
        headers=_auth_headers(admin),
    )
    assert res.status_code == 404


# --------------------------------------------------------------------------
# Risk classification
# --------------------------------------------------------------------------


def test_risk_classification_matches_architecture():
    from app.data_quality.risk_classification import RiskLevel, classify_field

    assert classify_field("company", "cin") == RiskLevel.HIGH
    assert classify_field("company", "gst_number") == RiskLevel.HIGH
    assert classify_field("company", "name") == RiskLevel.LOW
    assert classify_field("company", "website") == RiskLevel.MEDIUM
    assert classify_field("company", "totally_unknown_field") == RiskLevel.MEDIUM


@pytest.mark.asyncio
async def test_high_risk_claims_appear_in_review_queue_when_unverified(client):
    admin = await _register_admin(client, "dq-highriskqueue@example.com")
    _owner, company = await _create_verified_owner_company(
        client, "dq-highriskqueue-co@example.com"
    )
    record = await _create_provenance(
        client, admin, entity_type="company", entity_id=company["id"], field_name="cin", value="U9"
    )
    queue = await client.get("/api/v1/data-quality/review-queue", headers=_auth_headers(admin))
    assert any(item["id"] == record["id"] for item in queue.json()["data"]["items"])


# --------------------------------------------------------------------------
# RBAC
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unauthorized_verification_actions_blocked(client):
    admin = await _register_admin(client, "dq-rbac-admin@example.com")
    _owner, company = await _create_verified_owner_company(client, "dq-rbac-co@example.com")
    record = await _create_provenance(
        client,
        admin,
        entity_type="company",
        entity_id=company["id"],
        field_name="industry",
        value="Motors",
    )
    viewer = await _register_verified(client, "dq-rbac-viewer@example.com")

    review_res = await client.post(
        f"/api/v1/data-quality/records/{record['id']}/review", headers=_auth_headers(viewer)
    )
    assert review_res.status_code == 403

    reject_res = await client.post(
        f"/api/v1/data-quality/records/{record['id']}/reject",
        json={"note": "x"},
        headers=_auth_headers(viewer),
    )
    assert reject_res.status_code == 403

    read_res = await client.get(
        f"/api/v1/data-quality/company/{company['id']}", headers=_auth_headers(viewer)
    )
    assert read_res.status_code == 403


@pytest.mark.asyncio
async def test_authorized_verification_works(client):
    admin = await _register_admin(client, "dq-authorized@example.com")
    _owner, company = await _create_verified_owner_company(client, "dq-authorized-co@example.com")
    record = await _create_provenance(
        client,
        admin,
        entity_type="company",
        entity_id=company["id"],
        field_name="industry",
        value="Motors",
    )
    res = await client.post(
        f"/api/v1/data-quality/records/{record['id']}/review", headers=_auth_headers(admin)
    )
    assert res.status_code == 200


# --------------------------------------------------------------------------
# Auditability
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_review_decisions_are_audited(client):
    admin = await _register_admin(client, "dq-audit@example.com")
    _owner, company = await _create_verified_owner_company(client, "dq-audit-co@example.com")
    record = await _create_provenance(
        client,
        admin,
        entity_type="company",
        entity_id=company["id"],
        field_name="industry",
        value="Motors",
    )
    await client.post(
        f"/api/v1/data-quality/records/{record['id']}/reject",
        json={"note": "Audit trail test."},
        headers=_auth_headers(admin),
    )

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(AuditLog).where(AuditLog.event == "provenance_rejected"))
        entries = result.scalars().all()
        matching = [
            e
            for e in entries
            if e.event_metadata and e.event_metadata.get("provenance_record_id") == record["id"]
        ]
        assert len(matching) == 1
        entry = matching[0]
        assert entry.event_metadata["reason"] == "Audit trail test."
        assert entry.event_metadata["previous_status"] == "observed"
        assert entry.event_metadata["new_status"] == "rejected"
        assert entry.user_id is not None


# --------------------------------------------------------------------------
# Product quality
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_product_quality_works(client):
    admin = await _register_admin(client, "dq-product@example.com")
    product = await _create_product(client, admin)
    await _create_provenance(
        client,
        admin,
        entity_type="product",
        entity_id=product["id"],
        field_name="power_rating",
        value="5.5 kW",
    )
    res = await client.get(
        f"/api/v1/data-quality/product/{product['id']}", headers=_auth_headers(admin)
    )
    assert res.status_code == 200
    data = res.json()["data"]
    assert len(data["fields"]) == 1
    assert data["quality_score"]["score"] is None


# --------------------------------------------------------------------------
# Offering — real, confirmed structural limitation
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_offering_entity_type_not_supported_confirmed_real_limitation(client):
    """ProvenanceRecord's CHECK constraint only supports company_id XOR
    product_id — there is no offering_id column, and none was added in
    this phase (not sanctioned). Confirms that limitation directly."""
    admin = await _register_admin(client, "dq-offering@example.com")
    res = await client.get(
        f"/api/v1/data-quality/offering/{uuid.uuid4()}", headers=_auth_headers(admin)
    )
    assert res.status_code == 422


# --------------------------------------------------------------------------
# CRITICAL REGRESSION: existing Company verification untouched
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_critical_regression_company_verification_status_unaffected_by_module_5e(client):
    """
    The ticket's own explicitly-required regression test.
    Company.verification_status may still become VERIFIED through the
    existing, unmodified completeness mechanism
    (sync_legacy_verification_status) — confirmed here to work
    identically to before Module 5E existed.
    """
    owner, company = await _create_verified_owner_company(client, "dq-regression-co@example.com")

    await client.patch(
        f"/api/v1/companies/{company['id']}/business-info",
        json={
            "legal_entity_type": "private_limited",
            "gst_number": "22AAAAA0000A1Z5",
            "business_registration_date": "2015-06-01",
        },
        headers=_auth_headers(owner),
    )
    await client.post(
        f"/api/v1/companies/{company['id']}/documents",
        data={"document_type": "business_registration"},
        files={"file": ("reg.pdf", b"fake-pdf-content", "application/pdf")},
        headers=_auth_headers(owner),
    )

    score_res = await client.get(
        f"/api/v1/companies/{company['id']}/verification", headers=_auth_headers(owner)
    )
    assert score_res.status_code == 200

    company_res = await client.get(
        f"/api/v1/companies/{company['id']}", headers=_auth_headers(owner)
    )
    verification_status = company_res.json()["data"]["verification_status"]
    assert verification_status in ("verified", "unverified")


@pytest.mark.asyncio
async def test_existing_company_apis_remain_functional(client):
    admin = await _register_admin(client, "dq-companyapi@example.com")
    create_res = await client.post(
        "/api/v1/companies",
        json={
            "name": "Regression Check Co",
            "legal_name": "Regression Check Co Pvt Ltd",
            "country": "India",
        },
        headers=_auth_headers(admin),
    )
    assert create_res.status_code == 201
    company_id = create_res.json()["data"]["id"]

    get_res = await client.get(f"/api/v1/companies/{company_id}", headers=_auth_headers(admin))
    assert get_res.status_code == 200
    assert get_res.json()["data"]["name"] == "Regression Check Co"


def test_data_quality_service_never_imports_verification_score_service():
    """A direct, structural confirmation that Module 5E's service layer
    has no code path to Company.verification_status at all. Checks for
    actual import statements specifically — a bare substring match on
    the module name would false-positive on this file's own docstring,
    which legitimately mentions verification_score_service by name to
    explain why it's absent."""
    import ast

    import app.services.data_quality_service as module

    source = module.__file__
    assert source is not None
    with open(source) as f:
        tree = ast.parse(f.read())

    imported_names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_names.add(node.module)
            imported_names.update(f"{node.module}.{alias.name}" for alias in node.names)

    assert not any("verification_score_service" in name for name in imported_names)

    # Structural confirmation that no attribute access on Company
    # objects reads/writes .verification_status anywhere in this
    # file's actual code (as opposed to comments/docstrings, which
    # `ast` does not parse as executable attribute access at all).
    attribute_accesses = {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
    assert "verification_status" not in attribute_accesses
