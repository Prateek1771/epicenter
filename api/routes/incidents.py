"""Incident endpoints (API.md "Alerts and incidents") and the SSE stream (LLD §9)."""

import asyncio
import json
import time
from typing import Annotated, Literal

from fastapi import APIRouter, BackgroundTasks, Header, Query, Request
from fastapi.responses import PlainTextResponse, StreamingResponse

from api.config import get_settings
from api.deliver.report import incident_markdown
from api.events import bus
from api.graph import EnvGraph
from api.models import (
    Accepted,
    ActionOut,
    ChangeRef,
    EvidenceOut,
    ExplanationOut,
    FootprintOut,
    FootprintSummary,
    GraphCall,
    GraphChange,
    GraphEvidence,
    GraphHypothesis,
    GraphOp,
    HypothesisOut,
    HypothesisRef,
    IncidentGraph,
    IncidentOut,
    IncidentPage,
    IncidentStatus,
    IncidentSummary,
    NoRootCause,
    NoteIn,
    NoteOut,
    Prediction,
    ResolveIn,
    ResolveOut,
    SimilarOut,
    Verdict,
    local_id,
    scoped_id,
)
from api.routes.deps import ApiError, Env, decode_cursor, encode_cursor, env_name, epoch, incident_or_404, iso
from api.search import causal
from api.search.score import load_weights
from api.tools import graph_tools

router = APIRouter()

RESOLVABLE = {"diagnosed", "delivered", "no_root_cause"}  # LLD §8
TAIL_BLOCK_MS = 2000  # one blocking read per subscriber; under the 5 s socket timeout


