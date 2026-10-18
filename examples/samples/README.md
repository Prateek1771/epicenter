# Synthetic samples (Demo 1)

We generated 26 incidents and committed them, so an evaluator doesn't need to download or generate anything. Each
folder is one case in the RCAEval file layout, so it goes through the same ingest as the real benchmark:

| File | What |
|---|---|
| `traces.parquet`, `metrics.parquet`, `logs.parquet` | The telemetry, 10 minutes before the fault and 5 after (`mem` has 6 hours of metrics for a slow leak) |
| `inject_time.txt` | When the fault starts |
| `changes.jsonl` | `config` cases only. The change event that comes before the fault |
| `labels.json` | The answer, either the faulty service and operation or `no_root_cause`. Only the eval and the `/runs` "matches" check read it. We never ingest it |

There are three system sizes, each with every fault kind:

| Size | Services | Cases | Measured AC@1 (seed 1, weights `2026-10-17.v5`) |
|---|---|---|---|
| `synth-small_*` | 5 | 8 (`two` needs two independent services, and this topology doesn't have them) | 8 / 8 |
| `synth-medium_*` | 30 | 9 | 7 / 9 |
| `synth-huge_*` | 300 | 9 | 5 / 9 |

Faults:
- `cpu`, `delay`, `error`, `down`;
- `mem`, a 3-hour leak that the slow-burn pass finds;
- `config`, which has a change event;
- `loud-victim`, where the service in front fails loudly and the quiet datastore behind it is the cause;
- `two`, two independent faults;
- `healthy`, where you should expect `no_root_cause`.

We kept the misses on purpose. [EXAMPLE_RUNS §4](../../docs/EXAMPLE_RUNS.md#4-synthetic-samples-self-made) explains them.

To run one:
- open http://localhost:3001/runs → *Demo 1 · Synthetic*;
- or use the **Run a sample incident** button on an empty `/incidents`;
- or run it from the command line:
  `docker compose exec api python -m api.ingest.rcaeval --case synth-small_mongodb_loud-victim_1 --env synthetic`.

The API reads this folder (`SAMPLES_DIR`, read-only). If `RCAEVAL_DIR` has a case with the same name, that one wins.

To regenerate, run the command below. It is deterministic: seed 1 gives these exact bytes, and `tests/test_runs.py`
checks that.
```bash
docker compose exec api python examples/synthetic/gen.py --size medium --fault cpu --seed 1 --out data/rcaeval
```
