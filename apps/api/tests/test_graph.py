"""
Module 5F tests — Industrial Knowledge Graph. Covers Factory/Capability
creation, relationship creation/verification/rejection, duplicate
prevention, manual conflict flagging, the unified query layer
(Offering-derived edges + graph_relationships), RBAC, and — the
ticket's own explicitly-required critical regression tests — that
Modules 5A-5E's existing behavior is completely unaffected.
"""

import uuid

import pytest
from sqlalchemy import select

from app.db.session import AsyncSessionLocal
from app.models.company import Company
from tests.test_acquisition import _register_admin
from tests.test_companies import _auth_headers, _company_payload, _register_verified


async def _create_company(client, owner, **overrides) -> dict:
    payload = {**_company_payload("Graph Test Co"), **overrides}
    res = await client.post("/api/v1/companies", json=payload, headers=_auth_headers(owner))
    assert res.status_code == 201, res.text
    return res.json()["data"]


async def _create_factory(client, admin, company_id: str, **overrides) -> dict:
    payload = {"company_id": company_id, "name": "Test Plant", "country": "India", **overrides}
    res = await client.post("/api/v1/graph/factories", json=payload, headers=_auth_headers(admin))
    assert res.status_code == 201, res.text
    return res.json()["data"]


async def _create_capability(client, admin, name: str) -> dict:
    res = await client.post(
        "/api/v1/graph/capabilities", json={"name": name}, headers=_auth_headers(admin)
    )
    assert res.status_code == 201, res.text
    return res.json()["data"]


async def _create_relationship(client, admin, **payload) -> dict:
    res = await client.post(
        "/api/v1/graph/relationships", json=payload, headers=_auth_headers(admin)
    )
    assert res.status_code == 201, res.text
    return res.json()["data"]


# --------------------------------------------------------------------------
# Factory
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_factory_creation_requires_real_company(client):
    admin = await _register_admin(client, "graph-factory-nocompany@example.com")
    res = await client.post(
        "/api/v1/graph/factories",
        json={"company_id": str(uuid.uuid4()), "name": "Ghost Plant"},
        headers=_auth_headers(admin),
    )
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_company_to_factory_relationship(client):
    admin = await _register_admin(client, "graph-cf@example.com")
    company = await _create_company(client, admin, name="CF Co")
    factory = await _create_factory(client, admin, company["id"], city="Pune")
    assert factory["company_id"] == company["id"]
    assert factory["city"] == "Pune"

    factories = await client.get(
        f"/api/v1/graph/companies/{company['id']}/factories", headers=_auth_headers(admin)
    )
    assert len(factories.json()["data"]) == 1


@pytest.mark.asyncio
async def test_factory_to_location_is_distinct_from_company_registered_address(client):
    """Architecture Section 9's own rule: factory location must not be
    confused with the company's registered address."""
    admin = await _register_admin(client, "graph-factloc@example.com")
    company = await _create_company(
        client, admin, name="FactLoc Co", city="Mumbai", state="Maharashtra"
    )
    factory = await _create_factory(client, admin, company["id"], city="Pune", state="Maharashtra")
    assert company["city"] == "Mumbai"
    assert factory["city"] == "Pune"  # genuinely different, both real


# --------------------------------------------------------------------------
# Capability
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_capability_creation_is_idempotent_on_name(client):
    admin = await _register_admin(client, "graph-capidem@example.com")
    first = await _create_capability(client, admin, "Forging")
    second = await _create_capability(client, admin, "Forging")
    assert first["id"] == second["id"]


@pytest.mark.asyncio
async def test_company_to_capability_relationship(client):
    admin = await _register_admin(client, "graph-cc@example.com")
    company = await _create_company(client, admin, name="CC Co")
    capability = await _create_capability(client, admin, "Casting")
    relationship = await _create_relationship(
        client,
        admin,
        company_subject_id=company["id"],
        relationship_type="has_capability",
        object_type="capability",
        capability_object_id=capability["id"],
    )
    assert relationship["status"] == "observed"


# --------------------------------------------------------------------------
# Capability -> Company.capabilities sync (Module 8C)
# --------------------------------------------------------------------------


async def _sync_capabilities(client, admin, company_id: str):
    return await client.post(
        f"/api/v1/graph/companies/{company_id}/sync-capabilities",
        headers=_auth_headers(admin),
    )


