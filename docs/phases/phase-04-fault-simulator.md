# Phase 4: Fault Simulator

**Goal:** for every hypothesis, predict its symptom footprint from the call graph and the propagation rules, compare it
with what was observed, and turn that into a scoring feature. The same machinery finds a second root cause, returns a
typed `no_root_cause`, and answers "what if X fails?" with no incident. This is the headline feature.

**Depends on:** phase 3. **Unblocks:** 5, 6 (`/simulate`, `/footprint`).

## Spec

- [LLD §7 Fault Simulator](../LLD.md#7-fault-simulator): rules (§7.1), simulation (§7.2), observed set (§7.3), match + score (§7.4), second cause (§7.5), `no_root_cause` (§7.6), what-if (§7.7), overlay (§7.8)
- [LLD §2.2 Q6](../LLD.md#22-causal-search-queries), [LLD §6.3 weights v2](../LLD.md#63-weightsjson)
- [ADR 0011](../adr/0011-fault-simulator.md), research in [TECH_RESEARCH](../TECH_RESEARCH.md)

## Files

```
api/search/simulate.py    load_rules, simulate, observed_set, match, footprint_score, what_if
seed/propagation_rules.yaml   (seeded in phase 1)
tests/test_simulate.py
tests/fixtures/multi_fault.cypher  tests/fixtures/healthy.cypher
```

## Tasks

- [x] `load_rules(kb)`: read `Rule` nodes once per diagnosis, sorted by id; carry `rules_version`.
- [x] `simulate(env, cand_op, cause_kind, rules, min_p)`: self predictions (cause itself p = 1, plus `direction:self` rules); Q6 rows; per hop `p_hop = rule.p × share`, `share = min(1, call.rps / caller_total_in_rps)`; hop n treats hop n−1's symptom as the new cause; best path = max product; keep `p ≥ min_p`; onset window `[t_cause, t_cause + hops × delay_s_max]`. Output sorted by `(hops, op)`.
- [x] Respect `service_kind` on rules (datastore `down` rule).
- [x] `observed_set(incident)`: ops with an anomaly, strongest kind, earliest onset; always includes the symptom.
- [x] `match`: matched / missed / unexplained; `coverage`, `precision`, `order` (Spearman of hops vs onset mapped to [0, 1], 0.5 if < 3 matched); `footprint = 0.5·cov + 0.3·prec + 0.2·order`.
- [x] Write `Evidence {kind:'footprint', summary:'explains X of Y symptoms', value:{…}}`: `SUPPORTED_BY` if `coverage ≥ refute_below_coverage`, else `REFUTED_BY`.
- [x] Add `footprint` to the phase 3 feature set (weights v2). Keep v1 runnable for the ablation.
- [x] Second root cause: after scoring, winner's unexplained set `U`; if `|U| ≥ min_unexplained_ops` or any op in `U` has score ≥ `strong_anomaly`, run Q1 → checks → score once from the earliest-onset op in `U`; write `ROOT_CAUSE {rank:2}`. At most one extra round.
- [x] `no_root_cause`: no hypothesis with `coverage ≥ max_coverage` and strongest anomaly `< max_anomaly` → incident status `no_root_cause`, no `ROOT_CAUSE` edge, summary lists what was checked.
- [x] `what_if(env, target, kind, save)`: operation or service (service = every op, merged on max p); attach owners via `OWNED_BY`; `save` writes `Simulation -[:PREDICTS {p, hops, kind}]-> Operation`.
- [x] All thresholds come from `weights.json → simulator`.

## Acceptance (LLD §12)

- **Fault Simulator:** on `mini_graph`, the true cause's coverage ≥ 0.8 and beats the loudest victim; a hand-computed `p` for a 2-hop path matches.
- **Multi-fault:** `multi_fault.cypher` (two independent faults) → second `ROOT_CAUSE {rank:2}`.
- **Healthy baseline:** `healthy.cypher` (weak unrelated anomalies) → `no_root_cause`, no `ROOT_CAUSE` edge.
- **What-if:** `what_if('redis','down')` returns the same ops as reverse `CALLS*` with traffic, sorted, with owners.
- Same inputs → same predictions list (determinism).

## Scalability

- **One Q6 per hypothesis**, ≤ 50 hypotheses × ~10 ms. Matching is in-process set math. Well inside the 60 s budget ([HLD §6](../HLD.md#6-non-functional-requirements-how-each-is-met)).
- **Rules are environment-agnostic data** in `kb:propagation`. New failure modes = new YAML rows + a version bump, no code.
  Growing toward a Causely-style codebook means richer rules, same interface.
- **Traffic-only edges** (`rps > 0`) prune cold paths, so prediction size tracks the live call graph, not the full topology.
- **Cache per diagnosis:** rules and Q6 results for a candidate are reused between the main round and the second-cause round; don't re-query.
- Ceiling: Q6 is a variable-length reverse traversal; on a very wide fan-in (thousands of callers) cap by hops or by rps share before `min_p` pruning.

## Risks / open questions

- Rule probabilities are guesses until tuned on RCAEval (phase 10). Freeze with `rules_version` before the demo.
- `caller_total_in_rps` for entry points needs the op's own rps; make sure ingest stores it (add to `Operation` in GRAPH_SCHEMA if missing).

## Done when

Footprint evidence exists for every hypothesis, the footprint feature is in the score, the three special outcomes (second cause, `no_root_cause`, what-if) have passing tests.

## Results (2026-10-16, 3 RE2-TT cases)

| Case | v1 (no simulator) | v2, spec (refute < 0.2) | v2, footprint as a feature (shipped) |
|---|---|---|---|
| `ts-auth-service_cpu_1` | ✅ auth | ❌ false `no_root_cause` | ✅ auth |
| `ts-auth-service_cpu_2` | ❌ seat (rank 3) | ❌ false `no_root_cause` | ❌ seat (rank 5) |
| `ts-order-service_delay_1` | ❌ its caller (rank 2) | ✅ order-service | ✅ order-service (explains 30% vs 3%) |

AC@1: 1/3 → 2/3. No spurious second causes after the independence gate. Fixtures: mini_graph → Charge (3 of 4) over the
victim (2 of 4); multi_fault → db + cache (rank 2); healthy → `no_root_cause`. Q6 p95 < 5 ms. Three cases are a smoke
check, not the eval: phase 10 runs all 90 and tunes `refute_below_coverage`, `min_p` and the rule `p` values.
