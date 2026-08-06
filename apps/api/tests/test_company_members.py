"""
Company membership lifecycle tests — Module 3A: invite → accept, role
changes, removal, self-leave, and ownership transfer (including the
single-Owner invariant enforced at both the service and database level).
"""

import pytest

from tests.test_companies import _auth_headers, _company_payload, _register_verified


async def _create_company_and_invite(
    client, owner_email: str, invitee_email: str, role: str = "viewer"
):
    owner = await _register_verified(client, owner_email, "Owner Person")
    invitee = await _register_verified(client, invitee_email, "Invitee Person")
    create_res = await client.post(
        "/api/v1/companies", json=_company_payload(), headers=_auth_headers(owner)
    )
    company_id = create_res.json()["data"]["id"]
    add_res = await client.post(
        f"/api/v1/companies/{company_id}/members",
        json={"user_id": invitee["user"]["id"], "role": role},
        headers=_auth_headers(owner),
    )
    return owner, invitee, company_id, add_res.json()["data"]["id"]


@pytest.mark.asyncio
async def test_invited_member_starts_pending(client):
    _, _, _, _ = await _create_company_and_invite(
        client, "invite-owner@example.com", "invite-target@example.com"
    )
    # Re-fetch via list to confirm pending status is visible.
    owner = await _register_verified(client, "invite-owner2@example.com")
    invitee = await _register_verified(client, "invite-target2@example.com")
    create_res = await client.post(
        "/api/v1/companies", json=_company_payload(), headers=_auth_headers(owner)
    )
    company_id = create_res.json()["data"]["id"]
    add_res = await client.post(
        f"/api/v1/companies/{company_id}/members",
        json={"user_id": invitee["user"]["id"], "role": "editor"},
        headers=_auth_headers(owner),
    )
    assert add_res.status_code == 201
    assert add_res.json()["data"]["status"] == "pending"
    assert add_res.json()["data"]["joined_at"] is None