@pytest.mark.asyncio
async def test_capability_sync_uses_only_verified_relationships(client):
    admin = await _register_admin(client, "graph-capsync-verified@example.com")
    company = await _create_company(client, admin, name="CapSync Verified Co")
    verified_cap = await _create_capability(client, admin, "Verified Welding")
    observed_cap = await _create_capability(client, admin, "Observed Welding")

    verified_rel = await _create_relationship(
        client,
        admin,
        company_subject_id=company["id"],
        relationship_type="has_capability",
        object_type="capability",
        capability_object_id=verified_cap["id"],
    )
    await client.post(
        f"/api/v1/graph/relationships/{verified_rel['id']}/verify", headers=_auth_headers(admin)
    )
    await _create_relationship(
        client,
        admin,
        company_subject_id=company["id"],
        relationship_type="has_capability",
        object_type="capability",
        capability_object_id=observed_cap["id"],
    )  # deliberately left at observed — never verified

    res = await _sync_capabilities(client, admin, company["id"])
    assert res.status_code == 200, res.text
    body = res.json()["data"]
    assert body["added"] == ["Verified Welding"]
    assert "Verified Welding" in body["capabilities"]
    assert "Observed Welding" not in body["capabilities"]


@pytest.mark.asyncio
async def test_capability_sync_ignores_observed_relationships_entirely(client):
    """A company with ONLY an observed (never verified) relationship
    syncs to a genuinely empty result — not merely 'excludes the
    observed one from a mixed set' (covered above), a true
    empty-verified-input case."""
    admin = await _register_admin(client, "graph-capsync-observed-only@example.com")
    company = await _create_company(client, admin, name="CapSync Observed Only Co")
    capability = await _create_capability(client, admin, "Only Observed Capability")
    await _create_relationship(
        client,
        admin,
        company_subject_id=company["id"],
        relationship_type="has_capability",
        object_type="capability",
        capability_object_id=capability["id"],
    )

    res = await _sync_capabilities(client, admin, company["id"])
    assert res.status_code == 200, res.text
    body = res.json()["data"]
    assert body["added"] == []
    assert not body["capabilities"]


@pytest.mark.asyncio
async def test_capability_sync_is_idempotent(client):
    admin = await _register_admin(client, "graph-capsync-idem@example.com")
    company = await _create_company(client, admin, name="CapSync Idempotent Co")
    capability = await _create_capability(client, admin, "Idempotent Milling")
    rel = await _create_relationship(
        client,
        admin,
        company_subject_id=company["id"],
        relationship_type="has_capability",
        object_type="capability",
        capability_object_id=capability["id"],
    )
    await client.post(
        f"/api/v1/graph/relationships/{rel['id']}/verify", headers=_auth_headers(admin)
    )

    first = await _sync_capabilities(client, admin, company["id"])
    assert first.status_code == 200, first.text
    assert first.json()["data"]["added"] == ["Idempotent Milling"]

    second = await _sync_capabilities(client, admin, company["id"])
    assert second.status_code == 200, second.text
    assert second.json()["data"]["added"] == []  # true no-op, nothing new to add
    assert second.json()["data"]["capabilities"] == ["Idempotent Milling"]  # not duplicated


@pytest.mark.asyncio
async def test_capability_sync_preserves_manually_entered_capabilities(client):
    admin = await _register_admin(client, "graph-capsync-preserve@example.com")
    company = await _create_company(client, admin, name="CapSync Preserve Co")

    # Simulate a manually entered capability with no backing graph
    # relationship at all — set directly via the DB, matching this
    # file's own established pattern for direct-DB test setup (e.g.
    # tests/test_acquisition.py's _register_admin sets user.role
    # directly, since no API surface exists for the thing under test).
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Company).where(Company.id == uuid.UUID(company["id"])))
        db_company = result.scalar_one()
        db_company.capabilities = ["Manually Typed Capability"]
        await db.commit()

    capability = await _create_capability(client, admin, "Graph Verified Capability")
    rel = await _create_relationship(
        client,
        admin,
        company_subject_id=company["id"],
        relationship_type="has_capability",
        object_type="capability",
        capability_object_id=capability["id"],
    )
    await client.post(
        f"/api/v1/graph/relationships/{rel['id']}/verify", headers=_auth_headers(admin)
    )

    res = await _sync_capabilities(client, admin, company["id"])
    assert res.status_code == 200, res.text
    body = res.json()["data"]
    assert body["added"] == ["Graph Verified Capability"]
    assert body["capabilities"] == ["Manually Typed Capability", "Graph Verified Capability"]


