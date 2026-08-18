"""
Requirement Intelligence foundation tests — Module 7A-1. Covers
Requirement/RequirementSpecificationCriterion creation, retrieval,
validation (operator/value shape, category/specification existence,
operator/datatype compatibility), relationship integrity, and
ownership-scoped authorization. Reuses test_product_graph.py's and
test_companies.py's established fixtures — Requirement creation needs
only an authenticated user (mirrors app.api.v1.products.create_product's
own precedent), not an admin.
"""

import pytest

from tests.test_companies import _auth_headers, _register_verified
from tests.test_product_graph import _create_category, _create_specification


def _requirement_payload(**overrides) -> dict:
    payload = {"raw_query": "Need a 5kW industrial motor supplier in Germany"}
    payload.update(overrides)
    return payload


async def _create_requirement(client, user, **overrides) -> dict:
    res = await client.post(
        "/api/v1/requirements", json=_requirement_payload(**overrides), headers=_auth_headers(user)
    )
    assert res.status_code == 201, res.text
    return res.json()["data"]


# --------------------------------------------------------------------------
# Creation
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_requirement_requires_auth(client):
    res = await client.post("/api/v1/requirements", json=_requirement_payload())
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_create_minimal_requirement(client):
    user = await _register_verified(client, "req-minimal@example.com")
    data = await _create_requirement(client, user)
    assert data["raw_query"] == "Need a 5kW industrial motor supplier in Germany"
    assert data["status"] == "submitted"  # server-set, never client-chosen in this phase
    assert data["product_category_id"] is None
    assert data["criteria"] == []
    assert data["created_by"] == user["user"]["id"]


@pytest.mark.asyncio
async def test_create_full_requirement_captures_every_field(client):
    user = await _register_verified(client, "req-full@example.com")
    data = await _create_requirement(
        client,
        user,
        industry="Industrial Machinery",
        country="Germany",
        state="Bavaria",
        city="Munich",
        certifications=["ISO 9001", "CE"],
        quantity="500 units",
        budget="$50,000",
        timeline="Q3 2026",
        extraction_confidence=0.82,
    )
    assert data["industry"] == "Industrial Machinery"
    assert data["country"] == "Germany"
    assert data["state"] == "Bavaria"
    assert data["city"] == "Munich"
    assert data["certifications"] == ["ISO 9001", "CE"]
    assert data["quantity"] == "500 units"
    assert data["budget"] == "$50,000"
    assert data["timeline"] == "Q3 2026"
    assert data["extraction_confidence"] == 0.82


# --------------------------------------------------------------------------
# Specification criteria — creation, all operators
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_requirement_with_criteria_all_operators(client):
    user = await _register_verified(client, "req-criteria@example.com")
    category = await _create_category(client, user, "Motors")
    power = await _create_specification(
        client, user, category["id"], name="Power", datatype="number"
    )
    ip_rating = await _create_specification(
        client, user, category["id"], name="IP Rating", datatype="enum", unit=None
    )
    voltage = await _create_specification(
        client, user, category["id"], name="Voltage", datatype="range", unit="V"
    )

    data = await _create_requirement(
        client,
        user,
        product_category_id=category["id"],
        criteria=[
            {"specification_id": power["id"], "operator": "gte", "value": 5.0},
            {"specification_id": ip_rating["id"], "operator": "in", "value": ["IP54", "IP65"]},
            {"specification_id": voltage["id"], "operator": "range", "value": [110, 240]},
        ],
    )
    assert len(data["criteria"]) == 3
    by_spec_name = {c["specification_name"]: c for c in data["criteria"]}
    assert by_spec_name["Power"]["operator"] == "gte"
    assert by_spec_name["Power"]["value"] == 5.0
    assert by_spec_name["IP Rating"]["operator"] == "in"
    assert by_spec_name["IP Rating"]["value"] == ["IP54", "IP65"]
    assert by_spec_name["Voltage"]["operator"] == "range"
    assert by_spec_name["Voltage"]["value"] == [110, 240]


@pytest.mark.asyncio
async def test_eq_operator_accepts_a_single_scalar(client):
    user = await _register_verified(client, "req-eq@example.com")
    category = await _create_category(client, user, "Fasteners")
    material = await _create_specification(
        client, user, category["id"], name="Material", datatype="text", unit=None
    )
    data = await _create_requirement(
        client,
        user,
        product_category_id=category["id"],
        criteria=[
            {"specification_id": material["id"], "operator": "eq", "value": "Stainless Steel"}
        ],
    )
    assert data["criteria"][0]["value"] == "Stainless Steel"


# --------------------------------------------------------------------------
# Retrieval
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_requirement_by_owner(client):
    user = await _register_verified(client, "req-get@example.com")
    created = await _create_requirement(client, user)
    res = await client.get(f"/api/v1/requirements/{created['id']}", headers=_auth_headers(user))
    assert res.status_code == 200
    assert res.json()["data"]["id"] == created["id"]


