# ADR 0014: The event demo runs locally; the EC2 design stays as the deployment plan

**Status:** Accepted · **Date:** 2026-10-17 · **Supersedes for the event:** [ADR 0013](0013-ephemeral-demo-deployment.md)

## Context
ADR 0013 put the event demo on one EC2 box behind Caddy, created before the event and destroyed after. The scripts for
it are built (`deploy/`). Running it means a paid cloud account and a public box with fault buttons. The laptop already runs the whole topology (phase 9), including live faults.

## Decision
- The event demo runs **locally** on the presenter's laptop: a synthetic case, an RCAEval incident recorded in
  rehearsal, then the OTel Demo live (`paymentFailure`). Fallback: the recorded video.
- The AWS design in ADR 0013 is **kept as the deployment plan**, written up for judges in
  [DEPLOYMENT_PLAN.md](../DEPLOYMENT_PLAN.md). `deploy/` stays in the repo as its ready-to-run implementation, checked
  locally but not run against AWS.
- **Three demos**, one per size, and one `syscheck` tier each: **small** = synthetic (any laptop, a known answer),
  **medium** = RCAEval RE2-TT replays (real recorded faults, the accuracy number), **real-world** = the OTel Demo live.
  flip-commerce ([ADR 0010](0010-example-environments.md)) and synthetic medium / huge stay in the repo and in
  EXAMPLE_RUNS as development environments, not in the demo set. HotROD and Train-Ticket live are dropped.

## Consequences
- No cloud cost and no public attack surface during the event.
- Judges can't open a public URL; they run it from SETUP.md, which is what `syscheck.py` exists for.
- Unverified until someone deploys: Let's Encrypt on `sslip.io`, the external port scan, `destroy` leaving nothing
  behind (listed in DEPLOYMENT_PLAN §4).
