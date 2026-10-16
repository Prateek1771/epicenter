"""REST API + SSE (phase 6): contract shapes, alert join, replay, errors, state transitions, pagination, views."""

from pathlib import Path

from api import models as m
from api.config import get_settings
from api.events import RedisStreamBus, bus
from api.graph import GraphUnavailable
from api.ingest.seed import seed_indexes
from api.search.simulate import what_if
from api.tools import graph_tools
from tests.conftest import API_ENV as ENV
from tests.conftest import diagnosed as _diagnosed

FIXTURES = Path(__file__).parent / "fixtures"
Q = {"env": ENV}


def test_incident_detail_matches_the_contract(client):
    body = _diagnosed(client)
    inc = m.IncidentOut(**body)
    assert inc.status == "diagnosed" and inc.run == 2
    v = inc.verdict
    assert v.root_cause.target == "payment/Charge" and v.root_cause.id == "h-2"
    assert v.path == ["frontend/GET /checkout", "checkout/PlaceOrder", "payment/Charge"]
    assert {e.kind for e in v.evidence} == {"propagation", "change", "footprint"}
    assert v.footprint and v.footprint.coverage == 0.75  # 3 of 4 symptoms (LLD §12)
    assert {h.target for h in inc.hypotheses} >= {"payment/Charge", "checkout/PlaceOrder", "cart/GetCart"}
    fp = client.get("/api/v1/incidents/inc-1/hypotheses/h-2/footprint", params=Q)
    assert fp.status_code == 200 and m.FootprintOut(**fp.json()).predicted[0].onset_window_s is not None
    why = client.get("/api/v1/incidents/inc-1/why-not/checkout", params=Q).json()
    assert why["answer"] == "victim"


def test_no_root_cause_shape(client, graph):
    g = graph.env(ENV)
    g.delete()
    seed_indexes(g)
    g.load_cypher(FIXTURES / "healthy.cypher")
    assert client.post("/api/v1/incidents/inc-h/diagnose", params=Q).status_code == 202
    inc = m.IncidentOut(**client.get("/api/v1/incidents/inc-h", params=Q).json())
    assert inc.status == "no_root_cause" and inc.verdict is None
    assert inc.no_root_cause and inc.no_root_cause.checked


def test_two_alerts_on_one_symptom_make_one_incident(client):
    a = {"symptom": "frontend/GET /cart", "starts_at": "2026-10-16T14:05:12Z", "auto_diagnose": False}
    r1 = client.post("/api/v1/alerts", params=Q, json=a | {"alert_id": "am-1"})
    r2 = client.post("/api/v1/alerts", params=Q, json=a | {"alert_id": "am-2", "starts_at": "2026-10-16T14:09:00Z"})
    assert r1.status_code == r2.status_code == 202
    one, two = m.AlertAccepted(**r1.json()), m.AlertAccepted(**r2.json())
    assert (one.joined_existing, two.joined_existing) == (False, True) and one.incident_id == two.incident_id
    assert client.get(f"/api/v1/incidents/{one.incident_id}", params=Q).json()["alert_count"] == 2
    # the same alert re-sent stays on its incident; 11 min later on the same symptom → a new incident
    again = client.post("/api/v1/alerts", params=Q, json=a | {"alert_id": "am-1"}).json()
    assert again["incident_id"] == one.incident_id
    late = client.post("/api/v1/alerts", params=Q, json=a | {"alert_id": "am-3", "starts_at": "2026-10-16T14:16:13Z"})
    assert late.json()["incident_id"] != one.incident_id and late.json()["joined_existing"] is False


def test_alert_with_auto_diagnose_runs_in_the_background(client):
    a = {"alert_id": "am-9", "symptom": "frontend/GET /checkout", "starts_at": "2026-10-16T15:00:00Z"}
    r = client.post("/api/v1/alerts", params=Q, json=a)
    assert r.status_code == 202 and r.json()["status"] == "diagnosing"
    assert r.json()["stream"].startswith("/api/v1/incidents/inc-am-9/stream")
    # The test client runs the background task before returning: the flow has finished on the alert's incident
    assert client.get("/api/v1/incidents/inc-am-9", params=Q).json()["run"] == 1


def _read_sse(client, incident: str, headers: dict | None = None) -> list[dict]:
    r = client.get(f"/api/v1/incidents/{incident}/stream", params=Q | {"follow": "false"}, headers=headers or {})
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
    out = []
    for block in r.text.strip().split("\n\n"):
        fields = dict(line.split(": ", 1) for line in block.splitlines() if not line.startswith(":"))
        if fields:
            out.append({"seq": int(fields["id"]), "event": fields["event"]})
    return out


