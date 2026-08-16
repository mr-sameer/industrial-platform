"""
Industrial Product Graph tests — Phase 4B. Covers the five in-scope
entities (ProductCategory, Product, ProductSpecification,
ProductAttribute, Offering): creation, the dynamic specification
system, the EAV attribute validation, search/pagination, and — the
module's own ABSOLUTE RULE — that many Offerings can reference one
Product without duplicating it. Authorization boundaries reuse the
exact company-role fixtures test_companies.py already established.
"""

import pytest

from tests.test_companies import _auth_headers, _company_payload, _register_verified


def _category_payload(name: str = "Electric Motors") -> dict:
    return {"name": name}


def _spec_payload(name: str = "Power", datatype: str = "number", unit: str | None = "kW") -> dict:
    return {"name": name, "unit": unit, "datatype": datatype, "required": False}


async def _create_category(client, owner, name: str = "Electric Motors") -> dict:
    res = await client.post(
        "/api/v1/product-categories", json=_category_payload(name), headers=_auth_headers(owner)
    )
    assert res.status_code == 201, res.text
    return res.json()["data"]


async def _create_specification(client, owner, category_id: str, **kwargs) -> dict:
    res = await client.post(
        f"/api/v1/product-categories/{category_id}/specifications",
        json=_spec_payload(**kwargs),
        headers=_auth_headers(owner),
    )
    assert res.status_code == 201, res.text
    return res.json()["data"]


async def _create_product(
    client, owner, category_id: str, name: str = "XJ-450 Motor", attributes=None
) -> dict:
    payload = {
        "name": name,
        "description": "A test product.",
        "category_id": category_id,
        "industry": "Manufacturing",
        "attributes": attributes or [],
    }
    res = await client.post("/api/v1/products", json=payload, headers=_auth_headers(owner))
    assert res.status_code == 201, res.text
    return res.json()["data"]


async def _publish(client, owner, product_id: str) -> dict:
    res = await client.patch(
        f"/api/v1/products/{product_id}", json={"status": "published"}, headers=_auth_headers(owner)
    )
    assert res.status_code == 200, res.text
    return res.json()["data"]


async def _create_verified_company(client, email: str, name: str) -> tuple[dict, dict]:
    owner = await _register_verified(client, email)
    res = await client.post(
        "/api/v1/companies", json=_company_payload(name), headers=_auth_headers(owner)
    )
    assert res.status_code == 201, res.text
    return owner, res.json()["data"]


# --------------------------------------------------------------------------
# ProductCategory
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_category_requires_auth(client):
    res = await client.post("/api/v1/product-categories", json=_category_payload())
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_create_category_and_list_it(client):
    owner = await _register_verified(client, "cat-owner@example.com")
    category = await _create_category(client, owner, "Pumps")
    assert category["name"] == "Pumps"
    assert category["slug"] == "pumps"
    assert category["parent_id"] is None

    list_res = await client.get("/api/v1/product-categories")
    assert list_res.status_code == 200
    slugs = [c["slug"] for c in list_res.json()["data"]]
    assert "pumps" in slugs


@pytest.mark.asyncio
async def test_child_category_references_parent(client):
    owner = await _register_verified(client, "cat-parent@example.com")
    parent = await _create_category(client, owner, "Industrial Equipment")
    child_res = await client.post(
        "/api/v1/product-categories",
        json={"name": "Packaging Machinery", "parent_id": parent["id"]},
        headers=_auth_headers(owner),
    )
    assert child_res.status_code == 201
    assert child_res.json()["data"]["parent_id"] == parent["id"]


@pytest.mark.asyncio
async def test_create_category_with_nonexistent_parent_404s(client):
    owner = await _register_verified(client, "cat-badparent@example.com")
    res = await client.post(
        "/api/v1/product-categories",
        json={"name": "Orphan", "parent_id": "00000000-0000-0000-0000-000000000000"},
        headers=_auth_headers(owner),
    )
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "CATEGORY_NOT_FOUND"


# --------------------------------------------------------------------------
# ProductSpecification — the dynamic specification system
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_different_categories_get_different_specifications(client):
    """Phase 4A's core requirement: specifications are never hardcoded
    per product type — Motors and Pumps get entirely different, real,
    independently-defined specification sets."""
    owner = await _register_verified(client, "spec-dynamic@example.com")
    motors = await _create_category(client, owner, "Motors")
    pumps = await _create_category(client, owner, "Pumps")

    await _create_specification(client, owner, motors["id"], name="Voltage", unit="V")
    await _create_specification(
        client, owner, motors["id"], name="RPM", unit=None, datatype="number"
    )
    await _create_specification(client, owner, pumps["id"], name="Flow Rate", unit="LPM")

    motor_specs = await client.get(f"/api/v1/product-categories/{motors['id']}/specifications")
    pump_specs = await client.get(f"/api/v1/product-categories/{pumps['id']}/specifications")

    motor_names = {s["name"] for s in motor_specs.json()["data"]}
    pump_names = {s["name"] for s in pump_specs.json()["data"]}
    assert motor_names == {"Voltage", "RPM"}
    assert pump_names == {"Flow Rate"}