@pytest.mark.asyncio
async def test_get_requirement_requires_auth(client):
    user = await _register_verified(client, "req-get-noauth@example.com")
    created = await _create_requirement(client, user)
    res = await client.get(f"/api/v1/requirements/{created['id']}")
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_get_nonexistent_requirement_404s(client):
    user = await _register_verified(client, "req-get-missing@example.com")
    res = await client.get(
        "/api/v1/requirements/00000000-0000-0000-0000-000000000000", headers=_auth_headers(user)
    )
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "REQUIREMENT_NOT_FOUND"


# --------------------------------------------------------------------------
# Authorization — ownership-scoped, 404 not 403 for a non-owner
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_requirement_owned_by_someone_else_404s_not_403(client):
    owner = await _register_verified(client, "req-owner@example.com")
    other = await _register_verified(client, "req-other@example.com")
    created = await _create_requirement(client, owner)
    res = await client.get(f"/api/v1/requirements/{created['id']}", headers=_auth_headers(other))
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "REQUIREMENT_NOT_FOUND"


# --------------------------------------------------------------------------
# Validation — nonexistent category/specification
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_nonexistent_category_404s(client):
    user = await _register_verified(client, "req-badcat@example.com")
    res = await client.post(
        "/api/v1/requirements",
        json=_requirement_payload(product_category_id="00000000-0000-0000-0000-000000000000"),
        headers=_auth_headers(user),
    )
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "CATEGORY_NOT_FOUND"


@pytest.mark.asyncio
async def test_nonexistent_specification_rejected(client):
    user = await _register_verified(client, "req-badspec@example.com")
    category = await _create_category(client, user, "Valves")
    res = await client.post(
        "/api/v1/requirements",
        json=_requirement_payload(
            product_category_id=category["id"],
            criteria=[
                {
                    "specification_id": "00000000-0000-0000-0000-000000000000",
                    "operator": "eq",
                    "value": "x",
                }
            ],
        ),
        headers=_auth_headers(user),
    )
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "INVALID_SPECIFICATION"


@pytest.mark.asyncio
async def test_specification_from_a_different_category_rejected(client):
    user = await _register_verified(client, "req-crosscat@example.com")
    category_a = await _create_category(client, user, "Category A")
    category_b = await _create_category(client, user, "Category B")
    spec_in_b = await _create_specification(client, user, category_b["id"], name="Only in B")

    res = await client.post(
        "/api/v1/requirements",
        json=_requirement_payload(
            product_category_id=category_a["id"],
            criteria=[{"specification_id": spec_in_b["id"], "operator": "eq", "value": "x"}],
        ),
        headers=_auth_headers(user),
    )
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "INVALID_SPECIFICATION"


@pytest.mark.asyncio
async def test_criteria_without_category_rejected(client):
    user = await _register_verified(client, "req-nocategory@example.com")
    res = await client.post(
        "/api/v1/requirements",
        json=_requirement_payload(
            criteria=[
                {
                    "specification_id": "00000000-0000-0000-0000-000000000000",
                    "operator": "eq",
                    "value": "x",
                }
            ]
        ),
        headers=_auth_headers(user),
    )
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "CATEGORY_REQUIRED_FOR_CRITERIA"


@pytest.mark.asyncio
async def test_duplicate_specification_in_criteria_rejected(client):
    user = await _register_verified(client, "req-dupe@example.com")
    category = await _create_category(client, user, "Pumps Dup")
    spec = await _create_specification(client, user, category["id"], name="Flow Rate")
    res = await client.post(
        "/api/v1/requirements",
        json=_requirement_payload(
            product_category_id=category["id"],
            criteria=[
                {"specification_id": spec["id"], "operator": "eq", "value": "10"},
                {"specification_id": spec["id"], "operator": "gte", "value": 5},
            ],
        ),
        headers=_auth_headers(user),
    )
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "INVALID_SPECIFICATION"


# --------------------------------------------------------------------------
# Validation — operator/datatype compatibility
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_numeric_operator_against_text_specification_rejected(client):
    user = await _register_verified(client, "req-baddatatype@example.com")
    category = await _create_category(client, user, "Textiles")
    color = await _create_specification(
        client, user, category["id"], name="Color", datatype="text", unit=None
    )
    res = await client.post(
        "/api/v1/requirements",
        json=_requirement_payload(
            product_category_id=category["id"],
            criteria=[{"specification_id": color["id"], "operator": "gte", "value": 5}],
        ),
        headers=_auth_headers(user),
    )
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "INVALID_CRITERION_VALUE"


# --------------------------------------------------------------------------
# Validation — operator/value shape (schema-layer, 422 from FastAPI itself)
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_range_operator_requires_exactly_two_numbers(client):
    user = await _register_verified(client, "req-rangeshape@example.com")
    category = await _create_category(client, user, "Cables")
    spec = await _create_specification(
        client, user, category["id"], name="Length", datatype="range"
    )
    res = await client.post(
        "/api/v1/requirements",
        json=_requirement_payload(
            product_category_id=category["id"],
            criteria=[{"specification_id": spec["id"], "operator": "range", "value": [1]}],
        ),
        headers=_auth_headers(user),
    )
    assert res.status_code == 422


