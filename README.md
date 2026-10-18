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

Built for **Graph Hacks: Context for AI Agents** (FalkorDB), **Track 01: Agents That Act on Connected Data**. Incident
memory (similar past incidents and their fixes) is a supporting feature.

> Status: built and demo-ready (phases 0–12). Runs locally with Docker Compose.

**Demo video:** _add the link before submitting_ · **Recording script:** [docs/DEMO_SCRIPT.md](docs/DEMO_SCRIPT.md)

## Quick start (10 minutes, any laptop)

You need Docker Desktop (Compose v2) and ports 6380, 3002, 8081, 8000, 3001 and 3000 free.

```bash
git clone https://github.com/Prateek1771/epicenter.git && cd epicenter
cp .env.example .env            # PowerShell: Copy-Item .env.example .env
```

In `.env`, set `FALKORDB_PASSWORD` and `MCP_API_KEY` to any long random strings (`openssl rand -hex 24`). Nothing
else is required.

```bash
docker compose up -d            # first build ~5 min
docker compose ps               # wait until api and falkordb are "healthy"
```

1. Open **http://localhost:3001/incidents** and press **Run a sample incident**. The samples ship with the repo in
   [`examples/samples/`](examples/samples/): 26 generated incidents, each with a known answer, at three sizes (5, 30
   and 300 services). That's ~140 MB of the clone, so there is nothing to download or generate.
2. Within a few seconds the incident page shows the verdict, the graph path from the alert to the root cause, every
   suspect the Fault Simulator confirmed or refuted, and the evidence.
3. Open **http://localhost:3001/runs** for every sample: small, medium and huge. Each card says whether the verdict
   matched the expected answer. Try `loud-victim`: the loudest service is refuted and the quiet datastore behind it is
   blamed.
