"""Graph views (API.md "Graph views"): subgraph for the canvas, service map, blast radius, what-if simulation."""

import json
import time
from typing import Annotated, Literal

from fastapi import APIRouter, Query, Request

from api.models import (
    Affected,
    BlastRadius,
    Explore,
    GraphCall,
    GraphEdge,
    GraphNode,
    RuleOut,
    Rules,
    RunbookOut,
    Runbooks,
    ServiceItem,
    ServiceRisk,
    Services,
    ServicesRisk,
    SimCompare,
    SimCompareOut,
    SimulatedOp,
    SimulateIn,
    SimulateOut,
    SimulationItem,
    Simulations,
    Subgraph,
    Topology,
    TopologyEdge,
    TopologyNode,
)
from api.routes.deps import ApiError, Env, env_name, incident_or_404
from api.search import simulate as simulator
from api.tools import graph_tools

router = APIRouter()
MAP_LIMIT = 2000


@router.get("/graph/subgraph", response_model=Subgraph, response_model_by_alias=True)
def subgraph(
    env: Env,
    center: Annotated[str, Query(description="an operation id (`svc/op`) or a service name")],
    hops: Annotated[int, Query(ge=1, le=3)] = 2,
    incident: str | None = None,
) -> Subgraph:
    starts = [center] if "/" in center else [r["op"] for r in env.ro("service_ops", svc=center)]
    rows = env.ro("subgraph", starts=starts, hops=hops) if starts else []
    if not rows:
        raise ApiError(404, "SERVICE_NOT_FOUND", f"No operation or service {center!r}")
    nodes = [GraphNode(id=r["id"], label="Operation", props={"service": r["service"],
             "service_kind": r["service_kind"]}) for r in rows]  # fmt: skip
    edges = [
        GraphEdge(from_=r["id"], to=c["to"], type="CALLS", props={k: c[k] for k in ("rps", "p95_ms", "err_rate")})
        for r in rows
        for c in r["calls"]
    ]
    if incident:
        incident_or_404(env, incident)
        ops = [r["id"] for r in rows]
        for a in env.ro("subgraph_anomalies", inc=incident, ops=ops):
            nodes.append(GraphNode(id=a["id"], label="Anomaly", props={k: a[k] for k in ("kind", "onset", "score")}))
            edges.append(GraphEdge(from_=a["id"], to=a["op"], type="ON", props={}))
        for h in env.ro("subgraph_hypotheses", inc=incident, ops=ops):
            nodes.append(GraphNode(id=h["id"], label="Hypothesis", props={"status": h["status"], "score": h["score"]}))
            edges.append(GraphEdge(from_=h["id"], to=h["op"], type="BLAMES", props={}))
    return Subgraph(nodes=nodes, edges=edges)


@router.get("/blast-radius/{service}", response_model=BlastRadius)
def blast_radius(service: str, env: Env) -> BlastRadius:
    if not env.ro("service_exists", svc=service):
        raise ApiError(404, "SERVICE_NOT_FOUND", f"No service {service!r}")
    callers = graph_tools.blast_radius(service, env=env_name(env))
    sources = [r["op"] for r in env.ro("service_ops", svc=service)]
    ops = sorted(set(sources) | {c.op for c in callers})
    return BlastRadius(
        service=service,
        affected=[Affected(service=c.service, operation=c.op, hops=c.hops, owner=c.team) for c in callers],
        counts={"services": len({c.service for c in callers}), "operations": len(callers)},
        past_incidents=[r["id"] for r in env.ro("service_past_incidents", svc=service)],
        sources=sources,
        edges=[GraphCall(**e) for e in env.ro("graph_edges", ops=ops)],
    )


