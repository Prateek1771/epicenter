# ADR 0002: Deterministic ingestion and scoring; the LLM explains and picks tools

**Status:** Accepted · **Date:** 2026-10-15

## Context
The pitch is "every answer is a path you can rerun". If an LLM writes topology or ranks causes, reruns can differ and
answers can't be traced to data. Competitor AI-SREs are criticized for exactly this.

## Options
1. LLM agent investigates freely and states the root cause.
2. LLM ranks candidates produced by queries.
3. **Deterministic code writes the graph and scores candidates; LLMs choose which tools to call, explain the result, and pick from bounded options.**

## Decision
Option 3. Ingest, anomaly detection, hypothesis status rules and the score are plain Python + Cypher with fixed weights
(`weights.json`, versioned) and id tie-breaks. LLM output is written only to `Explanation` and `Action{status:'proposed'}`
and is never read by the scorer. Narrator claims must cite `Evidence` ids; Jev drops unsupported claims.

## Consequences
- Same input → same verdict (N3); the verdict survives an LLM outage (N7).
- Less "magic": the LLM can't discover causes outside the graph. Mitigation: humans can add `Change` / `Decision` nodes mid-incident.
- Weights need tuning on RCAEval and must be frozen before the demo.
