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
        "/api/v1/incidents/{incident_id}/graph",
        "/api/v1/incidents/{incident_id}/stream",
        "/api/v1/incidents/{incident_id}/hypotheses/{hid}/footprint",
        "/api/v1/incidents/{incident_id}/why-not/{service}",
        "/api/v1/incidents/{incident_id}/notes",
        "/api/v1/incidents/{incident_id}/resolve",
        "/api/v1/graph/subgraph",
        "/api/v1/blast-radius/{service}",
        "/api/v1/simulate",
        "/api/v1/health",
        "/api/v1/envs",
        "/api/v1/services",
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


def test_incident_graph_has_everything_the_canvas_draws(client):
    before = m.IncidentGraph(**client.get("/api/v1/incidents/inc-1/graph", params=Q).json())
    assert before.run == 1 and before.symptom == "frontend/GET /checkout"  # the fixture's run 1
    _diagnosed(client)
    g = m.IncidentGraph(**client.get("/api/v1/incidents/inc-1/graph", params=Q).json())
    assert (g.run, g.status, g.root_cause, g.second_cause) == (2, "diagnosed", "payment/Charge", None)
    ops = {n.id for n in g.nodes}
    assert {h.op for h in g.hypotheses} <= ops and g.symptom in ops
    assert all(set(e.path) <= ops for h in g.hypotheses for e in h.evidence)  # every evidence path is drawable
    charge = next(h for h in g.hypotheses if h.op == "payment/Charge")
    assert charge.status == "confirmed" and {e.kind for e in charge.evidence} == {"propagation", "change", "footprint"}
    assert ("checkout/PlaceOrder", "payment/Charge") in {(c.src, c.dst) for c in g.edges}
    assert next(n for n in g.nodes if n.id == "payment/Charge").anomaly.kind == "errors"
    assert client.get("/api/v1/incidents/nope/graph", params=Q).status_code == 404
    events = bus.history(f"env:{ENV}", "inc-1")
    assert g.last_seq == (events[-1]["seq"] if events else 0)  # the stream resumes right after the snapshot
    svcs = m.Services(**client.get("/api/v1/services", params=Q).json())
    assert {"payment", "redis"} <= {s.name for s in svcs.items}
    assert next(s for s in svcs.items if s.name == "redis").kind == "datastore"
    envs = m.Envs(**client.get("/api/v1/envs").json())
    assert ENV in envs.items and envs.default


def test_service_changes_for_the_map_side_panel(client, monkeypatch):
    """Phase 12 /map: recent changes on a service, newest first, with their authors; bounded by `hours`."""
    from api.tools import graph_tools

    monkeypatch.setattr(graph_tools.time, "time", lambda: 3600)  # the fixture's change is at ts 60
    r = client.get("/api/v1/services/payment/changes", params=Q | {"hours": 1})
    assert r.status_code == 200, r.text
    [c] = r.json()["items"]
    assert (c["id"], c["type"], c["authors"]) == ("ch-1", "flag", ["alice"])
    assert client.get("/api/v1/services/redis/changes", params=Q).json()["items"] == []


def test_blast_radius_dossier_routes(client):
    """/blast-radius bento: people to pull in, runbooks, and the riskiest services when none is picked."""
    people = client.get("/api/v1/services/payment/people", params=Q).json()["items"]
    alice = next(p for p in people if p["handle"] == "alice")
    assert "AUTHORED" in alice["via"]  # she authored the flag change on payment (mini_graph ch-1)
    assert client.get("/api/v1/services/nope/people", params=Q).status_code == 404
    assert isinstance(client.get("/api/v1/services/payment/runbooks", params=Q).json()["items"], list)
    risk = client.get("/api/v1/services/risk", params=Q | {"limit": 50}).json()["items"]
    pay = next(r for r in risk if r["name"] == "payment")
    assert pay["callers"] >= 1  # checkout calls it
    assert [r["incidents"] for r in risk] == sorted((r["incidents"] for r in risk), reverse=True)


def test_graph_explore_is_bounded_and_spans_labels(client):
    """/map Network view: every label, ids are Label:key, edges only between returned nodes, capped by limit."""
    g = client.get("/api/v1/graph/explore", params=Q | {"limit": 500}).json()
    labels = {n["label"] for n in g["nodes"]}
    assert {"Service", "Operation", "Team"} <= labels and set(g["label_counts"]) >= labels
    ids = {n["id"] for n in g["nodes"]}
    assert "Service:payment" in ids and all(e["from"] in ids and e["to"] in ids for e in g["edges"])
    assert {"HAS_OP", "CALLS", "OWNED_BY"} <= {e["type"] for e in g["edges"]}
    small = client.get("/api/v1/graph/explore", params=Q | {"limit": 10}).json()
    assert len(small["nodes"]) == 10 and small["truncated"] and small["nodes"][0]["label"] == "Service"
    assert g == client.get("/api/v1/graph/explore", params=Q | {"limit": 500}).json()  # deterministic