def test_sse_replays_after_last_event_id_without_gaps(client):
    base = bus.history(f"env:{ENV}", "inc-sse")
    start = base[-1]["seq"] if base else 0
    client.g.rw("alert_open_incident", id="inc-sse", symptom="x/y", opened_at=1, weights_version="v")
    seqs = [bus.publish(f"env:{ENV}", "inc-sse", "hypothesis.status", {"id": f"h-{i}", "status": "open"})
            for i in range(8)]  # fmt: skip
    assert seqs == list(range(start + 1, start + 9))
    first = _read_sse(client, "inc-sse", {"Last-Event-ID": str(start)})
    assert [e["seq"] for e in first] == seqs
    rest = _read_sse(client, "inc-sse", {"Last-Event-ID": str(seqs[4])})  # disconnected after the 5th
    assert [e["seq"] for e in rest] == seqs[5:]
    # seq lives in Redis, not in the process: a fresh bus (a restarted API) continues the count
    assert RedisStreamBus().publish(f"env:{ENV}", "inc-sse", "error", {"code": "x", "message": "y"}) == seqs[-1] + 1


def test_sse_covers_a_diagnosis(client):
    _diagnosed(client)
    kinds = [e["event"] for e in _read_sse(client, "inc-1")]
    assert {"incident.status", "hypothesis.created", "evidence.added", "verdict"} <= set(kinds)


def test_errors_use_the_envelope(client, monkeypatch):
    r = client.get("/api/v1/incidents/nope", params=Q)
    assert r.status_code == 404 and r.json()["error"]["code"] == "INCIDENT_NOT_FOUND"
    assert r.json()["request_id"].startswith("req-") and r.headers["X-Request-ID"] == r.json()["request_id"]
    r = client.get("/api/v1/incidents", params={"env": "no-such-env"})
    assert r.status_code == 404 and r.json()["error"]["code"] == "ENV_NOT_FOUND"
    r = client.post("/api/v1/alerts", params=Q, json={"alert_id": "x"})
    assert r.status_code == 400 and r.json()["error"]["code"] == "VALIDATION_ERROR"
    r = client.get("/api/v1/incidents", params=Q | {"cursor": "%%%"})
    assert r.status_code == 400

    def down(*a, **k):
        raise GraphUnavailable("connection refused")

    monkeypatch.setattr("api.graph.EnvGraph.ro", down)
    r = client.get("/api/v1/incidents/inc-1", params=Q)
    assert r.status_code == 503 and r.json()["error"]["code"] == "GRAPH_UNAVAILABLE" and r.json()["request_id"]
    assert client.get("/api/v1/health").status_code == 200  # the process stays up


def test_api_key_when_configured(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "api_key", "s3cret")
    r = client.get("/api/v1/incidents", params=Q)
    assert r.status_code == 401 and r.json()["error"]["code"] == "UNAUTHORIZED"
    assert client.get("/api/v1/incidents", params=Q, headers={"X-API-Key": "s3cret"}).status_code == 200
    assert client.get("/api/v1/health").status_code == 200


