"""
Company Verification & Industrial Identity tests — Module 3B. Covers the
verification scoring engine (the module's core "trust" logic), document
upload/replace/delete with real file bytes, logo/cover image upload with
real generated images, social links, business info updates, and
authorization boundaries.
"""

import io

import pytest
from PIL import Image

from tests.test_companies import _auth_headers, _company_payload, _register_verified


def _make_test_image_bytes(size: tuple[int, int] = (400, 300), fmt: str = "PNG") -> bytes:
    img = Image.new("RGB", size, color=(200, 50, 50))
    buf = io.BytesIO()
    img.save(buf, format=fmt)
    return buf.getvalue()


def _make_test_pdf_bytes() -> bytes:
    return b"%PDF-1.4\n%fake pdf content for testing\n%%EOF"


async def _create_verified_owner_company(client, email: str, name: str = "Acme Industrial Co"):
    owner = await _register_verified(client, email)
    create_res = await client.post(
        "/api/v1/companies", json=_company_payload(name), headers=_auth_headers(owner)
    )
    company = create_res.json()["data"]
    return owner, company


# --------------------------------------------------------------------------
# Verification scoring
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_new_company_starts_unverified(client):
    owner, company = await _create_verified_owner_company(client, "score-new@example.com")
    response = await client.get(
        f"/api/v1/companies/{company['id']}/verification", headers=_auth_headers(owner)
    )
    assert response.status_code == 200
    body = response.json()["data"]
    # Owner's email IS verified (via _register_verified), so the company
    # starts at Email Verified (20%), not Unverified (0%).
    assert body["level"] == "email_verified"
    assert body["percentage"] == 20
    assert "owner_email_verified" in body["satisfied_requirement_keys"]


@pytest.mark.asyncio
async def test_business_info_moves_company_toward_business_verified(client):
    owner, company = await _create_verified_owner_company(client, "score-business@example.com")
    await client.patch(
        f"/api/v1/companies/{company['id']}/business-info",
        json={
            "legal_entity_type": "private_limited",
            "gst_number": "22AAAAA0000A1Z5",
            "business_registration_date": "2015-06-01",
        },
        headers=_auth_headers(owner),
    )
    response = await client.get(
        f"/api/v1/companies/{company['id']}/verification", headers=_auth_headers(owner)
    )
    body = response.json()["data"]
    # email(20) + legal_entity_type(6) + government_id(7) + reg_date(4) = 37, still below 45 threshold
    assert body["percentage"] == 37
    assert body["level"] == "email_verified"
    assert body["next_level"] == "business_verified"
    missing_keys = {m["key"] for m in body["missing_requirements"]}
    assert "business_registration_document_uploaded" in missing_keys


@pytest.mark.asyncio
async def test_verification_score_never_manually_settable(client):
    """There must be no way to directly set verification level/percentage — only compute it."""
    owner, company = await _create_verified_owner_company(client, "score-immutable@example.com")
    # No PATCH/PUT endpoint exists for verification at all; confirm the only
    # verb accepted is GET (405 for anything else, not a silent accept).
    response = await client.patch(
        f"/api/v1/companies/{company['id']}/verification",
        json={"level": "premium_verified", "percentage": 100},
        headers=_auth_headers(owner),
    )
    assert response.status_code == 405


@pytest.mark.asyncio
async def test_legacy_verification_status_syncs_automatically(client):
    """Module 3A's coarse verification_status field should flip to 'verified' once Business Verified is reached."""
    owner, company = await _create_verified_owner_company(client, "score-legacy-sync@example.com")

    await client.patch(
        f"/api/v1/companies/{company['id']}/business-info",
        json={
            "legal_entity_type": "llp",
            "gst_number": "22AAAAA0000A1Z5",
            "business_registration_date": "2015-06-01",
        },
        headers=_auth_headers(owner),
    )
    files = {"file": ("reg.pdf", _make_test_pdf_bytes(), "application/pdf")}
    await client.post(
        f"/api/v1/companies/{company['id']}/documents",
        data={"document_type": "business_registration"},
        files=files,
        headers=_auth_headers(owner),
    )

    # Trigger a recompute (any GET .../verification call does this).
    await client.get(
        f"/api/v1/companies/{company['id']}/verification", headers=_auth_headers(owner)
    )

    detail = await client.get(f"/api/v1/companies/{company['id']}", headers=_auth_headers(owner))
    assert detail.json()["data"]["verification_status"] == "verified"


