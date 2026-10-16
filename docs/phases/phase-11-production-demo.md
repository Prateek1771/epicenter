# Phase 11: Demo deployment (AWS), setup guide, system evaluator, demo samples

**Goal:**
- Epicenter runs on a public HTTPS URL during the demo, with live faults, and is torn down afterwards.
- Anyone (a judge, an evaluator, a teammate) can set it up from [SETUP.md](../SETUP.md).
- A **system evaluator** (`syscheck.py`) checks the machine. It picks the biggest set of samples the machine can run,
  from a small simulation up to full live environments, runs them and their tests, and reports what to try next.
- Demo samples come in three sizes: small, medium and huge.

**Depends on:** phases 9 and 10. **Unblocks:** the event demo and submission.

## Spec

- [ADR 0013](../adr/0013-ephemeral-demo-deployment.md): one EC2 host for the demo, then destroy it
- [HLD §5.3 demo deployment](../HLD.md#53-demo-deployment-aws), [HLD §9 security](../HLD.md#9-security)
- [LLD §13 system evaluator](../LLD.md#13-system-evaluator-syscheck), [LLD §11 config](../LLD.md#11-configuration),
  [LLD §12 test plan](../LLD.md#12-test-plan)
- [EXAMPLE_RUNS §0 sizes](../EXAMPLE_RUNS.md#0-sample-sizes-small-medium-huge),
  [§4 synthetic](../EXAMPLE_RUNS.md#4-synthetic-samples-self-made), [§5 HotROD](../EXAMPLE_RUNS.md#5-jaeger-hotrod-small-live),
  [§6 Train-Ticket](../EXAMPLE_RUNS.md#6-train-ticket-huge-live-opt-in)
- [SETUP.md](../SETUP.md): the guide this phase has to make true

## Files

```
deploy/
  compose.prod.yaml     override: every app port bound to 127.0.0.1, Caddy on 80/443
  Caddyfile             HTTPS + basic auth; /api/* → api:8000 (SSE unbuffered), the rest → web:3000
  cloud-init.sh         EC2 user-data: tools, /etc/hosts, sysctl, swap, clones (no secrets)
  aws.sh                create | start | stop | status | ssh | destroy  (AWS CLI v2, tag-based)
  demo.sh               on the box: up | down | status | backup
syscheck.py             host system evaluator (stdlib only): probe → tier → run → report
api/selftest.py         in-container small simulation: fixtures → diagnose → verdict table
examples/synthetic/gen.py   self-made samples in the RCAEval layout (small / medium / huge)
examples/hotrod/        compose.yaml, run.py, faults.py (Jaeger HotROD)
examples/train-ticket/  notes + compose override + faults.py (stretch)
tests/test_syscheck.py  pick_tier() on fake probes
tests/test_synth.py     same seed → same files; small case → expected verdict
```

## Tasks

### A. AWS demo deployment ([ADR 0013](../adr/0013-ephemeral-demo-deployment.md), [HLD §5.3](../HLD.md#53-demo-deployment-aws))

The plan: create the box two days before the event and rehearse on it, stop it, start it on demo day, run the demo,
back up the graph and destroy everything.

**Target**

| Item | Choice | Why |
|---|---|---|
| Instance | `m6i.2xlarge` (8 vCPU, 32 GB) | OTel Demo ~6 GB + Epicenter ~3 GB + flip-commerce ~2 GB, with headroom; steady CPU (a `t3.2xlarge` works but burns CPU credits under constant load) |
| OS | Ubuntu 24.04 LTS (x86_64) | Docker, Python 3.12 and Node 22 install cleanly; kernel 6.8 has no Mongo 8 `rseq` issue |
| Disk | 60 GB gp3 | images ~25 GB (OTel Demo, Epicenter, flip-commerce), traces, FalkorDB data, swap |
| Address | Elastic IP | the hostname stays the same across stop/start |
| Hostname | `<a-b-c-d>.sslip.io` (the Elastic IP with dashes) | a public name for Let's Encrypt without buying a domain; fallback: your own domain, or `tls internal` (browser warning) |
| Region | the one nearest the presenter | lower latency on stage |
| Metadata | IMDSv2 required | blocks SSRF-style reads of instance credentials |
| Tags | `Project=epicenter-demo` on every resource | `destroy` finds and deletes everything by tag |

**Cost** (on-demand, rough; check the AWS pricing page for your region):

| State | What you pay | Roughly |
|---|---|---|
| Running | instance + EBS + public IPv4 | ~$0.40 / h |
| Stopped | EBS 60 GB + idle Elastic IP | ~$0.30 / day |
| Destroyed | nothing | $0 |

A 3-day window with ~10 running hours costs under $10. Set a $20 AWS Budgets alert anyway.

- [ ] `docker-compose.yml`: web build arg `NEXT_PUBLIC_API_URL: ${PUBLIC_API_URL:-http://localhost:8000/api/v1}` (the
  only change to the base compose; local runs keep today's default).
- [ ] `deploy/compose.prod.yaml` (Compose ≥ 2.24 for `!override`):
  - `ports: !override ["127.0.0.1:<port>:<port>"]` for falkordb (6380, 3002), falkordb-mcp (8081), api (8000),
    web (3001), open-connector (3000). Nothing of Epicenter's listens on a public interface except Caddy.
  - `caddy` service, pinned `caddy:2.x-alpine` tag, ports 80 and 443, `deploy/Caddyfile`, volumes
    `caddy_data` / `caddy_config` (certificates survive restarts, so Let's Encrypt isn't asked again).
- [ ] `deploy/Caddyfile`:
  ```
  {$EPICENTER_HOST} {
      basic_auth {
          {$DEMO_USER} {$DEMO_PASSWORD_HASH}     # caddy hash-password; the hash lives in .env on the box only
      }
      handle /api/* {
          reverse_proxy api:8000 {
              flush_interval -1                  # SSE: send each event as it happens
          }
      }
      handle {
          reverse_proxy web:3000
      }
  }
  ```
  The UI and the API share one origin, so the browser sends the basic-auth credentials with every `fetch` and
  `EventSource`. That is why `API_KEY` stays empty on the box: the web UI doesn't send `X-API-Key`, and the API is only
  reachable through Caddy. `/mcp`, falkordb-mcp and the FalkorDB browser are **not** exposed; use
  `ssh -L 3002:127.0.0.1:3002` when you need them.
- [ ] `deploy/cloud-init.sh` (EC2 user-data; **no secrets**, user-data is readable from the console and the
  metadata service):
  - Docker Engine + compose plugin from Docker's apt repo; `ubuntu` in the `docker` group.
  - `python3.12`, `python3.12-venv`, Node 22 (NodeSource), k6 (Grafana apt repo), uv, git, jq.
  - `echo "127.0.0.1 host.docker.internal" >> /etc/hosts`: on Linux the host itself doesn't know this name, and
    flip-node (a host process) connects to Mongo with it. Containers already get it via `extra_hosts: host-gateway`.
  - `sysctl vm.max_map_count=262144` (persisted): OpenSearch in the OTel Demo won't start without it.
  - 4 GB swap file: survives a memory spike during image builds.
  - Clones into `/opt`:
    - `Prateek1771/epicenter`;
    - `open-telemetry/opentelemetry-demo` at tag `3.1.0`;
    - `xDAnkit/system-design-journey`.
  - Builds flip-node (`npm ci && npm run build` in `servers/01-node`). `dist/` is git-ignored there, and this only
    adds build output to a throwaway clone; the source is never edited (hard rule 10).
  - `npm ci` in `examples/flip-commerce/otel-node`.
  - Writes `/opt/READY` when done; `aws.sh create` waits for it over SSH.
- [ ] `deploy/aws.sh` (bash + AWS CLI v2; profile and region from `AWS_PROFILE` / `AWS_REGION`):
  - `create`:
    - key pair (saved to `~/.ssh/epicenter-demo.pem`, mode 600);
    - security group: 443 and 80 from `0.0.0.0/0`, 22 from `$(curl -s https://checkip.amazonaws.com)/32` only;
    - Elastic IP;
    - `run-instances` with the latest Ubuntu 24.04 AMI from the Canonical SSM parameter, `cloud-init.sh` as
      user-data, IMDSv2 required, 60 GB gp3, tags;
    - associates the EIP, waits for `/opt/READY`, prints the hostname.
  - `start` / `stop` / `status` (state, IP, hostname, running hours this month).
  - `ssh`: opens a shell with tunnels for 3002 / 8000.
  - `allow-my-ip`: re-adds port 22 for your current IP (it changes between venues).
  - `destroy`:
    - lists every resource tagged `Project=epicenter-demo` and asks `y/N`;
    - terminates the instance and waits;
    - releases the EIP, deletes the security group and the key pair;
    - checks that no volume or snapshot with the tag is left.
- [ ] `deploy/demo.sh` (runs on the box, from `/opt/epicenter`):
  - `up`:
    1. If `.env` is missing, generate it:
       - `FALKORDB_PASSWORD`, `MCP_API_KEY`, `FAULT_RUNNER_TOKEN` and `DEMO_PASSWORD` from `openssl rand -hex 24`;
       - prompt for `OPENROUTER_API_KEY` without echo (`read -s`; empty is allowed, the verdict works without it);
       - `EPICENTER_HOST`, `PUBLIC_API_URL=https://$EPICENTER_HOST/api/v1`, `WEB_ORIGIN=https://$EPICENTER_HOST`;
       - `FAULT_RUNNER_BIND=0.0.0.0`, `DEMO_DIR=/opt/opentelemetry-demo`,
         `FLIP_REPO=/opt/system-design-journey/season-1/2.vertical-vs-horizontal-scaling`;
       - `chmod 600 .env`.
    2. `docker compose -f docker-compose.yml -f deploy/compose.prod.yaml up -d --build`.
    3. Smoke test.
    4. Download the 3 RCAEval cases if missing.
    5. `python3 examples/otel-demo/run.py up`.
    6. Print the URL and the login (shown once).
  - `down`: `run.py down` for whichever env is up, then `docker compose … stop`. Never `down -v`.
  - `status`:
    - containers, plus `run.py status` per env;
    - fault runner health;
    - free memory and disk;
    - certificate expiry.
  - `backup`: `redis-cli BGSAVE` in falkordb, wait for `LASTSAVE` to change, `docker cp` the `dump.rdb` to
    `backups/epicenter-<utc>.rdb`. Then, from the laptop, `aws.sh ssh -- cat …` it into `data/backups/`
    (git-ignored). This keeps the incident history (rehearsal and demo) after the box is gone.
- [ ] Fault runner on Linux: `FAULT_RUNNER_BIND=0.0.0.0` (ADR 0012 already allows it). Port 8090 is closed by the
  security group; the token still guards it.
- [ ] Ports opened by the example environments (8080, 16686, 9090, 9200, 6379, 27017–27019, 4317–4318, 5001) are
  published on all interfaces by their own compose files. Docker bypasses `ufw`, so **the security group is the
  boundary**. Check from outside with `nmap -Pn -p 1-65535 <host>`: only 80 and 443 (and 22 from your IP).
- [ ] Rehearsal on the box: `python3 syscheck.py --run --live` (expects tier 4), then every scenario from `/runs` through
  the public URL; write down the verdicts next to EXAMPLE_RUNS.
- [ ] Use a separate OpenRouter key with a spend limit for the box; revoke it after the demo.

**Demo-day runbook** (also in [SETUP §9](../SETUP.md#9-hosted-demo-for-the-presenter)):

| When | Step |
|---|---|
| T−2 days | `aws.sh create` → `demo.sh up` → full rehearsal (`syscheck --run --live`, every `/runs` scenario) → `demo.sh backup` → `aws.sh stop` |
| T−45 min | `aws.sh allow-my-ip` → `aws.sh start` → `demo.sh up` (OTel Demo) → let load run ≥ 10 min (the baseline window is t−10 min … t−2 min) |
| T−10 min | `demo.sh status` all green; open `/runs` (ready dots green) and one rehearsal incident in a second tab |
| Demo | OTel `paymentFailure` live (Fault Simulator moment on `frontend`); flip-commerce and RCAEval shown from rehearsal incidents already in the graph (only one live env runs at a time); what-if on `redis` |
| Right after | `/runs` → Undo on anything still in; `demo.sh backup` |
| Same day | `aws.sh destroy` → revoke the OpenRouter key → check Billing: no instance, EIP, volume or snapshot left |

Fallbacks, in order: the laptop setup (identical topology), then the recorded video (phase 10).

### B. System evaluator ([LLD §13](../LLD.md#13-system-evaluator-syscheck))

- [ ] `syscheck.py` at the repo root, stdlib only (runs before anything is installed; Python ≥ 3.10):
  - **Probe** (read-only, < 15 s): OS / arch, cores, RAM, disk free, Docker + Compose version, **Docker VM limits**
    (`docker info` → `NCPU`, `MemTotal`), free ports, tools (git, node, k6, uv), internet (Hugging Face,
    OpenRouter), `.env` sanity (present, no `change-me`), Epicenter stack health, a 3 s CPU benchmark and a
    256 MB disk write.
  - **Tier:** `pick_tier(probe)`, a pure function on `min(host, Docker VM)` (thresholds in LLD §13).
  - **Recommend:** the runs that fit the tier and `--minutes`, with commands and expected verdicts.
  - **`--run`:** runs the tier's checks up to tier 2 (it starts Epicenter's own stack but never touches an example
    environment).
  - **`--run --live`:** adds tiers 3–5. It asks `y/N` per environment and per scenario, undoes each fault, and
    waits for `run.py status` to be healthy before the next one.
  - **Report:** a table on screen plus `data/syscheck/<n>-<utc>.json` and `.md`, numbered and never overwritten.
    Exit code 0 = all checks passed, 1 = a check failed, 2 = the machine is below tier 1.
- [ ] `api/selftest.py`: loads each `tests/fixtures/*.cypher` into its own `scratch:selftest-<name>` graph, diagnoses it,
  prints verdict / top suspect / footprint / ms against the expected answer, and deletes the graph in `finally`.
  `python -m api.selftest [--json]`.
- [ ] `api/runs.py` `Scenario.expect` (machine-readable, e.g. `{"target_prefix": "redis/"}` or
  `{"status": "no_root_cause"}`) on every live scenario, so `syscheck` and the `/runs` card compare verdicts instead
  of eyeballing them. The card shows "matches expected" / "differs".
- [ ] `tests/test_syscheck.py`: `pick_tier` on fake probes: 2 cores / 4 GB → 1; a 16 GB host whose Docker VM has 8 GB →
  2 (the VM wins); 8 / 32 / 60 GB + tools → 4; no Docker → 0.

### C. Demo samples ([EXAMPLE_RUNS §0](../EXAMPLE_RUNS.md#0-sample-sizes-small-medium-huge))

- [ ] **Synthetic generator** `examples/synthetic/gen.py --size small|medium|huge --fault <kind> --seed <n>`
  ([EXAMPLE_RUNS §4](../EXAMPLE_RUNS.md#4-synthetic-samples-self-made)):
  - writes the RCAEval layout plus `labels.json` (and `changes.jsonl` for `config`) into `data/rcaeval/synth-…`;
  - the case regex in `api/runs.py` and `api/ingest/rcaeval.py` accepts `synth-<size>_<svc>_<fault>_<n>` → env
    `synthetic`;
  - the RCAEval adapter reads an optional `changes.jsonl` through `changes.read_journal`.
- [ ] `api.eval --suite synth [--size …]`: AC@1 / AC@3 per size, the scale curve.
- [ ] `tests/test_synth.py`: same seed → byte-identical files; `small/cpu` → the labelled op wins; `small/healthy` →
  `no_root_cause`.
- [ ] **HotROD** env ([EXAMPLE_RUNS §5](../EXAMPLE_RUNS.md#5-jaeger-hotrod-small-live)):
  - compose, `run.py` and `faults.py`;
  - `LIVE_ENVS` entry `hotrod` with its own `jaeger_url`;
  - registry rows.
  - Check the fix flags with `docker run --rm jaegertracing/example-hotrod:<tag> all --help` before wiring scenarios.
- [ ] **OTel Demo minimal:** `run.py up --minimal` (the demo's `docker-compose.minimal.yml` + our override). Verify that
  `paymentFailure` and `adHighCpu` still give the same verdicts.
- [ ] **Train-Ticket** (stretch) ([EXAMPLE_RUNS §6](../EXAMPLE_RUNS.md#6-train-ticket-huge-live-opt-in)): only if a
  16-core / 32 GB box is rehearsed. `ts-auth-service` cpu and `ts-order-service` delay, compared with the RE2-TT
  replays.

### D. Docs

- [ ] [SETUP.md](../SETUP.md) checked end to end on a clean machine per tier (Windows laptop, the EC2 box, a 2-core /
  4 GB Docker limit), and every "phase 11" label removed as its command lands.
- [ ] EXAMPLE_RUNS: write the real results of the new samples (verdicts, timings), including misses.
- [ ] README: "Judges: start with [docs/SETUP.md](../SETUP.md)" (done in the docs pass); the phase 10 results table.

## Acceptance

- `https://<host>` asks for the login, then shows the UI. SSE updates arrive live through Caddy (the incident canvas
  fills during a run).
- From outside, only 80 / 443 (and 22 from the presenter's IP) answer.
- `/runs` on the box: ready dots green for `astronomy-shop`; `paymentFailure` → `payment/Charge` with the flag change;
  Undo returns the flags to `off`.
- `aws.sh destroy` leaves zero resources tagged `Project=epicenter-demo` (checked with
  `aws resourcegroupstaggingapi get-resources`).
- `demo.sh backup` produces a `dump.rdb` that loads in a local FalkorDB with the demo's incidents in it.
- `syscheck.py` picks tier 1 with Docker capped at 2 CPUs / 4 GB, tier 4 on the EC2 box, the laptop's tier on the
  laptop. `--run` passes on each and writes a numbered report.
- `test_syscheck.py` and `test_synth.py` pass; synthetic small / medium / huge give their labelled verdicts (misses
  reported, not hidden).

## Scalability

- **The box is the laptop topology on Linux.** Nothing in the app changes for the deployment, only the edges (proxy,
  binding, secrets). The same files run on any Linux VM (another cloud, a lab server).
- **Upgrade path past a demo box:**
  - FalkorDB → a managed or dedicated instance (`FALKORDB_URL`);
  - API replicas behind the proxy, after the in-process pieces move as AGENTS.md says (server-backed checkpointer,
    Redis lock);
  - real auth (OIDC at the proxy) instead of basic auth;
  - the fault runner dropped entirely in production (it exists for example environments only).
- **The evaluator's tiers are data** (a table in `syscheck.py` mirroring LLD §13). A new sample is a new row with
  its minimum resources and command.
- **Synthetic samples scale the graph without hardware:** "huge" exercises 2000 operations and a 6-hour window on a
  laptop, which is where N2 (query p95 < 200 ms) gets measured at size.

## Risks / open questions

- **Let's Encrypt on `sslip.io`** can hit rate limits shared with other users of that domain; if issuance fails, use
  your own domain (one A record) or `tls internal` and accept the warning.
- **Venue Wi-Fi may block SSH** (port 22). Run `demo.sh up` before leaving, or add AWS Systems Manager Session
  Manager (needs an instance role).
- **The demo box exposes fault buttons** to anyone with the login: keep the password off slides, and rotate it if
  shown.
- **Live envs need ~10 min of traffic before a fault** (baseline window); plan the stage time around it.
- **Train-Ticket's real footprint is unmeasured here.** Treat 24 GB+ as an estimate until `docker stats` says
  otherwise.
- The **HotROD fix flags** and **OTel minimal's** flag coverage are taken from their docs; verify on the pinned tags
  before wiring.

## Done when

The demo ran from the public URL and the box is destroyed with its graph backed up. SETUP.md works on a clean machine
at each tier. `syscheck.py` picks the right tier and its `--run` passes. The small / medium / huge samples run with
results written into EXAMPLE_RUNS.
