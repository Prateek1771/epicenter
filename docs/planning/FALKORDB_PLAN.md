# FalkorDB on Docker: setup and integration plan (Graph Hacks)

Focus: the FalkorDB "Graph Hacks: Context for AI Agents" hackathon only. Full system design:
[`docs/ARCHITECTURE.md`](../ARCHITECTURE.md). Product plan: [`GRAPH_HACKS_PLAN.md`](GRAPH_HACKS_PLAN.md).

## 1. Which image

| Image | Contains | Use it for |
|---|---|---|
| `falkordb/falkordb` | server (6379) + browser UI (3000) | **Dev and demo (our choice)**: one container, browser included |
| `falkordb/falkordb-server` | server only | Production / deployment without the UI |
| `falkordb/falkordb-browser` | browser only, needs `FALKORDB_URL` | If the server runs elsewhere |
| `falkordb/mcpserver` | official MCP server (HTTP or stdio) | Read-only Cypher tool for the chat agent |

Pin the version after the first pull (`FALKORDB_TAG` in `.env`). Don't demo on `latest`.

## 2. Ports (avoid clashes)

| Port | Who | Why this port |
|---|---|---|
| 6379 | FalkorDB server | default |
| **3002** | FalkorDB browser | OpenConnector already uses 3000 |
| 3001 | our Next.js UI | |
| 8000 | our FastAPI | |
| **8081** | `falkordb/mcpserver` | the OTel Demo shop uses 8080 |
| 8090 | our `graph-mcp` | |

## 3. Quick start (single container, no compose)

```bash
docker run -d --name falkordb -p 6379:6379 -p 3002:3000 \
  -e REDIS_ARGS="--requirepass change-me --appendonly yes" \
  -e FALKORDB_ARGS="THREAD_COUNT 4 TIMEOUT_MAX 30000" \
  -v falkordb_data:/var/lib/falkordb/data \
  falkordb/falkordb:latest
```

The FalkorDB docs show two different data paths (`/data` in the compose examples, `/var/lib/falkordb/data` in the FAQ).
Check which one the image uses before trusting persistence:

```bash
docker exec falkordb sh -c 'ls -la /data /var/lib/falkordb/data 2>/dev/null'
```

## 4. Compose (the version we'll actually run)

The full `docker-compose.yml` (FalkorDB + MCP server + api + web + OpenConnector) is in
[`docs/HLD.md` §5.2](../HLD.md#52-docker-composeyml). The FalkorDB part:

```yaml
services:
  falkordb:
    image: falkordb/falkordb:${FALKORDB_TAG:-latest}
    ports: ["6379:6379", "3002:3000"]
    environment:
      REDIS_ARGS: "--requirepass ${FALKORDB_PASSWORD} --appendonly yes"
      FALKORDB_ARGS: "THREAD_COUNT 4 TIMEOUT_MAX 30000"
    volumes: [falkordb_data:/var/lib/falkordb/data]
    healthcheck:
      test: ["CMD", "redis-cli", "-a", "${FALKORDB_PASSWORD}", "PING"]
      interval: 5s
      retries: 10
volumes:
  falkordb_data:
```

## 5. Verify it works

```bash
docker compose up -d falkordb
docker compose exec falkordb redis-cli -a "$FALKORDB_PASSWORD" PING                       # PONG
docker compose exec falkordb redis-cli -a "$FALKORDB_PASSWORD" \
  GRAPH.QUERY env:smoke "CREATE (:Service {name:'cart'})-[:CALLS]->(:Service {name:'valkey'})"
docker compose exec falkordb redis-cli -a "$FALKORDB_PASSWORD" \
  GRAPH.QUERY env:smoke "MATCH (a)-[:CALLS]->(b) RETURN a.name, b.name"
docker compose restart falkordb    # then run the MATCH again: data must still be there
```

Open the browser UI at http://localhost:3002 and connect to `localhost:6379` with the password.

## 6. Python client

```python
# pip install falkordb
import os
from falkordb import FalkorDB

db = FalkorDB(host="localhost", port=6379, password=os.environ["FALKORDB_PASSWORD"])
g = db.select_graph("env:astronomy-shop")
res = g.query(
    "MATCH (s:Operation {id:$op})-[:CALLS*1..6]->(c) RETURN c.id",
    {"op": "checkout/PlaceOrder"},
)
for row in res.result_set:
    print(row)
```

- Use **parameters** (`$op`), never string formatting. That's the injection guard for anything an agent passes in.
- Use `g.ro_query(...)` for read paths (runs as `GRAPH.RO_QUERY`).
- Use one graph per environment (`env:<name>`) and throwaway `scratch:<incident>` graphs for algorithm projections;
  `g.delete()` drops a scratch graph.

## 7. Indexes (run once per graph, in `seed.py`)

```cypher
CREATE INDEX FOR (o:Operation) ON (o.id)
CREATE INDEX FOR (s:Service) ON (s.name)
CREATE INDEX FOR (a:Anomaly) ON (a.incident)
CREATE INDEX FOR (c:Change) ON (c.ts)
CALL db.idx.fulltext.createNodeIndex('Signal', 'text')
CREATE VECTOR INDEX FOR (i:Incident) ON (i.signature) OPTIONS {dimension: 64, similarityFunction: 'cosine'}
```

## 8. Official MCP server (read-only)

```yaml
  falkordb-mcp:
    image: falkordb/mcpserver:${FALKORDB_MCP_TAG:-latest}
    ports: ["8081:8080"]
    environment:
      FALKORDB_HOST: falkordb
      FALKORDB_PORT: 6379
      FALKORDB_PASSWORD: ${FALKORDB_PASSWORD}
      FALKORDB_DEFAULT_READONLY: "true"
      MCP_TRANSPORT: http
      MCP_PORT: 8080
      MCP_API_KEY: ${MCP_API_KEY}
```

Tools it exposes: `query_graph`, `query_graph_readonly`, `get_graph_schema`, `get_node_schema`, `get_relationship_schema`,
plus list/delete graphs. In HTTP mode, clients send `Authorization: Bearer $MCP_API_KEY` and reuse the returned
`Mcp-Session-Id` header. Our agents use it only for the "ask anything" box; the main reasoning goes through our typed
`graph-mcp` tools (ARCHITECTURE §10).

## 9. Smoke test before writing product code

One script, `api/smoke_falkordb.py`, that checks the features the design depends on, on the pinned version:
1. Variable-length path `[:CALLS*1..6]` with a filter on the end node.
2. `UNWIND` over `nodes(p)` with an `OPTIONAL MATCH` per node (Q2 in the architecture).
3. `CALL algo.pageRank(...)` signature and output.
4. Vector index create + `db.idx.vector.queryNodes` with `vecf32`.
5. Full-text index query.
6. Two writers in parallel on the same graph (investigator concurrency).

If any fails, fix the query in ARCHITECTURE §7 before building on it.

## 10. Backup and reset

```bash
docker compose exec falkordb redis-cli -a "$FALKORDB_PASSWORD" BGSAVE        # snapshot
docker compose exec falkordb redis-cli -a "$FALKORDB_PASSWORD" GRAPH.LIST    # list graphs
docker compose exec falkordb redis-cli -a "$FALKORDB_PASSWORD" GRAPH.DELETE env:smoke
docker compose down -v                                                       # wipes the volume (demo reset)
```

## Sources
[FalkorDB Docker docs](https://docs.falkordb.com/operations/docker.html) ·
[FalkorDB MCP server](https://github.com/FalkorDB/FalkorDB-MCPServer) ·
[FalkorDB algorithms](https://docs.falkordb.com/algorithms/)