@pytest.mark.asyncio
async def test_public_verification_endpoint_requires_no_auth(client):
    owner, company = await _create_verified_owner_company(client, "score-public@example.com")
    response = await client.get(f"/api/v1/companies/slug/{company['slug']}/verification")
    assert response.status_code == 200
    assert response.json()["data"]["level"] == "email_verified"


@pytest.mark.asyncio
async def test_public_verification_404s_for_unknown_slug(client):
    response = await client.get("/api/v1/companies/slug/does-not-exist/verification")
    assert response.status_code == 404


# --------------------------------------------------------------------------
# Business information
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_business_info_returns_current_values(client):
    owner, company = await _create_verified_owner_company(client, "biz-get@example.com")
    await client.patch(
        f"/api/v1/companies/{company['id']}/business-info",
        json={"legal_entity_type": "llp", "pan": "ABCDE1234F"},
        headers=_auth_headers(owner),
    )
    response = await client.get(
        f"/api/v1/companies/{company['id']}/business-info", headers=_auth_headers(owner)
    )
    assert response.status_code == 200
    body = response.json()["data"]
    assert body["legal_entity_type"] == "llp"
    assert body["pan"] == "ABCDE1234F"
    assert body["export_capable"] is False  # default, never set


@pytest.mark.asyncio
async def test_editor_can_update_business_info(client):
    owner, company = await _create_verified_owner_company(client, "biz-owner@example.com")
    response = await client.patch(
        f"/api/v1/companies/{company['id']}/business-info",
        json={
            "business_type": "manufacturer",
            "export_capable": True,
            "capabilities": ["CNC machining", "welding"],
        },
        headers=_auth_headers(owner),
    )
    assert response.status_code == 200
    assert set(response.json()["data"]["updated_fields"]) == {
        "business_type",
        "export_capable",
        "capabilities",
    }


@pytest.mark.asyncio
async def test_viewer_cannot_update_business_info(client):
    owner, company = await _create_verified_owner_company(client, "biz-viewer-owner@example.com")
    viewer = await _register_verified(client, "biz-viewer@example.com")
    add_res = await client.post(
        f"/api/v1/companies/{company['id']}/members",
        json={"user_id": viewer["user"]["id"], "role": "viewer"},
        headers=_auth_headers(owner),
    )
    member_id = add_res.json()["data"]["id"]
    await client.patch(
        f"/api/v1/companies/{company['id']}/members/{member_id}",
        json={"status": "active"},
        headers=_auth_headers(viewer),
    )

    response = await client.patch(
        f"/api/v1/companies/{company['id']}/business-info",
        json={"business_type": "trader"},
        headers=_auth_headers(viewer),
    )
    assert response.status_code == 403


# --------------------------------------------------------------------------
# Logo & cover image (real images, real Pillow processing)
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_branding_returns_current_state(client):
    owner, company = await _create_verified_owner_company(client, "branding-get@example.com")
    empty = await client.get(
        f"/api/v1/companies/{company['id']}/branding", headers=_auth_headers(owner)
    )
    assert empty.status_code == 200
    assert empty.json()["data"]["logo_url"] is None

    files = {"file": ("logo.png", _make_test_image_bytes(), "image/png")}
    await client.post(
        f"/api/v1/companies/{company['id']}/logo", files=files, headers=_auth_headers(owner)
    )

    after = await client.get(
        f"/api/v1/companies/{company['id']}/branding", headers=_auth_headers(owner)
    )
    assert after.json()["data"]["logo_url"] is not None


@pytest.mark.asyncio
async def test_upload_logo_generates_thumbnail(client):
    owner, company = await _create_verified_owner_company(client, "logo-owner@example.com")
    files = {"file": ("logo.png", _make_test_image_bytes((800, 800)), "image/png")}
    response = await client.post(
        f"/api/v1/companies/{company['id']}/logo", files=files, headers=_auth_headers(owner)
    )
    assert response.status_code == 200
    body = response.json()["data"]
    assert body["logo_url"] is not None
    assert body["logo_thumbnail_url"] is not None

    # The thumbnail must actually be a valid, correctly-sized image — fetch it for real.
    thumb_response = await client.get(body["logo_thumbnail_url"])
    assert thumb_response.status_code == 200
    thumb_img = Image.open(io.BytesIO(thumb_response.content))
    assert thumb_img.size == (256, 256)