@pytest.mark.asyncio
async def test_capability_sync_never_modifies_company_status_or_verification_status(client):
    admin = await _register_admin(client, "graph-capsync-status@example.com")
    company = await _create_company(client, admin, name="CapSync Status Co")
    capability = await _create_capability(client, admin, "Status-Neutral Capability")
    rel = await _create_relationship(
        client,
        admin,
        company_subject_id=company["id"],
        relationship_type="has_capability",
        object_type="capability",
        capability_object_id=capability["id"],
    )
    await client.post(
        f"/api/v1/graph/relationships/{rel['id']}/verify", headers=_auth_headers(admin)
    )

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Company).where(Company.id == uuid.UUID(company["id"])))
        db_company = result.scalar_one()
        before_status = db_company.status.value
        before_verification_status = db_company.verification_status.value

    res = await _sync_capabilities(client, admin, company["id"])
    assert res.status_code == 200, res.text
    assert res.json()["data"]["added"] == ["Status-Neutral Capability"]

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Company).where(Company.id == uuid.UUID(company["id"])))
        db_company = result.scalar_one()
        assert db_company.status.value == before_status
        assert db_company.verification_status.value == before_verification_status
        assert db_company.verification_status.value == "unverified"


@pytest.mark.asyncio
async def test_capability_sync_requires_admin(client):
    admin = await _register_admin(client, "graph-capsync-rbac-admin@example.com")
    company = await _create_company(client, admin, name="CapSync RBAC Co")
    viewer = await _register_verified(client, "graph-capsync-rbac-viewer@example.com")

    res = await _sync_capabilities(client, viewer, company["id"])
    assert res.status_code == 403


@pytest.mark.asyncio
async def test_capability_sync_requires_real_company(client):
    admin = await _register_admin(client, "graph-capsync-nocompany@example.com")
    res = await _sync_capabilities(client, admin, str(uuid.uuid4()))
    assert res.status_code == 404


# --------------------------------------------------------------------------
# Product / Offering separation (architecture Section 3, unchanged)
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_product_offering_separation_preserved(client):
    """Offering carries commercial facts; Product never does — the
    graph reuses Offering directly rather than duplicating it."""
    admin = await _register_admin(client, "graph-po@example.com")
    company = await _create_company(client, admin, name="PO Co")
    cat_res = await client.post(
        "/api/v1/product-categories",
        json={"name": f"Cat {uuid.uuid4().hex[:8]}"},
        headers=_auth_headers(admin),
    )
    category_id = cat_res.json()["data"]["id"]
    prod_res = await client.post(
        "/api/v1/products",
        json={"name": "Hydraulic Cylinder", "category_id": category_id},
        headers=_auth_headers(admin),
    )
    product = prod_res.json()["data"]
    offering_res = await client.post(
        f"/api/v1/companies/{company['id']}/offerings",
        json={
            "product_id": product["id"],
            "role": "manufacturer",
            "moq": "100",
            "lead_time": "30 days",
        },
        headers=_auth_headers(admin),
    )
    assert offering_res.status_code == 201, offering_res.text

    view = await client.get(
        f"/api/v1/graph/companies/{company['id']}/view", headers=_auth_headers(admin)
    )
    offering_edges = view.json()["data"]["offering_edges"]
    assert len(offering_edges) == 1
    assert offering_edges[0]["relationship_type"] == "manufactures"
    assert offering_edges[0]["moq"] == "100"  # commercial fact lives on the Offering edge

    product_check = await client.get(f"/api/v1/products/{product['id']}")
    assert "moq" not in product_check.json()["data"]  # never moved onto Product


