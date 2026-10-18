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
| 404 | `INCIDENT_NOT_FOUND`, `SERVICE_NOT_FOUND`, `ENV_NOT_FOUND`, `HYPOTHESIS_NOT_FOUND`, `ACTION_NOT_FOUND`, `EVAL_NOT_FOUND`, `CONVERSATION_NOT_FOUND` | Unknown id (or no eval result yet) |
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
    "owner": "team-payments",
    "change": { "id": "chg-91", "service": "payment", "type": "flag", "ts": "2026-10-16T14:03:31Z",
                "summary": "flag paymentFailure → on" },
    "found_in_ms": 658,
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
  "actions": [ { "id": "a-1", "name": "turn off flag paymentFailure", "status": "proposed", "rank": 1, "chosen_by": "history", "p": null, "runbook": "rb-flag-rollback", "precedent": ["inc-17", "inc-9"] } ],
  "delivery": { "slack": { "ok": true, "url": "https://…", "error": null, "message": null, "ts": 1792159512, "run": 2 } }
}
```
`explanation.source` is `llm` (GPT-4o, gated by Jev) or `template` (built from the evidence: no key, model down or
invalid output; the UI shows "AI explanation unavailable"). Claim `status`: `verified` (Jev `support_p` ≥ the
calibrated `min_support`, 0.65),
`unverified` (Jev down), `template` (a fact the engine always states itself). `actions[].chosen_by`: `history` (it
fixed earlier incidents), `runbook` (runbook order), `demoted` (Jev judged it unrelated to the cause the evidence
shows; listed last). `p` is Jev's relevance score. Action ids are per run. `precedent`: incidents an action with
this name resolved, newest first (≤ 5), so a proposed fix cites where it worked before.

Verdict facts (phase 12): `owner` is the team owning the root cause's service; `change` is the `Change` the root
cause's `change` evidence attributes (null when no change preceded it); `found_in_ms` is diagnosis start → verdict
published, measured by the run that produced the current verdict.

When nothing explains the alert, `status` is `no_root_cause`, `verdict` is `null`, and the response has
`"no_root_cause": { "summary": "Nothing in the graph explains this alert", "checked": ["h-1", "h-2"], "max_coverage": 0.31 }`.
When a second, independent fault is found, `verdict.second_root_cause` holds a hypothesis in the same shape as `root_cause`.

### `GET /incidents/{id}/export.md`
Query: `flavor` = `human` (default) or `agent`. The incident as `text/markdown`, sent as a download:
`Content-Disposition: attachment; filename="{id}.incident_info.md"` (human) or `"{id}.agent.md"` (agent).
`human` is the report for people (facts, verdict, evidence, ruled out, explanation); `agent` is an AGENTS-style
context file for a coding agent opened on the failing service's repo (where to look, what's established, what not to
do). Built from `GET /incidents/{id}` by `deliver/report.py`: no LLM, so the same incident always gives the same file.
`400 VALIDATION_ERROR` for another `flavor`; `404 INCIDENT_NOT_FOUND`.

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
  "edges": [ { "src": "checkout/PlaceOrder", "dst": "payment/Charge", "rps": 1.05, "err_rate": 0.31, "p95_ms": 610.4 } ],
  "alert_ts": 1705918170,
  "changes": [ { "id": "chg-91", "service": "payment", "type": "flag", "ts": 1705918011, "summary": "flag paymentFailure → on" } ],
  "receipts": { "run": 3, "queries": [ { "n": 1, "qid": "incident", "ms": 3.5, "rows": 1 } ], "dropped": 0,
                "total_query_ms": 622.0, "verdict_ms": 658, "run_ms": 4970 } }
```
Phase 12 fields:
- `alert_ts` (epoch s, like anomaly onsets) is the time axis of the timeline lanes, the onset slicer and the T-minus
  strip.
- `changes` are the changes on the canvas's services from `lookback_s` (weights.json) before the alert to the window
  end.
