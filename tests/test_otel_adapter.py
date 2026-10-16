"""`otel` adapter (api/ingest/otel.py): flip-commerce files, OTel Demo HTTP sources, gaps, the change journal."""

import json

import httpx

from api.ingest.changes import read_journal
from api.ingest.otel import OtelAdapter, parse_nginx, parse_winston
from tests.test_spans import request

PREFIXES = {"/node/": "flip-node"}


def test_nginx_line_names_its_upstream_operation():
    line = '1760600000.250 "GET /node/products/64f0c0ffee0123456789abcd?x=1 HTTP/1.1" 503 0.250 127.0.0.1:5001 0.240'
    s = parse_nginx(line, PREFIXES)
    assert s.op == "nginx/GET /node/products/{id}" and s.error
    assert s.upstream_op == "flip-node/GET /products/{id}" and s.upstream_ms == 240.0
    assert round(s.start, 3) == 1760600000.0
    assert parse_nginx("garbage", PREFIXES) is None


def test_winston_json_line():
    ln = parse_winston('{"level":"error","message":"MongoDB socket dropped","timestamp":"2026-10-16T08:00:00.123Z"}',
                       "flip-node")  # fmt: skip
    assert (ln.service, ln.level, ln.text, ln.ts) == ("flip-node", "ERROR", "MongoDB socket dropped", 1792137600)
    assert parse_winston("plain text", "flip-node") is None


def test_flip_mode_reads_files_and_records_gaps(tmp_path):
    traces = tmp_path / "spans.jsonl"
    traces.write_text("\n".join(json.dumps(request(f"t{i}", 100.0 + i, 30, 20)) for i in range(5)) + "\n{cut",
                      encoding="utf-8")  # fmt: skip
    nginx = tmp_path / "access.log"
    nginx.write_text('101.040 "GET /node/products/64f0c0ffee0123456789abcd HTTP/1.1" 200 0.040 x 0.031\n')
    ad = OtelAdapter("flip-commerce", "flip", {"otel_file": str(traces), "nginx_log": str(nginx),
                                               "prefixes": PREFIXES, "kinds": {"nginx": "proxy"},
                                               "log_dir": str(tmp_path / "missing")})  # fmt: skip
    calls = {(c.caller_op, c.callee_op): c for c in ad.calls(100, 110)}
    assert ("nginx/GET /node/products/{id}", "flip-node/GET /products/{id}") in calls
    assert calls[("nginx/GET /node/products/{id}", "flip-node/GET /products/{id}")].caller_kind == "proxy"
    assert ("flip-node/GET /products/{id}", "mongodb/find products") in calls
    assert list(ad.logs(0, 200)) == [] and ad.gaps == ["logs"]  # the cut line is skipped, no logs is a gap


def test_demo_mode_jaeger_and_a_down_prometheus(tmp_path):
    trace = {
        "processes": {"p": {"serviceName": "payment"}},
        "spans": [
            {
                "traceID": "x",
                "spanID": "1",
                "references": [],
                "operationName": "Charge",
                "processID": "p",
                "startTime": 100_000_000,
                "duration": 1_000,
                "tags": [{"key": "span.kind", "value": "server"}],
            }
        ],
    }

    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path == "/api/services":
            return httpx.Response(200, json={"data": ["payment"]})
        if req.url.path == "/api/traces":
            return httpx.Response(200, json={"data": [trace]})
        raise httpx.ConnectError("down", request=req)  # prometheus is down

    ad = OtelAdapter("astronomy-shop", "demo", {"jaeger_url": "http://jaeger", "prometheus_url": "http://prom",
                                                 "prom_queries": {"cpu": "q"}},
                     client=httpx.Client(transport=httpx.MockTransport(handler)))  # fmt: skip
    ops = {s.op for s in ad.series(90, 110)}
    assert "payment/Charge" in ops and ad.gaps == ["metrics"]


def test_journal_filters_env_and_time(tmp_path):
    j = tmp_path / "changes.jsonl"
    rows = [
        {
            "id": "c1",
            "env": "flip-commerce",
            "service": "mongodb",
            "service_kind": "datastore",
            "type": "infra",
            "ts": 50,
            "summary": "old",
        },
        {
            "id": "c2",
            "env": "flip-commerce",
            "service": "mongodb",
            "service_kind": "datastore",
            "type": "infra",
            "ts": 150,
            "summary": "docker stop fk-mongo-primary",
        },
        {"id": "c3", "env": "astronomy-shop", "service": "payment", "type": "flag", "ts": 150, "summary": "x"},
    ]
    j.write_text("\n".join(json.dumps(r) for r in rows) + "\nnot json\n")
    [c] = read_journal(j, "flip-commerce", 100)
    assert (c.id, c.service_kind, c.summary) == ("c2", "datastore", "docker stop fk-mongo-primary")


def test_live_window_stops_at_the_last_complete_bucket(graph, tmp_path):
    """Steady traffic up to 'now', ingested mid-bucket: the half-filled last bucket must not read as `down`."""
    from api.ingest.window import ingest_window

    now = 1_800_000_003  # 3 s into a 5 s bucket
    traces = tmp_path / "spans.jsonl"
    lines = [json.dumps(request(f"t{i}", now - 900 + i * 0.5, 30, 20)) for i in range(1800)]  # 2 req/s, 15 min
    traces.write_text("\n".join(lines), encoding="utf-8")
    ad = OtelAdapter("test-live", "flip", {"otel_file": str(traces), "prefixes": PREFIXES})
    env = graph.env("test-live")
    env.delete()
    try:
        out = ingest_window(ad, "test-live", graph, "inc-live", "flip-node/GET /products/{id}", now - 60, until=now)
    finally:
        env.delete()
    assert "down" not in out["by_kind"], out["top"]


def test_flip_mode_reads_rotated_span_files(tmp_path):
    (tmp_path / "spans-2026-10-16T11-17-20.jsonl").write_text(json.dumps(request("old", 100.0, 30, 20)) + "\n")
    (tmp_path / "spans.jsonl").write_text(json.dumps(request("new", 105.0, 30, 20)) + "\n")
    ad = OtelAdapter("flip-commerce", "flip", {"otel_file": str(tmp_path / "spans.jsonl"), "prefixes": PREFIXES})
    assert {s.trace for s in ad.load(0, 200)} == {"old", "new"}


def test_alert_ingest_runs_once_even_when_the_window_was_healthy(graph, tmp_path, monkeypatch):
    from api.ingest import live, write
    from api.ingest.seed import seed_indexes

    f = tmp_path / "inc.cypher"
    f.write_text("CREATE (:Incident {id: 'inc-h', status: 'open', symptom: 'web/GET /', opened_at: 160});")
    env = graph.env("test-live-once")
    env.delete()
    seed_indexes(env)
    env.load_cypher(f)
    seen = []

    def window(ad, env_name, g, incident, *a, **k):  # a healthy window: a new ingest, no anomalies
        seen.append(incident)
        write.new_ingest(g.env(env_name), incident)
        return {"calls": 0, "changes": 0, "anomalies": 0, "gaps": []}

    monkeypatch.setattr(live, "adapter_for", lambda e: object())
    monkeypatch.setattr(live, "ingest_window", window)
    try:
        assert live.ingest_for_alert(graph, "test-live-once", "inc-h") is not None
        assert live.ingest_for_alert(graph, "test-live-once", "inc-h") is None  # a rerun keeps the alert-time window
        assert live.ingest_for_alert(graph, "test-live-once", "inc-h", again=True) is not None
    finally:
        env.delete()
    assert seen == ["inc-h", "inc-h"]
