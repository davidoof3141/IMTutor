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
        "study_time": "under_2h",
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
            "study_time": "under_2h",
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
            "study_time": "over_4h",
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
