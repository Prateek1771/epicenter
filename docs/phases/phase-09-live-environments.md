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

- [ ] `otel` adapter, OTel Demo mode: Jaeger → `CallAgg` per 30 s tick, Prometheus `query_range` → `Series`, OpenSearch → `LogLine`, flagd flag changes → `ChangeEvent`. All reads 5 s timeout, 2 retries; failures go to `Incident.gaps`.
- [ ] Check the flagd flag names in the demo's current config before wiring scenarios (`paymentFailure`, `adHighCpu`, `emailMemoryLeak`).
- [ ] `otel` adapter, flip-commerce mode: tail the collector's JSON-lines file, winston JSON logs (`NODE_ENV=production`), nginx access log with upstream timings.
- [ ] `examples/flip-commerce/`: collector config; start scripts that run `01-node` with `--require @opentelemetry/auto-instrumentations-node/register` and `06-fastapi` with `opentelemetry-instrument`; **never modify the source repo**. Go server skipped.
- [ ] `faults.py`: writes the `Change` node **before** acting; scenarios `mongo-primary-down`, `mongo-majority-lost`, `redis-down`, `cpu-saturation`, `circuit-misconfig`; each one reversible (`--undo`).
- [ ] Scenario registry: id, env, title, how to trigger, how to undo, expected verdict (from EXAMPLE_RUNS tables). `POST /runs` writes the `Change`, triggers the fault, fires the alert, returns `incident_id`.
- [ ] RCAEval scenarios listed from `RCAEVAL_DIR`.
- [ ] Healthy-baseline run: k6 normal load, hand-fired alert, expect `no_root_cause`.
- [ ] Fault Simulator demo moment: alert fired on `frontend` for `paymentFailure`, so the victim's small footprint is visible next to `payment/Charge`'s full one.

## Acceptance

- LLD §12 end-to-end: flip-commerce, stop the Mongo primary → incident → verdict names `mongodb` with the `docker stop` change.
- `circuit-misconfig` → `flip-node/*` with the config change; Mongo refuted (or `no_anomaly` in why-not).
- OTel `paymentFailure` → `payment/Charge`, change = flag on; footprint "explains N of M".
- Healthy baseline → `no_root_cause`.
- Each scenario's `--undo` returns the env to healthy.

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
- **Q-d:** add `api/runs.py` and `api/ingest/topology.py` to [LLD §1](../LLD.md#1-package-layout).

## Done when

Every scenario in EXAMPLE_RUNS can be started from `/runs` and ends with the expected verdict.
