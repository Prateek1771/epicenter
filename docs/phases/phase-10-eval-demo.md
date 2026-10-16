# Phase 10: Evaluation, hardening, demo

**Goal:** a published accuracy number on RCAEval with ablations (including losses), frozen weights and rules,
measured latency targets, and every hackathon deliverable ready.

**Depends on:** all earlier phases.

## Spec

- [LLD §12 eval row](../LLD.md#12-test-plan), [API.md `GET /eval`](../API.md#example-runs-and-eval)
- [ARCHITECTURE §1.2 NFRs](../ARCHITECTURE.md#12-non-functional), [HLD §6](../HLD.md#6-non-functional-requirements-how-each-is-met)
- [ARCHITECTURE §7 risks](../ARCHITECTURE.md#7-risks-and-open-questions), [GRAPH_HACKS_PLAN §0 rules](../planning/GRAPH_HACKS_PLAN.md#0-rules-to-check-first-from-a-similar-falkordb--wemakedevs-hackathon-confirm-for-this-one)

## Files

```
api/eval.py           python -m api.eval --suite re2 --system tt [--weights v1|v2] [--ablate …]
api/routes/eval.py    GET /eval (last stored run)
data/eval/            results JSON per run (weights + rules version in the file name)
```

## Tasks

- [ ] Eval runner: for each RE2 case, fresh `env:rcaeval-<system>` graph, replay, diagnose, compare root-cause service/op with the label. AC@1, AC@3.
- [ ] Ablations: no PageRank, no temporal rule, no mechanism rule, no footprint (weights v1 vs v2). Same cases, same seed.
- [ ] Memory: leave-one-out precision@3 for Q5 recall.
- [ ] Rerun the Jev cutoff calibration (`python -m api.agents.calibrate --env rcaeval-tt`) on every diagnosed RE2
  case and update `explanation.min_support` if the recommendation moves ([phase 7](phase-07-memory-llm-delivery.md)).
- [ ] Tune on a dev split only (grid over weights and rule `p`), evaluate on the held-out split, then **freeze** `weights.json` version and `rules_version`.
- [ ] Measure N1 (alert → verdict < 60 s) and N2 (Q1–Q5 p95 < 200 ms) on all three environments; record in the README.
- [ ] Determinism check on the full suite: two runs, identical results file.
- [ ] Hardening pass: every failure mode in [HLD §7](../HLD.md#7-failure-modes) tried once by hand (stop FalkorDB, unset the OpenRouter key, stop Jaeger, stop OpenConnector, crash mid-diagnosis).
- [ ] Security pass: no secrets in the graph or logs, CORS origin, read-only MCP with key, parameterized queries only (grep for f-strings near `query(`).
- [ ] Demo assets: script (OTel `paymentFailure` with the frontend-anchoring moment, flip-commerce `circuit-misconfig`, healthy baseline, what-if on Redis, RCAEval number), recorded backup video, README results table.
- [ ] Deliverables: public repo, README, demo video, deployment, project info; confirm the event's rules (FalkorDB primary, data public / self-owned, code after kickoff).

## Acceptance

- `python -m api.eval --suite re2 --system tt` prints AC@1, AC@3 and the ablation table; `GET /eval` returns the same numbers.
- Numbers are reported as measured, including ablations that don't help.
- N1 and N2 measured and written down; any miss has a note.

## Scalability

- **Eval is a regression suite.** Run it in CI (nightly or on changes to `search/`, `ingest/detect.py`, `weights.json`, rules) so accuracy can't silently drop as the code grows.
- **Versioned weights and rules** in every result file make results comparable over time.
- **Per-case fresh graphs** mean the eval parallelizes across processes if the suite grows.

## Risks / open questions

- Overfitting weights to RE2-TT: report the held-out split, and RE2-OB if time allows.
- If the OTel Demo won't run on the judging machine, demo from flip-commerce + RCAEval + the video.

## Done when

The accuracy table is in the README, weights and rules are frozen, the demo runs from a clean `docker compose up`, and all deliverables are submitted.