@pytest.mark.asyncio
async def test_enum_specification_carries_options(client):
    owner = await _register_verified(client, "spec-enum@example.com")
    category = await _create_category(client, owner, "Enclosures")
    spec = await _create_specification(
        client, owner, category["id"], name="IP Rating", unit=None, datatype="enum"
    )
    # enum_options isn't part of the minimal test helper payload — verify
    # the field exists and is settable via a direct request.
    res = await client.post(
        f"/api/v1/product-categories/{category['id']}/specifications",
        json={
            "name": "IP Rating 2",
            "datatype": "enum",
            "enum_options": ["IP54", "IP65"],
            "required": False,
        },
        headers=_auth_headers(owner),
    )
    assert res.status_code == 201
    assert res.json()["data"]["enum_options"] == ["IP54", "IP65"]
    assert spec["datatype"] == "enum"


# --------------------------------------------------------------------------
# Product + ProductAttribute (EAV)
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_product_with_attributes(client):
    owner = await _register_verified(client, "product-create@example.com")
    category = await _create_category(client, owner, "Motors A")
    spec = await _create_specification(client, owner, category["id"], name="Power", unit="kW")

    product = await _create_product(
        client, owner, category["id"], attributes=[{"specification_id": spec["id"], "value": "5.5"}]
    )
    assert product["status"] == "draft"  # Phase 4A Section 6 — never auto-published
    assert len(product["attributes"]) == 1
    assert product["attributes"][0]["specification_name"] == "Power"
    assert product["attributes"][0]["unit"] == "kW"
    assert product["attributes"][0]["value"] == "5.5"
    assert product["category"]["id"] == category["id"]


@pytest.mark.asyncio
async def test_product_rejects_specification_from_a_different_category(client):
    """The EAV validation — a Motor product cannot silently accept a
    Pump-only specification value."""
    owner = await _register_verified(client, "product-wrongspec@example.com")
    motors = await _create_category(client, owner, "Motors B")
    pumps = await _create_category(client, owner, "Pumps B")
    pump_spec = await _create_specification(client, owner, pumps["id"], name="Flow Rate")

    res = await client.post(
        "/api/v1/products",
        json={
            "name": "Mismatched Motor",
            "category_id": motors["id"],
            "attributes": [{"specification_id": pump_spec["id"], "value": "100"}],
        },
        headers=_auth_headers(owner),
    )
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "INVALID_SPECIFICATION"


@pytest.mark.asyncio
async def test_create_product_requires_auth(client):
    res = await client.post(
        "/api/v1/products",
        json={"name": "X", "category_id": "00000000-0000-0000-0000-000000000000"},
    )
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_product_slug_is_unique_and_url_safe(client):
    owner = await _register_verified(client, "product-slug@example.com")
    category = await _create_category(client, owner, "Slug Test Category")
    p1 = await _create_product(client, owner, category["id"], name="Same Name")
    p2 = await _create_product(client, owner, category["id"], name="Same Name")
    assert p1["slug"] != p2["slug"]
    assert p2["slug"] == "same-name-2"


@pytest.mark.asyncio
async def test_get_product_by_slug(client):
    owner = await _register_verified(client, "product-byslug@example.com")
    category = await _create_category(client, owner, "Slug Lookup Category")
    product = await _create_product(client, owner, category["id"], name="Findable Product")
    res = await client.get(f"/api/v1/products/slug/{product['slug']}")
    assert res.status_code == 200
    assert res.json()["data"]["id"] == product["id"]


@pytest.mark.asyncio
async def test_update_product_replaces_attributes(client):
    owner = await _register_verified(client, "product-update@example.com")
    category = await _create_category(client, owner, "Update Category")
    spec = await _create_specification(client, owner, category["id"], name="Power", unit="kW")
    product = await _create_product(
        client, owner, category["id"], attributes=[{"specification_id": spec["id"], "value": "5.5"}]
    )

    res = await client.patch(
        f"/api/v1/products/{product['id']}",
        json={"attributes": [{"specification_id": spec["id"], "value": "7.5"}]},
        headers=_auth_headers(owner),
    )
    assert res.status_code == 200
    assert res.json()["data"]["attributes"][0]["value"] == "7.5"
    assert len(res.json()["data"]["attributes"]) == 1  # replaced, not appended


