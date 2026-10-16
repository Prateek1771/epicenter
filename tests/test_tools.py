"""Typed tools (ADR 0003) on the fixtures: typed output, why_not answers, env binding."""

from pathlib import Path

import pytest

from api.ingest.seed import seed_indexes
from api.search.causal import diagnose
from api.tools import graph_tools as t

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def load(graph, monkeypatch):
    monkeypatch.setattr(t, "get_graph", lambda: graph)
    made = []

    def _load(fixture: str, name: str):
        g = graph.env(name)
        g.delete()
        seed_indexes(g)
        g.load_cypher(FIXTURES / fixture)
        made.append(g)
        return g

    yield _load
    for g in made:
        g.delete()


def test_read_tools_return_typed_rows(load):
    load("mini_graph.cypher", "test-tools")
    radius = t.blast_radius("redis", env="test-tools")
    assert [(c.op, c.hops, c.team) for c in radius][0] == ("cart/GetCart", 1, "platform")
    assert [c.op for c in t.upstream_candidates("inc-1", env="test-tools")] == [
        "payment/Charge",
        "checkout/PlaceOrder",
        "cart/GetCart",
    ]
    [path] = t.propagation_path("inc-1", "payment/Charge", env="test-tools")
    assert path.onsets == [120, 110, 100]
    [mech] = t.mechanism("inc-1", "payment/Charge", env="test-tools")
    assert [c["id"] for c in mech.changes] == ["ch-1"]
    assert [c.id for c in t.recent_changes("payment", minutes=10, until=100, env="test-tools")] == ["ch-1"]
    assert [p.handle for p in t.who_knows("payment", env="test-tools")] == ["alice", "bob", "carol"]
    assert [s.incident for s in t.similar_incidents("inc-1", env="test-tools")] == ["inc-0", "inc-00"]
    sim = t.simulate("redis", "down", env="test-tools")
    assert sim.predictions[0].op == "redis/GET" and sim.rules_version


@pytest.mark.parametrize(
    "fixture, incident, service, answer",
    [
        ("mini_graph.cypher", "inc-1", "payment", "is_root_cause"),
        ("mini_graph.cypher", "inc-1", "checkout", "victim"),
        ("mini_graph.cypher", "inc-1", "cart", "later_onset"),
        ("mini_graph.cypher", "inc-1", "redis", "no_anomaly"),
        ("healthy.cypher", "inc-h", "web", "lost_on_score"),
        ("healthy.cypher", "inc-h", "search", "later_onset"),
    ],
)
def test_why_not_answers(graph, load, fixture, incident, service, answer):
    load(fixture, "test-why")
    diagnose(graph, "test-why", incident)
    why = t.why_not(incident, service, env="test-why")
    assert why.answer == answer and why.summary
    if answer in ("victim", "later_onset"):
        assert why.evidence and all(e.verdict == "refutes" for e in why.evidence)


def test_why_not_not_upstream(graph, load):
    g = load("mini_graph.cypher", "test-why")
    g.rw(  # an anomaly on the frontend's cart page, which the alerting checkout page doesn't depend on
        "U2",
        op="frontend/GET /cart",
        id="an-inc-1-x",
        incident="inc-1",
        kind="latency",
        onset=130,
        score=0.5,
        self_ratio=None,
        child_ratio=None,
        ref=None,
        detector="short",
    )
    g.rw(
        "U1",
        caller_svc="shop",
        caller_op="shop/Home",
        caller_name="Home",
        callee_svc="shop-api",
        callee_kind="app",
        callee_op="shop-api/Get",
        callee_name="Get",
        rps=1.0,
        p95_ms=1.0,
        err_rate=0.0,
        ts=1,
    )
    g.rw(
        "U2",
        op="shop-api/Get",
        id="an-inc-1-y",
        incident="inc-1",
        kind="errors",
        onset=130,
        score=0.5,
        self_ratio=None,
        child_ratio=None,
        ref=None,
        detector="short",
    )
    diagnose(graph, "test-why", "inc-1")
    assert t.why_not("inc-1", "shop-api", env="test-why").answer == "not_upstream"


def test_tools_reject_unknown_environments(load):
    with pytest.raises(ValueError, match="unknown environment"):
        t.blast_radius("redis", env="no-such-env")


def test_every_tool_is_exposed_over_mcp():
    from api.tools.mcp_server import server

    assert [fn.__name__ for fn in t.TOOLS] == [
        "blast_radius",
        "upstream_candidates",
        "propagation_path",
        "mechanism",
        "why_not",
        "recent_changes",
        "similar_incidents",
        "who_knows",
        "simulate",
    ]
    assert server is not None
