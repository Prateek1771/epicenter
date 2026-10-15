# ADR 0007: Agents coordinate through the incident subgraph

**Status:** Accepted · **Date:** 2026-10-15

## Context
Track 02 asks for shared state and handoffs between agents. Multi-agent frameworks usually pass messages or a large
state object between agents, which hides the work and makes handoffs to humans hard.

## Options
1. LangGraph state holds all findings; agents pass it along.
2. A message bus between agents.
3. **Agents read and write `Hypothesis`, `Evidence`, `Decision`, `Explanation` and `Action` nodes; LangGraph state holds ids only.**

## Decision
Option 3. Investigators write their own evidence nodes in parallel (no conflicts: each writes only under its own
hypothesis). The skeptic and historian read what investigators wrote. Humans hand off by adding `Decision` / `Change`
nodes. The SSE stream mirrors graph writes, so the canvas shows the coordination live.

## Consequences
- Coordination is visible and queryable after the fact ("who concluded what, from which evidence").
- Resume after a crash is natural: the graph already holds the finished work.
- Every agent step costs a few graph round-trips; negligible at our scale.
