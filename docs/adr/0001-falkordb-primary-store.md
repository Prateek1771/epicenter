# ADR 0001: FalkorDB is the primary store, one graph per environment

**Status:** Accepted · **Date:** 2026-10-15

## Context
Epicenter's core questions are about connections: what sits upstream of the symptom, which hops went bad in time order,
what breaks if X goes down, who fixed this before. The hackathon also requires FalkorDB to be the primary database and
central to the product. We need graph traversal, vector search for incident memory, and full-text search over log
templates, ideally in one store.

## Options
1. **FalkorDB**: Cypher, multi-graph, vector + full-text + range indexes, built-in PageRank / BFS / WCC, official MCP server, Docker image.
2. Neo4j: richer algorithm library (GDS), but not the hackathon's database.
3. Postgres + recursive CTEs + pgvector: familiar, but multi-hop path queries are awkward and slow to write.
4. In-memory networkx: trivial for small graphs, but no persistence, no sharing between agents, no memory across sessions.

## Decision
FalkorDB holds all persistent state. One graph per environment (`env:<name>`) as the tenant boundary, and throwaway
`scratch:<incident>` graphs for algorithm projections.

## Consequences
- Causal search, memory and agent coordination are graph queries, so the product doesn't work without FalkorDB (as required).
- Smaller algorithm set than Neo4j GDS (no personalized PageRank, no Louvain); a networkx fallback covers PageRank if needed.
- SSPLv1 license: fine for us; we never call it open source.
- FalkorDB serializes writes per graph; acceptable at our write volume (HLD §8).