def test_state_transitions(client):
    client.g.rw("alert_open_incident", id="inc-open", symptom="x/y", opened_at=1, weights_version="v")
    r = client.post("/api/v1/incidents/inc-open/resolve", params=Q, json={"by": "priya"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "INCIDENT_STATE"
    _diagnosed(client)
    again = client.post("/api/v1/incidents/inc-1/diagnose", params=Q)
    assert again.status_code == 409 and again.json()["error"]["code"] == "INCIDENT_STATE"
    assert client.post("/api/v1/incidents/inc-1/diagnose", params=Q | {"force": "true"}).status_code == 202
    assert client.get("/api/v1/incidents/inc-1", params=Q).json()["run"] == 3  # a new, kept run
    r = client.post("/api/v1/incidents/inc-1/resolve", params=Q, json={"by": "priya", "note": "flag off"})
    assert r.status_code == 200 and m.ResolveOut(**r.json()).status == "resolved"
    assert "priya" in [p.handle for p in graph_tools.who_knows("payment", env=ENV)]  # FIXED an incident rooted there


def test_notes_write_a_decision_and_a_change(client):
    body = {"by": "priya", "text": "currency deployed at 14:02",
            "change": {"service": "payment", "type": "deploy", "ts": "1970-01-01T00:01:30Z"}}  # fmt: skip
    r = client.post("/api/v1/incidents/inc-1/notes", params=Q, json=body)
    assert r.status_code == 201
    out = m.NoteOut(**r.json())
    assert out.decision_id == "d-1" and out.change_id == "chg-manual-inc-1-1"
    assert "chg-manual-inc-1-1" in [c.id for c in graph_tools.recent_changes("payment", 10, 100, env=ENV)]
    second = client.post("/api/v1/incidents/inc-1/notes", params=Q, json={"by": "bob", "text": "looking"}).json()
    assert second == {"decision_id": "d-2", "change_id": None}
    bad = client.post(
        "/api/v1/incidents/inc-1/notes", params=Q, json=body | {"change": body["change"] | {"service": "nope"}}
    )
    assert bad.status_code == 404 and bad.json()["error"]["code"] == "SERVICE_NOT_FOUND"


def test_cursor_pagination(client):
    seen, cursor = [], None
    while True:
        r = client.get("/api/v1/incidents", params=Q | {"limit": 2} | ({"cursor": cursor} if cursor else {}))
        page = m.IncidentPage(**r.json())
        seen += [i.id for i in page.items]
        cursor = page.next_cursor
        if cursor is None:
            break
    assert seen == ["inc-1", "inc-0", "inc-00"]  # newest first; mini_graph holds three incidents
    first = m.IncidentPage(**client.get("/api/v1/incidents", params=Q | {"limit": 2}).json())
    assert len(first.items) == 2 and first.next_cursor
    resolved = client.get("/api/v1/incidents", params=Q | {"status": "resolved"}).json()["items"]
    assert [i["id"] for i in resolved] == ["inc-0", "inc-00"]
    assert [i["id"] for i in client.get("/api/v1/incidents", params=Q | {"cause": "payment"}).json()["items"]] == [
        "inc-0"
    ]


def test_graph_views(client):
    one = m.Subgraph(**client.get("/api/v1/graph/subgraph", params=Q | {"center": "payment/Charge", "hops": 1}).json())
    two = m.Subgraph(**client.get("/api/v1/graph/subgraph", params=Q | {"center": "payment/Charge"}).json())
    assert {n.id for n in one.nodes} == {"payment/Charge", "checkout/PlaceOrder"}
    assert {n.id for n in one.nodes} < {n.id for n in two.nodes}
    assert any(e.from_ == "checkout/PlaceOrder" and e.to == "payment/Charge" for e in one.edges)
    raw = client.get("/api/v1/graph/subgraph", params=Q | {"center": "payment", "hops": 1, "incident": "inc-1"}).json()
    assert {"Operation", "Anomaly"} <= {n["label"] for n in raw["nodes"]} and "from" in raw["edges"][0]
    assert client.get("/api/v1/graph/subgraph", params=Q | {"center": "payment/Charge", "hops": 4}).status_code == 400

    br = m.BlastRadius(**client.get("/api/v1/blast-radius/redis", params=Q).json())
    assert [a.operation for a in br.affected] == [c.op for c in graph_tools.blast_radius("redis", env=ENV)]
    assert br.counts == {"services": 3, "operations": 4}
    assert client.get("/api/v1/blast-radius/nope", params=Q).json()["error"]["code"] == "SERVICE_NOT_FOUND"

    sim = m.SimulateOut(**client.post("/api/v1/simulate", params=Q, json={"service": "redis", "kind": "down"}).json())
    expected = what_if(client.app.state.graph, ENV, "redis", "down")
    assert [(p.op, p.kind, p.p) for p in sim.predicted] == [
        (p["op"], p["kind"], p["p"]) for p in expected["predictions"]
    ]
    both = client.post(
        "/api/v1/simulate", params=Q, json={"service": "redis", "operation": "redis/GET", "kind": "down"}
    )
    assert both.status_code == 400


def test_health_reports_every_dependency(client):
    h = m.Health(**client.get("/api/v1/health").json())
    assert h.falkordb == "ok" and h.openrouter in ("ok", "down", "not_configured") and h.jev == h.openrouter
    assert h.falkordb_mcp in ("ok", "down", "not_configured") and h.openconnector in ("ok", "down", "not_configured")


def test_openapi_lists_every_endpoint(client):
    paths = set(client.get("/openapi.json").json()["paths"])
    assert {
        "/api/v1/alerts",
        "/api/v1/incidents",
        "/api/v1/incidents/{incident_id}",
        "/api/v1/incidents/{incident_id}/diagnose",
        "/api/v1/incidents/{incident_id}/stream",
        "/api/v1/incidents/{incident_id}/hypotheses/{hid}/footprint",
        "/api/v1/incidents/{incident_id}/why-not/{service}",
        "/api/v1/incidents/{incident_id}/notes",
        "/api/v1/incidents/{incident_id}/resolve",
        "/api/v1/graph/subgraph",
        "/api/v1/blast-radius/{service}",
        "/api/v1/simulate",
        "/api/v1/health",
    } <= paths


def test_resolve_with_an_action_bumps_its_runbook_step(client, tmp_path):
    seed = tmp_path / "runbook.cypher"
    seed.write_text(
        "MATCH (s:Service {name: 'payment'}) CREATE (:Runbook {id: 'rb-flag', kind: 'errors', "
        "steps: ['Turn the flag off', 'Confirm the error rate drops'], success: '{}'})-[:FOR]->(s)",
        encoding="utf-8",
    )
    client.g.load_cypher(seed)
    body = _diagnosed(client)
    step = next(a for a in body["actions"] if a["name"] == "Confirm the error rate drops")  # the responder's own action
    missing = client.post("/api/v1/incidents/inc-1/resolve", params=Q, json={"by": "priya", "fixed_by_action": "a-99"})
    assert missing.status_code == 404 and missing.json()["error"]["code"] == "ACTION_NOT_FOUND"
    r = client.post("/api/v1/incidents/inc-1/resolve", params=Q, json={"by": "priya", "fixed_by_action": step["id"]})
    assert r.status_code == 200
    [row] = client.g.ro("action", id=f"inc-1:r2:{step['id']}")
    assert (row["runbook"], row["step"], row["success"]) == ("rb-flag", 1, '{"1": 1}')