4. Optional:
   - add `OPENROUTER_API_KEY` for AI-written explanations (without it you get a template explanation; the verdict
     never depends on the LLM);
   - the medium demo is recorded benchmark faults and the real-world demo is a live microservice shop: see
     [docs/SETUP.md §5](docs/SETUP.md#5-the-three-demos).

Tests run inside the container: `docker compose exec api pytest`.

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

## What's in the app

| Screen | What it does |
|---|---|
| `/` | Landing page |
| `/incidents`, `/incident/{id}` | Live incident list. The incident page shows the verdict, the graph path, timeline lanes and evidence. A collapsible right panel holds suspects, the timeline, notes and an AI chat scoped to the incident. Deliver to Slack / Linear from the header. Download `incident_info.md` for people or an agent context file for Claude Code / Codex / Cursor |
| `/map` | The service map, with three views: **Layers** (layered call graph), **Network** (a force-directed view of every node and relationship, like the FalkorDB browser) and **Data** (tables). Double-click a node to expand its neighbours |
| `/blast-radius` | A dossier for one service: what a failure reaches (by hop), who to page, incidents rooted there, changes in the last 7 days, runbooks and inbound traffic. With no service picked, it lists the riskiest services |
| `/simulate` | The **What-if lab**. It runs the Fault Simulator for all six fault kinds side by side, shows a spread timeline (when each team is hit), checks "did it happen before?" against past incidents, shows the rules behind each predicted hop, and keeps saved experiments |
| `/ask` | A chat over the graph: history (stored in FalkorDB), text-file attachments, an env or incident scope and a quick wiki rail. Every answer shows its graph path |
| `/runs` | Start demo scenarios and live faults |
| `/eval` | Benchmark analysis: run history, ablation deltas, accuracy by fault, confidence calibration, synthetic scale test, where misses go, time to verdict and a per-case drill-down |

Every screen works at phone width.

## Graph model and queries

FalkorDB is the system of record: there is one graph per environment (`env:<name>`), a scratch graph per incident for
PageRank, and `kb:propagation` for the Fault Simulator's rules. Take FalkorDB out and nothing works: search,
evidence, scoring input, memory and agent hand-offs are all graph reads and writes.

- **Topology:** `(:Service)-[:HAS_OP]->(:Operation)-[:CALLS {rps, err_rate, p95_ms}]->(:Operation)`, rolled up
  from traces. `(:Change)-[:CHANGED]->(:Service)`, `(:Service)-[:OWNED_BY]->(:Team)`, `(:Person)-[:MEMBER_OF]->(:Team)`.
- **Incident:** `(:Incident)-[:HAS_HYPOTHESIS]->(:Hypothesis)-[:BLAMES]->(:Operation)`, with
  `-[:SUPPORTED_BY|REFUTED_BY]->(:Evidence)`, `(:Anomaly)-[:ON]->(:Operation)` and `(:Incident)-[:ROOT_CAUSE]->(:Hypothesis)`.
- **Memory:** `Incident.signature`, a 64-dimension vector in a vector index, plus `(:Incident)-[:RESOLVED_BY]->(:Action)`.

Full schema: [docs/GRAPH_SCHEMA.md](docs/GRAPH_SCHEMA.md).

The queries the product depends on all live in one dictionary, [`api/graph.py`](api/graph.py) `QUERIES`. They are
parameterized and bounded at 6 hops. Documented in [LLD §2](docs/LLD.md#2-graphpy):

| Query | What it does |
|---|---|
| `Q1` | Suspects: every operation the alerting one depends on, up to 6 `CALLS` hops away, that has an anomaly in this incident, ordered by onset |
| `Q2` | The path from the alert to a suspect, with each hop's onset (did it go bad first?) |
| `Q3` / `Q3b` | A suspect's own anomalies (self-time vs. child-time) and the changes on its service just before onset; for a datastore, its callers' wait split |
| `Q4a` → `Q4_blame` → `Q4b` | Builds a `BLAME` projection of the anomalous call graph in `scratch:<incident>`, then runs `algo.pageRank` on it |
| `Q5` | Memory: `db.idx.vector.queryNodes` on incident signatures, giving similar resolved incidents and the actions that fixed them |
| `Q6` | Fault Simulator: every caller path with live traffic into a suspect, which the propagation rules turn into a predicted footprint |
| `explore` | The `/map` Network view: every label and relationship, bounded |

Graph algorithms used: bounded variable-length path search, `algo.pageRank` on a per-incident projection, and a vector
index for memory. Agents query the graph through typed tools; free-form Cypher only goes through the read-only
`falkordb-mcp`.

## Why Epicenter

- **The graph does the reasoning.** Suspects, evidence, memory and agent handoffs all live in FalkorDB, and the same
  input always gives the same answer.
- **It explains the whole pattern, not the loudest symptom.** Fixating on the most visible symptom is the most common way
  AI SRE agents get it wrong.
- **It doesn't invent a cause.** When nothing fits, it says so.

How others do it: [competitors](docs/COMPETITORS.md) · [technical research](docs/TECH_RESEARCH.md).

## Docs

**Judges and evaluators:** the [quick start](#quick-start-10-minutes-any-laptop) above is enough to see it work.
[docs/SETUP.md](docs/SETUP.md) goes further: `python syscheck.py` sizes your machine, then it walks you through three
demos. **Small** uses the committed synthetic samples (known answers, any laptop). **Medium** uses real recorded
faults from the RCAEval benchmark, downloaded per case. **Real-world** is live faults in the OpenTelemetry Demo shop,
which `run.py up` fetches. The hosted deployment is planned and scripted, not run for the event:
[docs/DEPLOYMENT_PLAN.md](docs/DEPLOYMENT_PLAN.md).

What's where:

| Path | What |
|---|---|
| `api/` | FastAPI app: `graph.py` (every Cypher query), `ingest/`, `search/` (causal search, scoring, Fault Simulator), `agents/`, `tools/` (typed tools + MCP), `routes/` |
| `web/` | Next.js UI |
| `examples/samples/` | The 26 committed synthetic incidents (Demo 1) |
| `examples/otel-demo/` | Epicenter's layer over the OpenTelemetry Demo (Demo 3); the demo itself is fetched |
| `examples/synthetic/gen.py` | The sample generator (deterministic) |
| `seed/` | Owners, runbooks, propagation rules |
| `weights.json` | The frozen scoring weights |
| `tests/` | pytest suite, run inside the api container |

[Setup guide](docs/SETUP.md) · [Demo script](docs/DEMO_SCRIPT.md) · [Implementation phases](docs/phases/) · [ARCHITECTURE](docs/ARCHITECTURE.md) · [HLD](docs/HLD.md) · [LLD](docs/LLD.md) · [User flows](docs/USER_FLOW.md) ·
[API](docs/API.md) · [Graph schema](docs/GRAPH_SCHEMA.md) · [Example runs](docs/EXAMPLE_RUNS.md) ·
[Deployment plan](docs/DEPLOYMENT_PLAN.md) · [ADRs 0001–0014](docs/adr/) · [Competitors](docs/COMPETITORS.md) · [Technical research](docs/TECH_RESEARCH.md) ·
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
cp .env.example .env
```

| Key | Required | Set to |
|---|---|---|
| `FALKORDB_PASSWORD`, `MCP_API_KEY` | yes | any long random strings (`openssl rand -hex 24`) |
| `OPENROUTER_API_KEY` | no | AI-written explanations and Jev claim checks; without it a template explanation is shown |
| `FAULT_RUNNER_TOKEN` | live demos only | a long random string (the host fault runner checks it) |
| `OPENCONNECTOR_API_KEY`, `SLACK_CHANNEL`, `LINEAR_TEAM_ID` | no | Slack / Linear delivery |
| image tags (`FALKORDB_TAG`, …) | yes | keep the pinned values from `.env.example` |

`.env` is git-ignored; never commit it.

## 3. Start

```bash
docker compose up -d falkordb
docker compose exec falkordb redis-cli -a "$FALKORDB_PASSWORD" PING     # → PONG
docker compose up -d                                                    # falkordb-mcp, api, web, open-connector
```

| URL | What |
|---|---|
| http://localhost:3001 | Epicenter landing page; the app starts at `/incidents` |
| http://localhost:8000/docs | API (Swagger) |
| http://localhost:3002 | FalkorDB browser (connect to host `falkordb`, port 6379 from inside Docker, or `localhost:6380` from the host) |

The API seeds indexes, owners and runbooks on startup. Every seed statement is idempotent.

Web development (hot reload against the API on :8000; stop the `web` container first, it owns port 3001):

```bash
docker compose stop web
cd web && npm ci
npm run dev -- -p 3001     # http://localhost:3001
npm run gen:api            # regenerate lib/api-types.ts after an API change (API must be up)
npm test                   # reducer + layout unit tests (node:test)
npm run lint && npm run build
```

Landing illustrations are optional: drop `web/public/landing/<name>.webp` files in (hero-poster, where-you-are,
philosophy, agent-triage, agent-investigator, agent-skeptic, agent-historian, what-it-does, science, run-it) and rebuild
the `web` container. Missing images fall back to the built-in artwork.

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

**Demo 1, synthetic (committed, nothing to download):** `/runs` → *Demo 1 · Synthetic*, or from the command line:
```bash
docker compose exec api python -m api.ingest.rcaeval --case synth-small_mongodb_loud-victim_1 --env synthetic
```

**Demo 2, RCAEval replay (real recorded faults, ~25 MB per case):**
```bash
docker compose exec api python -m api.ingest.rcaeval --case re2tt_ts-auth-service_cpu_2 --env rcaeval-tt --download
```

**Demo 3, OpenTelemetry Demo (live microservice shop, 8 CPU / 16 GB):** `python examples/otel-demo/run.py up`, which
clones the pinned demo on first use. Let it warm up for 25 minutes, then start faults from `/runs`. See
[examples/otel-demo/README.md](examples/otel-demo/README.md).

Then open http://localhost:3001/incidents and the new incident. Expected verdicts per demo: [SETUP §5](docs/SETUP.md#5-the-three-demos).

## 7. Evaluate

```bash
docker compose exec api python -m api.eval --suite re2 --system tt
```
Prints AC@1 / AC@3 and the ablations (no PageRank, no temporal rule, no mechanism rule, no Fault Simulator footprint).
`--download` fetches missing cases (~1.9 GB for all 90); one run takes ~35 min. Results land in
`data/eval/<n>-re2-tt-<weights>-<rules>.json` (numbered, kept) and on the `/eval` page.

### Results (measured 2026-10-17)

RCAEval RE2-TT, all 90 cases, frozen weights `2026-10-17.v5`, rules `2026-10-16`, engine only (no LLM). A hit means
the verdict's root-cause operation is in the labelled service; `no_root_cause` counts as a miss.

| | Cases | AC@1 | AC@3 |
|---|---|---|---|
| **Held-out** (rep 3, never tuned on) | 30 | **90.0%** | 90.0% |
| Dev (reps 1–2, weights tuned here) | 60 | 86.7% | 88.3% |
| All | 90 | 87.8% | 88.9% |
| Before tuning (v3 weights), all / held-out | 90 / 30 | 61.1% / 66.7% | 87.8% / 90.0% |

The ablations (all 90 cases, v5), losses included:

| Variant | AC@1 | AC@3 | Reading |
|---|---|---|---|
| full | 87.8% | 88.9% | |
| no PageRank | 76.7% | 85.6% | The biggest single contributor |
| no mechanism rule | 83.3% | 94.4% | Helps at @1; at @3 the victim refutes cost some runner-ups |
| no Fault Simulator footprint (v1) | 83.3% | 88.9% | +4.5 points at @1 |
| no temporal rule | **92.2%** | **95.6%** | **Better without it on RE2-TT.** Kept, because the live scenarios (a flag or a deploy before the effect) depend on onset order; noted as a known loss |

By fault (AC@1): cpu 100%, delay 100%, socket 93.3%, disk 86.7%, loss 73.3%, mem 73.3%.

Memory recall (leave-one-out precision@3, same service and fault): 12.2% (13.0% before the slow-burn fix, below). The signature describes the *shape* of an
incident (kinds, hops, service kind), and many RE2-TT services fail in the same shape. Recall is a weak point.

Determinism: two full runs give byte-identical result files (`cmp`).

Re-measured after the slow-burn fix (run `0008`: the pass now fetches its own 6 h of metrics): AC@1 / AC@3 and every
ablation unchanged; one verdict, already a miss, moved to another service.

Synthetic samples, reported apart (seed 1, `api.eval --suite synth`): small 8/8, medium 7/9, huge 5/9 AC@1; misses
and their causes in [EXAMPLE_RUNS §4](docs/EXAMPLE_RUNS.md#4-synthetic-samples-self-made).

**Latency** (targets from [ARCHITECTURE §1.2](docs/ARCHITECTURE.md#12-non-functional)):

| | Measured | Target |
|---|---|---|
| N1 alert → verdict, RCAEval replay (ingest 24 min of telemetry + diagnose) | p50 10.3 s, p95 15.4 s, max 21.0 s | < 60 s ✓ |
| N1 diagnosis only, RCAEval | p50 263 ms, p95 534 ms | |
| N1 diagnosis (agent flow), the 11 recorded live incidents (OTel Demo, flip-commerce) | 178–843 ms | < 60 s ✓ |
| N2 p95 per query, live API (Q1, Q2, Q3, Q3b, Q4a / Q4_blame / Q4b, Q5) | 8.4, 10.0, 11.4, 7.7, 6.1 / 4.1 / 7.3, 52.0 ms | < 200 ms ✓ |

For a live run, alert → verdict also includes the `settle_s` wait (by design, 60–90 s after the fault) and the ingest
from Jaeger / Prometheus. The verdict lands within about a second of the ingest.

How the weights were frozen:
- v4 came from a grid on the dev split only.
- v5 then raised `change_match`, which RCAEval can't tune because it has no change events, after v4 flipped one live
  flip-commerce verdict. It scales the rest uniformly, so the RE2-TT numbers are identical to v4's.

The reasoning is in [LLD §6.3](docs/LLD.md#63-weightsjson).

## 7b. Test reports

Every `pytest` run writes `data/reports/<n>-<utc>/findings.md` (what passed, failed, timings) and
`agent-context.md` (a guide you can hand to Claude Code, Codex or Cursor: per failure, the spec section, the code under
test and the exact rerun command). `cd web && npm test` appends the web results to the newest report. Reports are
numbered and kept; `pytest --no-report` skips writing one.

## 8. Troubleshooting

| Symptom | Fix |
|---|---|
| `bind: address already in use` on 6380 / 3002 / 8081 | Something else uses the port; change the host side in `docker-compose.yml` and in `.env` |
| `/runs` shows no synthetic samples | `examples/samples/` is missing from the clone (a sparse or partial checkout); `git checkout -- examples/samples` |
| OTel Demo fails on 8080 / 4317 | Another example environment holds the port; run one at a time |
| The first OTel fault blames the wrong service | The demo is still cold: wait 25 minutes after `run.py up` |
| Graph is empty after restart | Volume path wrong; see §4 |
| `NOAUTH Authentication required` | Pass `-a "$FALKORDB_PASSWORD"` / set it in the browser login |
| `api` can't reach Jaeger / Prometheus | They run on the host: URLs must use `host.docker.internal` (already set in compose) |
| Explanation says "AI explanation unavailable" | `OPENROUTER_API_KEY` missing or OpenRouter down; the verdict is still valid |

## 9. Reset

```bash
docker compose down -v      # removes containers and the FalkorDB volume (all graphs)
```

## License note

FalkorDB is SSPLv1 (source available); this project uses it unmodified via the official Docker image. The
OpenTelemetry Demo (Apache-2.0) is fetched at run time, not redistributed. RCAEval cases are downloaded from the
benchmark's public dataset on demand. The synthetic samples in `examples/samples/` are generated by this repo.
