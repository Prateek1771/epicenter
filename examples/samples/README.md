# Synthetic samples (Demo 1)

26 generated incidents, committed so an evaluator needs to download or generate nothing. Each folder is one case in
the RCAEval file layout, so it goes through the same ingest as the real benchmark:

| File | What |
|---|---|
| `traces.parquet`, `metrics.parquet`, `logs.parquet` | The telemetry: 10 minutes before the fault and 5 after (`mem`: 6 hours of metrics, a slow leak) |
| `inject_time.txt` | When the fault starts |
| `changes.jsonl` | `config` cases only: the change event that precedes the fault |
| `labels.json` | The answer: faulty service and operation, or `no_root_cause`. Read by the eval and the `/runs` "matches" check only, never ingested |

Three system sizes, each with every fault kind:

| Size | Services | Cases | Measured AC@1 (seed 1, weights `2026-10-17.v5`) |
|---|---|---|---|
| `synth-small_*` | 5 | 8 (`two` needs two independent services, which this topology doesn't have) | 8 / 8 |
| `synth-medium_*` | 30 | 9 | 7 / 9 |
| `synth-huge_*` | 300 | 9 | 5 / 9 |

Faults:
- `cpu`, `delay`, `error`, `down`;
- `mem`, a 3-hour leak found by the slow-burn pass;
- `config`, which has a change event;
- `loud-victim`: the service in front fails loudly, and the quiet datastore behind it is the cause;
- `two`, two independent faults;
- `healthy`: expect `no_root_cause`.

The misses are kept on purpose and explained in [EXAMPLE_RUNS §4](../../docs/EXAMPLE_RUNS.md#4-synthetic-samples-self-made).

**Run one:**
- open http://localhost:3001/runs → *Demo 1 · Synthetic*;
- or use the **Run a sample incident** button on an empty `/incidents`;
- or, from the command line:
  `docker compose exec api python -m api.ingest.rcaeval --case synth-small_mongodb_loud-victim_1 --env synthetic`.

The API reads this folder (`SAMPLES_DIR`, read-only). A case with the same name in `RCAEVAL_DIR` takes precedence.

**Regenerate** (deterministic: seed 1 gives these exact bytes, which `tests/test_runs.py` checks):
```bash
docker compose exec api python examples/synthetic/gen.py --size medium --fault cpu --seed 1 --out data/rcaeval
```
