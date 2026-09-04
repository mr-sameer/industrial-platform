"""
ProductAttribute evidence tests — the approved additive extension of
Module 5A's provenance pattern to ProductAttribute (Phase 4B). Covers
creation (including the VERIFIED-at-creation guard, regardless of
extraction_method), multi-source corroboration/conflict detection
reusing DataConflict, the explicit verify/reject lifecycle, and
apply_reviewed_attribute_to_product's end-to-end traceability all the
way back to the originating RawObservation. Reuses
test_companies.py/test_product_graph.py/test_provenance.py/
test_acquisition.py's established fixtures rather than duplicating
them.
"""

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.db.session import AsyncSessionLocal
from app.models.raw_observation import RawObservation
from tests.test_acquisition import _register_admin
from tests.test_companies import _auth_headers, _register_verified
from tests.test_product_graph import _create_category, _create_product, _create_specification
from tests.test_provenance import _create_observation, _create_source


async def _setup_product_with_spec(client, user, category_name: str = "Centrifugal Pumps"):
    category = await _create_category(client, user, category_name)
    spec = await _create_specification(client, user, category["id"], name="Flow Rate", unit="LPM")
    product = await _create_product(client, user, category["id"], name="Test Pump")
    return category, spec, product


async def _setup_observation(
    client, user, value: str = "500", content_hash: str = "hash-1"
) -> dict:
    source = await _create_source(client, user, name=f"Test Catalogue {content_hash}")
    return await _create_observation(client, user, source["id"], value, content_hash=content_hash)


def _evidence_payload(
    product_id: str, specification_id: str, raw_observation_id: str, value: str = "500", **overrides
) -> dict:
    return {
        "product_id": product_id,
        "specification_id": specification_id,
        "raw_observation_id": raw_observation_id,
        "value_observed": value,
        "extraction_method": "manual",
        "confidence": 0.7,
        **overrides,
    }


async def _create_evidence(
    client, user, product_id: str, specification_id: str, raw_observation_id: str, **overrides
) -> dict:
    res = await client.post(
        f"/api/v1/products/{product_id}/attributes/{specification_id}/evidence",
        json=_evidence_payload(product_id, specification_id, raw_observation_id, **overrides),
        headers=_auth_headers(user),
    )
    assert res.status_code == 201, res.text
    return res.json()["data"]


# --------------------------------------------------------------------------
# Creation
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_evidence_requires_auth(client):
    user = await _register_verified(client, "pae-noauth@example.com")
    _category, spec, product = await _setup_product_with_spec(client, user)
    observation = await _setup_observation(client, user)
    res = await client.post(
        f"/api/v1/products/{product['id']}/attributes/{spec['id']}/evidence",
        json=_evidence_payload(product["id"], spec["id"], observation["id"]),
    )
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_cannot_create_evidence_as_verified_directly(client):
    """(a) VERIFIED creation is rejected."""
    user = await _register_verified(client, "pae-verified-guard@example.com")
    _category, spec, product = await _setup_product_with_spec(client, user)
    observation = await _setup_observation(client, user)
    res = await client.post(
        f"/api/v1/products/{product['id']}/attributes/{spec['id']}/evidence",
        json=_evidence_payload(product["id"], spec["id"], observation["id"], status="verified"),
        headers=_auth_headers(user),
    )
    assert res.status_code == 422


@pytest.mark.asyncio
async def test_observed_evidence_creation_works(client):
    """(b) OBSERVED evidence creation works."""
    user = await _register_verified(client, "pae-observed@example.com")
    _category, spec, product = await _setup_product_with_spec(client, user)
    observation = await _setup_observation(client, user)
    evidence = await _create_evidence(
        client, user, product["id"], spec["id"], observation["id"], status="observed"
    )
    assert evidence["status"] == "observed"
    assert evidence["value_observed"] == "500"
    assert evidence["raw_observation_id"] == observation["id"]
    assert evidence["verified_by"] is None
    assert evidence["conflict_id"] is None


