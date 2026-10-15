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
web/lib/useIncidentStream.ts           SSE hook with Last-Event-ID reconnect
web/components/graph/                  React Flow canvas, node types, overlay legend
```

## Tasks

- [ ] Typed API client generated from `/openapi.json` (no hand-written duplicate types).
- [ ] `useIncidentStream`: `EventSource`, reducer keyed by event type, reconnect with `Last-Event-ID`, connection banner.
- [ ] Canvas (React Flow): operations as nodes grouped by service, `CALLS` edges, hypotheses as branches; status colours (open, supported, refuted, inconclusive grey, confirmed glow); auto layout (dagre / elk) computed once per new node batch.
- [ ] Overlay (LLD §7.8): observed = filled, predicted = dashed outline; matched green, missed amber, unexplained red; legend "explains 6 / 7 · precision 0.82 · order 0.9". Click a hypothesis to switch overlay.
- [ ] Verdict card: root cause, confidence, `score_parts` bars, runner-up, second root cause, `no_root_cause` state with what was checked.
- [ ] Evidence list and explanation: `[E3]` citations highlight that evidence's path on the canvas; "AI explanation unavailable" and "Claims not verified" badges.
- [ ] Why-not box (service autocomplete) → answer + highlighted path.
- [ ] Memory panel, actions with Send / Retry, Resolve dialog (pick the action that fixed it), notes input (Decision / Change).
- [ ] Blast radius (grouped by hops, owners, past incidents link → simulate), What-if (service + kind → ranked predictions, save), Ask (answer + clickable path + Cypher when fallback used), Runs (pick env + scenario), Eval table.
- [ ] Degraded states from HLD §7: "graph offline" banner, "Traces unavailable for this window", grey inconclusive branches, resume button.
- [ ] Dark-first, keyboard accessible, readable at laptop and projector sizes; skeleton loaders, no layout jump as SSE events arrive.

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
- Decide dagre vs elk early; elk handles grouped (compound) nodes better.

## Done when

Every screen in USER_FLOW works against the live API, the main flow is demo-ready, and degraded states look intentional.
