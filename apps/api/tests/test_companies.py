"""
Company Core tests — Module 3A. Covers creation/slug generation,
CRUD authorization (Owner/Admin/Editor/Viewer graduated permissions),
the single-Owner invariant, IDOR protection, and public search/profile
endpoints. Membership lifecycle (invite/accept/remove/ownership
transfer) is covered separately in tests/test_company_members.py.
"""

from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app.db.session import AsyncSessionLocal
from app.models.user import User


def _register_payload(email: str, full_name: str = "Test User") -> dict:
    return {"email": email, "password": "correct-horse-9", "full_name": full_name}


async def _register_verified(client, email: str, full_name: str = "Test User") -> dict:
    """
    Registers a user and marks them email-verified directly via the DB —
    bypassing the token flow (already covered by
    tests/test_email_verification.py) since most company tests need a
    verified user as a precondition, not as what's under test. Returns
    the register response's `data` payload (tokens + user).
    """
    res = await client.post("/api/v1/auth/register", json=_register_payload(email, full_name))
    data = res.json()["data"]
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(User).where(User.id == data["user"]["id"]))
        user = result.scalar_one()
        user.is_email_verified = True
        user.email_verified_at = datetime.now(UTC)
        await db.commit()
    return data


def _auth_headers(data: dict) -> dict:
    return {"Authorization": f"Bearer {data['access_token']}"}


def _company_payload(name: str = "Acme Industrial Co") -> dict:
    return {
        "name": name,
        "legal_name": f"{name} Pvt Ltd",
        "description": "We make things.",
        "industry": "Manufacturing",
        "website": "https://acme.example.com",
        "email": "contact@acme.example.com",
        "phone": "+1-555-0100",
        "year_established": 1998,
        "company_size": "51-200",
        "country": "India",
        "state": "Maharashtra",
        "city": "Pune",
    }


