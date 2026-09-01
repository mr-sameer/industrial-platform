"""
Admin document-verification review workflow tests — Phase 1 (see
docs/adr/0029-module-3b-verification-and-identity.md decision #3) and
Phase 2A (the cross-company admin verification queue).
Covers document_service.review_document directly-adjacent behavior via
the API (approve/reject, the PENDING-only guard, verified_by/verified_at/
review_note field semantics), the platform-Role.ADMIN-only authorization
boundary (deliberately distinct from CompanyRole — see
app/api/v1/company_verification.py's module docstring), IDOR protection
across companies, the two new audit events, and (Phase 2A)
GET /companies/documents/pending's pagination, status filtering,
cross-company attribution, and the same authorization boundary. Reuses
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


PENDING_QUEUE_URL = "/api/v1/companies/documents/pending"


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


# --------------------------------------------------------------------------
# Phase 2A: admin verification queue — GET /companies/documents/pending
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pending_queue_is_empty_when_no_documents_exist(client):
    admin = await _register_admin(client, "queue-empty-admin@example.com")

    response = await client.get(PENDING_QUEUE_URL, headers=_auth_headers(admin))
    assert response.status_code == 200
    body = response.json()["data"]
    assert body["items"] == []
    assert body["total"] == 0
    assert body["page"] == 1
    assert body["page_size"] == 20
    assert body["total_pages"] == 1


@pytest.mark.asyncio
async def test_pending_queue_returns_one_pending_document_with_full_fields(client):
    owner, company = await _create_verified_owner_company(client, "queue-one-owner@example.com", name="Queue One Co")
    document = await _upload_pending_document(client, owner, company, document_type="gst_certificate")
    admin = await _register_admin(client, "queue-one-admin@example.com")

    response = await client.get(PENDING_QUEUE_URL, headers=_auth_headers(admin))
    assert response.status_code == 200
    body = response.json()["data"]
    assert body["total"] == 1
    assert len(body["items"]) == 1

    item = body["items"][0]
    assert item["id"] == document["id"]
    assert item["document_type"] == "gst_certificate"
    assert item["file_type"] == "pdf"
    assert item["status"] == "pending"
    assert item["version"] == 1
    assert item["is_expired"] is False
    assert item["verified_at"] is None
    assert item["review_note"] is None
    assert item["company_id"] == company["id"]
    assert item["company_name"] == "Queue One Co"


@pytest.mark.asyncio
async def test_pending_queue_orders_oldest_document_first(client):
    owner_a, company_a = await _create_verified_owner_company(
        client, "queue-order-a-owner@example.com", name="Order A Co"
    )
    older = await _upload_pending_document(client, owner_a, company_a, document_type="iso")

    owner_b, company_b = await _create_verified_owner_company(
        client, "queue-order-b-owner@example.com", name="Order B Co"
    )
    newer = await _upload_pending_document(client, owner_b, company_b, document_type="iso")

    admin = await _register_admin(client, "queue-order-admin@example.com")
    response = await client.get(PENDING_QUEUE_URL, headers=_auth_headers(admin))
    assert response.status_code == 200
    items = response.json()["data"]["items"]
    assert [i["id"] for i in items] == [older["id"], newer["id"]]


@pytest.mark.asyncio
async def test_pending_queue_pagination(client):
    admin = await _register_admin(client, "queue-page-admin@example.com")
    uploaded_ids = []
    for i in range(3):
        owner, company = await _create_verified_owner_company(
            client, f"queue-page-owner-{i}@example.com", name=f"Page Co {i}"
        )
        doc = await _upload_pending_document(client, owner, company, document_type="iso")
        uploaded_ids.append(doc["id"])

    page1 = await client.get(f"{PENDING_QUEUE_URL}?page=1&page_size=2", headers=_auth_headers(admin))
    assert page1.status_code == 200
    body1 = page1.json()["data"]
    assert len(body1["items"]) == 2
    assert body1["total"] == 3
    assert body1["page"] == 1
    assert body1["page_size"] == 2
    assert body1["total_pages"] == 2
    assert [i["id"] for i in body1["items"]] == uploaded_ids[:2]

    page2 = await client.get(f"{PENDING_QUEUE_URL}?page=2&page_size=2", headers=_auth_headers(admin))
    assert page2.status_code == 200
    body2 = page2.json()["data"]
    assert len(body2["items"]) == 1
    assert body2["total"] == 3
    assert body2["page"] == 2
    assert body2["total_pages"] == 2
    assert body2["items"][0]["id"] == uploaded_ids[2]


@pytest.mark.asyncio
async def test_pending_queue_status_filter_defaults_to_pending(client):
    owner, company = await _create_verified_owner_company(client, "queue-status-owner@example.com")
    pending_doc = await _upload_pending_document(client, owner, company, document_type="iso")
    verified_doc = await _upload_pending_document(client, owner, company, document_type="ce")
    rejected_doc = await _upload_pending_document(client, owner, company, document_type="bis")
    admin = await _register_admin(client, "queue-status-admin@example.com")

    await client.post(
        _review(company["id"], verified_doc["id"]),
        json={"decision": "approve"},
        headers=_auth_headers(admin),
    )
    await client.post(
        _review(company["id"], rejected_doc["id"]),
        json={"decision": "reject", "note": "Not legible."},
        headers=_auth_headers(admin),
    )

    default_response = await client.get(PENDING_QUEUE_URL, headers=_auth_headers(admin))
    default_ids = {i["id"] for i in default_response.json()["data"]["items"]}
    assert default_ids == {pending_doc["id"]}

    verified_response = await client.get(f"{PENDING_QUEUE_URL}?status=verified", headers=_auth_headers(admin))
    verified_ids = {i["id"] for i in verified_response.json()["data"]["items"]}
    assert verified_ids == {verified_doc["id"]}

    rejected_response = await client.get(f"{PENDING_QUEUE_URL}?status=rejected", headers=_auth_headers(admin))
    rejected_ids = {i["id"] for i in rejected_response.json()["data"]["items"]}
    assert rejected_ids == {rejected_doc["id"]}
    rejected_item = next(i for i in rejected_response.json()["data"]["items"] if i["id"] == rejected_doc["id"])
    assert rejected_item["review_note"] == "Not legible."


@pytest.mark.asyncio
async def test_pending_queue_excludes_soft_deleted_documents(client):
    owner, company = await _create_verified_owner_company(client, "queue-deleted-owner@example.com")
    document = await _upload_pending_document(client, owner, company, document_type="iso")
    admin = await _register_admin(client, "queue-deleted-admin@example.com")

    delete_response = await client.delete(
        f"/api/v1/companies/{company['id']}/documents/{document['id']}", headers=_auth_headers(owner)
    )
    assert delete_response.status_code == 204

    response = await client.get(PENDING_QUEUE_URL, headers=_auth_headers(admin))
    ids = {i["id"] for i in response.json()["data"]["items"]}
    assert document["id"] not in ids


@pytest.mark.asyncio
async def test_pending_queue_attributes_multi_company_documents_correctly(client):
    """Guards against a company-scoped 'path trick': with two companies each holding a
    pending document, every queue row must be attributed to its OWN company_id/company_name,
    never mixed up or leaked across companies."""
    owner_a, company_a = await _create_verified_owner_company(
        client, "queue-multi-a-owner@example.com", name="Multi Co A"
    )
    doc_a = await _upload_pending_document(client, owner_a, company_a, document_type="iso")
    owner_b, company_b = await _create_verified_owner_company(
        client, "queue-multi-b-owner@example.com", name="Multi Co B"
    )
    doc_b = await _upload_pending_document(client, owner_b, company_b, document_type="ce")
    admin = await _register_admin(client, "queue-multi-admin@example.com")

    response = await client.get(PENDING_QUEUE_URL, headers=_auth_headers(admin))
    items_by_id = {i["id"]: i for i in response.json()["data"]["items"]}

    assert items_by_id[doc_a["id"]]["company_id"] == company_a["id"]
    assert items_by_id[doc_a["id"]]["company_name"] == "Multi Co A"
    assert items_by_id[doc_b["id"]]["company_id"] == company_b["id"]
    assert items_by_id[doc_b["id"]]["company_name"] == "Multi Co B"


@pytest.mark.asyncio
async def test_platform_admin_can_list_pending_queue(client):
    admin = await _register_admin(client, "queue-auth-admin@example.com")
    response = await client.get(PENDING_QUEUE_URL, headers=_auth_headers(admin))
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_company_owner_cannot_list_pending_queue(client):
    owner, _company = await _create_verified_owner_company(client, "queue-auth-owner-denied@example.com")
    response = await client.get(PENDING_QUEUE_URL, headers=_auth_headers(owner))
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_company_admin_cannot_list_pending_queue(client):
    owner, company = await _create_verified_owner_company(client, "queue-auth-companyadmin-owner@example.com")
    company_admin = await _add_member_with_role(
        client, owner, company, "queue-auth-companyadmin-member@example.com", "admin"
    )
    response = await client.get(PENDING_QUEUE_URL, headers=_auth_headers(company_admin))
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_company_editor_cannot_list_pending_queue(client):
    owner, company = await _create_verified_owner_company(client, "queue-auth-editor-owner@example.com")
    editor = await _add_member_with_role(
        client, owner, company, "queue-auth-editor-member@example.com", "editor"
    )
    response = await client.get(PENDING_QUEUE_URL, headers=_auth_headers(editor))
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_company_viewer_cannot_list_pending_queue(client):
    owner, company = await _create_verified_owner_company(client, "queue-auth-viewer-owner@example.com")
    viewer = await _add_member_with_role(
        client, owner, company, "queue-auth-viewer-member@example.com", "viewer"
    )
    response = await client.get(PENDING_QUEUE_URL, headers=_auth_headers(viewer))
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_outsider_cannot_list_pending_queue(client):
    outsider = await _register_verified(client, "queue-auth-outsider@example.com")
    response = await client.get(PENDING_QUEUE_URL, headers=_auth_headers(outsider))
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_pending_queue_route_is_not_reachable_via_a_company_scoped_path_trick(client):
    """The admin queue route (/companies/documents/pending) and the company-scoped
    document list route (/companies/{company_id}/documents) must never be confused with
    each other — a non-admin company Owner hitting the queue URL must get the platform-admin
    403, never anything that resembles a company-scoped 200 with leaked cross-company data."""
    owner, company = await _create_verified_owner_company(client, "queue-trick-owner@example.com")
    await _upload_pending_document(client, owner, company, document_type="iso")

    response = await client.get(PENDING_QUEUE_URL, headers=_auth_headers(owner))
    assert response.status_code == 403

    # Confirm the company's own document list endpoint is unaffected and still
    # correctly scoped — this route and the new one remain fully independent.
    own_list = await client.get(
        f"/api/v1/companies/{company['id']}/documents", headers=_auth_headers(owner)
    )
    assert own_list.status_code == 200
    assert len(own_list.json()["data"]) == 1
