# Setup guide: install, run and evaluate Epicenter

We wrote this for judges, evaluators and anyone trying Epicenter. It takes you from a clean machine to a diagnosed
incident on screen, at the size your machine can handle. The [README](../README.md) explains what Epicenter is.

> Samples marked **planned, not built yet** are specified in [phase 11](phases/phase-11-production-demo.md).
> Everything else works today.

---

## 1. Three ways in

| Way | You need | Time | You see |
|---|---|---|---|
| **A. Watch** | a browser | 5 min | the recorded demo video, with the full product and live faults. We run the event demo on the presenter's laptop ([ADR 0014](adr/0014-local-event-demo.md)). A hosted deployment is planned in [DEPLOYMENT_PLAN.md](DEPLOYMENT_PLAN.md) |
| **B. Local, quick** | Docker, 2–4 cores / 4–8 GB for Docker | ~15 min | demos 1 and 2. A self-made sample with a known answer, then recorded benchmark faults (RCAEval) |
| **C. Local, live** | Docker, 8 cores / 16 GB for Docker | ~30 min | demo 3. We inject faults into a running microservice shop (OTel Demo) and diagnose them live |

Not sure which fits? Run the system evaluator ([§3](#3-run-the-system-evaluator-first)). It measures your machine and
tells you.

## 2. What your machine can run

Epicenter ships three demos: **small** (synthetic), **medium** (RCAEval replays) and **real-world** (OTel Demo live).
The evaluator picks the biggest one your machine can run. It goes by **what Docker can use**, not by what the machine
has. On Windows and macOS, Docker Desktop runs in a VM with its own CPU and memory limit.

| Tier | Docker CPUs / memory | Disk free | Also needs | Runs |
|---|---|---|---|---|
| 0 | below tier 1 | | | nothing local, watch the demo video |
| 1 Small | 2+ / 4 GB | 10 GB | | core services, smoke test, fixture self-test, **demo 1: synthetic** |
| 2 Medium | 4+ / 8 GB | 20 GB | internet | + full test suite, **demo 2: RCAEval replays** + the accuracy eval |
| 3 Real-world | 8+ / 16 GB | 40 GB | the OTel Demo clone | + **demo 3: OTel Demo live faults** |

Set Docker's limits first.
- On Windows, use Docker Desktop with the WSL2 backend. The limit lives in `%UserProfile%\.wslconfig`:
  ```ini
  [wsl2]
  processors=8
  memory=16GB
  ```
  Then run `wsl --shutdown` and restart Docker Desktop.
- On macOS, go to Docker Desktop → Settings → Resources → CPUs / Memory.
- On Linux, Docker uses the whole machine. For demo 3, set `FAULT_RUNNER_BIND=0.0.0.0` in `.env`, because Linux
  containers reach the host through the Docker bridge, not loopback ([ADR 0012](adr/0012-host-fault-runner.md)). Also
  run `sudo sysctl -w vm.max_map_count=262144`, which OpenSearch needs.

## 3. Run the system evaluator first

`syscheck.py` needs only Python 3.10+ and no packages. It looks at the machine, picks a tier, and prints what to run.
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

Here is the output on our laptop (2026-10-17, `--run`):

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

Add `--live` for demo 3. It asks before starting the OTel Demo and undoes each fault.

[LLD §13](LLD.md#13-system-evaluator-syscheck) covers what `--run` does per tier, the thresholds and the safety rules.
In short, it never deletes data (`down -v`). It never touches an example environment unless you pass `--live` and
answer `y`. It undoes every fault it injects.

## 4. Install

### 4.1 Prerequisites

| Need | Version | Tier |
|---|---|---|
| Git | any | all |
| Docker Desktop (Windows / macOS) or Docker Engine + Compose plugin (Linux) | Compose 2.24+ | all |
| Python | 3.10+ (3.12 recommended) | evaluator, example env scripts |
| OpenRouter API key | | optional, for AI explanations. **Verdicts work without it** |

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

Leave the rest alone. Git ignores `.env`. Never commit it.

### 4.3 Start

```bash
docker compose up -d                   # falkordb, falkordb-mcp, api, web, open-connector (first build ~5 min)
docker compose ps                      # all "healthy" / "running"
docker compose exec api python -m api.smoke_falkordb   # → 6/6 PASS
```

On a tier-1 machine, start only the core with `docker compose up -d falkordb api web`.

| URL | What |
|---|---|
| http://localhost:3001 | Epicenter landing page. The app starts at `/incidents` |
| http://localhost:8000/docs | API (Swagger) |
| http://localhost:3002 | FalkorDB browser. Host `localhost`, port 6379 from inside its container, or `localhost:6380` from your machine. The password is in `.env` |

On startup the API creates its indexes, owners and runbooks.

## 5. The three demos

Each demo lists the verdict to expect, as we measured it on 2026-10-17. If a run misses, please still report it. That
is how we improved the engine in phase 9 ([EXAMPLE_RUNS §1](EXAMPLE_RUNS.md#1-opentelemetry-demo-primary-multi-hop)).

### Demo 1: small, synthetic (tier 1+)

A generated 5-service system with one injected fault and a known answer. It uses the RCAEval file layout, so it goes
through the same ingest as the benchmark. It runs on any laptop with no internet.

There is nothing to prepare. The samples are committed in [`examples/samples/`](../examples/samples/README.md): 26
cases, every fault at three sizes.

| Size | Services | Cases | Expect (AC@1) |
|---|---|---|---|
| small | 5 | 8 | 8 / 8 |
| medium | 30 | 9 | 7 / 9 |
| huge | 300 | 9 | 5 / 9 |

[EXAMPLE_RUNS §4](EXAMPLE_RUNS.md#4-synthetic-samples-self-made) explains the misses. Open
http://localhost:3001/incidents → **Run a sample incident**, or `/runs` → *Demo 1 · Synthetic*. Each card there says
whether the verdict matched.

From the command line:
```bash
docker compose exec api python -m api.selftest                                                     # 7 hand-made graphs → 7/7 PASS
docker compose exec api python examples/synthetic/gen.py --size small --fault cpu --seed 1 --run   # one JSON line: expected, got, ok
docker compose exec api python -m api.eval --suite synth --size small                              # every fault: 8/8, ~4 s of diagnosis
```
The faults are `cpu`, `mem` (a 3-hour leak that the slow-burn pass finds),
`delay`, `error`, `down`, `config` (with a change event), `loud-victim`, and `healthy` (expect `no_root_cause`).

### Demo 2: medium, RCAEval replays (tier 2+)

The RCAEval benchmark recorded these real faults on the Train-Ticket system (64 services). Each case is ~25 MB:
```bash
docker compose exec api python -m api.ingest.rcaeval --case re2tt_ts-auth-service_cpu_2 --env rcaeval-tt --download
```
Open http://localhost:3001/incidents → `rc-re2tt_ts-auth-service_cpu_2`. Expect `ts-auth-service/*`, kind `cpu`.
Also try `re2tt_ts-auth-service_cpu_1` and `re2tt_ts-order-service_delay_1`, or start them from `/runs`.

For the accuracy number, run all 90 RE2-TT cases (~35 min). We got AC@1 87.8%, and 90.0% on the held-out cases.
```bash
docker compose exec api python -m api.eval --suite re2 --system tt --download
```

### Demo 3: real-world, OTel Demo live (tier 3)

The OpenTelemetry Demo is an online shop of ~15 microservices in 8 languages, with real traces, metrics and logs. The
faults are its own feature flags, flipped live. `run.py up` loads the demo's minimal core plus its observability stack
(Jaeger, Prometheus, OpenSearch).
We don't copy the demo into this repo. The first time you run `run.py up`, it clones upstream's tag `3.1.0` into the
git-ignored `examples/otel-demo/upstream/`. Set `DEMO_DIR` to use a clone elsewhere. See
[examples/otel-demo/README.md](../examples/otel-demo/README.md).
```bash
python examples/otel-demo/run.py up        # first run: clone + pull ~10 GB of images; also starts the fault runner
python examples/otel-demo/run.py status
```
After a fresh start, let it warm up for **25 minutes** before the first fault. Later faults need 10 minutes between
them. Epicenter compares the fault window with the minutes before it, and a cold demo stalls when a flag flips. On
2026-10-17 we ran `paymentFailure` 10 minutes after start and it blamed `postgresql`. The flag reload slowed the
still-cold product-catalog / postgres, checkouts stalled, and payment threw too few errors to stand out. At 27 minutes
after start it gave `payment/Charge` at 0.99. Once warm, open `/runs`:

| Scenario | Expect | Measured 2026-10-17 |
|---|---|---|
| `paymentFailure` | `payment/…/Charge`, change "flag paymentFailure → 50%" | ✓ 0.99, found in 0.8 s |
| `adHighCpu` | `ad/…/GetAds`, kind `cpu` | ✓ 0.999, found in 2.4 s |
| `emailMemoryLeak` | `no_root_cause` or `email/…`, depending on how far the leak got | `email/POST /send_order_confirmation` |

Undo each scenario from its card before starting the next, and wait a few minutes in between. Run `run.py down` when
you're done.

We also used other environments while building Epicenter (flip-commerce, synthetic medium / huge). Their runs are in
[EXAMPLE_RUNS](EXAMPLE_RUNS.md), but they aren't part of the demo set.

## 6. A 10-minute tour of the UI

1. Incidents (`/`) has one row per incident, with its status and verdict.
2. The incident page fills its canvas live as the agents work. Suspects appear, get checked, and are confirmed or
   ruled out. The verdict card shows the root cause, its confidence, the graph path from cause to alert, and the
   change that came before it.
3. In the Fault Simulator, click a suspect. Its predicted footprint lights up and reads "explains N of M" against what
   actually broke. In `paymentFailure`, compare the runner-up `checkout` ("explains 1 of 5") with `payment/Charge`,
   which explains the whole chain.
4. Why not X: every ruled-out suspect says why (started too late, no anomaly, footprint doesn't match).
5. Memory lists similar past incidents and what fixed them.
6. What-if (`/simulate`) answers "what breaks if `redis` fails?" before you ship.
7. Runs (`/runs`) lets you start a scenario, watch it count down to the alert, open the incident, and undo.

Things to check as a judge:
- the same input gives the same answer (rerun an incident and you get a new numbered run with identical scores);
- it says `no_root_cause` on a healthy system instead of inventing a cause;
- the verdict still appears with no OpenRouter key. Only the explanation text changes.

## 7. Tests

```bash
docker compose exec api pytest -q                 # needs FalkorDB up; ~4 min; "live" tests (real OpenRouter) skip
docker compose exec api ruff check .
cd web && npm ci && npm test && npm run lint      # web unit tests + lint
```

## 8. Troubleshooting

| Symptom | Fix |
|---|---|
| `bind: address already in use` | Another program holds the port. Check the port table in [HLD §5.1](HLD.md#51-ports), then stop that program or change the host port |
| Containers restart or get killed (exit 137) | Docker is out of memory. Raise its limit (§2) or drop a tier |
| OTel Demo stuck at "dependency failed to start" | Use `run.py up`. It adds `compose.epicenter.yaml`, which fixes a healthcheck. Give Docker 16 GB |
| OpenSearch exits on Linux | `sudo sysctl -w vm.max_map_count=262144` |
| Everything is slow, checkout p95 in seconds with no fault | The machine is overloaded, and the load generator is already at 10 users. Give Docker more memory, or stay with demos 1–2 |
| `/runs` says "Fault runner not reachable" | Start the env with its `run.py up`, which starts the runner. On Linux set `FAULT_RUNNER_BIND=0.0.0.0` |
| `run.py` can't find the demo clone | Set `DEMO_DIR`. The default is our Windows path |
| "AI explanation unavailable" | `OPENROUTER_API_KEY` is empty or OpenRouter is down. The verdict is still valid |
| Smoke test fails on the vector index while the machine is busy | Rerun it when the machine is idle. The index builds in the background |

## 9. Presenter demo (local)

We run the event demo on the presenter's laptop ([ADR 0014](adr/0014-local-event-demo.md)). We planned and scripted a
hosted version but haven't run it. See [DEPLOYMENT_PLAN.md](DEPLOYMENT_PLAN.md).

| When | Step |
|---|---|
| Day before | `python syscheck.py --run --live` (expect tier 3). Run demo 2 so a rehearsal RCAEval incident is in the graph, and generate one synthetic case |
| T−35 min | `docker compose up -d`, then `python examples/otel-demo/run.py up`. Let it warm up ≥ 25 min, because a cold demo misses (§5, demo 3) |
| T−5 min | In `/runs`, the ready dots for `astronomy-shop` are green. Keep the rehearsal incident open in a second tab |
| Demo | small → medium → real-world. A synthetic case from `/runs`, the RCAEval incident, then OTel `paymentFailure` live (the Fault Simulator moment on `frontend`), then what-if on `redis` |
| Right after | `/runs` → Undo on anything still in, then `python examples/otel-demo/run.py down` |

If anything fails, fall back to the recorded video.

## 10. Stop and clean up

```bash
python examples/otel-demo/run.py down        # stops the demo, keeps its data
docker compose stop                          # Epicenter, keeps the graphs
docker compose down                          # removes containers, keeps the graphs
docker compose down -v                       # also deletes every graph and incident: only if you mean it
```