@pytest.mark.asyncio
async def test_company_offering_product_category_traversal(client):
    admin = await _register_admin(client, "graph-traverse@example.com")
    company = await _create_company(client, admin, name="Traverse Co")
    cat_res = await client.post(
        "/api/v1/product-categories",
        json={"name": f"Cat {uuid.uuid4().hex[:8]}"},
        headers=_auth_headers(admin),
    )
    category = cat_res.json()["data"]
    prod_res = await client.post(
        "/api/v1/products",
        json={"name": "Traverse Product", "category_id": category["id"]},
        headers=_auth_headers(admin),
    )
    product = prod_res.json()["data"]
    await client.post(
        f"/api/v1/companies/{company['id']}/offerings",
        json={"product_id": product["id"], "role": "manufacturer"},
        headers=_auth_headers(admin),
    )

    traversal = await client.get(
        f"/api/v1/graph/query/companies/{company['id']}/offerings-by-category",
        headers=_auth_headers(admin),
    )
    assert traversal.status_code == 200
    rows = traversal.json()["data"]
    assert len(rows) == 1
    assert rows[0]["product_name"] == "Traverse Product"
    assert rows[0]["category_name"] == category["name"]


# --------------------------------------------------------------------------
# Duplicate prevention
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_duplicate_relationship_prevention(client):
    admin = await _register_admin(client, "graph-dup@example.com")
    company = await _create_company(client, admin, name="Dup Co")
    factory = await _create_factory(client, admin, company["id"])

    first = await _create_relationship(
        client,
        admin,
        company_subject_id=company["id"],
        relationship_type="owns",
        object_type="factory",
        factory_object_id=factory["id"],
    )
    second = await _create_relationship(
        client,
        admin,
        company_subject_id=company["id"],
        relationship_type="owns",
        object_type="factory",
        factory_object_id=factory["id"],
    )
    assert first["id"] == second["id"]  # idempotent, not a duplicate row


# --------------------------------------------------------------------------
# Relationship verification (Module 5E status vocabulary, reused)
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_relationship_starts_observed_never_auto_verified(client):
    admin = await _register_admin(client, "graph-observed@example.com")
    company = await _create_company(client, admin, name="Observed Co")
    factory = await _create_factory(client, admin, company["id"])
    relationship = await _create_relationship(
        client,
        admin,
        company_subject_id=company["id"],
        relationship_type="owns",
        object_type="factory",
        factory_object_id=factory["id"],
    )
    assert relationship["status"] == "observed"
    assert relationship["verified_by"] is None


@pytest.mark.asyncio
async def test_cannot_create_relationship_as_verified_directly(client):
    admin = await _register_admin(client, "graph-noverify@example.com")
    company = await _create_company(client, admin, name="No Verify Co")
    factory = await _create_factory(client, admin, company["id"])
    res = await client.post(
        "/api/v1/graph/relationships",
        json={
            "company_subject_id": company["id"],
            "relationship_type": "owns",
            "object_type": "factory",
            "factory_object_id": factory["id"],
            "status": "verified",
        },
        headers=_auth_headers(admin),
    )
    assert res.status_code == 422


@pytest.mark.asyncio
async def test_relationship_verify_and_reverify_rejected(client):
    admin = await _register_admin(client, "graph-verify@example.com")
    company = await _create_company(client, admin, name="Verify Co")
    factory = await _create_factory(client, admin, company["id"])
    relationship = await _create_relationship(
        client,
        admin,
        company_subject_id=company["id"],
        relationship_type="owns",
        object_type="factory",
        factory_object_id=factory["id"],
    )
    verify_res = await client.post(
        f"/api/v1/graph/relationships/{relationship['id']}/verify", headers=_auth_headers(admin)
    )
    assert verify_res.status_code == 200
    assert verify_res.json()["data"]["status"] == "verified"
    assert verify_res.json()["data"]["verified_by"] is not None

    reverify_res = await client.post(
        f"/api/v1/graph/relationships/{relationship['id']}/verify", headers=_auth_headers(admin)
    )
    assert reverify_res.status_code == 409


@pytest.mark.asyncio
async def test_relationship_reject_requires_note(client):
    admin = await _register_admin(client, "graph-reject@example.com")
    company = await _create_company(client, admin, name="Reject Co")
    factory = await _create_factory(client, admin, company["id"])
    relationship = await _create_relationship(
        client,
        admin,
        company_subject_id=company["id"],
        relationship_type="owns",
        object_type="factory",
        factory_object_id=factory["id"],
    )
    res = await client.post(
        f"/api/v1/graph/relationships/{relationship['id']}/reject",
        json={"note": "Could not corroborate ownership."},
        headers=_auth_headers(admin),
    )
    assert res.status_code == 200
    assert res.json()["data"]["status"] == "rejected"
    assert res.json()["data"]["review_note"] == "Could not corroborate ownership."


