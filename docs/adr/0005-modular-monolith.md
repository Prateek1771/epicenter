# ADR 0005: Modular monolith

**Status:** Accepted · **Date:** 2026-10-15

## Context
Team of 1–3, hackathon timeline, one demo audience. The first design had a separate `graph-mcp` container for the typed tools.

## Options
1. Separate services: ingest, agents, tools/MCP, API.
2. **One API process with modules `ingest`, `search`, `agents`, `tools`; MCP mounted at `/mcp` on the same app.**

## Decision
Option 2 (senior-architect pattern guide: team < 10 and unclear scaling needs → modular monolith). Containers: `falkordb`,
`falkordb-mcp` (third-party image), `api`, `web`, `open-connector`. Module rule: `agents → tools → search → graph`,
`ingest → graph`; only `graph.py` talks to FalkorDB.

## Consequences
- One fewer container, no network hop between agents and tools, one place to debug.
- Ingest and agents share CPU; fine at our scale. If ingest ever needs to scale alone, it's already a separate module to extract.
