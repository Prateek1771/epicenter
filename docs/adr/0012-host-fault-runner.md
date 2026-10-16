# ADR 0012: Faults run on the host, through a token-gated fault runner

**Status:** Accepted · **Date:** 2026-10-16

## Context
`POST /runs` (phase 9) has to inject a fault into an example environment: stop a Mongo or Redis container, restart
flip-commerce's API with a bad config, add load, or flip an OTel Demo feature flag. The API runs in a container. It has
no Docker CLI, can't restart processes on the host (flip-commerce runs there, not in Docker), and AGENTS rule 9 says
only `examples/*/faults.py` changes an environment.

## Options
1. Mount the Docker socket into the `api` container and run the fault logic in the API.
2. A sidecar container with the socket, called by the API.
3. **A small process on the host (`examples/fault_runner.py`) that runs `examples/<env>/faults.py`, called by the API
   over HTTP with a shared token.**

## Decision
Option 3:
- The runner is stdlib Python. It listens on `127.0.0.1:8090`; Docker Desktop's `host.docker.internal` reaches the
  host's loopback, so it isn't exposed on the LAN.
- Every request needs `X-Runner-Token` (= `FAULT_RUNNER_TOKEN`). It runs only the registered `faults.py` of a known
  env, with a validated scenario id and change id, and nothing else.
- `GET /health` answers which example environments are up (`run.py ready`), which feeds `ready` on
  `GET /runs/scenarios`.
- `run.py up` starts it with the environment.

## Consequences
- The API never holds the Docker socket (it would be root on the host) and stays read-only towards monitored systems
  (N4). The fault code is the same whether a person runs `faults.py` by hand or `/runs` does.
- One more process to start; `run.py up` handles it, and `/runs` shows "Fault runner not reachable" when it's missing.
- On Linux with the plain `docker0` bridge, the container can't reach the host's loopback: set
  `FAULT_RUNNER_BIND=0.0.0.0` (still token-gated) or run the API on the host network.
