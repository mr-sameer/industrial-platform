"""
Tests for the candidate.evidence field returned by
GET /requirements/{id}/matches — specifically
app.api.v1.requirements._fetch_product_evidence, which surfaces the
real VERIFIED-and-applied ProductAttributeEvidence trail behind each
matched Product's canonical attribute values (via
ProductAttribute.latest_evidence_id), never a fabricated or upgraded
claim. Covers exactly the trust rules that function's own docstring
states: REJECTED evidence is never surfaced; evidence that was created
but never verified+applied is never surfaced (only the row that
actually became the ProductAttribute's canonical value is reachable at
all); a product's evidence list is an honest [] when it truly has none;
and a returned item's source_url resolves to a real
RawObservation.external_reference.

Reuses the established fixtures from test_product_attribute_evidence.py
(evidence create/verify/apply) and test_requirement_matching.py
(requirement/matches HTTP flow) rather than duplicating them.
"""

import pytest

from tests.test_acquisition import _register_admin
from tests.test_companies import _auth_headers, _register_verified
from tests.test_product_attribute_evidence import _create_evidence
from tests.test_product_graph import (
    _create_category,
    _create_product,
    _create_specification,
    _publish,
)
from tests.test_provenance import _create_source
from tests.test_requirement_matching import (
    _create_company_at,
    _create_requirement,
    _get_matches,
    _offer,
)


async def _create_observation_with_reference(
    client, owner, source_id: str, value: str, *, external_reference: str, content_hash: str
) -> dict:
    """Same shape as tests.test_provenance._create_observation, plus a
    real external_reference — needed here specifically to prove a
    returned evidence item's source_url resolves to it."""
    res = await client.post(
        f"/api/v1/sources/{source_id}/observations",
        json={
            "source_id": source_id,
            "external_reference": external_reference,
            "raw_content": {"value": value},
            "content_hash": content_hash,
            "collection_method_used": "api",
            "collected_at": "2026-08-08T00:00:00Z",
        },
        headers=_auth_headers(owner),
    )
    assert res.status_code == 201, res.text
    return res.json()["data"]


async def _verify(client, admin, evidence_id: str) -> None:
    res = await client.post(
        f"/api/v1/products/attribute-evidence/{evidence_id}/verify", headers=_auth_headers(admin)
    )
    assert res.status_code == 200, res.text


async def _apply(client, admin, evidence_id: str) -> None:
    res = await client.post(
        f"/api/v1/products/attribute-evidence/{evidence_id}/apply", headers=_auth_headers(admin)
    )
    assert res.status_code == 200, res.text


async def _reject(client, admin, evidence_id: str) -> None:
    res = await client.post(
        f"/api/v1/products/attribute-evidence/{evidence_id}/reject",
        json={"note": "test rejection"},
        headers=_auth_headers(admin),
    )
    assert res.status_code == 200, res.text


@pytest.mark.asyncio
async def test_verified_and_applied_evidence_is_surfaced_in_match_response(client):
    """(1)+(2)+(3): a real VERIFIED, applied ProductAttributeEvidence
    row appears in candidate.evidence with its real observed value and
    a source_url resolving to the real RawObservation.external_reference."""
    user = await _register_verified(client, "matchev-owner@example.com")
    admin = await _register_admin(client, "matchev-admin@example.com")
    category = await _create_category(client, user, "Match Evidence Category")
    spec = await _create_specification(client, user, category["id"], name="Motor Power", unit="kW")
    product = await _create_product(client, user, category["id"], name="Match Evidence Product")
    await _publish(client, user, product["id"])
    owner, company = await _create_company_at(
        client, "matchev-co@example.com", "Match Evidence Co", country="India", state="", city=""
    )
    await _offer(client, owner, company, product)

    source = await _create_source(client, user, name="Real Match Evidence Source")
    observation = await _create_observation_with_reference(
        client, user, source["id"], "5.5",
        external_reference="https://example.com/real-catalogue-page-4",
        content_hash="matchev-hash-1",
    )
    evidence = await _create_evidence(
        client, user, product["id"], spec["id"], observation["id"], value="5.5"
    )
    await _verify(client, admin, evidence["id"])
    await _apply(client, admin, evidence["id"])

    requirement = await _create_requirement(client, user, product_category_id=category["id"])
    data = await _get_matches(client, user, requirement["id"])
    assert data["returned_count"] == 1
    match = data["matches"][0]
    assert len(match["evidence"]) == 1
    item = match["evidence"][0]
    assert item["field_name"] == "Motor Power"
    assert item["value_observed"] == "5.5"
    assert item["status"] == "verified"
    assert item["source_url"] == "https://example.com/real-catalogue-page-4"


