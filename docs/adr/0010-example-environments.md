# ADR 0010: Example environments: OTel Demo, flip-commerce, RCAEval

**Status:** Accepted · **Date:** 2026-10-15

## Context
The demo needs real telemetry and repeatable faults, using public or self-owned data. The user has their own system,
`system-design-journey` (flip-commerce: nginx → API in 6 stacks → Mongo replica set + Redis, k6 load), which has no
traces or fault API and only about 2 hops of depth.

## Options
1. OTel Demo only.
2. flip-commerce only.
3. RCAEval only.
4. **All three, each for what it's good at.**

## Decision
Option 4:
- **OTel Demo (primary):** multi-hop search across ~20 services, flagd faults.
- **flip-commerce (secondary):** a real failure in the user's own system. Telemetry via OTel auto-instrumentation from the command line plus winston / nginx logs; faults via `examples/flip-commerce/faults.py`. **The source repo is never modified.**
- **RCAEval replay (offline):** accuracy numbers and ablations.

One environment runs at a time (shared port 8080). Each gets its own `env:*` graph.

## Consequences
- Three adapters to maintain; they share the writers and detectors, so the extra code is small.
- flip-commerce adds a "your own system" story and the `circuit-misconfig` scenario (config change beats the obvious suspect).
- The Go server in flip-commerce is skipped (auto-instrumentation needs code changes there).
