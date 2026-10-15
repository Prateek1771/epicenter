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
api/routes/incidents.py  alerts.py  graph_views.py  simulate.py  health.py   (split by resource)
api/events.py         per-subscriber asyncio.Queue, seq counter, replay from graph
tests/test_api.py
```

## Tasks

- [ ] Error envelope `{error:{code,message,details}, request_id}` for every error; codes from API.md; `GraphUnavailable` → 503.
- [ ] `?env=` on every endpoint, default `ENV_NAME`; unknown env → `404 ENV_NOT_FOUND`.
- [ ] Pagination `limit` + opaque `cursor` (encode `(opened_at, id)`), `next_cursor` null at the end.
- [ ] `POST /alerts`: `MERGE` incident on alert id; join an open incident with the same symptom within 10 min (alert `count` +1); `202` with `stream` URL; start diagnosis in the background if `auto_diagnose`.
- [ ] `GET /incidents` (filters `status`, `cause`), `GET /incidents/{id}` (full verdict shape incl. `footprint`, `second_root_cause`, `no_root_cause`).
- [ ] `POST /incidents/{id}/diagnose` (resume; `409 INCIDENT_STATE` if diagnosed unless `?force=true`).
- [ ] `GET /incidents/{id}/hypotheses/{hid}/footprint`, `GET /incidents/{id}/why-not/{service}`.
- [ ] `POST /incidents/{id}/notes` → `Decision` (+ optional `Change`), so the next agent step sees it.
- [ ] `POST /incidents/{id}/resolve` → `RESOLVED_BY`, `FIXED`, runbook success count +1. Enforce state transitions per LLD §8.
- [ ] `GET /graph/subgraph` (hops 1–3), `GET /blast-radius/{service}`, `POST /simulate`.
- [ ] `GET /incidents/{id}/stream`: `text/event-stream`, `id: <seq>`, event names from LLD §9; `Last-Event-ID` → replay missed events by reading the incident subgraph, then live.
- [ ] `GET /health`: FalkorDB, falkordb-mcp, OpenRouter, OpenConnector status + per-query p50/p95 from the phase 1 registry.
- [ ] CORS restricted to the web origin; optional `X-API-Key` check when `API_KEY` is set (deployed mode).
- [ ] OpenAPI at `/docs` matches API.md (pydantic response models, not dicts).

## Acceptance

- Contract tests: each endpoint's response validates against the pydantic model built from the API.md example.
- Two alerts on the same symptom within 10 min → one incident, `alert_count = 2`.
- SSE client disconnects at seq 5 and reconnects with `Last-Event-ID: 5` → receives 6… with no gaps or duplicates.
- FalkorDB stopped → `503 GRAPH_UNAVAILABLE` with the error envelope, API process stays up.
- Resolving an `open` incident → `409 INCIDENT_STATE`.

## Scalability

- **Stateless handlers.** Every request reads from the graph; nothing about an incident lives in API memory except SSE
  subscriber queues. That makes horizontal scaling a matter of replacing the event bus (phase 5 note).
- **Replay from the graph, not from a buffer.** Reconnects work across restarts and across replicas because the graph is the source of truth.
- **Cursor pagination**, not offset, so lists stay fast as incident history grows.
- **Background diagnosis.** `POST /alerts` returns `202` immediately; the long work never holds a request open.
- **Alert-storm safe:** `MERGE` on alert id + 10-min join window means a storm becomes one incident, not hundreds of diagnoses.
- Ceiling: one uvicorn process. Before adding workers/replicas, move the event bus to Redis Streams and the checkpointer off SQLite.

## Risks / open questions

- `seq` must be monotonic per incident across restarts; store the last `seq` on the `Incident` node or derive it from write order.

## Done when

The UI team can build every screen against the live API, and every documented error and failure mode behaves as written.
