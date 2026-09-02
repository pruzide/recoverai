import app.main as main_module
from fastapi.testclient import TestClient


def test_ready_when_database_and_redis_ok(monkeypatch):
    monkeypatch.setattr(main_module, "check_database", lambda: True)
    monkeypatch.setattr(main_module, "check_redis", lambda: True)

    with TestClient(main_module.app) as client:
        response = client.get("/ready")

        assert response.status_code == 200

        body = response.json()

        assert body["status"] == "ready"
        assert body["checks"]["database"] == "ok"
        assert body["checks"]["redis"] == "ok"


def test_ready_fails_when_database_down(monkeypatch):
    def database_error():
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(main_module, "check_database", database_error)
    monkeypatch.setattr(main_module, "check_redis", lambda: True)

    with TestClient(main_module.app) as client:
        response = client.get("/ready")

        assert response.status_code == 503

        body = response.json()

        assert body["status"] == "not_ready"
        assert body["checks"]["database"] == "error"
        assert body["checks"]["redis"] == "ok"


def test_ready_fails_when_redis_down(monkeypatch):
    def redis_error():
        raise RuntimeError("redis unavailable")

    monkeypatch.setattr(main_module, "check_database", lambda: True)
    monkeypatch.setattr(main_module, "check_redis", redis_error)

    with TestClient(main_module.app) as client:
        response = client.get("/ready")

        assert response.status_code == 503

        body = response.json()

        assert body["status"] == "not_ready"
        assert body["checks"]["database"] == "ok"
        assert body["checks"]["redis"] == "error"