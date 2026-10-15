# ADR 0009: FalkorDB via Docker, pinned tag, host port 6380

**Status:** Accepted · **Date:** 2026-10-15

## Context
FalkorDB runs as a Redis module; the embedded mode is experimental. The flip-commerce example already uses Redis on
host port 6379, and OpenConnector uses 3000, the FalkorDB browser's default.

## Options
1. FalkorDB Cloud: no local setup, but a network dependency during the demo.
2. **Docker image `falkordb/falkordb` (server + browser).**
3. `falkordb/falkordb-server` + separate browser image: more containers for no gain.

## Decision
Option 2 with:
- pinned `FALKORDB_TAG` (no `latest` at the demo)
- host ports `6380→6379`, `3002→3000`; inside Docker the API uses `falkordb:6379`
- `REDIS_ARGS="--requirepass … --appendonly yes"`, `FALKORDB_ARGS="THREAD_COUNT 4 TIMEOUT_MAX 30000"`
- named volume; data path verified on first run (docs show both `/data` and `/var/lib/falkordb/data`)
- health check `redis-cli PING`; other services wait for `service_healthy`

## Consequences
- Works offline; one `docker compose up`.
- Anyone connecting from the host must remember 6380, not 6379 (README troubleshooting covers it).
