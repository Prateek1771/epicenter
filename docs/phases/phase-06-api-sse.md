# Phase 6: REST API + SSE

**Goal:** every endpoint in [API.md](../API.md) (except `/deliver`, `/ask`, `/runs`, `/eval`, which come with their
phases) returns the documented shape, errors use one envelope, and the incident stream pushes one event per graph write
with replay on reconnect.

**Depends on:** phase 5. **Unblocks:** 7, 8, 9.

## Spec

- [API.md](../API.md): errors, pagination, `?env`, every endpoint body and response
- [LLD §9 Events (SSE)](../LLD.md#9-events-sse), [LLD §10 timeouts](../LLD.md#10-external-calls-timeouts-and-retries)
- [HLD §7 failure modes](../HLD.md#7-failure-modes), [HLD §9 security](../HLD.md#9-security), [HLD §10 observability](../HLD.md#10-observability-of-epicenter-itself)
- [LLD §8 incident state machine](../LLD.md#8-state-machines)

## Files

```
api/main.py           routers mounted, error handlers, CORS, request id middleware, startup seed
api/routes/incidents.py  alerts.py  graph_views.py (+ /simulate)  health.py  deps.py   (split by resource)
api/events.py         RedisStreamBus: per-incident Redis Stream + INCR seq in FalkorDB's Redis (LLD §9)
tests/test_api.py
```

## Tasks

- [x] Error envelope `{error:{code,message,details}, request_id}` for every error; codes from API.md; `GraphUnavailable` → 503.
- [x] `?env=` on every endpoint, default `ENV_NAME`; unknown env → `404 ENV_NOT_FOUND`.
- [x] Pagination `limit` + opaque `cursor` (encode `(opened_at, id)`), `next_cursor` null at the end.
- [x] `POST /alerts`: `MERGE` incident on alert id; join an open incident with the same symptom within 10 min (alert `count` +1); `202` with `stream` URL; start diagnosis in the background if `auto_diagnose`.
- [x] `GET /incidents` (filters `status`, `cause`), `GET /incidents/{id}` (full verdict shape incl. `footprint`, `second_root_cause`, `no_root_cause`).
- [x] `POST /incidents/{id}/diagnose` (resume; `409 INCIDENT_STATE` if diagnosed unless `?force=true`).
- [x] `GET /incidents/{id}/hypotheses/{hid}/footprint`, `GET /incidents/{id}/why-not/{service}`.
- [x] `POST /incidents/{id}/notes` → `Decision` (+ optional `Change`), so the next agent step sees it.
- [x] `POST /incidents/{id}/resolve` → `RESOLVED_BY`, `FIXED`, runbook success count +1. Enforce state transitions per LLD §8.
- [x] `GET /graph/subgraph` (hops 1–3), `GET /blast-radius/{service}`, `POST /simulate`.
- [x] `GET /incidents/{id}/stream`: `text/event-stream`, `id: <seq>`, event names from LLD §9; `Last-Event-ID` → replay missed events from the incident's Redis Stream, then live (decision: Redis Streams, not a rebuild from the subgraph; LLD §9).
- [x] `GET /health`: FalkorDB, falkordb-mcp, OpenRouter, OpenConnector status + per-query p50/p95 from the phase 1 registry.
- [x] CORS restricted to the web origin; optional `X-API-Key` check when `API_KEY` is set (deployed mode).
- [x] OpenAPI at `/docs` matches API.md (pydantic response models, not dicts).

## Acceptance

- Contract tests: each endpoint's response validates against the pydantic model built from the API.md example.
- Two alerts on the same symptom within 10 min → one incident, `alert_count = 2`.
- SSE client disconnects at seq 5 and reconnects with `Last-Event-ID: 5` → receives 6… with no gaps or duplicates.
- FalkorDB stopped → `503 GRAPH_UNAVAILABLE` with the error envelope, API process stays up.
- Resolving an `open` incident → `409 INCIDENT_STATE`.

## Scalability

- **Stateless handlers.** Every request reads from FalkorDB; nothing about an incident lives in API memory.
- **Replay from Redis Streams, not from a process buffer.** Reconnects work across restarts and across replicas: the
  stream and its seq live in FalkorDB's Redis.
- **Cursor pagination**, not offset, so lists stay fast as incident history grows.
- **Background diagnosis.** `POST /alerts` returns `202` immediately; the long work never holds a request open.
- **Alert-storm safe:** `MERGE` on alert id + 10-min join window means a storm becomes one incident, not hundreds of diagnoses.
- Ceiling: one uvicorn process. Before adding workers/replicas, move the checkpointer off SQLite and the
  "diagnosis running" set to a Redis `SET NX` lock (the event bus is already shared).

## Risks / open questions

- ~~`seq` monotonic per incident across restarts~~ **Closed:** `INCR seq:env:<name>:<incident>` + `XADD 0-<seq>` in
  one Lua script (LLD §9).
- `POST /alerts` with `auto_diagnose` diagnoses whatever anomalies the graph already holds; ingesting telemetry on
  alert arrives with the live adapters (phase 9).
- LangGraph thread ids now include the env (`<env>:<incident>:r<run>`): envs share one checkpoint DB.

## Done when

The UI team can build every screen against the live API, and every documented error and failure mode behaves as written.

## Results (2026-10-16)

- `tests/test_api.py` (15 tests): every endpoint's body parses into its pydantic model; two alerts in 10 min → one
  incident, `alert_count = 2`, 11 min → a new one; SSE replay after `Last-Event-ID` returns exactly the missed seqs and
  a fresh bus continues the count; `GraphUnavailable` → `503` envelope with `request_id` while `/health` still answers;
  resolve `open` → `409`; diagnose `diagnosed` → `409`, `?force=true` → a new run; cursor pages are complete and
  ordered; subgraph / blast radius / simulate match the tools.
- Live on `env:rcaeval-tt` (curl): `POST /diagnose?force=true` → `202`; the stream carried the whole run (109 events,
  ending in `verdict` + `incident.status`); reconnecting with `Last-Event-ID: 106` returned 107–109; `GET /incidents/{id}`
  matches the CLI verdict.
