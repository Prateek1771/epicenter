# Phase 5: Agents, typed tools, MCP

**Goal:** a LangGraph flow runs a full diagnosis from an `incident_id`: triage → parallel investigators → scorer →
skeptic → second cause / `no_root_cause` → (historian, narrator, jev, responder stubs until phase 7). Agents share
state through the incident subgraph; LangGraph state holds ids only. The same typed tools are exposed over MCP at `/mcp`.

**Depends on:** phases 3, 4. **Unblocks:** 6, 7.

## Spec

- [LLD §5 Agents](../LLD.md#5-agents-agentsflowpy): state (§5.1), step graph (§5.2), contracts (§5.3)
- [LLD §2.3 tool queries](../LLD.md#23-tool-queries), [ADR 0003](../adr/0003-typed-mcp-tools.md) typed tools, [ADR 0007](../adr/0007-graph-as-shared-agent-state.md) graph as shared state
- [HLD §3.1 main flow](../HLD.md#31-alert--diagnosis-the-main-flow), [HLD §7 failure modes](../HLD.md#7-failure-modes)

## Files

```
api/agents/flow.py            IncidentState, graph wiring, checkpointer
api/agents/triage.py  investigator.py  skeptic.py  historian.py  narrator.py  responder.py  ask.py   (last four stubbed here)
api/tools/graph_tools.py      blast_radius, upstream_candidates, propagation_path, mechanism, why_not,
                              recent_changes, similar_incidents, who_knows, simulate
api/tools/mcp_server.py       same functions over MCP, mounted at /mcp
api/events.py                 publish(incident_id, event, data) interface (in-process impl, phase 6 wires SSE)
tests/test_flow.py
```

## Tasks

- [ ] `IncidentState` exactly as LLD §5.1: ids, flags, counters only. No evidence, no telemetry in state.
- [ ] triage: `Incident {status:'diagnosing'}`, `TRIGGERED_BY`, hypotheses via `causal.hypotheses`; emits `hypothesis.created`.
- [ ] investigator per hypothesis via `Send`: Q2, Q3, Fault Simulator; writes only under its own hypothesis; emits `evidence.added`, `footprint`, `hypothesis.status`. Optional LLM context calls (`recent_changes`, `who_knows`) never set status.
- [ ] scorer: phase 3/4 scoring, `ROOT_CAUSE`, emits `verdict` (or `no_root_cause`).
- [ ] skeptic: LLM chooses *which* alternative and *which* tool; deterministic tools decide. Leads with the winner's unexplained symptoms. Max 2 rounds back to scorer. Without an LLM it falls back to "test runner-up with its footprint".
- [ ] Second-cause branch and `no_root_cause` branch as in the LLD §5.2 diagram.
- [ ] Every step: structured log `{incident_id, agent, tool, query_id, duration_ms, rows}` ([HLD §10](../HLD.md#10-observability-of-epicenter-itself)); errors appended to `state.errors`.
- [ ] Checkpointer (SQLite `./data/checkpoints.db`) so `diagnose` resumes after a crash; finished work is already in the graph, so a resumed step must be idempotent (`MERGE` on hypothesis/evidence ids).
- [ ] Typed tools: plain Python functions with pydantic input/output models, each bound to one env (`tool(env, …)`); no tool accepts Cypher.
- [ ] `why_not(incident, service)` answers `victim`, `later_onset`, `no_anomaly`, `not_upstream`, `small_footprint`, `lost_on_score`, `is_root_cause` ([API.md](../API.md#get-incidentsidwhy-notservice)).
- [ ] MCP server at `/mcp` exposes the same functions (generated from the same signatures, not hand-duplicated).
- [ ] `events.publish` is an interface with one in-process implementation.

## Acceptance

- `run(incident_id)` on a replayed RCAEval incident ends in `diagnosed` (or `no_root_cause`) with all hypotheses in a terminal status.
- Killing the process mid-investigation and calling resume finishes without duplicate nodes.
- Investigators run concurrently (log timestamps overlap) and no evidence lands under the wrong hypothesis.
- With no `OPENROUTER_API_KEY`, the flow still produces the same verdict (N7).
- An MCP client can list and call `blast_radius` at `/mcp`.

## Scalability

- **Ids-only state** keeps checkpoints tiny and lets any process pick up an incident from the graph.
- **Fan-out is per hypothesis** with no shared locks; FalkorDB serializes writes per graph, so keep each investigator's
  writes small (one evidence batch per check).
- **`events.publish` is an interface.** The in-process queue is the ceiling for one API replica. Upgrade path: Redis
  Streams (FalkorDB already runs Redis) behind the same interface when there is more than one API process.
- **Checkpointer is SQLite on local disk**, the second single-process ceiling. Upgrade path: LangGraph Postgres / Redis
  checkpointer, same interface.
- **Tools are the API for every agent and for MCP clients.** Adding an agent never needs new database access, only tools.
- Long-running diagnoses should move to a background task / worker (`asyncio.create_task` now; a job queue when diagnosing many incidents at once).

## Risks / open questions

- **Q-c:** `?force=true` rerun marks old hypotheses "superseded"; add that status to [LLD §8](../LLD.md#8-state-machines) and GRAPH_SCHEMA, or reuse `pruned` with a flag.
- LangGraph `Send` + checkpointer + resume needs a spike early in this phase.

## Done when

A full deterministic diagnosis runs through the agent flow, resumes after a crash, and the typed tools work both in-process and over MCP.
