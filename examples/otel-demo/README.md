# OpenTelemetry Demo (Demo 3: real-world)

The [OpenTelemetry Demo](https://github.com/open-telemetry/opentelemetry-demo) (Apache-2.0) is an online shop of
~15 microservices in 8 languages, with real traces, metrics and logs. We use it unmodified, pinned at tag **3.1.0**.
The faults are the demo's own feature flags, and `faults.py` flips them live.

This folder holds only our side:

| File | What |
|---|---|
| `run.py` | `up` / `status` / `down`. The first `up` clones the demo into `upstream/` (git-ignored). Then it starts the demo's core and observability stack plus `compose.epicenter.yaml`, and the host fault runner |
| `compose.epicenter.yaml` | A thin layer. It publishes the Jaeger and OpenSearch query ports Epicenter reads and adds two compatibility fixes. Nothing else changes |
| `faults.py` | The scenarios (`paymentFailure`, `adHighCpu`, …). Each one flips a flag in the demo's flag file |

```bash
python examples/otel-demo/run.py up       # first run: clone (~15 MB) + pull ~10 GB of images
python examples/otel-demo/run.py status
python examples/otel-demo/run.py down     # stops the containers, keeps volumes
```

Set `DEMO_DIR` to use a clone elsewhere. You need 8 CPUs / 16 GB for Docker, and ports 8080 and 4317 free. After a
fresh start, wait **25 minutes** before the first fault, then start scenarios from `/runs`. For details see
[docs/SETUP.md](../../docs/SETUP.md) (Demo 3) and [docs/EXAMPLE_RUNS.md](../../docs/EXAMPLE_RUNS.md) §1.