# --------------------------------------------------------------------------
# Search — only PUBLISHED products are discoverable
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_draft_products_are_not_searchable(client):
    owner = await _register_verified(client, "search-draft@example.com")
    category = await _create_category(client, owner, "Draft Search Category")
    await _create_product(client, owner, category["id"], name="Unpublished Widget")

    res = await client.get("/api/v1/products/search", params={"name": "Unpublished Widget"})
    assert res.status_code == 200
    assert res.json()["data"]["total"] == 0


@pytest.mark.asyncio
async def test_published_product_is_searchable_by_name_and_industry(client):
    owner = await _register_verified(client, "search-published@example.com")
    category = await _create_category(client, owner, "Search Category")
    product = await _create_product(client, owner, category["id"], name="Searchable CNC Router")
    await _publish(client, owner, product["id"])

    by_name = await client.get("/api/v1/products/search", params={"name": "CNC Router"})
    assert by_name.json()["data"]["total"] == 1

    by_industry = await client.get("/api/v1/products/search", params={"industry": "Manufacturing"})
    assert any(item["id"] == product["id"] for item in by_industry.json()["data"]["items"])


# --------------------------------------------------------------------------
# Offering — the ABSOLUTE RULE: many companies, one Product, zero duplication
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_multiple_companies_can_offer_the_same_product_without_duplicating_it(client):
    owner = await _register_verified(client, "offering-shared-owner@example.com")
    category = await _create_category(client, owner, "Shared Product Category")
    product = await _create_product(client, owner, category["id"], name="Shared Bearing")
    await _publish(client, owner, product["id"])

    async def _offer_as(owner_data: dict, company: dict, role: str = "manufacturer") -> dict:
        res = await client.post(
            f"/api/v1/companies/{company['id']}/offerings",
            json={"product_id": product["id"], "role": role},
            headers=_auth_headers(owner_data),
        )
        assert res.status_code == 201, res.text
        return res.json()["data"]

    owner_a_data, company_a = await _create_verified_company(
        client, "offer-a2@example.com", "Company A2"
    )
    owner_b_data, company_b = await _create_verified_company(
        client, "offer-b2@example.com", "Company B2"
    )
    owner_c_data, company_c = await _create_verified_company(
        client, "offer-c2@example.com", "Company C2"
    )

    await _offer_as(owner_a_data, company_a)
    await _offer_as(owner_b_data, company_b, role="supplier")
    await _offer_as(owner_c_data, company_c, role="distributor")

    # Exactly one Product row exists (same id throughout — never duplicated)
    detail = await client.get(f"/api/v1/products/{product['id']}")
    assert detail.status_code == 200
    assert detail.json()["data"]["id"] == product["id"]

    offerings = await client.get(f"/api/v1/products/{product['id']}/offerings")
    assert offerings.json()["data"]["total"] == 3
    roles = {o["role"] for o in offerings.json()["data"]["items"]}
    assert roles == {"manufacturer", "supplier", "distributor"}
    company_ids = {o["company"]["id"] for o in offerings.json()["data"]["items"]}
    assert company_ids == {company_a["id"], company_b["id"], company_c["id"]}


@pytest.mark.asyncio
async def test_offering_role_is_per_offering_not_per_company(client):
    """A company can be a manufacturer for one product and a distributor
    for another — the exact refinement Phase 4A Section 2 requires."""
    owner = await _register_verified(client, "role-per-offering-owner@example.com")
    category = await _create_category(client, owner, "Role Per Offering Category")
    product_a = await _create_product(client, owner, category["id"], name="Product Role A")
    product_b = await _create_product(client, owner, category["id"], name="Product Role B")
    await _publish(client, owner, product_a["id"])
    await _publish(client, owner, product_b["id"])

    company_owner, company = await _create_verified_company(
        client, "role-per-offering@example.com", "Multi-Role Co"
    )

    res_a = await client.post(
        f"/api/v1/companies/{company['id']}/offerings",
        json={"product_id": product_a["id"], "role": "manufacturer"},
        headers=_auth_headers(company_owner),
    )
    res_b = await client.post(
        f"/api/v1/companies/{company['id']}/offerings",
        json={"product_id": product_b["id"], "role": "distributor"},
        headers=_auth_headers(company_owner),
    )
    assert res_a.status_code == 201
    assert res_b.status_code == 201
    assert res_a.json()["data"]["role"] == "manufacturer"
    assert res_b.json()["data"]["role"] == "distributor"


@pytest.mark.asyncio
async def test_duplicate_offering_is_rejected(client):
    owner = await _register_verified(client, "dup-offering-owner@example.com")
    category = await _create_category(client, owner, "Dup Offering Category")
    product = await _create_product(client, owner, category["id"], name="Dup Offering Product")
    await _publish(client, owner, product["id"])

    company_owner, company = await _create_verified_company(
        client, "dup-offering@example.com", "Dup Co"
    )
    first = await client.post(
        f"/api/v1/companies/{company['id']}/offerings",
        json={"product_id": product["id"], "role": "manufacturer"},
        headers=_auth_headers(company_owner),
    )
    assert first.status_code == 201

    second = await client.post(
        f"/api/v1/companies/{company['id']}/offerings",
        json={"product_id": product["id"], "role": "manufacturer"},
        headers=_auth_headers(company_owner),
    )
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "DUPLICATE_OFFERING"


