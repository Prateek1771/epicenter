# GraphRCA: High-Level Design

Scope: the containers, how they talk, how data moves and ages, how the system fails, scales and stays safe.
Module-level detail is in [LLD.md](LLD.md). Requirements (F1–F10, N1–N7) are in [ARCHITECTURE.md §1](ARCHITECTURE.md#1-requirements).

---

## 1. Architecture style

**Modular monolith** ([ADR 0005](docs/adr/0005-modular-monolith.md)). A team of 1–3 people building for a hackathon gets
nothing from microservices. The API process holds four modules with clear boundaries: `ingest`, `search`, `agents`,
`tools`. They talk through function calls, and **through the graph**. FalkorDB is the only stateful component.

Exceptions, each with a reason:
- `falkordb-mcp` is the official image, so it runs as its own container.
- `web` is a separate Next.js app.
- `open-connector` is a third-party service.

---

## 2. Containers

```mermaid
flowchart LR
    U(["Browser"]) -->|":3001"| WEB["web<br/>Next.js"]
    WEB -->|"REST + SSE :8000/api/v1"| API

    subgraph API["api (FastAPI, Python 3.12)"]
        direction TB
        REST["REST + SSE"]
        AGT["agents<br/>(LangGraph)"]
        SRCH["search<br/>Q1–Q5 · scorer"]
        TOOLS["tools<br/>typed, also MCP at /mcp"]
        ING["ingest<br/>adapters + detectors"]
        BUS["in-process event bus"]
        REST --> AGT --> TOOLS & SRCH
        AGT --> BUS --> REST
    end

    API -->|"redis protocol :6379"| FDB[("falkordb<br/>FalkorDB server")]
    FMCP["falkordb-mcp<br/>read-only"] --> FDB
    AGT -->|"MCP HTTP :8080"| FMCP
    BRW["FalkorDB browser<br/>:3002"] --> FDB

    AGT -->|HTTPS| OR["OpenRouter<br/>LLM · Jev"]
    AGT -->|":3000 /v1/actions"| OC["open-connector"] --> EXT["Slack · Linear"]

    ING -->|"read-only HTTP / files"| SRC["Telemetry sources<br/>Jaeger · Prometheus · OTel Collector ·<br/>log files · RCAEval files"]
```

| Container | Image | Responsibility | State |
|---|---|---|---|
| `falkordb` | `falkordb/falkordb:<pinned>` | Graph storage and queries; browser UI | **All persistent state** (named volume) |
| `falkordb-mcp` | `falkordb/mcpserver:<pinned>` | Read-only Cypher + schema tools for the ask box | none |
| `api` | built from `./api` | Ingest, causal search, agents, typed tools (REST + MCP), SSE | none (in-memory event bus only) |
| `web` | built from `./web` | UI | none |
| `open-connector` | OpenConnector self-host image | Slack / Linear delivery with OAuth | its own config |

---

## 3. Runtime views

### 3.1 Alert → diagnosis (the main flow)

```mermaid
sequenceDiagram
    autonumber
    participant SRC as Env (OTel / flip / replay)
    participant API as api: REST
    participant ING as api: ingest
    participant AG as api: agents
    participant G as FalkorDB
    participant OR as OpenRouter
    participant OC as OpenConnector
    participant WEB as web (SSE)

    SRC->>API: POST /api/v1/alerts
    API->>G: MERGE Incident (dedup on alert id)
    API-->>SRC: 202 {incident_id}
    API->>ING: snapshot window [t-10m, t+5m]
    ING->>SRC: read traces / metrics / logs / changes
    ING->>G: write Anomaly + Change nodes
    API->>AG: run(incident_id)
    AG->>G: triage: blast radius, Q1 → Hypothesis nodes
    AG-->>WEB: hypothesis.created …
    par investigators
        AG->>G: Q2, Q3 → Evidence, SUPPORTED_BY / REFUTED_BY
        AG-->>WEB: evidence.added, hypothesis.status
    end
    AG->>G: Q4 on scratch graph, score, ROOT_CAUSE
    AG->>G: skeptic, historian (Q5)
    AG->>OR: narrate winning path (cites Evidence ids)
    AG->>OR: Jev: is each claim supported?
    AG->>G: Explanation, Action
    AG-->>WEB: incident.diagnosed
    AG->>OC: Slack card + Linear issue
```

### 3.2 Ask box

`POST /api/v1/ask` → ask agent (OpenRouter LLM) with two tool sets: the typed tools (preferred) and
`falkordb-mcp` (`get_graph_schema`, `query_graph_readonly`) as a fallback. The answer comes back with the node/edge ids it
used, so the UI highlights the path.

### 3.3 Memory recall

The historian computes the incident's 64-dim signature ([ADR 0008](docs/adr/0008-deterministic-incident-signature.md)) and runs Q5
(vector index + graph overlap). It writes `SIMILAR_TO` edges. When an incident is resolved, `RESOLVED_BY` edges and the
runbook step's success count update **procedural memory**.

---

## 4. Data flow and lifecycle

```mermaid
flowchart LR
    T["Traces"] -->|"every 30 s"| TOPO["Service / Operation / CALLS<br/>(rolling stats)"]
    M["Metrics"] -->|"per incident window"| AN["Anomaly"]
    L["Logs"] -->|"per incident window"| SIG["Signal (log template)"] --> AN
    C["Flag flips / deploys / config / docker stop"] -->|"as they happen"| CH["Change"]
    TOPO & AN & CH --> INV["Incident subgraph<br/>Hypothesis · Evidence · Explanation · Action"]
    INV -->|"projection"| SCR["scratch:&lt;incident&gt;<br/>(deleted after scoring)"]
    INV -->|"kept"| MEM["Memory<br/>SIMILAR_TO · RESOLVED_BY"]
```

| Data | Created | Updated | Deleted |
|---|---|---|---|
| Topology (`Service`, `Operation`, `CALLS`, `Pod`) | first seen in traces | rolling stats every 30 s | never (marked `last_seen`) |
| `Change` | when the change happens | never | never |
| `Anomaly`, `Signal` | when an incident window opens | never | with the incident (manual purge only) |
| `Incident` subgraph | on alert | during diagnosis and resolution | kept as memory |
| `scratch:<incident>` graph | scoring step | — | right after scoring |

Raw telemetry (spans, metric points, log lines) is **never** stored in FalkorDB ([ADR 0006](docs/adr/0006-operation-level-aggregation.md)).
Evidence nodes keep a `ref` back to the source (trace id, PromQL, log file + line range).

---

## 5. Deployment

### 5.1 Ports

| Host port | Container | Note |
|---|---|---|
| **6380** | `falkordb:6379` | 6379 is left free for flip-commerce's own Redis ([ADR 0009](docs/adr/0009-falkordb-via-docker.md)) |
| **3002** | `falkordb:3000` (browser) | 3000 belongs to OpenConnector |
| **8081** | `falkordb-mcp:8080` | 8080 belongs to the example environments |
| 8000 | `api` | REST at `/api/v1`, MCP at `/mcp` |
| 3001 | `web` | |
| 3000 | `open-connector` | |
| 8080, 16686, 9090 | OTel Demo (separate compose) | run one example environment at a time |
| 8080, 6379, 27017–27019 | flip-commerce (its own compose) | run one example environment at a time |

### 5.2 `docker-compose.yml`

```yaml
services:
  falkordb:
    image: falkordb/falkordb:${FALKORDB_TAG}
    ports: ["6380:6379", "3002:3000"]
    environment:
      REDIS_ARGS: "--requirepass ${FALKORDB_PASSWORD} --appendonly yes"
      FALKORDB_ARGS: "THREAD_COUNT 4 TIMEOUT_MAX 30000"
    volumes:
      - falkordb_data:/var/lib/falkordb/data   # docs also mention /data; verify on first run (README §4)
    healthcheck:
      test: ["CMD", "redis-cli", "-a", "${FALKORDB_PASSWORD}", "PING"]
      interval: 5s
      retries: 10
    restart: unless-stopped

  falkordb-mcp:
    image: falkordb/mcpserver:${FALKORDB_MCP_TAG}
    ports: ["8081:8080"]
    environment:
      FALKORDB_HOST: falkordb
      FALKORDB_PORT: 6379
      FALKORDB_PASSWORD: ${FALKORDB_PASSWORD}
      FALKORDB_DEFAULT_READONLY: "true"
      MCP_TRANSPORT: http
      MCP_PORT: 8080
      MCP_API_KEY: ${MCP_API_KEY}
    depends_on: { falkordb: { condition: service_healthy } }

  api:
    build: ./api
    ports: ["8000:8000"]
    env_file: .env
    environment:
      FALKORDB_URL: redis://:${FALKORDB_PASSWORD}@falkordb:6379
      FALKORDB_MCP_URL: http://falkordb-mcp:8080/mcp
      OPENCONNECTOR_URL: http://open-connector:3000
    extra_hosts: ["host.docker.internal:host-gateway"]   # reach example environments on the host
    depends_on: { falkordb: { condition: service_healthy } }

  web:
    build: ./web
    ports: ["3001:3000"]
    environment:
      NEXT_PUBLIC_API_URL: http://localhost:8000/api/v1
    depends_on: [api]

  open-connector:
    image: ${OPENCONNECTOR_IMAGE}
    ports: ["3000:3000"]
    env_file: .env.openconnector

volumes:
  falkordb_data:
```

**Startup order:** `falkordb` (healthy) → `falkordb-mcp`, `api` → `web`. `api` runs the seed step (indexes, runbooks,
owners) on startup; every statement in it is idempotent (`MERGE`, `CREATE INDEX` guarded).

---

## 6. Non-functional requirements: how each is met

| NFR | Design response |
|---|---|
| N1 < 60 s diagnosis | Window snapshot instead of continuous anomaly detection; investigators in parallel; LLM calls only after the verdict |
| N2 < 200 ms queries | Hop limit 6; operation-level graph ([ADR 0006](docs/adr/0006-operation-level-aggregation.md)); indexes on every lookup key; `Anomaly` filtered by `incident` index first |
| N3 determinism | Deterministic detectors, fixed weights, tie-break on id, sorted iteration; LLM output never read by the scorer |
| N4 production safety | Adapters use read-only APIs; responder actions are posted as proposals |
| N5 laptop footprint | FalkorDB < 1 GB; one API process; OTel Demo is the only heavy part and is optional |
| N6 explainability | `Explanation.cites` must reference `Evidence` ids; Jev gate drops claims under 0.7 |
| N7 LLM-free verdict | Verdict = scorer output; narrator has a template fallback |

---

## 7. Failure modes

| Failure | Detected by | Behaviour | User sees |
|---|---|---|---|
| FalkorDB down | health check, connection error | API returns `503 GRAPH_UNAVAILABLE`; ingest skips the tick and retries | Red banner "graph offline" |
| Telemetry source down | adapter timeout (5 s) | Incident continues with the signals it has; `Incident.gaps` lists missing sources | "Traces unavailable for this window" |
| OpenRouter down / timeout | HTTP error, 20 s timeout | Template explanation from `score_parts`; verdict unchanged | "AI explanation unavailable" badge |
| Jev down | HTTP error | Keep cited claims, mark them `unverified` | "Claims not verified" badge |
| OpenConnector down | HTTP error | `Action.delivery = failed`; retry button | Retry button on the card |
| Agent crash mid-incident | LangGraph exception | Incident stays `diagnosing`; `POST /incidents/{id}/diagnose` resumes. The graph already holds what finished | Resume button |
| Duplicate alerts (storm) | `MERGE` on alert id + 10-min window per symptom | Joins the open incident | One incident, alert count goes up |
| Query too slow | FalkorDB `TIMEOUT_MAX` 30 s; app-side 5 s per query | Hypothesis marked `inconclusive` | Grey branch on the canvas |

---

## 8. Bottlenecks and how they're handled

| Bottleneck | Why | Handling |
|---|---|---|
| Variable-length paths `[:CALLS*1..6]` | Path count grows fast with fan-out | Hop limit, start from the indexed symptom, filter by `Anomaly.incident` early, aggregate to operations |
| Writes to one graph | FalkorDB serializes writes per graph | Writes are small (one hypothesis' evidence at a time); reads run in parallel on `THREAD_COUNT` threads |
| PageRank on the whole env graph | Unnecessary work, and blame should only flow among anomalous ops | Copy only anomalous ops + the calls among them into `scratch:<incident>` (tens of nodes) |
| SSE fan-out | Many browser tabs | In-process broadcaster; one event per graph write; 1 demo audience, so no broker needed |
| LLM latency | 2–10 s per call | Only after the verdict; claims verified in parallel |

---

## 9. Security

| Concern | Control |
|---|---|
| DB access | `requirepass`; FalkorDB not exposed beyond localhost in the demo; password from `.env` |
| Cypher injection | All queries parameterized (`$param`); agents can't send Cypher to the write path |
| Agent overreach | LLM agents call typed tools only; free-form Cypher goes through `falkordb-mcp` with `FALKORDB_DEFAULT_READONLY=true` + `MCP_API_KEY` |
| Prompt injection via telemetry (log lines are untrusted text) | Log text reaches the LLM only inside evidence fields marked as data; tools are read-only; the verdict doesn't depend on the LLM |
| Secrets | Never written to the graph; `.env` git-ignored; OpenConnector holds OAuth tokens |
| Web | CORS restricted to the web origin; no auth for the local demo, API key header if deployed ([docs/API.md](docs/API.md)) |
| Tenancy | One graph per environment; tool calls are bound to the incident's environment |

---

## 10. Observability of GraphRCA itself

- Structured JSON logs per agent step: `incident_id`, `agent`, `tool`, `query_id`, `duration_ms`, `rows`.
- Query timings for Q1–Q5 are exported on `GET /api/v1/health` (last p50 / p95) so N2 is visible during the demo.
- Every LLM call records model id, token counts and latency on the `Explanation` node (`ai_calls` property).

---

## 11. Technology choices

| Concern | Choice | Why |
|---|---|---|
| Graph DB | FalkorDB | Native graph + vector + full-text, multi-graph, built-in algorithms, MCP server ([ADR 0001](docs/adr/0001-falkordb-primary-store.md)) |
| API | FastAPI | Async, SSE, typed models; matches the team's stack |
| Agents | LangGraph | Fixed graph of steps with parallel fan-out; checkpoints for resume |
| LLM access | OpenRouter (LLM + Jev) | One key, pinned model ids |
| Delivery | OpenConnector | Slack / Linear OAuth handled for us |
| Anomaly detection | numpy + `ruptures` (PELT) + Drain3 | Deterministic, light |
| UI | Next.js + Tailwind + shadcn + React Flow | Team's stack; React Flow handles a few hundred nodes |
