"""
Provenance & Source Registry tests — Module 5A. Covers the four new
entities (SourceRegistry, RawObservation, ProvenanceRecord,
DataConflict) and, most importantly, the architecture doc's Section 11
hard rule this module exists to enforce: OBSERVED/EXTRACTED/CLAIMED
information must never automatically become VERIFIED. Reuses
test_companies.py's established fixtures rather than duplicating them.
"""

import pytest

from tests.test_companies import _auth_headers, _company_payload, _register_verified


def _source_payload(name: str = "Test MCA Registry") -> dict:
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


async def _create_observation(
    client, owner, source_id: str, value: str, content_hash: str = "hash1"
) -> dict:
    res = await client.post(
        f"/api/v1/sources/{source_id}/observations",
        json={
            "source_id": source_id,
            "raw_content": {"value": value},
            "content_hash": content_hash,
            "collection_method_used": "api",
            "collected_at": "2026-08-08T00:00:00Z",
        },
        headers=_auth_headers(owner),
    )
    assert res.status_code == 201, res.text
    return res.json()["data"]


async def _create_verified_company(client, email: str, name: str) -> tuple[dict, dict]:
    owner = await _register_verified(client, email)
    res = await client.post(
        "/api/v1/companies", json=_company_payload(name), headers=_auth_headers(owner)
    )
    assert res.status_code == 201, res.text
    return owner, res.json()["data"]


def _provenance_payload(company_id: str, observation_id: str, value: str, **overrides) -> dict:
    return {
        "entity_type": "company",
        "company_id": company_id,
        "field_name": "legal_name",
        "raw_observation_id": observation_id,
        "value_observed": value,
        "extraction_method": "manual",
        "confidence": 0.8,
        **overrides,
    }


# --------------------------------------------------------------------------
# Source Registry
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_source_requires_auth(client):
    res = await client.post("/api/v1/sources", json=_source_payload())
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_create_and_list_source(client):
    owner = await _register_verified(client, "source-owner@example.com")
    source = await _create_source(client, owner, name="Company Website")
    assert source["source_class"] == "public_government"
    assert (
        source["collection_policy_status"] == "pending_legal_review"
    )  # honest default, never auto-allowed
    assert source["is_active"] is True

    list_res = await client.get("/api/v1/sources")
    assert list_res.status_code == 200
    names = [s["name"] for s in list_res.json()["data"]]
    assert "Company Website" in names


@pytest.mark.asyncio
async def test_update_source_collection_policy(client):
    owner = await _register_verified(client, "source-update@example.com")
    source = await _create_source(client, owner, name="Update Test Source")
    res = await client.patch(
        f"/api/v1/sources/{source['id']}",
        json={"collection_policy_status": "blocked"},
        headers=_auth_headers(owner),
    )
    assert res.status_code == 200
    assert res.json()["data"]["collection_policy_status"] == "blocked"


@pytest.mark.asyncio
async def test_get_nonexistent_source_404s(client):
    res = await client.get("/api/v1/sources/00000000-0000-0000-0000-000000000000")
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "SOURCE_NOT_FOUND"


# --------------------------------------------------------------------------
# Raw Observations — append-only
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_raw_observation(client):
    owner = await _register_verified(client, "obs-owner@example.com")
    source = await _create_source(client, owner, name="Obs Test Source")
    observation = await _create_observation(client, owner, source["id"], "some raw value")
    assert observation["raw_content"] == {"value": "some raw value"}
    assert observation["source_id"] == source["id"]


@pytest.mark.asyncio
async def test_raw_observation_source_id_mismatch_rejected(client):
    owner = await _register_verified(client, "obs-mismatch@example.com")
    source_a = await _create_source(client, owner, name="Source A")
    source_b = await _create_source(client, owner, name="Source B")
    res = await client.post(
        f"/api/v1/sources/{source_a['id']}/observations",
        json={
            "source_id": source_b["id"],  # deliberately mismatched vs. the URL path
            "raw_content": {"value": "x"},
            "content_hash": "h1",
            "collection_method_used": "api",
            "collected_at": "2026-08-08T00:00:00Z",
        },
        headers=_auth_headers(owner),
    )
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "SOURCE_MISMATCH"


