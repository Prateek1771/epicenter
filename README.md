# Epicenter

**Find where every outage started.**

*An epicenter is the point where a quake starts and the shockwave spreads out from. When production breaks, Epicenter
finds that point and shows how the failure spread.*

Epicenter keeps a live FalkorDB graph of your production system. When an alert fires, it searches the graph upstream
from the alert for the root cause. Several agents work the incident together through that same graph. Epicenter
remembers every incident and what fixed it, and every answer comes with the graph path behind it.

Its key feature is the **Fault Simulator**. For every suspect it asks: *"if this were the cause, what would we see?"*
It predicts which operations should break and in what order, compares that with what actually broke, and scores the
match ("explains 6 of 7 symptoms"). The same check finds a second, independent fault when there is one, and says
"no root cause" when nothing in the graph explains the alert. It can also answer "what breaks if X fails?" before you
ship a change.

Built for **Graph Hacks: Context for AI Agents** (FalkorDB). Tracks: 01 (main), 02, 03 (light).

> Status: design docs only. Code starts at hackathon kickoff. Commands below are the target workflow.

## How it works

1. **Map:** traces are rolled up every 30 s into a graph of services, operations and who calls whom. Deploys, flag flips
   and config changes are added as they happen.
2. **Alert:** Epicenter opens an incident and reads a short window of metrics, traces and logs from your existing tools
   (plus a 6-hour lookback for slow leaks). Only the findings go into the graph.
3. **Search:** every operation upstream of the alert that misbehaved becomes a suspect. Agents check each one in
   parallel: did it go bad first, is it slow itself, did something change right before?
4. **Simulate:** the Fault Simulator predicts each suspect's footprint and checks it against what actually broke.
5. **Answer:** a deterministic score picks the root cause. Past similar incidents and their fixes are recalled, an AI
   explanation cites the evidence (unsupported claims are dropped), and the result goes to Slack / Linear.

Details: [ARCHITECTURE](docs/ARCHITECTURE.md).

## Why Epicenter

- **The graph does the reasoning.** Suspects, evidence, memory and agent handoffs all live in FalkorDB, and the same
  input always gives the same answer.
- **It explains the whole pattern, not the loudest symptom.** Fixating on the most visible symptom is the most common way
  AI SRE agents get it wrong.
- **It doesn't invent a cause.** When nothing fits, it says so.

How others do it: [competitors](docs/COMPETITORS.md) · [technical research](docs/TECH_RESEARCH.md).

## Docs

[Implementation phases](docs/phases/) · [ARCHITECTURE](docs/ARCHITECTURE.md) · [HLD](docs/HLD.md) · [LLD](docs/LLD.md) · [User flows](docs/USER_FLOW.md) ·
[API](docs/API.md) · [Graph schema](docs/GRAPH_SCHEMA.md) · [Example runs](docs/EXAMPLE_RUNS.md) ·
[ADRs 0001–0011](docs/adr/) · [Competitors](docs/COMPETITORS.md) · [Technical research](docs/TECH_RESEARCH.md) ·
[Planning notes](docs/planning/)

---

## 1. Prerequisites

