from fastapi.testclient import TestClient

from api.main import app


def test_health_reports_falkordb(falkordb_url):
    with TestClient(app) as client:
        r = client.get("/api/v1/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "falkordb": "ok"}


def test_health_degraded_when_falkordb_down(monkeypatch):
    monkeypatch.setattr("api.graph.Graph.ping", lambda self: False)
    with TestClient(app) as client:
        r = client.get("/api/v1/health")
    assert r.json() == {"status": "degraded", "falkordb": "down"}


def test_unknown_route_uses_error_envelope():
    with TestClient(app) as client:
        r = client.get("/api/v1/nope")
    assert r.status_code == 404
    assert set(r.json()["error"]) == {"code", "message", "details"}