@pytest.mark.asyncio
async def test_extracted_evidence_creation_works(client):
    """(c) EXTRACTED evidence creation works."""
    user = await _register_verified(client, "pae-extracted@example.com")
    _category, spec, product = await _setup_product_with_spec(client, user)
    observation = await _setup_observation(client, user)
    evidence = await _create_evidence(
        client,
        user,
        product["id"],
        spec["id"],
        observation["id"],
        status="extracted",
        extraction_method="rule_based",
    )
    assert evidence["status"] == "extracted"
    assert evidence["extraction_method"] == "rule_based"


@pytest.mark.asyncio
async def test_ai_assisted_evidence_cannot_be_created_verified(client):
    """(d) AI_ASSISTED evidence cannot be created as VERIFIED — confidence
    and extraction_method never confer authority."""
    user = await _register_verified(client, "pae-ai@example.com")
    _category, spec, product = await _setup_product_with_spec(client, user)
    observation = await _setup_observation(client, user)
    res = await client.post(
        f"/api/v1/products/{product['id']}/attributes/{spec['id']}/evidence",
        json=_evidence_payload(
            product["id"],
            spec["id"],
            observation["id"],
            extraction_method="ai_assisted",
            status="verified",
        ),
        headers=_auth_headers(user),
    )
    assert res.status_code == 422

    # AI-assisted extraction may still create a non-verified row.
    evidence = await _create_evidence(
        client,
        user,
        product["id"],
        spec["id"],
        observation["id"],
        extraction_method="ai_assisted",
        status="extracted",
    )
    assert evidence["extraction_method"] == "ai_assisted"
    assert evidence["status"] == "extracted"


@pytest.mark.asyncio
async def test_evidence_path_body_mismatch_rejected(client):
    user = await _register_verified(client, "pae-mismatch@example.com")
    _category, spec, product = await _setup_product_with_spec(client, user)
    _c2, other_spec, _p2 = await _setup_product_with_spec(client, user, "Other Category")
    observation = await _setup_observation(client, user)
    res = await client.post(
        f"/api/v1/products/{product['id']}/attributes/{spec['id']}/evidence",
        json=_evidence_payload(product["id"], other_spec["id"], observation["id"]),
        headers=_auth_headers(user),
    )
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "ATTRIBUTE_MISMATCH"


@pytest.mark.asyncio
async def test_evidence_rejected_when_specification_not_in_product_category(client):
    user = await _register_verified(client, "pae-wrongcat@example.com")
    _c1, _spec1, product = await _setup_product_with_spec(client, user, "Pumps A")
    _c2, other_spec, _product2 = await _setup_product_with_spec(client, user, "Pumps B")
    observation = await _setup_observation(client, user)
    res = await client.post(
        f"/api/v1/products/{product['id']}/attributes/{other_spec['id']}/evidence",
        json=_evidence_payload(product["id"], other_spec["id"], observation["id"]),
        headers=_auth_headers(user),
    )
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "INVALID_SPECIFICATION"


@pytest.mark.asyncio
async def test_creating_duplicate_evidence_for_same_source_is_idempotent(client):
    user = await _register_verified(client, "pae-idempotent@example.com")
    _category, spec, product = await _setup_product_with_spec(client, user)
    observation = await _setup_observation(client, user)
    first = await _create_evidence(client, user, product["id"], spec["id"], observation["id"])
    second = await _create_evidence(client, user, product["id"], spec["id"], observation["id"])
    assert first["id"] == second["id"]


