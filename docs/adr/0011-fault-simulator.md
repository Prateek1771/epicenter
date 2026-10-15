# ADR 0011: Fault Simulator: predict each hypothesis's symptom footprint and compare it with what we observed

**Status:** Accepted · **Date:** 2026-10-15 · **Research:** [TECH_RESEARCH.md](../TECH_RESEARCH.md)

## Context
Our causal search checks that a candidate is **upstream** of the symptom and went bad **earlier**. It doesn't check that
the candidate **explains the whole pattern** of what broke. That's the gap behind the most common AI SRE failure:
anchoring on one loud symptom (ORCA-Bench). We also always name a cause, even on a healthy system, where Causely showed a
typed "no root cause" answer cut false positives from 67% to 0%. And our blast radius only says what's reachable, not
what would actually break.

## Options
1. **Bayesian codebook (Causely-style):** P(symptoms | cause) for every entity type, abductive argmax. Most principled, but needs calibrated per-type probabilities we don't have.
2. **LLM predicts the impact:** easy to build, but nondeterministic and exactly the guessing we avoid ([ADR 0002](0002-deterministic-ingestion-and-scoring.md)).
3. **Rule-based propagation over the call graph:** a small environment-agnostic rule set (callee errors → caller errors, p 0.8, …) applied hop by hop along `CALLS`, weighted by traffic share. Deterministic and graph-native, and it grows into option 1 later.

## Decision
Option 3, called the **Fault Simulator**.

- **Rules:** live in their own FalkorDB graph `kb:propagation` (seeded from `seed/propagation_rules.yaml`, versioned).
- **Simulation (Q6):** for every hypothesis, propagate the fault upstream (6 hops max, edges with traffic only) to get a **predicted footprint**: operations, expected symptom kind, probability, expected order.
- **Comparison:** predicted vs. observed → `coverage`, `precision`, `order` → a `footprint` score, which becomes a new scoring feature (weight 0.20, `weights.json` v2).
- **Multi-fault:** symptoms the winner doesn't explain seed one extra search for a second root cause.
- **Negative answer:** if nothing explains at least 50% of symptoms and anomalies are weak, the incident ends `no_root_cause`.
- **What-if:** the same simulation without an incident answers "what if X fails?" before a change.

Detail: [LLD §7](../LLD.md#7-fault-simulator).

## Consequences
- **Counters symptom anchoring:** a downstream victim predicts a small footprint that misses the deeper anomalies, so its coverage stays low.
- **Visible on the canvas:** predicted (dashed) vs. observed (filled), with matched / missed / unexplained colouring. A strong, honest demo moment.
- **Rule quality caps accuracy:** rule probabilities are tuned on RCAEval and the footprint weight goes through the ablation table, so its value is measured, not assumed.
- **Extra cost:** one more query per hypothesis (Q6) plus Python matching. Under 50 hypotheses × ~10 ms, so well within the 60 s budget.
- **Traffic-based scope:** the simulation only follows calls that carried traffic in the window, so a cold path won't be predicted. That's intended: no traffic means no symptoms.
