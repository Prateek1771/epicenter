# Phase 2: Ingest + RCAEval adapter + detectors

**Goal:** an RCAEval case replays into `env:rcaeval-tt`: topology (`Service`, `Operation`, `CALLS`) from traces,
`Anomaly` nodes from metrics / logs / spans for the incident window, all deterministic. RCAEval comes first because it
needs no extra containers and gives labelled answers.

**Depends on:** phase 1. **Unblocks:** 3, 9.

## Spec

- [LLD §3.1 Adapter protocol](../LLD.md#31-adapter-protocol), [LLD §3.2 Detectors](../LLD.md#32-detectors-detectpy) incl. the slow-burn pass
- [LLD §2.1 upserts U1–U3](../LLD.md#21-upserts-ingest)
- [HLD §4 Data flow and lifecycle](../HLD.md#4-data-flow-and-lifecycle): what is stored and what never is
- [ADR 0006](../adr/0006-operation-level-aggregation.md), [ADR 0002](../adr/0002-deterministic-ingestion-and-scoring.md)
- [EXAMPLE_RUNS §3](../EXAMPLE_RUNS.md#3-rcaeval-replay-offline-measured)

## Files

```
api/ingest/base.py        Adapter Protocol + CallAgg, Series, LogLine, ChangeEvent dataclasses
api/ingest/rcaeval.py     file adapter + `python -m api.ingest.rcaeval --case … --env …`
api/ingest/logs.py        Drain3 template mining (shared by all adapters)
api/ingest/detect.py      robust z, PELT onset, self/child ratios, log anomalies, slow burn
api/ingest/write.py       the only ingest → graph writer; write_topology = one roll-up tick (U1 batched).
                          The periodic 30 s loop for live sources lands in phase 9.
tests/test_detect.py
```

## Tasks

- [x] `Adapter` protocol with `calls / series / logs / changes` exactly as LLD §3.1. Adapters return plain dataclasses; they never import `graph.py`.
- [x] Writer functions (U1 per `CallAgg`, U2 per anomaly, U3 per change) live in one place and take dataclasses. All adapters share them.
- [x] Operation ids `<service>/<operation>`; datastores → `Service {kind:'datastore'}` from `db.system` ([LLD §2.1](../LLD.md#21-upserts-ingest)).
- [x] RCAEval adapter: `traces.csv` → `CallAgg`, metrics parquet → `Series`, `logs.csv` → `LogLine`. `inject_time.txt` is the **alert time only**, never a `Change` (no answer leak).
- [x] Snapshot window: baseline `[t − BASELINE_S − 120 s, t − 120 s]`, window `[t − 120 s, t + WINDOW_AFTER_S]` from config.
- [x] Robust z (median / MAD, ε), anomaly if `max |z| ≥ 4`; onset = first PELT change point (`ruptures`, `model="rbf"`) in the window, fallback = first `|z| ≥ 4`.
- [x] Self vs child time from spans → `self_ratio`, `child_ratio` on latency anomalies.
- [x] Drain3 per service: `new_template` and `log_burst` (ratio ≥ 5 and ≥ 10 occurrences). Write `Signal` nodes and `IN_SIGNAL` edges.
- [x] `down`: had traffic in baseline, no spans and no metrics in the window.
- [x] Slow-burn pass for `SLOW_BURN_KINDS`: 1-min series over `SLOW_BURN_LOOKBACK_S`, Mann-Kendall p < 0.01 + Theil-Sen, ≥ 1.5× or > 80% of limit, PELT onset; merge with a short-pass anomaly on the same op+kind (earlier onset, higher score).
- [x] Sort every input by key before processing; anomaly ids `an-<incident>-<n>` assigned in sorted order (N3).
- [x] Score normalized to 0..1 (document the mapping from z in `detect.py`).
- [x] Unavailable source → append to `Incident.gaps`, keep going ([HLD §7](../HLD.md#7-failure-modes)).

## Acceptance

- Slow-burn test from [LLD §12](../LLD.md#12-test-plan): synthetic memory series climbing for 3 h; short pass alone misses it, with slow burn it's detected with onset within 5 min of the climb's start.
- Replaying one RCAEval case twice produces byte-identical `Anomaly` rows (ids, onsets, scores).
- After replay, `MATCH (n) RETURN labels(n)[0], count(*)` shows no span-level nodes; operations are in the hundreds.
- Detector unit tests: robust z on a flat series = no anomaly; step change = anomaly with onset at the step.

## Scalability

- **Adapters are the extension point.** A new telemetry source (Datadog, Tempo, Loki) is a new class implementing the
  protocol. Detectors, writers and everything downstream stay untouched.
- **Aggregate before writing.** Spans become `(caller_op, callee_op)` aggregates in Python; only one `CALLS` update per
  pair per tick reaches FalkorDB. Graph writes scale with the number of edges, not with traffic.
- **Batch writes:** U1 for one tick can go as one `UNWIND $rows` statement instead of N round trips. Do this as soon as
  a tick has > ~100 pairs.
- **Raw data never enters the graph.** Evidence keeps a `ref` back to the source. Keeps FalkorDB under 1 GB regardless of traffic.
- **Detectors are pure functions** (series in, anomalies out). They can move to a worker process or job queue unchanged
  if ingest needs to scale away from the API ([ADR 0005](../adr/0005-modular-monolith.md) consequences).
- Ceiling: the 30 s roll-up runs in the API process. Extract `ingest` into its own container when one env produces
  more pairs than one tick can write, or when there are many envs.

## Risks / open questions

- RCAEval file formats differ between RE1/RE2 and systems; pin the dataset version and write the column mapping at the top of `rcaeval.py`.
- ~~PELT penalty~~: `weights.json → detect.pelt_pen` (10), with `sustain` 3 and `eps_rel` 0.1 picked on one case
  (`re2tt_ts-auth-service_cpu_2`); phase 10 tunes them on a dev split and freezes them.

- Re-replaying a case no longer deletes its anomalies: phase 3 added ingest versions (`Incident.ingest`, previous ingest
  retired as `<incident>@i<k>`), so diagnosis history stays linked. See [LLD §3.1](../LLD.md#31-adapter-protocol).

## Done when

`python -m api.ingest.rcaeval --case re2tt_<service>_<fault>_<n> --env rcaeval-tt --download` fills the graph deterministically and the detector tests pass.
