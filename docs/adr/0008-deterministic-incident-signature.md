# ADR 0008: Incident memory uses a deterministic 64-dim signature vector

**Status:** Accepted · **Date:** 2026-10-15

## Context
The historian needs "similar past incidents". An LLM embedding of an incident summary is easy but nondeterministic
across model versions and needs an extra API call.

## Options
1. LLM / sentence-transformer embedding of a text summary.
2. **Hand-built feature vector from the graph.**

## Decision
Option 2. 64 dims, L2-normalized:
- dims 0–7: anomaly kind histogram on the root-cause hypothesis
- dims 8–15: anomaly kind histogram across all hypotheses
- dims 16–19: hop distance of the root cause (one-hot 0, 1, 2, 3+)
- dims 20–24: change type present (deploy, flag, config, infra, manual)
- dims 25–31: datastore / app / proxy involvement
- dims 32–63: hashed top log templates on the root cause (feature hashing)

Stored on `Incident.signature`, vector-indexed (cosine), queried by Q5, then re-ranked with graph overlap (same root-cause
operation or change type).

## Implementation note (phase 7, clarification)
`api/search/signature.py`. Kind order `latency, errors, cpu, mem, saturation, log_burst, new_template, down`; change
types `deploy, flag, config, infra, manual`. Dims 25–31: 25–27 root-cause service kind one-hot (datastore, app, proxy),
28–30 share of anomalous operations per service kind, 31 = a second root cause was found. Templates are hashed with
`blake2b` (Python's `hash()` is salted per process). Each block is scaled to [0, 1] before the L2 normalization. An
all-zero signature (nothing anomalous) is not written.

## Consequences
- Recall is reproducible and free; it can be evaluated leave-one-out on RCAEval (precision@3).
- It won't match incidents that are similar only in wording. Acceptable: our memory is about mechanism, not wording.