@pytest.mark.asyncio
async def test_ai_generated_suggestion_never_automatically_verified(client):
    """Architecture Section 22's rule: AI extraction produces at most
    EXTRACTED status, never a shortcut to VERIFIED."""
    admin = await _register_admin(client, "graph-noai@example.com")
    company = await _create_company(client, admin, name="No AI Co")
    factory = await _create_factory(client, admin, company["id"])
    relationship = await _create_relationship(
        client,
        admin,
        company_subject_id=company["id"],
        relationship_type="owns",
        object_type="factory",
        factory_object_id=factory["id"],
        status="extracted",
        confidence=0.95,  # even a high-confidence AI-style extraction
    )
    assert relationship["status"] == "extracted"  # not verified, regardless of confidence


# --------------------------------------------------------------------------
# Conflict — manual flagging, honestly scoped
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_manual_conflict_flagging(client):
    admin = await _register_admin(client, "graph-conflict@example.com")
    company = await _create_company(client, admin, name="Conflict Co")
    cap_a = await _create_capability(client, admin, "Sheet metal fabrication")
    cap_b = await _create_capability(client, admin, "Heat treatment")
    rel_a = await _create_relationship(
        client,
        admin,
        company_subject_id=company["id"],
        relationship_type="has_capability",
        object_type="capability",
        capability_object_id=cap_a["id"],
    )
    rel_b = await _create_relationship(
        client,
        admin,
        company_subject_id=company["id"],
        relationship_type="has_capability",
        object_type="capability",
        capability_object_id=cap_b["id"],
    )
    res = await client.post(
        f"/api/v1/graph/relationships/flag-conflict?relationship_a_id={rel_a['id']}&relationship_b_id={rel_b['id']}",
        headers=_auth_headers(admin),
    )
    assert res.status_code == 200
    conflict_id = res.json()["data"]["conflict_id"]

    rel_a_check = await client.get(
        f"/api/v1/graph/relationships/{rel_a['id']}", headers=_auth_headers(admin)
    )
    rel_b_check = await client.get(
        f"/api/v1/graph/relationships/{rel_b['id']}", headers=_auth_headers(admin)
    )
    assert rel_a_check.json()["data"]["conflict_id"] == conflict_id
    assert rel_b_check.json()["data"]["conflict_id"] == conflict_id

    conflicts = await client.get(
        "/api/v1/provenance/conflicts?status=open", headers=_auth_headers(admin)
    )
    assert any(c["id"] == conflict_id for c in conflicts.json()["data"]["items"])


# --------------------------------------------------------------------------
# Graph queries (architecture Section 19)
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_find_cnc_manufacturers_in_pune(client):
    admin = await _register_admin(client, "graph-q1@example.com")
    company = await _create_company(client, admin, name="Q1 Co", city="Pune")
    other_company = await _create_company(client, admin, name="Q1 Other Co", city="Mumbai")
    capability = await _create_capability(client, admin, f"CNC machining {uuid.uuid4().hex[:8]}")

    rel = await _create_relationship(
        client,
        admin,
        company_subject_id=company["id"],
        relationship_type="has_capability",
        object_type="capability",
        capability_object_id=capability["id"],
    )
    await client.post(
        f"/api/v1/graph/relationships/{rel['id']}/verify", headers=_auth_headers(admin)
    )
    await _create_relationship(
        client,
        admin,
        company_subject_id=other_company["id"],
        relationship_type="has_capability",
        object_type="capability",
        capability_object_id=capability["id"],
    )

    res = await client.get(
        f"/api/v1/graph/query/companies-by-capability/{capability['id']}?city=Pune&verified_only=true",
        headers=_auth_headers(admin),
    )
    ids = res.json()["data"]
    assert company["id"] in ids
    assert other_company["id"] not in ids  # different city, correctly excluded


