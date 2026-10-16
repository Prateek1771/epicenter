"""Spans → calls / series (api/ingest/spans.py): the operation model both live modes share."""

from api.ingest import spans as sp


def _attr(k, v):
    return {"key": k, "value": {"intValue": str(v)} if isinstance(v, int) else {"stringValue": v}}


def _span(trace, sid, parent, name, kind, t, ms, attrs=(), err=False):
    ns = int(t * 1e9)
    return {"traceId": trace, "spanId": sid, "parentSpanId": parent, "name": name, "kind": kind,
            "startTimeUnixNano": str(ns), "endTimeUnixNano": str(ns + int(ms * 1e6)),
            "attributes": [_attr(k, v) for k, v in attrs], "status": {"code": 2 if err else 0}}  # fmt: skip


def otlp(svc, spans):
    return {"resourceSpans": [{"resource": {"attributes": [_attr("service.name", svc)]},
                               "scopeSpans": [{"spans": spans}]}]}  # fmt: skip


def request(trace, t, total_ms, db_ms, err=False):
    """flip-node: raw node:http server span "GET" → internal mongoose span → mongodb client span."""
    return otlp("flip-node", [
        _span(trace, "a", "", "GET", 2, t, total_ms, [("url.path", "/products/64f0c0ffee0123456789abcd"),
                                                     ("http.response.status_code", 503 if err else 200)]),
        _span(trace, "b", "a", "mongoose.Product.findOne", 1, t + 0.001, db_ms + 1),
        _span(trace, "c", "b", "mongodb.find", 3, t + 0.002, db_ms,
              [("db.system", "mongodb"), ("db.operation", "find"), ("db.mongodb.collection", "products")], err),
    ])  # fmt: skip


def test_operations_routes_and_datastore_callee():
    spans = sp.from_otlp(request("t1", 100.0, 30, 20))
    ops = sorted(s.op for s in spans if sp.is_op(s))
    # the id segment is a route parameter, the internal mongoose span is plumbing, mongodb is a datastore
    assert ops == ["flip-node/GET /products/{id}", "mongodb/find products"]
    [c] = sp.calls(spans, 100, 101)
    assert (c.caller_op, c.callee_op, c.callee_kind) == ("flip-node/GET /products/{id}", "mongodb/find products",
                                                         "datastore")  # fmt: skip


def test_error_rate_p95_and_self_child_split():
    spans = []
    for i in range(10):
        spans += sp.from_otlp(request(f"t{i}", 100.0 + i * 0.1, 30, 20, err=i < 3))
    [c] = sp.calls(spans, 100, 102)
    assert c.err_rate == 0.3 and c.rps == 5.0
    by = {(s.op, s.metric): s for s in sp.series(spans, 100, 110, 5, "otel:test")}
    assert by[("flip-node/GET /products/{id}", "errors")].values[0] == 0.3
    # the request spends 21 ms in the mongoose call (the outermost span on the way to mongodb), 9 ms itself
    assert round(by[("flip-node/GET /products/{id}", "child_ms")].values[0], 3) == 21.0
    assert round(by[("flip-node/GET /products/{id}", "self_ms")].values[0], 3) == 9.0
    assert by[("mongodb/find products", "latency")].kind == "latency"


def test_entry_op_is_the_busiest_inbound():
    spans = sp.from_otlp(request("t1", 100.0, 30, 20)) + sp.from_otlp(request("t2", 101.0, 30, 20))
    assert sp.entry_ops(spans) == {"flip-node": "flip-node/GET /products/{id}", "mongodb": "mongodb/find products"}


def test_jaeger_trace_parses_to_the_same_model():
    trace = {
        "processes": {"p1": {"serviceName": "checkout"}, "p2": {"serviceName": "payment"}},
        "spans": [
            {"traceID": "x", "spanID": "1", "references": [], "operationName": "oteldemo.CheckoutService/PlaceOrder",
             "processID": "p1", "startTime": 100_000_000, "duration": 50_000, "tags": [{"key": "span.kind",
                                                                                         "value": "server"}]},
            {"traceID": "x", "spanID": "2", "references": [{"refType": "CHILD_OF", "spanID": "1"}],
             "operationName": "oteldemo.PaymentService/Charge", "processID": "p1", "startTime": 100_001_000,
             "duration": 40_000, "tags": [{"key": "span.kind", "value": "client"}]},
            {"traceID": "x", "spanID": "3", "references": [{"refType": "CHILD_OF", "spanID": "2"}],
             "operationName": "oteldemo.PaymentService/Charge", "processID": "p2", "startTime": 100_002_000,
             "duration": 30_000, "tags": [{"key": "span.kind", "value": "server"},
                                          {"key": "otel.status_code", "value": "ERROR"}]},
        ],
    }  # fmt: skip
    [c] = sp.calls(sp.from_jaeger(trace), 100, 101)
    assert (c.caller_op, c.callee_op, c.err_rate) == (
        "checkout/oteldemo.CheckoutService/PlaceOrder",
        "payment/oteldemo.PaymentService/Charge",
        1.0,
    )


def test_route_collapses_skus_and_static_files():
    assert sp.route("/api/products/2ZYFJ3GM2N") == "/api/products/{id}"
    assert sp.route("/_next/static/chunks/3bcp_90ku75or.js") == "/_next/static/chunks/{file}"
    assert sp.route("/products/RoofBinoculars.jpg") == "/products/{file}"
    assert sp.route("/api/checkout") == "/api/checkout"  # words stay routes
    assert sp.route("/api/data/") == "/api/data" and sp.route("/") == "/"
    # a span named "METHOD /path" (Next.js, the demo's frontend) is normalized like a bare-method span's route
    assert sp.op_name("GET /api/products/2ZYFJ3GM2N", {}) == "GET /api/products/{id}"
    assert sp.op_name("oteldemo.AdService/GetAds", {}) == "oteldemo.AdService/GetAds"


def test_a_slow_parent_never_lands_before_the_child_that_failed_it():
    # the request starts at 104 (bucket 100) but waits 4 s before its mongodb call fails at 108.0 (bucket 105)
    spans = sp.from_otlp(otlp("flip-node", [
        _span("t", "a", "", "GET", 2, 104.0, 4100, [("url.path", "/products"), ("http.response.status_code", 503)]),
        _span("t", "c", "a", "mongodb.find", 3, 108.0, 50,
              [("db.system", "mongodb"), ("db.operation", "find"), ("db.mongodb.collection", "products")], True),
    ]))  # fmt: skip
    by = {(s.op, s.metric): s for s in sp.series(spans, 100, 120, 5, "otel:test")}
    assert by[("flip-node/GET /products", "errors")].ts.tolist() == [105]
    assert by[("mongodb/find products", "errors")].ts.tolist() == [105]