# --------------------------------------------------------------------------
# Corroboration / conflict
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_agreeing_sources_produce_no_conflict(client):
    """(e) Two agreeing sources produce no conflict."""
    user = await _register_verified(client, "pae-agree@example.com")
    _category, spec, product = await _setup_product_with_spec(client, user)
    obs_a = await _setup_observation(client, user, value="500", content_hash="agree-a")
    obs_b = await _setup_observation(client, user, value="500", content_hash="agree-b")

    evidence_a = await _create_evidence(
        client, user, product["id"], spec["id"], obs_a["id"], value="500"
    )
    evidence_b = await _create_evidence(
        client, user, product["id"], spec["id"], obs_b["id"], value="500"
    )
    assert evidence_a["conflict_id"] is None
    assert evidence_b["conflict_id"] is None


@pytest.mark.asyncio
async def test_disagreeing_sources_produce_conflict(client):
    """(f) Two disagreeing sources produce a DataConflict."""
    user = await _register_verified(client, "pae-disagree@example.com")
    _category, spec, product = await _setup_product_with_spec(client, user)
    obs_a = await _setup_observation(client, user, value="500", content_hash="disagree-a")
    obs_b = await _setup_observation(client, user, value="450", content_hash="disagree-b")

    evidence_a = await _create_evidence(
        client, user, product["id"], spec["id"], obs_a["id"], value="500"
    )
    evidence_b = await _create_evidence(
        client, user, product["id"], spec["id"], obs_b["id"], value="450"
    )
    assert evidence_a["conflict_id"] is None  # not yet flagged at its own creation time

    # Re-fetch A — its conflict_id is set once B (the disagreeing claim)
    # is created, per the conflict-detection sweep.
    refetch_a = await client.get(f"/api/v1/products/attribute-evidence/{evidence_a['id']}")
    assert refetch_a.json()["data"]["conflict_id"] is not None
    assert refetch_a.json()["data"]["conflict_id"] == evidence_b["conflict_id"]


@pytest.mark.asyncio
async def test_evidence_rows_preserved_after_conflict_resolution(client):
    """(g) Evidence rows remain preserved after conflict resolution —
    resolving the DataConflict never deletes or mutates any evidence
    row's value_observed."""
    user = await _register_verified(client, "pae-resolve@example.com")
    _category, spec, product = await _setup_product_with_spec(client, user)
    obs_a = await _setup_observation(client, user, value="500", content_hash="resolve-a")
    obs_b = await _setup_observation(client, user, value="450", content_hash="resolve-b")
    evidence_a = await _create_evidence(
        client, user, product["id"], spec["id"], obs_a["id"], value="500"
    )
    evidence_b = await _create_evidence(
        client, user, product["id"], spec["id"], obs_b["id"], value="450"
    )
    refetch_a = (
        await client.get(f"/api/v1/products/attribute-evidence/{evidence_a['id']}")
    ).json()["data"]
    conflict_id = refetch_a["conflict_id"]

    resolve = await client.post(
        f"/api/v1/provenance/conflicts/{conflict_id}/resolve",
        json={"resolution_note": "Source B refers to a different model variant."},
        headers=_auth_headers(user),
    )
    assert resolve.status_code == 200, resolve.text

    # Both evidence rows still exist, values untouched.
    list_res = await client.get(
        f"/api/v1/products/{product['id']}/attributes/{spec['id']}/evidence"
    )
    values = {item["id"]: item["value_observed"] for item in list_res.json()["data"]["items"]}
    assert values[evidence_a["id"]] == "500"
    assert values[evidence_b["id"]] == "450"


# --------------------------------------------------------------------------
# Verify / reject
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_human_verification_sets_verified(client):
    """(h) Human verification sets VERIFIED."""
    user = await _register_verified(client, "pae-verify-user@example.com")
    admin = await _register_admin(client, "pae-verify-admin@example.com")
    _category, spec, product = await _setup_product_with_spec(client, user)
    observation = await _setup_observation(client, user)
    evidence = await _create_evidence(client, user, product["id"], spec["id"], observation["id"])

    res = await client.post(
        f"/api/v1/products/attribute-evidence/{evidence['id']}/verify",
        headers=_auth_headers(admin),
    )
    assert res.status_code == 200, res.text
    verified = res.json()["data"]
    assert verified["status"] == "verified"
    assert verified["verified_by"] == admin["user"]["id"]
    assert verified["verified_at"] is not None


