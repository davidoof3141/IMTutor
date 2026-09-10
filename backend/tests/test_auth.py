from fastapi.testclient import TestClient

from tests.conftest import SUPERUSER, login, make_learner


def test_register_then_approval_gate(raw_client: TestClient) -> None:
    r = raw_client.post(
        "/api/auth/register", json={"username": "alice", "password": "password1"}
    )
    assert r.status_code == 201
    assert r.json()["status"] == "pending"

    # Login is blocked until an admin approves.
    r = raw_client.post("/api/auth/login", json={"username": "alice", "password": "password1"})
    assert r.status_code == 403
    assert "approval" in r.json()["detail"]

    admin = login(raw_client, **SUPERUSER)
    users = raw_client.get("/api/users", headers={"Authorization": f"Bearer {admin}"}).json()
    alice_id = next(u["id"] for u in users if u["username"] == "alice")
    r = raw_client.post(
        f"/api/users/{alice_id}/status",
        json={"status": "approved"},
        headers={"Authorization": f"Bearer {admin}"},
    )
    assert r.status_code == 200

    r = raw_client.post("/api/auth/login", json={"username": "alice", "password": "password1"})
    assert r.status_code == 200
    assert r.json()["user"]["role"] == "learner"


def test_unauthenticated_requests_are_rejected(raw_client: TestClient) -> None:
    assert raw_client.post("/api/onboarding", json={
        "role": "practitioner",
        "prior_experience": "low",
        "goal": "certification",
        "industry": "healthcare",
        "learner_type": "visuell",
    }).status_code == 401


def test_user_management_is_admin_only(raw_client: TestClient) -> None:
    learner = make_learner(raw_client)
    r = raw_client.get("/api/users", headers={"Authorization": f"Bearer {learner}"})
    assert r.status_code == 403


def test_learner_cannot_touch_another_learners_config(raw_client: TestClient) -> None:
    token_a = make_learner(raw_client, "alice", "password1")
    token_b = make_learner(raw_client, "bob", "password2")

    onboard = raw_client.post(
        "/api/onboarding",
        json={
            "role": "practitioner",
            "prior_experience": "low",
            "goal": "certification",
            "industry": "healthcare",
            "learner_type": "visuell",
        },
        headers={"Authorization": f"Bearer {token_a}"},
    )
    learner_a = onboard.json()["profile"]["learner_id"]

    r = raw_client.get(
        f"/api/config/{learner_a}", headers={"Authorization": f"Bearer {token_b}"}
    )
    assert r.status_code == 403

    r = raw_client.get(
        f"/api/config/{learner_a}", headers={"Authorization": f"Bearer {token_a}"}
    )
    assert r.status_code == 200


def test_admin_can_reach_any_learner(raw_client: TestClient) -> None:
    token = make_learner(raw_client)
    learner = raw_client.post(
        "/api/onboarding",
        json={
            "role": "academic",
            "prior_experience": "high",
            "goal": "orientation",
            "industry": "finance",
            "learner_type": "auditiv",
        },
        headers={"Authorization": f"Bearer {token}"},
    ).json()["profile"]["learner_id"]

    admin = login(raw_client, **SUPERUSER)
    r = raw_client.get(
        f"/api/config/{learner}", headers={"Authorization": f"Bearer {admin}"}
    )
    assert r.status_code == 200


def test_admin_can_create_admin_directly(raw_client: TestClient) -> None:
    admin = login(raw_client, **SUPERUSER)
    r = raw_client.post(
        "/api/users",
        json={"username": "carol", "password": "password1", "role": "admin"},
        headers={"Authorization": f"Bearer {admin}"},
    )
    assert r.status_code == 201
    body = r.json()
    assert body["role"] == "admin"
    assert body["status"] == "approved"

    # No approval step needed -- the new admin can log in immediately.
    r = raw_client.post("/api/auth/login", json={"username": "carol", "password": "password1"})
    assert r.status_code == 200
    assert r.json()["user"]["role"] == "admin"


def test_create_user_is_admin_only(raw_client: TestClient) -> None:
    learner = make_learner(raw_client)
    r = raw_client.post(
        "/api/users",
        json={"username": "dave", "password": "password1", "role": "admin"},
        headers={"Authorization": f"Bearer {learner}"},
    )
    assert r.status_code == 403