@router.post("/simulate", response_model=SimulateOut)
def simulate(body: SimulateIn, env: Env, request: Request) -> SimulateOut:
    target = _sim_target(body, env)
    out = simulator.what_if(request.app.state.graph, env_name(env), target, body.kind, save=body.save)
    preds = [
        SimulatedOp(
            op=p["op"],
            service=p["service"],
            kind=p["kind"],
            p=p["p"],
            hops=p["hops"],
            expected_delay_s=p["expected_delay_s"],
            owner=p["team"],
        )
        for p in out["predictions"]
    ]
    return SimulateOut(
        simulation_id=out.get("simulation"),
        target=target,
        kind=body.kind,
        rules_version=out["rules_version"],
        predicted=preds,
        counts={"services": len({p.service for p in preds}), "operations": len({p.op for p in preds})},
        edges=[GraphCall(**e) for e in env.ro("graph_edges", ops=sorted({p.op for p in preds}))] if preds else [],
    )


def _sim_target(body: SimulateIn, env) -> str:
    target = body.operation or body.service
    exists = env.ro("service_exists", svc=target) if body.service else env.ro("service_ops", svc=target.split("/")[0])
    if not exists:
        raise ApiError(404, "SERVICE_NOT_FOUND", f"No service or operation {target!r}")
    return target


@router.post("/simulate/compare", response_model=SimCompareOut)
def simulate_compare(body: SimulateIn, env: Env, request: Request) -> SimCompareOut:
    """The what-if prediction vs every past incident rooted at the target's service: would it have explained it?"""
    target = _sim_target(body, env)
    rows = simulator.compare(request.app.state.graph, env_name(env), target, body.kind)
    return SimCompareOut(target=target, kind=body.kind, items=[SimCompare(**r) for r in rows])


@router.get("/simulations", response_model=Simulations)
def simulations(env: Env, limit: Annotated[int, Query(ge=1, le=50)] = 20) -> Simulations:
    return Simulations(items=[SimulationItem(**r) for r in env.ro("simulations_recent", limit=limit)])


@router.get("/rules", response_model=Rules)
def rules(request: Request) -> Rules:
    """The propagation rules the simulator uses (kb:propagation, read-only)."""
    return Rules(items=[RuleOut(**r) for r in request.app.state.graph.kb().ro("rules")])


@router.get("/graph/explore", response_model=Explore, response_model_by_alias=True)
def explore(env: Env, limit: Annotated[int, Query(ge=10, le=MAP_LIMIT)] = 300) -> Explore:
    """Everything in the env graph, bounded: the /map Network view. Node ids are `Label:key` (keys repeat across
    labels: a Service and its Team can share a name)."""
    counts = {r["label"]: r["n"] for r in env.ro("explore_counts")}
    rows = env.ro("explore_nodes", limit=limit)
    keys = sorted({r["key"] for r in rows})
    ids = {f"{r['label']}:{r['key']}" for r in rows}
    nodes = [
        GraphNode(
            id=f"{r['label']}:{r['key']}",
            label=r["label"],
            props={k: v for k, v in r.items() if k not in ("label",) and v is not None},
        )
        for r in rows
    ]
    edges = [
        GraphEdge(
            from_=f"{e['a_label']}:{e['a']}",
            to=f"{e['b_label']}:{e['b']}",
            type=e["type"],
            props={k: e[k] for k in ("rps", "err_rate") if e[k] is not None},
        )
        for e in env.ro("explore_edges", keys=keys, limit=limit * 4)
        if f"{e['a_label']}:{e['a']}" in ids and f"{e['b_label']}:{e['b']}" in ids
    ]
    return Explore(nodes=nodes, edges=edges, label_counts=counts, truncated=sum(counts.values()) > len(nodes))


