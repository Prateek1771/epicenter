# OpenTelemetry Demo (Demo 3: real-world)

The [OpenTelemetry Demo](https://github.com/open-telemetry/opentelemetry-demo) (Apache-2.0) is an online shop of
~15 microservices in 8 languages with real traces, metrics and logs. Epicenter uses it unmodified, pinned at tag
**3.1.0**. Faults are the demo's own feature flags, flipped live by `faults.py`.

This folder holds only Epicenter's side:

| File | What |
|---|---|
| `run.py` | `up` / `status` / `down`. On the first `up` it clones the demo into `upstream/` (git-ignored), then starts the demo's core and observability stack plus `compose.epicenter.yaml`, and the host fault runner |
| `compose.epicenter.yaml` | A thin layer: publishes the Jaeger and OpenSearch query ports Epicenter reads, plus two compatibility fixes; nothing else changes |
| `faults.py` | The scenarios (`paymentFailure`, `adHighCpu`, …): each one flips a flag in the demo's flag file |

```bash
python examples/otel-demo/run.py up       # first run: clone (~15 MB) + pull ~10 GB of images
python examples/otel-demo/run.py status
python examples/otel-demo/run.py down     # stops the containers, keeps volumes
```

Set `DEMO_DIR` to use a clone elsewhere. Needs 8 CPUs / 16 GB for Docker, ports 8080 and 4317 free. After a fresh
start, wait **25 minutes** before the first fault, then start scenarios from `/runs`. Details:
[docs/SETUP.md](../../docs/SETUP.md) (Demo 3) and [docs/EXAMPLE_RUNS.md](../../docs/EXAMPLE_RUNS.md) §1.
