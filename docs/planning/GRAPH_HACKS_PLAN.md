# Graph Hacks (FalkorDB): outage diagnosis where the graph *is* the reasoning

Focus: only the FalkorDB "Graph Hacks: Context for AI Agents" hackathon. Same problem as EvidenceRCA
(diagnose an outage: what broke, where, why, what to do), rebuilt so that FalkorDB is the core and not an add-on.

**Full design:** [`graph-hacks/ARCHITECTURE.md`](../../ARCHITECTURE.md) · **FalkorDB Docker setup:** [`FALKORDB_PLAN.md`](FALKORDB_PLAN.md) ·
**Deep dive:** [`FALKORDB_BRAINSTORM.md`](FALKORDB_BRAINSTORM.md). Working name: **GraphRCA**.

## 0. Rules to check first (from a similar FalkorDB / WeMakeDevs hackathon; confirm for this one)
- FalkorDB must be the **primary** database and central to the product. A graph used only for visualization does not
  count; the product must **not work** with FalkorDB removed.
- Data must be public, synthetic or self-owned. RCAEval and the OpenTelemetry Demo are both fine.
- Main coding must start **after** the hackathon begins. Our repo has only docs so far, which is fine; write no product code before kickoff.
- Deliverables: repo, README, demo video, deployment, project info.

## 1. What the money-printers do (and what we copy)
| Company | Core idea | What we take |
|---|---|---|
| **Traversal** ($48M, Kleiner + Sequoia) | "Production World Model": live causal graph of services, deps, deploys, configs, telemetry, code, past incidents (1.7M+ nodes, 30 node types). "Causal Search Engine": a candidate cause must be **upstream** of the symptom in the graph, must have **changed before** the symptom, and the **mechanism must fit**. Thousands of hypotheses run in parallel and get pruned | This is literally a graph query. We build the same thing on FalkorDB, in the open |
| **Resolve AI** ($1B valuation) | Always-current knowledge graph of production; a planner agent hands work to sub-agents that test hypotheses; read-only access; can revert commits / open PRs within guardrails | Planner + sub-agents that share state **through the graph** |
| **HolmesGPT** (CNCF sandbox, OSS) | Agent decides which telemetry to fetch, iterates on hypotheses | No graph: it re-fetches and re-stitches every time. That's our contrast |
| **Coroot** (OSS) | eBPF service map; AI RCA follows the dependency graph from the affected service | Proves graph-walk RCA works; their AI is paid / cloud only |

**Our pitch:** *"Traversal's causal search, open and explainable, on FalkorDB. Every diagnosis is a path in the graph you can click, rerun and argue with."*

## 2. The graph (Production World Model, hackathon size)
One graph per tenant/environment (`env:astronomy-shop`, `env:rcaeval-tt`), using FalkorDB multi-graph.

**Nodes:** `Service`, `Operation`, `Pod`, `Node`, `Deploy`, `ConfigChange`/`FeatureFlag`, `Metric`, `LogTemplate`, `Anomaly`,
`Incident`, `Hypothesis`, `Evidence`, `Finding`, `Action`, `Team`, `Person`, `Runbook`.

**Edges:**
- Topology: `(Operation)-[:CALLS {p95, err_rate, rps}]->(Operation)`, `(Operation)-[:OF]->(Service)`, `(Service)-[:RUNS_ON]->(Pod)-[:ON]->(Node)`
- Change: `(Deploy|ConfigChange|FeatureFlag)-[:CHANGED {ts}]->(Service)`
- Signal: `(Anomaly {onset, score, kind})-[:ON]->(Operation|Pod)`, `(Anomaly)-[:SEEN_IN]->(Metric|LogTemplate)`
- Investigation: `(Incident)-[:HAS_HYPOTHESIS]->(Hypothesis)-[:BLAMES]->(Service|Change)`, `(Hypothesis)-[:SUPPORTED_BY|REFUTED_BY]->(Evidence)`
- Memory: `(Incident)-[:ROOT_CAUSE]->(...)`, `(Incident)-[:RESOLVED_BY]->(Action)`, `(Incident)-[:SIMILAR_TO {score}]->(Incident)`
- People: `(Service)-[:OWNED_BY]->(Team)`, `(Person)-[:FIXED]->(Incident)`, `(Person)-[:AUTHORED]->(Deploy)`