@pytest.mark.asyncio
async def test_reverification_is_rejected(client):
    """(i) Re-verification is rejected."""
    user = await _register_verified(client, "pae-reverify-user@example.com")
    admin = await _register_admin(client, "pae-reverify-admin@example.com")
    _category, spec, product = await _setup_product_with_spec(client, user)
    observation = await _setup_observation(client, user)
    evidence = await _create_evidence(client, user, product["id"], spec["id"], observation["id"])

    first = await client.post(
        f"/api/v1/products/attribute-evidence/{evidence['id']}/verify",
        headers=_auth_headers(admin),
    )
    assert first.status_code == 200
    second = await client.post(
        f"/api/v1/products/attribute-evidence/{evidence['id']}/verify",
        headers=_auth_headers(admin),
    )
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "ALREADY_VERIFIED"


@pytest.mark.asyncio
async def test_verify_requires_admin(client):
    user = await _register_verified(client, "pae-verify-nonadmin@example.com")
    _category, spec, product = await _setup_product_with_spec(client, user)
    observation = await _setup_observation(client, user)
    evidence = await _create_evidence(client, user, product["id"], spec["id"], observation["id"])

    res = await client.post(
        f"/api/v1/products/attribute-evidence/{evidence['id']}/verify",
        headers=_auth_headers(user),
    )
    assert res.status_code == 403


@pytest.mark.asyncio
async def test_verify_rejects_evidence_below_confidence_threshold(client):
    """P0 safety guard: evidence with confidence < MIN_VERIFIABLE_CONFIDENCE
    (0.45) must never become VERIFIED, regardless of who attempts it."""
    user = await _register_verified(client, "pae-verify-lowconf-user@example.com")
    admin = await _register_admin(client, "pae-verify-lowconf-admin@example.com")
    _category, spec, product = await _setup_product_with_spec(client, user)
    observation = await _setup_observation(client, user)
    evidence = await _create_evidence(
        client,
        user,
        product["id"],
        spec["id"],
        observation["id"],
        confidence=0.20,
        status="extracted",
    )

    res = await client.post(
        f"/api/v1/products/attribute-evidence/{evidence['id']}/verify",
        headers=_auth_headers(admin),
    )
    assert res.status_code == 422, res.text
    assert res.json()["error"]["code"] == "EVIDENCE_CONFIDENCE_TOO_LOW"

    refetch = await client.get(f"/api/v1/products/attribute-evidence/{evidence['id']}")
    refetched = refetch.json()["data"]
    assert refetched["status"] == "extracted"
    assert refetched["verified_by"] is None
    assert refetched["verified_at"] is None


@pytest.mark.asyncio
async def test_verify_succeeds_at_exact_threshold_boundary(client):
    """The floor is inclusive: confidence == MIN_VERIFIABLE_CONFIDENCE
    (0.45) is still verifiable — only strictly-below is blocked."""
    user = await _register_verified(client, "pae-verify-boundary-user@example.com")
    admin = await _register_admin(client, "pae-verify-boundary-admin@example.com")
    _category, spec, product = await _setup_product_with_spec(client, user)
    observation = await _setup_observation(client, user)
    evidence = await _create_evidence(
        client, user, product["id"], spec["id"], observation["id"], confidence=0.45
    )

    res = await client.post(
        f"/api/v1/products/attribute-evidence/{evidence['id']}/verify",
        headers=_auth_headers(admin),
    )
    assert res.status_code == 200, res.text
    verified = res.json()["data"]
    assert verified["status"] == "verified"
    assert verified["verified_by"] == admin["user"]["id"]
    assert verified["verified_at"] is not None


