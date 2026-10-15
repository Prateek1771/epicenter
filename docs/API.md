# GraphRCA API Reference

**Base URL:** `http://localhost:8000/api/v1` · **Format:** JSON (UTF-8) · **Time:** ISO-8601 UTC
**Auth:** none for the local demo. If deployed, send `X-API-Key: <key>`; requests without it get `401`.
**MCP:** the same typed tools are served over MCP at `http://localhost:8000/mcp` (see [LLD §2.3](../LLD.md#23-tool-queries)).

---

## Errors

Every error uses one shape:

```json
{
  "error": { "code": "INCIDENT_NOT_FOUND", "message": "No incident 'inc-42' in env 'astronomy-shop'", "details": [] },
  "request_id": "req-7f3a"
}
```

| HTTP | Code | When |
|---|---|---|
| 400 | `VALIDATION_ERROR` | Bad body or query parameter |
| 401 | `UNAUTHORIZED` | Missing / wrong API key (deployed mode only) |
| 404 | `INCIDENT_NOT_FOUND`, `SERVICE_NOT_FOUND`, `ENV_NOT_FOUND` | Unknown id |
| 409 | `INCIDENT_STATE` | Action not allowed in the current state (e.g. resolve an `open` incident) |
| 502 | `UPSTREAM_ERROR` | OpenConnector or a telemetry source returned an error |
| 503 | `GRAPH_UNAVAILABLE` | FalkorDB unreachable |

Pagination (list endpoints): `?limit=20&cursor=<opaque>` → response has `next_cursor` (null at the end).

All endpoints take an optional `?env=<name>`; default is `ENV_NAME`.

---

## Alerts and incidents

### `POST /alerts`
Alertmanager-style webhook. Opens an incident or joins an open one (same symptom within 10 min).

```json
{ "alert_id": "am-8812", "env": "astronomy-shop", "symptom": "checkout/PlaceOrder",
  "starts_at": "2026-10-16T14:05:12Z", "labels": { "severity": "page" }, "auto_diagnose": true }
```
`202 Accepted`
```json
{ "incident_id": "inc-42", "status": "diagnosing", "joined_existing": false, "stream": "/api/v1/incidents/inc-42/stream" }
```

### `GET /incidents`
Query: `status`, `cause` (service name), `limit`, `cursor`.
```json
{ "items": [ { "id": "inc-42", "status": "diagnosed", "symptom": "checkout/PlaceOrder",
               "root_cause": "payment/Charge", "confidence": 0.91, "opened_at": "2026-10-16T14:05:12Z" } ],
  "next_cursor": null }
```

### `GET /incidents/{id}`
```json
{
  "id": "inc-42", "env": "astronomy-shop", "status": "diagnosed", "symptom": "checkout/PlaceOrder",
  "alert_count": 3, "gaps": [], "weights_version": "2026-10-15.v2",
  "verdict": {
    "root_cause": { "id": "h-7", "target": "payment/Charge", "target_type": "Operation", "status": "confirmed",
                    "score": 0.83, "hops": 2, "onset": "2026-10-16T14:03:40Z",
                    "score_parts": { "onset_earliness": 1.0, "strength": 0.9, "mechanism_fit": 1.0,
                                     "pagerank": 0.71, "change_match": 1.0, "footprint": 0.85, "refuted": 0 } },
    "confidence": 0.91,
    "footprint": { "coverage": 0.86, "precision": 0.82, "order": 0.9, "summary": "explains 6 of 7 symptoms",
                   "unexplained": ["ad/GetAds"] },
    "second_root_cause": null,
    "runner_up": { "id": "h-3", "target": "cart/GetCart", "status": "pruned", "score": 0.41 },
    "path": ["checkout/PlaceOrder", "payment/Charge"],
    "evidence": [
      { "id": "E3", "kind": "propagation", "verdict": "supports", "summary": "payment/Charge errors began 52 s before checkout/PlaceOrder",
        "path": ["checkout/PlaceOrder", "payment/Charge"], "ref": "jaeger:trace/4bf92f…" },
      { "id": "E5", "kind": "change", "verdict": "supports", "summary": "flag paymentFailure turned on at 14:03:31",
        "path": ["flag:paymentFailure", "payment"], "ref": "flagd:event/91" }
    ]
  },
  "hypotheses": [ { "id": "h-3", "target": "cart/GetCart", "status": "refuted" } ],
  "explanation": { "claims": [ { "section": "why", "text": "Payment requests started failing right after the paymentFailure flag was turned on.", "cites": ["E5", "E3"], "support_p": 0.94 } ],
                   "dropped": 1, "verified": true },
  "similar": [ { "incident": "inc-17", "score": 0.93, "cause": "payment/Charge", "fixes": ["turn off flag paymentFailure"] } ],
  "actions": [ { "id": "a-1", "name": "turn off flag paymentFailure", "status": "proposed", "delivery": null } ]
}
```

When nothing explains the alert, `status` is `no_root_cause`, `verdict` is `null`, and the response has
`"no_root_cause": { "summary": "Nothing in the graph explains this alert", "checked": ["h-1", "h-2"], "max_coverage": 0.31 }`.
When a second, independent fault is found, `verdict.second_root_cause` holds a hypothesis in the same shape as `root_cause`.

### `POST /incidents/{id}/diagnose`
Runs the agent flow, or resumes it after a crash. `202` → `{ "incident_id": "inc-42", "status": "diagnosing" }`.
`409 INCIDENT_STATE` if it's already `diagnosed` (send `?force=true` to rerun; the old hypotheses are kept and marked superseded).

### `GET /incidents/{id}/stream`
Server-Sent Events. Supports `Last-Event-ID` for replay. Event types are listed in [LLD §9](../LLD.md#9-events-sse).
```
id: 12
event: evidence.added
data: {"id":"E3","hypothesis_id":"h-7","kind":"propagation","verdict":"supports","path":["checkout/PlaceOrder","payment/Charge"]}
```

### `GET /incidents/{id}/hypotheses/{hid}/footprint`
Fault Simulator result for one hypothesis ([LLD §7](../LLD.md#7-fault-simulator)): predicted vs. observed.
```json
{ "hypothesis_id": "h-7", "target": "payment/Charge", "cause_kind": "errors",
  "coverage": 0.86, "precision": 0.82, "order": 0.9, "footprint": 0.85,
  "predicted": [ { "op": "checkout/PlaceOrder", "kind": "errors", "p": 0.8, "hops": 1, "onset_window_s": [0, 30] },
                 { "op": "frontend/POST /cart/checkout", "kind": "errors", "p": 0.62, "hops": 2, "onset_window_s": [0, 60] } ],
  "matched": ["payment/Charge", "checkout/PlaceOrder", "frontend/POST /cart/checkout"],
  "missed": ["frontend-proxy/POST /api/checkout"],
  "unexplained": ["ad/GetAds"],
  "summary": "explains 6 of 7 symptoms" }
```

### `GET /incidents/{id}/why-not/{service}`
```json
{ "service": "frontend", "answer": "victim",
  "summary": "frontend is slow because it waits on cart: child time ×6.1, self time ×1.0",
  "evidence": [ { "id": "E9", "kind": "victim", "verdict": "refutes", "path": ["frontend/GET /", "cart/GetCart"] } ] }
```
`answer` ∈ `victim`, `later_onset`, `no_anomaly`, `not_upstream`, `small_footprint` (explains too few symptoms),
`lost_on_score`, `is_root_cause`.

### `POST /incidents/{id}/notes`
Human input during an incident ([USER_FLOW Flow 6](../USER_FLOW.md#flow-6-human-takeover-mid-incident)).
```json
{ "by": "priya", "text": "currency deployed at 14:02", "change": { "service": "currency", "type": "deploy", "ts": "2026-10-16T14:02:00Z" } }
```
`201` → `{ "decision_id": "d-4", "change_id": "chg-manual-4" }` (`change` is optional).

### `POST /incidents/{id}/deliver`
```json
{ "targets": ["slack", "linear"], "slack_channel": "#incidents" }
```
`200` → `{ "results": [ { "target": "slack", "ok": true, "url": "https://…" }, { "target": "linear", "ok": false, "error": "UPSTREAM_ERROR" } ] }`

### `POST /incidents/{id}/resolve`
```json
{ "fixed_by_action": "a-1", "by": "priya", "note": "flag off, errors gone" }
```
`200` → `{ "status": "resolved" }`. Writes `RESOLVED_BY`, `FIXED`, bumps the runbook step's success count.

---

## Graph views

### `GET /graph/subgraph`
Query: `center` (node id), `hops` (1–3, default 2), `incident` (optional: include that incident's nodes).
```json
{ "nodes": [ { "id": "payment/Charge", "label": "Operation", "props": { "service": "payment" } } ],
  "edges": [ { "from": "checkout/PlaceOrder", "to": "payment/Charge", "type": "CALLS", "props": { "p95_ms": 840, "err_rate": 0.31 } } ] }
```

### `GET /blast-radius/{service}`
```json
{ "service": "redis", "affected": [ { "service": "cart", "operation": "cart/GetCart", "hops": 1, "owner": "team-cart" } ],
  "counts": { "services": 3, "operations": 9 }, "past_incidents": ["inc-11"] }
```

### `POST /simulate`
What-if mode of the Fault Simulator ([LLD §7.7](../LLD.md#77-what-if-mode-no-incident)): "what breaks if X fails?",
no incident needed. Give either `operation` or `service`.
```json
{ "service": "redis", "kind": "down", "save": true }
```
```json
{ "simulation_id": "sim-12", "target": "redis", "kind": "down", "rules_version": "2026-10-15",
  "predicted": [
    { "op": "cart/GetCart", "service": "cart", "kind": "errors", "p": 0.95, "hops": 1, "expected_delay_s": 15, "owner": "team-cart" },
    { "op": "checkout/PlaceOrder", "service": "checkout", "kind": "errors", "p": 0.61, "hops": 2, "expected_delay_s": 45, "owner": "team-payments" } ],
  "counts": { "services": 3, "operations": 9 } }
```
`kind` ∈ `errors`, `latency`, `cpu`, `mem`, `saturation`, `down`. `save: true` writes a `Simulation` node, so a later
incident can be compared with this prediction.

### `POST /ask`
```json
{ "question": "who should I page for checkout?", "incident_id": null }
```
```json
{ "answer": "team-payments owns checkout; Ravi fixed the last two checkout incidents.",
  "path": ["person:ravi", "FIXED", "inc-17", "ROOT_CAUSE", "h-7", "BLAMES", "checkout/PlaceOrder"],
  "tools_used": [ { "tool": "who_knows", "args": { "service": "checkout" } } ],
  "cypher": null }
```
`cypher` is set when the answer came from the read-only `falkordb-mcp` fallback, so the user can see the query.

---

## Example runs and eval

### `GET /runs/scenarios`
```json
{ "items": [ { "env": "flip-commerce", "id": "mongo-primary-down", "title": "Kill the Mongo primary" },
             { "env": "astronomy-shop", "id": "paymentFailure", "title": "flagd: paymentFailure" },
             { "env": "rcaeval-tt", "id": "re2-tt/ts-auth-service_cpu_1", "title": "RCAEval case" } ] }
```

### `POST /runs`
```json
{ "env": "flip-commerce", "scenario": "mongo-primary-down" }
```
`202` → `{ "run_id": "run-5", "incident_id": "inc-43" }`. Writes the `Change` node for the fault before triggering it.

### `GET /eval`
```json
{ "suite": "re2", "system": "tt", "cases": 90, "ac1": 0.0, "ac3": 0.0,
  "ablations": { "no_pagerank": { "ac1": 0.0 }, "no_temporal": { "ac1": 0.0 }, "no_mechanism": { "ac1": 0.0 } } }
```
(Values are placeholders until the eval runs.)

---

## Health

### `GET /health`
```json
{ "status": "ok", "falkordb": "ok", "falkordb_mcp": "ok", "openrouter": "ok", "openconnector": "degraded",
  "query_ms": { "Q1": { "p50": 9, "p95": 31 }, "Q2": { "p50": 14, "p95": 48 } } }
```
