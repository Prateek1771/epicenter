# Phase 0: Foundation

**Goal:** one `docker compose up` gives a healthy, password-protected, persistent FalkorDB on a pinned tag, an empty
API and web shell, and a smoke test proving every FalkorDB feature the design depends on works on that tag.

**Depends on:** nothing. **Unblocks:** everything.

## Spec

- [README §1–5](../../README.md#1-prerequisites): prerequisites, `.env`, start, persistence check, smoke test
- [HLD §5.1 Ports](../HLD.md#51-ports), [HLD §5.2 compose file](../HLD.md#52-docker-composeyml)
- [ADR 0009](../adr/0009-falkordb-via-docker.md) FalkorDB via Docker, [ADR 0005](../adr/0005-modular-monolith.md) modular monolith
- [LLD §1 layout](../LLD.md#1-package-layout), [LLD §11 configuration](../LLD.md#11-configuration)
- [FALKORDB_PLAN §9](../planning/FALKORDB_PLAN.md#9-smoke-test-before-writing-product-code) smoke-test list

## Files

```
docker-compose.yml  .env.example  .gitignore  weights.json (placeholder v1/v2 from LLD §6.3)
api/Dockerfile  api/pyproject.toml (or requirements.txt)
api/__init__.py  api/main.py (FastAPI app, /api/v1/health stub)  api/config.py
api/smoke_falkordb.py
web/ (Next.js + Tailwind + shadcn scaffold, one page that calls /health)
tests/conftest.py
.github/workflows/ci.yml
```

## Tasks

- [x] `docker-compose.yml` exactly as [HLD §5.2](../HLD.md#52-docker-composeyml): host ports 6380 / 3002 / 8081 / 8000 / 3001 / 3000, health check, `service_healthy` dependencies, named volume, `extra_hosts: host.docker.internal`.
- [x] `.env.example` with every variable from [README §2](../../README.md#2-configure) and [LLD §11](../LLD.md#11-configuration). `.env` and `.env.openconnector` git-ignored.
- [x] Pull `falkordb/falkordb` and `falkordb/mcpserver`, pin both tags in `.env.example` (never `latest` for the demo).
- [x] Run the persistence check from [README §4](../../README.md#4-check-persistence-first-run-only); fix the volume path (`/data` vs `/var/lib/falkordb/data`) in compose and note the answer in HLD §5.2.
- [x] `api/config.py`: one `Settings(BaseSettings)` class, every env var typed with the LLD §11 default. No other module reads `os.environ`.
- [x] `api/main.py`: FastAPI app, router at `/api/v1`, `GET /health` returning `{"status":"ok","falkordb":…}` (FalkorDB `PING`). Startup hook placeholder for the seed step (phase 1).
- [x] `api/smoke_falkordb.py` (`python -m api.smoke_falkordb`), six checks on a throwaway graph, each printing PASS/FAIL, exit code ≠ 0 on any failure:
  1. `[:CALLS*1..6]` with a filter on the end node
  2. Q2 shape: `UNWIND` over `nodes(p)` + `OPTIONAL MATCH` per node ([LLD §2.2](../LLD.md#22-causal-search-queries))
  3. `CALL algo.pageRank(...)`: record the real signature and whether weights are supported
  4. vector index create + `db.idx.vector.queryNodes` with `vecf32`
  5. full-text index create + query
  6. two writers in parallel on one graph (threads), both writes present after
- [x] Record the smoke results (tag, PageRank signature, weighted yes/no) at the top of [LLD §2](../LLD.md#2-graphpy).
- [x] Dockerfile: Python 3.12 slim, copy `api/` **as a package** under `/app/api` so `python -m api.…` works (open question Q-f).
- [x] `web/`: Next.js App Router scaffold, Tailwind, shadcn, dark-first; `NEXT_PUBLIC_API_URL` from env.
- [ ] CI: ruff + pytest on push; a FalkorDB service container for integration tests (pinned tag). *Workflow written and the same steps pass locally; tick after the first green run on GitHub.*

## Acceptance

```bash
docker compose up -d && docker compose ps                  # all healthy
curl localhost:8000/api/v1/health                          # {"status":"ok","falkordb":"ok"}
docker compose exec api python -m api.smoke_falkordb       # 6/6 PASS
docker compose restart falkordb && <rerun persistence check>  # data survives
```

## Scalability

- **Config in one place.** Every tunable (windows, thresholds, URLs) comes from `Settings`. Moving to another
  deployment means changing env vars, not code.
- **API stays stateless** except for the two documented in-process pieces (event bus, LangGraph checkpointer, phases 5–6).
  Don't add more in-process state; anything shared lives in FalkorDB.
- **Pinned images** make every environment reproducible. Bumping a tag = rerun the smoke test first.
- `falkordb/falkordb-server` (no browser) is the production image if this is ever deployed beyond the laptop
  ([FALKORDB_PLAN §1](../planning/FALKORDB_PLAN.md#1-which-image)).

## Risks / open questions

- Port clashes on 6379 / 8080 / 3000: see [README §8](../../README.md#8-troubleshooting).
- ~~If `algo.pageRank` has no weighted form on the pinned tag, decide here.~~ **Decided:** v4.22.1 has no weighted form; phase 3 uses unweighted `algo.pageRank`, networkx (weighted) only if the eval shows it helps. See [LLD §2](../LLD.md#2-graphpy).
- ~~Q-d (smoke part):~~ `smoke_falkordb.py` added to [LLD §1](../LLD.md#1-package-layout).

## Done when

The stack is up, healthy, persistent, the smoke test passes 6/6 on the pinned tag, and CI is green.
