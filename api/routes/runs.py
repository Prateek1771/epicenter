"""Example runs (API.md "Example runs and eval"): list scenarios, start one, undo it.

`POST /runs` on a live scenario, in order:
1. write the `Change` (deploy-like: on record before the fault, LLD §3.1);
2. trigger the fault on the host (fault runner);
3. open the incident with its alert at fault + `settle_s`;
4. return 202.

In the background it waits for that moment, then diagnoses: the live adapter ingests the window around the alert
first (api/ingest/live.py). A replay scenario re-ingests the RCAEval case and diagnoses it.
"""

import time
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Query, Request

from api import runs
from api.config import get_settings
from api.ingest import rcaeval, write
from api.ingest.base import ChangeEvent
from api.ingest.seed import seed_indexes
from api.models import AlertIn, RunAccepted, RunIn, RunOut, Runs, RunUndone, ScenarioOut, Scenarios
from api.routes.alerts import open_alert
from api.routes.deps import ApiError, graph, iso, resolve_env

router = APIRouter()

FLUSH_S = 5  # the collector's file exporter and Jaeger need a moment to hold the last spans before the alert


@router.get("/runs/scenarios", response_model=Scenarios)
def list_scenarios(request: Request) -> Scenarios:
    up = request.app.state.runner.health()
    items = [
        ScenarioOut(
            env=s.env,
            id=s.id,
            title=s.title,
            expected=s.expected,
            kind=s.kind,
            ready=True if s.kind == "replay" else up.get(s.env, False),
        )  # fmt: skip
        for s in runs.scenarios()
    ]
    return Scenarios(items=items, runner=bool(up))


@router.get("/runs", response_model=Runs)
def recent_runs(request: Request, env: str = Query(), limit: int = Query(5, ge=1, le=50)) -> Runs:
    """The env's latest runs, newest first: the shared record (Run nodes), so every viewer sees the same history."""
    if env not in graph(request).env_names():
        return Runs(items=[])  # a live env's graph appears with its first topology tick or run
    items = []
    for r in graph(request).env(env).ro("runs_recent", limit=limit):
        sc = runs.find(env, r["scenario"])
        settle = sc.settle_s if sc and sc.kind != "replay" else 0
        items.append(RunOut(run_id=r["id"], env=env, scenario=r["scenario"], title=sc.title if sc else r["scenario"],
                            kind=sc.kind if sc else "fault", status=r["status"], incident_id=r["incident"],
                            started_at=iso(r["started_at"]), alert_at=iso(r["started_at"] + settle),
                            detail=r["detail"]))  # fmt: skip
    return Runs(items=items)


def _diagnose_at(diagnosis, env: str, incident: str, alert_ts: int) -> None:
    time.sleep(max(0.0, alert_ts + FLUSH_S - time.time()))
    diagnosis.start(env, incident, False)


def _replay(request: Request, env: str, case: str) -> None:
    out = rcaeval.replay(Path(get_settings().rcaeval_dir) / case, env, graph(request))
    request.app.state.diagnosis.start(env, out["incident"], False)


@router.post("/runs", status_code=202, response_model=RunAccepted)
def start_run(body: RunIn, request: Request, background: BackgroundTasks) -> RunAccepted:
    sc = runs.find(body.env, body.scenario)
    if sc is None:
        raise ApiError(404, "SCENARIO_NOT_FOUND", f"No scenario {body.scenario!r} for env {body.env!r}")
    ts = int(time.time())
    run_id = f"run-{ts}"
    g = graph(request).env(sc.env)
    seed_indexes(g)  # a live env's graph may not exist before its first run

    if sc.kind == "replay":
        incident = f"rc-{sc.id}"
        g.rw("run_create", id=run_id, scenario=sc.id, ts=ts, incident=incident)
        background.add_task(_replay, request, sc.env, sc.id)
        return RunAccepted(run_id=run_id, incident_id=incident, alert_at=iso(ts))

    runner = request.app.state.runner
    if not runner.health().get(sc.env):
        start = f"examples/{runs.EXAMPLE_DIRS.get(sc.env, sc.env)}/run.py up"
        raise ApiError(503, "ENV_NOT_RUNNING", f"{sc.env} isn't up (start it with {start})")
    change_id = None
    if sc.change:
        change_id = f"chg-{run_id}"
        write.write_change(g, ChangeEvent(id=change_id, ts=ts, ref=f"run:{run_id}", **sc.change))
    alert_ts = ts + sc.settle_s
    incident, _, _ = open_alert(g, AlertIn(alert_id=run_id, symptom=sc.symptom, auto_diagnose=False,
                                           starts_at=datetime.fromtimestamp(alert_ts, UTC),
                                           labels={"run": run_id, "scenario": sc.id}), join=False)  # fmt: skip
    g.rw("run_create", id=run_id, scenario=sc.id, ts=ts, incident=incident)
    if sc.kind != "baseline":
        try:
            detail = runner.fault(sc.env, sc.id, change_id=change_id)
        except runs.RunnerError as e:
            # the tail: a traceback ends with its error
            g.rw("run_set_status", id=run_id, status="fault_failed", detail=str(e)[-500:])
            raise ApiError(502, "FAULT_FAILED", str(e)[-500:]) from e
        g.rw("run_set_status", id=run_id, status="started", detail=detail[:500])
    background.add_task(_diagnose_at, request.app.state.diagnosis, sc.env, incident, alert_ts)
    return RunAccepted(run_id=run_id, incident_id=incident, alert_at=iso(alert_ts), change_id=change_id)


@router.delete("/runs/{run_id}", response_model=RunUndone)
def undo_run(run_id: str, request: Request, env: str = Query()) -> RunUndone:
    g = resolve_env(request, env)
    [r] = g.ro("run_get", id=run_id) or [None]
    if r is None:
        raise ApiError(404, "RUN_NOT_FOUND", f"No run {run_id!r} in {env!r}")
    sc = runs.find(env, r["scenario"])
    if sc is None or sc.kind in ("replay", "baseline"):
        return RunUndone(run_id=run_id, status="nothing_to_undo")
    if r["status"] == "undone":
        return RunUndone(run_id=run_id, status="undone")
    try:
        detail = request.app.state.runner.fault(env, sc.id, undo=True)
    except runs.RunnerError as e:
        raise ApiError(502, "FAULT_FAILED", str(e)[-500:]) from e
    g.rw("run_set_status", id=run_id, status="undone", detail=detail[:500])
    return RunUndone(run_id=run_id, status="undone")