def test_temporary_password_forces_a_change_before_use(raw_client: TestClient) -> None:
    admin = login(raw_client, **SUPERUSER)
    headers = {"Authorization": f"Bearer {admin}"}
    r = raw_client.post(
        "/api/users",
        json={
            "username": "temp",
            "password": "temp-pass-1",
            "role": "learner",
            "temporary_password": True,
        },
        headers=headers,
    )
    assert r.status_code == 201
    assert r.json()["must_change_password"] is True

    # The account logs in, but is barred from everything except /me and the
    # password change itself.
    token = login(raw_client, "temp", "temp-pass-1")
    auth = {"Authorization": f"Bearer {token}"}
    assert raw_client.get("/api/auth/me", headers=auth).json()["user"]["must_change_password"] is True
    assert raw_client.get("/api/conversations/anything", headers=auth).status_code == 403

    # Wrong current password is rejected; a matching new password is rejected.
    assert raw_client.post(
        "/api/auth/change-password",
        json={"current_password": "not-it-1", "new_password": "brand-new-1"},
        headers=auth,
    ).status_code == 401
    assert raw_client.post(
        "/api/auth/change-password",
        json={"current_password": "temp-pass-1", "new_password": "temp-pass-1"},
        headers=auth,
    ).status_code == 400

    changed = raw_client.post(
        "/api/auth/change-password",
        json={"current_password": "temp-pass-1", "new_password": "brand-new-1"},
        headers=auth,
    )
    assert changed.status_code == 200
    assert changed.json()["user"]["must_change_password"] is False

    # The old token was revoked by the version bump; the fresh one works and
    # the gate is gone (404 = past auth, just an unknown learner id).
    assert raw_client.get("/api/conversations/anything", headers=auth).status_code == 401
    new_token = changed.json()["token"]
    new_auth = {"Authorization": f"Bearer {new_token}"}
    assert raw_client.get("/api/auth/me", headers=new_auth).json()["user"][
        "must_change_password"
    ] is False
    assert raw_client.get("/api/conversations/anything", headers=new_auth).status_code == 404

    # The temporary password no longer works; the new one does.
    assert raw_client.post(
        "/api/auth/login", json={"username": "temp", "password": "temp-pass-1"}
    ).status_code == 401
    assert raw_client.post(
        "/api/auth/login", json={"username": "temp", "password": "brand-new-1"}
    ).status_code == 200


def test_created_user_without_temporary_flag_is_unrestricted(raw_client: TestClient) -> None:
    admin = login(raw_client, **SUPERUSER)
    raw_client.post(
        "/api/users",
        json={"username": "steady", "password": "steady-pass-1", "role": "learner"},
        headers={"Authorization": f"Bearer {admin}"},
    )
    token = login(raw_client, "steady", "steady-pass-1")
    auth = {"Authorization": f"Bearer {token}"}
    assert raw_client.get("/api/auth/me", headers=auth).json()["user"]["must_change_password"] is False
    # 404 = the password gate let the request through to an unknown learner id.
    assert raw_client.get("/api/conversations/anything", headers=auth).status_code == 404


def test_login_is_rate_limited(raw_client: TestClient) -> None:
    raw_client.post("/api/auth/register", json={"username": "eve", "password": "password1"})
    attempts = [
        raw_client.post(
            "/api/auth/login", json={"username": "eve", "password": "wrong-password"}
        ).status_code
        for _ in range(12)
    ]
    assert attempts[:10] == [401] * 10
    assert 429 in attempts[10:]


def test_register_does_not_reveal_taken_usernames(raw_client: TestClient) -> None:
    first = raw_client.post(
        "/api/auth/register", json={"username": "frank", "password": "password1"}
    )
    second = raw_client.post(
        "/api/auth/register", json={"username": "frank", "password": "different1"}
    )
    assert first.status_code == second.status_code == 201
    assert first.json() == second.json() == {"status": "pending"}

    # The original password still works -- the second call was a silent no-op.
    admin = login(raw_client, **SUPERUSER)
    headers = {"Authorization": f"Bearer {admin}"}
    frank_id = next(
        u["id"] for u in raw_client.get("/api/users", headers=headers).json()
        if u["username"] == "frank"
    )
    raw_client.post(
        f"/api/users/{frank_id}/status", json={"status": "approved"}, headers=headers
    )
    assert (
        raw_client.post(
            "/api/auth/login", json={"username": "frank", "password": "password1"}
        ).status_code
        == 200
    )


def test_admin_role_change_revokes_existing_tokens(raw_client: TestClient) -> None:
    token = make_learner(raw_client, "grace", "password1")
    assert raw_client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 200

    admin = login(raw_client, **SUPERUSER)
    headers = {"Authorization": f"Bearer {admin}"}
    grace_id = next(
        u["id"] for u in raw_client.get("/api/users", headers=headers).json()
        if u["username"] == "grace"
    )
    raw_client.post(f"/api/users/{grace_id}/role", json={"role": "admin"}, headers=headers)

    # The token issued before the change no longer works; a fresh login does.
    assert raw_client.get(
        "/api/auth/me", headers={"Authorization": f"Bearer {token}"}
    ).status_code == 401
    assert raw_client.post(
        "/api/auth/login", json={"username": "grace", "password": "password1"}
    ).status_code == 200