@pytest.mark.asyncio
async def test_rejected_evidence_never_surfaced(client):
    """(4): a REJECTED evidence row must never appear as positive
    evidence — and since it was never applied, it can never even reach
    ProductAttribute.latest_evidence_id, so it structurally cannot
    surface here regardless."""
    user = await _register_verified(client, "matchev-rej-owner@example.com")
    admin = await _register_admin(client, "matchev-rej-admin@example.com")
    category = await _create_category(client, user, "Match Evidence Rejected Category")
    spec = await _create_specification(client, user, category["id"], name="Motor Power", unit="kW")
    product = await _create_product(client, user, category["id"], name="Match Evidence Rejected Product")
    await _publish(client, user, product["id"])
    owner, company = await _create_company_at(
        client, "matchev-rej-co@example.com", "Match Evidence Rejected Co", country="India", state="", city=""
    )
    await _offer(client, owner, company, product)

    source = await _create_source(client, user, name="Rejected Evidence Source")
    observation = await _create_observation_with_reference(
        client, user, source["id"], "999",
        external_reference="https://example.com/bad-claim",
        content_hash="matchev-hash-rej",
    )
    evidence = await _create_evidence(
        client, user, product["id"], spec["id"], observation["id"], value="999"
    )
    await _reject(client, admin, evidence["id"])

    requirement = await _create_requirement(client, user, product_category_id=category["id"])
    data = await _get_matches(client, user, requirement["id"])
    assert data["returned_count"] == 1
    match = data["matches"][0]
    assert match["evidence"] == []


@pytest.mark.asyncio
async def test_verified_but_not_applied_evidence_not_surfaced(client):
    """(5): evidence that reached VERIFIED but was never applied (no
    admin ever ran the distinct, later apply action) must not be
    presented as the product's evidence — only the evidence a real
    apply call actually promoted to ProductAttribute.latest_evidence_id
    is reachable."""
    user = await _register_verified(client, "matchev-noapply-owner@example.com")
    admin = await _register_admin(client, "matchev-noapply-admin@example.com")
    category = await _create_category(client, user, "Match Evidence No Apply Category")
    spec = await _create_specification(client, user, category["id"], name="Motor Power", unit="kW")
    product = await _create_product(client, user, category["id"], name="Match Evidence No Apply Product")
    await _publish(client, user, product["id"])
    owner, company = await _create_company_at(
        client, "matchev-noapply-co@example.com", "Match Evidence No Apply Co", country="India", state="", city=""
    )
    await _offer(client, owner, company, product)

    source = await _create_source(client, user, name="Verified Not Applied Source")
    observation = await _create_observation_with_reference(
        client, user, source["id"], "7.5",
        external_reference="https://example.com/verified-not-applied",
        content_hash="matchev-hash-noapply",
    )
    evidence = await _create_evidence(
        client, user, product["id"], spec["id"], observation["id"], value="7.5"
    )
    await _verify(client, admin, evidence["id"])
    # Deliberately never applied.

    requirement = await _create_requirement(client, user, product_category_id=category["id"])
    data = await _get_matches(client, user, requirement["id"])
    assert data["returned_count"] == 1
    match = data["matches"][0]
    assert match["evidence"] == []


@pytest.mark.asyncio
async def test_product_with_no_evidence_returns_honest_empty_list(client):
    """(6): a product with zero ProductAttributeEvidence at all still
    returns matches — evidence is an honest [], not an error."""
    user = await _register_verified(client, "matchev-none-owner@example.com")
    category = await _create_category(client, user, "Match Evidence None Category")
    product = await _create_product(client, user, category["id"], name="Match Evidence None Product")
    await _publish(client, user, product["id"])
    owner, company = await _create_company_at(
        client, "matchev-none-co@example.com", "Match Evidence None Co", country="India", state="", city=""
    )
    await _offer(client, owner, company, product)

    requirement = await _create_requirement(client, user, product_category_id=category["id"])
    data = await _get_matches(client, user, requirement["id"])
    assert data["returned_count"] == 1
    assert data["matches"][0]["evidence"] == []
