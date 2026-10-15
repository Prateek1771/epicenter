# Phase 1: Graph layer

**Goal:** `api/graph.py` is the only door to FalkorDB. Every query has an id in one catalogue, runs parameterized,
is timed, and has a test against a known fixture graph. Startup seeds indexes, rules, owners and runbooks idempotently.

**Depends on:** phase 0. **Unblocks:** 2, 3.

## Spec

- [LLD §2 graph.py](../LLD.md#2-graphpy): `Graph` / `EnvGraph` API, `QUERIES` dict, U1–U3, Q1–Q6, tool queries
- [GRAPH_SCHEMA](../GRAPH_SCHEMA.md): graphs (§1), labels (§3), relationships (§4), [indexes (§5)](../GRAPH_SCHEMA.md#5-indexes), retention (§7)
- [LLD §7.1](../LLD.md#71-propagation-rules-kbpropagation) rule seed into `kb:propagation`
- [ADR 0001](../adr/0001-falkordb-primary-store.md) one graph per environment, [ADR 0006](../adr/0006-operation-level-aggregation.md) no span nodes

## Files

```
api/graph.py            Graph, EnvGraph, QUERIES, query timing registry
api/models.py           shared pydantic models (start with LLD §4; grows in later phases)
api/ingest/seed.py      indexes, kb:propagation rules, owners.yaml, runbooks.yaml
seed/owners.yaml  seed/runbooks.yaml  seed/propagation_rules.yaml
tests/fixtures/mini_graph.cypher     8 operations, one known root cause
tests/test_graph.py
```

## Tasks

- [ ] `Graph(url)` with `env(name)` → `env:<name>`, `scratch(incident_id)` → `scratch:<id>`, and `kb()` → `kb:propagation`.
- [ ] `EnvGraph.ro(qid, **params)` uses `GRAPH.RO_QUERY`; `rw(qid, **params)` uses `GRAPH.QUERY`; both return `list[dict]`.
- [ ] `QUERIES: dict[str, str]` holds U1–U3, Q1–Q6, Q4a/Q4b, the four tool queries and the seed statements. Callers pass ids, never Cypher.
- [ ] Each call logs `{qid, graph, duration_ms, rows}` (structured JSON) and pushes `duration_ms` into a per-qid ring buffer (last 200) for `/health` p50/p95.
- [ ] 5 s client-side timeout per query; 1 retry on connection errors only ([LLD §10](../LLD.md#10-external-calls-timeouts-and-retries)). Raise a typed `GraphUnavailable` the API maps to `503 GRAPH_UNAVAILABLE`.
- [ ] Ids: decide Q-a (below) and implement one `ids.py`-style helper in `graph.py` or `models.py` (not scattered f-strings).
- [ ] `seed.py`: every statement idempotent (`MERGE`, index creation that ignores "already exists"). Runs on API startup for the configured env graph and `kb:propagation`.
- [ ] Rules seed: read `seed/propagation_rules.yaml`, `MERGE (r:Rule {id})` per rule with `version`; replace the whole graph when the version changes ([GRAPH_SCHEMA §7](../GRAPH_SCHEMA.md#7-retention)).
- [ ] `mini_graph.cypher`: 8 ops across ~5 services incl. one datastore, `CALLS` with `rps`, one incident's `Anomaly` nodes with known onsets, one `Change`. Document the expected answer for each query at the top of the file.
- [ ] Test fixture loads into `env:test`, dropped after the run.

## Acceptance

- `tests/test_graph.py`: every Q1–Q6 and tool query returns the documented rows on `mini_graph` (LLD §12 "query unit tests").
- Running the seed twice leaves node/index counts unchanged.
- A query with a string containing `'})-[` as a parameter value returns no rows and does not error (injection check).

## Scalability

- **One module owns the database.** Swapping the store, adding read replicas or sharding env graphs onto separate
  FalkorDB instances is a change to `Graph.env()` only. Keep it that way: no `falkordb` import outside `graph.py`.
- **Query ids, not Cypher text,** give per-query metrics for free and let you tune or replace one query without touching callers.
- **Graph per environment** is the tenant boundary. Never write a query that spans `env:*` graphs; that's what lets
  environments move to separate instances later.
- **Index every lookup key** used in a `MATCH {…}` (GRAPH_SCHEMA §5). A new query that matches on a new property needs a new index in the same PR.
- **Graph size stays flat:** topology is updated in place (U1 `MERGE` + `SET`), so a 3-month run is the same size as a 3-minute run ([HLD §4.1](../HLD.md#41-whats-stored-where)).
- Ceiling: one FalkorDB instance, writes serialized per graph. Fine below ~100k nodes ([ARCHITECTURE §1.3](../ARCHITECTURE.md#13-scale-estimate-sizing-falkordb)).

## Risks / open questions

- **Q-a:** `Evidence.id = E<n>` collides across incidents in one env graph. Proposal: stored key `<incident>:E<n>`,
  API shows `E<n>`. Same for `Hypothesis` and `Action` ids. Decide and update GRAPH_SCHEMA §3.
- **Q-e:** move `Action` out of the `kb:propagation` section in GRAPH_SCHEMA §3.
- Index syntax differs between FalkorDB versions; trust the smoke-test results from phase 0.

## Done when

All queries are in the catalogue, tested on the fixture, timed, and the seed is idempotent.
