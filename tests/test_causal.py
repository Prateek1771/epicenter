"""Causal search: table-driven rule tests (LLD §12 "rule tests") and a full diagnosis on a copy of mini_graph."""

from pathlib import Path

import pytest

from api.ingest.seed import seed_indexes
from api.search import causal
from api.search.causal import best_path, diagnose, is_victim, propagation_passes

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.mark.parametrize(
    "onsets, ok",
    [
        ([120, 110, 100], True),  # started at the candidate, moved towards the symptom
        ([100, 130, 160], False),  # wrong direction
        ([100, 110, 120], True),  # each hop may be up to skew later: clock skew between services adds up
        ([100, 110], True),  # within the 15 s skew
        ([100, 116], False),  # just past the skew
        ([120, None, 100], False),  # the problem didn't pass through the middle op
        ([None, 110, 100], True),  # the symptom itself has no anomaly (load generator): skipped
        ([None, None, 100], False),
    ],
)
def test_onset_order_rule(onsets, ok):
    assert propagation_passes(onsets, skew_s=15) is ok


def test_best_path_prefers_passing_then_short_then_lexicographic():
    paths = [
        {"path": ["s", "a", "c"], "onsets": [30, 60, 10]},  # fails
        {"path": ["s", "b", "x", "c"], "onsets": [30, 20, 15, 10]},  # passes, longer
        {"path": ["s", "b", "c"], "onsets": [30, 20, 10]},  # passes, short
        {"path": ["s", "a2", "c"], "onsets": [30, 20, 10]},  # passes, short, smaller
    ]
    best, ok = best_path(paths, 15)
    assert ok and best["path"] == ["s", "a2", "c"]
    assert best_path([], 15) == (None, False)


@pytest.mark.parametrize(
    "self_ratio, child_ratio, victim",
    [
        (0.3, 2.5, True),
        (1.0, 2.0, True),
        (1.0, 1.9, False),  # child not 2× self
        (0.5, 1.4, False),  # child ratio too small to matter
        (3.0, 0.2, False),  # self-caused
        (None, 2.5, False),  # no span data
    ],
)
def test_victim_rule(self_ratio, child_ratio, victim):
    assert is_victim(self_ratio, child_ratio) is victim


@pytest.fixture
def causal_env(graph):
    g = graph.env("test-causal")
    g.delete()
    seed_indexes(g)
    g.load_cypher(FIXTURES / "mini_graph.cypher")
    yield g
    g.delete()


def test_mini_graph_root_cause_and_victim(graph, causal_env):
    v = diagnose(graph, "test-causal", "inc-1")
    assert v["run"] == 2  # the fixture already holds run 1
    assert v["root_cause"] == "payment/Charge"
    rows = {r["op"]: r for r in causal_env.ro("run_hypotheses", inc="inc-1", run=2)}
    assert rows["payment/Charge"]["status"] == "confirmed"
    charge_ev = {(rel, kind) for rel, kind, _ in rows["payment/Charge"]["evidence"]}
    assert charge_ev == {("SUPPORTED_BY", "propagation"), ("SUPPORTED_BY", "change")}
    # the loudest downstream victim is refuted by the victim rule
    assert rows["checkout/PlaceOrder"]["status"] == "refuted"
    assert ("REFUTED_BY", "victim") in {(rel, kind) for rel, kind, _ in rows["checkout/PlaceOrder"]["evidence"]}
    # GetCart went bad after the symptom: refuted by onset order
    assert rows["cart/GetCart"]["status"] == "refuted"
    assert rows["cart/GetCart"]["evidence"][0][:2] == ["REFUTED_BY", "propagation"]
    # the symptom is its own hypothesis (it has an anomaly) and is a victim too
    assert rows["frontend/GET /checkout"]["hops"] == 0 and rows["frontend/GET /checkout"]["status"] == "refuted"
    # why_not reads the current run only; run 1's hypothesis is kept as history
    [why] = causal_env.ro("why_not", inc="inc-1", svc="checkout")
    assert why["hypothesis"].startswith("inc-1:r2:")
    assert causal_env.ro("run_hypotheses", inc="inc-1", run=1)[0]["id"] == "inc-1:r1:h-2"


def test_rerun_is_identical_and_kept(graph, causal_env):
    a = diagnose(graph, "test-causal", "inc-1")
    b = diagnose(graph, "test-causal", "inc-1")
    assert (a["run"], b["run"]) == (2, 3)
    ra = causal_env.ro("run_hypotheses", inc="inc-1", run=2)
    rb = causal_env.ro("run_hypotheses", inc="inc-1", run=3)
    strip = [{k: v for k, v in r.items() if k != "id"} for r in ra]
    assert strip == [{k: v for k, v in r.items() if k != "id"} for r in rb]  # byte-identical score_parts, statuses
    assert a["ranking"] == b["ranking"] and a["confidence"] == b["confidence"]


def test_scratch_graph_deleted_even_when_pagerank_fails(graph, causal_env, monkeypatch):
    real_ro = causal.EnvGraph.ro

    def failing_ro(self, qid, **params):
        if qid == "Q4b":
            raise RuntimeError("algo.pageRank unavailable")
        return real_ro(self, qid, **params)

    monkeypatch.setattr(causal.EnvGraph, "ro", failing_ro)
    v = diagnose(graph, "test-causal", "inc-1")
    assert v["pagerank_impl"] == "networkx" and v["root_cause"] == "payment/Charge"
    assert graph.scratch("inc-1").ro("count_nodes") == []  # gone (reads on a missing graph return [])