@pytest.mark.asyncio
async def test_find_manufacturers_of_product(client):
    admin = await _register_admin(client, "graph-q2@example.com")
    company = await _create_company(client, admin, name="Q2 Manufacturer Co")
    cat_res = await client.post(
        "/api/v1/product-categories",
        json={"name": f"Cat {uuid.uuid4().hex[:8]}"},
        headers=_auth_headers(admin),
    )
    prod_res = await client.post(
        "/api/v1/products",
        json={"name": "Q2 Product", "category_id": cat_res.json()["data"]["id"]},
        headers=_auth_headers(admin),
    )
    product = prod_res.json()["data"]
    await client.post(
        f"/api/v1/companies/{company['id']}/offerings",
        json={"product_id": product["id"], "role": "manufacturer"},
        headers=_auth_headers(admin),
    )

    res = await client.get(
        f"/api/v1/graph/query/manufacturers-of-product/{product['id']}",
        headers=_auth_headers(admin),
    )
    assert company["id"] in res.json()["data"]


@pytest.mark.asyncio
async def test_find_distributors_of_product_in_delhi(client):
    admin = await _register_admin(client, "graph-q3@example.com")
    company = await _create_company(client, admin, name="Q3 Distributor Co")
    cat_res = await client.post(
        "/api/v1/product-categories",
        json={"name": f"Cat {uuid.uuid4().hex[:8]}"},
        headers=_auth_headers(admin),
    )
    prod_res = await client.post(
        "/api/v1/products",
        json={"name": "Q3 Product", "category_id": cat_res.json()["data"]["id"]},
        headers=_auth_headers(admin),
    )
    product = prod_res.json()["data"]
    await client.post(
        f"/api/v1/companies/{company['id']}/offerings",
        json={"product_id": product["id"], "role": "distributor", "country": "Delhi"},
        headers=_auth_headers(admin),
    )

    res = await client.get(
        f"/api/v1/graph/query/distributors-of-product/{product['id']}?country=Delhi",
        headers=_auth_headers(admin),
    )
    assert company["id"] in res.json()["data"]


# --------------------------------------------------------------------------
# RBAC
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unauthorized_graph_mutation_blocked(client):
    admin = await _register_admin(client, "graph-rbac-admin@example.com")
    company = await _create_company(client, admin, name="RBAC Co")
    viewer = await _register_verified(client, "graph-rbac-viewer@example.com")

    factory_res = await client.post(
        "/api/v1/graph/factories",
        json={"company_id": company["id"], "name": "Unauthorized Plant"},
        headers=_auth_headers(viewer),
    )
    assert factory_res.status_code == 403

    cap_res = await client.post(
        "/api/v1/graph/capabilities",
        json={"name": "Unauthorized Cap"},
        headers=_auth_headers(viewer),
    )
    assert cap_res.status_code == 403


@pytest.mark.asyncio
async def test_graph_mutation_requires_auth(client):
    res = await client.post(
        "/api/v1/graph/factories", json={"company_id": str(uuid.uuid4()), "name": "X"}
    )
    assert res.status_code == 401


# --------------------------------------------------------------------------
# CRITICAL REGRESSION TESTS — Modules 5A-5E unaffected
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_regression_existing_field_provenance_still_works(client):
    """Module 5A's field-level ProvenanceRecord workflow, completely
    unaffected by graph_relationships existing alongside it."""
    admin = await _register_admin(client, "graph-reg-5a@example.com")
    company = await _create_company(client, admin, name="Reg 5A Co")
    source_res = await client.post(
        "/api/v1/sources",
        json={
            "name": "Reg Source",
            "source_class": "public_government",
            "collection_method": "api",
        },
        headers=_auth_headers(admin),
    )
    source_id = source_res.json()["data"]["id"]
    obs_res = await client.post(
        f"/api/v1/sources/{source_id}/observations",
        json={
            "source_id": source_id,
            "raw_content": {"industry": "Motors"},
            "content_hash": uuid.uuid4().hex,
            "collection_method_used": "api",
            "collected_at": "2026-08-09T00:00:00Z",
        },
        headers=_auth_headers(admin),
    )
    obs_id = obs_res.json()["data"]["id"]
    prov_res = await client.post(
        "/api/v1/provenance/records",
        json={
            "entity_type": "company",
            "company_id": company["id"],
            "field_name": "industry",
            "raw_observation_id": obs_id,
            "value_observed": "Motors",
            "extraction_method": "manual",
            "confidence": 0.8,
        },
        headers=_auth_headers(admin),
    )
    assert prov_res.status_code == 201
    assert prov_res.json()["data"]["status"] == "observed"


