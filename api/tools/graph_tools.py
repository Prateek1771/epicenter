"""Typed tools (ADR 0003): the only way agents and MCP clients read the graph. Plain functions with pydantic models in
and out, each bound to one environment (`env`, default ENV_NAME). None of them accepts Cypher; every query is a
catalogue id in graph.py. `mcp_server.py` exposes exactly this `TOOLS` list.
"""

import json
import time
from typing import Literal

from pydantic import BaseModel

from api.config import get_settings
from api.graph import EnvGraph, get_graph
from api.models import local_id
from api.search import score as sc
from api.search import simulate as simulator


def _env(env: str | None) -> EnvGraph:
    name = env or get_settings().env_name
    if name not in get_graph().env_names():
        raise ValueError(f"unknown environment {name!r}")
    return get_graph().env(name)


def _incident(env: EnvGraph, incident: str) -> dict:
    rows = env.ro("incident", inc=incident)
    if not rows:
        raise ValueError(f"unknown incident {incident!r}")
    return rows[0]


# --- models ---


class Caller(BaseModel):
    service: str
    op: str
    hops: int
    team: str | None


class Candidate(BaseModel):
    op: str
    hops: int
    onset: int
    strength: float
    kinds: list[str]


class Path(BaseModel):
    path: list[str]
    onsets: list[int | None]


class Mechanism(BaseModel):
    anomaly: str
    kind: str
    self_ratio: float | None
    child_ratio: float | None
    changes: list[dict]


class EvidenceRef(BaseModel):
    id: str
    kind: str
    verdict: Literal["supports", "refutes"]
    summary: str
    path: list[str]


class WhyNot(BaseModel):
    service: str
    answer: Literal[
        "is_root_cause", "victim", "later_onset", "small_footprint", "lost_on_score", "no_anomaly", "not_upstream"
    ]
    summary: str
    evidence: list[EvidenceRef]


class Change(BaseModel):
    id: str
    type: str
    ts: int
    summary: str
    authors: list[str]


class Changes(BaseModel):
    items: list[Change]


class Similar(BaseModel):
    incident: str
    distance: float
    cause_type: str
    cause: str
    fixes: list[str]


class IncidentSummary(BaseModel):
    incident: str
    status: str
    symptom: str | None
    opened_at: int | None
    causes: list[str]  # current run's root causes, rank 1 first
    fixes: list[str]  # names of the actions that resolved it
    fixed_by: list[str]


class Person(BaseModel):
    handle: str
    name: str | None
    score: int
    via: list[str]  # how they know the service: MEMBER_OF (its owning team), FIXED (an incident there), AUTHORED
    team: str | None  # the service's owning team, so an answer can cite service → team → person


class People(BaseModel):
    items: list[Person]


class Predicted(BaseModel):
    op: str
    kind: str
    p: float
    hops: int
    expected_delay_s: int
    service: str | None
    team: str | None


class WhatIf(BaseModel):
    target: str
    kind: str
    rules_version: str
    predictions: list[Predicted]
    simulation: str | None = None


# --- tools ---


def blast_radius(service: str, env: str | None = None) -> list[Caller]:
    """Every operation that calls into `service` within 6 hops, with its owning team (LLD §2.3)."""
    return [Caller(**r) for r in _env(env).ro("blast_radius", svc=service)]


def upstream_candidates(incident: str, env: str | None = None) -> list[Candidate]:
    """Q1: anomalous operations the incident's symptom depends on (its root-cause candidates)."""
    e = _env(env)
    return [Candidate(**r) for r in e.ro("Q1", symptom=_incident(e, incident)["symptom"], inc=incident)]


def propagation_path(incident: str, operation: str, env: str | None = None) -> list[Path]:
    """Q2: call paths from the symptom to `operation` with the onset of each hop."""
    e = _env(env)
    rows = e.ro("Q2", symptom=_incident(e, incident)["symptom"], cand=operation, inc=incident)
    return [Path(**r) for r in rows]


def mechanism(incident: str, operation: str, env: str | None = None) -> list[Mechanism]:
    """Q3: self vs child time of `operation`'s anomalies and changes on its service shortly before."""
    w = sc.load_weights(get_settings().weights_path)
    rows = _env(env).ro("Q3", cand=operation, inc=incident, lookback_s=w["lookback_s"])
    return [Mechanism(**r) for r in rows]