- `receipts` is the current run's numbered graph queries (the `receipts` SSE event, kept on the incident so a reload
  shows them).

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

### `GET /graph/topology`
The service map (`/map`). Query: `level` = `service` (default) or `operation`; `hours` (1–168, default 24): halos
and crowns come from unresolved incidents opened that recently. Capped at 2000 nodes / edges (`truncated: true` when
hit).
```json
{ "level": "service", "truncated": false,
  "nodes": [ { "id": "payment", "service": "payment", "kind": "app", "owner": "payments", "ops": 1,
               "anomalies": [ { "incident": "inc-42", "kind": "errors", "score": 0.99 } ], "root_cause_of": ["inc-42"] } ],
  "edges": [ { "src": "checkout", "dst": "payment", "rps": 0.02, "err_rate": 0.5, "p95_ms": 610.4 } ] }
```
At `level=service`, an edge sums `rps` and takes the max `err_rate` / `p95_ms` over the operation calls between two
services; calls inside one service aren't edges.

### `GET /graph/explore`
The `/map` Network view: every label in the env graph, bounded. Query: `limit` (10–2000, default 300) nodes. Same
shape as `/graph/subgraph`, plus `label_counts` (every node in the env, by label: the legend) and `truncated` (more
nodes exist than were sent). Node ids are `Label:key` (key = `id`, else `name`, else `handle`), since keys repeat
across labels. Nodes come topology first (Service, Operation, Team, Person, Incident, Change, Runbook, Hypothesis,
Anomaly, then the rest); edges are the relationships among the sent nodes. `Conversation` and `Message` are left out.
```json
{ "nodes": [ { "id": "Service:payment", "label": "Service", "props": { "key": "payment", "name": "payment", "kind": "app" } } ],
  "edges": [ { "from": "Service:payment", "to": "Team:payments", "type": "OWNED_BY", "props": {} } ],
  "label_counts": { "Anomaly": 41, "Operation": 37, "Service": 12 }, "truncated": true }
```

