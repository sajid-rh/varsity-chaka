from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_returns_standard_envelope():
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["error"] is None
    assert body["data"]["status"] == "ok"
    # "up" with a running database, "down" without one; the endpoint must not crash
    assert body["data"]["database"] in ("up", "down")