def why_not(incident: str, service: str, env: str | None = None) -> WhyNot:
    """Why isn't `service` the root cause of `incident`? Answers from the current diagnosis run's evidence."""
    e = _env(env)
    _incident(e, incident)
    hyps = e.ro("service_hypotheses", inc=incident, svc=service)
    if not hyps:
        anomalous = e.ro("service_anomalies", inc=incident, svc=service)[0]["n"]
        if anomalous:
            return WhyNot(
                service=service,
                answer="not_upstream",
                summary=f"{service} has anomalies, but none of them is upstream of the alerting operation",
                evidence=[],
            )
        return WhyNot(
            service=service, answer="no_anomaly", summary=f"{service} showed no anomaly in this incident", evidence=[]
        )
    h = max(hyps, key=lambda x: (x["status"] == "confirmed", x["score"] or -9, x["id"]))
    ev = [
        EvidenceRef(
            id=local_id(x["id"]),
            kind=x["kind"],
            verdict="supports" if x["rel"] == "SUPPORTED_BY" else "refutes",
            summary=x["summary"],
            path=x["path"] or [],
        )
        for x in h["evidence"]
    ]
    refutes = [x for x in ev if x.verdict == "refutes"]
    if h["status"] == "confirmed":
        return WhyNot(service=service, answer="is_root_cause", summary=f"{h['op']} is the root cause", evidence=ev)
    for kind, answer in (("victim", "victim"), ("propagation", "later_onset"), ("footprint", "small_footprint")):
        hit = next((x for x in refutes if x.kind == kind), None)
        if hit:
            return WhyNot(service=service, answer=answer, summary=hit.summary, evidence=refutes)
    facts = json.loads(h["facts"] or "{}")
    winner = e.ro("root_causes", inc=incident)
    win_cov = (
        json.loads(e.ro("hypothesis", id=winner[0]["hypothesis"])[0]["facts"] or "{}").get("coverage", 0.0)
        if winner
        else 0.0
    )
    if facts.get("coverage", 0.0) < win_cov:
        return WhyNot(
            service=service,
            answer="small_footprint",
            summary=f"{h['op']} explains {facts.get('coverage', 0):.0%} of the symptoms, the root cause {win_cov:.0%}",
            evidence=ev,
        )
    return WhyNot(
        service=service,
        answer="lost_on_score",
        summary=f"{h['op']} was consistent with the evidence but scored {h['score'] or 0:.2f} and lost on score",
        evidence=ev,
    )


def recent_changes(service: str, minutes: int = 60, until: int | None = None, env: str | None = None) -> list[Change]:
    """Changes on `service` in the `minutes` before `until` (default now), with their authors."""
    since = (until or int(time.time())) - minutes * 60
    return [Change(**r) for r in _env(env).ro("recent_changes", svc=service, since=since)]


def similar_incidents(incident: str, env: str | None = None) -> list[Similar]:
    """Q5: resolved incidents with a similar signature, their root cause and fixes. Empty until the incident has a
    signature (historian, phase 7)."""
    e = _env(env)
    sig = e.ro("incident_signature", inc=incident)
    if not sig or sig[0]["signature"] is None:
        return []
    rows = e.ro("Q5", sig=sig[0]["signature"], inc=incident)
    return [Similar(distance=r.pop("score"), **r) for r in rows]


def incident_summary(incident: str, env: str | None = None) -> IncidentSummary:
    """One incident's status, root cause(s), the actions that fixed it and who fixed it."""
    e = _env(env)
    _incident(e, incident)
    [row] = e.ro("incident_summary", inc=incident)
    return IncidentSummary(**row)


def who_knows(service: str, env: str | None = None) -> list[Person]:
    """People who know `service`: owners, who fixed incidents rooted there, who changed it."""
    return [Person(**r | {"via": sorted(r["via"])}) for r in _env(env).ro("who_knows", svc=service)]


def simulate(target: str, kind: str, env: str | None = None) -> WhatIf:
    """What breaks if `target` (an operation `svc/op`, or a service) fails with `kind`? Fault Simulator, no incident."""
    name = env or get_settings().env_name
    _env(name)
    return WhatIf(**simulator.what_if(get_graph(), name, target, kind))


TOOLS = [
    blast_radius,
    upstream_candidates,
    propagation_path,
    mechanism,
    why_not,
    recent_changes,
    similar_incidents,
    incident_summary,
    who_knows,
    simulate,
]
