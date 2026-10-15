# ADR 0003: Typed MCP tools for agents; the official FalkorDB MCP server only read-only

**Status:** Accepted · **Date:** 2026-10-15

## Context
Track 01 asks for tool selection through MCP. Letting an LLM write arbitrary Cypher is flexible but risky (writes,
expensive queries, wrong answers that look right). FalkorDB ships an official MCP server with `query_graph`,
`query_graph_readonly` and schema tools.

## Options
1. Only the official MCP server, LLM writes Cypher.
2. **Our typed tools (fixed, parameterized queries) as the main surface, plus the official server in read-only mode for open questions.**
3. Typed tools only.

## Decision
Option 2. `blast_radius`, `upstream_candidates`, `propagation_path`, `mechanism`, `why_not`, `recent_changes`,
`similar_incidents` and `who_knows` are Python functions over `graph.py`, exposed over MCP at `/mcp` on the API.
`falkordb-mcp` runs with `FALKORDB_DEFAULT_READONLY=true` and an API key, used only by the ask box; the Cypher it ran is
shown to the user.

## Consequences
- Agents can't change the graph through free-form queries.
- Typed tools cover the demo questions with predictable latency; the read-only fallback keeps the ask box open-ended.
- Two MCP surfaces to explain; the doc and UI label which one answered.