Ingestion is deterministic code (OTel traces/metrics/logs, k8s, deploy log, flagd events). No LLM writes topology.

## 3. Causal search = Cypher (the core; Track 01)
For a symptom (alerting operation), generate hypotheses and prune them, Traversal-style:

```cypher
// 1. Upstream candidates: anything the symptom depends on, up to 6 hops
MATCH p = (sym:Operation {id:$symptom})-[:CALLS*0..6]->(cand:Operation)
// 2. Temporal rule: candidate went bad before (or with) the symptom
MATCH (a:Anomaly)-[:ON]->(cand)
WHERE a.onset <= $symptom_onset
// 3. Every hop on the path must also be anomalous in time order (propagation consistency)
WITH p, cand, a
WHERE all(i IN range(0, length(p)-2) WHERE
      nodes(p)[i+1].onset <= nodes(p)[i].onset)
// 4. Look for a change that explains it
OPTIONAL MATCH (ch)-[c:CHANGED]->(:Service)<-[:OF]-(cand)
WHERE c.ts <= a.onset AND c.ts >= a.onset - $lookback
RETURN cand, a, p, collect(ch) AS changes
```

Then deterministic scoring per hypothesis: onset earliness + anomaly strength + **self-time vs child-time**
(is the candidate slow itself, or only because its own callee is slow?) + change match + Personalized PageRank on the
anomaly-weighted reverse call graph (`algo.pageRank`, check the exact name). Each surviving hypothesis is written back as a
`Hypothesis` node with `SUPPORTED_BY`/`REFUTED_BY` edges, so the pruning itself is visible in the graph.

The LLM never ranks. It **chooses which graph tools to call** (MCP) and **explains** the winning path.

## 4. Agents that share state through the graph (Track 02)
LangGraph planner + sub-agents. They don't pass big blobs to each other; they read and write the `Incident` subgraph.

| Agent | Reads | Writes |
|---|---|---|
| **Triage** | alert, `OWNED_BY`, blast radius (`CALLS*` reverse) | `Incident`, severity |
| **Investigator** (×N, one per hypothesis branch, in parallel) | causal-search tools | `Hypothesis` + `Evidence` edges |
| **Skeptic** | each hypothesis + its evidence | `REFUTED_BY` edges; tries "why not X?" |
| **Historian** | `Incident -[:SIMILAR_TO]-` past incidents (vector index on incident signature + graph overlap) | links to past fixes |
| **Responder** | winning hypothesis + `Runbook` + past `RESOLVED_BY` | `Action` proposals; posts via OpenConnector (Slack/Linear) |

- **Persistent memory:** every resolved incident stays in the graph. Next week's incident finds it via `SIMILAR_TO`.
- **Concurrency:** investigators write in parallel to the same incident graph. Show this in the UI as a live graph growing.
- **Per-tenant:** one FalkorDB graph per environment/customer.
- Memory types: episodic = `Incident` history; semantic = topology + ownership; procedural = `Runbook` + `RESOLVED_BY` success counts.

## 5. Company-brain slice (Track 03, light)
"Who should I page?" `(Service)-[:OWNED_BY]->(Team)`, `(Person)-[:FIXED]->(Incident)-[:ROOT_CAUSE]->(Service)`,
`(Person)-[:AUTHORED]->(Deploy)`. Answers come with sources (the deploy, the past incident).
Data: synthetic owners/teams yaml + git log of the OTel demo repo (public).

## 6. MCP graph tools (what the agent can call)
`blast_radius(service)`, `upstream_candidates(op, hops)`, `explain_path(a, b)`, `why_not(service)`,
`recent_changes(service, window)`, `similar_incidents(incident)`, `who_knows(service)`, `cypher_readonly(query)` (guarded).
Expose them through our own small MCP server (Python), backed by the `falkordb` client. Also run FalkorDB's official
MCP server (`falkordb/mcpserver`, HTTP on host port 8081, `FALKORDB_DEFAULT_READONLY=true`) for the "ask anything" box:
`get_graph_schema` + `query_graph_readonly`.

