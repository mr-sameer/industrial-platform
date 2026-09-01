"""
Admin document-verification review workflow tests — Phase 1 (see
docs/adr/0029-module-3b-verification-and-identity.md decision #3).
Covers document_service.review_document directly-adjacent behavior via
the API (approve/reject, the PENDING-only guard, verified_by/verified_at/
review_note field semantics), the platform-Role.ADMIN-only authorization
boundary (deliberately distinct from CompanyRole — see
app/api/v1/company_verification.py's module docstring), IDOR protection
across companies, and the two new audit events. Reuses
tests/test_companies.py, tests/test_company_verification.py, and
tests/test_acquisition.py's established fixtures rather than
reintroducing them — matching tests/test_data_quality.py's own
cross-import pattern for _register_admin.
"""

import pytest
from sqlalchemy import select

from app.db.session import AsyncSessionLocal
from app.models.audit_log import AuditLog
from app.models.verification_document import DocumentStatus, VerificationDocument
from tests.test_acquisition import _register_admin
from tests.test_companies import _auth_headers, _register_verified
from tests.test_company_verification import _create_verified_owner_company, _make_test_pdf_bytes


async def _upload_pending_document(client, owner, company, document_type: str = "iso") -> dict:
    files = {"file": (f"{document_type}.pdf", _make_test_pdf_bytes(), "application/pdf")}
    response = await client.post(
        f"/api/v1/companies/{company['id']}/documents",
        data={"document_type": document_type},
        files=files,
        headers=_auth_headers(owner),
    )
    assert response.status_code == 201
    return response.json()["data"]


async def _add_member_with_role(client, owner, company, email: str, role: str) -> dict:
    """Registers a new verified user, adds them to `company` with `role`, and activates
    the membership — mirrors test_company_verification.py's own inline pattern
    (test_editor_cannot_upload_document_only_admin_plus), extracted since this file
    needs it for all four company-scoped roles, not just Editor."""
    member = await _register_verified(client, email)
    add_res = await client.post(
        f"/api/v1/companies/{company['id']}/members",
        json={"user_id": member["user"]["id"], "role": role},
        headers=_auth_headers(owner),
    )
    member_id = add_res.json()["data"]["id"]
    await client.patch(
        f"/api/v1/companies/{company['id']}/members/{member_id}",
        json={"status": "active"},
        headers=_auth_headers(member),
    )
    return member


def _review(company_id: str, document_id: str) -> str:
    return f"/api/v1/companies/{company_id}/documents/{document_id}/review"


# --------------------------------------------------------------------------
# Approve / reject — happy path
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_platform_admin_can_approve_pending_document(client):
    owner, company = await _create_verified_owner_company(client, "review-approve-owner@example.com")
    document = await _upload_pending_document(client, owner, company)
    admin = await _register_admin(client, "review-approve-admin@example.com")

    response = await client.post(
        _review(company["id"], document["id"]),
        json={"decision": "approve"},
        headers=_auth_headers(admin),
    )
    assert response.status_code == 200
    body = response.json()["data"]
    assert body["status"] == "verified"
    assert body["review_note"] is None


@pytest.mark.asyncio
async def test_platform_admin_can_reject_pending_document(client):
    owner, company = await _create_verified_owner_company(client, "review-reject-owner@example.com")
    document = await _upload_pending_document(client, owner, company)
    admin = await _register_admin(client, "review-reject-admin@example.com")

    response = await client.post(
        _review(company["id"], document["id"]),
        json={"decision": "reject", "note": "Certificate has expired."},
        headers=_auth_headers(admin),
    )
    assert response.status_code == 200
    body = response.json()["data"]
    assert body["status"] == "rejected"
    assert body["review_note"] == "Certificate has expired."


@pytest.mark.asyncio
async def test_approval_ignores_a_supplied_note(client):
    """APPROVE always clears review_note to None, even if a client sends one —
    matching document_service.review_document's documented behavior exactly."""
    owner, company = await _create_verified_owner_company(client, "review-approve-note-owner@example.com")
    document = await _upload_pending_document(client, owner, company)
    admin = await _register_admin(client, "review-approve-note-admin@example.com")

    response = await client.post(
        _review(company["id"], document["id"]),
        json={"decision": "approve", "note": "This note should never be stored."},
        headers=_auth_headers(admin),
    )
    assert response.status_code == 200
    assert response.json()["data"]["review_note"] is None


