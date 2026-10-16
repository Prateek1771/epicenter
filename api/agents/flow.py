"""LangGraph wiring for one diagnosis run (LLD §5.2).

    python -m api.agents.flow --env rcaeval-tt --incident rc-<case> [--resume]

triage → investigator × N (Send, parallel) → scorer ⇄ skeptic (≤ 2 challenges) → decide → [round 2: investigator2 × M
→ scorer2] → finalize → historian → narrator → jev_gate → responder. State holds ids, flags and counters only
(ADR 0007); every step rebuilds what it needs from the graph, which is why any process can resume a run.

ponytail: the checkpointer is SQLite on local disk, one API process. With more replicas use LangGraph's Postgres or
Redis checkpointer, same interface.
"""

import argparse
import json
import logging
import operator
import sqlite3
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Annotated, TypedDict

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from api.agents import historian, investigator, narrator, responder, skeptic, triage
from api.config import get_settings
from api.events import publish
from api.models import local_id
from api.search import causal
from api.tools.graph_tools import get_graph

log = logging.getLogger("epicenter.agents")
MAX_SKEPTIC_ROUNDS = 2


class IncidentState(TypedDict, total=False):
    incident_id: str
    env: str
    symptom: str
    alert_ts: int
    run: int
    weights_path: str | None
    hypothesis_ids: list[str]  # set by triage
    round2_ids: list[str]  # second-cause round (§7.5)
    verdict_id: str | None  # provisional winner, then the committed root cause
    second_cause_id: str | None
    no_root_cause: bool  # typed negative answer (§7.6)
    skeptic_rounds: int
    skeptic_refuted: bool
    explanation_id: str | None
    action_ids: list[str]
    errors: Annotated[list[str], operator.add]


def _run(state: dict) -> causal.Run:
    return causal.open_run(get_graph(), state["env"], state["incident_id"], state.get("weights_path"))


def _node(agent: str, fn: Callable[[dict], dict]) -> Callable[[dict], dict]:
    """Structured log per step (HLD §10). Exceptions propagate, so the checkpoint keeps the run resumable."""

    def wrapped(state: dict) -> dict:
        t0 = time.perf_counter()
        try:
            return fn(state)
        finally:
            ms = round((time.perf_counter() - t0) * 1000, 1)
            log.info(json.dumps({"incident_id": state.get("incident_id"), "agent": agent, "duration_ms": ms}))

    return wrapped


def n_triage(state: dict) -> dict:
    return triage.triage(state, _run(state))


def fan_out(key: str, node: str) -> Callable[[dict], list[Send]]:
    def route(state: dict) -> list[Send] | str:
        ids = state.get(key) or []
        if not ids:
            return "scorer" if node == "investigator" else "finalize"
        base = {k: state[k] for k in ("incident_id", "env")} | {"weights_path": state.get("weights_path")}
        return [Send(node, base | {"hypothesis_id": h}) for h in ids]

    return route


def n_investigator(task: dict) -> dict:
    return investigator.investigate(_run(task), task["hypothesis_id"])


def n_scorer(state: dict) -> dict:
    r = _run(state)
    ordered = causal.score_round(r, 1)
    for h in ordered:
        publish(r.incident, "hypothesis.status", {"id": local_id(h["id"]), "status": h["status"], "score": h["score"]})
    top = causal.pick(ordered)
    return {"verdict_id": top["id"] if top else None}


def after_scorer(state: dict) -> str:
    if state.get("verdict_id") is None or state.get("skeptic_rounds", 0) >= MAX_SKEPTIC_ROUNDS:
        return "decide"
    return "skeptic"


def n_skeptic(state: dict) -> dict:
    refuted = skeptic.challenge(_run(state), state["verdict_id"])
    return {"skeptic_rounds": state.get("skeptic_rounds", 0) + 1, "skeptic_refuted": refuted}


def after_skeptic(state: dict) -> str:
    return "scorer" if state.get("skeptic_refuted") else "decide"


def n_decide(state: dict) -> dict:
    r = _run(state)
    d = causal.decide(r, causal.score_round(r, 1))
    out = {"no_root_cause": d["no_root_cause"], "verdict_id": d["winner"]["id"] if d["winner"] else None}
    if d.get("second_seed"):
        winner_op = d["winner"]["op"]
        round2 = causal.triage(r, 2, d["second_seed"], d["second_scope"], exclude=winner_op)
        for h in round2:
            publish(
                r.incident,
                "hypothesis.created",
                {"id": local_id(h["id"]), "target": h["op"], "hops": h["hops"], "onset": h["onset"], "round": 2},
            )
        out["round2_ids"] = [h["id"] for h in round2]
    return out


def n_scorer2(state: dict) -> dict:
    r = _run(state)
    [w] = r.env.ro("hypothesis", id=state["verdict_id"])
    second = causal.pick_second(r, {"op": w["op"]}, causal.score_round(r, 2))
    return {"second_cause_id": second["id"] if second else None}