@pytest.mark.asyncio
async def test_offering_mutation_requires_editor_role(client):
    """A Viewer-level member cannot create an offering for the company —
    reuses company_authorization's require_company_role(EDITOR) exactly,
    same as every Module 3B mutation endpoint."""
    owner = await _register_verified(client, "offering-viewer-owner@example.com")
    category = await _create_category(client, owner, "Viewer Test Category")
    product = await _create_product(client, owner, category["id"], name="Viewer Test Product")
    await _publish(client, owner, product["id"])

    company_owner, company = await _create_verified_company(
        client, "offering-viewer@example.com", "Viewer Test Co"
    )
    viewer = await _register_verified(client, "offering-viewer-member@example.com")

    invite_res = await client.post(
        f"/api/v1/companies/{company['id']}/members",
        json={"user_id": viewer["user"]["id"], "role": "viewer"},
        headers=_auth_headers(company_owner),
    )
    assert invite_res.status_code in (200, 201), invite_res.text

    res = await client.post(
        f"/api/v1/companies/{company['id']}/offerings",
        json={"product_id": product["id"], "role": "manufacturer"},
        headers=_auth_headers(viewer),
    )
    assert res.status_code == 403


@pytest.mark.asyncio
async def test_offering_for_nonexistent_product_404s(client):
    owner, company = await _create_verified_company(
        client, "offering-noproduct@example.com", "No Product Co"
    )
    res = await client.post(
        f"/api/v1/companies/{company['id']}/offerings",
        json={"product_id": "00000000-0000-0000-0000-000000000000", "role": "manufacturer"},
        headers=_auth_headers(owner),
    )
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "PRODUCT_NOT_FOUND"


@pytest.mark.asyncio
async def test_update_and_delete_offering(client):
    owner = await _register_verified(client, "offering-update-owner@example.com")
    category = await _create_category(client, owner, "Offering Update Category")
    product = await _create_product(client, owner, category["id"], name="Offering Update Product")
    await _publish(client, owner, product["id"])
    company_owner, company = await _create_verified_company(
        client, "offering-update@example.com", "Update Co"
    )

    create_res = await client.post(
        f"/api/v1/companies/{company['id']}/offerings",
        json={"product_id": product["id"], "role": "supplier", "lead_time": "4 weeks"},
        headers=_auth_headers(company_owner),
    )
    offering_id = create_res.json()["data"]["id"]

    update_res = await client.patch(
        f"/api/v1/companies/{company['id']}/offerings/{offering_id}",
        json={"lead_time": "2 weeks"},
        headers=_auth_headers(company_owner),
    )
    assert update_res.status_code == 200
    assert update_res.json()["data"]["lead_time"] == "2 weeks"

    delete_res = await client.delete(
        f"/api/v1/companies/{company['id']}/offerings/{offering_id}",
        headers=_auth_headers(company_owner),
    )
    assert delete_res.status_code == 204

    offerings_after = await client.get(f"/api/v1/products/{product['id']}/offerings")
    assert offerings_after.json()["data"]["total"] == 0


@pytest.mark.asyncio
async def test_cannot_mutate_another_companys_offering(client):
    """IDOR check — the exact class of bug company_authorization.py's
    module docstring exists to prevent."""
    owner_1, company_1 = await _create_verified_company(
        client, "idor-company1@example.com", "IDOR Co 1"
    )
    owner_2, company_2 = await _create_verified_company(
        client, "idor-company2@example.com", "IDOR Co 2"
    )
    category = await _create_category(client, owner_1, "IDOR Category")
    product = await _create_product(client, owner_1, category["id"], name="IDOR Product")
    await _publish(client, owner_1, product["id"])

    create_res = await client.post(
        f"/api/v1/companies/{company_1['id']}/offerings",
        json={"product_id": product["id"], "role": "manufacturer"},
        headers=_auth_headers(owner_1),
    )
    offering_id = create_res.json()["data"]["id"]

    # owner_2 tries to mutate company_1's offering via company_2's own
    # (legitimate) membership — must fail, not succeed via IDOR.
    attack_res = await client.patch(
        f"/api/v1/companies/{company_2['id']}/offerings/{offering_id}",
        json={"lead_time": "1 day"},
        headers=_auth_headers(owner_2),
    )
    assert attack_res.status_code == 404  # offering doesn't belong to company_2
