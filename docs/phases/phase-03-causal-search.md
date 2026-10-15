# Phase 3: Causal search + scorer

**Goal:** given an incident's symptom operation, produce hypotheses (Q1), support or refute each with deterministic
rules (Q2 onset order, Q3 mechanism / change), rank them with PageRank (Q4) plus a fixed-weight score, and pick a root
cause with a confidence. No LLM anywhere in this phase.

**Depends on:** phases 1, 2. **Unblocks:** 4, 5.

## Spec

- [LLD §2.2 Q1–Q4](../LLD.md#22-causal-search-queries) and the Python rules under each query
- [LLD §6 Scoring](../LLD.md#6-scoring-searchscorepy): features, formula, `weights.json`, tie-break
- [LLD §4 models](../LLD.md#4-data-models-modelspy-excerpt), [LLD §8 hypothesis state machine](../LLD.md#8-state-machines)
- [ADR 0002](../adr/0002-deterministic-ingestion-and-scoring.md), [HLD §8 bottlenecks](../HLD.md#8-bottlenecks-and-how-theyre-handled)

## Files

```
api/search/causal.py    hypotheses (Q1 + symptom at hops 0), check_propagation (Q2), check_mechanism (Q3), project_and_rank (Q4)
api/search/score.py     features, score, confidence, tie-break
weights.json            v1 (no footprint) and v2 (with footprint) per LLD §6.3
tests/test_causal.py  tests/test_score.py
```

## Tasks

- [ ] `hypotheses(env, incident, symptom)`: Q1 rows + the symptom itself (`hops = 0`); write `Hypothesis {status:'open'}`, `HAS_HYPOTHESIS`, `BLAMES`.
- [ ] `check_propagation`: Q2 paths; a path passes if no `null` onset and `onsets[i+1] <= onsets[i] + skew_s`. Best path = passes, fewest hops, lexicographic. Pass → `Evidence{kind:'propagation'}` `SUPPORTED_BY`; none → `REFUTED_BY`.
- [ ] `check_mechanism`: Q3; victim rule `child_ratio >= 2·self_ratio and child_ratio > 1.5` → `Evidence{kind:'victim'}` `REFUTED_BY`; change in `lookback_s` → `Evidence{kind:'change'}` `SUPPORTED_BY`, `ABOUT` the `Change`.
- [ ] Evidence `summary` comes from a template string, never an LLM ("payment/Charge errors began 52 s before checkout/PlaceOrder").
- [ ] Hypothesis status from evidence only: any `REFUTED_BY` → `refuted`; only `SUPPORTED_BY` → `supported`; query timeout / missing data → `inconclusive`.
- [ ] Q4: Q4a on the env graph → edge list; write ops + `BLAME {w}` into `scratch:<incident>`; Q4b PageRank; **delete the scratch graph in `finally`**. Fallback `networkx.pagerank` on the same edge list; record `score_parts.pagerank_impl`.
- [ ] Features rank-normalized within the incident; `score = w·features − 1.0·refuted`; `confidence = sigmoid(k·(s1 − s2))`.
- [ ] Tie-break: score desc, onset asc, op id asc. Store `weights_version` on the `Incident`, `score` + `score_parts` (JSON, sorted keys) on each `Hypothesis`.
- [ ] Write `(Incident)-[:ROOT_CAUSE {rank:1}]->(top)`; top → `confirmed`, the rest `supported` → `pruned`.
- [ ] `weights.json` loaded once, validated (weights sum, required keys); version string goes everywhere a score goes.

## Acceptance

- LLD §12 "rule tests": table-driven tests for the victim rule, the onset-order rule (with skew), the change lookback window.
- On `mini_graph`, the known root cause wins; the loudest downstream victim is refuted by the victim rule.
- **Determinism:** diagnose one RCAEval case twice → identical `score_parts` JSON, byte for byte (N3).
- Scratch graph is gone after scoring, also when PageRank raises.
- Each of Q1–Q4 under 200 ms p95 on the RCAEval TT graph (check `/health` timings later, log now).

## Scalability

- **Bounded search:** hop limit 6, start from the indexed symptom, filter `Anomaly` by `incident` first. Cost grows with
  the anomalous subgraph, not the whole topology.
- **Projection to a scratch graph** keeps PageRank to tens of nodes regardless of env size. Same pattern for any future
  algorithm (WCC, betweenness): project, run, delete.
- **Per-hypothesis checks are independent** (Q2, Q3 read; writes only under that hypothesis). That's what lets phase 5
  run them in parallel without locks.
- **Weights and thresholds are data** (`weights.json`, versioned). Tuning never needs a code change, and old incidents
  stay explainable by their stored version.
- Ceiling: one scorer pass per incident in-process; ≤ 50 hypotheses by design. If hypothesis count grows past a few hundred, cap Q1 by onset/strength before checks.

## Risks / open questions

- **Q-b:** add `footprint` to `EvidenceOut.kind` in [LLD §4](../LLD.md#4-data-models-modelspy-excerpt) (needed in phase 4).
- Weighted PageRank depends on the phase 0 smoke result.
- `mechanism_fit` for non-latency kinds is a coarse rule; validate on RCAEval in phase 10.

## Done when

An RCAEval case produces a ranked, deterministic verdict in the graph with supporting and refuting evidence for every hypothesis.