@router.get("/graph/topology", response_model=Topology)
def topology(
    env: Env,
    level: Literal["service", "operation"] = "service",
    hours: Annotated[int, Query(ge=1, le=168, description="halos / crowns from unresolved incidents this recent")] = 24,
) -> Topology:
    """The service map (/map): services or operations with their calls, plus anomalies and root causes of recent
    unresolved incidents. Capped at MAP_LIMIT nodes and edges; `truncated` says when the cap was hit."""
    since = int(time.time()) - hours * 3600
    svcs = env.ro("topology_services", limit=MAP_LIMIT)
    owner = {s["id"]: s["owner"] for s in svcs}
    anomalies: dict[str, list[dict]] = {}
    for a in env.ro("map_anomalies", since=since):
        anomalies.setdefault(a["op"], []).append({k: a[k] for k in ("incident", "kind", "score")})
    crowns: dict[str, list[str]] = {}
    for c in env.ro("map_root_causes", since=since):
        crowns.setdefault(c["op"], []).append(c["incident"])
    if level == "service":
        ops = env.ro("topology_ops", limit=MAP_LIMIT * 10)  # anomalies are per operation: fold them per service
        svc_of = {o["id"]: o["service"] for o in ops}
        s_anom: dict[str, list[dict]] = {}
        s_crown: dict[str, list[str]] = {}
        for op, xs in sorted(anomalies.items()):
            s_anom.setdefault(svc_of.get(op, op.split("/")[0]), []).extend(xs)
        for op, xs in sorted(crowns.items()):
            s_crown.setdefault(svc_of.get(op, op.split("/")[0]), []).extend(xs)
        nodes = [TopologyNode(id=s["id"], service=s["id"], kind=s["kind"], owner=s["owner"], ops=s["ops"],
                              anomalies=s_anom.get(s["id"], []), root_cause_of=sorted(set(s_crown.get(s["id"], []))))
                 for s in svcs]  # fmt: skip
        edges = env.ro("topology_service_calls", limit=MAP_LIMIT)
    else:
        ops = env.ro("topology_ops", limit=MAP_LIMIT)
        nodes = [TopologyNode(id=o["id"], service=o["service"], kind=o["kind"], owner=owner.get(o["service"]),
                              anomalies=anomalies.get(o["id"], []), root_cause_of=crowns.get(o["id"], []))
                 for o in ops]  # fmt: skip
        ids = {o["id"] for o in ops}
        edges = [e for e in env.ro("topology_op_calls", limit=MAP_LIMIT * 2) if e["src"] in ids and e["dst"] in ids]
    return Topology(
        level=level,
        nodes=nodes,
        edges=[TopologyEdge(**e) for e in edges],
        truncated=len(nodes) >= MAP_LIMIT or len(edges) >= MAP_LIMIT,
    )


@router.get("/services/{service}/changes", response_model=graph_tools.Changes)
def service_changes(env: Env, service: str, hours: Annotated[int, Query(ge=1, le=168)] = 24) -> graph_tools.Changes:
    """Changes on one service in the last `hours`, newest first (the /map side panel). Bounded by time, so no cursor."""
    return graph_tools.Changes(items=graph_tools.recent_changes(service, minutes=hours * 60, env=env_name(env)))


@router.get("/services/risk", response_model=ServicesRisk)
def services_risk(env: Env, limit: Annotated[int, Query(ge=1, le=50)] = 12) -> ServicesRisk:
    """The riskiest services: most incidents rooted there, then most calling services (the /blast-radius start)."""
    return ServicesRisk(items=[ServiceRisk(**r) for r in env.ro("services_risk", limit=limit)])


@router.get("/services/{service}/people", response_model=graph_tools.People)
def service_people(env: Env, service: str) -> graph_tools.People:
    """Who to pull in: the owning team's members, who fixed incidents rooted here, who changed it (who_knows)."""
    if not env.ro("service_exists", svc=service):
        raise ApiError(404, "SERVICE_NOT_FOUND", f"No service {service!r}")
    return graph_tools.People(items=graph_tools.who_knows(service, env=env_name(env)))


@router.get("/services/{service}/runbooks", response_model=Runbooks)
def service_runbooks(env: Env, service: str) -> Runbooks:
    rows = env.ro("service_runbooks", svc=service)
    return Runbooks(
        items=[
            RunbookOut(id=r["id"], kind=r["kind"], steps=r["steps"] or [], success=json.loads(r["success"] or "{}"))
            for r in rows
        ]
    )


@router.get("/services", response_model=Services)
def services(env: Env) -> Services:
    """Every service in the env with its kind and operation count, for pickers (blast radius, what-if, why-not)."""
    return Services(items=[ServiceItem(**r) for r in env.ro("services")])
