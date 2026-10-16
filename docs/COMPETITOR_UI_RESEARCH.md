# Competitor UI/UX Research: incident and root-cause screens

How 16 products in the AI SRE and observability space present an investigation and its root cause: their screens,
the content on them, how they look, and what they do. The last part maps every finding to Epicenter's screens in
[UI_SCREENS.md](UI_SCREENS.md). For market positioning and pricing, see [COMPETITORS.md](COMPETITORS.md).

**Researched:** 2026-10-16, by web search and by reading vendor docs, product pages, launch blogs and changelogs.

**Labels used:**
- **VERIFIED**: the claim was read on the cited page.
- **INFERRED**: the claim comes from a screenshot filename, alt text, a search snippet, or reasoning.
- Unmarked rows in the tables summarise VERIFIED points from the section above them.

**Limits:**
- Most public layouts are marketing mock-ups or videos. Few vendors document which panel sits where.
- Every accuracy figure is the vendor's own claim, and none is independently reproduced.
- Comparison posts written by competitors are flagged as biased.
- Screenshots are linked, not embedded. The ASCII mockups are **reconstructions** from docs and screenshots, and only
  labels that appear in a source are quoted.

---

## Contents

1. [Landscape at a glance](#1-landscape-at-a-glance)
2. [Graph-native AI SRE](#2-graph-native-ai-sre): Traversal, Resolve AI, Causely, Anyshift, Cleric, NeuBird
3. [Incumbents](#3-incumbents): Datadog, PagerDuty, incident.io, Rootly
4. [Open source and observability platforms](#4-open-source-and-observability-platforms): HolmesGPT, Coroot, K8sGPT, Grafana, Dynatrace, Honeycomb, New Relic
5. [Graph explorers](#5-graph-explorers-canvas-patterns): Neo4j Bloom, FalkorDB Browser
6. [Cross-cutting patterns](#6-cross-cutting-patterns)
7. [Gaps nobody fills](#7-gaps-nobody-fills)
8. [Epicenter mapping: what to borrow, where](#8-epicenter-mapping-what-to-borrow-where)
9. [Sources](#9-sources)

---

## 1. Landscape at a glance

| Product | Primary surface | Draws a graph in the investigation? | Confidence shown as | Shows ruled-out causes? | Actions | Memory in UI |
|---|---|---|---|---|---|---|
| **Traversal** | Slack + web + MCP | marketing only (world model, request path) | High / Medium / Low = "data completeness" | not documented | "recommendations, not actions" | Knowledge Bank: Wiki, Memories, Docs, Skills |
| **Resolve AI** | web chat + Slack | knowledge-graph image; not in investigation docs | none (bold verdict + numbers) | in prose | Approve/Reject card with risk + revertability | Team Knowledge, Skills |
| **Causely** | web dashboard + MCP + Grafana | **yes**: causality graph, service map, dataflow, blast radius | "high confidence" label (marketing) | not documented | remediation text | not documented |
| **Anyshift** | Slack + web + playground | 3D resource graph (demo); not in RCA | none | not documented | "Propose Fix" → PR | memory cards in 4 categories |
| **Cleric** | Slack + web | none | confidence scores (launch PR); grounded critique | **yes**: "causes that were ruled out" | fix PR, read-only by default | Memories with Remember / Reject |
| **NeuBird** | Slack + web console + IDE MCP | "service risk map" tile only | internal score (third-party) | not documented | Approve/Reject gate with policy + audit | `search_memory` in IDE |
| **Datadog Bits** | web + Slack | Service Map (separate); **hypothesis tree** | validated / invalidated / inconclusive | **yes**: invalidated nodes | one-click triage actions | `bits.md`, alert memory |
| **PagerDuty** | incident page tab + Slack | none rendered | % likelihood (Probable Origin only) | no | "With human approval" | per-service memory, editable |
| **incident.io** | Slack-first + web + macOS + Claude Code | none | **5-step evidence ladder** | **yes**: "discounted" findings in audit | PR-only | graded against real causes |
| **Rootly** | Slack + web | links out to Datadog | High / Med / Low label | no | "Propose change", Draft PR | similar past incidents |
| **HolmesGPT** | CLI + Slack + K9s | none | none | no | read-only, PRs in operator mode | none |
| **Coroot** | web | **yes**: eBPF service map + propagation paths | none (score on own benchmark) | flags unrelated signals | remediation text | none |
| **K8sGPT** | CLI + MCP | none | none | no | none | none |
| **Grafana** | web (Assistant, Asserts, Sift) | **yes**: Asserts graph, mind map | hypothesis status | **yes**: "Disprove" / "Reopen" | — | Knowledge Graph |
| **Dynatrace** | web | **yes**: Visual Resolution Path, Smartscape | up to 3 candidates, no score | no | workflows | close comment → annotation |
| **Honeycomb** | web Canvas + Slack | none | ranked fields with severity | no | — | — |
| **New Relic** | web issue page | issue maps | none | no | mitigation steps | "What happened previously?" |

**Reading the table:**
- **Only Causely, Grafana Asserts, Dynatrace and Coroot draw a causal or propagation graph inside the investigation.**
- **Only Datadog, incident.io, Grafana and Cleric show ruled-out causes.**
- **No product does both.** That is Epicenter's opening (§7).

---

## 2. Graph-native AI SRE

### 2.1 Traversal

**Surfaces** (VERIFIED, [docs](https://docs.traversal.com/introduction)):
- Web app at app.traversal.com, described as having "rich timelines, signal previews, and post-mortem creation".
- Slack: start an investigation by hand or have it auto-triggered, get the RCA summary, ask follow-ups in the thread.
- MCP access from Claude, Cursor and ChatGPT.
- A Workers console for managing its agents.

**Screens**

| Screen | Content (quoted labels) | Status |
|---|---|---|
| Investigation input | One box for a question or a pasted incident. "@" references teams, services, applications and environments. Changing the time window starts a new investigation | VERIFIED |
| Result | Sections: "Root cause summary", "Evidence citations", "Timeline", "Recommended next steps", relevant anomalies, impact estimate | VERIFIED |
| Production World Model™ (homepage) | 3D graph: "1,749,612 total nodes", "30 node types", "Details panel", "Node Types" filter with counts ("Pod 356,745"), "Drag to rotate · Click a node to explore" | marketing |
| Request analysis (homepage) | Sev-1 api-gateway. Chips "P99 4.2s", "47% requests dropped", "pool exhausted". Flow Client → api-gateway → auth-service → identity-provider, last hop "timeout suspected". Legend "Healthy call / Failing path / Originating slow service" | marketing |
| PR review card | "Don't merge — this will cause an incident", "Estimated impact: 0 pods affected", note on historical precedent, buttons "Open PR #2093", "Dismiss" | marketing |
| Knowledge Bank | Tabs "Traversal Wiki" (versioned; header shows pages added, updated, removed), "Memories", "Uploaded docs", "Skills" (`SKILL.md`). "Auto-created" chip. Memories table has a "Related investigation" column. Wiki pages have "Comments" and "Quote in comment" | VERIFIED |

**How the root cause is shown** (VERIFIED, [understanding results](https://docs.traversal.com/using-traversal/understanding-results)):
- Confidence is **High, Medium or Low**, and the docs say it "reflects data completeness, not certainty". A hover
  tooltip explains why for that investigation.
- Citations can be hovered for a preview, expanded, or followed into the source tool. Citation kinds: metric
  anomalies, log lines, deploys, code diffs, topology relationships, PRs.
- Next steps are labelled "recommendations, not actions".

Reconstruction of the result card:

```
┌ Root cause summary ─────────────────────────────── Confidence: [ High ⓘ ] ┐
│ identity-provider token endpoint timing out; api-gateway pool exhausted   │    ⓘ hover: why High
│                                                                           │      (data completeness,
│ Evidence citations   [metric anomaly ⧉] [log line ⧉] [deploy ⧉] [diff ⧉]  │       not certainty)
│ Relevant anomalies   P99 4.2s · 47% requests dropped · pool exhausted     │
│ Timeline             ──●────●──────●──────▶                               │
│ Impact estimate      …                                                    │
│ Recommended next steps (recommendations, not actions)                     │
│  1. …                                                                     │
└───────────────────────────────────────────────────────────────────────────┘
```

**Interaction** (VERIFIED, [Slack docs](https://docs.traversal.com/using-traversal/slack)):
- Workers join the incident channel and post findings in threads, keeping the main channel for updates everyone needs.
- On resolve, a Worker posts a draft post-mortem with a "5 Whys" section and what it got right and what it missed.
- Memory proposals arrive as Slack cards with approve and reject.
- The Sessions API has a "Stream session status" endpoint.

**Trust:**
- Citations deep-link into the source tools.
- Workers check recovery against live telemetry before calling an incident closed.
- Claimed RCA accuracy is 82% / 80% / 75% at named customer types, plus a "255-point Elo gap" over frontier models.
  These are vendor claims.

**Copy:**
- A confidence label with a stated definition and a tooltip.
- Memories that need approval and link back to the investigation that produced them.
- An agent-written wiki that humans comment on line by line.
- A pre-merge card that says "this PR will cause an incident".

**Weak:**
- Ruled-out hypotheses aren't documented.
- The impressive graph is on the marketing site, not in the documented investigation page.

**Media:**
- [workers-incident-arrival.mp4](https://mintcdn.com/traversal-ff380fca/mf0u61Gl90W-p1_q/images/workers/workers-incident-arrival.mp4)
- [workers-incident-collaboration.mp4](https://mintcdn.com/traversal-ff380fca/mf0u61Gl90W-p1_q/images/workers/workers-incident-collaboration.mp4)
- [workers-postmortem-slack.mp4](https://mintcdn.com/traversal-ff380fca/mf0u61Gl90W-p1_q/images/workers/workers-postmortem-slack.mp4)
- [dashboard image](https://cdn.prod.website-files.com/69b7d15e970d88f7a10898a6/6a98423bb5f4402c7064a009_traversal-workers-1920_2.avif)

---

### 2.2 Resolve AI

**Screens** (VERIFIED: [product](https://resolve.ai/product/ai-sre), [auto-investigations](https://docs.resolve.ai/auto-investigations), [chats](https://docs.resolve.ai/chats.md))

| Screen | Content |
|---|---|
| Investigations sidebar | An "Alerts" tab listing alerts and whether each was investigated. Titles come from the alert, e.g. "High Alert Reception Latency (p90 > 10 mins over 20 min window)" |
| Background agents | Cards "Daily Pulse" (daily 7:00 AM), "PostgreSQL Watch" (on alert event). Confirmation "Background agent created" with a plain-language trigger, e.g. "Alerts if p99 drift > 25% within 2h" |
| Investigation canvas | Where action proposals appear |
| Chats | Opened from the sidebar, from any investigation, or from Home → Activity. Can be pinned or starred. "/" lists skills; `/rca` starts a deep investigation. Buttons "Deep Investigation", "Continue Investigation" |

**How the root cause is shown** (VERIFIED):
- The answer opens with a bold verdict: "**Yes — drift starts ~2h after the deploy.**"
- Evidence is given inline as numbers (p99 ~142ms → ~387ms).
- Hypotheses are labelled "Likely candidate", and ruled-out signals are stated in prose ("error rate and throughput normal").
- There is no numeric confidence.
- Depth has three modes: Triage, Adaptive, Investigation. In the last, "a team of agents explore multiple working
  theories in parallel" ([modes](https://docs.resolve.ai/alert-investigation-modes.md)).

**Action proposal card** (VERIFIED, [mitigation actions](https://docs.resolve.ai/mitigation-actions.md)):

```
┌ Proposed action ─────────────────────────────────────────────┐
│ Silence alert …                                              │
│ Rationale   …                                                │
│ Risk level  Low        Duration  2h       Revertible  Yes    │
│                                    [ Reject ]  [ Approve ]   │
└──────────────────────────────────────────────────────────────┘
 after approval:  [View in platform] [Revoke]
 status: Pending · Approved · Rejected · Revoked · Failed · Expired
 "The AI model cannot call write APIs."
```

**Slack** (VERIFIED, [Slack app](https://docs.resolve.ai/app-for-slack)):
- `@Resolve` in a channel, or `@Resolve /rca` in an alert thread.
- Channel types: Alert, Change event, General.
- Settings include "Proactively share insights" and "Catch up new participants".
- 👍/👎 reactions are logged for quality review; they don't become memory.

**Trust:** "5x faster MTTR", Coinbase "72% faster investigation time" (vendor claims).

**Copy:**
- Lead with a one-line verdict in bold, then the numbers.
- Triage first, with "Continue Investigation" to go deeper.
- Action cards that state risk and revertability, with a status audit trail.
- Background agents described in plain language.

**Weak:** no confidence, and the investigation page layout isn't public.

**Media:**
- [Slack GIF](https://resolve-prod-strapi-bucket.s3.us-east-2.amazonaws.com/slack_integration_ee0d48e63b.gif)
- [alert investigation GIF](https://resolve-prod-strapi-bucket.s3.us-east-2.amazonaws.com/alert_short_rounded_6fbc9bc950.gif)
- [knowledge graph](https://resolve-prod-strapi-bucket.s3.us-east-2.amazonaws.com/knowledge_graph_checkout_eeaa4c66b0.png)
- [post-mortem](https://resolve-prod-strapi-bucket.s3.us-east-2.amazonaws.com/post_mortem_small_fa4cf30ee7.svg)

---

### 2.3 Causely: the most graph-explicit of the six

**Screens** (VERIFIED: [root causes](https://docs.causely.ai/in-action/root-causes.md), [topology](https://docs.causely.ai/in-action/topology.md))

| Screen | Content |
|---|---|
| Issues list | Filters: **Urgency** (Urgent = red, "currently impacting services and SLOs"; Non-urgent = elevated risk), **State** (Active / Historical / Hidden), scope, service, workload |
| Issue detail | Three tabs (below) |
| Topology catalog | Filters Scope, Severity, Type (service, container, HTTP path, background operation, data store, queue). Per-entity tabs: Summary, Diagnoses, Signals, Service map ("Edges indicate direction and relative traffic"), Infrastructure stack (cluster down to process), Dataflow map (topics, queues, databases), Labels (copy a value to filter) |
| Grafana plugin | Root causes, impacted services and SLO risk inside Grafana dashboards |

The three issue-detail tabs:
- **Summary**: Description, Impact and blast radius (degraded services + a diagram), Remediation, Evidence.
- **Causality graph**: "links observed Signals to the inferred Diagnosis".
- **Timeline**: from first detection to resolution.

Clicking a Diagnosis highlights the Signals it explains, and clicking a Signal highlights the Diagnoses that could
cause it.

Reconstruction of the issue detail:

```
┌ Issue: postgres-primary ─────────────── ( Urgent ) ( Active ) ──────────────────────────┐
│ [ Summary ] [ Causality graph ] [ Timeline ]                                             │
├──────────────────────────────────────────────────────────────────────────────────────────┤
│ Causality graph                                                                          │
│                                                                                          │
│   ┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓        ┌──────────────────────────┐                    │
│   ┃ DIAGNOSIS                   ┃ ─────▶ │ SIGNAL checkout latency  │                    │
│   ┃ postgres-primary            ┃ ─────▶ │ SIGNAL order errors      │                    │
│   ┃ connection pool exhausted   ┃ ─────▶ │ SIGNAL SLO breach: cart  │                    │
│   ┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛        └──────────────────────────┘                    │
│   click Diagnosis → highlight Signals it explains · click Signal → candidate Diagnoses   │
└──────────────────────────────────────────────────────────────────────────────────────────┘
```

Homepage verdict card (marketing, [causely.ai](https://www.causely.ai/)):

```
┌──────────────────────────────────────────────────────────┐
│ ROOT CAUSE: postgres-primary                             │
│ connection pool exhausted (87/100)                       │
│ path: checkout → order → postgres                        │
│ BLAST RADIUS: checkout, payments, cart                   │
│ OWNER: platform-team (#db-oncall)                        │
│ 12s to triage · high confidence                          │
└──────────────────────────────────────────────────────────┘
```

**Slack** (VERIFIED, [Slack workflow](https://docs.causely.ai/workflows/slack.md)):
- A parent message with header, entity, severity and a **View** button.
- Threaded replies in order: 1) Summary, 2) Labels, 3) Evidence and impacted SLOs, 4) Remediation.
- Empty sections are skipped.

**Interaction:** dashboard-first, plus MCP with use cases Incident Triage, Quick Service Health, Post-Deploy
Validation and Post-Incident Reporting.

**Trust:** "100% fault accuracy", "−48% tokens", "−63% time to answer" across "72 experiments" (vendor claims).

**Copy:**
- The two-way Diagnosis ↔ Signals link.
- A compact "path: A → B → C" line.
- Owner and on-call channel on the verdict.
- A Summary / Causality graph / Timeline tab structure.
- Slack threads split by section.

**Weak:**
- Little conversation and no documented memory.
- The docs still have placeholders: "We will add a screenshot".

**Media:**
- [causal graph](https://www.causely.ai/images/onboarding-steps/step-2-graph.webp)
- Root cause and prevention images: `step-3-cause.webp` and `step-4-prevention.webp`, same folder
- [Grafana demo](https://dev.to/causely/causely-feature-demo-unlock-root-cause-analysis-in-grafana-2817)

---

### 2.4 Anyshift (agent "Annie")

**Screens** (VERIFIED: [anyshift.io](https://www.anyshift.io/), [docs](https://docs.anyshift.io/pages/overview))
- A web dashboard for "Visual exploration and configuration management".
- An "Ask your graph" panel with sample prompts: "What's my single point of failure?", "What has drifted?".
- Six agent cards, e.g. "Incident investigator — Find likely causes. Show the evidence.", Alert triage, Deployment
  checker, Monitor review, Kubernetes health check, CI failure investigator.
- A 3D graph demo, "Code, traffic and monitoring relationships in production" (Git revision → Deployment → Pods;
  Cloudflare → K8s Service; Datadog monitor observing the Service), with "hover to explore, drag to orbit".
- A public **playground**: https://playground.anyshift.io

**RCA report** (VERIFIED, [RCA docs](https://docs.anyshift.io/pages/product/root_cause_analysis)):

```
┌ Root Cause Analysis ─────────────────────────────── ~30–90 s ┐
│ Executive Summary                                            │
│ Timeline of Events                                           │
│   1:45 PM  Security group sg-prod-db was modified            │
│ Root Cause Details    • evidence • evidence                  │
│ Affected Resources    …                                      │
│ Remediation Steps                                            │
│   Immediate   …                                              │
│   Short-term  …                                              │
│   Long-term   …                                              │
│ [ Propose Fix ]  → opens a PR with the diff                  │
└──────────────────────────────────────────────────────────────┘
```

**Graph:**
- A versioned resource graph covering cloud, IaC, K8s, code and monitoring, with 7 days of history.
- Every IAM change, Helm rollout, Terraform apply and commit is a node, and "what changed?" is answered as a graph
  diff, conversationally ([time travel](https://docs.anyshift.io/pages/product/time_travel)).
- No visual diff UI is documented.

**Slack** (VERIFIED, [Slack docs](https://docs.anyshift.io/pages/product/integration/slack)):
- Commands: `@Annie`, `/register_annie_on_call`, "@Annie listen" (adopts an alert bot).
- Live progress appears in the thread.
- "Relevant" / "Ignore" votes are synced between Slack and the web.
- "View Full Report" link.
- Weekly report DMs, with "Stop weekly report DMs" and "Resume".

**Memory** (VERIFIED, [memory](https://docs.anyshift.io/pages/overview/memory_agents)):
- Cards for Infrastructure Patterns, Operational Baselines, Tool Shortcuts and Business Context.
- Three parallel agents (Observability, Infrastructure, Code).
- Annie "reflects" after each investigation.

**Copy:**
- Remediation split by time horizon.
- "Propose Fix" on each hypothesis.
- Changes stored as graph nodes, with "what changed" answered as a diff.
- A public playground.
- Feedback synced across surfaces.

**Weak:** no confidence, no citation format, no graph inside the RCA. Video: https://www.youtube.com/embed/ppgrX1fligI

---

### 2.5 Cleric

**Screens** (VERIFIED: [product](https://cleric.ai/product.md), [how investigations work](https://docs.cleric.ai/usage/how-investigations-work.md), [memories](https://docs.cleric.ai/learning/memories.md))
- Slack plus a web app where "changes, issues, and chats each have their own view".
- **Issue page:** status, grouped alerts, investigation history, evidence, suggested fixes, an activity log (tool runs
  and intermediate findings), and the full conversation.
- **Knowledge > Memories:** browse, search and filter across ten categories (e.g. "Alerts & Runbooks",
  "Observability", "Agent Behavior"), with "Add memory" and a trash icon.

**How uncertainty is shown (the strongest of the six):**
- Reports contain "evidence, reasoning, uncertainty, and recommended next steps".
- An inconclusive report lists **Partial findings**, **Access limitations** (data Cleric couldn't reach) and
  **Remaining uncertainty**.
- An escalation states the service, why a human is needed, the decision required, and evidence **"including causes
  that were ruled out"**.
- "Every line of the fix links to the production data behind it, including past investigations where the same fix worked."
- The launch release mentions confidence scores ([BusinessWire](https://businesswire.com/news/home/20251209625361/en/Cleric-Launches-the-First-Self-Learning-AI-SRE)).
- Cleric's calibration blog found self-assessed confidence was poorly calibrated (investigations rated 80% were no
  more likely to be correct than ones rated 60%), while critique grounded in evidence tracked success.

Reconstruction of an inconclusive report and an escalation:

```
┌ Investigation: payments-api 5xx ─────────────── ( Inconclusive ) ┐
│ Partial findings                                                 │
│   • 5xx began 14:02, after deploy v3.1                           │
│ Access limitations                                               │
│   • No access to RDS performance insights                        │
│ Remaining uncertainty                                            │
│   • DB vs connection-pool cause not separated                    │
│ Ruled out                                                        │
│   ✕ upstream gateway (latency normal)                            │
│   ✕ node pressure (CPU/mem normal)                               │
│ Decision needed: roll back v3.1?                                 │
└──────────────────────────────────────────────────────────────────┘
```

**Interaction** (VERIFIED, [verifying fixes](https://cleric.ai/blog/verifying-fixes)):
- Slack-first and read-only by default: "Review the fix PR and its production evidence in Cleric before approving."
- It watches announced deploys and flags regressions. A verifier gives "resolved" / "open" / "undetermined".

**Memory:**
- Slack proposals with **Remember** / **Reject**, confirmed by "👍 Memory saved."
- Typed commands "@Cleric Remember …" and "@Cleric Forget …".
- Stale memories are pruned.

**Trust** (vendor, as of Oct 2026):
- "58% of alerts closed without an engineer replying".
- 4.08/5 engineer rating.
- 51% of resolved incidents fixed with Cleric's suggested remediation.

**Copy:**
- **Access limitations** shown honestly.
- Ruled-out causes in escalations.
- Fix lines that cite precedent.
- Remember / Reject memory.
- Confidence grounded in evidence, not the model's self-rating.

**Weak:** no graph or topology, and little public UI. The live demo at https://demo.cleric.ai rendered empty.

---

### 2.6 NeuBird (Hawkeye)

**Screens** (VERIFIED as homepage mock-ups, [neubird.ai](https://neubird.ai/)):
- **"NB / OPS CENTER / LIVE"**, which feeds Slack, a leadership brief and a Cursor MCP session.
- **Console:** triaged incidents, open alerts, average time to root cause, a service risk map, signals, an "Ask agent" prompt.
- **Cursor MCP session:** an "Ask" panel where `search_memory` returns past investigation inv-2291 with cited metrics,
  the deploy and a staged PR.
- **Leadership brief:** investigations, engineer time returned, value returned, model spend by team.
- **Audit trail:** timestamped approvals with "Policy · Act" or "Policy · Recommend".

**Slack incident card and approval gate** (VERIFIED, [Slack solution](https://neubird.ai/solutions/slack)):

```
┌ Incident summary ─────────────────────────────────────────────────┐
│ Root cause          …                                             │
│ Affected services   payments-api                                  │
│ Contributing change …                                             │
│ Impact              …                                             │
│ Recommended fix     rollback                                      │
│ Found in 4m 12s · 15+ sources queried in parallel                 │
│                       [ View evidence ]   [ Approve rollback ]    │
└───────────────────────────────────────────────────────────────────┘
┌ Auditable approval gate ──────────────────────────────────────────┐
│ Policy  Recommend · human approval required                       │
│ Scope   payments-api · prod-east                                  │
│ Awaiting the on-call engineer           [ Reject ]  [ Approve ]   │
└───────────────────────────────────────────────────────────────────┘
 → "Approved by Andrew Lee · 10:37 AM · recorded in the audit trail"
 → "Rollback complete"   p99 4.2s → 310ms
```

**Live progress:**
- Steps "+ sources" → "Correlating evidence" → "Root cause found in 4m 12s".
- Source chips: Metrics, Logs, Traces, Deploys, K8s events, Git, Postgres, PagerDuty, Change history.
- A "Deeper investigation" card has **TRACE / LOGS / DIFF** evidence rows.

**Proactive signals:**
- Header "No alert has fired yet · Risk signals for payments · 3 flagged".
- Cards are tagged High / Medium / Low, with "Pause rollout", "Open investigation" and "Dismiss".

**Post-incident:** an MTTR and time-to-root-cause header, a timeline, and follow-ups linked to Jira tickets with owners.

**Trust:** "RCA accuracy: 94%", "under 5 minutes" (vendor claims).

**Copy:**
- A policy level on every action.
- Named, timestamped approvals in an audit trail.
- Before/after metric shown after the fix.
- Source chips while it works.
- A leadership brief that includes model spend.

**Weak:**
- The UI evidence is mostly marketing.
- Per Better Stack (a competitor, so biased), it has no on-call routing or status pages.

**Screens:** [desktop](https://neubird.ai/images/product/neubird-desktop.png), [Slack](https://neubird.ai/images/product/neubird-slack.png)

---

## 3. Incumbents

### 3.1 Datadog: Bits AI SRE, Watchdog RCA, Watchdog Insights, Service Map

**Screens**

| Screen | Content | Source |
|---|---|---|
| Investigations list | `app.datadoghq.com/bits-ai/investigations`. "Reports" tab: counts over time by monitor, user, service and team; "mean time to conclusion" | VERIFIED [D1][D2] |
| Investigation: **Investigation Steps** (live) | Records each step, how evidence was weighed, and the decisions made | VERIFIED [D1] |
| Investigation: **Hypothesis Tree** (done) | Draws the investigative path as a tree. A validated hypothesis spawns sub-hypotheses; branches without evidence are pruned | VERIFIED [D1][D6] |
| Chat beside the tree | Answers with "rich widgets and citations" pointing to the exact investigation step | VERIFIED [D2], layout INFERRED [D3] |
| **Agent Trace** | Every step: tools called, data queried, intermediate analysis, to "inspect how hypotheses were formed and eliminated" | VERIFIED [D3] |
| Watchdog RCA panel | Three blocks: **Root Cause**, **Critical Failure**, **Impact** (with a "Views impacted" pop-up) | VERIFIED [D4] |
| Watchdog Insights carousel | Top of the Log, APM, RUM, DB and Synthetics explorers; high priority on the left; "View all" opens a side panel; cards have "Filter on Insight" and "Copy Link" | VERIFIED [D5] |
| Service Map | See the graph notes below | VERIFIED [D7] |

**Ways to start an investigation:**
- Buttons: "Investigate with Bits Investigation" (monitor page, top right), "Investigate Recent Alerts",
  "Auto-Investigate" / "Auto-Investigate All", "New Investigation" (a free prompt, defaulting to the past 4 hours).
- Slack: `@Datadog Investigate this alert`, which uses the whole thread as context.

**Findings:**
- Each hypothesis is **validated / invalidated / inconclusive**.
- The investigation ends either with an "evidence-backed conclusion" or as **inconclusive** "when the data can't
  support a defensible answer".
- Watchdog wording rules:
  - Root-cause types are fixed: version change, traffic increase, AWS instance failure, disk full.
  - Critical Failure is always a latency or error-rate increase. The degraded performance itself is never called
    the root cause.

Reconstruction of the hypothesis tree with chat:

```
┌ Bits Investigation · checkout latency ─────────── [Investigation Steps | Hypothesis Tree] ┐
│                                                         │ CHAT                            │
│  ● Alert: checkout p99 high                             │ > Why do you think there's      │
│  ├── ✓ validated  DB query slowness                     │   database query slowness?      │
│  │   ├── ✓ validated  index dropped in deploy v2.4      │ Bits: The deploy at 14:02 …     │
│  │   └── ✕ invalidated  connection pool saturation      │   [widget: query latency] [→ step 3]
│  ├── ✕ invalidated  upstream gateway errors             │                                 │
│  └── ? inconclusive  noisy neighbour on host            │ [Send to Slack] [Create incident]
│                                                         │ [Create case] [Create Jira]     │
│  [Agent Trace]  tools called · data queried · analysis  │                                 │
└─────────────────────────────────────────────────────────┴─────────────────────────────────┘
```

**Graph (Service Map):**
- Node borders turn red or yellow from "Service Health", which combines Watchdog anomalies, paging monitors and incidents.
- Edges are animated, directional request lines; hovering a node highlights its lines.
- **Inspect view:** upstream services on the left, downstream on the right, because services "on the right are more
  likely root causes". You click through hop by hop, and nodes outside the filter are collapsed.
- Filters: service type, last deploy time, monitor status, incident status, `env`, "Second Primary Tag", group by Team or Application.

```
 Inspect: checkout
 UPSTREAM (callers)          SELECTED            DOWNSTREAM (more likely root causes →)
 ┌───────────┐            ┏━━━━━━━━━━┓           ┌───────────┐
 │ frontend  │ ─────────▶ ┃ checkout ┃ ────────▶ │ payment   │ (red border)
 └───────────┘            ┗━━━━━━━━━━┛ ────────▶ │ postgres  │
                                                 └───────────┘
```

**Interaction:**
- One-click triage from chat: send to Slack or Teams, create an incident, create a case, create a Jira ticket, all pre-filled.
- Users can "correct Bits when it makes a mistake or reinforce its conclusions".
- Team knowledge lives in a `bits.md` file (Preview).
- Bits can generate a notebook summary.

**Copy:**
- The live step log becomes a tree when the investigation finishes.
- Every hypothesis node carries a three-state badge.
- The inspect view rule: "right = more likely root cause".
- Strict Root Cause → Critical Failure → Impact wording.
- An explicit inconclusive ending.

**Weak:**
- Findings are spread across the carousel, RCA panel, Bits and the map. There is no single incident cockpit (INFERRED).
- No numeric confidence (INFERRED).

**Screens:**
- [Bits overview](https://docs.dd-static.net/images/bits_ai/overview_2.32422fb7d170d351702b1d017117958e.png)
- [hypotheses](https://docs.dd-static.net/images/bits_ai/bits_ai_sre_investigation_hypotheses.388a74db896dcfc962a133b702e62bfa.png)
- [tree + chat](https://web-assets.dd-static.net/42588/1776292034-bits-ai-sre-deeper-reasoning-bits-reasoning.png)
- [Agent Trace](https://web-assets.dd-static.net/42588/1776292093-bits-ai-sre-deeper-reasoning-agent-trace-view.png)
- [triage actions](https://web-assets.dd-static.net/42588/1776292098-bits-ai-sre-deeper-reasoning-bits-triage-actions.png)
- [Slack](https://web-assets.dd-static.net/42588/1776292150-bits-ai-sre-slack-v2.png)
- [Watchdog RCA](https://docs.dd-static.net/images/watchdog/rca/root_cause_cropped.9f55d64e9abbe037aacc3703ffbc2401.png)
- [Service Map](https://docs.dd-static.net/images/tracing/visualization/services_map/service_map_overview_3.3b80f55bde2fa4baefdb2bdbdb92d7fb.png)

---

### 3.2 PagerDuty: SRE Agent ("Paige"), AIOps

**Screens** (VERIFIED: [SRE Agent](https://support.pagerduty.com/docs/sre-agent), [Probable Origin](https://support.pagerduty.com/main/docs/probable-origin))
- **Incident details page, "Paige" tab on the right:** an incident summary and suggested next steps, then chat with
  nudge buttons and file attachments.
- **Operations Console:** an optional Paige column; clicking an incident Title opens the Paige tab.
- **Nudges:** "Analyze Past Incidents", "Analyze Related Incidents", "Generate a Playbook", "Check Change Events", "Search Logs".
- **AIOps cards on the incident page:**
  - **Probable Origin:** up to 3 candidate incidents, each with a % likelihood, priority, service link, status and timestamp.
  - **Related Incidents:** up to 20 on other services.
  - **Past Incidents:** same service.
  - **Recent Changes:** 3 change events on web, 2 on mobile, each with the reason it was correlated (time, related
    service, or "intelligence").

Reconstruction of the incident page with the Paige tab:

```
┌ Incident #4821 · checkout errors ────────────────────────────┬ Paige ─────────────────────────┐
│ PROBABLE ORIGIN                                              │ Summary                        │
│  #4819 db-primary        72%  P1  Triggered 14:02            │ Detected 15% increase in       │
│  #4817 auth-service      18%  P2  Ack'd 13:58                │ checkout errors. Correlated to │
│ RECENT CHANGES                                               │ recent DB migration. Found 3   │
│  DB migration 0042  · correlated by: time                    │ similar incidents in history.  │
│  deploy cart v8     · correlated by: related service         │ Next steps                     │
│ [Related Incidents (20)] [Past Incidents]                    │  ▶ Run Database Optimization   │
│                                                              │    Workflow                    │
│                                                              │ [Analyze Past Incidents]       │
│                                                              │ [Check Change Events] [Search  │
│                                                              │  Logs] [Generate a Playbook]   │
│                                                              │ 👍 👎 Rate AI Response         │
└──────────────────────────────────────────────────────────────┴────────────────────────────────┘
```

**Interaction:**
- Slack: the "Paige Triage" button or `@pagerduty`, and "Upload Runbook" / "Update Runbook".
- The agent posts its analysis of new notes automatically; this can be turned off in AI Settings.
- It can be added to schedules and escalation policies as a "virtual responder", before anyone acknowledges.
- Fixes run only "With human approval" ([blog](https://www.pagerduty.com/blog/ai/we-built-an-sre-agent-with-memory-and-its-transforming-incident-response/)).
- Each chat request or nudge costs 4 AI Actions credits.

**Memory:**
- Per-service artifacts: "SRE Incident Playbook", "Customer Service Runbook", "Incident Summarization", "Service Profile".
- Saved only after resolve; "Update Memory" adds more.
- A Memory API can view, update or redact entries.

**Copy:**
- Nudge chips under the chat.
- Up to 3 origin candidates with a % likelihood each.
- "Why correlated" on each change.
- The agent as a first responder on the schedule.
- Editable per-service memory.

**Weak:**
- The AI reads as a side-tab add-on.
- Nudges cost credits.
- No graph or hypothesis view (INFERRED).

**Screens:**
- [Ops Console](https://files.readme.io/40c7e374fd30af34a3df5272f542000368f5015a0e387beddb41dbfa1298dd48-SRE_Agent_in_Ops_Console.png)
- [Slack](https://files.readme.io/13f86634c08b509949154791694be0cd9b6e15724b6cba9c55b4cacf74c211d0-SRE_Agent.png)
- [Probable Origin](https://files.readme.io/5f99f0a05cb8d2da64b0ced405ca18c9a2a7ff04cafc39e3719678fc6728a65e-probable-origin-overview.webp)
- [interactive tour](https://pagerduty.navattic.com/int-pagerduty-advance?q=cmeuf7co0004004jxaj7z511n&s=0)

---

### 3.3 incident.io: AI SRE "Investigations"

**Surfaces** (VERIFIED: [how investigations work](https://docs.incident.io/investigations/how-investigations-work), [walkthrough](https://incident.io/blog/how-it-feels-to-run-an-incident-with-ai-sre))
- **Slack channel (primary):** one summary message that keeps editing itself, with progress threaded under it, and a
  separate heads-up when it finds something important.
- **Incident dashboard:** a plain-language summary, the findings still standing with confidence and evidence, and links
  to the Slack message, PR, dashboard or log line.
- **macOS app:** a pinned incident lives in the notch as a live view.
- **Claude Code:** `/incident INC-19672` pulls the investigation into the terminal.

**Findings model (the most rigorous of the incumbents):**
- A **finding** is a claim about what happened.
- **Evidence** supports or contradicts it, and each finding has a **confidence**.
- A finding can be **"discounted"**. It stays in the audit trail, and the final report shows only findings still standing.
- A second agent challenges conclusions before they are shared.
- It checks third-party status (AWS, GitHub, Stripe) automatically.
- Phases: fast diagnosis → gather context in parallel → analyse and refine. It re-assesses on new activity until resolved.

Confidence ladder (VERIFIED, quoted):

```
 ▁ Speculation
 ▂ Pattern match
 ▃ Supported by context
 ▅ Validated by system state
 █ Validated, alternatives ruled out
 + states: "contradicted", "alternative is just as likely"

┌ Finding ───────────────────────────────── [▅ Validated by system state] ┐
│ Payment errors started after flag paymentFailure was enabled            │
│ Evidence  + flag change 14:03 (supports)  + error spike 14:04 (supports)│
│           − cart latency normal (contradicts alt.)                      │
│ Discounted (audit): "DB connection pool exhaustion" — contradicted      │
└─────────────────────────────────────────────────────────────────────────┘
```

**Trust** ([trust and safety](https://docs.incident.io/investigations/trust-and-safety)):
- High confidence only with "verifiable evidence against sources it trusts". Otherwise it "states what it couldn't
  confirm" and lists the gaps.
- "The only change Investigations can make to your systems is a pull request you review and merge yourself."
- Investigations are graded against the actual causes, and changes are backtested before shipping.

**Timeline:**
- Pin a Slack message with 📌 and it lands on the timeline at its original time.
- Timestamps can be edited, and activity can be added with "+".
- Items are "promoted" or custom.

**Post-mortem** ([AI post-mortems](https://docs.incident.io/post-incident/postmortem-ai), [launch](https://incident.io/blog/post-mortems-launch)):
- A one-click AI draft, with an AI toggle and custom instructions per section.
- A **"Review"** button leaves inline suggestions only the author sees.
- Select text to redraft it. A floating chat creates follow-ups, and clicking a reference scrolls to that place.
- `@` mentions pull live data and `/` inserts blocks.
- Scribe transcribes debriefs. Editing is multiplayer.

**Copy:**
- The evidence ladder instead of a %.
- Discounted findings kept in the audit trail.
- One Slack message that updates itself.
- Fixes delivered only as PRs.
- Author-only review comments.

**Weak:** no topology or blast-radius visual, and few screenshots with captions, so the web layout is unverified.

---

### 3.4 Rootly: AI SRE

**Screens** (VERIFIED as product-page mock-ups: [AI SRE](https://rootly.com/ai-sre), [deploy correlation](https://rootly.com/blog/telemetry-deploy-correlation-ai-sre))
- **Slack:**
  - The message progresses "Investigating…" → "What I've found so far" → "See details and follow along on Rootly AI SRE".
  - Buttons: Update, Action Items, Assign Roles, Escalate.
- **Web AI SRE view:**
  - A "Likely root cause" summary with bullets citing specific values.
  - A "Root cause analysis" panel with a confidence label ("High"), supporting points, and code lines with file and line numbers.
  - "Suggestions".
  - A "Chain of thought" panel with "View graph in Datadog ↗".
- **Evidence panels:** stack trace, recent deploys (author and time), user impact (first and last seen, occurrences,
  regions), flag changes, a service health chart.
- **Actions per suggestion:** "Propose change", "Open staging", "Escalate incident", with inline status ("Draft PR #848 opened").
- Similar past incidents, with dates.

Change-timing strip (VERIFIED):

```
 T−12m            T−5m              T−0m
 ──●────────────────●─────────────────●──────▶
   PR merged        flag enabled      500-error spike
 tighter alignment → higher confidence · rollback recommended where applicable
```

**Retrospectives** ([AI in retrospectives](https://docs.rootly.com/ai/ai-in-retrospectives/overview)):
- 10 preset AI blocks, e.g. What Happened, Impact, Contributing Factors, Learnings, Follow-Up Actions, Curated Timeline.
- Each block can show its **sources and prompt**, be regenerated (with a warning if edited by hand), be converted to
  text, be commented on, or be rated.
- A block can be previewed against a past incident before rollout.
- Drafts are blameless: they refer to roles and "don't invent facts, times, or owners".

**Comms:** status updates drafted per audience (technical, leadership, customers), moving Draft → Approved → Send.

**Copy:**
- The T-minus change strip.
- Action buttons with inline PR status.
- Evidence that goes down to the code line.
- A sources-and-prompt toggle on AI content.
- Audience-specific comms.

**Weak:**
- Evidence mostly from marketing.
- The confidence meaning isn't documented.
- incident.io argues its accuracy claims lack precision/recall evidence ([biased source](https://incident.io/blog/rootly-ai-accuracy-vs-competitors)).

---

## 4. Open source and observability platforms

### 4.1 HolmesGPT (Robusta, CNCF Sandbox)

**Surfaces:**
- A CLI: `holmes ask` opens interactive mode with a `>` prompt.
- Third-party front ends: Slack and Teams bots, and a Web UI.
- A K9s plugin, an HTTP server, and an operator mode that "messages you in Slack with the fix" and can open PRs ([docs](https://holmesgpt.dev/latest/)).
- In Robusta: an **"Ask Holmes"** Slack button and a **"Root Cause"** tab on alerts ([Robusta](https://docs.robusta.dev/master/configuration/ai-analysis.html)).

**Tool-call receipts, its best idea** (VERIFIED, [interactive mode](https://holmesgpt.dev/latest/walkthrough/interactive-mode/)):

```
> why is payment crashing?
Running tool #1 kubectl_find_resource: kubectl get -A --show-labels -o wide deployment | grep payment
Finished #1 in 1.32s, output length: 894 characters - /show 1 to view contents
Running tool #2 …
Finished #2 in 0.84s, output length: 2,130 characters - /show 2 to view contents

1. **Root cause** … (numbered findings, bold labels, fenced fix)

> /show 1          ← raw output of tool call 1
> /run kubectl …   → "Share output with AI? (Y/n)"  → "Add a comment or question (optional)"
  also: /clear  /context  /shell
```

**Trust:** read-only and RBAC-aware. Tools run under a `ulimit -v` memory cap, and output gets an `[OOM]` prefix when
the cap is hit ([tool safety](https://holmesgpt.dev/latest/data-sources/tool-execution-safety/)).

**Copy:** numbered receipts linked to their raw evidence, and a consent step before user data reaches the model.

**Weak:** no graph, timeline or memory.

---

### 4.2 Coroot

**Screens** (VERIFIED, [GitHub](https://github.com/coroot/coroot), [AI docs](https://docs.coroot.com/ai/overview)):
- **Service Map** built with eBPF ("covers 100% of your system", zero instrumentation) ([screenshot](https://user-images.githubusercontent.com/194465/235189673-833066d1-b18f-4c7a-8b81-81b37f966daf.png)).
- Application Health Summary, built to stay readable with "hundreds" of services.
- Tracing, log patterns, one-click profiling against a baseline, deployment tracking (each release vs the previous one), SLOs, cost.

**RCA flow:**
1. You select an anomaly on the SLI chart.
2. A deterministic ML pass walks the dependency graph.
3. **"Explain with AI"** sends only those findings to the model, never raw telemetry.

Coroot's own words: "No tools, no agent loop", about 9.8k tokens of findings ([blog](https://coroot.com/blog/hard-part-of-ai-root-cause-analysis-is-no-longer-the-model/)).

Reconstruction of the RCA report:

```
┌ RCA: frontend latency ───────────────────────────────────────────┐
│ Anomaly summary                                                  │
│ Issue propagation paths                                          │
│   frontend → ad → otel-collector                                 │
│   (kafka latency: unrelated, flagged)                            │
│ Key findings / Root Cause Analysis   • evidence • evidence       │
│ Remediation                                                      │
│ Relevant charts   [▁▃▇▅]  [▂▂▆▇]                                 │
└──────────────────────────────────────────────────────────────────┘
```

**Benchmark page:** a score (e.g. 2/3) with sub-checks (problematic service found, fix suggested, a detail missed),
plus the model, tokens and cost (about $0.07) ([scenario](https://coroot.com/ai-benchmark/scenarios/productCatalogFailure)).

**Copy:**
- Deterministic engine first, LLM second. **This is Epicenter's own design (ADR 0002).**
- Propagation as an arrow chain.
- Unrelated signals shown and labelled as such.
- The RCA's completeness scored.
- Token cost shown per investigation.

**Weak:** AI RCA is Enterprise-only, and Community Edition gets 10 free investigations a month.

---

### 4.3 K8sGPT

**Surfaces** (VERIFIED, [GitHub](https://github.com/k8sgpt-ai/k8sgpt)):
- A one-shot CLI: `k8sgpt analyze --explain`, with `--filter`, `--namespace`, `--output=json`, `--anonymize`,
  `--with-doc`, and `-s` for per-analyzer timing.
- `serve --mcp` exposes 12 tools.

**Findings:** one sentence per resource from deterministic analyzers, then an AI explanation.

**Copy:** "analyzer finds, LLM explains", plus an anonymize toggle.

**Weak:** a flat list with no causal links. [Demo GIF](https://github.com/k8sgpt-ai/k8sgpt/blob/main/images/demo4.gif)

---

### 4.4 Grafana: Assistant Investigations, Asserts RCA Workbench, Sift, Knowledge Graph

#### Assistant Investigations (public preview since Oct 2025)

VERIFIED: [docs](https://grafana.com/docs/grafana-cloud/machine-learning/assistant/investigations), [launch](https://grafana.com/whats-new/2025-10-08-introducing-assistant-investigations--now-in-public-preview/)

**This is the best current pattern for hypotheses.**
- Multiple agents: a lead investigator plans, specialists (Prometheus, Loki, Tempo, Pyroscope) gather evidence, and
  a reporter writes it up.

```
┌ Investigation: checkout errors ───────────────── [● running]  [ Stop ] ┐
│ [ Report ] [ Hypotheses ] [ Sources ]                                  │
├────────────────────────────────────────────────────────────────────────┤
│ Hypotheses                                                             │
│ ▾ ( supported )  payment flag enabled                    [ Disprove ]  │
│     Evidence  error rate ↑ after flag  [Source 1] [Source 3]           │
│     Timeline  14:03 flag · 14:04 errors                                │
│ ▸ ( disproved )  DB saturation                           [ Reopen ]    │
│ ▸ ( open )       cart latency                            [ Disprove ]  │
│                                                                        │
│ (after report)  Was this the cause?  [ Yes ] [ No ]   [ Change ]       │
├────────────────────────────────────────────────────────────────────────┤
│ Steer…  Enter = queue (≤5)  ·  Ctrl/Cmd+Enter = steer now  ·  /ask     │
└────────────────────────────────────────────────────────────────────────┘
 Source N → opens panel with its query, time range, data source
 Report → export Markdown / HTML / PDF · live sharing · snapshots · 👍👎
```

- Select text and click "Ask" to ask about that passage.
- "Stop" produces a summary marked incomplete.
- New evidence reopens a finished investigation.

#### Asserts RCA Workbench

VERIFIED: [docs](https://grafana.com/docs/grafana-cloud/monitor-applications/asserts/manage-infra-apps/workbench), [blog](https://grafana.com/blog/2024/09/24/contextual-root-cause-analysis-grafana-cloud/)

- Views: **Timeline / Summary / Graph / Mind map**.
- Entity × time swimlanes, nested category → context type → request context → insight name. Example from the docs:
  `outbound - flagd` / `ErrorRatioBreach`.

```
 RCA Workbench   [Timeline] Summary Graph Mind map        time ◀ 13:30 ─────── 14:30 ▶   ⚙
 ─────────────────────────────────────────────────────────────────────────────────────────
 ▾ flagd           ║ amend ║                                     ← blue = change (deploy, flag)
 ▾ postgres                  ████████████                        ← red = error / failure
     saturation               ▆▆▆▆▆▆
 ▾ checkout                       ████████████████
     error › outbound - flagd › ErrorRatioBreach
 ─────────────────────────────────────────────────────────────────────────────────────────
 entity: [Causes] [KPIs] [Show Connected Entities]   point: Logs / Traces / Profiles
 insight: Open chart · View rules · View insight details · Update threshold · Notify · Suppress
 ⚙ Hide Insights older than 48h · Hide Insights present more than 90% · Show Entity with Insights
 drag on the timeline to zoom · "Open graph preview" · "Analyze RCA Workbench" → Assistant
```

The worked example: a flag flips (blue) → Postgres connection surge → crash-loops. The graph preview shows Postgres is
the most downstream node, so the investigation starts there.

Screens:
- [example](https://a-us.storyblok.com/f/1022730/6393218ec7/rca-workbench-example-asserts-grafana-cloud.png)
- [sequence](https://a-us.storyblok.com/f/1022730/092c035d83/rca-workbench-sequence-assertions-grafana-cloud.png)
- [spatial](https://a-us.storyblok.com/f/1022730/465f015204/rca-workbench-spatial-dimension-grafana-cloud.png)
- [feature flag](https://a-us.storyblok.com/f/1022730/a1aee0f683/rca-workbench-feature-flag-grafana-cloud.png)

#### Sift

VERIFIED: [docs](https://grafana.com/docs/grafana-cloud/alerting-and-irm/machine-learning/sift/sift/)

- Started from "Run investigation" in Explore or a panel menu, from the command palette, or from "Start Sift
  investigation" in the incident sidebar.
- Checks sit in a left column grouped **Application / Infrastructure / Other**, e.g. Error Pattern Logs and Kube Crashes.
  Each has its own UI.
- Labels are taken from PromQL and can be edited. Noisy labels are dropped.
- Interesting results become suggestions you can add to the incident timeline or dismiss.

**Copy:** a visible, categorised check list, so the user sees what was examined, including checks that found nothing.

#### Knowledge Graph

An entity catalog with red indicators on entities that have insights, and entity pages with RED or infrastructure
metrics plus pre-filtered logs, traces and profiles ([docs](https://grafana.com/docs/grafana-cloud/monitor-applications/asserts/)).

---

### 4.5 Dynatrace: Problems, Visual Resolution Path, Smartscape

**Problem feed** (VERIFIED, [Problems app](https://docs.dynatrace.com/docs/dynatrace-intelligence/problems-app)):
- A problem chart sits above the table; select a peak to drill into it.
- Open problems are pinned to the top.
- Left filters: Status, Category, Impact (Frontend / Service / Infrastructure / Environment), Severity (Critical,
  Major, Minor, Warning, Informational).
- An AND/OR filter bar (`Duration>1h`), saved team **Segments**, bulk close (up to 50), CSV export.
- A count in the Dock, or a red dot when it's collapsed.

**Problem details:**
- The root-cause entity carries a **red mark**.
- Up to three candidates, from a community answer, so INFERRED.

Reconstruction:

```
┌ Problem P-2310 · Failure rate increase ───────────────────────────── [ Close… (comment required) ] ┐
│ Overview │ Affected entities (12) │ Logs (340) │ Deployment view │ Troubleshooting │ Event properties  │
├───────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ ⠿ Impact         Frontends 2 · Services 5 · Infrastructure 1 · Synthetic 0 · Environment 0          │
│ ⠿ Root cause     ● payment-svc (red mark)   host · process · k8s workload                           │
│ ⠿ Visual resolution path                                                                [Maximize]   │
│     ┌───────────── PROBLEM (group, coloured by state) ─────────────┐                                 │
│     │  (frontend) ──▶ (checkout) ──▶ ((payment-svc ●))             │   (cart)  (ad)   ← gray: related, │
│     └──────────────────────────────────────────────────────────────┘                    not impacted  │
│     timeline:  frontend   ──────█████                                                               │
│                checkout   ────██████                                                                │
│                payment    ██████████     (one lane per entity when expanded)                        │
│ ⠿ Automation and remediation   workflow "restart" · state: running                                  │
└───────────────────────────────────────────────────────────────────────────────────────────────────────┘
 ⠿ = drag to reorder sections (saved per user) · no VRP is drawn if no root cause was found
```

**Other tabs:**
- **Deployment view:** a UML-like diagram up to five levels, with the root cause expanded and a red badge.
- **Troubleshooting:** generates a notebook with "Initial Response & Detection / Troubleshooting / Remediation steps".
- **Closing a problem requires a comment**, which is saved as an annotation.

**Smartscape problem graph** ([problem graph](https://docs.dynatrace.com/docs/analyze-explore-automate/smartscape/smartscape-views/problem-graph)):
- Shows only active problems linked to affected and related nodes, for judging blast radius.
- "View topology" offers **Vertical** (the full hierarchy) and **Horizontal** (direct upstream and downstream) views.

**Copy:**
- The problem drawn as a group on the graph.
- Gray context nodes.
- One timeline lane per entity.
- Reorderable sections.
- A mandatory close comment, which feeds learning.

**Weak:** dense, and nothing graphical is drawn when there's no root cause.

**Screens:**
- [details](https://dt-cdn.net/images/problems-details-view-page-1920-3d5f2bb781.png)
- [overview](https://dt-cdn.net/images/problems-screenshot-with-overview-1920-6c68de3f34.png)
- [deployment view](https://dt-cdn.net/images/problem-deployment-view-1920-e646972d40.png)
- [feed](https://dt-cdn.net/images/problem-feed-latest-3840-3cde469692.png)
- [problem graph](https://dt-cdn.net/images/problem-graph-smartscape-1920-1f8a7b5198.png)

---

### 4.6 Honeycomb: BubbleUp and Canvas

**BubbleUp** (VERIFIED, [docs](https://docs.honeycomb.io/investigate/analyze/identify-outliers/)):

```
 heatmap: drag a box around the slow requests (selection = yellow, baseline = blue)
 ┌ BubbleUp ───────────────────────────── [BubbleUp Filter 🔍] ┐
 │ Dimensions                                                  │
 │  app.version   v2.4 ████████████ yellow                     │
 │                v2.3 ██ yellow   █████████ blue               │
 │  region        us-e █████ yellow ████ blue   (donuts: fill%) │
 │ Measures                                                    │
 │  db.duration   ▁▂▅█ yellow   ▁▂▂▁ blue                       │
 └─────────────────────────────────────────────────────────────┘
 click a bar → Group by Field · Show only where… · > / <
 with Honeycomb Intelligence: plain-language summary + ranked fields by severity
```

- Started by brushing a heatmap, clicking a line, or "BubbleUp: Compare `<value>` to all other events".
- The URL is a shareable permalink.

**Canvas** (VERIFIED, [blog](https://www.honeycomb.io/blog/meet-canvas-your-ai-guided-workspace-within-honeycomb), [alert investigation](https://docs.honeycomb.io/investigate/canvas/alert-investigation)):
- An AI assistant plus a notebook where you "follow along with live visualizations".
- An **"Investigate"** link in Slack, PagerDuty or email alerts opens a session that's already running, with the
  clicking user's permissions.

**Copy:**
- Selection vs baseline in two colours.
- The investigation is already running by the time the user clicks.

**Weak:** no topology.

---

### 4.7 New Relic

**Issue page** (VERIFIED, [docs](https://docs.newrelic.com/docs/alerts/incident-management/response-intelligence-ai/)):

```
┌ Issue: High error rate · checkout ──────────────────────────────┐
│ ▸ AI summary (affected entity, severity, condition explained)   │
│ ┌ What's impacted? ┐ ┌ What happened previously? ┐ ┌ What to   ┐│
│ │ …                │ │ similar past issues +     │ │ check?    ││
│ │                  │ │ postmortems (RAG)         │ │ …         ││
│ └──────────────────┘ └───────────────────────────┘ └───────────┘│
│ Potential causes                                                │
│  • cause → mitigation steps · [chart] · NRQL: SELECT …          │
│ "Always verify insights against your data."                     │
└─────────────────────────────────────────────────────────────────┘
```

- Log alerts get an analysis of up to 100k lines: "Analysis context / What happened / Findings".
- Issue maps (2021) show the impacted entities and their neighbours.
- The Feb 2026 SRE Agent does "Intelligent RCA" with probabilistic causal models over topology (search snippet, [BusinessWire](https://www.businesswire.com/news/home/20260224122073/en)).

**Copy:** "What happened previously?", and the query shown next to each cause.

---

## 5. Graph explorers: canvas patterns

**Neo4j Bloom:**
- UI areas: Perspective drawer, Settings drawer, Legend panel (rule-based styling), Search bar, Card list ([visual tour](https://neo4j.com/docs/bloom-user-guide/current/bloom-visual-tour/)).
- **Search phrases:** parameterised Cypher templates typed in the search box.
- **Slicer** ([blog](https://neo4j.com/blog/developer/slice-and-dice-your-graph-data-with-neo4j-bloom/)):

```
 Slicer: anomaly.onset
 ▁▂▃▅▇█▇▅▃▂▁▁▁▁▂▃▅▇▅▂     [+ Add Range]  (up to 5)
     [=====]                ← drag window: nodes outside it fade out
 ▶ Playback: ( Slide range to end | Start of range to end | Within range )
```

- Date/time-based styling arrived in Bloom 2.1. Expand / Dismiss menus are INFERRED.

**FalkorDB Browser** (VERIFIED, [GitHub](https://github.com/FalkorDB/falkordb-browser)):
- Stack: Next 16, React 19, Tailwind 4, Radix, **cmdk**, **react-resizable-panels**, Monaco.
- Graph rendering: **cytoscape + cytoscape-fcose**, plus d3, ECharts and `@falkordb/canvas`.
- Per-label styling saved per graph, inline property editing, query history.
- Cypher errors are underlined with "Did you mean…?" fixes, plus **"Fix with AI"**.

---

## 6. Cross-cutting patterns

### 6.1 Verdict / hero card

| Who | Fields |
|---|---|
| Causely | ROOT CAUSE, metric, `path: A → B → C`, BLAST RADIUS, OWNER (+ on-call channel), time to triage, confidence |
| NeuBird | Root cause, Affected services, Contributing change, Impact, Recommended fix, "Found in 4m 12s · 15+ sources" |
| Datadog Watchdog | Root Cause → Critical Failure → Impact |
| Resolve | Bold one-line answer, then numbers |
| Dynatrace | Impact / Root cause (+ stack) / resolution path / automation, reorderable |

**Pattern:** answer, path, impact, owner, change, time, on one card. Epicenter's verdict card has root cause, path,
score parts and runner-up. **It is missing owner, contributing change, and "found in Ns".**

### 6.2 Confidence

| Style | Who | Note |
|---|---|---|
| Label with a definition (High/Med/Low = data completeness) + tooltip | Traversal | Honest. It explains the number |
| Evidence ladder (Speculation → Validated, alternatives ruled out) | incident.io | The most rigorous wording |
| Three states (validated / invalidated / inconclusive) | Datadog, Cleric verifier | Per hypothesis |
| % likelihood, top 3 | PagerDuty Probable Origin | Only on origin candidates |
| None | Resolve, Anyshift, Coroot, Dynatrace | Prose or ranking only |

Cleric's calibration blog found **the model's own confidence was poorly calibrated**. Epicenter's confidence is
deterministic, from `score_parts`, so it can say exactly why. That is a better story than any of the above, if the UI
explains it.

### 6.3 Hypotheses and ruled-out causes

| Who | Mechanism |
|---|---|
| Grafana Assistant | Hypotheses tab, "Disprove" / "Reopen", "Was this the cause? Yes / No" |
| Datadog | Hypothesis tree with invalidated branches |
| incident.io | "Discounted" findings kept in the audit trail |
| Cleric | "causes that were ruled out" + **Access limitations** + Remaining uncertainty |
| Grafana Sift | A visible, categorised check list |
| Coroot | Unrelated signals flagged on the propagation map |

### 6.4 Graph and topology

| Pattern | Who |
|---|---|
| The problem drawn as a group, gray context nodes, root cause with a red mark | Dynatrace VRP |
| Inspect view: upstream left, downstream right ("right = more likely root cause") | Datadog Service Map |
| Diagnosis ↔ Signals linked both ways | Causely |
| Propagation as an arrow chain | Coroot |
| Health on node borders, animated directional edges | Datadog |
| Vertical (hierarchy) vs Horizontal (neighbours) topology | Dynatrace |
| Time slicer with playback | Neo4j Bloom |
| 3D world model, node-type filter with counts | Traversal, Anyshift (marketing) |

### 6.5 Timeline

| Pattern | Who |
|---|---|
| Entity × time swimlanes, blue = change, red = failure, noise sliders | Grafana Asserts |
| One lane per entity under the resolution path | Dynatrace |
| T-minus change strip (PR −12m, flag −5m, spike 0) | Rootly |
| Pin from Slack → timeline at the original time | incident.io, Rootly |
| Conversational time travel ("1:45 PM: sg-prod-db modified") | Anyshift |

### 6.6 Live progress

| Pattern | Who |
|---|---|
| Numbered tool receipts with timing, size and `/show N` | HolmesGPT |
| Live steps that become a tree when done | Datadog |
| Step labels + source chips (Metrics, Logs, Traces, Deploys…) | NeuBird |
| One Slack message that edits itself + a thread | incident.io |
| "Stop" → summary marked incomplete; steering queue | Grafana Assistant |

### 6.7 Slack format

| Pattern | Who |
|---|---|
| Parent (header, entity, severity, View) + threaded Summary / Labels / Evidence / Remediation; empty sections skipped | Causely |
| Card with rows + "Found in … · N sources" + [View evidence] [Approve] | NeuBird |
| "Investigating…" → "What I've found so far" → link | Rootly |
| Relevant / Ignore votes synced with the web | Anyshift |

### 6.8 Actions and approval

| Pattern | Who |
|---|---|
| Card: rationale, risk level, duration, revertible; status Pending → … → Expired | Resolve |
| Policy (Act / Recommend), scope, named + timestamped approval, before/after metric | NeuBird |
| Only PRs you merge yourself | incident.io, Cleric |
| "With human approval", agent on the schedule | PagerDuty |
| Inline status: "Draft PR #848 opened" | Rootly |

### 6.9 Memory

| Pattern | Who |
|---|---|
| Proposal cards with Approve/Reject (Remember/Reject), linked to the source investigation | Traversal, Cleric |
| Categorised memory browser with search | Cleric (10 categories), Anyshift (4) |
| Agent-written versioned wiki with line comments | Traversal |
| Per-service memory artifacts, editable and redactable | PagerDuty |
| "What happened previously?" from postmortems | New Relic |
| Fix lines that cite past incidents where the same fix worked | Cleric |

### 6.10 Post-incident

| Pattern | Who |
|---|---|
| AI draft + "Review" with author-only inline suggestions | incident.io |
| AI blocks that show sources and prompt; regenerate / rate / preview on a past incident | Rootly |
| A mandatory close comment, saved as an annotation | Dynatrace |
| Draft post-mortem with "5 Whys" + what the agent got right and missed | Traversal |
| Follow-ups linked to Jira with owners | NeuBird |

### 6.11 Feedback loops

| Pattern | Who |
|---|---|
| 👍/👎 on each response | PagerDuty, Resolve (logged, not memory), Grafana |
| "Was this the cause?" Yes/No | Grafana |
| Correct or reinforce conclusions | Datadog |
| Investigations graded against real causes, changes backtested | incident.io |
| A benchmark score with sub-checks and cost | Coroot |

---

## 7. Gaps nobody fills

| Gap | Closest competitor | Epicenter strength that fills it |
|---|---|---|
| **Hypotheses drawn on the causal graph, with evidence for and against per node** | Causely (graph, no ruled-out list), Cleric (ruled-out list, no graph), Datadog (tree, not topology) | Incident canvas: hypothesis status rings on real operations, the winning path, citation spotlight |
| **"If this were the cause, what would we see?", drawn on the graph** | nobody. Coroot flags unrelated signals; Causely links Diagnosis↔Signals | **Fault Simulator overlay**: matched / missed / unexplained, "explains 6 of 7" |
| **"Why not X?" on demand** | Cleric's escalation lists ruled-out causes, but you can't ask about one | Why-not box: `victim`, `later_onset`, `not_upstream`, `lost_on_score`… plus the path |
| **Confidence you can take apart** | Traversal defines its label; no one shows the parts | Verdict `score_parts` bars (deterministic, versioned weights) |
| **Same input → same answer, shown on screen** | nobody | Kept numbered runs ([UI_SCREENS §12.4](UI_SCREENS.md#124-run-compare-incidentidruns)) |
| **Accuracy you can reproduce on a public benchmark** | Coroot has a scenario benchmark; everyone else gives vendor numbers | RCAEval AC@1 / AC@3 + ablations on `/eval` |
| **Honest "no root cause"** | Datadog "inconclusive", Cleric access limitations | `no_root_cause` card with what was checked and max coverage |
| **Open and self-hostable, graph-native** | HolmesGPT (no graph), Coroot (AI is paid) | the whole product (COMPETITORS §4) |

**Positioning line the UI should make obvious:** *Others tell you the cause. Epicenter shows you the graph that
proves it, what each suspect would have explained, and why every other one lost.*

---

## 8. Epicenter mapping: what to borrow, where

Each row names its competitor source, its target screen in [UI_SCREENS.md](UI_SCREENS.md), and any constraint from the
AGENTS.md hard rules. P0 = demo-critical; P3 = nice to have.

**Status (2026-10-16):** rows marked ✅ were built in [phase 12](phases/phase-12-ui-upgrades.md), along with the
Graph | Data toggle on every graph view. P0 #33 (eval per-case table) waits for phase 10's eval runner.

### 8.1 Incident page ([UI_SCREENS §4](UI_SCREENS.md#4-incident-incidentid))

| # | Borrow | From | Where | Priority | Constraint |
|---|---|---|---|---|---|
| 1 | Confidence tooltip that **defines** the number ("deterministic score from 6 parts, weights v…") | Traversal | Verdict ring | P1 ✅ built (phase 12) | rule 5: show weights version |
| 2 | Owner + contributing change + "found in Ns" on the verdict card | Causely, NeuBird | Verdict card | P1 ✅ built (phase 12) | data exists (`OWNED_BY`, `Change`) |
| 3 | **"Ruled out"** section on the verdict: refuted / pruned suspects, each with a one-line why-not | Cleric, incident.io | Verdict card | **P0** ✅ built (phase 12) | from why-not answers; no LLM |
| 4 | **"Couldn't see"** section (`Incident.gaps`) next to the verdict, not just a banner | Cleric (Access limitations) | Verdict card | P1 ✅ built (phase 12) | — |
| 5 | Three-state badge wording on suspects: supported / refuted / inconclusive, already in place; add "validated, alternatives ruled out" for confirmed | Datadog, incident.io | Suspect list | P2 | status set by the engine only (rule 4) |
| 6 | **Numbered query receipts** in the timeline: `#3 Q2 propagation · 14 ms · 6 rows` | HolmesGPT | Timeline tab | P1 ✅ built (phase 12) | log fields already in the design (`query_id`, `duration_ms`, `rows`) |
| 7 | Source chips while diagnosing (traces, metrics, logs, changes; grey if in gaps) | NeuBird | Header strip | P2 | — |
| 8 | Live steps that become a hypothesis tree when done | Datadog | Right rail: a "Tree" view of suspects → evidence | P2 | — |
| 9 | **Per-entity timeline lanes** under the canvas (anomaly onset bars, changes as blue ticks) | Asserts, Dynatrace | New canvas footer | **P0** ✅ built (phase 12) | uses `anomaly.onset`, `Change.ts` |
| 10 | T-minus change strip (change −Nm → onset → alert) | Rootly | Verdict card | P1 ✅ built (phase 12) | — |
| 11 | **Gray context nodes** (on the call path but not anomalous) | Dynatrace | Canvas | P2 | — |
| 12 | Problem drawn as a group around the anomalous region | Dynatrace | Canvas | P3 | — |
| 13 | Time slicer with **playback** of onsets on the canvas | Neo4j Bloom | Canvas | P1 (demo wow) ✅ built (phase 12) | — |
| 14 | Diagnosis ↔ Signals both ways: click a symptom → which suspects explain it | Causely | Canvas overlay | P1 ✅ built (phase 12) | from footprint `matched` |
| 15 | "Was this the cause? Yes / No" after the verdict → feeds resolve | Grafana | Verdict card | P2 | feedback never changes the score (rule 4) |
| 16 | Disprove / Reopen on suspects | Grafana | Suspect list | P3 | a human note, not a status change (rule 4); goes into `POST /notes` |
| 17 | Fix lines that cite precedent ("fixed inc-17, inc-9") | Cleric | Proposed actions | P1 ✅ built (phase 12) | `RESOLVED_BY` exists |
| 18 | Action card fields: rationale, risk, revertible, **"proposal only"** badge | Resolve, NeuBird | Proposed actions | P2 | rule 9: never executes |
| 19 | Memory proposal **Remember / Reject** at resolve | Traversal, Cleric | Resolve dialog | P3 | — |
| 20 | Mandatory note on resolve | Dynatrace | Resolve dialog | P3 | — |
| 21 | Reorderable left-rail sections | Dynatrace | Left rail | P3 | — |
| 22 | "Stop" → partial verdict marked incomplete | Grafana | Header | P3 | — |

### 8.2 Delivery (Slack / Linear)

| # | Borrow | From | Priority |
|---|---|---|---|
| 23 | Parent message + threaded Summary / Evidence / Remediation; empty sections skipped | Causely | P1 |
| 24 | "Found in Ns · N queries" footer + [Open in Epicenter] [View evidence] | NeuBird | P1 |
| 25 | Preview before sending (UI_SCREENS G9) | — | P2 |

### 8.3 Other existing screens

| # | Borrow | From | Screen | Priority |
|---|---|---|---|---|
| 26 | Inspect layout: upstream left, selected centre, downstream right | Datadog | Blast radius (graph mode) | P1 ✅ built (phase 12) |
| 27 | Probability shown as node intensity + **playback in expected-delay order** | Bloom, Asserts | What-if | P1 ✅ built (phase 12) |
| 28 | "Predicted vs observed" after a saved simulation (UI_SCREENS G1) | nobody does this | Incident | P1 |
| 29 | Nudge chips (suggested questions) under the composer, aware of the incident | PagerDuty | Ask | P2 |
| 30 | Show the query behind the answer (already done) + a **"Sources" tab** | New Relic, Grafana | Ask | done / P3 |
| 31 | Select text → ask about it | Grafana | Incident explanation | P3 |
| 32 | Status filters + a problem chart above the list; select a peak to filter | Dynatrace | Incidents list | P2 |
| 33 | **Benchmark with sub-checks + per-case table** (case, label, our top-3, hit/miss, link) | Coroot | Eval | **P0** |
| 34 | Scenario cards with expected verdict + "investigation already running" on open | Honeycomb | Runs | **P0** |
| 35 | Public **playground** / demo env link from the landing page | Anyshift | Landing | P2 |

### 8.4 Candidate new screens ([UI_SCREENS §12](UI_SCREENS.md#12-candidate-new-screens)) re-ranked by this research

| Screen | Competitor evidence | Verdict |
|---|---|---|
| Service map `/map` | Datadog Service Map, Coroot, Dynatrace Smartscape, Grafana Knowledge Graph: **table stakes** for graph tools | ✅ **built (phase 12)**. **P1**: build. Health on node borders, animated edges, upstream-left inspect |
| Graph What-if with playback | nobody animates predicted spread | ✅ **built (phase 12)**. **P1**: differentiator |
| Run compare | nobody | **P2**: unique trust proof, cheap if a runs endpoint exists |
| System / trust page | Coroot shows tokens and cost; NeuBird model spend; nobody shows weights | **P2**: show weights, rules, query latency, LLM spend |
| Changes feed | Anyshift (whole product), Rootly strip, Asserts blue bars | **P3** as a page; **P0 as canvas lanes (#9)** |
| Memory browser `/memory` | Cleric, Traversal, Anyshift, PagerDuty | **P3**: categories + search over resolved incidents and runbooks |
| Postmortem / report | incident.io, Rootly, Traversal "5 Whys" | **P3**: template from evidence; LLM text only with citations |
| War-room / live | NeuBird Ops Center | P3 |
| Leadership brief | NeuBird | skip |

### 8.5 Do not copy

| Pattern | Why not |
|---|---|
| Executing fixes ("Approve rollback" that runs) | Hard rule 9: read-only; actions are proposals |
| LLM self-rated confidence | Cleric shows it's poorly calibrated; rule 4: the LLM never ranks |
| 3D "world model" graph | Marketing value, poor readability; a 2D layered layout explains paths better |
| Credit-metered AI nudges | Friction; the core verdict needs no LLM (rule 12) |
| Chat-only investigation | Loses the "every answer is a path" principle (P5) |

---

## 9. Sources

**Traversal:**
- https://docs.traversal.com/introduction
- https://docs.traversal.com/using-traversal/investigations
- https://docs.traversal.com/using-traversal/understanding-results
- https://docs.traversal.com/using-traversal/knowledge-bank
- https://docs.traversal.com/using-traversal/slack
- https://docs.traversal.com/llms.txt
- https://www.traversal.com/

**Resolve AI:**
- https://resolve.ai/
- https://resolve.ai/product/ai-sre
- https://docs.resolve.ai/auto-investigations
- https://docs.resolve.ai/chats.md
- https://docs.resolve.ai/alert-investigation-modes.md
- https://docs.resolve.ai/mitigation-actions.md
- https://docs.resolve.ai/app-for-slack
- https://docs.resolve.ai/team-knowledge.md
- https://docs.resolve.ai/skills.md

**Causely:**
- https://www.causely.ai/
- https://docs.causely.ai/
- https://docs.causely.ai/in-action/root-causes.md
- https://docs.causely.ai/in-action/topology.md
- https://docs.causely.ai/workflows/slack.md
- https://grafana.com/grafana/plugins/esara-causely-app
- https://dev.to/causely/causely-feature-demo-unlock-root-cause-analysis-in-grafana-2817

**Anyshift:**
- https://www.anyshift.io/
- https://docs.anyshift.io/pages/overview
- https://docs.anyshift.io/pages/product/root_cause_analysis
- https://docs.anyshift.io/pages/product/time_travel
- https://docs.anyshift.io/pages/product/integration/slack
- https://docs.anyshift.io/pages/overview/memory_agents
- https://playground.anyshift.io

**Cleric:**
- https://cleric.ai/
- https://cleric.ai/product.md
- https://docs.cleric.ai/usage/how-investigations-work.md
- https://docs.cleric.ai/learning/memories.md
- https://cleric.ai/blog/verifying-fixes
- https://businesswire.com/news/home/20251209625361/en/Cleric-Launches-the-First-Self-Learning-AI-SRE

**NeuBird:**
- https://neubird.ai/
- https://neubird.ai/solutions/slack
- https://betterstack.com/community/comparisons/neubird-alternatives/ (competitor, biased)

**Datadog:**
- [D1] https://docs.datadoghq.com/bits_ai/bits_ai_sre/investigate_issues/
- [D2] https://www.datadoghq.com/blog/bits-ai-sre/
- [D3] https://www.datadoghq.com/blog/bits-ai-sre-deeper-reasoning
- [D4] https://docs.datadoghq.com/watchdog/rca/
- [D5] https://docs.datadoghq.com/watchdog/insights/
- [D6] https://www.datadoghq.com/blog/building-bits-ai-sre/
- [D7] https://docs.datadoghq.com/tracing/services/services_map/
- [D8] https://docs.datadoghq.com/bits_ai/bits_ai_sre/chat_bits_ai_sre/

**PagerDuty:**
- https://support.pagerduty.com/docs/sre-agent
- https://support.pagerduty.com/docs/related-incidents
- https://support.pagerduty.com/docs/change-events
- https://support.pagerduty.com/main/docs/probable-origin
- https://www.pagerduty.com/blog/ai/new-enhancements-to-pagerdutys-sre-agent-triage-faster-without-waking-a-human/
- https://www.pagerduty.com/blog/ai/we-built-an-sre-agent-with-memory-and-its-transforming-incident-response/
- https://www.pagerduty.com/blog/product/the-path-to-autonomous-operations-pagerduty-spring-26-release/

**incident.io:**
- https://incident.io/ai-sre
- https://docs.incident.io/investigations/overview
- https://docs.incident.io/investigations/how-investigations-work
- https://docs.incident.io/investigations/trust-and-safety
- https://incident.io/blog/how-it-feels-to-run-an-incident-with-ai-sre
- https://docs.incident.io/post-incident/timeline
- https://incident.io/blog/post-mortems-launch
- https://docs.incident.io/post-incident/postmortem-ai

**Rootly:**
- https://rootly.com/ai-sre
- https://rootly.com/blog/telemetry-deploy-correlation-ai-sre
- https://docs.rootly.com/incidents/incident-timeline/adding-events-to-timeline-via-slack
- https://rootly.com/changelog/2022-07-27-beautiful-incident-timeline-pages
- https://docs.rootly.com/retrospectives/retrospectives.md
- https://docs.rootly.com/ai/ai-in-retrospectives/overview
- https://rootly.com/changelog/retrospective-template-with-opinions
- https://incident.io/blog/rootly-ai-accuracy-vs-competitors (competitor, biased)

**HolmesGPT:**
- https://holmesgpt.dev/latest/
- https://holmesgpt.dev/latest/walkthrough/interactive-mode/
- https://holmesgpt.dev/latest/data-sources/tool-execution-safety/
- https://github.com/robusta-dev/holmesgpt
- https://docs.robusta.dev/master/configuration/ai-analysis.html

**Coroot:**
- https://github.com/coroot/coroot
- https://docs.coroot.com/ai/overview
- https://docs.coroot.com/inspections/overview
- https://coroot.com/blog/hard-part-of-ai-root-cause-analysis-is-no-longer-the-model/
- https://coroot.com/ai-benchmark/scenarios/productCatalogFailure

**K8sGPT:**
- https://github.com/k8sgpt-ai/k8sgpt

**Grafana:**
- https://grafana.com/docs/grafana-cloud/machine-learning/assistant/investigations
- https://grafana.com/whats-new/2025-10-08-introducing-assistant-investigations--now-in-public-preview/
- https://grafana.com/docs/grafana-cloud/monitor-applications/asserts/manage-infra-apps/workbench
- https://grafana.com/blog/2024/09/24/contextual-root-cause-analysis-grafana-cloud/
- https://grafana.com/docs/grafana-cloud/alerting-and-irm/machine-learning/sift/sift/
- https://grafana.com/docs/grafana-cloud/monitor-applications/asserts/

**Dynatrace:**
- https://docs.dynatrace.com/docs/dynatrace-intelligence/problems-app
- https://docs.dynatrace.com/docs/analyze-explore-automate/smartscape/smartscape-modals/visual-resolution-path
- https://docs.dynatrace.com/docs/analyze-explore-automate/smartscape/smartscape-views/problem-graph
- https://docs.dynatrace.com/docs/analyze-explore-automate/smartscape/smartscape-modals/smartscape-view-topology
- https://community.dynatrace.com/t5/Alerting/Can-Dynatrace-send-multiple-rootcause-nodes-in-a-single-problem/m-p/176040

**Honeycomb:**
- https://docs.honeycomb.io/investigate/analyze/identify-outliers/
- https://www.honeycomb.io/blog/meet-canvas-your-ai-guided-workspace-within-honeycomb
- https://docs.honeycomb.io/investigate/canvas/alert-investigation
- https://www.honeycomb.io/blog/ai-working-for-you-mcp-canvas-agentic-workflows-pt2

**New Relic:**
- https://docs.newrelic.com/docs/alerts/incident-management/response-intelligence-ai/
- https://docs.newrelic.com/whats-new/2021/05/whats-new-5-27-aiops-issuemaps-and-more/
- https://www.businesswire.com/news/home/20260224122073/en

**Neo4j Bloom:**
- https://neo4j.com/docs/bloom-user-guide/current/bloom-visual-tour/
- https://neo4j.com/blog/developer/slice-and-dice-your-graph-data-with-neo4j-bloom/
- https://neo4j.com/blog/developer/time-travel-with-neo4j-bloom-2-1/
- https://neo4j.com/blog/developer/how-to-create-conditional-and-dynamic-queries-in-neo4j-bloom/

**FalkorDB Browser:**
- https://github.com/FalkorDB/falkordb-browser
- https://browser.falkordb.com

**Not covered** (fetch limits during research): the Datadog Incident Management timeline doc, the full PagerDuty
Spring '26 post, the PagerDuty incident timeline UI, the Rootly product/ai page (403), and the Cleric live demo
(rendered empty).