@pytest.mark.asyncio
async def test_reject_still_works_on_low_confidence_evidence(client):
    """The confidence guard applies only to verify — reject remains
    available on low-confidence/ambiguous evidence exactly as before,
    since it is how a human documents why an unreliable claim should
    never be revisited."""
    user = await _register_verified(client, "pae-reject-lowconf-user@example.com")
    admin = await _register_admin(client, "pae-reject-lowconf-admin@example.com")
    _category, spec, product = await _setup_product_with_spec(client, user)
    observation = await _setup_observation(client, user)
    evidence = await _create_evidence(
        client, user, product["id"], spec["id"], observation["id"], confidence=0.20
    )

    res = await client.post(
        f"/api/v1/products/attribute-evidence/{evidence['id']}/reject",
        json={"note": "Confidence too low to trust — multiple conflicting occurrences."},
        headers=_auth_headers(admin),
    )
    assert res.status_code == 200, res.text
    assert res.json()["data"]["status"] == "rejected"


@pytest.mark.asyncio
async def test_reject_evidence_marks_rejected_and_preserves_row(client):
    user = await _register_verified(client, "pae-reject-user@example.com")
    admin = await _register_admin(client, "pae-reject-admin@example.com")
    _category, spec, product = await _setup_product_with_spec(client, user)
    observation = await _setup_observation(client, user, value="450")
    evidence = await _create_evidence(
        client, user, product["id"], spec["id"], observation["id"], value="450"
    )

    res = await client.post(
        f"/api/v1/products/attribute-evidence/{evidence['id']}/reject",
        json={"note": "Different product variant, not this SKU."},
        headers=_auth_headers(admin),
    )
    assert res.status_code == 200, res.text
    rejected = res.json()["data"]
    assert rejected["status"] == "rejected"
    assert rejected["review_note"] == "Different product variant, not this SKU."

    # The row itself is never deleted.
    refetch = await client.get(f"/api/v1/products/attribute-evidence/{evidence['id']}")
    assert refetch.status_code == 200
    assert refetch.json()["data"]["value_observed"] == "450"


@pytest.mark.asyncio
async def test_reject_requires_admin(client):
    user = await _register_verified(client, "pae-reject-nonadmin@example.com")
    _category, spec, product = await _setup_product_with_spec(client, user)
    observation = await _setup_observation(client, user)
    evidence = await _create_evidence(client, user, product["id"], spec["id"], observation["id"])

    res = await client.post(
        f"/api/v1/products/attribute-evidence/{evidence['id']}/reject",
        json={"note": "no"},
        headers=_auth_headers(user),
    )
    assert res.status_code == 403


# --------------------------------------------------------------------------
# Apply
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_apply_requires_verified_evidence(client):
    """(j) apply_reviewed_attribute_to_product requires VERIFIED evidence."""
    user = await _register_verified(client, "pae-apply-notverified-user@example.com")
    admin = await _register_admin(client, "pae-apply-notverified-admin@example.com")
    _category, spec, product = await _setup_product_with_spec(client, user)
    observation = await _setup_observation(client, user)
    evidence = await _create_evidence(client, user, product["id"], spec["id"], observation["id"])

    res = await client.post(
        f"/api/v1/products/attribute-evidence/{evidence['id']}/apply",
        headers=_auth_headers(admin),
    )
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "NOT_VERIFIED"


@pytest.mark.asyncio
async def test_apply_still_blocked_when_verify_was_never_reached(client):
    """Low-confidence evidence that was never (and, per the P0 guard,
    can never be) verified is still correctly rejected by apply's own,
    unmodified NOT_VERIFIED guard — the two guards are independent and
    both hold."""
    user = await _register_verified(client, "pae-apply-lowconf-user@example.com")
    admin = await _register_admin(client, "pae-apply-lowconf-admin@example.com")
    _category, spec, product = await _setup_product_with_spec(client, user)
    observation = await _setup_observation(client, user)
    evidence = await _create_evidence(
        client, user, product["id"], spec["id"], observation["id"], confidence=0.20
    )

    res = await client.post(
        f"/api/v1/products/attribute-evidence/{evidence['id']}/apply",
        headers=_auth_headers(admin),
    )
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "NOT_VERIFIED"