## 7. Data and demo
- **Live:** OpenTelemetry Demo (Astronomy Shop) on Docker. It ships Jaeger/Prometheus and **flagd fault flags**
  (e.g. `paymentFailure`, `adHighCpu`, `emailMemoryLeak`; check the names). Flip a flag → alert → agents → graph fills in → Slack card.
- **Offline / evaluation:** RCAEval RE2 (public) replayed into the same graph. Report AC@1 / AC@3 for our causal search vs
  BARO, honestly. It's a credibility number, not the headline.
- **Fallback:** a recorded run if the 6 GB demo stack won't run on the judging machine.

## 8. UI (Next.js + Tailwind + shadcn, dark-first)
- **Incident page:** verdict card; a **live graph canvas** (React Flow or Cosmograph) where hypotheses appear as branches and
  turn red or green as investigators prune them; the winning path glows.
- **"Why not X?"** box: type any service, get the refuting path.
- **Blast-radius view:** "if `cart` dies, these 7 operations break" (their example question #4).
- **Memory panel:** similar past incidents and what fixed them.
- **Ask box:** natural-language question → agent picks MCP tools → answer with the clickable path behind it.
Design references: Traversal and Resolve product pages, incident.io timeline, Datadog Watchdog card.

## 9. Stack
FalkorDB (Docker) · FastAPI + LangGraph · OpenRouter for all LLM calls (Jev for bounded choices) · OpenConnector for Slack/Linear ·
Next.js + Tailwind + shadcn · Docker Compose.

**FalkorDB runs in Docker:** image `falkordb/falkordb` (server + browser UI), pinned tag in `.env`.
Ports: server **6379**, browser UI **3002** (OpenConnector owns 3000), official MCP server **8081** (the OTel demo owns 8080),
our `graph-mcp` 8090, API 8000, web 3001. Password and AOF via `REDIS_ARGS`, threads/timeouts via `FALKORDB_ARGS`,
named volume for data. Full compose file: [`graph-hacks/ARCHITECTURE.md` §4](../../HLD.md#52-docker-composeyml).

## 10. Why this wins (and the risks)
- The graph does real work: causal search, pruning, memory, ownership and handoffs all live in it. Remove FalkorDB and nothing works, which is exactly what the rules ask for.
- It hits every "work the graph has to do" item in the brief: follow connections, remember across sessions, share state between agents, connect people and decisions, show the path.
- A recognizable, valuable story: "the open, explainable Traversal".
- **Risks:** the OTel demo needs about 6 GB of RAM (record a backup video). Cypher variable-length path performance on large span graphs (aggregate spans to operations first). Check FalkorDB's exact `algo.*` names and Cypher support for `all(...)` on paths before relying on them.

## 11. Build order
1. Ingest RCAEval TT/OB case → graph (topology + anomalies). Causal-search Cypher works on one case.
2. MCP tools + investigator/skeptic agents writing hypotheses to the graph.
3. UI: live graph canvas + verdict + "why not X?".
4. Memory (`SIMILAR_TO`, vector index) + Historian + Responder → OpenConnector Slack.
5. Live OTel demo + ownership slice + eval table + video.

## Sources
[Traversal causal search engine](https://www.traversal.com/blog/introducing-causal-search-engine-from-correlated-alerts-to-causally-consistent-diagnoses) ·
[Traversal production world model](https://www.traversal.com/glossary/production-world-model) ·
[Traversal vs Resolve](https://www.traversal.com/comparison/traversal-vs-resolve-ai) ·
[Resolve AI knowledge graph](https://resolve.ai/blog/knowledge-graph-agentic-ai-incident-response) ·
[LSVP on Resolve AI](https://lsvp.com/stories/building-the-ai-for-production-our-investment-in-resolve-ai/) ·
[HolmesGPT (CNCF)](https://www.cncf.io/blog/2026/01/07/holmesgpt-agentic-troubleshooting-built-for-the-cloud-native-era/) ·
[Coroot AI RCA](https://docs.coroot.com/ai/overview) ·
[Rootly incident knowledge graph](https://rootly.com/blog/turning-your-incident-data-into-a-knowledge-graph) ·
[FalkorDB hackathon rules (WeMakeDevs, earlier event)](https://www.wemakedevs.org/hackathons/falkordb/rules) ·
[FalkorDB algorithms](https://docs.falkordb.com/algorithms/)
