# Phase 9: Live environments (OTel Demo, flip-commerce) and example runs

**Goal:** Epicenter diagnoses live faults on the OpenTelemetry Demo (multi-hop) and on flip-commerce (a real Mongo /
Redis failure in the user's own system), started from the `/runs` screen. Same writers, detectors and search as the
RCAEval path; only the adapter differs.

**Depends on:** phases 2, 6. **Unblocks:** 10 (demo).

## Spec

- [EXAMPLE_RUNS](../EXAMPLE_RUNS.md): [OTel Demo (§1)](../EXAMPLE_RUNS.md#1-opentelemetry-demo-primary-multi-hop), [flip-commerce (§2)](../EXAMPLE_RUNS.md#2-flip-commerce-your-system-design-journey) incl. scenarios, expected footprints, healthy baseline, limits
- [LLD §3.1 adapter table](../LLD.md#31-adapter-protocol), [LLD §11 config](../LLD.md#11-configuration)
- [ADR 0010](../adr/0010-example-environments.md), [HLD §5.1 ports](../HLD.md#51-ports)
- [API.md](../API.md#example-runs-and-eval) `GET /runs/scenarios`, `POST /runs`; [USER_FLOW Flow 7](../USER_FLOW.md)

## Files

```
api/ingest/otel.py           Jaeger /api/traces, Prometheus query_range, OpenSearch logs, flagd changes;
                             flip-commerce mode: collector file exporter (JSON lines), winston JSON + nginx logs
api/ingest/changes.py        flagd events, docker events, faults.py journal, manual changes
api/runs.py                  scenario registry + runner (POST /runs)
api/routes/runs.py
examples/otel-demo/          notes + fault script (flagd toggles)
examples/flip-commerce/      collector.yaml, run scripts (auto-instrumented start), faults.py
```

## Tasks

- [x] `otel` adapter, OTel Demo mode: Jaeger → `CallAgg` per 30 s tick, Prometheus `query_range` → `Series`, OpenSearch → `LogLine`, flagd flag changes → `ChangeEvent`. All reads 5 s timeout, 2 retries; failures go to `Incident.gaps`.
- [x] Check the flagd flag names in the demo's current config before wiring scenarios (`paymentFailure`, `adHighCpu`, `emailMemoryLeak`).
- [x] `otel` adapter, flip-commerce mode: tail the collector's JSON-lines file, winston JSON logs (`NODE_ENV=production`), nginx access log with upstream timings.
- [x] `examples/flip-commerce/`: collector config; start scripts that run `01-node` with `--import @opentelemetry/auto-instrumentations-node/register`; **never modify the source repo**. Go server skipped. `06-fastapi` skipped too: one app keeps the laptop free for faults, and nginx's `/fastapi/` route is wired for when it's needed.
- [x] `faults.py`: writes the `Change` node **before** acting; scenarios `mongo-primary-down`, `mongo-majority-lost`, `redis-down`, `cpu-saturation`, `circuit-misconfig`; each one reversible (`--undo`).
- [x] Scenario registry: id, env, title, how to trigger, how to undo, expected verdict (from EXAMPLE_RUNS tables). `POST /runs` writes the `Change`, triggers the fault, fires the alert, returns `incident_id`.
- [x] RCAEval scenarios listed from `RCAEVAL_DIR`.
- [x] Healthy-baseline run: k6 normal load, hand-fired alert, expect `no_root_cause`.
- [x] Fault Simulator demo moment: alert fired on `frontend` for `paymentFailure`, so the victim's small footprint is visible next to `payment/Charge`'s full one.

## Acceptance

- LLD §12 end-to-end: flip-commerce, stop the Mongo primary → incident → verdict names `mongodb` with the `docker stop` change.
- `circuit-misconfig` → `flip-node/*` with the config change; Mongo refuted (or `no_anomaly` in why-not).
- OTel `paymentFailure` → `payment/Charge`, change = flag on; footprint "explains N of M".
- Healthy baseline → `no_root_cause`.
- Each scenario's `--undo` returns the env to healthy.

## Results (2026-10-16)

Every scenario was started from `/runs` in Chrome and undone afterwards. The verdicts are re-diagnosed against the final
code; reruns are kept as numbered runs.

| Env | Scenario | Expected | Verdict |
|---|---|---|---|
| flip-commerce | `mongo-primary-down` | `no_root_cause` (failover < 1 s, reads stay up) | `no_root_cause` |
| flip-commerce | `mongo-majority-lost` | `mongodb`, kind `down` | `mongodb/findAndModify $cmd`, 0.80 |
| flip-commerce | `redis-down` | `redis`, kind `down` | `redis/GET`, 1.00 |
| flip-commerce | `circuit-misconfig` | `flip-node/*`, change config | `flip-node/GET /products`, 0.62 (Mongo runner-up) |
| flip-commerce | `cpu-saturation` | `flip-node/*`, saturation | `flip-node/GET /products`, 0.60 |
| flip-commerce | `healthy-baseline` | `no_root_cause` | `no_root_cause` |
| astronomy-shop | `paymentFailure` | `payment/Charge`, change = flag | `payment/oteldemo.PaymentService/Charge`, 0.83 |
| astronomy-shop | `adHighCpu` | `ad/*`, cpu | `ad/oteldemo.AdService/GetAds`, 1.00 |
| astronomy-shop | `emailMemoryLeak` | `no_root_cause` at demo traffic | `no_root_cause` |
| rcaeval-tt | cpu_1 / cpu_2 / delay_1 | unchanged | 0.60 / 0.58 / 0.53, same targets as phase 8 |

Acceptance notes:
- The LLD §12 "Mongo primary down → `mongodb`" check doesn't hold on this system, and that is the correct answer: the
  replica set fails over in under a second and reads stay up (`primaryPreferred`). Losing the majority is the outage
  that names `mongodb`. EXAMPLE_RUNS §2 has the details.
- `emailMemoryLeak` changed from "`email/*`, kind `mem`" to `no_root_cause`. At demo traffic the leak adds ~10% memory in
  the window and then plateaus.
- Bugs that only live data showed are listed in EXAMPLE_RUNS §1 and §2: end-time buckets, the cpu counter, weak
  self-blame, ingest-once by counter, a cp1252 crash in the fault runner, and the Jaeger base path.

## Scalability

- **New environment = adapter mode + scenario entries.** No change to search, agents or UI.
- **Changes are first-class and timestamped before the fault**, so attribution doesn't depend on log timing; the same
  path takes real deploy / CI webhooks later (`POST` a `ChangeEvent`).
- **Read-only towards sources** (N4): adapters use query APIs and file tails only; nothing writes back to the monitored system except the explicit fault scripts.
- **One env graph per environment** means running several environments later is just several ingest loops with different `ENV_NAME`s.
- Ceiling: one ingest loop per API process; a second live environment at the same time should get its own ingest worker.

## Risks / open questions

- OTel Demo needs ~6 GB RAM; record a backup video ([ARCHITECTURE §7](../ARCHITECTURE.md#7-risks-and-open-questions)).
- Port 8080 is shared by both environments: one at a time.
- flip-commerce is shallow (~2 hops); use it for the "real failure" story, not multi-hop.
- ~~**Q-d:** add `api/runs.py` (and the 30 s roll-up loop over `write.write_topology`) to [LLD §1](../LLD.md#1-package-layout).~~ Done.

## Done when

Every scenario in EXAMPLE_RUNS can be started from `/runs` and ends with the expected verdict.
