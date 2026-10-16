"""Memory (USER_FLOW Flow 5): a resolved incident's fix ranks first when the same fault comes back."""

import json
from pathlib import Path

import pytest

from api.agents import flow
from api.events import bus
from api.ingest.seed import seed_indexes
from api.tools import graph_tools

FIXTURES = Path(__file__).parent / "fixtures"
ENV = "test-memory"

RUNBOOK = """MATCH (s:Service {name: 'payment'})
CREATE (:Runbook {id: 'rb-pay', kind: 'errors', success: '{}',
                  steps: ['Check recent flag changes', 'Turn the flag off', 'Restart payment']})-[:FOR]->(s)"""
# The same fault again: inc-1's anomalies copied onto a new incident inc-2
REPEAT = """MATCH (a:Anomaly {incident: 'inc-1'})-[:ON]->(o:Operation)
CREATE (:Anomaly {id: replace(a.id, 'inc-1', 'inc-2'), incident: 'inc-2', kind: a.kind, onset: a.onset, score: a.score,
                  self_ratio: a.self_ratio, child_ratio: a.child_ratio, detector: a.detector})-[:ON]->(o);
CREATE (:Incident {id: 'inc-2', status: 'open', symptom: 'frontend/GET /checkout', opened_at: 900,
                   weights_version: '2026-10-15.v2'})"""


@pytest.fixture
def env(graph, monkeypatch, tmp_path):
    monkeypatch.setattr(graph_tools, "get_graph", lambda: graph)
    monkeypatch.setattr(flow, "get_graph", lambda: graph)
    g = graph.env(ENV)
    g.delete()
    seed_indexes(g)
    g.load_cypher(FIXTURES / "mini_graph.cypher")
    for name, text in (("runbook", RUNBOOK), ("repeat", REPEAT)):
        (tmp_path / f"{name}.cypher").write_text(text, encoding="utf-8")
    g.load_cypher(tmp_path / "runbook.cypher")
    g.tmp, g.db = tmp_path, str(tmp_path / "cp.db")
    yield g
    g.delete()


def test_repeat_incident_recalls_the_fix_and_ranks_it_first(env):
    flow.run("inc-1", ENV, db_path=env.db)  # no LLM, no Jev: history order, then runbook order
    first = env.ro("run_actions", inc="inc-1")
    assert [a["name"] for a in first][:3] == ["disable flag paymentFailure", "Check recent flag changes",
                                              "Turn the flag off"]  # fmt: skip
    # inc-0's fix comes first: memory (inc-0 was resolved by it), the runbook steps follow in order
    assert first[0]["chosen_by"] == "history" and first[1]["chosen_by"] == "runbook"
    fixed_by = next(a for a in first if a["name"] == "Turn the flag off")
    env.rw("incident_resolve", inc="inc-1", by="priya", ts=1000)
    env.rw("action_resolve", inc="inc-1", id=fixed_by["id"])

    env.load_cypher(env.tmp / "repeat.cypher")
    before = bus.history(env.key, "inc-2")
    flow.run("inc-2", ENV, db_path=env.db)
    ev = [e for e in bus.history(env.key, "inc-2", after_seq=before[-1]["seq"] if before else 0)]
    [mem] = [e["data"]["similar"] for e in ev if e["event"] == "memory.similar"]
    assert mem[0]["incident"] == "inc-1" and mem[0]["cause"] == "payment/Charge"  # same signature, same root op
    assert mem[0]["worked"] == {"Turn the flag off": 1}
    actions = env.ro("run_actions", inc="inc-2")
    assert actions[0]["name"] == "Turn the flag off" and actions[0]["chosen_by"] == "history"  # Flow 5
    assert [s["incident"] for s in env.ro("similar_of_run", inc="inc-2")][0] == "inc-1"


def test_signature_is_written_and_identical_for_the_same_fault(env):
    flow.run("inc-1", ENV, db_path=env.db)
    env.load_cypher(env.tmp / "repeat.cypher")
    flow.run("inc-2", ENV, db_path=env.db)
    rows = {i: env.ro("incident_signature", inc=i)[0]["signature"] for i in ("inc-1", "inc-2")}
    assert len(rows["inc-1"]) == 64 and rows["inc-1"] == rows["inc-2"]


def test_no_root_cause_proposes_checking_the_threshold(graph, env):
    env.delete()
    seed_indexes(env)
    env.load_cypher(FIXTURES / "healthy.cypher")
    flow.run("inc-h", ENV, db_path=env.db)
    [a] = env.ro("run_actions", inc="inc-h")
    assert a["name"] == "Check the alert threshold against the baseline"
    [x] = [e for e in env.ro("explanation", inc="inc-h", id="inc-h:r1:X")]
    assert x["source"] == "template" and json.loads(x["claims"])  # explained from the evidence, cited


def test_jev_demotes_actions_that_do_not_address_the_cause(env, monkeypatch):
    from tests.fakes import FakeOpenRouter, use_openrouter

    # GPT-4o has no scripted answer (→ template explanation); Jev judges each remaining action's relevance
    fake = use_openrouter(monkeypatch, FakeOpenRouter(noul={"a0": 0.9, "a1": 0.8, "a2": 0.05}))
    flow.run("inc-1", ENV, db_path=env.db)
    got = [(a["name"], a["chosen_by"], a["p"]) for a in env.ro("run_actions", inc="inc-1")]
    assert got == [
        ("disable flag paymentFailure", "history", None),  # memory first, as before
        ("Check recent flag changes", "runbook", 0.9),
        ("Turn the flag off", "runbook", 0.8),
        ("Restart payment", "demoted", 0.05),  # doesn't address a flag fault: last
    ]
    [req] = [b for b in fake.bodies("/alpha/decisions") if "a0" in b["questions"]]
    assert any("flag paymentFailure" in s for s in req["state"]["evidence"])  # Jev sees why it failed
    assert all(q["type"] == "noul" for q in req["questions"].values())


def test_jev_down_keeps_history_then_runbook_order(env, monkeypatch):
    from tests.fakes import FakeOpenRouter, use_openrouter

    use_openrouter(monkeypatch, FakeOpenRouter(noul=503))
    flow.run("inc-1", ENV, db_path=env.db)
    got = [(a["name"], a["chosen_by"]) for a in env.ro("run_actions", inc="inc-1")]
    assert got == [("disable flag paymentFailure", "history"), ("Check recent flag changes", "runbook"),
                   ("Turn the flag off", "runbook"), ("Restart payment", "runbook")]  # fmt: skip