@pytest.mark.asyncio
async def test_raw_observation_for_nonexistent_source_404s(client):
    owner = await _register_verified(client, "obs-nosource@example.com")
    fake_id = "00000000-0000-0000-0000-000000000000"
    res = await client.post(
        f"/api/v1/sources/{fake_id}/observations",
        json={
            "source_id": fake_id,
            "raw_content": {"value": "x"},
            "content_hash": "h1",
            "collection_method_used": "api",
            "collected_at": "2026-08-08T00:00:00Z",
        },
        headers=_auth_headers(owner),
    )
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "SOURCE_NOT_FOUND"


# --------------------------------------------------------------------------
# Provenance Records — the core OBSERVED/EXTRACTED/VERIFIED/CLAIMED rule
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_provenance_record_defaults_to_observed(client):
    owner = await _register_verified(client, "prov-default@example.com")
    _, company = await _create_verified_company(
        client, "prov-default-co@example.com", "Prov Default Co"
    )
    source = await _create_source(client, owner, name="Default Status Source")
    observation = await _create_observation(client, owner, source["id"], "Prov Default Co Ltd")

    res = await client.post(
        "/api/v1/provenance/records",
        json=_provenance_payload(company["id"], observation["id"], "Prov Default Co Ltd"),
        headers=_auth_headers(owner),
    )
    assert res.status_code == 201, res.text
    assert res.json()["data"]["status"] == "observed"
    assert res.json()["data"]["verified_by"] is None
    assert res.json()["data"]["verified_at"] is None


@pytest.mark.asyncio
async def test_cannot_create_provenance_record_as_verified_directly(client):
    """THE core rule: status=verified must be unreachable at creation,
    regardless of who's asking or how confident the caller claims to
    be."""
    owner = await _register_verified(client, "prov-noverify@example.com")
    _, company = await _create_verified_company(
        client, "prov-noverify-co@example.com", "No Verify Co"
    )
    source = await _create_source(client, owner, name="No Verify Source")
    observation = await _create_observation(client, owner, source["id"], "No Verify Co Ltd")

    res = await client.post(
        "/api/v1/provenance/records",
        json=_provenance_payload(
            company["id"], observation["id"], "No Verify Co Ltd", status="verified", confidence=1.0
        ),
        headers=_auth_headers(owner),
    )
    assert res.status_code == 422


@pytest.mark.asyncio
async def test_verify_provenance_record_requires_explicit_action(client):
    owner = await _register_verified(client, "prov-verify@example.com")
    _, company = await _create_verified_company(client, "prov-verify-co@example.com", "Verify Co")
    source = await _create_source(client, owner, name="Verify Source")
    observation = await _create_observation(client, owner, source["id"], "Verify Co Ltd")

    create_res = await client.post(
        "/api/v1/provenance/records",
        json=_provenance_payload(company["id"], observation["id"], "Verify Co Ltd"),
        headers=_auth_headers(owner),
    )
    record_id = create_res.json()["data"]["id"]
    assert create_res.json()["data"]["status"] == "observed"

    verify_res = await client.post(
        f"/api/v1/provenance/records/{record_id}/verify", headers=_auth_headers(owner)
    )
    assert verify_res.status_code == 200
    verified_data = verify_res.json()["data"]
    assert verified_data["status"] == "verified"
    assert verified_data["verified_by"] is not None
    assert verified_data["verified_at"] is not None


