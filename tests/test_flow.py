"""Agent flow (LLD §5): same verdict as the sequential steps, parallel investigators, resume after a crash, events."""

import threading
import time
from pathlib import Path

import pytest

from api.agents import flow
from api.events import bus
from api.ingest.seed import seed_indexes
from api.search import causal
from api.search.causal import diagnose
from api.tools import graph_tools

FIXTURES = Path(__file__).parent / "fixtures"
TERMINAL = {"confirmed", "refuted", "pruned"}


@pytest.fixture
def env(graph, tmp_path, monkeypatch):
    monkeypatch.setattr(graph_tools, "get_graph", lambda: graph)
    monkeypatch.setattr(flow, "get_graph", lambda: graph)
    made = []

    def load(fixture: str, name: str = "test-flow"):
        g = graph.env(name)
        g.delete()
        seed_indexes(g)
        g.load_cypher(FIXTURES / fixture)
        made.append(g)
        return g

    load.db = str(tmp_path / "cp.db")
    yield load
    for g in made:
        g.delete()


def _core(v: dict) -> dict:
    keys = ("status", "root_cause", "second_cause", "confidence", "explains", "statuses")
    return {k: v[k] for k in keys} | {"ranking": [(x["op"], x["status"], x["score"]) for x in v["ranking"]]}


@pytest.mark.parametrize(
    "fixture, incident, status, cause, second",
    [
        ("mini_graph.cypher", "inc-1", "diagnosed", "payment/Charge", None),
        ("multi_fault.cypher", "inc-m", "diagnosed", "db/Query", "cache/Get"),
        ("healthy.cypher", "inc-h", "no_root_cause", None, None),
    ],
)
def test_flow_matches_sequential_diagnosis(graph, env, fixture, incident, status, cause, second):
    g = env(fixture)
    seq = diagnose(graph, "test-flow", incident)
    agents = flow.run(incident, "test-flow", db_path=env.db)
    assert _core(agents) == _core(seq)  # no LLM anywhere: identical verdict (N7)
    assert (agents["status"], agents["root_cause"], agents["second_cause"]) == (status, cause, second)
    statuses = {r["status"] for r in g.ro("run_hypotheses", inc=incident, run=agents["run"])}
    assert statuses <= TERMINAL


def test_investigators_run_in_parallel_and_write_only_their_own_evidence(graph, env, monkeypatch):
    g = env("mini_graph.cypher")
    spans, real = [], causal.investigate

    def timed(r, hyp_id):
        t0 = time.perf_counter()
        time.sleep(0.2)
        out = real(r, hyp_id)
        spans.append((t0, time.perf_counter(), threading.get_ident()))
        return out

    monkeypatch.setattr(causal, "investigate", timed)
    v = flow.run("inc-1", "test-flow", db_path=env.db)
    spans.sort()
    assert len(spans) == 4 and any(b[0] < a[1] for a, b in zip(spans, spans[1:], strict=False))  # overlapping in time
    for row in g.ro("run_evidence_ids", inc="inc-1", run=v["run"]):
        n = row["hypothesis"].rsplit("h-", 1)[1]
        assert row["evidence"].rsplit(":", 1)[1].startswith(f"E{n}.")  # E<n>.<k> belongs to hypothesis n


def test_resume_after_a_crash_finishes_without_duplicates(graph, env, monkeypatch):
    g = env("mini_graph.cypher")
    real, crashed = causal.investigate, []

    def crash_once(r, hyp_id):
        if hyp_id.endswith("h-3") and not crashed:  # PlaceOrder's investigator dies mid-run
            crashed.append(hyp_id)
            real(r, hyp_id)  # it already wrote its evidence …
            raise RuntimeError("investigator killed")  # … and dies before reporting back

    monkeypatch.setattr(causal, "investigate", lambda r, h: crash_once(r, h) or real(r, h))
    with pytest.raises(RuntimeError, match="killed"):
        flow.run("inc-1", "test-flow", db_path=env.db)
    [inc] = g.ro("incident", inc="inc-1")
    assert inc["status"] == "diagnosing"

    v = flow.resume("inc-1", "test-flow", db_path=env.db)
    assert v["status"] == "diagnosed" and v["root_cause"] == "payment/Charge" and v["run"] == inc["run"]
    rows = g.ro("run_evidence_ids", inc="inc-1", run=v["run"])
    ids = [r["evidence"] for r in rows]
    assert len(ids) == len(set(ids))  # every evidence node and edge exactly once
    hyps = [r["id"] for r in g.ro("run_hypotheses", inc="inc-1", run=v["run"])]
    assert len(hyps) == len(set(hyps)) == 4
    assert {r["status"] for r in g.ro("run_hypotheses", inc="inc-1", run=v["run"])} <= TERMINAL


def test_events_are_ordered_and_cover_the_run(graph, env):
    env("mini_graph.cypher")
    before = bus.history("inc-1")
    last = before[-1]["seq"] if before else 0
    flow.run("inc-1", "test-flow", db_path=env.db)
    ev = bus.history("inc-1", after_seq=last)
    seqs = [e["seq"] for e in ev]
    assert seqs == sorted(seqs) and len(set(seqs)) == len(seqs)
    kinds = [e["event"] for e in ev]
    assert kinds[0] == "incident.status" and kinds[-1] == "incident.status"
    assert {"hypothesis.created", "evidence.added", "footprint", "hypothesis.status", "verdict"} <= set(kinds)
    assert ev[-1]["data"]["status"] == "diagnosed"


def test_skeptic_refutes_a_winner_that_does_not_explain_the_alert(graph, env, tmp_path):
    g = env("mini_graph.cypher")
    # The alert now sees latency, not errors. Onset order still holds, but a Charge error predicts errors upstream,
    # not latency (0.8 x 0.3 per hop falls under min_p), so Charge doesn't explain the alert itself.
    shift = tmp_path / "shift.cypher"
    shift.write_text("MATCH (a:Anomaly {id: 'an-inc-1-3'}) SET a.kind = 'latency'", encoding="utf-8")
    g.load_cypher(shift)
    seq = diagnose(graph, "test-flow", "inc-1")
    agents = flow.run("inc-1", "test-flow", db_path=env.db)
    assert _core(agents) == _core(seq)
    by = {
        (r["hypothesis"].rsplit(":", 1)[1], r["by"]) for r in g.ro("run_evidence_ids", inc="inc-1", run=agents["run"])
    }
    assert ("h-2", "skeptic") in by  # payment/Charge challenged …
    charge = next(x for x in agents["ranking"] if x["op"] == "payment/Charge")
    assert charge["status"] == "refuted" and agents["root_cause"] != "payment/Charge"  # … and refuted
    why = graph_tools.why_not("inc-1", "payment", env="test-flow")
    assert why.answer == "small_footprint" and "does not explain the alerting operation" in why.summary