def n_finalize(state: dict) -> dict:
    r = _run(state)
    for hid in causal.finalize(r):
        publish(r.incident, "hypothesis.status", {"id": local_id(hid), "status": "pruned"})
    v = causal.read_verdict(r)
    if v["status"] == "no_root_cause":
        checked = [h["id"] for h in v["ranking"]]
        best = max((h["coverage"] for h in v["ranking"]), default=0.0)
        publish(r.incident, "no_root_cause", {"summary": v["summary"], "checked": checked, "max_coverage": best})
    else:
        publish(r.incident, "verdict", v)
    publish(r.incident, "incident.status", {"status": v["status"], "run": r.run})
    return {}


def build(checkpointer=None):
    g = StateGraph(IncidentState)
    g.add_node("triage", _node("triage", n_triage))
    g.add_node("investigator", _node("investigator", n_investigator))
    g.add_node("scorer", _node("scorer", n_scorer))
    g.add_node("skeptic", _node("skeptic", n_skeptic))
    g.add_node("decide", _node("decide", n_decide))
    g.add_node("investigator2", _node("investigator", n_investigator))
    g.add_node("scorer2", _node("scorer", n_scorer2))
    g.add_node("finalize", _node("finalize", n_finalize))
    g.add_node("historian", _node("historian", historian.remember))
    g.add_node("narrator", _node("narrator", narrator.narrate))
    g.add_node("jev_gate", _node("jev_gate", narrator.jev_gate))
    g.add_node("responder", _node("responder", responder.respond))
    g.add_edge(START, "triage")
    g.add_conditional_edges("triage", fan_out("hypothesis_ids", "investigator"), ["investigator", "scorer"])
    g.add_edge("investigator", "scorer")
    g.add_conditional_edges("scorer", after_scorer, ["skeptic", "decide"])
    g.add_conditional_edges("skeptic", after_skeptic, ["scorer", "decide"])
    g.add_conditional_edges("decide", fan_out("round2_ids", "investigator2"), ["investigator2", "finalize"])
    g.add_edge("investigator2", "scorer2")
    g.add_edge("scorer2", "finalize")
    for a, b in (("finalize", "historian"), ("historian", "narrator"), ("narrator", "jev_gate")):
        g.add_edge(a, b)
    g.add_edge("jev_gate", "responder")
    g.add_edge("responder", END)
    return g.compile(checkpointer=checkpointer)


def _checkpointer(db_path: str | None) -> SqliteSaver:
    path = Path(db_path or get_settings().checkpoint_db)
    path.parent.mkdir(parents=True, exist_ok=True)
    return SqliteSaver(sqlite3.connect(str(path), check_same_thread=False))


def _thread(incident_id: str, run: int) -> dict:
    return {"configurable": {"thread_id": f"{incident_id}:r{run}"}}


def run(incident_id: str, env: str | None = None, weights_path: str | None = None, db_path: str | None = None) -> dict:
    """Start a new, kept diagnosis run of `incident_id` through the agent flow and return its verdict."""
    env = env or get_settings().env_name
    r = causal.start_run(get_graph(), env, incident_id, weights_path)
    state = {
        "incident_id": incident_id,
        "env": env,
        "symptom": r.symptom,
        "run": r.run,
        "weights_path": weights_path,
        "skeptic_rounds": 0,
        "errors": [],
        "action_ids": [],
    }
    build(_checkpointer(db_path)).invoke(state, _thread(incident_id, r.run))
    return causal.read_verdict(causal.open_run(get_graph(), env, incident_id, weights_path))


def resume(
    incident_id: str, env: str | None = None, weights_path: str | None = None, db_path: str | None = None
) -> dict:
    """Continue the incident's current run from its last checkpoint (after a crash). Finished steps are not redone;
    a step that was cut off re-runs and MERGEs onto what it already wrote."""
    env = env or get_settings().env_name
    r = causal.open_run(get_graph(), env, incident_id, weights_path)
    app = build(_checkpointer(db_path))
    cfg = _thread(incident_id, r.run)
    if app.get_state(cfg).next:
        app.invoke(None, cfg)
    return causal.read_verdict(causal.open_run(get_graph(), env, incident_id, weights_path))


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Diagnose an incident through the agent flow")
    p.add_argument("--env")
    p.add_argument("--incident", required=True)
    p.add_argument("--weights")
    p.add_argument("--resume", action="store_true", help="continue the current run from its checkpoint")
    p.add_argument("--top", type=int, default=10)
    a = p.parse_args(argv)
    v = (resume if a.resume else run)(a.incident, a.env, a.weights)
    v["ranking"] = v["ranking"][: a.top]
    print(json.dumps(v, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
