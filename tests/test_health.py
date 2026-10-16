from fastapi.testclient import TestClient

from api.main import app


def test_health_reports_falkordb(falkordb_url):
    with TestClient(app) as client:
        r = client.get("/api/v1/health")
    assert r.status_code == 200
    body = r.json()
    assert (body["status"], body["falkordb"]) == ("ok", "ok")
    assert "idx_service" in body["query_ms"]  # the startup seed ran through the timed catalogue


def test_health_degraded_when_falkordb_down(monkeypatch):
    monkeypatch.setattr("api.graph.Graph.ping", lambda self: False)
    with TestClient(app) as client:
        r = client.get("/api/v1/health")
    assert (r.json()["status"], r.json()["falkordb"]) == ("degraded", "down")


def test_unknown_route_uses_error_envelope():
    with TestClient(app) as client:
        r = client.get("/api/v1/nope")
    assert r.status_code == 404
    assert set(r.json()["error"]) == {"code", "message", "details"}
