"""POST /alerts: Alertmanager-style webhook that opens an incident or joins an open one (API.md)."""

import json
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Query, Request

from api.config import get_settings
from api.models import AlertAccepted, AlertIn
from api.routes.deps import env_name, epoch, resolve_env
from api.search import score as sc

router = APIRouter()

JOIN_WINDOW_S = 600  # an alert on the same symptom within 10 min joins the open incident


@router.post("/alerts", status_code=202, response_model=AlertAccepted)
def post_alert(
    body: AlertIn, request: Request, background: BackgroundTasks, env: Annotated[str | None, Query()] = None
) -> AlertAccepted:
    g = resolve_env(request, body.env or env)
    ts = epoch(body.starts_at)
    # Storm safe: the same alert id always lands on its incident, and the join window folds a storm into one incident
    found = g.ro("alert_incident", id=body.alert_id) or g.ro(
        "alert_find_open", symptom=body.symptom, ts=ts, window_s=JOIN_WINDOW_S
    )
    if found:
        incident_id, status = found[0]["id"], found[0]["status"]
    else:
        incident_id = f"inc-{body.alert_id}"
        wv = sc.load_weights(get_settings().weights_path)["version"]
        [row] = g.rw("alert_open_incident", id=incident_id, symptom=body.symptom, opened_at=ts, weights_version=wv)
        status = row["status"]
    g.rw(
        "alert_upsert",
        inc=incident_id,
        id=body.alert_id,
        starts_at=ts,
        labels=json.dumps(body.labels, sort_keys=True),
        symptom=body.symptom,
    )
    if body.auto_diagnose and status == "open":
        # ponytail: diagnoses whatever anomalies the graph holds; live ingest on alert arrives with phase 9 adapters
        background.add_task(request.app.state.diagnosis.start, env_name(g), incident_id, False)
        status = "diagnosing"
    return AlertAccepted(
        incident_id=incident_id,
        status=status,
        joined_existing=bool(found),
        stream=f"/api/v1/incidents/{incident_id}/stream?env={env_name(g)}",
    )
