# Phase 12: Investigation UI upgrades (from the competitor research), Graph | Data, test reports

**Goal:** the UI makes the positioning obvious. Others tell you the cause; Epicenter shows the graph that proves it,
what each suspect would have explained, and why every other one lost. Every graph can also be read as data, and
every test run leaves a findings report plus a guide a coding agent can act on.

**Depends on:** phases 8 (web UI) and 9 (live environments, for real incidents to show). **Unblocks:** 10 (demo
assets), 11 (the evaluator writes the same report pair).

## Spec

- [COMPETITOR_UI_RESEARCH §8](../COMPETITOR_UI_RESEARCH.md#8-epicenter-mapping-what-to-borrow-where): every P0 + P1
  row, marked ✅ there as built
- [UI_SCREENS §1](../UI_SCREENS.md#1-visual-language) (Graph | Data rule), [§4.11b](../UI_SCREENS.md#411b-phase-12-additions-from-competitor_ui_research-81),
  [§12.1](../UI_SCREENS.md#121-service-map-map), [§12.2](../UI_SCREENS.md#122-graph-mode-blast-radius--what-if)
- [API.md](../API.md): `GET /incidents/{id}` verdict `owner` / `change` / `found_in_ms` and action `precedent`;
  `GET /incidents/{id}/graph` `alert_ts` / `changes` / `receipts`; `GET /graph/topology`; blast-radius and what-if
  `edges`
- [LLD §9](../LLD.md#9-events-sse) (`receipts` event), [§12](../LLD.md#12-test-plan), [§13.4](../LLD.md#134-report)

## Files

```
api/graph.py                  Receipts recorder (contextvars), QUERIES: incident_changes, change_by_id,
                              incident_set_timing / incident_timing / incident_set_receipts, fix_incidents,
                              topology_services / topology_service_calls / topology_ops / topology_op_calls,
                              map_anomalies / map_root_causes
api/agents/flow.py            one `receipts` event per run; found_in_ms at the verdict
api/agents/investigator.py    evidence.added carries its summary
api/routes/incidents.py       verdict facts, canvas extras, action precedent
api/routes/graph_views.py     GET /graph/topology; edges on blast radius and what-if
web/components/graph/         view-toggle.tsx, data-view.tsx, flow-graph.tsx (+ incident-canvas slicer fade)
web/components/incident/      lanes.tsx, receipts.tsx, explainers.tsx; verdict.tsx (facts, ring tooltip, T-minus,
                              Ruled out, Couldn't see); act.tsx (precedent)
web/app/map/page.tsx          service map; blast-radius and simulate pages get graph mode
web/lib/graph-data.ts         rows, filter, sort, CSV (pure, tested)
web/lib/investigation.ts      ruled out, lanes, slicer, T-minus, explainers (pure, tested)
web/scripts/test.mjs          `npm test`: node:test + appends web results to the newest report
tests/report.py               pytest plugin: data/reports/<n>-<utc>/findings.md + agent-context.md
```

## Tasks

- [x] **Graph | Data toggle** on the incident canvas, `/map`, blast radius and what-if:
  - Nodes / Edges tables with sort, multi-word filter and CSV;
  - a raw JSON tab with copy / download;
  - clicking a row jumps back to the graph with that node selected;
  - the state lives in `?view=data`.
- [x] **P0 #3 Ruled out** on the verdict card (and on the no-root-cause card): each refuted / pruned suspect with the
  engine's refuting evidence summary; click → its path.
- [x] **P0 #9 Timeline lanes** under the canvas: onset bars by kind, changes as blue ticks, the alert line.
- [x] **P1 #1** A confidence ring that defines the number (deterministic, N parts, weights version).
- [x] **P1 #2** Owner, contributing change and "found in Ns" on the verdict.
- [x] **P1 #4** "Couldn't see" (`gaps`) on the verdict, with what each gap hides.
- [x] **P1 #6** Numbered query receipts, recorded per run in `graph.py` and shown in the Timeline tab.
- [x] **P1 #10** T-minus strip: change → root onset → alert.
- [x] **P1 #13** Onset slicer with Play; operations that haven't gone bad yet fade on the canvas.
- [x] **P1 #14** Symptom → suspects ("Who explains this symptom?") from a canvas click or a lane click.
- [x] **P1 #17** Fixes cite precedent ("fixed inc-17, inc-9").
- [x] **P1 #26 / #27** Blast radius graph (inspect layout, right to left) and what-if graph with Play.
- [x] **P1 `/map`** service map: services ↔ operations, traffic bar, error-coloured edges, anomaly ring, ♛, side
  panel, find.
- [x] **Test reports:** `findings.md` + `agent-context.md` per pytest run (numbered, kept); the web tests append to
  the same report.
- [x] P0 #33 Eval per-case table: `GET /eval` `per_case` (case, split, label, our top 3, hit@1 / hit@3), with an
  All / Misses filter on `/eval`.
- [x] `/map` side panel "recent changes" (`GET /services/{service}/changes`, 24 h) and double-click expand: the
  node's neighbourhood (1 hop, +1 per repeat up to 3, "Show all" resets), computed in the browser from the topology
  already loaded (UI_SCREENS §12.1).

## Acceptance

- `pytest`: the new API / flow / report tests pass, and the full suite is green; the run writes
  `data/reports/<n>-…/findings.md` and `agent-context.md`.
- Web `tsc`, `lint`, `npm test` (graph-data + investigation suites) and `next build` pass.
- On a real incident (`astronomy-shop` `inc-run-1792159031`):
  - the verdict shows owner `payments`, the flag change, "found in", T-minus, Ruled out (2) and Couldn't see (logs);
  - the receipts list ~110 numbered queries;
  - the slicer fades operations before their onset.
- A rerun of an RCAEval incident gives identical scores, statuses and `score_parts` as the run before it: the new
  fields don't touch ranking (rule 5).

## Results (2026-10-16)

- **Python:** 188 passed / 2 skipped (final run, report `0003`) after one fix. The first full run caught a real bug (the receipts summary
  returned the live list, so the receipts write itself slipped in after the total), and its own
  `agent-context.md` pointed at the failing test and the rerun command.
- **Web:** `tsc`, `lint`, 20 / 20 unit tests and `next build` pass.
- **`inc-run-1792159031` rerun (run 4):** `payment/Charge` 0.83 as before, found in 658 ms, 110 graph queries,
  622 ms in FalkorDB.
- **`rc-re2tt_ts-auth-service_cpu_2`:** runs 55 and 56 are identical on all 13 suspects (score, status,
  `score_parts`).
- Checked in Chrome: the incident page (verdict extras, lanes, slicer at −2m 41s, receipts, explainers on an RCAEval
  incident, the Data tab), `/map` with its side panel, the blast radius graph (right to left) and what-if Play.

## Design system (2026-10-17)

The whole UI was re-skinned to [`design_reference/`](../../design_reference/design.md) (Linear style reference):
- the tokens in `globals.css`;
- Inter / JetBrains Mono;
- the shadcn primitives restyled to the reference's component specs;
- the accent sweep (`primary` → `signal`, with lime only for the primary action, the active nav item and playheads);
- status colours on the token palette;
- no gradients, weights capped at 590, radii at 12px.

Rules: [UI_SCREENS §1](../UI_SCREENS.md#1-visual-language). Web-only: no API or behaviour change.

## Scalability

- **The data tables render every row:** fine up to a few thousand. Past that, virtualize the rows (same component
  props).
- **Receipts:** capped at 500 listed queries per run, with the rest counted. Recording is a context variable, so it
  costs nothing when no run is recording.
- **`/graph/topology`:** a full scan of the env's `CALLS`, capped at 2000 (`ponytail:` in `graph.py`). Past that,
  serve it from a per-service roll-up written by the topology tick.
- **Footprints for "who explains":** one request per suspect (≤ ~50), cached per run. A batch endpoint is the upgrade
  if suspects grow.

## Risks / open questions

- **The map's halo window (24 h, unresolved)** keeps old test incidents lit until they are resolved. Resolve demo
  incidents, or lower `hours`.
- **"Found in"** is measured from the start of a resume when a run was resumed after a crash.

## Done when

Every P0 / P1 row in COMPETITOR_UI_RESEARCH §8 is built or waits on a named phase. Every graph view has
Graph | Data. A test run leaves `findings.md` + `agent-context.md`.

## Addendum: UI round (2026-10-17)

Shipped after "Done when" was met. API in [API.md](../API.md), new labels in [GRAPH_SCHEMA](../GRAPH_SCHEMA.md),
query ids in [LLD §2.4](../LLD.md#24-ui-and-conversation-queries), flows in [USER_FLOW](../USER_FLOW.md).

- [x] **Incident exports:** `GET /incidents/{id}/export.md?flavor=human|agent` (`deliver/report.py`, no LLM);
  header buttons `incident_info.md` and `AGENTS.md`.
- [x] **Incident page:** right panel collapsed by default, tabs Suspects / Timeline / Notes / Chat; Deliver menu
  (Slack / Linear) in the header beside Rerun / Resolve.
- [x] **Ask as a chat:** `Conversation` / `Message` in the env graph; `POST|GET|DELETE /conversations`; `POST /ask`
  takes `conversation_id` and `attachments` (≤ 5 files, ≤ 200k chars), sends the last 6 turns as history, saves the
  user turn even on a `502`. Env or incident scope, wiki rail.
- [x] **Blast radius dossier:** `GET /services/risk`, `/services/{service}/people`, `/services/{service}/runbooks`;
  risk line, impact by hop, graph, people, incidents rooted here, changes (7 d), runbooks, callers, try-it links.
- [x] **What-if lab:** six kinds side by side, spread timeline, `POST /simulate/compare`, `GET /rules`,
  `GET /simulations`.
- [x] **Map Network view:** `GET /graph/explore` (bounded, every label, `Label:key` ids); Layers | Network | Data,
  legend toggles, highlight search.
- [x] **Eval page:** `GET /eval` adds `per_case[].confidence / diagnose_ms / variants / parts`, `history`, `synth`;
  KPIs, run history, ablation deltas, by fault, calibration, synthetic scale, score parts, where misses go, time to
  verdict, per-case drill-down.
- [x] **Landing:** scroll text reveal; optional illustration slots `web/public/landing/<name>.webp`.

Tests added:
- [x] `tests/test_api.py::test_export_markdown_human_and_agent`
- [x] `tests/test_api.py::test_blast_radius_dossier_routes`
- [x] `tests/test_api.py::test_simulate_lab_routes`
- [x] `tests/test_api.py::test_graph_explore_is_bounded_and_spans_labels`
- [x] `tests/test_api.py::test_service_changes_for_the_map_side_panel`
- [x] `tests/test_ask.py::test_conversation_keeps_history_attachments_and_survives_a_502`
- [x] `tests/test_eval.py::test_get_eval` (extended: `per_case` drill-down fields, `history`, `synth`)