@pytest.mark.asyncio
async def test_verify_already_verified_record_conflicts(client):
    owner = await _register_verified(client, "prov-reverify@example.com")
    _, company = await _create_verified_company(
        client, "prov-reverify-co@example.com", "Reverify Co"
    )
    source = await _create_source(client, owner, name="Reverify Source")
    observation = await _create_observation(client, owner, source["id"], "Reverify Co Ltd")

    create_res = await client.post(
        "/api/v1/provenance/records",
        json=_provenance_payload(company["id"], observation["id"], "Reverify Co Ltd"),
        headers=_auth_headers(owner),
    )
    record_id = create_res.json()["data"]["id"]
    await client.post(
        f"/api/v1/provenance/records/{record_id}/verify", headers=_auth_headers(owner)
    )

    second_verify = await client.post(
        f"/api/v1/provenance/records/{record_id}/verify", headers=_auth_headers(owner)
    )
    assert second_verify.status_code == 409
    assert second_verify.json()["error"]["code"] == "ALREADY_VERIFIED"


@pytest.mark.asyncio
async def test_extracted_status_also_cannot_skip_to_verified_without_the_action(client):
    """Covers EXTRACTED specifically, not just the default OBSERVED
    case — the rule applies uniformly to both non-verified statuses."""
    owner = await _register_verified(client, "prov-extracted@example.com")
    _, company = await _create_verified_company(
        client, "prov-extracted-co@example.com", "Extracted Co"
    )
    source = await _create_source(client, owner, name="Extracted Source")
    observation = await _create_observation(client, owner, source["id"], "Extracted Co Ltd")

    res = await client.post(
        "/api/v1/provenance/records",
        json=_provenance_payload(
            company["id"],
            observation["id"],
            "Extracted Co Ltd",
            status="extracted",
            extraction_method="ai_assisted",
        ),
        headers=_auth_headers(owner),
    )
    assert res.status_code == 201
    assert res.json()["data"]["status"] == "extracted"
    assert res.json()["data"]["verified_by"] is None


@pytest.mark.asyncio
async def test_provenance_record_for_nonexistent_company_rejected(client):
    owner = await _register_verified(client, "prov-nocompany@example.com")
    source = await _create_source(client, owner, name="No Company Source")
    observation = await _create_observation(client, owner, source["id"], "X")

    res = await client.post(
        "/api/v1/provenance/records",
        json=_provenance_payload("00000000-0000-0000-0000-000000000000", observation["id"], "X"),
        headers=_auth_headers(owner),
    )
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "INVALID_PROVENANCE_RECORD"


@pytest.mark.asyncio
async def test_provenance_record_for_nonexistent_observation_404s(client):
    owner = await _register_verified(client, "prov-noobs@example.com")
    _, company = await _create_verified_company(client, "prov-noobs-co@example.com", "No Obs Co")

    res = await client.post(
        "/api/v1/provenance/records",
        json=_provenance_payload(company["id"], "00000000-0000-0000-0000-000000000000", "X"),
        headers=_auth_headers(owner),
    )
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "RAW_OBSERVATION_NOT_FOUND"


@pytest.mark.asyncio
async def test_lineage_view_returns_all_provenance_for_an_entity(client):
    owner = await _register_verified(client, "lineage-owner@example.com")
    _, company = await _create_verified_company(client, "lineage-co@example.com", "Lineage Co")
    source = await _create_source(client, owner, name="Lineage Source")

    obs1 = await _create_observation(
        client, owner, source["id"], "Lineage Co Ltd", content_hash="h1"
    )
    obs2 = await _create_observation(
        client, owner, source["id"], "Lineage Co Limited", content_hash="h2"
    )

    await client.post(
        "/api/v1/provenance/records",
        json=_provenance_payload(
            company["id"], obs1["id"], "Lineage Co Ltd", field_name="legal_name"
        ),
        headers=_auth_headers(owner),
    )
    await client.post(
        "/api/v1/provenance/records",
        json=_provenance_payload(company["id"], obs2["id"], "Lineage Co", field_name="name"),
        headers=_auth_headers(owner),
    )

    res = await client.get(f"/api/v1/provenance?entity_type=company&entity_id={company['id']}")
    assert res.status_code == 200
    assert res.json()["data"]["total"] == 2