@pytest.mark.asyncio
async def test_apply_requires_admin(client):
    user = await _register_verified(client, "pae-apply-nonadmin@example.com")
    admin = await _register_admin(client, "pae-apply-nonadmin-admin@example.com")
    _category, spec, product = await _setup_product_with_spec(client, user)
    observation = await _setup_observation(client, user)
    evidence = await _create_evidence(client, user, product["id"], spec["id"], observation["id"])
    await client.post(
        f"/api/v1/products/attribute-evidence/{evidence['id']}/verify",
        headers=_auth_headers(admin),
    )

    res = await client.post(
        f"/api/v1/products/attribute-evidence/{evidence['id']}/apply",
        headers=_auth_headers(user),
    )
    assert res.status_code == 403


@pytest.mark.asyncio
async def test_apply_copies_value_and_sets_latest_evidence_id(client):
    """(k) apply copies value into ProductAttribute. (l) apply sets
    latest_evidence_id."""
    user = await _register_verified(client, "pae-apply-user@example.com")
    admin = await _register_admin(client, "pae-apply-admin@example.com")
    _category, spec, product = await _setup_product_with_spec(client, user)
    observation = await _setup_observation(client, user, value="500")
    evidence = await _create_evidence(
        client, user, product["id"], spec["id"], observation["id"], value="500"
    )
    await client.post(
        f"/api/v1/products/attribute-evidence/{evidence['id']}/verify",
        headers=_auth_headers(admin),
    )

    apply_res = await client.post(
        f"/api/v1/products/attribute-evidence/{evidence['id']}/apply",
        headers=_auth_headers(admin),
    )
    assert apply_res.status_code == 200, apply_res.text
    applied = apply_res.json()["data"]
    assert applied["value"] == "500"
    assert applied["product_id"] == product["id"]
    assert applied["specification_id"] == spec["id"]

    detail = await client.get(f"/api/v1/products/{product['id']}")
    attributes = {a["specification_id"]: a for a in detail.json()["data"]["attributes"]}
    applied_attr = attributes[spec["id"]]
    assert applied_attr["value"] == "500"
    assert applied_attr["latest_evidence_id"] == evidence["id"]


@pytest.mark.asyncio
async def test_historical_evidence_remains_unchanged_after_apply(client):
    """(m) Historical evidence remains unchanged after a later apply —
    the losing/uninvolved evidence row is never mutated or deleted."""
    user = await _register_verified(client, "pae-history-user@example.com")
    admin = await _register_admin(client, "pae-history-admin@example.com")
    _category, spec, product = await _setup_product_with_spec(client, user)
    obs_a = await _setup_observation(client, user, value="500", content_hash="history-a")
    obs_b = await _setup_observation(client, user, value="450", content_hash="history-b")
    evidence_a = await _create_evidence(
        client, user, product["id"], spec["id"], obs_a["id"], value="500"
    )
    evidence_b = await _create_evidence(
        client, user, product["id"], spec["id"], obs_b["id"], value="450"
    )

    await client.post(
        f"/api/v1/products/attribute-evidence/{evidence_a['id']}/verify",
        headers=_auth_headers(admin),
    )
    await client.post(
        f"/api/v1/products/attribute-evidence/{evidence_a['id']}/apply",
        headers=_auth_headers(admin),
    )

    # evidence_b (never verified, never applied, on the losing side of
    # the conflict) is completely untouched.
    refetch_b = await client.get(f"/api/v1/products/attribute-evidence/{evidence_b['id']}")
    assert refetch_b.status_code == 200
    unchanged = refetch_b.json()["data"]
    assert unchanged["value_observed"] == "450"
    assert unchanged["status"] == "observed"
    assert unchanged["verified_by"] is None


