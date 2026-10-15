# FalkorDB deep dive + brainstorm (Graph Hacks only)

Focus: the FalkorDB "Graph Hacks: Context for AI Agents" hackathon. The first hackathon (RCAEval / "Diagnose the Outage")
is no longer a constraint. Result of this brainstorm: [`docs/ARCHITECTURE.md`](../ARCHITECTURE.md).

## 1. FalkorDB in one page

| Area | What it has | Why we care |
|---|---|---|
| Engine | Property graph stored as sparse adjacency matrices; traversals run as linear algebra (GraphBLAS). Successor of RedisGraph. Runs as a Redis module | Fast multi-hop queries |
| Docker | `falkordb/falkordb` (server 6379 + browser UI 3000), `falkordb/falkordb-server`, `falkordb/falkordb-browser`. Configured with `REDIS_ARGS` (password, AOF) and `FALKORDB_ARGS` (`THREAD_COUNT`, `TIMEOUT_MAX`) | One container for dev; see [`FALKORDB_PLAN.md`](FALKORDB_PLAN.md) |
| Query | OpenCypher (+ extensions), RESP and Bolt protocols, Python client `falkordb` (`query`, `ro_query`) | Same Cypher as Neo4j; LangChain has a FalkorDB wrapper |
| Indexes | Range, full-text (nodes, and edges since v4.8), **vector similarity** | Graph + text + vector search in one store. No separate vector DB |
| Algorithms | BFS, shortest paths (`SPpath`), all paths (`SSpath`), A*, MSF, **PageRank**, **betweenness**, harmonic centrality, **WCC**, **CDLP**, **MaxFlow** | PageRank on a reversed call graph is a known RCA method (MicroRank) |
| Multi-tenancy | Thousands of separate graphs in one instance | One graph per environment, plus throwaway projection graphs |
| Persistence | Redis RDB + AOF, replication | Incident memory survives restarts |
| MCP | `falkordb/mcpserver`: tools `query_graph`, `query_graph_readonly`, `get_graph_schema`, `get_node_schema`, `get_relationship_schema`; stdio or HTTP; `FALKORDB_DEFAULT_READONLY=true` | Track 01's "tool selection through MCP" out of the box |
| Agent ecosystem | **Graphiti** (Zep) temporal memory supports FalkorDB, with its own MCP server (experimental); GraphRAG-SDK; Code-Graph demo | Ready-made memory, but see idea F |

**Weak spots (be honest):**
- License is **SSPLv1** (source available, not OSI open source). Fine for a hackathon; don't call it "open source".
- Speed numbers (e.g. "496x faster") are vendor claims and don't agree with each other. Don't repeat them.
- The embedded mode is experimental. Use Docker.
- Small algorithm set next to Neo4j GDS (no Louvain, no node similarity, no personalized PageRank listed). Check exact
  `algo.*` names on the pinned version.
- The docs show two different data-volume paths (`/data` vs `/var/lib/falkordb/data`). Check on first run.

## 2. What the judges want, and what fails

The brief: "the graph has to shape what the agent does, not sit on the side." A similar FalkorDB hackathon's rules said
a graph used only for visualization doesn't count, and the product must not still work with FalkorDB removed.

So these fail:
- A 15-service topology stored in FalkorDB while the real logic is statistics in Python.
- "We also save results to a graph."
- A chat bot that writes Cypher with nothing else going on.

## 3. Ideas, ranked (Graph Hacks only)