# --------------------------------------------------------------------------
# Data Conflicts — detection and flagging, never auto-resolution
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_disagreeing_values_create_a_conflict(client):
    owner = await _register_verified(client, "conflict-owner@example.com")
    _, company = await _create_verified_company(client, "conflict-co@example.com", "Conflict Co")
    source = await _create_source(client, owner, name="Conflict Source")

    obs1 = await _create_observation(
        client, owner, source["id"], "Conflict Co Ltd", content_hash="c1"
    )
    obs2 = await _create_observation(
        client, owner, source["id"], "Conflict Co Limited", content_hash="c2"
    )

    first = await client.post(
        "/api/v1/provenance/records",
        json=_provenance_payload(company["id"], obs1["id"], "Conflict Co Ltd"),
        headers=_auth_headers(owner),
    )
    assert first.json()["data"]["conflict_id"] is None  # no conflict yet — nothing to disagree with

    second = await client.post(
        "/api/v1/provenance/records",
        json=_provenance_payload(company["id"], obs2["id"], "Conflict Co Limited"),
        headers=_auth_headers(owner),
    )
    conflict_id = second.json()["data"]["conflict_id"]
    assert conflict_id is not None

    conflicts_res = await client.get("/api/v1/provenance/conflicts?status=open")
    assert any(c["id"] == conflict_id for c in conflicts_res.json()["data"]["items"])


@pytest.mark.asyncio
async def test_agreeing_values_do_not_create_a_conflict(client):
    owner = await _register_verified(client, "noconflict-owner@example.com")
    _, company = await _create_verified_company(
        client, "noconflict-co@example.com", "No Conflict Co"
    )
    source = await _create_source(client, owner, name="No Conflict Source")

    obs1 = await _create_observation(
        client, owner, source["id"], "Same Value Ltd", content_hash="s1"
    )
    obs2 = await _create_observation(
        client, owner, source["id"], "Same Value Ltd", content_hash="s2"
    )

    await client.post(
        "/api/v1/provenance/records",
        json=_provenance_payload(company["id"], obs1["id"], "Same Value Ltd"),
        headers=_auth_headers(owner),
    )
    second = await client.post(
        "/api/v1/provenance/records",
        json=_provenance_payload(company["id"], obs2["id"], "Same Value Ltd"),
        headers=_auth_headers(owner),
    )
    assert second.json()["data"]["conflict_id"] is None


@pytest.mark.asyncio
async def test_conflict_against_an_already_verified_record_is_still_flagged(client):
    """The honesty guarantee: a new disagreeing observation must be
    flagged even against data that was previously verified — never
    silently ignored just because the existing record has higher
    status."""
    owner = await _register_verified(client, "conflict-verified@example.com")
    _, company = await _create_verified_company(
        client, "conflict-verified-co@example.com", "Conflict Verified Co"
    )
    source = await _create_source(client, owner, name="Conflict Verified Source")

    obs1 = await _create_observation(
        client, owner, source["id"], "Verified Value Ltd", content_hash="v1"
    )
    first = await client.post(
        "/api/v1/provenance/records",
        json=_provenance_payload(company["id"], obs1["id"], "Verified Value Ltd"),
        headers=_auth_headers(owner),
    )
    first_id = first.json()["data"]["id"]
    await client.post(f"/api/v1/provenance/records/{first_id}/verify", headers=_auth_headers(owner))

    obs2 = await _create_observation(
        client, owner, source["id"], "Disagreeing Value Ltd", content_hash="v2"
    )
    second = await client.post(
        "/api/v1/provenance/records",
        json=_provenance_payload(company["id"], obs2["id"], "Disagreeing Value Ltd"),
        headers=_auth_headers(owner),
    )
    conflict_id = second.json()["data"]["conflict_id"]
    assert conflict_id is not None

    first_record = await client.get(f"/api/v1/provenance/records/{first_id}")
    assert first_record.json()["data"]["conflict_id"] == conflict_id
    assert first_record.json()["data"]["status"] == "verified"  # unchanged by the conflict


