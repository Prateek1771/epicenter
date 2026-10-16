"""Graph views (API.md "Graph views"): subgraph for the canvas, blast radius, what-if simulation."""

from typing import Annotated

from fastapi import APIRouter, Query, Request

from api.models import Affected, BlastRadius, GraphEdge, GraphNode, SimulatedOp, SimulateIn, SimulateOut, Subgraph
from api.routes.deps import ApiError, Env, env_name, incident_or_404
from api.search import simulate as simulator
from api.tools import graph_tools

router = APIRouter()


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
    return BlastRadius(
        service=service,
        affected=[Affected(service=c.service, operation=c.op, hops=c.hops, owner=c.team) for c in callers],
        counts={"services": len({c.service for c in callers}), "operations": len(callers)},
        past_incidents=[r["id"] for r in env.ro("service_past_incidents", svc=service)],
    )


@router.post("/simulate", response_model=SimulateOut)
def simulate(body: SimulateIn, env: Env, request: Request) -> SimulateOut:
    target = body.operation or body.service
    exists = env.ro("service_exists", svc=target) if body.service else env.ro("service_ops", svc=target.split("/")[0])
    if not exists:
        raise ApiError(404, "SERVICE_NOT_FOUND", f"No service or operation {target!r}")
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
    )
