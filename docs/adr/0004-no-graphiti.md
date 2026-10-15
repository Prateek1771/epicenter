# ADR 0004: No Graphiti for agent memory

**Status:** Accepted · **Date:** 2026-10-15

## Context
Graphiti (Zep) is a temporal knowledge-graph memory framework that supports FalkorDB and has an MCP server. It extracts
entities and facts from text with an LLM and writes them into the graph.

## Options
1. Graphiti as the memory layer.
2. **Our own deterministic memory: incident subgraphs, `SIMILAR_TO` via a deterministic signature, `RESOLVED_BY` success counts.**

## Decision
Option 2. With Graphiti, an LLM decides what enters the graph, which breaks ADR 0002 (reruns differ, provenance is fuzzy).
Our memory items are already structured (incidents, hypotheses, actions), so LLM extraction adds nothing.

## Consequences
- We write the memory code ourselves (small: one signature function, Q5, two edge types).
- We lose free-text memory of chats. If Slack threads are ingested later, revisit with Graphiti for that source only, in a separate graph.