def test_simulate_lab_routes(client):
    """/simulate lab: compare a prediction with past incidents, list saved experiments, show the rules."""
    _diagnosed(client)  # inc-1 is rooted at payment/Charge
    body = {"service": "payment", "kind": "errors"}
    cmp = client.post("/api/v1/simulate/compare", params=Q, json=body).json()
    [row] = [r for r in cmp["items"] if r["incident"] == "inc-1"]
    assert 0 <= row["coverage"] <= 1 and row["explains"].startswith("explains ")
    assert cmp == client.post("/api/v1/simulate/compare", params=Q, json=body).json()  # deterministic
    assert (
        client.post("/api/v1/simulate/compare", params=Q, json={"service": "nope", "kind": "down"}).status_code == 404
    )
    saved = client.post("/api/v1/simulate", params=Q, json={"service": "redis", "kind": "down", "save": True}).json()
    sims = client.get("/api/v1/simulations", params=Q).json()["items"]
    assert sims[0]["id"] == saved["simulation_id"] and sims[0]["operations"] == saved["counts"]["operations"]
    rules = client.get("/api/v1/rules").json()["items"]
    assert rules and [r["id"] for r in rules] == sorted(r["id"] for r in rules)


def test_export_markdown_human_and_agent(client):
    """Incident page downloads: incident_info.md for people, an agent context file for coding agents. Deterministic."""
    _diagnosed(client)
    r = client.get("/api/v1/incidents/inc-1/export.md", params=Q)
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/markdown")
    assert 'filename="inc-1.incident_info.md"' in r.headers["content-disposition"]
    md = r.text
    assert md.startswith("# Incident inc-1") and "**Root cause:** `payment/Charge`" in md and "## Evidence" in md
    a = client.get("/api/v1/incidents/inc-1/export.md", params=Q | {"flavor": "agent"})
    assert 'filename="inc-1.agent.md"' in a.headers["content-disposition"]
    assert "## Where to look" in a.text and "`payment`" in a.text and "## Constraints" in a.text
    assert a.text == client.get("/api/v1/incidents/inc-1/export.md", params=Q | {"flavor": "agent"}).text
    assert client.get("/api/v1/incidents/nope/export.md", params=Q).status_code == 404
    bad = client.get("/api/v1/incidents/inc-1/export.md", params=Q | {"flavor": "x"})
    assert bad.status_code == 400 and bad.json()["error"]["code"] == "VALIDATION_ERROR"


def test_verdict_card_and_canvas_extras(client):
    """Phase 12: owner, contributing change, found-in on the verdict; changes + alert time on the canvas; precedent."""
    body = _diagnosed(client)
    v = m.Verdict(**body["verdict"])
    assert v.owner == "payments" and v.change and v.change.id == "ch-1" and v.change.service == "payment"
    assert v.found_in_ms is not None and v.found_in_ms > 0
    fix = next(a for a in body["actions"] if a["name"] == "disable flag paymentFailure")  # chosen by history
    assert fix["chosen_by"] == "history" and fix["precedent"] == ["inc-0"]
    g = m.IncidentGraph(**client.get("/api/v1/incidents/inc-1/graph", params=Q).json())
    assert g.alert_ts == 130 and [(c.id, c.service, c.ts) for c in g.changes] == [("ch-1", "payment", 60)]


def test_service_map_topology(client):
    s = m.Topology(**client.get("/api/v1/graph/topology", params=Q).json())
    by = {n.id: n for n in s.nodes}
    assert s.level == "service" and not s.truncated
    assert by["payment"].owner == "payments" and by["payment"].ops == len(client.g.ro("service_ops", svc="payment"))
    assert any(e.src == "checkout" and e.dst == "payment" for e in s.edges)
    assert all(e.src != e.dst for e in s.edges)  # calls inside one service aren't service edges
    o = m.Topology(**client.get("/api/v1/graph/topology", params=Q | {"level": "operation"}).json())
    assert {n.id for n in o.nodes} >= {"payment/Charge", "checkout/PlaceOrder"}
    assert any(e.src == "checkout/PlaceOrder" and e.dst == "payment/Charge" for e in o.edges)
    # the fixture's incidents are from 1970, so "recent" halos come from the query with an old cutoff
    halos = client.g.ro("map_anomalies", since=0)
    assert {(h["op"], h["incident"]) for h in halos} >= {("payment/Charge", "inc-1")}
    assert all(h["incident"] != "inc-0" for h in halos)  # resolved incidents leave no halo


def test_blast_radius_and_what_if_carry_their_edges(client):
    br = m.BlastRadius(**client.get("/api/v1/blast-radius/redis", params=Q).json())
    drawn = set(br.sources) | {a.operation for a in br.affected}
    assert br.sources == ["redis/GET"] and br.edges and all({e.src, e.dst} <= drawn for e in br.edges)
    sim = m.SimulateOut(**client.post("/api/v1/simulate", params=Q, json={"service": "redis", "kind": "down"}).json())
    assert sim.edges and all({e.src, e.dst} <= {p.op for p in sim.predicted} for e in sim.edges)


def test_canvas_snapshot_carries_the_runs_receipts(client):
    body = _diagnosed(client)
    g = m.IncidentGraph(**client.get("/api/v1/incidents/inc-1/graph", params=Q).json())
    assert g.receipts and g.receipts["run"] == body["run"] and g.receipts["queries"][0]["n"] == 1