@pytest.mark.asyncio
async def test_range_operator_requires_min_less_than_or_equal_max(client):
    user = await _register_verified(client, "req-rangeminmax@example.com")
    category = await _create_category(client, user, "Cables Two")
    spec = await _create_specification(
        client, user, category["id"], name="Length2", datatype="range"
    )
    res = await client.post(
        "/api/v1/requirements",
        json=_requirement_payload(
            product_category_id=category["id"],
            criteria=[{"specification_id": spec["id"], "operator": "range", "value": [10, 1]}],
        ),
        headers=_auth_headers(user),
    )
    assert res.status_code == 422


@pytest.mark.asyncio
async def test_in_operator_requires_non_empty_list(client):
    user = await _register_verified(client, "req-inshape@example.com")
    category = await _create_category(client, user, "Bolts")
    spec = await _create_specification(
        client, user, category["id"], name="Size", datatype="enum", unit=None
    )
    res = await client.post(
        "/api/v1/requirements",
        json=_requirement_payload(
            product_category_id=category["id"],
            criteria=[{"specification_id": spec["id"], "operator": "in", "value": []}],
        ),
        headers=_auth_headers(user),
    )
    assert res.status_code == 422


@pytest.mark.asyncio
async def test_gte_operator_rejects_a_list_value(client):
    user = await _register_verified(client, "req-gteshape@example.com")
    category = await _create_category(client, user, "Gauges")
    spec = await _create_specification(
        client, user, category["id"], name="Pressure", datatype="number"
    )
    res = await client.post(
        "/api/v1/requirements",
        json=_requirement_payload(
            product_category_id=category["id"],
            criteria=[{"specification_id": spec["id"], "operator": "gte", "value": [1, 2]}],
        ),
        headers=_auth_headers(user),
    )
    assert res.status_code == 422


@pytest.mark.asyncio
async def test_eq_operator_rejects_a_list_value(client):
    user = await _register_verified(client, "req-eqshape@example.com")
    category = await _create_category(client, user, "Sensors")
    spec = await _create_specification(
        client, user, category["id"], name="Type", datatype="text", unit=None
    )
    res = await client.post(
        "/api/v1/requirements",
        json=_requirement_payload(
            product_category_id=category["id"],
            criteria=[{"specification_id": spec["id"], "operator": "eq", "value": ["a", "b"]}],
        ),
        headers=_auth_headers(user),
    )
    assert res.status_code == 422


@pytest.mark.asyncio
async def test_invalid_operator_value_rejected_by_enum(client):
    user = await _register_verified(client, "req-badop@example.com")
    category = await _create_category(client, user, "Screws")
    spec = await _create_specification(
        client, user, category["id"], name="Length3", datatype="number"
    )
    res = await client.post(
        "/api/v1/requirements",
        json=_requirement_payload(
            product_category_id=category["id"],
            criteria=[{"specification_id": spec["id"], "operator": "contains", "value": "x"}],
        ),
        headers=_auth_headers(user),
    )
    assert res.status_code == 422


# --------------------------------------------------------------------------
# Relationship integrity
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_requirement_criteria_relationship_integrity():
    """
    Direct service-layer check (not HTTP): after creation, every
    criterion's requirement_id points back at the parent, and the
    specification relationship is loaded and correct — proves the
    selectinload/back_populates wiring in app.models.requirement is
    real, not just superficially passing through the API layer.
    """
    import uuid

    from app.core.security import hash_password
    from app.db.session import AsyncSessionLocal
    from app.models.product_specification import SpecificationDataType
    from app.models.user import Role, User
    from app.schemas.requirement import RequirementCreate, RequirementSpecificationCriterionInput
    from app.services import product_service, requirement_service

    async with AsyncSessionLocal() as db:
        user = User(
            email=f"req-integrity-{uuid.uuid4().hex[:8]}@example.com",
            hashed_password=hash_password("irrelevant"),
            full_name="Integrity Test User",
            role=Role.VIEWER,
            is_email_verified=True,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)

        category = await product_service.create_category(db, "Integrity Category", None)
        spec = await product_service.create_specification(
            db,
            category.id,
            name="Weight",
            unit="kg",
            datatype=SpecificationDataType.NUMBER,
            enum_options=None,
            required=False,
        )

        requirement = await requirement_service.create_requirement(
            db,
            RequirementCreate(
                raw_query="Integrity check",
                product_category_id=category.id,
                criteria=[
                    RequirementSpecificationCriterionInput(
                        specification_id=spec.id, operator="gte", value=1.0
                    )
                ],
            ),
            created_by=user.id,
        )

        assert len(requirement.criteria) == 1
        criterion = requirement.criteria[0]
        assert criterion.requirement_id == requirement.id
        assert criterion.specification.id == spec.id
        assert criterion.specification.name == "Weight"
