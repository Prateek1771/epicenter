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

- [x] Eval runner: for each RE2 case, fresh `env:eval-<system>` scratch graph (never the demo's `env:rcaeval-tt`), replay, diagnose, compare root-cause service/op with the label. AC@1, AC@3.
- [x] Ablations: no PageRank, no temporal rule, no mechanism rule, no footprint (weights v1 vs v2). Same cases, same seed.
- [x] Memory: leave-one-out precision@3 for Q5 recall.
- [x] Rerun the Jev cutoff calibration (`python -m api.agents.calibrate --env rcaeval-tt`) on every diagnosed RE2
  case and update `explanation.min_support` if the recommendation moves ([phase 7](phase-07-memory-llm-delivery.md)).
- [x] Tune on a dev split only (grid over weights and rule `p`), evaluate on the held-out split, then **freeze** `weights.json` version and `rules_version`. (Done over the weights only. Rule `p` wasn't gridded: re-scoring can't vary it without re-running the simulator for every combination. Add that when the rules change.)
- [x] Measure N1 (alert → verdict < 60 s) and N2 (Q1–Q5 p95 < 200 ms) on all three environments; record in the README.
- [x] Determinism check on the full suite: two runs, identical results file.
- [x] Hardening pass: every failure mode in [HLD §7](../HLD.md#7-failure-modes) tried once by hand (stop FalkorDB, unset the OpenRouter key, stop Jaeger, stop OpenConnector, crash mid-diagnosis).
- [x] Security pass: no secrets in the graph or logs, CORS origin, read-only MCP with key, parameterized queries only (grep for f-strings near `query(`).
- [ ] Demo assets: script ([EXAMPLE_RUNS §7](../EXAMPLE_RUNS.md#7-demo-script-phase-10), done), README results table (done), recorded backup video (**yours**: not done). Original: (OTel `paymentFailure` with the frontend-anchoring moment, flip-commerce `circuit-misconfig`, healthy baseline, what-if on Redis, RCAEval number), recorded backup video, README results table.
- [ ] Deliverables (**yours**: submission, video, deployment plan per [phase 11](phase-11-production-demo.md)): public repo, README, demo video, deployment plan ([DEPLOYMENT_PLAN.md](../DEPLOYMENT_PLAN.md)), project info; confirm the event's rules (FalkorDB primary, data public / self-owned, code after kickoff).

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

## Hardening pass (2026-10-17)

Each [HLD §7](../HLD.md#7-failure-modes) failure mode tried once on the local stack, then everything restored
(`/health` all `ok` afterwards).

| Failure | How | Observed | Result |
|---|---|---|---|
| FalkorDB down | `docker compose stop falkordb` | API `503 GRAPH_UNAVAILABLE`; `/health` `degraded`; UI shows "Degraded" and "The graph is offline". After `start`, the API answers again in ~6 s without a restart; falkordb-mcp crashes with the DB and comes back by its restart policy (~15 s) | pass |
| Telemetry source down | OTel Demo (Jaeger) not running | `POST /runs` → `503 ENV_NOT_RUNNING` with the start command. A source missing mid-ingest lands in `Incident.gaps` (`test_otel_adapter`, `test_rcaeval`) | pass |
| OpenRouter down | `OPENROUTER_API_KEY=` for one agent-flow run | Verdict unchanged (`payment/Charge`, 0.999); explanation is the template, every claim `template` (hard rule 12) | pass |
| Jev down | (shares the OpenRouter key; simulated) | Cited claims kept as `unverified` (`test_jev_down_keeps_cited_claims_unverified`) | pass |
| OpenConnector down | `docker compose stop open-connector`, deliver to Slack | `200` with that target `ok:false, UPSTREAM_ERROR` in ~4 s; stored on the incident, retry button | pass |
| Crash mid-diagnosis | `POST …/diagnose?force=true`, then `docker kill` the api | Incident stays `diagnosing` (run 58); `POST …/diagnose` resumes the **same** run to `diagnosed` with the same verdict | pass |

## Security pass (2026-10-17)

- **Cypher:** no f-string, `%` or `.format` builds query text. String formatting in `api/graph.py` touches only graph
  keys (`env:` / `scratch:`) and stream names. Every query is a `QUERIES` entry with `$params`.
- **Secrets in the graph:** every node and edge property of every graph (`env:*`, `kb:*`, `smoke:*`; 15k nodes) was
  scanned for `sk-or-`, `xoxb-`, `lin_api_`, `ghp_`, `AKIA…`, `Bearer …`. Result: 0 hits.
- **Secrets in the logs:** api and web container logs scanned for the same patterns. Result: 0 hits.
- **CORS:** a single origin (`WEB_ORIGIN`).
- **falkordb-mcp:** `FALKORDB_DEFAULT_READONLY=true` plus `MCP_API_KEY`; the ask agent allowlists the read-only tools
  (HLD §9).
- **`.env*`:** git-ignored.

## Results (2026-10-17)

The full tables are in the [README](../../README.md#results-measured-2026-10-17).
- **Accuracy:** RE2-TT, 90 cases, frozen `2026-10-17.v5` / rules `2026-10-16`. Held-out AC@1 **90.0%**, all
  87.8% / 88.9%. Before tuning (v3) it was 61.1% overall and 66.7% held-out.
- **Ablations:** PageRank is the biggest contributor (−11.1 at @1). The mechanism rule and the footprint are worth
  −4.5 each at @1. **No temporal rule scores better** (92.2%): reported as a loss and kept, because the live scenarios
  depend on onset order.
- **Memory:** leave-one-out P@3 is 13.0%. The signature doesn't separate RE2-TT services that fail in the same shape.
- **Jev cutoff:** rerun on the v5 RCAEval incidents (`data/calibration/jev-2026-10-17.json`). It recommended 0.60, but
  on fewer claims (33 / 78). The 2026-10-16 run saw a false claim at 0.57, so the cutoff over both runs stays
  **0.65**, unchanged.
- **Freeze history:**
  - v4 = the dev-split grid.
  - v4 flipped flip-commerce `circuit-misconfig` to a victim. RCAEval can't tune `change_match` (it has no changes),
    so v5 raises that weight to 0.25 and scales the rest uniformly.
  - v5: the RE2-TT numbers equal v4's, and all 11 recorded live incidents keep their root-cause operation
    ([LLD §6.3](../LLD.md#63-weightsjson)).
- **Determinism:** result files 0003/0004 (v4) and 0005/0006 (v5) are byte-identical in pairs.
- **N1:**
  - RCAEval replay plus diagnosis: p95 15.4 s, max 21.0 s.
  - Diagnosis only: p95 534 ms (RCAEval), 178–843 ms on the live incidents.
  - Gap: live alert → verdict, including the Jaeger/Prometheus ingest, was not re-measured this phase, because that
    needs fresh faults on the example environments. It was under a minute in the phase-9 runs.
- **N2:** all Q1–Q5 p95 ≤ 52 ms (Q5 the slowest), against a 200 ms target.
- **Bugs found by the full suite:**
  - RE2-TT log rows with a null message crashed the replay. Fixed and tested
    (`test_logs_skip_rows_without_a_message`).
  - The eval's N2 list named `Q4`, which runs as `Q4a` / `Q4_blame` / `Q4b`. Fixed.
