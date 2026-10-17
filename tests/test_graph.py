"""Query unit tests on tests/fixtures/mini_graph.cypher (LLD §12). Expected rows are documented in the fixture."""

import pytest

from api.graph import Graph, GraphUnavailable, query_stats

SYMPTOM = "frontend/GET /checkout"


def test_q1_upstream_candidates(env_test):
    rows = env_test.ro("Q1", symptom=SYMPTOM, inc="inc-1")
    assert [(r["op"], r["hops"], r["onset"]) for r in rows] == [
        ("payment/Charge", 2, 100),
        ("checkout/PlaceOrder", 1, 110),
        ("cart/GetCart", 2, 200),
    ]
    assert rows[0]["kinds"] == ["errors"] and rows[0]["strength"] == pytest.approx(0.95)


def test_q2_propagation_path(env_test):
    rows = env_test.ro("Q2", symptom=SYMPTOM, cand="payment/Charge", inc="inc-1")
    assert rows == [{"path": [SYMPTOM, "checkout/PlaceOrder", "payment/Charge"], "onsets": [120, 110, 100]}]


def test_q3_mechanism(env_test):
    [charge] = env_test.ro("Q3", cand="payment/Charge", inc="inc-1", lookback_s=600)
    assert charge["kind"] == "errors" and charge["self_ratio"] == 3.0
    assert [c["id"] for c in charge["changes"]] == ["ch-1"]
    [place] = env_test.ro("Q3", cand="checkout/PlaceOrder", inc="inc-1", lookback_s=600)
    assert place["changes"] == [] and place["child_ratio"] == 2.5
    # change outside the lookback is not attributed
    [late] = env_test.ro("Q3", cand="payment/Charge", inc="inc-1", lookback_s=10)
    assert late["changes"] == []


def test_q4_pagerank_on_scratch(env_test, blank):
    edges = env_test.ro("Q4a", inc="inc-1")
    assert [(e["caller"], e["callee"]) for e in edges] == [
        ("checkout/PlaceOrder", "cart/GetCart"),
        ("checkout/PlaceOrder", "payment/Charge"),
        (SYMPTOM, "checkout/PlaceOrder"),
    ]
    blank.rw("Q4_blame", edges=[{"caller": e["caller"], "callee": e["callee"], "w": e["err"]} for e in edges])
    ranks = {r["op"]: r["score"] for r in blank.ro("Q4b")}
    # Plain PageRank: the symptom ranks lowest and the two callees of PlaceOrder tie. PlaceOrder itself can outrank
    # them (it gets all of the symptom's rank, they split its share), which is why pagerank is a low-weight feature.
    assert min(ranks, key=ranks.get) == SYMPTOM
    assert ranks["payment/Charge"] == pytest.approx(ranks["cart/GetCart"])


def test_q5_similar_incidents(env_test):
    sig = [1.0] + [0.0] * 63
    rows = env_test.ro("Q5", sig=sig, inc="inc-1")
    assert [r["incident"] for r in rows] == ["inc-0", "inc-00"]
    assert rows[0]["score"] == pytest.approx(0.0, abs=1e-6)  # cosine distance
    assert (rows[0]["cause_type"], rows[0]["cause"], rows[0]["fixes"]) == (
        "Operation",
        "payment/Charge",
        ["disable flag paymentFailure"],
    )


def test_q6_simulate(env_test):
    rows = env_test.ro("Q6", cand="payment/Charge")
    assert [(r["op"], r["hops"]) for r in rows] == [("checkout/PlaceOrder", 1), (SYMPTOM, 2)]
    assert rows[1]["path"] == [SYMPTOM, "checkout/PlaceOrder", "payment/Charge"]
    assert env_test.ro("Q6", cand="payment/Refund") == []  # the only call into it carries no traffic


def test_blast_radius(env_test):
    rows = env_test.ro("blast_radius", svc="redis")
    assert [(r["op"], r["hops"], r["team"]) for r in rows] == [
        ("cart/GetCart", 1, "platform"),
        ("checkout/PlaceOrder", 2, "payments"),
        ("frontend/GET /cart", 2, "web"),
        (SYMPTOM, 3, "web"),
    ]


def test_why_not(env_test):
    [row] = env_test.ro("why_not", inc="inc-1", svc="checkout")
    assert (row["hypothesis"], row["status"]) == ("inc-1:r1:h-2", "refuted")
    assert [(e["id"], e["kind"]) for e in row["refuted_by"]] == [("inc-1:r1:E2", "victim")]
    assert env_test.ro("why_not", inc="inc-1", svc="redis") == []  # no hypothesis: caller falls back to Q1


def test_recent_changes(env_test):
    [row] = env_test.ro("recent_changes", svc="payment", since=0)
    assert (row["id"], row["authors"]) == ("ch-1", ["alice"])
    assert env_test.ro("recent_changes", svc="payment", since=61) == []


def test_who_knows(env_test):
    rows = env_test.ro("who_knows", svc="payment")
    assert [(r["handle"], r["score"], sorted(r["via"]), r["team"]) for r in rows] == [
        ("alice", 2, ["AUTHORED", "MEMBER_OF"], "payments"),
        ("bob", 2, ["FIXED", "MEMBER_OF"], "payments"),
        ("carol", 1, ["FIXED"], "payments"),
    ]


def test_injection_is_inert(env_test):
    before = env_test.ro("count_nodes")
    evil = "x'})-[:CALLS]->(n) DETACH DELETE n //"
    assert env_test.ro("Q1", symptom=evil, inc=evil) == []
    assert env_test.ro("count_nodes") == before


def test_upserts_are_idempotent(blank):
    call = dict(
        caller_svc="a",
        caller_op="a/x",
        caller_name="x",
        callee_svc="db",
        callee_kind="datastore",
        callee_op="db/get",
        callee_name="get",
        p95_ms=5.0,
        err_rate=0.0,
        ts=1,
    )
    blank.rw("U1", rps=1.0, **call)
    blank.rw("U1", rps=7.0, **call)
    change = {
        "service": "db",
        "service_kind": "datastore",
        "id": "ch-9",
        "type": "infra",
        "ts": 1,
        "summary": "docker stop db",
        "ref": None,
    }
    blank.rw("U3", **change)
    blank.rw("U3", **change)
    assert blank.ro("count_nodes") == [{"n": 5}]  # 2 services, 2 operations, 1 change
    assert blank.ro("Q6", cand="db/get") == [{"op": "a/x", "hops": 1, "path": ["a/x", "db/get"], "rps": [7.0]}]


def test_change_on_unseen_service_creates_it(blank):
    # a fault's change is written before the topology tick may have seen the service (phase 9)
    blank.rw("U3", service="mongodb", service_kind="datastore", id="ch-1", type="infra", ts=5, summary="stop", ref=None)
    assert blank.ro("count_nodes") == [{"n": 2}]
    assert blank.ro("recent_changes", svc="mongodb", since=0)[0]["id"] == "ch-1"


def test_every_query_is_timed(env_test):
    env_test.ro("Q6", cand="payment/Charge")
    stats = query_stats()
    assert "Q6" in stats and stats["Q6"]["p50"] <= stats["Q6"]["p95"]


def test_unreachable_raises_graph_unavailable():
    g = Graph("redis://:x@127.0.0.1:1", timeout_s=0.2)
    assert g.ping() is False
    with pytest.raises(GraphUnavailable):
        g.env("nowhere").ro("count_nodes")