| # | Idea | Graph does the work? | Verdict | In architecture |
|---|---|---|---|---|
| 1 | **Causal search as Cypher** (Traversal-style): candidates = upstream operations with anomalies; prune by onset order along the path, self vs child time, and changes just before onset; PageRank on a reversed projection | Yes: generation and pruning are graph queries | **Core. Build first** | §7 |
| 2 | **Agents share state through the incident subgraph**: investigators in parallel, skeptic, historian, responder all read and write `Hypothesis` / `Evidence` nodes | Yes: the graph is the coordination layer | **Core (Track 02)** | §8 |
| 3 | **"Why not X?" and blast radius** as typed MCP tools | Yes: multi-hop reverse traversals | **Core. Best demo moment** | §10 |
| 4 | **Incident memory**: deterministic signature vector + vector index + graph overlap; runbook success counts (procedural memory) | Yes: recall and update live in the graph | **Build (Track 02)** | §9 |
| 5 | **Provenance**: every explanation cites `Evidence` nodes; Jev drops unsupported claims; the UI highlights the path | Yes: the path is the answer | **Build** | §10, §12 |
| 6 | **Ownership slice**: `OWNED_BY`, `FIXED`, `AUTHORED`; "who should I page?" with sources | Yes, but light | **Build late (Track 03 touch)** | §5, §10 |
| 7 | Live **graph canvas** that grows as agents write | No by itself (visual), but it shows 1–3 working | **Build. It sells the demo** | §12 |
| 8 | **Graphiti** for memory | LLM decides what enters the graph → nondeterministic, hard to trust | **Skip** | — |
| 9 | Span-level graph (every span a node) | Too big, slow variable-length queries | **Skip**: aggregate to operations | §6 |

## 4. Positioning

| Product | Graph? | Gap we use |
|---|---|---|
| Traversal | Yes: "production world model", causal search over 1.7M nodes | Closed, enterprise-only; you can't see its search |
| Resolve AI | Yes: production knowledge graph, planner + sub-agents | Closed |
| HolmesGPT (OSS) | No: the agent refetches and re-stitches telemetry each step | No memory, no structure |
| Coroot (OSS) | Service map; AI RCA is paid / cloud | Not agentic, no shared memory |

**Pitch:** *"Traversal's causal search, open and explainable, on FalkorDB."*

## 5. Decisions taken
- FalkorDB via **Docker** (`falkordb/falkordb`, browser on host port 3002).
- Official `falkordb/mcpserver` in **read-only** mode for the ask box; our own typed `graph-mcp` for reasoning.
- Ingestion and scoring stay deterministic; the LLM picks tools and explains.
- Data: OpenTelemetry Demo (live, flagd faults) + RCAEval replay (offline eval). Both public.
- Main track: 01. Also covers 02; 03 lightly.

## Sources
[FalkorDB docs: Docker](https://docs.falkordb.com/operations/docker.html) ·
[FalkorDB docs: algorithms](https://docs.falkordb.com/algorithms/) ·
[FalkorDB MCP server](https://github.com/FalkorDB/FalkorDB-MCPServer) ·
[Graphiti MCP server on FalkorDB](https://docs.falkordb.com/agentic-memory/graphiti-mcp-server.html) ·
[FalkorDB MCP + GraphRAG blog](https://www.falkordb.com/blog/mcp-integration-falkordb-graphrag) ·
[Graphiti adds FalkorDB support (Zep)](https://blog.getzep.com/graphiti-knowledge-graphs-falkordb-support/) ·
[FalkorDB for GraphRAG overview (Atlan)](https://atlan.com/know/ai-agent/knowledge-graph/falkordb-graph-database-for-graphrag/) ·
[FalkorDB vs AWS Neptune FAQ](https://falkordb.com/falkordb-vs-aws-neptune/) ·
[FalkorDB hackathon rules (earlier WeMakeDevs event)](https://www.wemakedevs.org/hackathons/falkordb/rules) ·
[Traversal causal search](https://www.traversal.com/blog/introducing-causal-search-engine-from-correlated-alerts-to-causally-consistent-diagnoses) ·
[Resolve AI knowledge graph](https://resolve.ai/blog/knowledge-graph-agentic-ai-incident-response) ·
[HolmesGPT (CNCF)](https://www.cncf.io/blog/2026/01/07/holmesgpt-agentic-troubleshooting-built-for-the-cloud-native-era/) ·
[Coroot AI RCA](https://docs.coroot.com/ai/overview)
