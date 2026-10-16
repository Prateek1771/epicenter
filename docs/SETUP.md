# Setup guide: install, run and evaluate Epicenter

For judges, evaluators and anyone trying Epicenter. It gets you from nothing to a diagnosed incident on screen, at the
size your machine can handle. Epicenter is the root-cause engine described in the [README](../README.md).

> Commands marked **(phase 11)** are specified in [phase 11](phases/phase-11-production-demo.md) and not built yet.
> Everything else works today.

---

## 1. Three ways in

| Way | You need | Time | You see |
|---|---|---|---|
| **A. Hosted demo** | a browser + the login from the team | 0 min | the full product, live faults included. Online only during the event; the box is destroyed afterwards |
| **B. Local, quick** | Docker, 4 cores / 8 GB for Docker | ~15 min | real diagnoses on recorded benchmark cases (RCAEval) and self-made samples |
| **C. Local, live** | Docker, 8 cores / 16 GB for Docker, Node, k6 | ~45 min | faults injected into running systems (OTel Demo, flip-commerce) and diagnosed live |

Not sure which fits? Run the system evaluator ([§3](#3-run-the-system-evaluator-first)). It measures the machine and
tells you.

## 2. What your machine can run

Epicenter sizes its samples small / medium / huge ([EXAMPLE_RUNS §0](EXAMPLE_RUNS.md#0-sample-sizes-small-medium-huge)).
The evaluator uses the tiers below. What counts is **what Docker can use**, not what the machine has: on Windows and
macOS, Docker Desktop runs in a VM with its own CPU and memory limit.

| Tier | Docker CPUs / memory | Disk free | Extra tools | Runs |
|---|---|---|---|---|
| 0 | below tier 1 | | | nothing local: use the hosted demo or the video |
| 1 Lite | 2+ / 4 GB | 10 GB | | core services, smoke test, fixture self-test, synthetic **small** |
| 2 Standard | 4+ / 8 GB | 20 GB | internet | + full test suite, synthetic **medium**, RCAEval replays + eval, HotROD live (small) |
| 3 Live | 6+ / 12 GB | 30 GB | Node 20+, k6, uv | + flip-commerce live faults, OTel Demo **minimal** |
| 4 Full | 8+ / 16 GB | 40 GB | same | + OTel Demo full, synthetic **huge** |
| 5 Huge | 16+ / 32 GB | 80 GB | same | + Train-Ticket live (opt-in, stretch) |

**Set Docker's limits first:**
- **Windows:** Docker Desktop with the WSL2 backend. The limit is in `%UserProfile%\.wslconfig`:
  ```ini
  [wsl2]
  processors=8
  memory=16GB
  ```
  Then run `wsl --shutdown` and restart Docker Desktop.
- **macOS:** Docker Desktop → Settings → Resources → CPUs / Memory.
- **Linux:** Docker uses the whole machine. Add `127.0.0.1 host.docker.internal` to `/etc/hosts` (tier 3+, for
  flip-commerce) and set `FAULT_RUNNER_BIND=0.0.0.0` in `.env` (tier 2+ live runs). The second step is needed because
  on Linux containers reach the host through the Docker bridge, not loopback
  ([ADR 0012](adr/0012-host-fault-runner.md)).

## 3. Run the system evaluator first

**(phase 11)**. Until it lands, pick your tier from the table in §2 by hand.

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

Example output (illustrative):

```
Epicenter system check
  host        Windows 11, 16 cores, 32.0 GB RAM, 412 GB free on D:
  docker      27.3 (Compose 2.30), VM: 8 CPUs, 15.6 GB   ← the limit that counts
  ports       6380 3002 8081 8000 3001 3000 free · 8080 in use (another env running?)
  tools       git ✓  node 22 ✓  k6 ✓  uv ✓
  internet    huggingface.co ✓  openrouter.ai ✓
  .env        present · OPENROUTER_API_KEY empty (explanations use the template; verdicts unaffected)
  bench       cpu 1.0× reference · disk 1.4 GB/s

Tier 3  Live   (tier 4 needs 16 GB for Docker; this VM has 15.6 GB)

Recommended runs (≈ 25 min)
  1. Smoke + fixture self-test                    docker compose exec api python -m api.selftest
  2. Synthetic medium, cpu fault                  expect: the labelled op, kind cpu
  3. RCAEval re2tt ts-auth-service cpu #2         expect: ts-auth-service/*, kind cpu
  4. flip-commerce: redis-down                    expect: redis, kind down          (live, asks first)
  5. flip-commerce: healthy-baseline              expect: no_root_cause             (live)
Report → data/syscheck/0003-20261016T101500Z.md
```

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
| Node.js | 20+ | 3+ (flip-commerce) |
| k6 | any recent | 3+ (flip-commerce load) |
| uv | any recent | 3+ |
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
| http://localhost:3001 | Epicenter UI |
| http://localhost:8000/docs | API (Swagger) |
| http://localhost:3002 | FalkorDB browser (host `localhost`, port 6379 from inside its container, or `localhost:6380` from your machine; password from `.env`) |

The API creates its indexes, owners and runbooks on startup.

## 5. Run samples, by size

Each sample says what verdict to expect. A run that misses is still worth reporting; that is how the engine improved
in phase 9 ([EXAMPLE_RUNS §1](EXAMPLE_RUNS.md#1-opentelemetry-demo-primary-multi-hop)).

### Small (tier 1+)

**Fixture self-test (phase 11):** six hand-made graphs (a known root cause, two faults at once, a healthy system,
a quiet symptom, a saturated caller, weak self-blame), each diagnosed in a throwaway graph.
```bash
docker compose exec api python -m api.selftest
```
Today, the same fixtures run as tests:
```bash
docker compose exec api pytest -q tests/test_simulate.py tests/test_causal.py
```

**Synthetic small (phase 11):** 5 services, one fault, 15 minutes of generated traces / metrics / logs.
```bash
docker compose exec api python examples/synthetic/gen.py --size small --fault cpu --seed 1   # prints the case id
docker compose exec api python -m api.ingest.rcaeval --case <case id> --env synthetic
```
Expect: the labelled operation (in `labels.json`), kind `cpu`.

**HotROD live (phase 11, tier 2+):** Jaeger's small ride-sharing demo with real traces and known bugs.
`python examples/hotrod/run.py up`, then `/runs` → `db-slow` → expect `mysql/*`.

### Medium (tier 2+)

**RCAEval replay** (recorded faults on the Train-Ticket system; ~25 MB per case):
```bash
docker compose exec api python -m api.ingest.rcaeval --case re2tt_ts-auth-service_cpu_2 --env rcaeval-tt --download
```
Open http://localhost:3001 → the incident `rc-re2tt_ts-auth-service_cpu_2`. Expect `ts-auth-service/*`, kind `cpu`.
Also try `re2tt_ts-auth-service_cpu_1` and `re2tt_ts-order-service_delay_1`, or start them from `/runs`.

**Synthetic medium (phase 11):** 30 services, including a two-fault and a "loud victim" case.
```bash
docker compose exec api python examples/synthetic/gen.py --size medium --fault two --seed 1
```

**flip-commerce (tier 3+):** a real e-commerce backend (Node + a Mongo replica set + Redis). It is the
`system-design-journey` repo, which Epicenter never modifies.
```bash
git clone https://github.com/xDAnkit/system-design-journey.git ../system-design-journey
cd ../system-design-journey/season-1/2.vertical-vs-horizontal-scaling/servers/01-node
npm ci && npm run build               # dist/ is git-ignored there; this only adds build output
cd -
```
Point the scripts at it, then start it:
```bash
export FLIP_REPO="$(cd ../system-design-journey/season-1/2.vertical-vs-horizontal-scaling && pwd)"
#   PowerShell: $env:FLIP_REPO = (Resolve-Path ..\system-design-journey\season-1\2.vertical-vs-horizontal-scaling)
python examples/flip-commerce/run.py up       # ~2 min: Mongo, Redis, collector, nginx, flip-node, load, fault runner
python examples/flip-commerce/run.py status
```
Then open `/runs` in the UI and pick a scenario:

| Scenario | Expect |
|---|---|
| `redis-down` | `redis/GET` |
| `mongo-majority-lost` | `mongodb/*` |
| `circuit-misconfig` | `flip-node/*` with the config change |
| `cpu-saturation` | `flip-node/*` |
| `mongo-primary-down` | `no_root_cause`: the replica set fails over in under 1 s |
| `healthy-baseline` | `no_root_cause` |

Undo each one from its card before starting the next. Details: [EXAMPLE_RUNS §2](EXAMPLE_RUNS.md#2-flip-commerce-your-system-design-journey).

**OTel Demo minimal (phase 11, tier 3+):** `run.py up --minimal` (about 3 GB, no Kafka). Same flags as the full demo
below.

### Huge (tier 4+)

**OTel Demo full** (~20 services, ~6 GB). Stop flip-commerce first; both use port 8080.
```bash
python examples/flip-commerce/run.py down
git clone --branch 3.1.0 https://github.com/open-telemetry/opentelemetry-demo ../opentelemetry-demo
export DEMO_DIR="$(cd ../opentelemetry-demo && pwd)"     # PowerShell: $env:DEMO_DIR = (Resolve-Path ..\opentelemetry-demo)
python examples/otel-demo/run.py up        # first start pulls ~10 GB of images
python examples/otel-demo/run.py status
```
Let the load run for **10 minutes** before the first fault: Epicenter compares the fault window with the minutes
before it.

| `/runs` scenario | Expect |
|---|---|
| `paymentFailure` | `payment/…/Charge`, change "flag paymentFailure → 50%" |
| `adHighCpu` | `ad/…/GetAds`, kind `cpu` |
| `emailMemoryLeak` | `no_root_cause` at demo traffic (the leak is too slow for the window) |

**Synthetic huge (phase 11):** 300 services / ~2000 operations over 6 hours. It tests scale and the slow-burn pass
without big hardware.

**Train-Ticket live (phase 11, tier 5, stretch):** the same system RCAEval recorded, faulted live, so the live verdict
can be compared with the replay. See [EXAMPLE_RUNS §6](EXAMPLE_RUNS.md#6-train-ticket-huge-live-opt-in).

### Accuracy number

```bash
docker compose exec api python -m api.eval --suite re2 --system tt     # AC@1 / AC@3 + ablations (phase 10)
```

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
| Everything is slow, checkout p95 in seconds with no fault | The machine is overloaded; the load generator is already at 10 users. Drop to OTel minimal or flip-commerce |
| `/runs` says "Fault runner not reachable" | Start the env with its `run.py up` (it starts the runner). On Linux set `FAULT_RUNNER_BIND=0.0.0.0` |
| flip-node won't start: `dist/server.js` missing | Build it once (§5, flip-commerce) |
| `run.py` can't find the repo / demo clone | Set `FLIP_REPO` / `DEMO_DIR` (the defaults are the authors' Windows paths) |
| "AI explanation unavailable" | `OPENROUTER_API_KEY` is empty or OpenRouter is down. The verdict is still valid |
| Smoke test fails on the vector index while the machine is busy | Rerun it when the machine is idle; the index builds in the background |

## 9. Hosted demo (for the presenter)

The event demo runs on one AWS EC2 box behind HTTPS and a login, and the box is destroyed afterwards
([ADR 0013](adr/0013-ephemeral-demo-deployment.md), [HLD §5.3](HLD.md#53-demo-deployment-aws)). **(phase 11)**:

```bash
export AWS_PROFILE=… AWS_REGION=ap-south-1
deploy/aws.sh create          # key, firewall, Elastic IP, Ubuntu box, tools + clones (~10 min); prints the hostname
deploy/aws.sh ssh
  cd /opt/epicenter && deploy/demo.sh up      # asks for the OpenRouter key, prints URL + login once
  python3 syscheck.py --run --live            # rehearsal, expect tier 4
  deploy/demo.sh backup
deploy/aws.sh stop            # between rehearsal and the event (~$0.30/day)
deploy/aws.sh start           # demo day, 45 min early; then demo.sh up and 10 min of warm-up
deploy/aws.sh destroy         # after the demo: lists everything tagged, asks, deletes; costs stop
```

The full runbook (timeline, demo order, fallbacks) is in
[phase 11, task block A](phases/phase-11-production-demo.md).

## 10. Stop and clean up

```bash
python examples/otel-demo/run.py down        # or examples/flip-commerce/run.py down (stops, keeps data)
docker compose stop                          # Epicenter, keeps the graphs
docker compose down                          # removes containers, keeps the graphs
docker compose down -v                       # also deletes every graph and incident: only if you mean it
```