@pytest.mark.asyncio
async def test_verified_by_and_verified_at_are_set_on_review(client):
    owner, company = await _create_verified_owner_company(client, "review-fields-owner@example.com")
    document = await _upload_pending_document(client, owner, company)
    admin = await _register_admin(client, "review-fields-admin@example.com")

    response = await client.post(
        _review(company["id"], document["id"]),
        json={"decision": "approve"},
        headers=_auth_headers(admin),
    )
    assert response.status_code == 200

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(VerificationDocument).where(VerificationDocument.id == document["id"])
        )
        row = result.scalar_one()
        assert str(row.verified_by) == admin["user"]["id"]
        assert row.verified_at is not None


# --------------------------------------------------------------------------
# Already-reviewed / non-PENDING guard
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_already_verified_document_cannot_be_reviewed_again(client):
    owner, company = await _create_verified_owner_company(client, "review-reverify-owner@example.com")
    document = await _upload_pending_document(client, owner, company)
    admin = await _register_admin(client, "review-reverify-admin@example.com")

    first = await client.post(
        _review(company["id"], document["id"]),
        json={"decision": "approve"},
        headers=_auth_headers(admin),
    )
    assert first.status_code == 200

    second = await client.post(
        _review(company["id"], document["id"]),
        json={"decision": "approve"},
        headers=_auth_headers(admin),
    )
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "DOCUMENT_NOT_PENDING"


@pytest.mark.asyncio
async def test_already_rejected_document_cannot_be_reviewed_again(client):
    owner, company = await _create_verified_owner_company(client, "review-rereject-owner@example.com")
    document = await _upload_pending_document(client, owner, company)
    admin = await _register_admin(client, "review-rereject-admin@example.com")

    first = await client.post(
        _review(company["id"], document["id"]),
        json={"decision": "reject", "note": "Blurry scan."},
        headers=_auth_headers(admin),
    )
    assert first.status_code == 200

    second = await client.post(
        _review(company["id"], document["id"]),
        json={"decision": "approve"},
        headers=_auth_headers(admin),
    )
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "DOCUMENT_NOT_PENDING"