| Need | Why |
|---|---|
| Docker Desktop (WSL2 backend on Windows), Compose v2 | FalkorDB and the app run in containers |
| 8 GB RAM free (16 GB with the OTel Demo) | The OTel Demo alone needs about 6 GB |
| OpenRouter API key | Explanations and Jev verification (optional: the verdict works without it) |
| OpenConnector + Slack / Linear OAuth | Delivery (optional) |
| Free ports: 6380, 3002, 8081, 8000, 3001, 3000 | See [HLD §5.1](docs/HLD.md#51-ports) |

## 2. Configure

```bash
cd graph-hacks
cp .env.example .env
```

```env
FALKORDB_TAG=            # pin after the first pull, e.g. the tag shown by `docker image ls falkordb/falkordb`
FALKORDB_MCP_TAG=
FALKORDB_PASSWORD=change-me
MCP_API_KEY=change-me
OPENROUTER_API_KEY=
LLM_MODEL=               # pinned OpenRouter model id
JEV_MODEL=typesafe/jev-1.13
OPENCONNECTOR_IMAGE=
OPENCONNECTOR_API_KEY=
ENV_NAME=astronomy-shop  # or flip-commerce / rcaeval-tt
```

## 3. Start

```bash
docker compose up -d falkordb
docker compose exec falkordb redis-cli -a "$FALKORDB_PASSWORD" PING     # → PONG
docker compose up -d                                                    # falkordb-mcp, api, web, open-connector
```

| URL | What |
|---|---|
| http://localhost:3001 | Epicenter UI |
| http://localhost:8000/docs | API (Swagger) |
| http://localhost:3002 | FalkorDB browser (connect to host `falkordb`, port 6379 from inside Docker, or `localhost:6380` from the host) |

The API seeds indexes, owners and runbooks on startup. Every seed statement is idempotent.

## 4. Check persistence (first run only)

The FalkorDB docs show two data paths. Find the real one and fix the volume in `docker-compose.yml` if needed:

```bash
docker compose exec falkordb sh -c 'ls -la /data /var/lib/falkordb/data 2>/dev/null'
docker compose exec falkordb redis-cli -a "$FALKORDB_PASSWORD" GRAPH.QUERY env:smoke "CREATE (:Service {name:'x'})"
docker compose restart falkordb
docker compose exec falkordb redis-cli -a "$FALKORDB_PASSWORD" GRAPH.QUERY env:smoke "MATCH (s:Service) RETURN s.name"   # → x
docker compose exec falkordb redis-cli -a "$FALKORDB_PASSWORD" GRAPH.DELETE env:smoke
```

## 5. Smoke test

```bash
docker compose exec api python -m api.smoke_falkordb
```

It checks the FalkorDB features the design depends on, on your pinned tag: variable-length paths with filters, the Q2
query shape, `algo.pageRank`, vector index + `vecf32`, full-text index, and two parallel writers.
If something fails, fix the query in [LLD §2](docs/LLD.md#2-graphpy) before building on it.

## 6. Run an example

**Fastest (no extra containers): RCAEval replay**
```bash
docker compose exec api python -m api.ingest.rcaeval --case re2tt_ts-auth-service_cpu_2 --env rcaeval-tt --download
```
Then open http://localhost:3001 and the new incident.

**OTel Demo (multi-hop)** and **flip-commerce (your system-design-journey, real Mongo failover)**: see
[docs/EXAMPLE_RUNS.md](docs/EXAMPLE_RUNS.md). Run one example environment at a time; both want port 8080.

## 7. Evaluate

```bash
docker compose exec api python -m api.eval --suite re2 --system tt
```
Prints AC@1 / AC@3 and the ablations (no PageRank, no temporal rule, no mechanism rule, no Fault Simulator footprint).

## 8. Troubleshooting

| Symptom | Fix |
|---|---|
| `bind: address already in use` on 6380 / 3002 / 8081 | Something else uses the port; change the host side in `docker-compose.yml` and in `.env` |
| flip-commerce Redis won't start | It needs 6379; Epicenter uses 6380 on the host, so check nothing else holds 6379 |
| OTel Demo and flip-commerce both fail on 8080 | Run only one example environment at a time |
| Graph is empty after restart | Volume path wrong; see §4 |
| `NOAUTH Authentication required` | Pass `-a "$FALKORDB_PASSWORD"` / set it in the browser login |
| `api` can't reach Jaeger / Prometheus | They run on the host: URLs must use `host.docker.internal` (already set in compose) |
| Explanation says "AI explanation unavailable" | `OPENROUTER_API_KEY` missing or OpenRouter down; the verdict is still valid |

## 9. Reset

```bash
docker compose down -v      # removes containers and the FalkorDB volume (all graphs)
```

## License note

FalkorDB is SSPLv1 (source available). This project uses it unmodified via the official Docker image.
