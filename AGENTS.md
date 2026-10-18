# AGENTS.md

Guide for coding agents (and humans) working in this repo. Read it before writing code.

## Project

**Epicenter** finds where an outage started. It keeps a live FalkorDB graph of a production system (services,
operations, calls, changes, owners), searches it upstream from an alert for the root cause, checks each suspect with a
**Fault Simulator** ("if this were the cause, what would we see?"), remembers past incidents and their fixes, and
returns every answer as a graph path. Built for Graph Hacks (FalkorDB).

**Status:** built and demo-ready (phases 0–12). Build order and acceptance checks are in
[docs/phases/](docs/phases/README.md): new work starts from the first phase whose "Done when" isn't met.

## Where to look

| Need | Read |
|---|---|
| What to build next, task list, acceptance checks | [docs/phases/](docs/phases/README.md) |
| Requirements, principles, decisions at a glance | [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) |
| Containers, ports, compose, failure modes, security | [docs/HLD.md](docs/HLD.md) |
| Modules, signatures, every Cypher query, scoring, agents, tests | [docs/LLD.md](docs/LLD.md) |
| Labels, edges, properties, indexes | [docs/GRAPH_SCHEMA.md](docs/GRAPH_SCHEMA.md) |
| Endpoints and payloads | [docs/API.md](docs/API.md) |
| Screens and user flows | [docs/USER_FLOW.md](docs/USER_FLOW.md) |
| Demo environments and fault scenarios | [docs/EXAMPLE_RUNS.md](docs/EXAMPLE_RUNS.md) |
| Why a decision was made | [docs/adr/](docs/adr/) |

When docs disagree: ARCHITECTURE / HLD / LLD / API / GRAPH_SCHEMA / ADRs win over [docs/planning/](docs/planning/)
(older notes) and over the phase files (which only point at the design).

## Stack

FalkorDB (Docker, pinned tag) · Python 3.12, FastAPI, pydantic v2, LangGraph · numpy, `ruptures`, Drain3, networkx
(fallback only) · OpenRouter (LLM + Jev) · OpenConnector (Slack / Linear) · Next.js App Router, Tailwind, shadcn,
React Flow · Docker Compose.

## Layout (target, from [LLD §1](docs/LLD.md#1-package-layout))

```
api/        main.py config.py graph.py models.py events.py
            ingest/  search/  agents/  tools/  ai/  deliver/  eval.py  smoke_falkordb.py
web/        Next.js app
seed/       owners.yaml runbooks.yaml propagation_rules.yaml
examples/   flip-commerce/ otel-demo/
tests/      fixtures/mini_graph.cypher …
weights.json  docker-compose.yml  .env.example
```

## Commands

```bash
cp .env.example .env                                   # fill FALKORDB_PASSWORD, pinned tags, keys
docker compose up -d                                   # falkordb, falkordb-mcp, api, web, open-connector
docker compose exec api python -m api.smoke_falkordb   # FalkorDB feature check on the pinned tag
docker compose exec api pytest                         # tests (FalkorDB must be up)
docker compose exec api python -m api.ingest.rcaeval --case re2tt_ts-auth-service_cpu_2 --env rcaeval-tt --download
docker compose exec api python -m api.eval --suite re2 --system tt
```

Host ports: FalkorDB **6380** (not 6379), browser 3002, falkordb-mcp 8081, API 8000, web 3001, OpenConnector 3000.

## Hard rules

Breaking one of these breaks the product's core promise. Each has an ADR.

