"""
Session lifecycle tests: rotation, reuse detection, listing, and
per-device/all-device revocation. See docs/adr/0014-refresh-token-and-session-model.md.
"""

import pytest


def _register_payload(email: str = "grace@example.com") -> dict:
    return {"email": email, "password": "correct-horse-9", "full_name": "Grace Hopper"}


@pytest.mark.asyncio
async def test_refresh_rotates_the_token_and_old_one_stops_working(client):
    register_res = await client.post("/api/v1/auth/register", json=_register_payload())
    old_refresh_token = register_res.json()["data"]["refresh_token"]

    refresh_res = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": old_refresh_token}
    )
    assert refresh_res.status_code == 200
    new_refresh_token = refresh_res.json()["data"]["refresh_token"]
    assert new_refresh_token != old_refresh_token

    # The rotated-away token must not work anymore (this is not the reuse-detection
    # path yet — that's tested separately below — this just confirms rotation happened).
    second_use_of_old = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": old_refresh_token}
    )
    assert second_use_of_old.status_code == 401


@pytest.mark.asyncio
async def test_reusing_a_rotated_away_token_revokes_the_whole_session(client):
    """
    The core theft-mitigation guarantee: replaying an already-rotated
    token doesn't just fail — it revokes the session, so the *current*
    (legitimate) refresh token also stops working immediately.
    """
    register_res = await client.post("/api/v1/auth/register", json=_register_payload())
    original_token = register_res.json()["data"]["refresh_token"]

    first_refresh = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": original_token}
    )
    current_valid_token = first_refresh.json()["data"]["refresh_token"]

    # Replay the original (already-rotated-away) token — simulates an attacker
    # using a stolen token after the legitimate user has already refreshed.
    replay_response = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": original_token}
    )
    assert replay_response.status_code == 401
    assert replay_response.json()["error"]["code"] == "REFRESH_TOKEN_REUSE_DETECTED"

    # The legitimate, currently-valid token must ALSO be dead now — the
    # whole session was revoked, not just the replayed token.
    legitimate_attempt = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": current_valid_token}
    )
    assert legitimate_attempt.status_code == 401
    assert legitimate_attempt.json()["error"]["code"] == "INVALID_REFRESH_TOKEN"


@pytest.mark.asyncio
async def test_logout_revokes_only_that_devices_session(client):
    register_res = await client.post("/api/v1/auth/register", json=_register_payload())
    refresh_token = register_res.json()["data"]["refresh_token"]

    logout_res = await client.post("/api/v1/auth/logout", json={"refresh_token": refresh_token})
    assert logout_res.status_code == 204

    refresh_after_logout = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": refresh_token}
    )
    assert refresh_after_logout.status_code == 401
    assert refresh_after_logout.json()["error"]["code"] == "INVALID_REFRESH_TOKEN"


@pytest.mark.asyncio
async def test_list_sessions_shows_active_sessions(client):
    register_res = await client.post("/api/v1/auth/register", json=_register_payload())
    access_token = register_res.json()["data"]["access_token"]

    response = await client.get(
        "/api/v1/auth/sessions", headers={"Authorization": f"Bearer {access_token}"}
    )
    assert response.status_code == 200
    sessions = response.json()["data"]
    assert len(sessions) == 1
    assert "id" in sessions[0]


@pytest.mark.asyncio
async def test_revoke_specific_session_by_id(client):
    register_res = await client.post("/api/v1/auth/register", json=_register_payload())
    access_token = register_res.json()["data"]["access_token"]
    refresh_token = register_res.json()["data"]["refresh_token"]

    sessions_res = await client.get(
        "/api/v1/auth/sessions", headers={"Authorization": f"Bearer {access_token}"}
    )
    session_id = sessions_res.json()["data"][0]["id"]

    revoke_res = await client.delete(
        f"/api/v1/auth/sessions/{session_id}", headers={"Authorization": f"Bearer {access_token}"}
    )
    assert revoke_res.status_code == 204

    # That session's refresh token must now be dead.
    refresh_after = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
    assert refresh_after.status_code == 401


@pytest.mark.asyncio
async def test_revoking_a_session_that_does_not_belong_to_you_returns_404(client):
    user_a = await client.post("/api/v1/auth/register", json=_register_payload("a@example.com"))
    user_a_token = user_a.json()["data"]["access_token"]

    user_b = await client.post("/api/v1/auth/register", json=_register_payload("b@example.com"))
    user_b_access = user_b.json()["data"]["access_token"]
    b_sessions = await client.get(
        "/api/v1/auth/sessions", headers={"Authorization": f"Bearer {user_b_access}"}
    )
    b_session_id = b_sessions.json()["data"][0]["id"]

    # User A tries to revoke User B's session — must not be able to.
    response = await client.delete(
        f"/api/v1/auth/sessions/{b_session_id}", headers={"Authorization": f"Bearer {user_a_token}"}
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_logout_all_revokes_every_session_for_the_user(client):
    register_res = await client.post("/api/v1/auth/register", json=_register_payload())
    access_token = register_res.json()["data"]["access_token"]
    first_refresh_token = register_res.json()["data"]["refresh_token"]

    # A second "device" logs in too.
    login_res = await client.post(
        "/api/v1/auth/login",
        json={"email": "grace@example.com", "password": "correct-horse-9", "device_name": "iPhone"},
    )
    second_refresh_token = login_res.json()["data"]["refresh_token"]

    logout_all_res = await client.post(
        "/api/v1/auth/logout-all", headers={"Authorization": f"Bearer {access_token}"}
    )
    assert logout_all_res.status_code == 204

    for token in (first_refresh_token, second_refresh_token):
        response = await client.post("/api/v1/auth/refresh", json={"refresh_token": token})
        assert response.status_code == 401


@pytest.mark.asyncio
async def test_malformed_refresh_token_is_rejected(client):
    response = await client.post("/api/v1/auth/refresh", json={"refresh_token": "not-a-real-token"})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_REFRESH_TOKEN"