@router.get("/incidents", response_model=IncidentPage)
def list_incidents(
    env: Env,
    status: IncidentStatus | None = None,
    cause: Annotated[str | None, Query(description="service name of the root cause")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    cursor: str | None = None,
) -> IncidentPage:
    c_ts, c_id = decode_cursor(cursor) if cursor else (None, None)
    rows = env.ro("incidents_page", status=status, cause=cause, c_ts=c_ts, c_id=c_id, limit=limit + 1)
    page = rows[:limit]
    items = [IncidentSummary(**(r | {"opened_at": iso(r["opened_at"])})) for r in page]
    more = len(rows) > limit
    return IncidentPage(items=items, next_cursor=encode_cursor(page[-1]["opened_at"], page[-1]["id"]) if more else None)


def _hypothesis(env: EnvGraph, hyp_id: str) -> HypothesisOut:
    [h] = env.ro("hypothesis", id=hyp_id)
    return HypothesisOut(
        id=local_id(h["id"]),
        target=h["op"],
        target_type="Operation",
        status=h["status"],
        score=h["score"],
        hops=h["hops"],
        onset=iso(h["onset"]),
        score_parts=json.loads(h["score_parts"] or "{}"),
    )


def _evidence(env: EnvGraph, hyp_id: str) -> list[dict]:
    return env.ro("hypothesis_evidence", id=hyp_id)


def _verdict(env: EnvGraph, incident_id: str, ranking: list[dict]) -> Verdict | None:
    causes = {c["rank"]: c for c in env.ro("root_causes", inc=incident_id)}
    if 1 not in causes:
        return None
    top = causes[1]["hypothesis"]
    ev = _evidence(env, top)
    fp = next((json.loads(e["value"]) for e in ev if e["kind"] == "footprint" and e["value"]), None)
    path = next((e["path"] for e in ev if e["kind"] == "propagation" and e["rel"] == "SUPPORTED_BY"), None)
    runner = next((h for h in ranking if h["id"] != local_id(top) and h["status"] != "refuted"), None)
    owners = env.ro("op_owners", ops=[causes[1]["op"]])
    ch = next((json.loads(e["value"]) for e in ev
               if e["kind"] == "change" and e["rel"] == "SUPPORTED_BY" and e["value"]), None)  # fmt: skip
    change = env.ro("change_by_id", id=ch["change"]) if ch else []
    timing = env.ro("incident_timing", inc=incident_id)
    return Verdict(
        root_cause=_hypothesis(env, top),
        confidence=causes[1]["confidence"],
        owner=owners[0]["team"] if owners else None,
        change=ChangeRef(**(change[0] | {"ts": iso(change[0]["ts"])})) if change else None,
        found_in_ms=timing[0]["found_in_ms"] if timing else None,
        footprint=FootprintSummary(
            coverage=fp["coverage"],
            precision=fp["precision"],
            order=fp["order"],
            summary=fp["explains"],
            unexplained=fp["unexplained"],
        )
        if fp
        else None,
        second_root_cause=_hypothesis(env, causes[2]["hypothesis"]) if 2 in causes else None,
        runner_up=HypothesisRef(id=runner["id"], target=runner["op"], status=runner["status"], score=runner["score"])
        if runner
        else None,
        path=path or [causes[1]["op"]],
        evidence=[
            EvidenceOut(
                id=local_id(e["id"]),
                kind=e["kind"],
                verdict="supports" if e["rel"] == "SUPPORTED_BY" else "refutes",
                summary=e["summary"],
                path=e["path"] or [],
                ref=e["ref"],
            )
            for e in ev
        ],
    )


@router.get("/incidents/{incident_id}", response_model=IncidentOut)
def get_incident(incident_id: str, env: Env, request: Request) -> IncidentOut:
    inc = incident_or_404(env, incident_id)
    out = IncidentOut(
        id=incident_id,
        env=env_name(env),
        status=inc["status"],
        symptom=inc["symptom"],
        alert_count=inc["alert_count"],
        gaps=inc["gaps"] or [],
        weights_version=inc["weights_version"],
        run=inc["run"],
        verdict=None,
        hypotheses=[],
    )
    if inc["run"] is None:
        return out
    v = causal.read_verdict(causal.open_run(request.app.state.graph, env_name(env), incident_id))
    rows = env.ro("run_hypotheses", inc=incident_id, run=inc["run"])
    out.hypotheses = [HypothesisRef(id=local_id(h["id"]), target=h["op"], status=h["status"], score=h["score"])
                      for h in rows]  # fmt: skip
    out.verdict = _verdict(env, incident_id, v["ranking"])
    if inc["status"] == "no_root_cause":
        out.no_root_cause = NoRootCause(
            summary=inc["summary"] or "Nothing in the graph explains this alert",
            checked=[h["id"] for h in v["ranking"]],
            max_coverage=max((h["coverage"] for h in v["ranking"]), default=0.0),
        )
    x = env.ro("explanation", inc=incident_id, id=scoped_id(incident_id, f"r{inc['run']}:X"))
    if x:
        out.explanation = ExplanationOut(
            claims=json.loads(x[0]["claims"]),
            dropped=x[0]["dropped"],
            verified=x[0]["verified"],
            source=x[0]["source"],
            ai_calls=json.loads(x[0]["ai_calls"] or "[]"),
        )
    out.similar = [SimilarOut(**{k: s[k] for k in ("incident", "score", "cause", "fixes")})
                   for s in env.ro("similar_of_run", inc=incident_id)]  # fmt: skip
    acts = env.ro("run_actions", inc=incident_id)
    precedent = {x["name"]: [i for i in x["incidents"] if i != incident_id]
                 for x in env.ro("fix_incidents", names=sorted({a["name"] for a in acts}))} if acts else {}  # fmt: skip
    out.actions = [ActionOut(**(a | {"id": local_id(a["id"]), "precedent": precedent.get(a["name"], [])}))
                   for a in acts]  # fmt: skip
    out.delivery = json.loads(inc["delivery"]) if inc["delivery"] else None
    return out


@router.get("/incidents/{incident_id}/export.md", response_class=PlainTextResponse)
def export_markdown(
    incident_id: str, env: Env, request: Request, flavor: Annotated[Literal["human", "agent"], Query()] = "human"
) -> PlainTextResponse:
    """The incident as Markdown: `human` (incident_info.md) or `agent` (a context file for coding agents)."""
    md = incident_markdown(get_incident(incident_id, env, request), flavor)
    name = f"{incident_id}.agent.md" if flavor == "agent" else f"{incident_id}.incident_info.md"
    return PlainTextResponse(md, media_type="text/markdown; charset=utf-8",
                             headers={"Content-Disposition": f'attachment; filename="{name}"'})  # fmt: skip


@router.get("/incidents/{incident_id}/graph", response_model=IncidentGraph)
def incident_graph(incident_id: str, env: Env) -> IncidentGraph:
    """The canvas in one load: hypotheses with their evidence, the operations on every evidence path, the calls among
    them. Bounded by the run (≤ 50 hypotheses, paths ≤ 6 hops)."""
    last_seq = bus.last_seq(env.key, incident_id)  # read first: an event racing this read is replayed, not lost
    inc = incident_or_404(env, incident_id)
    hyps = env.ro("run_evidence_paths", inc=incident_id) if inc["run"] is not None else []
    causes = {c["rank"]: c["op"] for c in env.ro("root_causes", inc=incident_id)}
    ops = {h["op"] for h in hyps} | {op for h in hyps for e in h["evidence"] for op in (e["path"] or [])}
    if inc["symptom"]:
        ops.add(inc["symptom"])
    ops = sorted(ops)
    nodes = [GraphOp(**n) for n in env.ro("graph_nodes", ops=ops, inc=incident_id)] if ops else []
    t = inc["opened_at"]
    changes = []
    if t is not None and nodes:
        since = t - load_weights(get_settings().weights_path)["lookback_s"]
        until = t + get_settings().window_after_s
        changes = env.ro("incident_changes", svcs=sorted({n.service for n in nodes}), since=since, until=until)
    return IncidentGraph(
        incident=incident_id,
        run=inc["run"],
        status=inc["status"],
        symptom=inc["symptom"],
        root_cause=causes.get(1),
        second_cause=causes.get(2),
        last_seq=last_seq,
        hypotheses=[
            GraphHypothesis(
                id=local_id(h["id"]),
                op=h["op"],
                status=h["status"],
                score=h["score"],
                hops=h["hops"],
                round=h["round"] or 1,
                evidence=[
                    GraphEvidence(
                        id=local_id(e["id"]),
                        kind=e["kind"],
                        verdict="supports" if e["rel"] == "SUPPORTED_BY" else "refutes",
                        summary=e["summary"],
                        path=e["path"] or [],
                    )
                    for e in h["evidence"]
                ],
            )
            for h in hyps
        ],
        nodes=nodes,
        edges=[GraphCall(**c) for c in env.ro("graph_edges", ops=ops)] if ops else [],
        alert_ts=t,
        changes=[GraphChange(**c) for c in changes],
        receipts=_receipts(env, incident_id, inc["run"]),
    )


def _receipts(env: EnvGraph, incident_id: str, run: int | None) -> dict | None:
    row = env.ro("incident_timing", inc=incident_id)
    rc = json.loads(row[0]["receipts"]) if row and row[0]["receipts"] else None
    return rc if rc and rc.get("run") == run else None


@router.post("/incidents/{incident_id}/diagnose", status_code=202, response_model=Accepted)
def diagnose(
    incident_id: str, env: Env, request: Request, background: BackgroundTasks, force: bool = False
) -> Accepted:
    inc = incident_or_404(env, incident_id)
    runner = request.app.state.diagnosis
    if runner.running(env_name(env), incident_id):
        return Accepted(incident_id=incident_id, status="diagnosing")
    if inc["status"] not in ("open", "diagnosing") and not force:
        raise ApiError(409, "INCIDENT_STATE", f"Incident {incident_id!r} is {inc['status']}; send ?force=true to rerun")
    resume = inc["status"] == "diagnosing" and not force
    background.add_task(runner.start, env_name(env), incident_id, resume)
    return Accepted(incident_id=incident_id, status="diagnosing")


@router.get("/incidents/{incident_id}/hypotheses/{hid}/footprint", response_model=FootprintOut)
def footprint(incident_id: str, hid: str, env: Env) -> FootprintOut:
    inc = incident_or_404(env, incident_id)
    hyp_id = scoped_id(incident_id, f"r{inc['run']}:{hid}")
    rows = env.ro("hypothesis", id=hyp_id)
    fp = next((json.loads(e["value"]) for e in _evidence(env, hyp_id) if e["kind"] == "footprint"), None)
    if not rows or fp is None:
        raise ApiError(404, "HYPOTHESIS_NOT_FOUND", f"No footprint for hypothesis {hid!r} in {incident_id!r}")
    h = rows[0]
    return FootprintOut(
        hypothesis_id=hid,
        target=h["op"],
        cause_kind="+".join(h["kinds"] or []),
        coverage=fp["coverage"],
        precision=fp["precision"],
        order=fp["order"],
        footprint=fp["footprint"],
        predicted=[
            Prediction(op=p[0], kind=p[1], p=p[2], hops=p[3], onset_window_s=p[4] if len(p) > 4 else None)
            for p in fp["predictions"]
        ],
        matched=fp["matched"],
        missed=fp["missed"],
        unexplained=fp["unexplained"],
        summary=fp["explains"],
    )


@router.get("/incidents/{incident_id}/why-not/{service}", response_model=graph_tools.WhyNot)
def why_not(incident_id: str, service: str, env: Env) -> graph_tools.WhyNot:
    incident_or_404(env, incident_id)
    return graph_tools.why_not(incident_id, service, env=env_name(env))


@router.post("/incidents/{incident_id}/notes", status_code=201, response_model=NoteOut)
def add_note(incident_id: str, body: NoteIn, env: Env) -> NoteOut:
    incident_or_404(env, incident_id)
    if body.change and not env.ro("service_exists", svc=body.change.service):
        raise ApiError(404, "SERVICE_NOT_FOUND", f"No service {body.change.service!r}")
    [d] = env.rw("decision_add", inc=incident_id, by=body.by, text=body.text, ts=int(time.time()))
    change_id = None
    if body.change:
        # The next agent step (Q3's change lookup) sees a human-reported change like any ingested one
        [c] = env.rw(
            "U3",
            service=body.change.service,
            service_kind="app",  # the service exists (checked above), so this is never applied
            id=f"chg-manual-{incident_id}-{d['n']}",
            type=body.change.type,
            ts=epoch(body.change.ts),
            summary=f"{body.change.type} on {body.change.service} (noted by {body.by}: {body.text})",
            ref=f"note:{d['id']}",
        )
        change_id = c["id"]
    return NoteOut(decision_id=local_id(d["id"]), change_id=change_id)


@router.post("/incidents/{incident_id}/resolve", response_model=ResolveOut)
def resolve(incident_id: str, body: ResolveIn, env: Env) -> ResolveOut:
    inc = incident_or_404(env, incident_id)
    if inc["status"] not in RESOLVABLE:
        raise ApiError(409, "INCIDENT_STATE", f"Incident {incident_id!r} is {inc['status']}; it can't be resolved yet")
    action = None
    if body.fixed_by_action:
        rows = env.ro("action", id=scoped_id(incident_id, f"r{inc['run']}:{body.fixed_by_action}"))
        if not rows:
            raise ApiError(404, "ACTION_NOT_FOUND", f"No action {body.fixed_by_action!r} on {incident_id!r}")
        action = rows[0]
    env.rw("incident_resolve", inc=incident_id, by=body.by, ts=int(time.time()))
    if action:
        env.rw("action_resolve", inc=incident_id, id=action["id"])
        if action["runbook"] is not None:
            # ponytail: read-modify-write of one JSON property; fine at human resolve rates
            success = json.loads(action["success"] or "{}")
            step = str(action["step"])
            success[step] = success.get(step, 0) + 1
            env.rw("runbook_success", id=action["runbook"], success=json.dumps(success, sort_keys=True))
    return ResolveOut(status="resolved")


def _sse(e: dict) -> str:
    return f"id: {e['seq']}\nevent: {e['event']}\ndata: {json.dumps(e['data'], default=str)}\n\n"


@router.get("/incidents/{incident_id}/stream")
async def stream(
    incident_id: str,
    env: Env,
    request: Request,
    last_event_id: Annotated[str | None, Header(alias="Last-Event-ID")] = None,
    after: Annotated[
        int | None, Query(description="replay after this seq (for clients that can't set headers)")
    ] = None,
    follow: Annotated[bool, Query(description="false: replay, then close")] = True,
) -> StreamingResponse:
    incident_or_404(env, incident_id)
    try:
        seq = int(last_event_id) if last_event_id else (after or 0)
    except ValueError as e:
        raise ApiError(400, "VALIDATION_ERROR", "Last-Event-ID must be an event seq") from e

    async def events():
        nonlocal seq
        # Replay first, from the stream (survives restarts), then tail it live
        for e in await asyncio.to_thread(bus.history, env.key, incident_id, seq):
            seq = e["seq"]
            yield _sse(e)
        while follow and not await request.is_disconnected():
            # ponytail: a blocking read per subscriber in the threadpool; redis.asyncio if subscribers grow past it
            fresh = await asyncio.to_thread(bus.history, env.key, incident_id, seq, TAIL_BLOCK_MS)
            if not fresh:
                yield ": keepalive\n\n"
            for e in fresh:
                seq = e["seq"]
                yield _sse(e)

    return StreamingResponse(events(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})
