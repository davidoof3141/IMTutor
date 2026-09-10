from fastapi.testclient import TestClient


def test_health_ok_when_database_reachable(raw_client: TestClient) -> None:
    response = raw_client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}


def test_health_reports_degraded_when_database_down(
    raw_client: TestClient, monkeypatch: object
) -> None:
    from app.store import db

    db.reset_pool()
    # Point the pool at a dead address so borrowing a connection fails fast.
    monkeypatch.setattr(  # type: ignore[attr-defined]
        db, "database_url", lambda: "postgresql://x:x@127.0.0.1:1/x?connect_timeout=1"
    )

    response = raw_client.get("/api/health")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "degraded"
    assert body["database"].startswith("error:")

    db.reset_pool()