# --------------------------------------------------------------------------
# Creation, slugs, email-verification gate
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unverified_user_cannot_create_a_company(client):
    res = await client.post(
        "/api/v1/auth/register", json=_register_payload("unverified@example.com")
    )
    tokens = res.json()["data"]
    response = await client.post(
        "/api/v1/companies", json=_company_payload(), headers=_auth_headers(tokens)
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "EMAIL_NOT_VERIFIED"


@pytest.mark.asyncio
async def test_creating_a_company_makes_the_creator_the_owner(client):
    user = await _register_verified(client, "owner@example.com")
    response = await client.post(
        "/api/v1/companies", json=_company_payload(), headers=_auth_headers(user)
    )
    assert response.status_code == 201
    body = response.json()["data"]
    assert body["my_role"] == "owner"
    assert body["member_count"] == 1
    assert body["status"] == "active"
    assert body["verification_status"] == "unverified"


@pytest.mark.asyncio
async def test_slug_is_generated_from_name(client):
    user = await _register_verified(client, "slugtest@example.com")
    response = await client.post(
        "/api/v1/companies",
        json=_company_payload("Acme Industrial Co"),
        headers=_auth_headers(user),
    )
    assert response.json()["data"]["slug"] == "acme-industrial-co"


@pytest.mark.asyncio
async def test_duplicate_company_names_get_distinct_slugs(client):
    user_a = await _register_verified(client, "dupe-a@example.com")
    user_b = await _register_verified(client, "dupe-b@example.com")

    res_a = await client.post(
        "/api/v1/companies", json=_company_payload("Same Name Ltd"), headers=_auth_headers(user_a)
    )
    res_b = await client.post(
        "/api/v1/companies", json=_company_payload("Same Name Ltd"), headers=_auth_headers(user_b)
    )
    slug_a = res_a.json()["data"]["slug"]
    slug_b = res_b.json()["data"]["slug"]
    assert slug_a == "same-name-ltd"
    assert slug_b == "same-name-ltd-2"
    assert slug_a != slug_b


@pytest.mark.asyncio
async def test_a_user_may_own_multiple_companies(client):
    """See docs/domain/08-business-rules.md."""
    user = await _register_verified(client, "multi-owner@example.com")
    res1 = await client.post(
        "/api/v1/companies", json=_company_payload("First Co"), headers=_auth_headers(user)
    )
    res2 = await client.post(
        "/api/v1/companies", json=_company_payload("Second Co"), headers=_auth_headers(user)
    )
    assert res1.status_code == 201
    assert res2.status_code == 201

    my_companies = await client.get("/api/v1/companies", headers=_auth_headers(user))
    names = {c["name"] for c in my_companies.json()["data"]}
    assert names == {"First Co", "Second Co"}


# --------------------------------------------------------------------------
# Reads: detail (members-only), public profile, search
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_company_requires_membership_and_404s_for_non_members(client):
    """IDOR protection: a non-member gets 404, not 403 (doesn't confirm the company exists to them)."""
    owner = await _register_verified(client, "detail-owner@example.com")
    outsider = await _register_verified(client, "detail-outsider@example.com")
    create_res = await client.post(
        "/api/v1/companies", json=_company_payload(), headers=_auth_headers(owner)
    )
    company_id = create_res.json()["data"]["id"]

    owner_view = await client.get(f"/api/v1/companies/{company_id}", headers=_auth_headers(owner))
    assert owner_view.status_code == 200

    outsider_view = await client.get(
        f"/api/v1/companies/{company_id}", headers=_auth_headers(outsider)
    )
    assert outsider_view.status_code == 404


@pytest.mark.asyncio
async def test_get_company_requires_authentication(client):
    response = await client.get("/api/v1/companies/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_update_company_requires_authentication_even_for_nonexistent_company(client):
    """Regression: unauthenticated must always 401, never race against the CompanyOr404 lookup's 404."""
    response = await client.patch(
        "/api/v1/companies/00000000-0000-0000-0000-000000000000", json={"description": "x"}
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_delete_company_requires_authentication_even_for_nonexistent_company(client):
    response = await client.delete("/api/v1/companies/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_add_member_requires_authentication_even_for_nonexistent_company(client):
    response = await client.post(
        "/api/v1/companies/00000000-0000-0000-0000-000000000000/members",
        json={"user_id": "00000000-0000-0000-0000-000000000001", "role": "viewer"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_public_profile_by_slug_requires_no_authentication(client):
    owner = await _register_verified(client, "public-owner@example.com")
    create_res = await client.post(
        "/api/v1/companies", json=_company_payload("Public Co"), headers=_auth_headers(owner)
    )
    slug = create_res.json()["data"]["slug"]

    response = await client.get(f"/api/v1/companies/slug/{slug}")
    assert response.status_code == 200
    body = response.json()["data"]
    assert body["name"] == "Public Co"
    assert body["member_count"] == 1
    # Public profile must not leak internal-only fields.
    assert "legal_name" not in body
    assert "gst_number" not in body
    assert "email" not in body


@pytest.mark.asyncio
async def test_public_profile_404s_for_unknown_slug(client):
    response = await client.get("/api/v1/companies/slug/does-not-exist")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_search_finds_companies_by_name_and_is_public(client):
    owner = await _register_verified(client, "search-owner@example.com")
    await client.post(
        "/api/v1/companies",
        json=_company_payload("Searchable Widgets Inc"),
        headers=_auth_headers(owner),
    )

    response = await client.get("/api/v1/companies/search?name=Searchable")
    assert response.status_code == 200
    body = response.json()["data"]
    assert body["total"] >= 1
    assert any(c["name"] == "Searchable Widgets Inc" for c in body["items"])


@pytest.mark.asyncio
async def test_search_filters_by_city_and_country(client):
    owner = await _register_verified(client, "search-geo@example.com")
    payload = _company_payload("Geo Filtered Co")
    payload["city"] = "Ahmedabad"
    payload["country"] = "India"
    await client.post("/api/v1/companies", json=payload, headers=_auth_headers(owner))

    response = await client.get("/api/v1/companies/search?city=Ahmedabad&country=India")
    body = response.json()["data"]
    assert any(c["name"] == "Geo Filtered Co" for c in body["items"])

    no_match = await client.get("/api/v1/companies/search?city=Nonexistentville")
    assert no_match.json()["data"]["total"] == 0


@pytest.mark.asyncio
async def test_search_pagination_shape(client):
    owner = await _register_verified(client, "search-page@example.com")
    for i in range(3):
        await client.post(
            "/api/v1/companies",
            json=_company_payload(f"Paginated Co {i}"),
            headers=_auth_headers(owner),
        )

    response = await client.get("/api/v1/companies/search?page=1&page_size=2")
    body = response.json()["data"]
    assert len(body["items"]) == 2
    assert body["page"] == 1
    assert body["page_size"] == 2
    assert body["total_pages"] >= 1


# --------------------------------------------------------------------------
# Update authorization (graduated: Owner/Admin/Editor/Viewer)
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_owner_can_update_legal_name(client):
    owner = await _register_verified(client, "update-owner@example.com")
    create_res = await client.post(
        "/api/v1/companies", json=_company_payload(), headers=_auth_headers(owner)
    )
    company_id = create_res.json()["data"]["id"]

    response = await client.patch(
        f"/api/v1/companies/{company_id}",
        json={"legal_name": "New Legal Name LLC"},
        headers=_auth_headers(owner),
    )
    assert response.status_code == 200
    assert response.json()["data"]["legal_name"] == "New Legal Name LLC"


@pytest.mark.asyncio
async def test_viewer_cannot_update_company(client):
    owner = await _register_verified(client, "viewer-update-owner@example.com")
    viewer = await _register_verified(client, "viewer-update-viewer@example.com")
    create_res = await client.post(
        "/api/v1/companies", json=_company_payload(), headers=_auth_headers(owner)
    )
    company_id = create_res.json()["data"]["id"]

    add_res = await client.post(
        f"/api/v1/companies/{company_id}/members",
        json={"user_id": viewer["user"]["id"], "role": "viewer"},
        headers=_auth_headers(owner),
    )
    member_id = add_res.json()["data"]["id"]
    await client.patch(
        f"/api/v1/companies/{company_id}/members/{member_id}",
        json={"status": "active"},
        headers=_auth_headers(viewer),
    )

    response = await client.patch(
        f"/api/v1/companies/{company_id}",
        json={"description": "hijacked"},
        headers=_auth_headers(viewer),
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "INSUFFICIENT_COMPANY_ROLE"


@pytest.mark.asyncio
async def test_editor_can_update_description_but_not_legal_name(client):
    owner = await _register_verified(client, "editor-owner@example.com")
    editor = await _register_verified(client, "editor-user@example.com")
    create_res = await client.post(
        "/api/v1/companies", json=_company_payload(), headers=_auth_headers(owner)
    )
    company_id = create_res.json()["data"]["id"]
    original_legal_name = create_res.json()["data"]["legal_name"]

    add_res = await client.post(
        f"/api/v1/companies/{company_id}/members",
        json={"user_id": editor["user"]["id"], "role": "editor"},
        headers=_auth_headers(owner),
    )
    member_id = add_res.json()["data"]["id"]
    await client.patch(
        f"/api/v1/companies/{company_id}/members/{member_id}",
        json={"status": "active"},
        headers=_auth_headers(editor),
    )

    response = await client.patch(
        f"/api/v1/companies/{company_id}",
        json={"description": "Updated by editor", "legal_name": "Should Not Change LLC"},
        headers=_auth_headers(editor),
    )
    assert response.status_code == 200
    body = response.json()["data"]
    assert body["description"] == "Updated by editor"
    assert (
        body["legal_name"] == original_legal_name
    )  # silently ignored, not an error — see docs/domain/09 fn2


@pytest.mark.asyncio
async def test_outsider_cannot_update_a_company_they_are_not_a_member_of(client):
    owner = await _register_verified(client, "outsider-update-owner@example.com")
    outsider = await _register_verified(client, "outsider-update-outsider@example.com")
    create_res = await client.post(
        "/api/v1/companies", json=_company_payload(), headers=_auth_headers(owner)
    )
    company_id = create_res.json()["data"]["id"]

    response = await client.patch(
        f"/api/v1/companies/{company_id}",
        json={"description": "hijacked"},
        headers=_auth_headers(outsider),
    )
    assert response.status_code == 404  # IDOR-safe: not a member at all, not even a 403


# --------------------------------------------------------------------------
# Delete (Owner-only, soft delete)
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_only_owner_can_delete_company(client):
    owner = await _register_verified(client, "delete-owner@example.com")
    admin = await _register_verified(client, "delete-admin@example.com")
    create_res = await client.post(
        "/api/v1/companies", json=_company_payload(), headers=_auth_headers(owner)
    )
    company_id = create_res.json()["data"]["id"]

    add_res = await client.post(
        f"/api/v1/companies/{company_id}/members",
        json={"user_id": admin["user"]["id"], "role": "admin"},
        headers=_auth_headers(owner),
    )
    member_id = add_res.json()["data"]["id"]
    await client.patch(
        f"/api/v1/companies/{company_id}/members/{member_id}",
        json={"status": "active"},
        headers=_auth_headers(admin),
    )

    admin_attempt = await client.delete(
        f"/api/v1/companies/{company_id}", headers=_auth_headers(admin)
    )
    assert admin_attempt.status_code == 403

    owner_attempt = await client.delete(
        f"/api/v1/companies/{company_id}", headers=_auth_headers(owner)
    )
    assert owner_attempt.status_code == 204


@pytest.mark.asyncio
async def test_deleted_company_disappears_from_search_and_slug_lookup(client):
    owner = await _register_verified(client, "delete-search-owner@example.com")
    create_res = await client.post(
        "/api/v1/companies", json=_company_payload("Soon Deleted Co"), headers=_auth_headers(owner)
    )
    company_id = create_res.json()["data"]["id"]
    slug = create_res.json()["data"]["slug"]

    await client.delete(f"/api/v1/companies/{company_id}", headers=_auth_headers(owner))

    assert (await client.get(f"/api/v1/companies/slug/{slug}")).status_code == 404
    search = await client.get("/api/v1/companies/search?name=Soon Deleted")
    assert search.json()["data"]["total"] == 0
    # But it's still readable by the (former) owner directly — soft delete, not physical delete.
    detail = await client.get(f"/api/v1/companies/{company_id}", headers=_auth_headers(owner))
    assert detail.status_code == 200
    assert detail.json()["data"]["status"] == "archived"
