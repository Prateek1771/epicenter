# ADR 0013: The demo runs on one ephemeral EC2 host behind Caddy

**Status:** Accepted as the deployment plan; superseded for the event by [ADR 0014](0014-local-event-demo.md) (the demo runs locally) · **Date:** 2026-10-16

## Context
The event demo needs a public URL that shows the whole product, including live faults injected into the OTel Demo and
flip-commerce. The box only has to exist around the event: rehearsal, demo, then gone. Today everything runs on one
laptop:
- Docker Compose for Epicenter and the example environments;
- flip-commerce's API as a host process;
- the token-gated host fault runner ([ADR 0012](0012-host-fault-runner.md)).

The pieces facing the outside aren't ready for the internet:
- the web bundle points at `localhost:8000`;
- every port binds all interfaces;
- `API_KEY` would lock out the web UI, which doesn't send it.

## Options
1. **ECS / Fargate.** Managed containers, but there is no host for flip-node or the fault runner. Faults would need
   the Docker socket or ECS API rights inside the app, which ADR 0012 rejected. The OTel Demo's ~25 services become ~25
   task definitions.
2. **EKS + the OTel Demo Helm chart.** Production-shaped, but a cluster to build and pay for, for a one-day demo. The
   live-fault path would have to be rewritten for Kubernetes.
3. **Lightsail.** Cheap and simple, but limited instance shapes and networking.
4. **One EC2 VM running the laptop topology on Linux, with Caddy in front (TLS + basic auth), created by a script
   and destroyed by the same script after the demo.**

## Decision
Option 4:
- **Size:** `m6i.2xlarge` (8 vCPU / 32 GB), Ubuntu 24.04, 60 GB gp3, Elastic IP, IMDSv2.
- **Name and TLS:** a `sslip.io` hostname, so Let's Encrypt works without a domain.
- **Network:** only Caddy is public (80/443). Every Epicenter port is bound to `127.0.0.1`, and the security group
  closes the example environments' ports.
- **Auth:** UI and API share Caddy's origin, so basic auth covers both, `EventSource` included. `API_KEY` stays unset.
- **Secrets:** generated on the box into `.env` (mode 600). They are never in user-data, the AMI or git.
- **Lifecycle:** `deploy/aws.sh create | start | stop | destroy`, by tag. Before destroying, `deploy/demo.sh backup`
  copies FalkorDB's `dump.rdb` home, so the incident history survives the box.

## Consequences
- The demo runs the topology the laptop already verified in phase 9, so live faults work unchanged.
  - The application code doesn't change.
  - One compose build arg changes: `PUBLIC_API_URL`.
  - One env var changes: `FAULT_RUNNER_BIND=0.0.0.0`, which ADR 0012 anticipated.
- Cost is bounded: about $0.40/h running, cents per day stopped, zero after `destroy`.
- **Not production:** one box, no HA, basic auth instead of real identity, and the security group is the network
  boundary (Docker bypasses `ufw`). Anyone with the login can trigger the example faults. That is fine for a demo
  environment, and it is why the box is destroyed after.
- **Upgrade path, if Epicenter is deployed for real:**
  - OIDC at the proxy;
  - FalkorDB on its own instance;
  - API replicas once the in-process checkpointer and running-set move to shared storage (AGENTS.md "Keep the API
    stateless");
  - no fault runner at all (it exists for example environments only).