### `GET /services`
Services in the env graph with their kind and operation count (the UI's service pickers).
```json
{ "items": [ { "name": "client", "kind": "external", "operations": 1 },
             { "name": "ts-admin-basic-info-service", "kind": "app", "operations": 3 } ] }
```

### `GET /services/{service}/changes`
Query: `hours` (1–168, default 24). Changes on one service in that window, newest first, with their authors (the
`/map` side panel). Bounded by time, so no cursor; an unknown service gives an empty list.
```json
{ "items": [ { "id": "chg-run-1792242819", "type": "flag", "ts": 1792242819, "summary": "flag paymentFailure → 50%",
               "authors": [] } ] }
```

### `GET /services/risk`
Query: `limit` (1–50, default 12). The riskiest services, the `/blast-radius` start screen: most incidents rooted
there (current run's root cause), then most distinct calling services.
```json
{ "items": [ { "name": "payment", "kind": "app", "callers": 2, "incidents": 3, "owner": "payments" } ] }
```

### `GET /services/{service}/people`
Who to page: the owning team's members, who fixed incidents rooted here, who changed it (the `who_knows` tool).
`404 SERVICE_NOT_FOUND`.
```json
{ "items": [ { "handle": "ravi", "name": "Ravi", "score": 3, "via": ["MEMBER_OF", "FIXED"], "team": "payments" } ] }
```

### `GET /services/{service}/runbooks`
Runbooks `FOR` the service, with each step's success count (times it fixed an incident). An unknown service gives an
empty list.
```json
{ "items": [ { "id": "rb-payment-flag", "kind": "errors", "steps": ["turn the flag off"], "success": { "turn the flag off": 2 } } ] }
```

### `GET /blast-radius/{service}`
```json
{ "service": "redis", "affected": [ { "service": "cart", "operation": "cart/GetCart", "hops": 1, "owner": "team-cart" } ],
  "counts": { "services": 3, "operations": 9 }, "past_incidents": ["inc-11"],
  "sources": ["redis/GET"],
  "edges": [ { "src": "cart/GetCart", "dst": "redis/GET", "rps": 3.1, "err_rate": 0.0, "p95_ms": 2.1 } ] }
```
`sources` are the failing service's own operations; `edges` are the `CALLS` among sources and affected operations
(the graph view).

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
  "counts": { "services": 3, "operations": 9 },
  "edges": [ { "src": "checkout/PlaceOrder", "dst": "cart/GetCart", "rps": 0.4, "err_rate": 0.0, "p95_ms": 12.0 } ] }
```
`edges` are the `CALLS` among the predicted operations (the graph view and its Play). `kind` ∈ `errors`, `latency`, `cpu`, `mem`, `saturation`, `down`. `save: true` writes a `Simulation` node, so a later
incident can be compared with this prediction.

### `POST /simulate/compare`
Body as `POST /simulate` (`save` is ignored). "Did it happen before?": the what-if prediction matched against each
past incident rooted at the target's service (the last 10), with the clock started at the target's earliest observed
onset in that incident ([LLD §7.7](LLD.md#77-what-if-mode-no-incident)). Incidents without anomalies are skipped.
Sorted by `footprint` desc, then incident. `404 SERVICE_NOT_FOUND`.
```json
{ "target": "payment", "kind": "errors",
  "items": [ { "incident": "inc-42", "observed": 7, "coverage": 0.86, "precision": 0.82, "footprint": 0.85,
               "explains": "explains 6 of 7 symptoms", "matched": ["payment/Charge"], "missed": [], "unexplained": ["ad/GetAds"] } ] }
```

### `GET /simulations`
Query: `limit` (1–50, default 20). Saved `Simulation` nodes (`POST /simulate` with `save: true`), newest first.
`operations` = how many operations it predicts.
```json
{ "items": [ { "id": "sim-redis-down-1792242819", "target": "redis", "kind": "down", "ts": 1792242819,
               "rules_version": "2026-10-15", "operations": 9 } ] }
```

### `GET /rules`
The propagation rules the simulator uses (`kb:propagation`, read-only; `?env` is ignored).
```json
{ "items": [ { "id": "r-errors-up", "cause_kinds": ["errors", "down"], "symptom_kind": "errors", "direction": "upstream",
               "p": 0.8, "delay_s_max": 30, "service_kind": null, "caller_kind": null, "version": "2026-10-15" } ] }
```

### `POST /ask`
```json
{ "question": "who should I page for checkout?", "incident_id": null, "conversation_id": "conv-1792242819000000000",
  "attachments": [ { "name": "pod.log", "text": "…" } ] }
```
```json
{ "answer": "team-payments owns checkout; Ravi fixed the last two checkout incidents.",
  "path": ["person:ravi", "FIXED", "inc-17", "ROOT_CAUSE", "h-7", "BLAMES", "checkout/PlaceOrder"],
  "tools_used": [ { "tool": "who_knows", "args": { "service": "checkout" } } ],
  "cypher": null, "conversation_id": "conv-1792242819000000000", "message_id": "conv-1792242819000000000:m0002" }
```
`cypher` is set when the answer came from the read-only `falkordb-mcp` fallback, so the user can see the query.
`path` only contains ids that appeared in tool results (plus relationship types). Needs the LLM: `502 UPSTREAM_ERROR`
when OpenRouter is unavailable.

`attachments`: up to 5 text files read in the browser (`name` ≤ 200 chars), ≤ 200,000 chars of text in total; context
for the model, never commands. `conversation_id` (optional) continues a saved conversation: its last 6 messages go to
the model as history, and the question and the answer are saved as `Message` nodes (attachment names only, never the
text). The question is saved before the model is called, so a `502` still leaves it in the thread. `message_id` is the
saved answer (`null` without a conversation). The first question becomes the conversation's title (≤ 60 chars, cut on
a word). `404 CONVERSATION_NOT_FOUND`.

### `POST /conversations`
```json
{ "title": null, "incident_id": "inc-42" }
```
`201` → a conversation (below). Created before the first question, so the client holds its id even when the LLM is
down. `incident_id` scopes it to an incident (`404 INCIDENT_NOT_FOUND`); `null` = the whole env. Conversations live
in the env graph, shared by every viewer.

### `GET /conversations`
Query: `incident` (only that incident's), `q` (title contains, case-insensitive, ≤ 100 chars), `limit` (1–100,
default 30), `cursor`. Newest `updated` first.
```json
{ "items": [ { "id": "conv-1792242819000000000", "title": "who should I page for checkout?", "incident": null,
               "created": "2026-10-17T10:00:19Z", "updated": "2026-10-17T10:00:24Z", "messages": 2 } ],
  "next_cursor": null }
```
`title` is `"New chat"` until the first question.

### `GET /conversations/{id}`
The conversation plus `message_list`, oldest first.
```json
{ "id": "conv-1792242819000000000", "title": "who should I page for checkout?", "incident": null,
  "created": "…", "updated": "…", "messages": 2,
  "message_list": [ { "id": "conv-1792242819000000000:m0001", "role": "user", "text": "who should I page for checkout?",
                      "ts": "…", "path": [], "tools_used": [], "cypher": null, "attachments": ["pod.log"] },
                    { "id": "conv-1792242819000000000:m0002", "role": "assistant", "text": "team-payments owns checkout…",
                      "ts": "…", "path": ["person:ravi", "FIXED", "inc-17"],
                      "tools_used": [ { "tool": "who_knows", "args": { "service": "checkout" } } ],
                      "cypher": null, "attachments": [] } ] }
```
`404 CONVERSATION_NOT_FOUND`.

### `DELETE /conversations/{id}`
`204`. Deletes the conversation and its messages. `404 CONVERSATION_NOT_FOUND`.

---

## Example runs and eval

### `GET /runs/scenarios`
Live scenarios from the registry (`api/runs.py`, EXAMPLE_RUNS tables) plus every replay case found in `RCAEVAL_DIR`
and in the committed `examples/samples/` (`SAMPLES_DIR`; a name in `RCAEVAL_DIR` wins).
`ready`: a live env is up (the host fault runner's `/health`, [ADR 0012](adr/0012-host-fault-runner.md)); a replay
case is on disk. `runner`: the fault runner answered.
```json
{ "runner": true,
  "items": [ { "env": "flip-commerce", "id": "mongo-majority-lost", "title": "Lose the Mongo majority (2 of 3 down)",
               "expected": "mongodb, kind down", "kind": "fault", "ready": true },
             { "env": "flip-commerce", "id": "healthy-baseline", "title": "Healthy baseline (no fault)",
               "expected": "no_root_cause", "kind": "baseline", "ready": true },
             { "env": "rcaeval-tt", "id": "re2tt_ts-auth-service_cpu_1", "title": "RCAEval replay: ts-auth-service cpu #1",
               "expected": "ts-auth-service/*, kind cpu", "kind": "replay", "ready": true } ] }
```
`kind`: `fault` (writes a `Change`, then injects) · `load` (traffic is the cause, no `Change`) · `baseline` (nothing
injected; a hand-fired alert that should end `no_root_cause`) · `replay` (RCAEval, or a synthetic case in env
`synthetic`). Each item also carries `expect`: `{"target_prefix": "payment/"}` or `{"status": "no_root_cause"}`.

### `GET /runs?env=&limit=`
The env's latest runs, newest first (the shared record: `Run` nodes). Each has `verdict` (the root-cause operation, or
the incident status when there is none) and `matches` (the verdict against the scenario's `expect`; `null` until
there is a verdict); the `/runs` cards show it as "matches expected" / "differs from expected".

### `POST /runs`
```json
{ "env": "flip-commerce", "scenario": "mongo-majority-lost" }
```
`202` → `{ "run_id": "run-1792145146", "incident_id": "inc-run-1792145146", "alert_at": "…", "change_id": "chg-run-1792145146" }`.

A live run, in order:
1. writes the `Change` node (like a deploy: on record **before** the fault, so its time precedes the effect);
2. has the fault runner inject the fault;
3. opens its own incident (never joins another run's, even on the same symptom) with the alert at fault +
   `settle_s` (~60 s, while the symptoms spread);
4. at `alert_at`, ingests the window around the alert from the live sources, then diagnoses.

A replay re-ingests the case and diagnoses it (incident `rc-<case>`).

Errors:
- `404 SCENARIO_NOT_FOUND`;
- `503 ENV_NOT_RUNNING` (start it with `examples/<env>/run.py up`);
- `502 FAULT_FAILED` (the fault script's output, recorded on the `Run` node).

### `DELETE /runs/{run_id}?env=`
Undo: the fault runner runs `faults.py <scenario> --undo`, which restores exactly what the fault touched. Returns
`{ "run_id", "status": "undone" }`, or `"nothing_to_undo"` for replays and baselines. Idempotent. The `Run` node stays
(history), marked `undone`.

### `GET /eval`
The newest result of `python -m api.eval` (`data/eval/<n>-re2-<system>-<weights>-<rules>.json`) with its timings, or
`404 EVAL_NOT_FOUND` before the first run. The suite never runs on a request.
```json
{ "run": "0003-re2-tt-2026-10-16.v3-2026-10-16", "suite": "re2", "system": "tt", "cases": 90,
  "ac1": 0.0, "ac3": 0.0,
  "split": { "dev": { "cases": 60, "ac1": 0.0, "ac3": 0.0 }, "test": { "cases": 30, "ac1": 0.0, "ac3": 0.0 } },
  "by_fault": { "cpu": { "cases": 15, "ac1": 0.0 } },
  "ablations": { "no_pagerank": { "ac1": 0.0, "ac3": 0.0 }, "no_temporal": { "ac1": 0.0, "ac3": 0.0 },
                 "no_mechanism": { "ac1": 0.0, "ac3": 0.0 }, "no_footprint": { "ac1": 0.0, "ac3": 0.0 } },
  "memory": { "cases": 88, "p_at_3": 0.0 },
  "weights_version": "2026-10-16.v3", "rules_version": "2026-10-16",
  "n1_ms": { "p50": 0.0, "p95": 0.0, "max": 0.0 }, "n2_p95_ms": { "Q1": 0.0, "Q2": 0.0, "Q3": 0.0, "Q4": 0.0, "Q5": 0.0 },
  "per_case": [ { "case": "re2tt_ts-auth-service_cpu_1", "split": "dev", "service": "ts-auth-service", "fault": "cpu",
                  "top3": ["ts-auth-service", "ts-user-service"], "hit1": true, "hit3": true } ] }
```
`per_case`: one row per case, sorted by name, for the `/eval` table (our top-3 services, verdict first; empty when the
verdict was `no_root_cause`). Each row also has `confidence`, `diagnose_ms` (from the timing file, else `null`),
`variants` (ablation → its top-1 service) and `parts` (the verdict's score parts) for the per-case drill-down.
`history`: every stored RE2 run, oldest first, as `{ "run", "ac1", "ac3", "cases", "weights_version" }`.
`synth`: the newest synthetic-suite summary (`--suite synth`), reported apart, or `null`:
`{ "run", "suite", "seed", "by_size": { "small": { "cases", "ac1", "ac3" } }, "weights_version", "rules_version" }`.
A hit means the verdict's root-cause operation belongs to the case's labelled service; AC@3 counts the labelled service
among the first three distinct services of the ranking. `no_root_cause` is a miss at every k. The values in the README
results table are the measured ones.

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