@pytest.mark.asyncio
async def test_apply_creates_attribute_when_none_existed_yet(client):
    """apply_reviewed_attribute_to_product get-or-creates the
    ProductAttribute row — evidence can exist before any attribute
    value was ever set at product-creation time."""
    user = await _register_verified(client, "pae-getorcreate@example.com")
    admin = await _register_admin(client, "pae-getorcreate-admin@example.com")
    category = await _create_category(client, user, "Bare Category")
    spec = await _create_specification(client, user, category["id"], name="Head", unit="m")
    # Product created with NO attributes at all.
    product = await _create_product(
        client, user, category["id"], name="Bare Product", attributes=[]
    )
    observation = await _setup_observation(client, user, value="60")
    evidence = await _create_evidence(
        client, user, product["id"], spec["id"], observation["id"], value="60"
    )
    await client.post(
        f"/api/v1/products/attribute-evidence/{evidence['id']}/verify",
        headers=_auth_headers(admin),
    )
    apply_res = await client.post(
        f"/api/v1/products/attribute-evidence/{evidence['id']}/apply",
        headers=_auth_headers(admin),
    )
    assert apply_res.status_code == 200, apply_res.text
    assert apply_res.json()["data"]["value"] == "60"

    detail = await client.get(f"/api/v1/products/{product['id']}")
    attributes = {a["specification_id"]: a for a in detail.json()["data"]["attributes"]}
    assert attributes[spec["id"]]["value"] == "60"


# --------------------------------------------------------------------------
# Referential integrity
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_raw_observation_deletion_blocked_when_referenced_by_evidence(client):
    """(n) RawObservation deletion is blocked when referenced — mirrors
    ProvenanceRecord's own RESTRICT behavior. No API delete route exists
    for RawObservation (append-only by design), so this is exercised
    directly at the database layer."""
    user = await _register_verified(client, "pae-restrict@example.com")
    _category, spec, product = await _setup_product_with_spec(client, user)
    observation = await _setup_observation(client, user)
    await _create_evidence(client, user, product["id"], spec["id"], observation["id"])

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(RawObservation).where(RawObservation.id == observation["id"])
        )
        row = result.scalar_one()
        await db.delete(row)
        with pytest.raises(IntegrityError):
            await db.commit()
        await db.rollback()


# --------------------------------------------------------------------------
# End-to-end traceability
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_end_to_end_traceability_from_attribute_to_raw_observation(client):
    """(r) ProductAttribute -> latest_evidence_id -> ProductAttributeEvidence
    -> raw_observation_id -> RawObservation resolves correctly."""
    user = await _register_verified(client, "pae-e2e-user@example.com")
    admin = await _register_admin(client, "pae-e2e-admin@example.com")
    _category, spec, product = await _setup_product_with_spec(client, user)
    observation = await _setup_observation(client, user, value="500", content_hash="e2e-hash")
    evidence = await _create_evidence(
        client, user, product["id"], spec["id"], observation["id"], value="500"
    )
    await client.post(
        f"/api/v1/products/attribute-evidence/{evidence['id']}/verify",
        headers=_auth_headers(admin),
    )
    await client.post(
        f"/api/v1/products/attribute-evidence/{evidence['id']}/apply",
        headers=_auth_headers(admin),
    )

    detail = await client.get(f"/api/v1/products/{product['id']}")
    attributes = {a["specification_id"]: a for a in detail.json()["data"]["attributes"]}
    attribute = attributes[spec["id"]]
    assert attribute["latest_evidence_id"] == evidence["id"]

    evidence_detail = await client.get(
        f"/api/v1/products/attribute-evidence/{attribute['latest_evidence_id']}"
    )
    assert evidence_detail.status_code == 200
    resolved_observation_id = evidence_detail.json()["data"]["raw_observation_id"]
    assert resolved_observation_id == observation["id"]
