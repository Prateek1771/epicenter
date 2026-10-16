# Epicenter: UI Screens

What every screen in `web/` has, how it looks, and what it calls. Existing screens first (as built in phase 8), then
gaps the design already promises, then candidate new screens. ASCII mockups are drawn at laptop width; real spacing,
colour and type come from the app (dark-first, Tailwind + shadcn, Geist / Geist Mono).

Sources: [USER_FLOW](USER_FLOW.md), [API](API.md), [phase 8](phases/phase-08-web-ui.md), [HLD §7](HLD.md#7-failure-modes),
[LLD §9](LLD.md#9-events-sse), [GRAPH_SCHEMA](GRAPH_SCHEMA.md), and the code under `web/app` and `web/components`.
How competitors build the same screens: [COMPETITOR_UI_RESEARCH.md](COMPETITOR_UI_RESEARCH.md).

---

## Contents

1. [Visual language](#1-visual-language)
2. [App shell (every page)](#2-app-shell-every-page)
3. [Incidents list `/`](#3-incidents-list-)
4. [Incident `/incident/[id]`](#4-incident-incidentid)
5. [Blast radius `/blast-radius`](#5-blast-radius-blast-radius)
6. [What-if `/simulate`](#6-what-if-simulate)
7. [Ask `/ask`](#7-ask-ask)
8. [Example runs `/runs`](#8-example-runs-runs)
9. [Eval `/eval`](#9-eval-eval)
10. [Degraded and empty states](#10-degraded-and-empty-states)
11. [Gaps: promised in the design, not on screen](#11-gaps-promised-in-the-design-not-on-screen)
12. [Candidate new screens](#12-candidate-new-screens)
13. [Priority summary](#13-priority-summary)

---

## 1. Visual language

| Token | Meaning | Used on |
|---|---|---|
| `st-open` | hypothesis open, not yet checked | canvas ring, pills |
| `st-supported` | evidence supports it | canvas ring, pills |
| `st-refuted` (red) | refuted / anomaly / error | ring, anomaly badge, `% err` edge label |
| `st-inconclusive` (grey) | a query timed out or data missing | grey branch |
| `st-pruned` | lost on score | dim ring |
| `st-confirmed` (green) | root cause, winning path | glow, crown badge, verdict card |
| `ov-matched` (green, solid outline) | predicted and observed | Fault Simulator overlay |
| `ov-missed` (amber, dashed outline) | predicted, but stayed quiet | overlay, warnings |
| `ov-unexplained` (red, solid outline) | observed, not predicted | overlay |
| `primary` | interactive, spotlight, live | citations, spotlight path |

Rules the UI keeps:
- **Status is colour + icon + word**, never colour alone (`StatusPill`).
- Operation ids render as `service/name`: service in foreground, `/name` muted, coloured dot per service (`OpLabel`).
- Numbers are mono and tabular. Scores show 2 decimals, confidence as a percent.
- Skeletons while loading; no layout jump as SSE events arrive.

Status pill legend (ASCII stand-ins used in the mockups below):

```
 ( ◌ Open )  ( ● Supported )  ( ✕ Refuted )  ( ? Inconclusive )  ( ⊘ Pruned )  ( ✓ Confirmed )
 ( ⟳ Diagnosing )  ( ✓ Diagnosed )  ( ? No root cause )  ( ➤ Delivered )  ( ⛨ Resolved )
```

---

## 2. App shell (every page)

File: `components/shell/top-bar.tsx`, `app/layout.tsx`.

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────────┐
│ [⌖] Epicenter   ◉ Incidents  ⑂ Blast radius  ⚗ What-if  ✉ Ask  ▶ Runs  ◔ Eval                       │
│                                                     ● All systems normal  [🔍 Jump to… ⌘K]  [astronomy-shop ▾] │
└──────────────────────────────────────────────────────────────────────────────────────────────────────┘
  sticky, 56 px, blurred background                                         toasts → bottom-right
```

| Part | What it does | API |
|---|---|---|
| Logo | Link home, keeps `?env=` | — |
| Nav | 6 routes. Icon only below `md`, with `aria-label` | — |
| Health dot | Green = ok, amber = degraded, red = API unreachable. Polls every 15 s. Tooltip lists each dependency | `GET /health` |
| ⌘K palette | Jump to the last 30 incidents (search by id, symptom, root cause) or to a page | `GET /incidents?limit=30` |
| Env switcher | One graph per environment. Choice lives in `?env=` and localStorage | `GET /envs` |

Health tooltip:

```
┌──────────────────────────┐
│ falkordb: ok             │
│ falkordb_mcp: ok         │
│ openrouter: ok           │
│ jev: ok                  │
│ openconnector: down      │
└──────────────────────────┘
```

Command palette:

```
┌───────────────────────────────────────────────────────────┐
│ 🔍 Incident id, symptom, page…                            │
├───────────────────────────────────────────────────────────┤
│ INCIDENTS                                                 │
│  ( ✓ Diagnosed )  inc-42            payment/Charge        │
│  ( ⟳ Diagnosing ) rc-re2tt_ts-auth… client/load          │
│  ( ? No root cause ) inc-am-77      flip-node/GET /prod…  │
│ PAGES                                                     │
│  ◉ Incidents   ⑂ Blast radius   ⚗ What-if   ✉ Ask  …     │
└───────────────────────────────────────────────────────────┘
```

---

## 3. Incidents list `/`

File: `app/page.tsx` · Persona: everyone · Status: **built**

```
┌──────────────────────────────────────────────────────────────────────────────────────────────┐
│ Incidents                                       [All] Diagnosing Diagnosed No root cause     │
│ Every alert becomes a live investigation:              Delivered Resolved                    │
│ suspects, evidence, a verdict you can check.                                                 │
│                                                                                              │
│ ┌──────────────────────────────────────────────────────────────────────────────────────────┐ │
│ │ INCIDENT            STATUS          ALERTING OP          ROOT CAUSE         CONF.  OPENED│ │
│ ├──────────────────────────────────────────────────────────────────────────────────────────┤ │
│ │ inc-42              ( ✓ Diagnosed ) checkout/PlaceOrder  payment/Charge     ████▌ 91% 4m │ │
│ │ inc-43              ( ⟳ Diagnosing) frontend/GET /cart   —                  —        1m →│ │
│ │ inc-am-77           ( ? No r.c. )   flip-node/GET /prod… —                  —        2h  │ │
│ │ rc-re2tt_ts-auth…   ( ➤ Delivered ) client/load          ts-auth/POST /log… ███▌  72% 1d │ │
│ │ inc-17              ( ⛨ Resolved )  checkout/PlaceOrder  payment/Charge     ████▊ 93% 7d │ │
│ └──────────────────────────────────────────────────────────────────────────────────────────┘ │
│                                      [ Load more ]                                           │
└──────────────────────────────────────────────────────────────────────────────────────────────┘
```

| Element | Detail |
|---|---|
| Header | Title, one-line pitch. With `?cause=redis`: "Filtered to root cause in **redis**. Clear" |
| Status filters | Toggle buttons (`aria-pressed`), written to `?status=` |
| Table | 6 columns on desktop; stacks to one column on mobile. Root cause in green. Arrow appears on hover |
| Refresh | Polls every 10 s |
| Pagination | Cursor-based "Load more" (never offset) |
| Empty | Radar icon + "No incidents here yet" + how to make one (`POST /api/v1/alerts`, RCAEval replay, Runs link) |
| Error | "The graph is offline." for `GRAPH_UNAVAILABLE`, else the error message in mono |

API: `GET /incidents?status&cause&limit=25&cursor`.

---

## 4. Incident `/incident/[id]`

Files: `app/incident/[id]/page.tsx`, `components/incident/{verdict,side,act}.tsx`, `components/graph/incident-canvas.tsx`,
`lib/{incident-state,useIncidentStream,layout}.ts` · Persona: Priya, judges · Status: **built** (the main demo screen)

### 4.1 Full layout

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│ ←  inc-42  ( ✓ Diagnosed )  🔔 alert on checkout/PlaceOrder           ● live   [⟲ Rerun]   [⛨ Resolve]      │
├──────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ ⚠ traces unavailable for this window: suspects that needed them may end inconclusive.        (only if gaps) │
├────────────────────────────┬───────────────────────────────────────────────────────────┬─────────────────────┤
│ LEFT RAIL  380px           │ CANVAS  (flex)                                            │ RIGHT RAIL  340px   │
│                            │                                                           │                     │
│ ┌────────────────────────┐ │  ┌ Fault Simulator  h-7 ─────────── ✕┐   Showing E3 ·   │ [Suspects][Timeline │
│ │ ♛ ROOT CAUSE      ╭──╮ │ │  │ ● payment/Charge                  │   propagation ✕  │  · 111][Notes]      │
│ │ ● payment/Charge  │91│ │ │  │ explains 6/7 · precision 0.82 ·   │                  │                     │
│ │ explains 6 of 7 · ╰──╯ │ │  │ order 0.90                        │                  │ WHY NOT…?           │
│ │ precision 0.82 ·       │ │  │ ▣ matched 6 ┆ missed 1 ▣ unexpl 1 │                  │ [why not… cart ][🔍]│
│ │ order 0.90             │ │  └───────────────────────────────────┘                  │                     │
│ │ [payment/Charge → chec │ │                                                           │ SUSPECTS  click to… │
│ │  kout/PlaceOrder]      │ │      (graph, see 4.3)                                     │ h-7 payment/Ch 0.83 │
│ │ Went bad first  ███ 1.0│ │                                                           │ h-3 cart/GetCa 0.41 │
│ │ Explains sympt. ██▌ .85│ │                                                           │ h-1 frontend/  0.20 │
│ │ Self-caused     ███ 1.0│ │                                                           │                     │
│ │ Anomaly str.    ██▊ .90│ │                                                           │ INCIDENT            │
│ │ Recent change   ███ 1.0│ │                                                           │ Alerts        3     │
│ │ Centrality      ██▏ .71│ │                                                           │ Diagnosis run 3     │
│ │ ────────────────────── │ │                                                           │ Weights 2026-10-15… │
│ │ Runner-up cart/GetC .41│ │  ┌minimap┐                                     [+][-][⤢]  │ Coverage      86%   │
│ └────────────────────────┘ │  └───────┘                                                │                     │
│ EXPLANATION                │                                                           │                     │
│ SEEN BEFORE                │                                                           │                     │
│ PROPOSED ACTIONS           │                                                           │                     │
└────────────────────────────┴───────────────────────────────────────────────────────────┴─────────────────────┘
  below lg: canvas first, then left rail, then right rail (stacked)
```

### 4.2 Header strip

| Element | Behaviour |
|---|---|
| ← | Back to the incidents list |
| id + status pill | Status comes from the live view, falling back to the detail |
| 🔔 alert on X | The symptom operation |
| `● live` | Pulsing dot while `diagnosing` and the stream is connected |
| `⚡ reconnecting…` | Amber pill while the SSE stream retries (with backoff, from `?after=<last seq>`) |
| Diagnose / Rerun | `POST /diagnose` (Rerun = `?force=true`, a new numbered run; old runs stay in the graph). Spinner + disabled while diagnosing |
| Resume diagnosis | Replaces Rerun when `diagnosing` with no events for 30 s (agent crash) |
| Resolve | Opens the resolve dialog (4.8). Disabled until there is a verdict |
| Gaps banner | Amber strip listing missing telemetry sources (`Incident.gaps`) |

### 4.3 Canvas

React Flow, elk layered layout left→right, grouped by service. Only the incident subgraph is drawn (24–42 nodes on RCAEval TT).

```
                     ┌──────────────────────────┐        ┌──────────────────────────┐
                     │▌frontend        🔔 alert │  ───▶  │▌checkout                 │
                     │▌GET /cart                │  31%err│▌PlaceOrder               │
                     │▌errors  h-1 · Refuted·.20│        │▌errors  h-4 · Pruned ·.38│
                     └──────────────────────────┘        └────────────┬─────────────┘
                                                                      │ ═══▶ (animated, green)
                     ┌──────────────────────────┐        ┏━━━━━━━━━━━━▼━━━━━━━━━━━━━┓
                     │▌cart                     │        ┃▌payment     ♛ root cause ┃  ← glow
                     │▌GetCart                  │        ┃▌Charge                   ┃
                     │▌latency h-3 · Pruned ·.41│        ┃▌errors h-7 · Confirmed·.83┃
                     └──────────────────────────┘        ┗━━━━━━━━━━━━━━━━━━━━━━━━━━┛
   ▌ = service colour strip      red-tinted card = has an anomaly      ring colour = hypothesis status
```

Node card (236 × 64): service colour strip · service name (muted, mono) · operation name · anomaly kind badge ·
`h-id · status · score` · badges `🔔 alert`, `♛ root cause`, `♛ 2nd cause`.

Edge: smoothstep arrow; `% err` label when error rate > 5%; winning path green, animated, glowing.

**Modes**

| Mode | Trigger | Look |
|---|---|---|
| Normal | default | all nodes, winning path glows; first view fits to winning path + alert |
| Overlay | click a suspect node or row | matched = solid green outline, missed = dashed amber, unexplained = solid red, predicted = dashed green; everything else dims to 30% |
| Spotlight | click a citation, path chip, or why-not answer | path nodes outlined in primary, edges animated, rest dimmed; pill top-right "Showing E3 · propagation · clear ✕" |

Overlay legend (top-left floating card):

```
┌ Fault Simulator   h-1 ─────────────────────── ✕ ┐
│ ● frontend/GET /cart                            │
│ explains 2 / 7 · precision 0.40 · order 0.50    │
│ ▣ matched 2   ┆▣┆ missed 3   ▣ unexplained 5    │
│ Predicted but quiet, off canvas: ad, email +1   │
└─────────────────────────────────────────────────┘
```

Extras: dotted grid background, minimap bottom-left (root = green, refuted = red, anomalous = rose, rest grey),
zoom controls bottom-right, nodes draggable, empty state "Nothing on the canvas yet: start a diagnosis."

Overlay demo moment (EXAMPLE_RUNS §1): alert fired on `frontend`; click `frontend` → small footprint, checkout and
payment light red as unexplained; click `payment/Charge` → the whole chain turns green, "explains 6 of 7".

### 4.4 Left rail: verdict card

```
┌─────────────────────────────────────────────┐
│ ♛ ROOT CAUSE                        ╭─────╮ │
│ ● payment/Charge                    │ 91% │ │   ← confidence ring (animated stroke)
│ explains 6 of 7 symptoms ·          ╰─────╯ │
│ precision 0.82 · order 0.90                 │
│ [payment/Charge] → [checkout/PlaceOrder]    │   ← click: spotlight winning path
│                                             │
│ Went bad first           ██████████  1.00   │
│ Explains the symptoms    ████████▌   0.85   │
│ Self-caused, not victim  ██████████  1.00   │   ← score_parts, deterministic
│ Anomaly strength         █████████   0.90   │
│ Recent change            ██████████  1.00   │
│ Graph centrality         ███████     0.71   │
│ ─────────────────────────────────────────── │
│ [2nd cause] ● ad/GetAds                     │   (only if found)
│ Runner-up   ● cart/GetCart            0.41  │
└─────────────────────────────────────────────┘
  green border + faint green gradient
```

Other states:

```
┌─────────────────────────────────────────────┐   ┌─────────────────────────────────────────────┐
│ ? NO ROOT CAUSE                             │   │ ┆ Investigating: suspects are being checked  ┆│
│ Nothing in the graph explains this alert    │   │ ┆ against the graph…                         ┆│
│ Checked 4 suspects; the best explains 31%   │   └─────────────────────────────────────────────┘
│ of the symptoms. No cause is invented.      │     dashed, while diagnosing
│ 💡 Check the alert threshold against the    │
│    baseline.                                │
└─────────────────────────────────────────────┘
  amber border
```

### 4.5 Left rail: explanation

```
EXPLANATION
( ✦ GPT-4o · every claim checked by Jev )  ( 1 unsupported claim removed )

WHAT
Checkout started failing because payment requests errored. [E3]  ✓ 0.94
WHERE
The failure began in payment/Charge, two hops below the alert. [E3][E1.1]  ✓ 0.88
WHY
Payment requests started failing right after the paymentFailure flag
was turned on. [E5][E3]  ✓ 0.94
```

| Element | Behaviour |
|---|---|
| Source badge | green "GPT-4o · every claim checked by Jev" / grey "AI explanation unavailable: built from the evidence" / amber "Claims not verified" |
| Dropped badge | "N unsupported claims removed" |
| `[E3]` chip | Click → spotlight that evidence's path; click again to clear. Ring when active |
| `✓ 0.94` | Tooltip: "Jev: probability the cited evidence supports this claim" |
| `(unverified)` | Shown per claim when Jev was down |
| Empty | "The explanation is written once the verdict is in." |

### 4.6 Left rail: seen before (memory)

```
SEEN BEFORE
┌─────────────────────────────────────────────┐
│ ↺ inc-17                              0.93  │   ← similarity (vector + graph overlap)
│ ● payment/Charge                            │
│ Fixed by: turn off flag paymentFailure      │
└─────────────────────────────────────────────┘
```
Empty: "No similar resolved incidents yet. Resolve this one and it becomes memory."

### 4.7 Left rail: proposed actions + delivery

```
PROPOSED ACTIONS
┌─────────────────────────────────────────────┐
│ (1) turn off flag paymentFailure            │
│     [fixed this before]  relevance 0.91     │
├─────────────────────────────────────────────┤
│ (2) restart payment                         │
│     [runbook]  relevance 0.62               │
├─────────────────────────────────────────────┤
│ (3) scale cart                              │
│     [unrelated to the cause]  relevance 0.12│
└─────────────────────────────────────────────┘
[➤ Sent to slack]  [➤ Retry linear]
slack: https://…/p1792159512
linear: LINEAR_TEAM_ID not set
```

| Element | Behaviour |
|---|---|
| Rank + name | Actions are proposals only (hard rule 9) |
| Tag | `history` green "fixed this before" · `runbook` grey · `demoted` amber "unrelated to the cause" |
| `✓ fixed it` | After resolve picked this action |
| Send buttons | Per target. "Send to X" → "Sent to X" (secondary) or "Retry X" on failure. Enabled on diagnosed / delivered / no_root_cause |
| Result lines | Permalink on success, error message (amber) on failure; toasts too |

API: `POST /incidents/{id}/deliver {targets}`.

### 4.8 Resolve dialog

```
┌──────────────────────────────────────────────────────┐
│ Resolve incident                                  ✕  │
│ Pick what fixed it: the next incident like this one  │
│ will rank that fix first.                            │
│                                                      │
│ What fixed it?                                       │
│ (•) turn off flag paymentFailure                     │
│ ( ) restart payment                                  │
│ ( ) Something else / not listed                      │
│                                                      │
│ Resolved by  [ priya                     ]           │
│ Note         [ flag off, errors gone     ]           │
│                                                      │
│                                        [ Resolve ]   │
└──────────────────────────────────────────────────────┘
```
API: `POST /resolve` → writes `RESOLVED_BY`, `FIXED`, runbook success +1.

### 4.9 Right rail: Suspects tab

```
[Suspects] [Timeline · 111] [Notes]          ← sticky tabs
WHY NOT…?
[ why not… cart              ] [🔍]          ← datalist of services on the canvas
┌───────────────────────────────────────────┐
│ ? CART: LOST ON SCORE                     │
│ cart scored 0.41 against payment's 0.83:  │
│ it went bad 40 s later.                   │
│ E8 propagation · E9 victim                │
└───────────────────────────────────────────┘
SUSPECTS              click to see what each would explain
 h-7  ● payment/Charge        0.83 ( ✓ Confirmed )
 h-3  ● cart/GetCart          0.41 ( ⊘ Pruned )
 h-1  ● frontend/GET /cart    0.20 ( ✕ Refuted )
 h-9  ● ad/GetAds             …    ( ◌ Open )
SECOND-CAUSE SEARCH
 Scored on the symptoms the root cause leaves unexplained;
 not ranked against the list above.
 h-12 ● ad/GetAds             0.66 ( ● Supported )
INCIDENT
 Alerts 3 · Diagnosis run 3 · Weights 2026-10-15.v2 · Coverage 86%
```

Why-not answers: `victim`, `later_onset`, `no_anomaly`, `not_upstream`, `small_footprint`, `lost_on_score`,
`is_root_cause`. The answer's evidence path is spotlighted on the canvas.
The suspect list is the accessible twin of the canvas, sorted by score then id.

### 4.10 Right rail: Timeline tab

```
│ #101 ● hypothesis h-7 created: payment/Charge (2 hops)
│ #104 ● E3 propagation supports h-7
│ #107 ● footprint h-7: explains 6 of 7
│ #109 ● h-3 pruned (0.41)
│ #111 ● verdict: payment/Charge 91%
```
Dot colour by tone (good / bad / info / warn / neutral). `aria-live="polite"`, auto-scrolls. A toast fires on `verdict`.
SSE events: `incident.status`, `hypothesis.created`, `evidence.added`, `footprint`, `hypothesis.status`, `verdict`,
`no_root_cause`, `memory.similar`, `explanation`, `action`.

### 4.11 Right rail: Notes tab

```
┌───────────────────────────────────────────┐
│ What do you know? e.g. currency deployed  │
│ at 14:02                                  │
└───────────────────────────────────────────┘
[ handle  ]  (○━) a change           [✎ Add]
[ service…            ▾] [ deploy ▾]         ← only when "a change" is on
📖 Notes land in the graph as decisions; a change is seen by the next diagnosis run.
```
API: `POST /notes {by, text, change?}` → `Decision` (+ `Change`).

### 4.12 Error page

```
                 ⚠
        Incident not found          (or "The graph is offline" / "Couldn't load the incident")
   No incident 'inc-99' in env 'astronomy-shop'
            [ ← All incidents ]
```

---

## 5. Blast radius `/blast-radius`

File: `app/blast-radius/page.tsx` · Persona: Arjun · Status: **built (list view)**

```
┌──────────────────────────────────────────────────────────────────────────────────────┐
│ ⑂ Blast radius                                                                       │
│ If this service fails, which operations can it reach through the call graph,         │
│ and who owns them?                                                                   │
│ [ redis                       ] [ Show impact ]                                      │
│                                                                                      │
│ ┌────────────┐ ┌────────────┐ ┌────────────┐   ┌──────────────────────────────────┐  │
│ │ Services   │ │ Operations │ │ Past inc.  │   │ 👥 OWNERS TO PULL IN             │  │
│ │ 3          │ │ 9          │ │ 1          │   │ team-cart                        │  │
│ └────────────┘ └────────────┘ └────────────┘   │ team-payments                    │  │
│ ┌────────────────────────────────────────────┐ │ team-web                         │  │
│ │ 1 HOP AWAY · 2                             │ └──────────────────────────────────┘  │
│ │ ● cart/GetCart                 team-cart   │ ┌──────────────────────────────────┐  │
│ │ ● cart/AddItem                 team-cart   │ │ ↺ PAST INCIDENTS ROOTED HERE     │  │
│ ├────────────────────────────────────────────┤ │ inc-11                           │  │
│ │ 2 HOPS AWAY · 4                            │ │ All incidents caused by redis →  │  │
│ │ ● checkout/PlaceOrder          team-paym…  │ └──────────────────────────────────┘  │
│ │ …                                          │ [ ⚗ Simulate a failure ]              │
│ └────────────────────────────────────────────┘                                       │
└──────────────────────────────────────────────────────────────────────────────────────┘
```

| Element | Detail |
|---|---|
| Picker | Text input + datalist from `GET /services`; writes `?service=` |
| Counts | Services, operations, past incidents |
| Hop groups | Reverse `CALLS*1..6` into the service's operations, grouped by distance, with owner |
| Empty | "Nothing calls into redis: a failure stays contained." |
| Owners | Unique `OWNED_BY` teams |
| Past incidents | Links to incidents; "All incidents caused by X →" goes to `/?cause=X` |
| Simulate | Jumps to `/simulate?service=X` (reachable → how likely) |

API: `GET /blast-radius/{service}`, `GET /services`.

---

## 6. What-if `/simulate`

File: `app/simulate/page.tsx` · Persona: Arjun · Status: **built**

```
┌────────────────────────────────────────────────────────────────────────────────────────────┐
│ ⚗ What-if                                                                                  │
│ The Fault Simulator, no incident needed: if this fails like that, what breaks,             │
│ how likely, and how soon?                                                                  │
│ [ redis               ] [down][errors][latency][cpu][mem][saturation]  (○━) 💾 save [Simulate]│
│                                                                                            │
│ ┌────────────────────────────────────────────────────────────────────────────────────────┐ │
│ │ If redis → down:          9 operations in 3 services · rules 2026-10-15               │ │
│ ├────────────────────────────────────────────────────────────────────────────────────────┤ │
│ │ 1  ● cart/GetCart           [errors]  █████████▌ 0.95   ≤ 15s · 1 hop    team-cart     │ │
│ │ 2  ● cart/AddItem           [errors]  ████████▊  0.88   ≤ 15s · 1 hop    team-cart     │ │
│ │ 3  ● checkout/PlaceOrder    [errors]  ██████     0.61   ≤ 45s · 2 hops   team-payments │ │
│ │ 4  ● frontend/GET /cart     [latency] ███▌       0.35   ≤ 60s · 3 hops   team-web      │ │
│ └────────────────────────────────────────────────────────────────────────────────────────┘ │
└────────────────────────────────────────────────────────────────────────────────────────────┘
  probability bar: red > 0.7, amber > 0.4, grey otherwise
```

| Element | Detail |
|---|---|
| Target | Service, or an operation if the text contains `/` |
| Kind | Radio group of 6 failure kinds |
| Save | Writes a `Simulation` node; toast "Simulation saved: sim-12, a later incident can be compared with it" |
| Rows | Rank, op, predicted symptom kind, probability, expected delay, hops, owner. Mobile hides the last three |
| Empty | "Nothing with traffic depends on it: the failure stays contained." |

API: `POST /simulate {service|operation, kind, save}`.

---

## 7. Ask `/ask`

File: `app/ask/page.tsx` · Persona: Arjun, Priya · Status: **built**

```
┌─────────────────────────────────────────────────────────────────────┐
│ ✉ Ask the graph                                                     │
│ GPT-4o answers with the typed graph tools first, and falls back to  │
│ a read-only Cypher query. Every answer shows the path it rests on.  │
│                                                                     │
│                          ┌────────────────────────────────────────┐ │
│                          │ who should I page for checkout?        │ │  ← user bubble
│                          └────────────────────────────────────────┘ │
│ ┌─────────────────────────────────────────────────────────────────┐ │
│ │ ✦ team-payments owns checkout; Ravi fixed the last two checkout │ │  ← answer
│ │   incidents.                                                    │ │
│ │ [person:ravi] → FIXED → [inc-17] → ROOT_CAUSE → [h-7] → BLAMES  │ │  ← path chips
│ │   → [checkout/PlaceOrder]                                       │ │
│ │ (🔧 who_knows)                                                  │ │  ← tools used
│ │ Read-only Cypher it ran (falkordb-mcp):                     [⧉] │ │  ← only on fallback
│ │ ┌─────────────────────────────────────────────────────────────┐ │ │
│ │ │ MATCH (o:Operation)<-[:CALLS]-(c) RETURN o.id, count(c) …   │ │ │
│ │ └─────────────────────────────────────────────────────────────┘ │ │
│ └─────────────────────────────────────────────────────────────────┘ │
│                                                                     │
│ ┌─────────────────────────────────────────────────────────────┬───┐ │
│ │ Ask about services, owners, incidents, fixes…               │ → │ │  ← sticky composer
│ └─────────────────────────────────────────────────────────────┴───┘ │
└─────────────────────────────────────────────────────────────────────┘
```

Before the first question, a 2×2 grid of examples: "Who should I page for payment?", "Which operation has the most
callers?", "What was the root cause of the last resolved incident and how was it fixed?", "What breaks if redis goes down?".

States: "walking the graph…" spinner; LLM down → "The ask box needs the LLM, and it's unavailable right now."
Enter sends, Shift+Enter is a new line. Conversation is in memory only.

API: `POST /ask {question, incident_id: null}`.

---

## 8. Example runs `/runs`

File: `app/runs/page.tsx` · Persona: judge / demo · Status: **stub, waits on phase 9**

Today:

```
┌───────────────────────────────────────────────────────────────┐
│ ▶ Example runs                                                │
│ Start a scripted fault on an example environment (OTel Demo,  │
│ flip-commerce) or replay an RCAEval case, then watch the      │
│ incident page.                                                │
│ ┆                         ◷                                  ┆│
│ ┆                 Arrives with phase 9                       ┆│
│ ┆ Scenario runs need the live environments and their fault   ┆│
│ ┆ scripts. The page calls GET /runs/scenarios and shows it   ┆│
│ ┆ here as soon as the API serves it.                         ┆│
└───────────────────────────────────────────────────────────────┘
```

If `/runs/scenarios` answers, it shows a 2-column grid of cards (title + `env · id`) with **no start button**.

Target per USER_FLOW Flow 7 (to build):

```
┌───────────────────────────────────────────────────────────────────────────────────────┐
│ ▶ Example runs                [ OTel Demo ] [ flip-commerce ] [ RCAEval ]              │
│                                                                                       │
│ ┌──────────────────────────────────┐  ┌──────────────────────────────────┐            │
│ │ flagd: paymentFailure            │  │ circuit-misconfig      ★ judges  │            │
│ │ astronomy-shop · multi-hop       │  │ flip-commerce                    │            │
│ │ Expected: payment/Charge,        │  │ Expected: flip-node/*, change    │            │
│ │ change = flag on                 │  │ config MONGO_CIRCUIT_FAILS=1;    │            │
│ │                                  │  │ mongodb refuted                  │            │
│ │ [▶ Start]  [↶ Undo]              │  │ [▶ Start]  [↶ Undo]              │            │
│ └──────────────────────────────────┘  └──────────────────────────────────┘            │
│ ┌──────────────────────────────────┐  ┌──────────────────────────────────┐            │
│ │ Healthy baseline                 │  │ re2tt_ts-auth-service_cpu_1      │            │
│ │ Expected: no_root_cause          │  │ rcaeval-tt · replay ~15 s        │            │
│ │ [▶ Start]                        │  │ [▶ Replay]                       │            │
│ └──────────────────────────────────┘  └──────────────────────────────────┘            │
│ Start → POST /runs → opens /incident/<id> and you watch it live                       │
└───────────────────────────────────────────────────────────────────────────────────────┘
```
Starting a fault changes an environment, so a confirm step belongs on Start.

API: `GET /runs/scenarios`, `POST /runs {env, scenario}` → `{run_id, incident_id}`.

---

## 9. Eval `/eval`

File: `app/eval/page.tsx` · Persona: judge · Status: **stub, waits on phase 10**

When `GET /eval` answers:

```
┌───────────────────────────────────────────────────────────┐
│ ◔ Eval                                                    │
│ Root-cause accuracy on the RCAEval benchmark (AC@1, AC@3),│
│ with ablations.                                           │
│ ┌───────────────────────────────────────────────────────┐ │
│ │ VARIANT                      AC@1        AC@3         │ │
│ ├───────────────────────────────────────────────────────┤ │
│ │ full (90 cases)              —%          —%           │ │
│ │ no pagerank                  —%                       │ │
│ │ no temporal                  —%                       │ │
│ │ no mechanism                 —%                       │ │
│ └───────────────────────────────────────────────────────┘ │
└───────────────────────────────────────────────────────────┘
```
Otherwise the "Arrives with phase 10" card. Room to grow: per-case table (case, label, our top-3, hit/miss, link to
the incident), weights + rules version, held-out vs dev split, a bar chart of the ablations.

---

## 10. Degraded and empty states

From [HLD §7](HLD.md#7-failure-modes); all are built.

| Failure | Where | What the user sees |
|---|---|---|
| FalkorDB down | everywhere | red health dot; "The graph is offline" on lists and incident page |
| API restart / network drop | incident | header pill `⚡ reconnecting…`; stream resumes from last seq, no duplicate nodes |
| Telemetry source down | incident | amber gaps banner; affected suspects end `inconclusive` (grey ring) |
| OpenRouter down | explanation | grey "AI explanation unavailable: built from the evidence" |
| Jev down | explanation | amber "Claims not verified", per-claim `(unverified)` |
| OpenConnector down | actions | "Retry slack" button + amber error line |
| Agent crash | incident header | "Resume diagnosis" after 30 s quiet |
| Query too slow | canvas | grey branch (`inconclusive`) |
| Nothing explains the alert | verdict | amber "No root cause" card |
| LLM down on Ask | ask | inline red "needs the LLM" message |

---

## 11. Gaps: promised in the design, not on screen

| # | Gap | Where it's promised | Needs |
|---|---|---|---|
| G1 | **Prediction vs reality**: incident shows "predicted 9, observed 8" against a saved `Simulation` | USER_FLOW Flow 8 step 5 | API field + UI panel |
| G2 | **Notes drawn on the canvas** as nodes linked to the incident; Notes tab doesn't list past decisions | USER_FLOW Flow 6 step 5 | API (list decisions) + UI |
| G3 | **Expand a node** to its neighbours on the canvas | phase 8 Scalability (`GET /graph/subgraph`) | UI only |
| G4 | **List of saved simulations** | GRAPH_SCHEMA `Simulation` | small API + UI |
| G5 | **Ask inside an incident** (`incident_id` is never sent); ask paths not drawn on a graph | API.md `/ask` | UI only |
| G6 | **Query latency** (`query_ms` p50/p95) never displayed | API.md `/health` | UI only |
| G7 | **Run history / compare**: runs are kept and numbered, only the current one is visible | LLD §8 | API + UI |
| G8 | **Runs start + undo** | phase 9 | backend first |
| G9 | **Slack / Linear card preview** before sending | — | UI only |

Mockups for the small ones:

G1, prediction vs reality panel (left rail, under verdict):

```
┌ PREDICTED vs OBSERVED ─────────────── sim-12 (2h ago, Arjun) ┐
│ predicted 9 · observed 8 · matched 7                         │
│ ✓ cart/GetCart        p 0.95  seen at +12s                   │
│ ✓ checkout/PlaceOrder p 0.61  seen at +40s                   │
│ ┆ frontend/GET /cart  p 0.35  stayed quiet                   │
│ ✕ ad/GetAds           not predicted, broke                   │
└──────────────────────────────────────────────────────────────┘
```

G2, notes as nodes on the canvas:

```
  ╭────────────────────────────╮
  │ ✎ priya · 14:06            │ ┄┄┄┄┄▶  ┌──────────────────┐
  │ currency deployed at 14:02 │         │▌currency         │
  │ [change: deploy]           │         │▌Convert          │
  ╰────────────────────────────╯         └──────────────────┘
   rounded, dashed link = human input
```

G9, delivery preview:

```
┌ Slack preview · #incidents ──────────────────────────────┐
│ 🔴 inc-42 · checkout/PlaceOrder failing                   │
│ Root cause: payment/Charge (91%) · explains 6 of 7        │
│ Why: paymentFailure flag turned on at 14:03:31 [E5]       │
│ Do: 1. turn off flag paymentFailure (fixed this before)   │
│ [Open in Epicenter]                                       │
│                                      [Cancel] [➤ Send]    │
└──────────────────────────────────────────────────────────┘
```

---

## 12. Candidate new screens

Each one is grounded in data the graph already holds ([GRAPH_SCHEMA](GRAPH_SCHEMA.md)). Competitor references are
from [COMPETITORS](COMPETITORS.md) and general knowledge; check them against current product pages.

### 12.1 Service map `/map`

**Why:** only one screen draws a graph today, in a graph hackathon. **Data:** `GET /graph/subgraph`, `GET /services`
(both exist). **Ref:** Datadog Service Map, Coroot, Traversal "production world model".

```
┌──────────────────────────────────────────────────────────────────────────────────────────────┐
│ ◎ Service map   astronomy-shop · 20 services · 148 ops        [Services|Operations] [🔍 find]│
├──────────────────────────────────────────────────────────────────────┬───────────────────────┤
│                                                                      │ ● payment             │
│   (frontend-proxy)──▶(frontend)──▶(checkout)──▶((payment))           │ kind: app             │
│                          │             │  ╲          ▲ red halo       │ owner: team-payments  │
│                          ▼             ▼   ╲                          │ ops: 3                │
│                       (cart)──▶(redis)  (currency)                    │ ───────────────────── │
│                          │                                            │ ANOMALIES NOW         │
│                          ▼                                            │ Charge · errors 0.95  │
│                       (ad)     (email)    (shipping)                  │ RECENT CHANGES        │
│                                                                      │ flag paymentFailure   │
│  node size = rps · edge width = rps · edge colour = err rate          │ on · 14:03            │
│  red halo = anomaly now · ♛ = root cause of an open incident          │ ───────────────────── │
│                                                                      │ [⑂ Blast radius]       │
│                                                     [+][-][⤢] ┌mini┐ │ [⚗ What-if]            │
│                                                               └────┘ │ [↺ Past incidents (2)]│
└──────────────────────────────────────────────────────────────────────┴───────────────────────┘
```

Features: service ↔ operation zoom levels, click to open a side panel, double-click to expand neighbours (`hops=1..3`),
search to centre, live anomaly halos from open incidents. Above a few hundred nodes, swap React Flow for a WebGL renderer
(sigma.js / Cosmograph) behind the same props (phase 8 note).

### 12.2 Graph-mode Blast radius / What-if

**Why:** both pages are lists; drawing them reuses the incident canvas. **Data:** existing endpoints.
**Ref:** Causely impact view.

```
┌ If redis → down ── 9 ops · 3 services ─────────────────── [List | Graph] ┐
│                                                                          │
│   HOP 0            HOP 1                HOP 2                HOP 3       │
│  ┏━━━━━━━┓      ┌───────────┐       ┌──────────────┐     ┌──────────┐   │
│  ┃ redis ┃ ───▶ │ cart/Get  │ ───▶  │ checkout/    │ ──▶ │ frontend │   │
│  ┃ down  ┃      │ p 0.95 15s│       │ PlaceOrder   │     │ p 0.35   │   │
│  ┗━━━━━━━┛ ───▶ │ cart/Add  │       │ p 0.61 45s   │     │ 60s      │   │
│                 │ p 0.88    │       └──────────────┘     └──────────┘   │
│                 └───────────┘                                            │
│  fill intensity = probability · column = hops · badge = owner            │
│  ▶ Play: animate the failure spreading in expected order                 │
└──────────────────────────────────────────────────────────────────────────┘
```

A "Play" button animating the spread in `expected_delay_s` order would make the Fault Simulator obvious in a demo.

### 12.3 Changes feed `/changes`

**Why:** "what changed?" is the first question on call. **Data:** `Change` nodes (deploy, flag, config, infra,
manual), `AUTHORED`. Needs `GET /changes`. **Ref:** Anyshift (whole product), incident.io.

```
┌──────────────────────────────────────────────────────────────────────────────────────────┐
│ ⟲ Changes          [all][deploy][flag][config][infra][manual]   service [ any ▾]  24h ▾  │
├──────────────────────────────────────────────────────────────────────────────────────────┤
│ 14:03  ⚑ flag     payment    paymentFailure → on        flagd     ⚠ inc-42 opened +1m    │
│ 14:02  ⇪ deploy   currency   v1.8.2                     priya     (manual note)          │
│ 11:40  ⚙ config   flip-node  MONGO_CIRCUIT_FAILS=1      faults.py ⚠ inc-am-80 opened +20s│
│ 09:15  ▣ infra    mongodb    docker stop mongo1         faults.py ⚠ inc-am-79 opened +8s │
│                                                                                          │
│ ──────┬──────┬──────┬──────┬──────┬──────┬──────  ← time strip: changes ▲ vs incidents ● │
│       ▲      ▲●            ▲●                ▲●                                          │
└──────────────────────────────────────────────────────────────────────────────────────────┘
```

### 12.4 Run compare `/incident/[id]/runs`

**Why:** the positioning is "deterministic, accuracy you can check" (COMPETITORS §5); no competitor shows this.
**Data:** numbered runs kept in the graph (LLD §8). Needs a runs endpoint.

```
┌ inc-42 · diagnosis runs ───────────────────────────────────────────────────────────────┐
│ Run [2 ▾]  vs  Run [3 ▾]          weights 2026-10-15.v2 = 2026-10-15.v2   rules same    │
│                                                                                        │
│  RANK  RUN 2                     RUN 3                     Δ                           │
│  1     payment/Charge   0.83     payment/Charge   0.83     =  identical                 │
│  2     cart/GetCart     0.41     cart/GetCart     0.41     =                           │
│  3     frontend/GET     0.20     frontend/GET     0.20     =                           │
│                                                                                        │
│  score_parts  ✓ byte-identical                                                          │
│  ( ✓ Same input → same answer )                                                        │
│                                                                                        │
│  (with a weights change: Δ column shows ↑ ↓ and which part moved)                       │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

### 12.5 Teams and ownership `/teams`

**Why:** "who do I page" without the LLM. **Data:** `Team`, `Person`, `OWNED_BY`, `MEMBER_OF`, `FIXED`, `AUTHORED`;
the `who_knows` tool already exists. **Ref:** PagerDuty service directory, Rootly.

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│ 👥 Teams                                                     [🔍 service or person]│
├──────────────────────────┬───────────────────────────────────────────────────────┤
│ team-payments        ▸   │ team-payments                                         │
│ team-cart                │ SERVICES   checkout · payment · currency              │
│ team-web                 │ PEOPLE                                                │
│ (no owner) 4 services    │  ravi    fixed 2 incidents · authored 5 changes       │
│                          │  meera   fixed 1                                      │
│                          │ RECENT INCIDENTS on owned services                    │
│                          │  inc-42  payment/Charge  ( ✓ Diagnosed )              │
│                          │  inc-17  payment/Charge  ( ⛨ Resolved ) by ravi       │
└──────────────────────────┴───────────────────────────────────────────────────────┘
```

### 12.6 Runbooks `/runbooks`

**Why:** shows memory learning over time. **Data:** `Runbook {kind, steps, success}`, `FOR`, `FROM`.
**Ref:** Rootly / incident.io workflows.

```
┌──────────────────────────────────────────────────────────────────────────┐
│ 📖 Runbooks                                                              │
│ ┌──────────────────────────────────────────────────────────────────────┐ │
│ │ rb-flag-rollback          kind: errors     for: payment, ad           │ │
│ │ 1. turn off the flag              worked 3 / 3  ██████████            │ │
│ │ 2. restart the service            worked 0 / 1  ░░░░░░░░░░            │ │
│ │ last used inc-42 · 2h ago                                             │ │
│ ├──────────────────────────────────────────────────────────────────────┤ │
│ │ rb-mongo-failover         kind: down       for: mongodb               │ │
│ │ 1. wait for election              worked 2 / 2                        │ │
│ └──────────────────────────────────────────────────────────────────────┘ │
│ Read-only here: runbooks come from seed/runbooks.yaml                    │
└──────────────────────────────────────────────────────────────────────────┘
```

### 12.7 System / trust `/system`

**Why:** "here's exactly how it scores" backs the open + deterministic pitch. **Data:** `GET /health` (incl.
`query_ms`), `weights.json`, `seed/propagation_rules.yaml` versions, Jev `min_support`. Needs a small config endpoint.

```
┌──────────────────────────────────────────────────────────────────────────────────────┐
│ ⚙ System                                                                             │
│ DEPENDENCIES                            QUERY LATENCY (p50 / p95, budget 200 ms)      │
│ ● falkordb       ok                     Q1 candidates    9 / 31   ███▏               │
│ ● falkordb_mcp   ok                     Q2 propagation  14 / 48   ████▊              │
│ ● openrouter     ok                     Q3 mechanism     …                           │
│ ● jev            ok                     Q4 pagerank      …                           │
│ ○ openconnector  down                   Q5 memory        …                           │
│                                         Q6 footprint     …                           │
│ SCORING (weights 2026-10-15.v2)         RULES (propagation 2026-10-15)               │
│ onset_earliness  0.25                   errors  → callers errors   p 0.80 · 0–30 s   │
│ footprint        0.20                   down    → callers errors   p 0.95 · 0–15 s   │
│ mechanism_fit    0.20                   latency → callers latency  p 0.70 · 0–60 s   │
│ …                                       …                                            │
│ Jev min_support 0.65 (calibrated 2026-10-16)                                         │
└──────────────────────────────────────────────────────────────────────────────────────┘
  (weight and rule values above are placeholders: read them from the files)
```

### 12.8 Postmortem / report `/incident/[id]/report`

**Why:** something to hand to people outside the incident. **Data:** `GET /incidents/{id}` (exists) + timeline.
**Ref:** incident.io and Rootly postmortems.

```
┌────────────────────────────────────────────────────────────────┐
│ Incident report · inc-42                 [⎙ Print] [⧉ Copy MD] │
│ astronomy-shop · opened 14:05 · resolved 14:31 (26 min)        │
│ ─────────────────────────────────────────────────────────────  │
│ SUMMARY   checkout/PlaceOrder failed; root cause payment/Charge │
│           (91%), explains 6 of 7 symptoms.                     │
│ TIMELINE  14:03 flag paymentFailure on                         │
│           14:04 payment/Charge errors begin                    │
│           14:05 alert on checkout/PlaceOrder                   │
│           14:06 verdict · 14:09 sent to Slack · 14:31 resolved │
│ WHY       (cited claims, as in the explanation panel)          │
│ GRAPH     [static snapshot of the winning path]                │
│ FIX       turn off flag paymentFailure · by priya              │
│ RULED OUT cart (lost on score), frontend (victim)              │
└────────────────────────────────────────────────────────────────┘
```

### 12.9 War-room dashboard `/live`

**Why:** projector view for the demo and on call. **Data:** existing (`/incidents?status=diagnosing`, `/health`).
**Ref:** Datadog / PagerDuty ops consoles.

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ ● LIVE  astronomy-shop                                 14:07:12   all ok ●   │
├───────────────────────────────┬──────────────────────────────────────────────┤
│ OPEN NOW                      │  ┌─ inc-43 (mini canvas, live) ───────────┐  │
│ ⟳ inc-43 frontend/GET /cart   │  │  ○──▶○──▶◉                             │  │
│   5 suspects · 2 refuted      │  │  branches resolving…                   │  │
│ ✓ inc-42 payment/Charge 91%   │  └────────────────────────────────────────┘  │
│                               │                                              │
│ TODAY  3 incidents · 1 no-rc  │  RECENT CHANGES  flag paymentFailure on 14:03│
└───────────────────────────────┴──────────────────────────────────────────────┘
```

### 12.10 Landing page `/about`

**Why:** judges arrive cold. **Data:** static + `GET /eval`.

```
┌──────────────────────────────────────────────────────────────────────┐
│                 ⌖ Epicenter                                          │
│    Find where every outage started.                                  │
│    Open, graph-native root cause analysis whose accuracy you can     │
│    check.                                                            │
│        [▶ Run a demo fault]   [◔ See the benchmark: AC@1 —%]         │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ │
│  │ The graph is │ │ Fault        │ │ Every answer │ │ Same input → │ │
│  │ the reasoning│ │ Simulator    │ │ is a path    │ │ same answer  │ │
│  └──────────────┘ └──────────────┘ └──────────────┘ └──────────────┘ │
└──────────────────────────────────────────────────────────────────────┘
```

### Skip for the hackathon

| Screen | Reason |
|---|---|
| Settings / integrations | Config lives in `.env`; no secrets in the UI (hard rule 11) |
| Auth / SSO / users | Open-core paid tier (COMPETITORS §5) |
| Cross-environment compare | Hard rule 8: never query across `env:*` graphs |
| Action execution ("run this fix") | Hard rule 9: actions are proposals only |

---

## 13. Priority summary

| Priority | Item | Type | Demo value | Effort |
|---|---|---|---|---|
| P0 | Runs: start / undo / opens incident | finish (phase 9) | very high | backend first |
| P0 | Eval: real numbers + per-case table | finish (phase 10) | very high | backend first |
| P1 | Service map `/map` | new | very high | medium, reuses canvas |
| P1 | Graph-mode What-if with "Play" | new | high | low–medium |
| P1 | G1 prediction vs reality | gap | high | medium |
| P2 | Run compare | new | high (trust story) | medium |
| P2 | System / trust page | new | medium–high | low |
| P2 | G5 Ask inside incident · G2 notes on canvas · G6 latency | gaps | medium | low |
| P3 | Changes feed | new | medium | medium |
| P3 | Teams · Runbooks · Report | new | medium | low–medium each |
| P3 | War-room · Landing | new | medium (demo polish) | low |