@pytest.mark.asyncio
async def test_resolve_conflict_requires_a_note_and_does_not_touch_provenance_values(client):
    owner = await _register_verified(client, "resolve-owner@example.com")
    _, company = await _create_verified_company(client, "resolve-co@example.com", "Resolve Co")
    source = await _create_source(client, owner, name="Resolve Source")

    obs1 = await _create_observation(client, owner, source["id"], "Resolve Ltd", content_hash="r1")
    obs2 = await _create_observation(
        client, owner, source["id"], "Resolve Limited", content_hash="r2"
    )
    await client.post(
        "/api/v1/provenance/records",
        json=_provenance_payload(company["id"], obs1["id"], "Resolve Ltd"),
        headers=_auth_headers(owner),
    )
    second = await client.post(
        "/api/v1/provenance/records",
        json=_provenance_payload(company["id"], obs2["id"], "Resolve Limited"),
        headers=_auth_headers(owner),
    )
    conflict_id = second.json()["data"]["conflict_id"]

    resolve_res = await client.post(
        f"/api/v1/provenance/conflicts/{conflict_id}/resolve",
        json={"resolution_note": "Confirmed 'Resolve Limited' via direct registry lookup."},
        headers=_auth_headers(owner),
    )
    assert resolve_res.status_code == 200
    assert resolve_res.json()["data"]["status"] == "resolved"
    assert resolve_res.json()["data"]["resolved_by"] is not None

    # The provenance records themselves are untouched — resolving is
    # record-keeping, not a data mutation (this module never writes to
    # Company/Product).
    second_record = await client.get(f"/api/v1/provenance/records/{second.json()['data']['id']}")
    assert second_record.json()["data"]["status"] == "observed"
    assert second_record.json()["data"]["value_observed"] == "Resolve Limited"


@pytest.mark.asyncio
async def test_resolve_conflict_without_note_rejected(client):
    owner = await _register_verified(client, "resolve-nonote@example.com")
    res = await client.post(
        "/api/v1/provenance/conflicts/00000000-0000-0000-0000-000000000000/resolve",
        json={"resolution_note": ""},
        headers=_auth_headers(owner),
    )
    assert res.status_code == 422  # empty note rejected by schema validation before any lookup


@pytest.mark.asyncio
async def test_resolve_nonexistent_conflict_404s(client):
    owner = await _register_verified(client, "resolve-missing@example.com")
    res = await client.post(
        "/api/v1/provenance/conflicts/00000000-0000-0000-0000-000000000000/resolve",
        json={"resolution_note": "N/A"},
        headers=_auth_headers(owner),
    )
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "CONFLICT_NOT_FOUND"


# --------------------------------------------------------------------------
# Cross-cutting: product entity type works identically to company
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_provenance_works_for_product_entity_type_too(client):
    """Confirms the architecture doc's requirement directly: the
    provenance system must be capable of attaching lineage to BOTH
    Company and Product information, not just Company."""
    owner = await _register_verified(client, "prod-prov-owner@example.com")
    category_res = await client.post(
        "/api/v1/product-categories",
        json={"name": "Provenance Test Category"},
        headers=_auth_headers(owner),
    )
    category_id = category_res.json()["data"]["id"]
    product_res = await client.post(
        "/api/v1/products",
        json={"name": "Provenance Test Product", "category_id": category_id},
        headers=_auth_headers(owner),
    )
    product_id = product_res.json()["data"]["id"]

    source = await _create_source(client, owner, name="Product Provenance Source")
    observation = await _create_observation(client, owner, source["id"], "5.5 kW")

    res = await client.post(
        "/api/v1/provenance/records",
        json={
            "entity_type": "product",
            "product_id": product_id,
            "field_name": "power_rating",
            "raw_observation_id": observation["id"],
            "value_observed": "5.5 kW",
            "extraction_method": "manual",
            "confidence": 0.7,
        },
        headers=_auth_headers(owner),
    )
    assert res.status_code == 201, res.text
    assert res.json()["data"]["entity_type"] == "product"
    assert res.json()["data"]["product_id"] == product_id
    assert res.json()["data"]["company_id"] is None

    lineage = await client.get(f"/api/v1/provenance?entity_type=product&entity_id={product_id}")
    assert lineage.json()["data"]["total"] == 1