@pytest.mark.asyncio
async def test_regression_existing_data_quality_still_works(client):
    """Module 5E's quality report, completely unaffected."""
    admin = await _register_admin(client, "graph-reg-5e@example.com")
    company = await _create_company(client, admin, name="Reg 5E Co")
    res = await client.get(
        f"/api/v1/data-quality/company/{company['id']}", headers=_auth_headers(admin)
    )
    assert res.status_code == 200
    assert "quality_score" in res.json()["data"]


@pytest.mark.asyncio
async def test_regression_existing_company_apis_unchanged(client):
    admin = await _register_admin(client, "graph-reg-company@example.com")
    company = await _create_company(client, admin, name="Reg Company Co")
    res = await client.get(f"/api/v1/companies/{company['id']}", headers=_auth_headers(admin))
    assert res.status_code == 200
    assert res.json()["data"]["name"] == "Reg Company Co"


@pytest.mark.asyncio
async def test_regression_existing_offering_apis_unchanged(client):
    admin = await _register_admin(client, "graph-reg-offering@example.com")
    company = await _create_company(client, admin, name="Reg Offering Co")
    cat_res = await client.post(
        "/api/v1/product-categories",
        json={"name": f"Cat {uuid.uuid4().hex[:8]}"},
        headers=_auth_headers(admin),
    )
    prod_res = await client.post(
        "/api/v1/products",
        json={"name": "Reg Product", "category_id": cat_res.json()["data"]["id"]},
        headers=_auth_headers(admin),
    )
    offering_res = await client.post(
        f"/api/v1/companies/{company['id']}/offerings",
        json={"product_id": prod_res.json()["data"]["id"], "role": "manufacturer"},
        headers=_auth_headers(admin),
    )
    assert offering_res.status_code == 201
    assert offering_res.json()["data"]["role"] == "manufacturer"


@pytest.mark.asyncio
async def test_regression_entity_resolution_unaffected(client):
    """Module 5D's Company-only entity resolution continues to work,
    completely independent of the new Company-Factory/Company-Capability
    relationship types this module adds."""
    from tests.test_mca_pilot import _create_mca_source, _real_shaped_record

    admin = await _register_admin(client, "graph-reg-5d@example.com")
    source = await _create_mca_source(client, admin)
    import app.collectors.mca_data_gov_in_adapter as adapter_module
    from tests.test_mca_pilot import _mock_response

    record = _real_shaped_record("U99999MH2015PTC099999", "Reg 5D Co")
    original_get = adapter_module.httpx.get
    adapter_module.httpx.get = lambda *a, **k: _mock_response([record])  # type: ignore[method-assign]
    try:
        job_res = await client.post(
            "/api/v1/acquisition/jobs",
            json={
                "source_id": source["id"],
                "collector_type": "mca_data_gov_in",
                "requested_scope": {
                    "api_key": "test-key",
                    "resource_id": "test-resource",
                    "limit": 25,
                },
            },
            headers=_auth_headers(admin),
        )
    finally:
        adapter_module.httpx.get = original_get
    assert job_res.json()["data"]["status"] == "succeeded"

    events = await client.get(
        f"/api/v1/acquisition/jobs/{job_res.json()['data']['id']}/events",
        headers=_auth_headers(admin),
    )
    obs_id = events.json()["data"]["items"][0]["raw_observation_id"]
    candidate_res = await client.post(
        "/api/v1/entity-resolution/candidates",
        json={"raw_observation_id": obs_id},
        headers=_auth_headers(admin),
    )
    assert candidate_res.status_code == 201
    assert candidate_res.json()["data"]["resolution_state"] == "new"


def test_regression_provenance_records_schema_unchanged():
    """Structural confirmation, not just behavioral: provenance_records
    has exactly the columns Module 5E's own migration (0009) left it
    with — Module 5F added zero columns to this table."""
    import inspect

    from app.models.provenance_record import ProvenanceRecord

    columns = {c.name for c in ProvenanceRecord.__table__.columns}
    expected = {
        "id",
        "entity_type",
        "company_id",
        "product_id",
        "field_name",
        "raw_observation_id",
        "value_observed",
        "extraction_method",
        "confidence",
        "status",
        "verified_by",
        "verified_at",
        "last_observed_at",
        "conflict_id",
        "created_at",
        "updated_at",
        "expires_at",
        "review_note",
        "verification_document_id",
    }
    assert columns == expected
    assert inspect.getsourcefile(ProvenanceRecord) is not None  # sanity: real, loadable model
