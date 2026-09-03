"""
SpecificationAlias management API tests — the dedicated ADMIN-only
alias endpoint resolving the authorization gap flagged in the
deterministic specification-extraction milestone's own completion
report. Reuses test_product_graph.py/test_acquisition.py/
test_companies.py's established fixtures rather than duplicating them.

Deliberately does NOT touch or re-test
app.api.v1.products.create_category_specification/create_category —
their authorization (authenticated user, not Role.ADMIN) is
unchanged, out of scope for this file.
"""

import pytest
from sqlalchemy import select

from app.db.session import AsyncSessionLocal
from app.models.product_attribute import ProductAttribute
from app.models.product_attribute_evidence import ProductAttributeEvidence
from tests.test_acquisition import _register_admin
from tests.test_companies import _auth_headers, _register_verified
from tests.test_product_graph import _create_category, _create_specification


async def _create_alias(client, admin, specification_id: str, alias: str):
    return await client.post(
        f"/api/v1/product-specifications/{specification_id}/aliases",
        json={"alias": alias},
        headers=_auth_headers(admin),
    )


async def _list_aliases(client, specification_id: str, headers: dict | None = None):
    return await client.get(
        f"/api/v1/product-specifications/{specification_id}/aliases", headers=headers or {}
    )


async def _setup_spec(client, admin, name: str = "Flow") -> dict:
    category = await _create_category(client, admin, f"{name} Category")
    return await _create_specification(client, admin, category["id"], name=name, unit="m³/h")


# --------------------------------------------------------------------------
# Security
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_admin_can_create_alias(client):
    admin = await _register_admin(client, "alias-admin-ok@example.com")
    spec = await _setup_spec(client, admin)
    res = await _create_alias(client, admin, spec["id"], "Flow Rate")
    assert res.status_code == 201, res.text
    body = res.json()["data"]
    assert body["alias"] == "Flow Rate"
    assert body["specification_id"] == spec["id"]


@pytest.mark.asyncio
async def test_non_admin_authenticated_user_receives_403(client):
    admin = await _register_admin(client, "alias-setup-nonadmin@example.com")
    spec = await _setup_spec(client, admin)
    non_admin = await _register_verified(client, "alias-nonadmin@example.com")
    res = await client.post(
        f"/api/v1/product-specifications/{spec['id']}/aliases",
        json={"alias": "Flow Rate"},
        headers=_auth_headers(non_admin),
    )
    assert res.status_code == 403


@pytest.mark.asyncio
async def test_unauthenticated_user_receives_401(client):
    admin = await _register_admin(client, "alias-setup-unauth@example.com")
    spec = await _setup_spec(client, admin)
    res = await client.post(
        f"/api/v1/product-specifications/{spec['id']}/aliases",
        json={"alias": "Flow Rate"},
    )
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_create_alias_for_missing_specification_404(client):
    admin = await _register_admin(client, "alias-missing-spec@example.com")
    res = await _create_alias(client, admin, "00000000-0000-0000-0000-000000000000", "Flow Rate")
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "SPECIFICATION_NOT_FOUND"


# --------------------------------------------------------------------------
# Validation
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_duplicate_alias_rejected(client):
    admin = await _register_admin(client, "alias-dup@example.com")
    spec = await _setup_spec(client, admin)
    first = await _create_alias(client, admin, spec["id"], "Flow Rate")
    assert first.status_code == 201, first.text
    second = await _create_alias(client, admin, spec["id"], "Flow Rate")
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "DUPLICATE_ALIAS"


@pytest.mark.asyncio
async def test_duplicate_alias_rejected_after_normalization(client):
    admin = await _register_admin(client, "alias-dup-normalized@example.com")
    spec = await _setup_spec(client, admin)
    first = await _create_alias(client, admin, spec["id"], "Flow Rate")
    assert first.status_code == 201, first.text
    # Same alias, different case/whitespace/trailing colon — must still
    # be caught, since app.extraction.label_matching would treat both
    # as the identical label at extraction time.
    second = await _create_alias(client, admin, spec["id"], "  flow   RATE:  ")
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "DUPLICATE_ALIAS"


@pytest.mark.asyncio
async def test_alias_identical_to_specification_name_rejected(client):
    admin = await _register_admin(client, "alias-same-as-name@example.com")
    spec = await _setup_spec(client, admin, name="Flow")
    res = await _create_alias(client, admin, spec["id"], "flow")
    assert res.status_code == 409
    assert res.json()["error"]["code"] == "DUPLICATE_ALIAS"