@pytest.mark.asyncio
async def test_expired_document_cannot_be_reviewed(client):
    owner, company = await _create_verified_owner_company(client, "review-expired-owner@example.com")
    document = await _upload_pending_document(client, owner, company)
    admin = await _register_admin(client, "review-expired-admin@example.com")

    # Nothing in the API can ever produce status=EXPIRED today (see
    # DocumentStatus's docstring) — set it directly via the DB, same
    # technique tests/test_acquisition.py's _register_admin uses to reach
    # a state no endpoint can produce.
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(VerificationDocument).where(VerificationDocument.id == document["id"])
        )
        row = result.scalar_one()
        row.status = DocumentStatus.EXPIRED
        await db.commit()

    response = await client.post(
        _review(company["id"], document["id"]),
        json={"decision": "approve"},
        headers=_auth_headers(admin),
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "DOCUMENT_NOT_PENDING"


# --------------------------------------------------------------------------
# Authorization: platform Role.ADMIN only — every CompanyRole is denied
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_company_owner_cannot_review_document(client):
    owner, company = await _create_verified_owner_company(client, "review-owner-denied@example.com")
    document = await _upload_pending_document(client, owner, company)

    response = await client.post(
        _review(company["id"], document["id"]),
        json={"decision": "approve"},
        headers=_auth_headers(owner),
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_company_admin_cannot_review_document(client):
    owner, company = await _create_verified_owner_company(client, "review-companyadmin-owner@example.com")
    document = await _upload_pending_document(client, owner, company)
    company_admin = await _add_member_with_role(
        client, owner, company, "review-companyadmin-member@example.com", "admin"
    )

    response = await client.post(
        _review(company["id"], document["id"]),
        json={"decision": "approve"},
        headers=_auth_headers(company_admin),
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_company_editor_cannot_review_document(client):
    owner, company = await _create_verified_owner_company(client, "review-editor-owner@example.com")
    document = await _upload_pending_document(client, owner, company)
    editor = await _add_member_with_role(
        client, owner, company, "review-editor-member@example.com", "editor"
    )

    response = await client.post(
        _review(company["id"], document["id"]),
        json={"decision": "approve"},
        headers=_auth_headers(editor),
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_company_viewer_cannot_review_document(client):
    owner, company = await _create_verified_owner_company(client, "review-viewer-owner@example.com")
    document = await _upload_pending_document(client, owner, company)
    viewer = await _add_member_with_role(
        client, owner, company, "review-viewer-member@example.com", "viewer"
    )

    response = await client.post(
        _review(company["id"], document["id"]),
        json={"decision": "approve"},
        headers=_auth_headers(viewer),
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_outsider_cannot_review_document(client):
    owner, company = await _create_verified_owner_company(client, "review-outsider-owner@example.com")
    document = await _upload_pending_document(client, owner, company)
    outsider = await _register_verified(client, "review-outsider@example.com")

    response = await client.post(
        _review(company["id"], document["id"]),
        json={"decision": "approve"},
        headers=_auth_headers(outsider),
    )
    assert response.status_code == 403


# --------------------------------------------------------------------------
# Cross-company IDOR
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_document_cannot_be_reviewed_via_a_different_companys_id(client):
    owner_a, company_a = await _create_verified_owner_company(client, "review-idor-a-owner@example.com")
    document_a = await _upload_pending_document(client, owner_a, company_a)
    owner_b, company_b = await _create_verified_owner_company(
        client, "review-idor-b-owner@example.com", name="Other Industrial Co"
    )
    admin = await _register_admin(client, "review-idor-admin@example.com")

    # document_a's real id, but company_b's id in the path — must 404, not
    # succeed and not leak whether the document exists under company_b.
    response = await client.post(
        _review(company_b["id"], document_a["id"]),
        json={"decision": "approve"},
        headers=_auth_headers(admin),
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "DOCUMENT_NOT_FOUND"

    # The real (company_a, document_a) pair still works — proves the 404
    # above was IDOR protection, not a broken review endpoint.
    real = await client.post(
        _review(company_a["id"], document_a["id"]),
        json={"decision": "approve"},
        headers=_auth_headers(admin),
    )
    assert real.status_code == 200


# --------------------------------------------------------------------------
# Audit events
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_audit_event_emitted_for_approval(client):
    owner, company = await _create_verified_owner_company(client, "review-audit-approve-owner@example.com")
    document = await _upload_pending_document(client, owner, company)
    admin = await _register_admin(client, "review-audit-approve-admin@example.com")

    response = await client.post(
        _review(company["id"], document["id"]),
        json={"decision": "approve"},
        headers=_auth_headers(admin),
    )
    assert response.status_code == 200

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(AuditLog).where(AuditLog.event == "company_document_verified")
        )
        entries = result.scalars().all()
        matching = [e for e in entries if e.event_metadata and e.event_metadata.get("document_id") == document["id"]]
        assert len(matching) == 1
        assert str(matching[0].user_id) == admin["user"]["id"]
        assert matching[0].event_metadata["company_id"] == company["id"]


@pytest.mark.asyncio
async def test_audit_event_emitted_for_rejection(client):
    owner, company = await _create_verified_owner_company(client, "review-audit-reject-owner@example.com")
    document = await _upload_pending_document(client, owner, company)
    admin = await _register_admin(client, "review-audit-reject-admin@example.com")

    response = await client.post(
        _review(company["id"], document["id"]),
        json={"decision": "reject", "note": "Wrong document type uploaded."},
        headers=_auth_headers(admin),
    )
    assert response.status_code == 200

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(AuditLog).where(AuditLog.event == "company_document_rejected")
        )
        entries = result.scalars().all()
        matching = [e for e in entries if e.event_metadata and e.event_metadata.get("document_id") == document["id"]]
        assert len(matching) == 1
        assert str(matching[0].user_id) == admin["user"]["id"]
        assert matching[0].event_metadata["review_note"] == "Wrong document type uploaded."