1. **Dependency direction:** `agents → tools → search → graph`, `ingest → graph`. Nothing imports `agents` except `main.py`. ([ADR 0005](docs/adr/0005-modular-monolith.md))
2. **Only `api/graph.py` talks to FalkorDB.** Every query lives in its `QUERIES` dict; callers pass a query id and parameters, never Cypher text.
3. **Parameterized Cypher only** (`$param`). No f-strings or `%` formatting into a query. Agents never send Cypher to the write path; free-form Cypher goes only through the read-only `falkordb-mcp`. ([ADR 0003](docs/adr/0003-typed-mcp-tools.md))
4. **The LLM never ranks, never writes topology, never sets hypothesis status.** LLM output goes only into `Explanation` and `Action {status:'proposed'}` and is never read by the scorer. ([ADR 0002](docs/adr/0002-deterministic-ingestion-and-scoring.md), [ADR 0004](docs/adr/0004-no-graphiti.md))
5. **Determinism:** same input → same ranking and `score_parts`, byte for byte. Sort inputs by key, tie-break on id, weights and rules come from versioned files, no `random`, no Python `hash()` for features.
6. **Agent state holds ids only;** content lives in the incident subgraph. ([ADR 0007](docs/adr/0007-graph-as-shared-agent-state.md))
7. **No raw telemetry in the graph.** Spans aggregate into `CALLS`; anomalies keep a `ref` back to the source. ([ADR 0006](docs/adr/0006-operation-level-aggregation.md))
8. **One graph per environment** (`env:<name>`). Never query across `env:*` graphs. Scratch graphs are deleted in `finally`.
9. **Read-only towards monitored systems.** Actions are proposals. Only `examples/*/faults.py` changes an environment, and only on purpose.
10. **Never modify the flip-commerce source repo** (`system-design-journey`). Everything it needs lives in `examples/flip-commerce/`.
11. **No secrets** in the graph, in logs, or in git. `.env*` is git-ignored.
12. **The verdict works with every LLM down** (template explanation, `unverified` claims).

## Writing scalable code

Build for the laptop demo, but don't paint the code into a corner. Prefer seams that already exist in the design over
new infrastructure. When you take a shortcut with a known ceiling, say so in a comment with the upgrade path.

- **Keep the API stateless.** Shared state belongs in FalkorDB (the SSE event log is a Redis Stream there). The allowed
  in-process pieces are the LangGraph SQLite checkpointer and the "diagnosis already running" set; each sits behind an
  interface so it can move to a server-backed checkpointer / a Redis lock when there is more than one API replica.
- **Extend through the existing seams:** a new telemetry source is a new `Adapter`; a new failure mode is a new rule in
  `seed/propagation_rules.yaml` + version bump; a new agent capability is a new typed tool; a new query is a new
  `QUERIES` entry with an index for its lookup key.
- **Bound every traversal** (hop limit 6, start from an indexed node, filter by `incident` early). Run graph algorithms on a projection in `scratch:<incident>`, never on the whole env graph.
- **Aggregate before writing** and batch writes with `UNWIND $rows` once a write loop exceeds ~100 rows. FalkorDB serializes writes per graph; keep each write small.
- **Pure functions for logic** (detectors, scoring, simulation, signature): data in, data out, no I/O. They test easily and can move to a worker unchanged.
- **Long work off the request path:** endpoints that start diagnosis return `202`; the work runs in the background.
- **Config from `api/config.py`** only. Thresholds and weights in `weights.json`, not in code.
- **Cursor pagination** on list endpoints; never offset.
- **Timeouts and retries on every external call** per [LLD §10](docs/LLD.md#10-external-calls-timeouts-and-retries).

## Code style

- Small modules matching the LLD layout. Match the surrounding code's naming, comment density and idioms.
- Type hints everywhere; pydantic models at boundaries (REST, tools, agent I/O).
- Structured JSON logs with `incident_id`, `agent`, `tool`, `query_id`, `duration_ms`, `rows`.
- No abstractions without a second user; no scaffolding "for later".
- Error responses use the envelope in [API.md](docs/API.md#errors).

## Tests

- Every non-trivial piece of logic (a rule, a detector, a score, a query) leaves one runnable check behind.
- Query tests run against `tests/fixtures/mini_graph.cypher` loaded into `env:test`.
- The full list of required tests is [LLD §12](docs/LLD.md#12-test-plan); each phase file names the ones it owns.
- A phase isn't done until its acceptance checks pass.

## Changing the design

- Small clarifications: edit the design doc in the same change as the code.
- Reversing a decision: add a new ADR in `docs/adr/` (next number) and update the docs that reference the old one.
- Open questions found while building are tracked in [docs/phases/README.md](docs/phases/README.md#open-questions-found-while-phasing); close them there when decided.

## Git

- Branch off `main`; small commits that each leave tests green.
- Commit or push only when asked.
