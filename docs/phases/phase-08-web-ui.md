# Phase 8: Web UI

**Goal:** the Next.js app shows the diagnosis live: hypotheses branch out on a graph canvas, turn red / green as
evidence lands, the Fault Simulator overlay shows predicted vs observed, and the winning path glows. Plus the blast
radius, what-if, ask, runs and eval screens. This is what judges see, so it has to look and feel best-in-class.

**Depends on:** phase 6 (phase 7 for memory / explanation / deliver panels). Can start earlier against API.md example payloads.

## Spec

- [USER_FLOW](../USER_FLOW.md): personas, the 7 screens and routes, flows 1–8 step by step (screen + API + graph work)
- [LLD §7.8 canvas overlay](../LLD.md#78-canvas-overlay), [LLD §9 SSE events](../LLD.md#9-events-sse)
- [API.md](../API.md) response shapes; [HLD §7](../HLD.md#7-failure-modes) "user sees" column for degraded states
- Design references: Traversal and Resolve product pages, incident.io timeline, Datadog Watchdog card ([GRAPH_HACKS_PLAN §8](../planning/GRAPH_HACKS_PLAN.md#8-ui-nextjs--tailwind--shadcn-dark-first))

## Files

```
web/app/page.tsx                       incidents list + env switcher
web/app/incident/[id]/page.tsx         canvas, verdict card, evidence, explanation, why-not, memory, deliver
web/app/blast-radius/page.tsx  simulate/page.tsx  ask/page.tsx  runs/page.tsx  eval/page.tsx
web/lib/api.ts                         typed client (types generated from the API's OpenAPI schema)
web/lib/useIncidentStream.ts           SSE hook; reconnects with ?after=<last seq> (EventSource can't set Last-Event-ID)
web/lib/incident-state.ts              pure reducer: /graph snapshot + SSE events, applied by id (node:test)
web/lib/layout.ts                      elk layered layout, incremental (placed nodes keep their spot)
web/components/graph/                  React Flow canvas, node types, overlay legend
```

## Tasks

- [x] Typed API client generated from `/openapi.json` (no hand-written duplicate types).
- [x] `useIncidentStream`: `EventSource`, reducer keyed by event type, reconnect from the last seq (`?after=`; the API accepts both), connection banner.
- [x] Canvas (React Flow): operations as nodes grouped by service, `CALLS` edges, hypotheses as branches; status colours (open, supported, refuted, inconclusive grey, confirmed glow); auto layout (elk) computed once per new node batch.
- [x] Overlay (LLD §7.8): observed = filled, predicted = dashed outline; matched green, missed amber, unexplained red; legend "explains 6 / 7 · precision 0.82 · order 0.9". Click a hypothesis to switch overlay.
- [x] Verdict card: root cause, confidence, `score_parts` bars, runner-up, second root cause, `no_root_cause` state with what was checked.
- [x] Evidence list and explanation: `[E3]` citations highlight that evidence's path on the canvas; "AI explanation unavailable" and "Claims not verified" badges.
- [x] Why-not box (service autocomplete) → answer + highlighted path.
- [x] Memory panel, actions with Send / Retry, Resolve dialog (pick the action that fixed it), notes input (Decision / Change).
- [x] Blast radius (grouped by hops, owners, past incidents link → simulate), What-if (service + kind → ranked predictions, save), Ask (answer + clickable path + Cypher when fallback used), Runs (pick env + scenario), Eval table.
- [x] Degraded states from HLD §7: "graph offline" banner, "Traces unavailable for this window", grey inconclusive branches, resume button.
- [x] Dark-first, keyboard accessible, readable at laptop and projector sizes; skeleton loaders, no layout jump as SSE events arrive.

## Acceptance

- Flow 1 end to end on an RCAEval replay: open incident page, watch branches appear and resolve, overlay switches per hypothesis, why-not works, citations highlight paths.
- Kill and restart the API mid-diagnosis: the page reconnects and shows no duplicate nodes.
- RCAEval TT incident (~400 ops) renders and pans smoothly; only the incident-relevant subgraph is drawn by default.
- Lighthouse accessibility ≥ 90 on the incident page.

## Scalability

- **Render the incident subgraph, not the world.** Load `GET /graph/subgraph?center=…&hops=2&incident=…` and expand on
  click. React Flow handles a few hundred nodes; beyond that, switch the canvas to a WebGL renderer (Cosmograph / sigma.js) behind the same component props.
- **Events reduce into state by id** (idempotent): replays and duplicates can't corrupt the view.
- **Types from OpenAPI** keep the UI in step with the API as endpoints grow.
- **Layout is incremental** (only new nodes are placed) so a long investigation doesn't re-layout and jump.

## Risks / open questions

- Mermaid `journey` scores in USER_FLOW are UX intent, not features; don't build them.
- ~~Decide dagre vs elk early~~ **Decided: elk** (`elkjs` 0.12, layered, left→right, service-grouped ordering).

## Done when

Every screen in USER_FLOW works against the live API, the main flow is demo-ready, and degraded states look intentional.

## Results (2026-10-16)

- **API for the canvas:** `GET /incidents/{id}/graph` returns one snapshot: hypotheses with evidence paths, nodes
  (ops on any evidence path, hypothesis ops, the symptom, each with its anomaly), `CALLS` edges among them, and
  `last_seq`. The page then streams `?after=last_seq`, so older runs never replay. Also `GET /envs` and
  `GET /services` (switcher, pickers). Contract test in `tests/test_api.py`.
- **Checks:** pytest 149 passed (2 live evals skipped), ruff clean; web `eslint`, `tsc --noEmit`, `npm test` 8/8
  (node:test with `--experimental-strip-types`; vitest dropped: its native rolldown binding was missing from the
  lockfile on Windows), `next build` in Docker. `npm run gen:api` against the running API → no diff in `api-types.ts`.
- **Flow 1 live (visible Chrome, RE2-TT cpu_1 / cpu_2):** the canvas opens on the winning path (29 nodes / 33
  edges); suspect click → overlay (matched / missed / unexplained, rest dimmed); `E1.1` → path spotlight; why-not
  `ts-order-service` → "lost on score" + path; Rerun → 111 events stream into the timeline, explanation turns
  "GPT-4o · every claim checked by Jev".
- **Reconnect:** `docker compose restart api` with the page open → "API unreachable" + stream `reconnecting` →
  back to live; the next rerun streams 111 more events, **0 duplicate seqs, node count unchanged (29)**.
- **Lighthouse accessibility (incident page): 100 mobile, 100 desktop** (fixed on the way: names for icon-only nav
  links at mobile width, path-chip label mismatch, heading order, anomaly badge and "Pruned" pill contrast).
- **TT size:** RE2-TT incident subgraphs are 24–42 nodes; the full ~400-op graph is never drawn (only the incident
  subgraph is loaded), so the 400-op pan check doesn't apply to the default view.

### Fixed while verifying

- Suspects mixed round 1 with the second-cause round (§7.5), so a pruned round-2 suspect (0.71) outranked the root
  cause (0.62). Round 2 now has its own "Second-cause search" group: its scores use a narrower symptom set.
- GPT-4o quoted the raw confidence ("0.576323"). The narrator now gets it rounded to 2 decimals. Hypothesis scores
  stay unrounded: rounding both made GPT-4o quote the winner's score (0.62) as the confidence (0.58), and Jev rejected
  the headline (0.06). With confidence-only rounding the headline passes at 0.92, 3/3 trials.
- Why-not printed `scored 0.486816` → 2 decimals.
- In a real Chrome (not headless): light native scrollbars on the dark UI (`color-scheme: dark`); the timeline pushed
  the column sideways and scrolled the tabs away (wrap + sticky tabs); citation spotlight didn't dim (the fade-in
  animation's fill mode held `opacity: 1`); the minimap was empty (controlled nodes had no measured size).
