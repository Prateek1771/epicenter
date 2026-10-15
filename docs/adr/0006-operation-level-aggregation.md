# ADR 0006: Aggregate spans to operations; never store span nodes

**Status:** Accepted · **Date:** 2026-10-15

## Context
A busy demo emits thousands of spans per minute. Span-level nodes would make variable-length path queries slow and the
graph huge, and the causal search reasons about operations, not individual requests.

## Options
1. One node per span.
2. Service-level graph only (~20 nodes): too coarse; can't tell `cart/GetCart` from `cart/AddItem`.
3. **Operation-level graph: `(Operation)-[:CALLS {rps, p95_ms, err_rate}]->(Operation)`, rolled up every 30 s.**

## Decision
Option 3. Self / child time and per-operation series are computed in Python from spans during ingest and stored on
`Anomaly` nodes. Evidence keeps a `ref` (trace id) so a user can jump to a real trace.

## Consequences
- Graph stays at hundreds to a few thousand nodes; Q1–Q5 stay under 200 ms.
- Request-level detail (one slow trace) is not in the graph; it's one click away via `ref`.
