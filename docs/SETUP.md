# Setup guide: install, run and evaluate Epicenter

For judges, evaluators and anyone trying Epicenter. It gets you from nothing to a diagnosed incident on screen, at the
size your machine can handle. Epicenter is the root-cause engine described in the [README](../README.md).

> Samples marked **planned, not built yet** are specified in [phase 11](phases/phase-11-production-demo.md).
> Everything else works today.

---

## 1. Three ways in

| Way | You need | Time | You see |
|---|---|---|---|
| **A. Watch** | a browser | 5 min | the recorded demo video: the full product, live faults included. The event demo runs on the presenter's laptop ([ADR 0014](adr/0014-local-event-demo.md)); a hosted deployment is planned in [DEPLOYMENT_PLAN.md](DEPLOYMENT_PLAN.md) |
| **B. Local, quick** | Docker, 2–4 cores / 4–8 GB for Docker | ~15 min | demos 1 and 2: a self-made sample with a known answer, then recorded benchmark faults (RCAEval) |
| **C. Local, live** | Docker, 8 cores / 16 GB for Docker | ~30 min | demo 3: faults injected into a running microservice shop (OTel Demo) and diagnosed live |

Not sure which fits? Run the system evaluator ([§3](#3-run-the-system-evaluator-first)). It measures the machine and
tells you.

## 2. What your machine can run

Epicenter ships three demos: **small** (synthetic), **medium** (RCAEval replays) and **real-world** (OTel Demo live).
The evaluator picks the biggest one your machine can run. What counts is **what Docker can use**, not what the machine
has: on Windows and macOS, Docker Desktop runs in a VM with its own CPU and memory limit.

| Tier | Docker CPUs / memory | Disk free | Also needs | Runs |
|---|---|---|---|---|
| 0 | below tier 1 | | | nothing local: watch the demo video |
| 1 Small | 2+ / 4 GB | 10 GB | | core services, smoke test, fixture self-test, **demo 1: synthetic** |
| 2 Medium | 4+ / 8 GB | 20 GB | internet | + full test suite, **demo 2: RCAEval replays** + the accuracy eval |
| 3 Real-world | 8+ / 16 GB | 40 GB | the OTel Demo clone | + **demo 3: OTel Demo live faults** |

**Set Docker's limits first:**
- **Windows:** Docker Desktop with the WSL2 backend. The limit is in `%UserProfile%\.wslconfig`:
  ```ini
  [wsl2]
  processors=8
  memory=16GB
  ```
  Then run `wsl --shutdown` and restart Docker Desktop.
- **macOS:** Docker Desktop → Settings → Resources → CPUs / Memory.
- **Linux:** Docker uses the whole machine. For demo 3 set `FAULT_RUNNER_BIND=0.0.0.0` in `.env`: on Linux
  containers reach the host through the Docker bridge, not loopback ([ADR 0012](adr/0012-host-fault-runner.md)), and
  `sudo sysctl -w vm.max_map_count=262144` (OpenSearch needs it).

## 3. Run the system evaluator first

`syscheck.py` needs only Python 3.10+ (no packages). It looks at the machine, picks a tier, and prints what to run.
By default it changes nothing.

```bash
git clone https://github.com/Prateek1771/epicenter.git
cd epicenter
python syscheck.py                 # probe + recommend (read-only, ~15 s)
python syscheck.py --run           # also run the tier's checks (starts Epicenter's own containers)
python syscheck.py --run --live    # also inject live faults (asks before each one, undoes it after)
python syscheck.py --minutes 10    # only suggest runs that fit in 10 minutes
python syscheck.py --tier 1        # force a smaller tier
python syscheck.py --json          # machine-readable output
```

Output on the authors' laptop (2026-10-17, `--run`):

```
  Windows 11 AMD64 | host 8 CPUs / 31.3 GB | Docker VM 8 CPUs / 15.3 GB | disk free 167.6 GB | CPU 5.6x ref

  TIER 3: Real-world (every tier's conditions hold)

  Running:
  PASS  smoke                                        exit 0              -> 6/6 PASS                     1.4 s
  PASS  selftest                                     exit 0              -> 7/7 PASS                     1.8 s
  PASS  synthetic small cpu                          svc-0/*             -> svc-0/op /svc-0/r3           5.9 s
  PASS  synthetic small healthy                      no_root_cause       -> no_root_cause                3.6 s
  PASS  pytest (full)                                exit 0              -> 212 passed, 2 skipped       55.1 s
  PASS  RCAEval re2tt_ts-auth-service_cpu_2          ts-auth-service/*   -> ts-auth-service/UserRep…    15.4 s
  PASS  RCAEval re2tt_ts-order-service_delay_1       ts-order-service/*  -> ts-order-service/find …     13.2 s
  PASS  N2 query p95                                 < 200 ms            -> 8.0 ms                       0.0 s
  report: data/syscheck/0005-20261017T123844Z
```

Add `--live` for demo 3 (asks before starting the OTel Demo, undoes each fault).

What `--run` does per tier, the thresholds and the safety rules: [LLD §13](LLD.md#13-system-evaluator-syscheck).
In short, it never deletes data (`down -v`), it never touches an example environment without `--live` and your
`y`, and every fault it injects it also undoes.

## 4. Install

### 4.1 Prerequisites

| Need | Version | Tier |
|---|---|---|
| Git | any | all |
| Docker Desktop (Windows / macOS) or Docker Engine + Compose plugin (Linux) | Compose 2.24+ | all |
| Python | 3.10+ (3.12 recommended) | evaluator, example env scripts |
| OpenRouter API key | | optional: AI explanations. **Verdicts work without it** |

### 4.2 Configure

```bash
git clone https://github.com/Prateek1771/epicenter.git
cd epicenter
cp .env.example .env                   # PowerShell: Copy-Item .env.example .env
```

Edit `.env`:

| Key | Required | Set to |
|---|---|---|
| `FALKORDB_PASSWORD`, `MCP_API_KEY` | yes | any long random strings (`openssl rand -hex 24`) |
| `FAULT_RUNNER_TOKEN` | live runs | a long random string |
| `OPENROUTER_API_KEY` | no | your key, for AI explanations |
| `OPENCONNECTOR_*`, `SLACK_CHANNEL`, `LINEAR_TEAM_ID` | no | only if you want Slack / Linear delivery |
| image tags (`FALKORDB_TAG`, …) | yes | keep the pinned values from `.env.example` |

Leave the rest as they are. `.env` is git-ignored; never commit it.

### 4.3 Start

```bash
docker compose up -d                   # falkordb, falkordb-mcp, api, web, open-connector (first build ~5 min)
docker compose ps                      # all "healthy" / "running"
docker compose exec api python -m api.smoke_falkordb   # → 6/6 PASS
```

On a tier-1 machine, start only the core: `docker compose up -d falkordb api web`.

| URL | What |
|---|---|
| http://localhost:3001 | Epicenter landing page; the app starts at `/incidents` |
| http://localhost:8000/docs | API (Swagger) |
| http://localhost:3002 | FalkorDB browser (host `localhost`, port 6379 from inside its container, or `localhost:6380` from your machine; password from `.env`) |

The API creates its indexes, owners and runbooks on startup.

## 5. The three demos

Each demo says what verdict to expect, measured on 2026-10-17. A run that misses is still worth reporting; that is how
the engine improved in phase 9 ([EXAMPLE_RUNS §1](EXAMPLE_RUNS.md#1-opentelemetry-demo-primary-multi-hop)).

### Demo 1: small, synthetic (tier 1+)

A generated 5-service system with one injected fault and a known answer, in the RCAEval file layout, so it goes
through the same ingest as the benchmark. Any laptop, no internet.

**Nothing to prepare:** the samples are committed in [`examples/samples/`](../examples/samples/README.md). That's 26
cases, every fault at three sizes:

| Size | Services | Cases | Expect (AC@1) |
|---|---|---|---|
| small | 5 | 8 | 8 / 8 |
| medium | 30 | 9 | 7 / 9 |
| huge | 300 | 9 | 5 / 9 |

The misses are explained in [EXAMPLE_RUNS §4](EXAMPLE_RUNS.md#4-synthetic-samples-self-made). Open
http://localhost:3001/incidents → **Run a sample incident**, or `/runs` → *Demo 1 · Synthetic*, where each card says
whether the verdict matched.

From the command line:
```bash
docker compose exec api python -m api.selftest                                                     # 7 hand-made graphs → 7/7 PASS
docker compose exec api python examples/synthetic/gen.py --size small --fault cpu --seed 1 --run   # one JSON line: expected, got, ok
docker compose exec api python -m api.eval --suite synth --size small                              # every fault: 8/8, ~4 s of diagnosis
```
Faults: `cpu`, `mem` (a 3-hour leak, found by the slow-burn pass),
`delay`, `error`, `down`, `config` (with a change event), `loud-victim`, `healthy` (expect `no_root_cause`).

### Demo 2: medium, RCAEval replays (tier 2+)

Real faults recorded on the Train-Ticket system (64 services) by the RCAEval benchmark, ~25 MB per case:
```bash
docker compose exec api python -m api.ingest.rcaeval --case re2tt_ts-auth-service_cpu_2 --env rcaeval-tt --download
```
Open http://localhost:3001/incidents → `rc-re2tt_ts-auth-service_cpu_2`. Expect `ts-auth-service/*`, kind `cpu`.
Also try `re2tt_ts-auth-service_cpu_1` and `re2tt_ts-order-service_delay_1`, or start them from `/runs`.

The accuracy number (all 90 RE2-TT cases, ~35 min): AC@1 87.8%, held-out 90.0%.
```bash
docker compose exec api python -m api.eval --suite re2 --system tt --download
```

### Demo 3: real-world, OTel Demo live (tier 3)

The OpenTelemetry Demo: an online shop of ~15 microservices in 8 languages with real traces, metrics and logs. Faults
are its own feature flags, flipped live. `run.py up` loads the demo's minimal core plus its observability stack
(Jaeger, Prometheus, OpenSearch).
The demo isn't copied into this repo: `run.py up` clones upstream's tag `3.1.0` into the git-ignored
`examples/otel-demo/upstream/` the first time (set `DEMO_DIR` to use a clone elsewhere). See
[examples/otel-demo/README.md](../examples/otel-demo/README.md).
```bash
python examples/otel-demo/run.py up        # first run: clone + pull ~10 GB of images; also starts the fault runner
python examples/otel-demo/run.py status
```
After a fresh start let it warm up for **25 minutes** before the first fault (later faults need 10 minutes apart):
Epicenter compares the fault window with the minutes before it, and a cold demo stalls when a flag flips. On
2026-10-17 a `paymentFailure` 10 minutes after start blamed `postgresql` (the flag reload slowed the still-cold
product-catalog / postgres and checkouts stalled, so payment's errors were too few); 27 minutes after start it gave
`payment/Charge` at 0.99. Then open `/runs`:

| Scenario | Expect | Measured 2026-10-17 |
|---|---|---|
| `paymentFailure` | `payment/…/Charge`, change "flag paymentFailure → 50%" | ✓ 0.99, found in 0.8 s |
| `adHighCpu` | `ad/…/GetAds`, kind `cpu` | ✓ 0.999, found in 2.4 s |
| `emailMemoryLeak` | `no_root_cause` or `email/…`, depending on how far the leak got | `email/POST /send_order_confirmation` |

Undo each one from its card before the next, and wait a few minutes in between. `run.py down` when you're done.

Other environments were used while building Epicenter (flip-commerce, synthetic medium / huge); their runs are recorded
in [EXAMPLE_RUNS](EXAMPLE_RUNS.md) but aren't part of the demo set.

## 6. A 10-minute tour of the UI

1. **Incidents** (`/`): one row per incident, with its status and verdict.
2. **Incident page:** the canvas fills live as agents work: suspects appear, get checked, and are confirmed or ruled
   out. The verdict card shows the root cause, its confidence, the graph path from cause to alert, and the change
   that preceded it.
3. **Fault Simulator:** click a suspect. Its predicted footprint lights up and reads "explains N of M" against what
   actually broke. In `paymentFailure`, compare the runner-up `checkout` ("explains 1 of 5") with `payment/Charge`
   (the whole chain).
4. **Why not X:** every ruled-out suspect says why (started too late, no anomaly, footprint doesn't match).
5. **Memory:** similar past incidents and what fixed them.
6. **What-if** (`/simulate`): "what breaks if `redis` fails?" before you ship.
7. **Runs** (`/runs`): start a scenario, watch it count down to the alert, open the incident, undo.

Things to check as a judge:
- the same input gives the same answer (rerun an incident: new numbered run, identical scores);
- it says `no_root_cause` on a healthy system instead of inventing one;
- the verdict still appears with no OpenRouter key; only the explanation text changes.

## 7. Tests

```bash
docker compose exec api pytest -q                 # needs FalkorDB up; ~4 min; "live" tests (real OpenRouter) skip
docker compose exec api ruff check .
cd web && npm ci && npm test && npm run lint      # web unit tests + lint
```

## 8. Troubleshooting

| Symptom | Fix |
|---|---|
| `bind: address already in use` | Another program holds the port. See the port table in [HLD §5.1](HLD.md#51-ports); stop it or change the host port |
| Containers restart or are killed (exit 137) | Docker is out of memory: raise its limit (§2) or drop a tier |
| OTel Demo stuck at "dependency failed to start" | Use `run.py up` (it adds `compose.epicenter.yaml`, which fixes a healthcheck); give Docker 16 GB |
| OpenSearch exits on Linux | `sudo sysctl -w vm.max_map_count=262144` |
| Everything is slow, checkout p95 in seconds with no fault | The machine is overloaded; the load generator is already at 10 users. Give Docker more memory, or stay with demos 1–2 |
| `/runs` says "Fault runner not reachable" | Start the env with its `run.py up` (it starts the runner). On Linux set `FAULT_RUNNER_BIND=0.0.0.0` |
| `run.py` can't find the demo clone | Set `DEMO_DIR` (the default is the authors' Windows path) |
| "AI explanation unavailable" | `OPENROUTER_API_KEY` is empty or OpenRouter is down. The verdict is still valid |
| Smoke test fails on the vector index while the machine is busy | Rerun it when the machine is idle; the index builds in the background |

## 9. Presenter demo (local)

The event demo runs on the presenter's laptop ([ADR 0014](adr/0014-local-event-demo.md)). A hosted version is planned
and scripted, not run: [DEPLOYMENT_PLAN.md](DEPLOYMENT_PLAN.md).

| When | Step |
|---|---|
| Day before | `python syscheck.py --run --live` (expect tier 3); run demo 2 so a rehearsal RCAEval incident is in the graph, and generate one synthetic case |
| T−35 min | `docker compose up -d`; `python examples/otel-demo/run.py up`; let it warm up ≥ 25 min (a cold demo misses: §5, demo 3) |
| T−5 min | `/runs`: ready dots green for `astronomy-shop`; the rehearsal incident open in a second tab |
| Demo | small → medium → real-world: a synthetic case from `/runs`, the RCAEval incident, then OTel `paymentFailure` live (Fault Simulator moment on `frontend`); what-if on `redis` |
| Right after | `/runs` → Undo on anything still in; `python examples/otel-demo/run.py down` |

Fallback: the recorded video.

## 10. Stop and clean up

```bash
python examples/otel-demo/run.py down        # stops the demo, keeps its data
docker compose stop                          # Epicenter, keeps the graphs
docker compose down                          # removes containers, keeps the graphs
docker compose down -v                       # also deletes every graph and incident: only if you mean it
```