@pytest.mark.asyncio
async def test_whitespace_only_alias_rejected(client):
    admin = await _register_admin(client, "alias-whitespace@example.com")
    spec = await _setup_spec(client, admin)
    res = await _create_alias(client, admin, spec["id"], "    ")
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "EMPTY_ALIAS"


@pytest.mark.asyncio
async def test_empty_alias_rejected(client):
    admin = await _register_admin(client, "alias-empty@example.com")
    spec = await _setup_spec(client, admin)
    res = await _create_alias(client, admin, spec["id"], "")
    assert res.status_code == 422


@pytest.mark.asyncio
async def test_alias_over_120_characters_rejected(client):
    admin = await _register_admin(client, "alias-too-long@example.com")
    spec = await _setup_spec(client, admin)
    res = await _create_alias(client, admin, spec["id"], "x" * 121)
    assert res.status_code == 422


@pytest.mark.asyncio
async def test_alias_at_exactly_120_characters_accepted(client):
    admin = await _register_admin(client, "alias-exactly-120@example.com")
    spec = await _setup_spec(client, admin)
    res = await _create_alias(client, admin, spec["id"], "x" * 120)
    assert res.status_code == 201, res.text


# --------------------------------------------------------------------------
# Behavior / read access / non-interference
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_created_alias_appears_in_list(client):
    admin = await _register_admin(client, "alias-list@example.com")
    spec = await _setup_spec(client, admin)
    await _create_alias(client, admin, spec["id"], "Flow Rate")
    await _create_alias(client, admin, spec["id"], "Capacity")

    res = await _list_aliases(client, spec["id"])
    assert res.status_code == 200, res.text
    aliases = {row["alias"] for row in res.json()["data"]}
    assert aliases == {"Flow Rate", "Capacity"}


@pytest.mark.asyncio
async def test_list_aliases_is_public_no_auth_required(client):
    admin = await _register_admin(client, "alias-public-read@example.com")
    spec = await _setup_spec(client, admin)
    await _create_alias(client, admin, spec["id"], "Flow Rate")

    res = await _list_aliases(client, spec["id"])
    assert res.status_code == 200, res.text
    assert len(res.json()["data"]) == 1


@pytest.mark.asyncio
async def test_list_aliases_for_specification_with_no_aliases_returns_empty(client):
    admin = await _register_admin(client, "alias-list-empty@example.com")
    spec = await _setup_spec(client, admin)
    res = await _list_aliases(client, spec["id"])
    assert res.status_code == 200, res.text
    assert res.json()["data"] == []


@pytest.mark.asyncio
async def test_alias_creation_does_not_modify_specification_name(client):
    admin = await _register_admin(client, "alias-no-name-change@example.com")
    spec = await _setup_spec(client, admin, name="Flow")
    await _create_alias(client, admin, spec["id"], "Flow Rate")

    specs = await client.get(f"/api/v1/product-categories/{spec['category_id']}/specifications")
    matching = next(s for s in specs.json()["data"] if s["id"] == spec["id"])
    assert matching["name"] == "Flow"


@pytest.mark.asyncio
async def test_alias_creation_touches_no_attribute_or_evidence_tables(client):
    admin = await _register_admin(client, "alias-no-side-effects@example.com")
    spec = await _setup_spec(client, admin)
    await _create_alias(client, admin, spec["id"], "Flow Rate")

    async with AsyncSessionLocal() as db:
        attrs = await db.execute(select(ProductAttribute))
        evidence = await db.execute(select(ProductAttributeEvidence))
        assert attrs.scalars().first() is None
        assert evidence.scalars().first() is None


@pytest.mark.asyncio
async def test_existing_specification_creation_endpoint_authorization_unchanged(client):
    """Regression guard for the explicit constraint this milestone must
    not violate: POST /product-categories/{id}/specifications still
    requires only an authenticated (non-admin) user."""
    non_admin = await _register_verified(client, "alias-spec-endpoint-unchanged@example.com")
    category = await client.post(
        "/api/v1/product-categories",
        json={"name": "Unchanged Auth Category"},
        headers=_auth_headers(non_admin),
    )
    assert category.status_code == 201, category.text
    res = await client.post(
        f"/api/v1/product-categories/{category.json()['data']['id']}/specifications",
        json={"name": "Pressure", "unit": "bar", "datatype": "number", "required": False},
        headers=_auth_headers(non_admin),
    )
    assert res.status_code == 201, res.text