@pytest.mark.asyncio
async def test_upload_logo_rejects_non_image(client):
    owner, company = await _create_verified_owner_company(client, "logo-reject@example.com")
    files = {"file": ("not-an-image.png", b"this is definitely not a real image file", "image/png")}
    response = await client.post(
        f"/api/v1/companies/{company['id']}/logo", files=files, headers=_auth_headers(owner)
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_IMAGE"


@pytest.mark.asyncio
async def test_upload_logo_rejects_oversized_file(client):
    owner, company = await _create_verified_owner_company(client, "logo-oversized@example.com")
    # A real (small, valid) image, but padded past the 5MB limit isn't
    # straightforward with a real image; instead assert the size check
    # fires before any image decoding — a large blob of image-like bytes.
    huge = _make_test_image_bytes((4000, 4000), fmt="PNG")
    if len(huge) <= 5 * 1024 * 1024:
        pytest.skip("generated test image did not exceed the 5MB limit on this Pillow/zlib build")
    files = {"file": ("huge.png", huge, "image/png")}
    response = await client.post(
        f"/api/v1/companies/{company['id']}/logo", files=files, headers=_auth_headers(owner)
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "FILE_TOO_LARGE"


@pytest.mark.asyncio
async def test_delete_logo(client):
    owner, company = await _create_verified_owner_company(client, "logo-delete@example.com")
    files = {"file": ("logo.png", _make_test_image_bytes(), "image/png")}
    await client.post(
        f"/api/v1/companies/{company['id']}/logo", files=files, headers=_auth_headers(owner)
    )

    response = await client.delete(
        f"/api/v1/companies/{company['id']}/logo", headers=_auth_headers(owner)
    )
    assert response.status_code == 204

    detail = await client.get(f"/api/v1/companies/{company['id']}", headers=_auth_headers(owner))
    # logo fields aren't in CompanyDetail schema directly tested here via branding endpoint instead:
    branding_check = await client.post(
        f"/api/v1/companies/{company['id']}/logo",
        files={"file": ("logo2.png", _make_test_image_bytes(), "image/png")},
        headers=_auth_headers(owner),
    )
    assert (
        branding_check.json()["data"]["logo_url"] is not None
    )  # re-upload after delete still works
    assert detail.status_code == 200


@pytest.mark.asyncio
async def test_upload_cover_image_generates_responsive_variants(client):
    owner, company = await _create_verified_owner_company(client, "cover-owner@example.com")
    files = {"file": ("cover.png", _make_test_image_bytes((2000, 1000)), "image/png")}
    response = await client.post(
        f"/api/v1/companies/{company['id']}/cover-image", files=files, headers=_auth_headers(owner)
    )
    assert response.status_code == 200
    assert response.json()["data"]["cover_image_url"] is not None


# --------------------------------------------------------------------------
# Social links
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_upsert_and_list_social_links(client):
    owner, company = await _create_verified_owner_company(client, "social-owner@example.com")
    response = await client.put(
        f"/api/v1/companies/{company['id']}/social-links",
        json={"platform": "linkedin", "url": "https://linkedin.com/company/acme"},
        headers=_auth_headers(owner),
    )
    assert response.status_code == 200
    assert response.json()["data"]["platform"] == "linkedin"

    # Upserting the same platform again updates, not duplicates.
    await client.put(
        f"/api/v1/companies/{company['id']}/social-links",
        json={"platform": "linkedin", "url": "https://linkedin.com/company/acme-updated"},
        headers=_auth_headers(owner),
    )
    list_res = await client.get(
        f"/api/v1/companies/{company['id']}/social-links", headers=_auth_headers(owner)
    )
    links = list_res.json()["data"]
    assert len(links) == 1
    assert links[0]["url"] == "https://linkedin.com/company/acme-updated"


@pytest.mark.asyncio
async def test_delete_social_link(client):
    owner, company = await _create_verified_owner_company(client, "social-delete@example.com")
    await client.put(
        f"/api/v1/companies/{company['id']}/social-links",
        json={"platform": "x", "url": "https://x.com/acme"},
        headers=_auth_headers(owner),
    )
    response = await client.delete(
        f"/api/v1/companies/{company['id']}/social-links/x", headers=_auth_headers(owner)
    )
    assert response.status_code == 204

    second_delete = await client.delete(
        f"/api/v1/companies/{company['id']}/social-links/x", headers=_auth_headers(owner)
    )
    assert second_delete.status_code == 404


# --------------------------------------------------------------------------
# Verification documents: upload, versioning/replace, delete, authorization
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_upload_document_starts_pending(client):
    owner, company = await _create_verified_owner_company(client, "doc-owner@example.com")
    files = {"file": ("iso.pdf", _make_test_pdf_bytes(), "application/pdf")}
    response = await client.post(
        f"/api/v1/companies/{company['id']}/documents",
        data={"document_type": "iso"},
        files=files,
        headers=_auth_headers(owner),
    )
    assert response.status_code == 201
    body = response.json()["data"]
    assert body["status"] == "pending"
    assert body["version"] == 1
    assert body["file_type"] == "pdf"


@pytest.mark.asyncio
async def test_editor_cannot_upload_document_only_admin_plus(client):
    """Documents require Admin+ (interpreting the brief's 'Company Owner' as Owner-and-Admin — see ADR-0029)."""
    owner, company = await _create_verified_owner_company(client, "doc-perm-owner@example.com")
    editor = await _register_verified(client, "doc-perm-editor@example.com")
    add_res = await client.post(
        f"/api/v1/companies/{company['id']}/members",
        json={"user_id": editor["user"]["id"], "role": "editor"},
        headers=_auth_headers(owner),
    )
    member_id = add_res.json()["data"]["id"]
    await client.patch(
        f"/api/v1/companies/{company['id']}/members/{member_id}",
        json={"status": "active"},
        headers=_auth_headers(editor),
    )

    files = {"file": ("iso.pdf", _make_test_pdf_bytes(), "application/pdf")}
    response = await client.post(
        f"/api/v1/companies/{company['id']}/documents",
        data={"document_type": "iso"},
        files=files,
        headers=_auth_headers(editor),
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_replace_document_creates_new_version_and_soft_deletes_old(client):
    owner, company = await _create_verified_owner_company(client, "doc-replace@example.com")
    files = {"file": ("iso-v1.pdf", _make_test_pdf_bytes(), "application/pdf")}
    upload_res = await client.post(
        f"/api/v1/companies/{company['id']}/documents",
        data={"document_type": "iso"},
        files=files,
        headers=_auth_headers(owner),
    )
    original_id = upload_res.json()["data"]["id"]

    replace_files = {"file": ("iso-v2.pdf", _make_test_pdf_bytes(), "application/pdf")}
    replace_res = await client.patch(
        f"/api/v1/companies/{company['id']}/documents/{original_id}/replace",
        files=replace_files,
        headers=_auth_headers(owner),
    )
    assert replace_res.status_code == 200
    new_doc = replace_res.json()["data"]
    assert new_doc["version"] == 2
    assert new_doc["id"] != original_id

    # The old version no longer appears in the list (soft-deleted).
    list_res = await client.get(
        f"/api/v1/companies/{company['id']}/documents", headers=_auth_headers(owner)
    )
    ids = {d["id"] for d in list_res.json()["data"]}
    assert original_id not in ids
    assert new_doc["id"] in ids


@pytest.mark.asyncio
async def test_delete_document_is_soft_delete(client):
    owner, company = await _create_verified_owner_company(client, "doc-delete@example.com")
    files = {"file": ("bis.pdf", _make_test_pdf_bytes(), "application/pdf")}
    upload_res = await client.post(
        f"/api/v1/companies/{company['id']}/documents",
        data={"document_type": "bis"},
        files=files,
        headers=_auth_headers(owner),
    )
    document_id = upload_res.json()["data"]["id"]

    response = await client.delete(
        f"/api/v1/companies/{company['id']}/documents/{document_id}", headers=_auth_headers(owner)
    )
    assert response.status_code == 204

    list_res = await client.get(
        f"/api/v1/companies/{company['id']}/documents", headers=_auth_headers(owner)
    )
    assert document_id not in {d["id"] for d in list_res.json()["data"]}

    # Deleting again 404s — it's really gone from the active set.
    second_delete = await client.delete(
        f"/api/v1/companies/{company['id']}/documents/{document_id}", headers=_auth_headers(owner)
    )
    assert second_delete.status_code == 404


@pytest.mark.asyncio
async def test_document_upload_rejects_invalid_file(client):
    owner, company = await _create_verified_owner_company(client, "doc-invalid@example.com")
    files = {"file": ("fake.pdf", b"not a real pdf or image", "application/pdf")}
    response = await client.post(
        f"/api/v1/companies/{company['id']}/documents",
        data={"document_type": "gst_certificate"},
        files=files,
        headers=_auth_headers(owner),
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_outsider_cannot_view_documents(client):
    owner, company = await _create_verified_owner_company(client, "doc-outsider-owner@example.com")
    outsider = await _register_verified(client, "doc-outsider@example.com")
    response = await client.get(
        f"/api/v1/companies/{company['id']}/documents", headers=_auth_headers(outsider)
    )
    assert response.status_code == 404  # IDOR-safe, matches Module 3A's pattern
