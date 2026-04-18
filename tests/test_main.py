from fastapi.testclient import TestClient

from app.main import app


def test_health_ok():
    with TestClient(app) as c:
        r = c.get("/health")
        assert r.status_code == 200
        assert r.json() == {"status": "ok"}


def test_missing_api_key_returns_401():
    with TestClient(app) as c:
        r = c.get("/api/v1/jobs/00000000-0000-0000-0000-000000000000")
        assert r.status_code == 401
        assert r.json()["error"]["code"] == "unauthorized"


def test_invalid_api_key_returns_401():
    with TestClient(app) as c:
        r = c.get(
            "/api/v1/jobs/00000000-0000-0000-0000-000000000000",
            headers={"X-API-Key": "ocr_live_bogus" + "0" * 32},
        )
        assert r.status_code == 401


def test_request_id_header_echoed():
    with TestClient(app) as c:
        r = c.get("/health")
        assert "x-request-id" in {k.lower() for k in r.headers.keys()}