@pytest.mark.asyncio
async def test_cannot_invite_the_same_user_twice(client):
    owner, invitee, company_id, _ = await _create_company_and_invite(
        client, "dup-invite-owner@example.com", "dup-invite-target@example.com"
    )
    response = await client.post(
        f"/api/v1/companies/{company_id}/members",
        json={"user_id": invitee["user"]["id"], "role": "viewer"},
        headers=_auth_headers(owner),
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "ALREADY_MEMBER"


@pytest.mark.asyncio
async def test_cannot_invite_someone_directly_as_owner(client):
    owner = await _register_verified(client, "no-owner-invite@example.com")
    invitee = await _register_verified(client, "no-owner-invite-target@example.com")
    create_res = await client.post(
        "/api/v1/companies", json=_company_payload(), headers=_auth_headers(owner)
    )
    company_id = create_res.json()["data"]["id"]
    response = await client.post(
        f"/api/v1/companies/{company_id}/members",
        json={"user_id": invitee["user"]["id"], "role": "owner"},
        headers=_auth_headers(owner),
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_only_admin_or_above_can_invite(client):
    owner = await _register_verified(client, "invite-perm-owner@example.com")
    viewer = await _register_verified(client, "invite-perm-viewer@example.com")
    outsider = await _register_verified(client, "invite-perm-outsider@example.com")
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

    viewer_attempt = await client.post(
        f"/api/v1/companies/{company_id}/members",
        json={"user_id": outsider["user"]["id"], "role": "viewer"},
        headers=_auth_headers(viewer),
    )
    assert viewer_attempt.status_code == 403


@pytest.mark.asyncio
async def test_invited_user_can_accept_their_own_invitation(client):
    owner, invitee, company_id, member_id = await _create_company_and_invite(
        client, "accept-owner@example.com", "accept-target@example.com", role="editor"
    )
    response = await client.patch(
        f"/api/v1/companies/{company_id}/members/{member_id}",
        json={"status": "active"},
        headers=_auth_headers(invitee),
    )
    assert response.status_code == 200
    body = response.json()["data"]
    assert body["status"] == "active"
    assert body["joined_at"] is not None
    assert body["role"] == "editor"  # self-accept does not change the assigned role


@pytest.mark.asyncio
async def test_invited_user_cannot_self_promote_while_accepting(client):
    """Self-service accept only covers status: pending -> active — a role change requires Admin+."""
    owner, invitee, company_id, member_id = await _create_company_and_invite(
        client, "no-promote-owner@example.com", "no-promote-target@example.com", role="viewer"
    )
    response = await client.patch(
        f"/api/v1/companies/{company_id}/members/{member_id}",
        json={"role": "admin", "status": "active"},
        headers=_auth_headers(invitee),
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_admin_can_change_a_members_role(client):
    owner, member, company_id, member_id = await _create_company_and_invite(
        client, "role-change-owner@example.com", "role-change-target@example.com", role="viewer"
    )
    response = await client.patch(
        f"/api/v1/companies/{company_id}/members/{member_id}",
        json={"role": "editor"},
        headers=_auth_headers(owner),
    )
    assert response.status_code == 200
    assert response.json()["data"]["role"] == "editor"


@pytest.mark.asyncio
async def test_member_can_remove_themselves(client):
    owner, member, company_id, member_id = await _create_company_and_invite(
        client, "leave-owner@example.com", "leave-target@example.com", role="viewer"
    )
    response = await client.delete(
        f"/api/v1/companies/{company_id}/members/{member_id}", headers=_auth_headers(member)
    )
    assert response.status_code == 204


@pytest.mark.asyncio
async def test_admin_can_remove_another_member(client):
    owner, member, company_id, member_id = await _create_company_and_invite(
        client, "remove-owner@example.com", "remove-target@example.com", role="viewer"
    )
    response = await client.delete(
        f"/api/v1/companies/{company_id}/members/{member_id}", headers=_auth_headers(owner)
    )
    assert response.status_code == 204


@pytest.mark.asyncio
async def test_viewer_cannot_remove_another_member(client):
    owner = await _register_verified(client, "no-remove-owner@example.com")
    viewer1 = await _register_verified(client, "no-remove-viewer1@example.com")
    viewer2 = await _register_verified(client, "no-remove-viewer2@example.com")
    create_res = await client.post(
        "/api/v1/companies", json=_company_payload(), headers=_auth_headers(owner)
    )
    company_id = create_res.json()["data"]["id"]

    for v in (viewer1, viewer2):
        add_res = await client.post(
            f"/api/v1/companies/{company_id}/members",
            json={"user_id": v["user"]["id"], "role": "viewer"},
            headers=_auth_headers(owner),
        )
        mid = add_res.json()["data"]["id"]
        await client.patch(
            f"/api/v1/companies/{company_id}/members/{mid}",
            json={"status": "active"},
            headers=_auth_headers(v),
        )

    members = (
        await client.get(f"/api/v1/companies/{company_id}/members", headers=_auth_headers(owner))
    ).json()["data"]
    viewer2_member_id = next(m["id"] for m in members if m["user_id"] == viewer2["user"]["id"])

    response = await client.delete(
        f"/api/v1/companies/{company_id}/members/{viewer2_member_id}",
        headers=_auth_headers(viewer1),
    )
    assert response.status_code == 403


# --------------------------------------------------------------------------
# Single-Owner invariant & ownership transfer
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_owner_cannot_be_removed_directly(client):
    owner = await _register_verified(client, "no-remove-owner-self@example.com")
    create_res = await client.post(
        "/api/v1/companies", json=_company_payload(), headers=_auth_headers(owner)
    )
    company_id = create_res.json()["data"]["id"]
    members = (
        await client.get(f"/api/v1/companies/{company_id}/members", headers=_auth_headers(owner))
    ).json()["data"]
    owner_member_id = members[0]["id"]

    response = await client.delete(
        f"/api/v1/companies/{company_id}/members/{owner_member_id}", headers=_auth_headers(owner)
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "CANNOT_REMOVE_OWNER"


@pytest.mark.asyncio
async def test_owner_role_cannot_be_changed_without_transferring(client):
    owner = await _register_verified(client, "no-demote-owner@example.com")
    create_res = await client.post(
        "/api/v1/companies", json=_company_payload(), headers=_auth_headers(owner)
    )
    company_id = create_res.json()["data"]["id"]
    members = (
        await client.get(f"/api/v1/companies/{company_id}/members", headers=_auth_headers(owner))
    ).json()["data"]
    owner_member_id = members[0]["id"]

    response = await client.patch(
        f"/api/v1/companies/{company_id}/members/{owner_member_id}",
        json={"role": "admin"},
        headers=_auth_headers(owner),
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "CANNOT_DEMOTE_LAST_OWNER"


@pytest.mark.asyncio
async def test_owner_cannot_be_suspended_without_transferring(client):
    """See app.services.company_service.update_member — status changes on the Owner are guarded too."""
    owner = await _register_verified(client, "no-suspend-owner@example.com")
    create_res = await client.post(
        "/api/v1/companies", json=_company_payload(), headers=_auth_headers(owner)
    )
    company_id = create_res.json()["data"]["id"]
    members = (
        await client.get(f"/api/v1/companies/{company_id}/members", headers=_auth_headers(owner))
    ).json()["data"]
    owner_member_id = members[0]["id"]

    response = await client.patch(
        f"/api/v1/companies/{company_id}/members/{owner_member_id}",
        json={"status": "suspended"},
        headers=_auth_headers(owner),
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "CANNOT_DEMOTE_LAST_OWNER"


@pytest.mark.asyncio
async def test_ownership_transfer_via_role_owner(client):
    """Transfer mechanism: PATCH the target member to role=owner — see docs/adr/0024."""
    owner, new_owner_user, company_id, member_id = await _create_company_and_invite(
        client, "transfer-owner@example.com", "transfer-target@example.com", role="admin"
    )
    await client.patch(
        f"/api/v1/companies/{company_id}/members/{member_id}",
        json={"status": "active"},
        headers=_auth_headers(new_owner_user),
    )

    response = await client.patch(
        f"/api/v1/companies/{company_id}/members/{member_id}",
        json={"role": "owner"},
        headers=_auth_headers(owner),
    )
    assert response.status_code == 200
    assert response.json()["data"]["role"] == "owner"

    # The old Owner is now demoted to Admin, not removed — still a member.
    members = (
        await client.get(
            f"/api/v1/companies/{company_id}/members", headers=_auth_headers(new_owner_user)
        )
    ).json()["data"]
    old_owner_membership = next(m for m in members if m["email"] == "transfer-owner@example.com")
    assert old_owner_membership["role"] == "admin"

    new_owner_membership = next(m for m in members if m["id"] == member_id)
    assert new_owner_membership["role"] == "owner"

    # The new Owner, not the old one, is now protected by the single-Owner invariant.
    demote_old_new_owner_attempt = await client.patch(
        f"/api/v1/companies/{company_id}/members/{member_id}",
        json={"role": "admin"},
        headers=_auth_headers(new_owner_user),
    )
    assert demote_old_new_owner_attempt.status_code == 409

    # ...while the previous Owner (now Admin) CAN be freely demoted/removed.
    old_owner_id = old_owner_membership["id"]
    now_removable = await client.delete(
        f"/api/v1/companies/{company_id}/members/{old_owner_id}",
        headers=_auth_headers(new_owner_user),
    )
    assert now_removable.status_code == 204


@pytest.mark.asyncio
async def test_database_enforces_single_owner_even_if_application_logic_were_bypassed(client):
    """
    Defense in depth: directly exercises the partial unique index
    (migration 0003) rather than going through the service layer, to
    prove the invariant holds at the database level too, not only in
    app.services.company_service.
    """
    import uuid

    from sqlalchemy.exc import IntegrityError

    from app.db.session import AsyncSessionLocal
    from app.models.company_member import CompanyMember, CompanyMemberStatus, CompanyRole

    owner = await _register_verified(client, "db-invariant-owner@example.com")
    second_user_data = await _register_verified(client, "db-invariant-second@example.com")
    create_res = await client.post(
        "/api/v1/companies", json=_company_payload(), headers=_auth_headers(owner)
    )
    company_id = create_res.json()["data"]["id"]

    async with AsyncSessionLocal() as db:
        rogue_owner_row = CompanyMember(
            id=uuid.uuid4(),
            company_id=company_id,
            user_id=second_user_data["user"]["id"],
            role=CompanyRole.OWNER,
            status=CompanyMemberStatus.ACTIVE,
        )
        db.add(rogue_owner_row)
        with pytest.raises(IntegrityError):
            await db.commit()
