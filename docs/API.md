# Epicenter API Reference

**Base URL:** `http://localhost:8000/api/v1` · **Format:** JSON (UTF-8) · **Time:** ISO-8601 UTC
**Auth:** none for the local demo. If deployed, send `X-API-Key: <key>`; requests without it get `401`.
**MCP:** the same typed tools are served over MCP at `http://localhost:8000/mcp` (see [LLD §2.3](LLD.md#23-tool-queries)).

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
| 404 | `INCIDENT_NOT_FOUND`, `SERVICE_NOT_FOUND`, `ENV_NOT_FOUND`, `HYPOTHESIS_NOT_FOUND`, `ACTION_NOT_FOUND` | Unknown id |
| 409 | `INCIDENT_STATE` | Action not allowed in the current state (e.g. resolve an `open` incident) |
| 502 | `UPSTREAM_ERROR` | OpenConnector or a telemetry source returned an error |
| 503 | `GRAPH_UNAVAILABLE` | FalkorDB unreachable |

Pagination (list endpoints): `?limit=20&cursor=<opaque>` → response has `next_cursor` (null at the end).
Every response carries an `X-Request-ID` header; errors repeat it as `request_id`.

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
{ "incident_id": "inc-42", "status": "diagnosing", "joined_existing": false, "stream": "/api/v1/incidents/inc-42/stream?env=astronomy-shop" }
```
A new incident's id is `inc-<alert_id>`. The same `alert_id` sent again lands on its incident (the alert's `count` +1);
otherwise an unresolved incident on the same `symptom` opened within ±10 min is joined. `auto_diagnose` starts a
diagnosis only for an incident that is still `open`; a joined one keeps its status. The env comes from the body, then
`?env`, then `ENV_NAME`.

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
  "explanation": { "claims": [ { "section": "why", "text": "Payment requests started failing right after the paymentFailure flag was turned on.", "cites": ["E5", "E3"], "support_p": 0.94, "status": "verified" } ],
                   "dropped": 1, "verified": true, "source": "llm",
                   "ai_calls": [ { "agent": "narrator", "model": "openai/gpt-4o-2024-11-20", "prompt_tokens": 1575, "completion_tokens": 210, "ms": 2053 } ] },
  "similar": [ { "incident": "inc-17", "score": 0.93, "cause": "payment/Charge", "fixes": ["turn off flag paymentFailure"] } ],
  "actions": [ { "id": "a-1", "name": "turn off flag paymentFailure", "status": "proposed", "rank": 1, "chosen_by": "history", "p": null, "runbook": "rb-flag-rollback" } ],
  "delivery": { "slack": { "ok": true, "url": "https://…", "error": null, "message": null, "ts": 1792159512, "run": 2 } }
}
```
`explanation.source` is `llm` (GPT-4o, gated by Jev) or `template` (built from the evidence: no key, model down or
invalid output; the UI shows "AI explanation unavailable"). Claim `status`: `verified` (Jev `support_p` ≥ the
calibrated `min_support`, 0.65),
`unverified` (Jev down), `template` (a fact the engine always states itself). `actions[].chosen_by`: `history` (it
fixed earlier incidents), `runbook` (runbook order), `demoted` (Jev judged it unrelated to the cause the evidence
shows; listed last). `p` is Jev's relevance score. Action ids are per run.

When nothing explains the alert, `status` is `no_root_cause`, `verdict` is `null`, and the response has
`"no_root_cause": { "summary": "Nothing in the graph explains this alert", "checked": ["h-1", "h-2"], "max_coverage": 0.31 }`.
When a second, independent fault is found, `verdict.second_root_cause` holds a hypothesis in the same shape as `root_cause`.

### `POST /incidents/{id}/diagnose`
Runs the agent flow, or resumes it after a crash. `202` → `{ "incident_id": "inc-42", "status": "diagnosing" }`.
`409 INCIDENT_STATE` if it's already `diagnosed` (send `?force=true` to rerun: a new run; earlier runs and their hypotheses stay in the graph as history, LLD §8).

### `GET /incidents/{id}/stream`
Server-Sent Events. Supports `Last-Event-ID` for replay (or `?after=<seq>` for clients that can't set headers);
`?follow=false` replays and closes. `seq` is per incident and survives API restarts (Redis Streams, [LLD §9](LLD.md#9-events-sse)).
A `: keepalive` comment is sent every ~2 s without events. Event types are listed in [LLD §9](LLD.md#9-events-sse).
```
id: 12
event: evidence.added
data: {"id":"E3","hypothesis_id":"h-7","kind":"propagation","verdict":"supports","path":["checkout/PlaceOrder","payment/Charge"]}
```

### `GET /incidents/{id}/graph`
Everything the incident canvas draws, in one load, for the current run. The UI then opens the stream with
`?after=<last_seq>`, so only newer events patch it (no replay of older runs). Bounded: ≤ 50 hypotheses, paths ≤ 6 hops.
`nodes` = every op on an evidence path + each hypothesis op + the symptom; `edges` = `CALLS` among those nodes.
```json
{ "incident": "inc-42", "run": 3, "status": "diagnosed", "symptom": "frontend/GET /cart",
  "root_cause": "payment/Charge", "second_cause": null, "last_seq": 118,
  "hypotheses": [ { "id": "h-1", "op": "payment/Charge", "status": "confirmed", "score": 0.71, "hops": 2, "round": 1,
                    "evidence": [ { "id": "E1.1", "kind": "propagation", "verdict": "supports", "summary": "…",
                                    "path": ["frontend/GET /cart", "checkout/PlaceOrder", "payment/Charge"] } ] } ],
  "nodes": [ { "id": "payment/Charge", "service": "payment", "service_kind": "app",
               "anomaly": { "kind": "errors", "onset": 1705918110, "score": 0.95 } } ],
  "edges": [ { "src": "checkout/PlaceOrder", "dst": "payment/Charge", "rps": 1.05, "err_rate": 0.31, "p95_ms": 610.4 } ] }
```
`round: 2` hypotheses are the second-cause search ([LLD §7.5](LLD.md)): scored on the symptoms the root cause leaves
unexplained, so their scores aren't comparable with round 1's.

### `GET /incidents/{id}/hypotheses/{hid}/footprint`
Fault Simulator result for one hypothesis ([LLD §7](LLD.md#7-fault-simulator)): predicted vs. observed.
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
Human input during an incident ([USER_FLOW Flow 6](USER_FLOW.md#flow-6-human-takeover-mid-incident)).
```json
{ "by": "priya", "text": "currency deployed at 14:02", "change": { "service": "currency", "type": "deploy", "ts": "2026-10-16T14:02:00Z" } }
```
`201` → `{ "decision_id": "d-4", "change_id": "chg-manual-inc-42-4" }` (`change` is optional; its service must exist,
else `404 SERVICE_NOT_FOUND`). The change is a normal `Change` node, so the next diagnosis run's change lookup sees it.

### `POST /incidents/{id}/deliver`
```json
{ "targets": ["slack", "linear"], "slack_channel": "#incidents" }
```
`200` → `{ "results": [ { "target": "slack", "ok": true, "url": "https://…" }, { "target": "linear", "ok": false, "error": "UPSTREAM_ERROR", "message": "LINEAR_TEAM_ID not set" } ] }`
Allowed on `diagnosed`, `delivered`, `no_root_cause` (else `409 INCIDENT_STATE`). Through OpenConnector
(`slack.post_message` + `slack.get_message_permalink`, `linear.create_linear_issue`); `slack_channel` defaults to
`SLACK_CHANNEL`, the Linear team to `LINEAR_TEAM_ID`. Each target succeeds or fails alone; the result is stored on the
incident (`delivery`), the status becomes `delivered` once a target succeeded. The `Idempotency-Key` is
`env:<name>:<incident>:r<run>:<target>:<payload hash>`: a retry of the same message never posts twice, and a different
message (another env, a recreated incident, a changed card) never reuses a key.

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

### `GET /services`
Services in the env graph with their kind and operation count (the UI's service pickers).
```json
{ "items": [ { "name": "client", "kind": "external", "operations": 1 },
             { "name": "ts-admin-basic-info-service", "kind": "app", "operations": 3 } ] }
```

### `GET /blast-radius/{service}`
```json
{ "service": "redis", "affected": [ { "service": "cart", "operation": "cart/GetCart", "hops": 1, "owner": "team-cart" } ],
  "counts": { "services": 3, "operations": 9 }, "past_incidents": ["inc-11"] }
```

### `POST /simulate`
What-if mode of the Fault Simulator ([LLD §7.7](LLD.md#77-what-if-mode-no-incident)): "what breaks if X fails?",
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
`path` only contains ids that appeared in tool results (plus relationship types). Needs the LLM: `502 UPSTREAM_ERROR`
when OpenRouter is unavailable.

---

## Example runs and eval

### `GET /runs/scenarios`
```json
{ "items": [ { "env": "flip-commerce", "id": "mongo-primary-down", "title": "Kill the Mongo primary" },
             { "env": "astronomy-shop", "id": "paymentFailure", "title": "flagd: paymentFailure" },
             { "env": "rcaeval-tt", "id": "re2tt_ts-auth-service_cpu_1", "title": "RCAEval case" } ] }
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
{ "status": "ok", "falkordb": "ok", "falkordb_mcp": "ok", "openrouter": "ok", "jev": "ok", "openconnector": "down",
  "query_ms": { "Q1": { "p50": 9, "p95": 31 }, "Q2": { "p50": 14, "p95": 48 } } }
```
`status` follows FalkorDB only (the verdict needs nothing else). `falkordb_mcp` / `openconnector` / `openrouter` /
`jev`: `ok` · `down` · `not_configured`. OpenRouter is checked with `GET /v1/key` (free), cached 60 s; `jev` shares
its key and status. Not behind `X-API-Key`.

### `GET /envs`
The environments that have a graph (`env:<name>`), and the default one. Feeds the UI's env switcher.
```json
{ "items": ["astronomy-shop", "demo", "rcaeval-tt"], "default": "astronomy-shop" }
```
