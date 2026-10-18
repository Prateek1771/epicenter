# Epicenter pitch deck (5 minutes)

Built with the hackathon-strategist pitch structure: problem → evidence → cost → solution → live demo → before/after →
tech → scale → team → Q&A. Every number here is either measured by us (README §7) or cited at the bottom. Slides that
still need input from you are marked **TODO**.

**USP in one sentence:** Epicenter doesn't blame the loudest service. For every suspect it asks "if this were the
cause, what would we see?" and checks the prediction against what actually broke, then shows the answer as a graph path
you can click.

**Persona:** the on-call backend engineer at a company running 30–300 microservices, paged at night, staring at ten
red dashboards with no idea which one started it.

---

## Global design system (use on every slide)

| Token | Value | Use |
|---|---|---|
| Background | `#050505` (void), cards `#0a0a0a`, borders `#26241f` | Every slide is dark |
| Text | `#dedbc8` (bone), muted `#9d998c` | Body and labels |
| Accent | `#e6c77d` (gold) | One highlight per slide: the key number or word |
| Failure | `#eb5757` (coral red) | Broken services, "before" numbers |
| Confirmed | `#27a644` (pulse green) | Root cause, "after" numbers |
| Signal | `#02b8cc` (teal) | Graph edges, paths, data flow |
| Headings | Instrument Serif, 56–72 pt, sentence case, italic allowed for one word | |
| Body | Inter, 20–24 pt, max 3 lines per block | |
| Code / ids | JetBrains Mono, 18 pt | `mongodb/find`, query ids |

Layout rules: 16:9, 80 px safe margin, 12-column grid. Left-align text; never center a paragraph. One idea per slide,
one gold accent per slide. Illustrations sit on the right 5–7 columns unless noted, fading into the black background
(no hard image edges).

**Base style string** (prepend to every image prompt below):

> Minimal dark editorial illustration, pure black background #050505, thin luminous lines, warm bone-white #dedbc8
> strokes, single gold #e6c77d accent, subtle film grain, lots of negative space, isometric-lite technical diagram
> feel, no text, no logos, no people's faces, 16:9

**Negative prompt** (all images): text, letters, watermark, logo, cartoon, neon cyberpunk overload, purple gradients,
stock-photo people, 3D glossy plastic, clutter, lens flare

---

## Slide 1. Hook (0:00–0:15)

**On slide**
- Title: *Epicenter*
- Subtitle: Find where every outage started.
- Small footer: Graph Hacks · FalkorDB · Track 01: Agents That Act on Connected Data

**Speaker script**
"Quick show of hands: who here has been paged for an outage and spent the first hour looking at the wrong service?
Keep them up if the service screaming the loudest wasn't actually the one that broke."

Pick one audience question (alternatives):
1. "Who's been paged at 3 a.m. and opened ten dashboards before finding the one that mattered?"
2. "Who's ever restarted a service during an outage, and it turned out it wasn't that one?"

**Alignment:** title left-aligned at 40% height, columns 1–6. Illustration fills columns 6–12, bleeding off the right
edge.

**Illustration prompt**
> [base style] A seismograph-like map seen from above: a dark network of small nodes connected by thin teal lines; one
> small node near the lower left glows gold and emits concentric shockwave rings that travel outward across the
> network; nodes further away flicker coral red where the rings hit them. The gold origin point is small and quiet, the
> red nodes are loud. Calm, precise, cinematic.

---

## Slide 2. The problem (0:15–0:40)

**On slide**
- Heading: The loudest service is rarely the cause.
- Three short lines:
  - One datastore slows down.
  - Twelve services in front of it start failing.
  - Every dashboard points at the wrong one.

**Speaker script**
"In a microservice system, failures spread. A database gets slow, and the service in front of it throws errors, and
the service in front of that times out. The on-call engineer gets an alert from the edge, sees red everywhere, and
chases the noisiest symptom. The real cause is quiet, upstream, and easy to miss."

**Alignment:** text in columns 1–5, vertically centered. Diagram in columns 6–12.

**Illustration prompt**
> [base style] A left-to-right chain of five rounded service boxes connected by thin teal arrows. The rightmost three
> boxes glow intense coral red with jagged alarm pulses; the leftmost box is dim, almost invisible, with a faint gold
> crack running through it. A tiny magnifying-glass cursor hovers over the brightest red box on the right, looking in
> the wrong place.

---

## Slide 3. Evidence (0:40–1:00)

**On slide** (three "headline clipping" cards, each with a source line)
- "Customer-facing incidents up 43% in a year." (PagerDuty, 2024)
- "Average incident takes 175 minutes to resolve." (PagerDuty, 2024)
- "Frontier AI agents find the right root cause ~25% of the time, and invent one in up to 40% of incidents."
  (Traversal ORCA-Bench)

**Speaker script**
"This isn't just us. PagerDuty's 2024 survey of 500 IT leaders found customer-facing incidents went up 43% in a year,
and each one takes almost three hours to resolve. And the AI tools aren't there yet: on Traversal's own on-call
benchmark, frontier models get the root cause right about a quarter of the time and make one up in up to 40% of
incidents."

**Alignment:** three cards in a row, columns 1–4 / 5–8 / 9–12, top-aligned at 35% height. Heading above, left-aligned.
Each card: big quote in Instrument Serif, source in JetBrains Mono, muted.

**Illustration prompt** (card backgrounds, optional)
> [base style] A slightly tilted torn newspaper clipping texture on black, paper in dark graphite #131210 with faint
> bone-colored ruled lines, no readable text, soft shadow, one corner curling. Generate 3 variations.

---

## Slide 4. The cost (1:00–1:15)

**On slide**
- One big number in gold: **$2M per hour**
- Under it: median cost of a high-impact outage (New Relic, 2025)
- Secondary line, muted: $4,537 per minute · ~$794k per incident (PagerDuty, 2024)

**Speaker script**
"New Relic's 2025 survey puts the median high-impact outage at two million dollars an hour. Every minute spent looking
at the wrong service costs money."

**Alignment:** number centered horizontally and vertically (the one exception to left-align), 160 pt. Captions below,
centered, max width 8 columns.

**Illustration prompt**
> [base style] A single thin gold line chart drawn across the full width, flat and calm on the left, then a sudden
> sharp spike and a long jagged red decline, like a revenue graph during an outage. Very sparse, the line is the only
> element, placed in the lower third so the top stays empty for a large number.

---

## Slide 5. The solution (1:15–1:40)

**On slide**
- Heading: Epicenter asks every suspect: *if it were you, what would we see?*
- Three steps, icons + one line each:
  1. **Map:** a live graph of your services and who calls whom
  2. **Simulate:** predict each suspect's footprint, compare with what really broke
  3. **Answer:** the root cause, the path it took, and who to page
- Screenshot: the incident page (verdict + graph path)

**Speaker script**
"Epicenter keeps a live map of your system in FalkorDB: services, who calls whom, recent deploys, owners. When an alert
fires, it walks upstream and treats everything that misbehaved as a suspect. Then for each one it runs a simulation:
if this were the cause, which things should break, and in what order? The suspect whose prediction matches reality
wins. You get the answer as a path you can click, not a paragraph you have to trust."

Grandparent test: "It works out which broken part broke the others first, by checking what each one would have broken."

**Alignment:** heading full width, top. Steps in columns 1–5 stacked vertically, 32 px gap. Screenshot in columns 6–12
inside a thin `#26241f` browser frame with 8 px radius, slight drop shadow.

**Illustration prompt** (three step icons, line style)
> [base style] Three minimal line icons, same stroke weight, bone white on black, laid out separately: (1) a small node
> graph of five connected circles, (2) a ghost/dotted copy of a graph overlaid on a solid one, slightly offset,
> (3) a single path of three nodes ending in a gold glowing node with a check mark shape formed by the edges. Flat,
> geometric, icon set.

**Screenshot to capture:** `/incident/{id}` for `loud-victim`, canvas showing alert → path → `mongodb/find`, right
panel open on Suspects.

---

## Slide 6. Live demo (1:40–3:10)

**On slide** (shown only before switching to the browser)
- Heading: Live: the loud victim
- One line: A datastore slows down. The service in front of it fails loudly. Who gets the blame?

**Demo steps** (from [DEMO_SCRIPT.md](DEMO_SCRIPT.md), USP first)
1. `/runs` → Demo 1 · Synthetic → `loud-victim` → **Run**. "A generated system with a known answer."
2. Incident page: point at alert → path → root cause. "It walks the call graph upstream in FalkorDB, at most six hops."
3. Right panel → **Suspects**: `svc-0` **refuted**, `mongodb/find` **confirmed**. "The loud one is refuted. Its
   predicted footprint doesn't match what broke. `mongodb/find` explains the symptoms, so it wins at 99.5%." **This is
   the moment. Pause here.**
4. Verdict card: score parts, evidence, **AGENTS.md** download. "Same input, same answer, byte for byte. The LLM never
   ranks."
5. If time: `/simulate` → `payment` → **Run experiment**. "The same simulator answers what-ifs before you ship."

Fallback: if the live site or Docker fails, play the recorded video (**TODO:** add link, README still says "add the
link before submitting").

**Alignment:** heading left at 40% height, subtitle below. Right side: a small QR code to the live demo URL in columns
10–12, bottom-aligned.

**Illustration prompt**
> [base style] A dark browser window floating at a slight angle, inside it an abstract graph canvas: a red alert node on
> the right, a teal path flowing left through three nodes to a gold node; beside the canvas a narrow side panel with
> two rows, one crossed out in red, one checked in green, shown as abstract bars without readable text.

---

## Slide 7. Before & after (3:10–3:30)

**On slide** (two columns)

| Before | After |
|---|---|
| Ten dashboards, one guess | One path, checked against every symptom |
| Finding the cause is part of a **175-minute** incident | Verdict in **~10 s** (p50, 24 min of telemetry ingested + diagnosed) |
| Blames the loudest service | Refutes the loud victim, names the quiet cause |
| AI that can make up a cause | Says "no root cause" when nothing fits |

**Speaker script**
"Before: the average incident runs almost three hours, and a big chunk of that is just finding where it started.
After: Epicenter gives a verdict in about ten seconds, with the path, the evidence and the owner. And when nothing in
the graph explains the alert, it says so instead of guessing."

Honesty note for Q&A: 175 min is full resolution time (PagerDuty), not diagnosis time alone. We cut the "where did it
start?" part, not the fix.

**Alignment:** two equal columns (1–6 / 7–12) split by a 1 px `#26241f` vertical rule. "Before" header and numbers in
coral red, "After" in pulse green. Rows aligned on the same baselines across columns.

**Illustration prompt**
> [base style] Split composition. Left half: a tangled cluster of glowing coral-red lines and many small dashboard
> rectangles, chaotic. Right half: the same nodes arranged cleanly with a single straight teal path ending in a gold
> point. A thin vertical divider in the center. Symmetric, calm on the right.

---

## Slide 8. Proof: we measured it (3:30–3:50)

**On slide**
- Big number: **90.0%** top-1 on held-out cases
- Under it: RCAEval RE2-TT, 90 real recorded faults, engine only, no LLM
- Small bar row: cpu 100% · delay 100% · socket 93% · disk 87% · loss 73% · mem 73%
- Footer: two runs give byte-identical results

**Speaker script**
"We didn't just demo it, we benchmarked it. On the public RCAEval benchmark, 90 real recorded faults, Epicenter puts the
right root cause first 87.8% of the time, and 90% on the cases we never tuned on. Most vendors publish their own MTTR
claims. We publish the score, the losses included."

**Alignment:** big number left (columns 1–6), 140 pt gold. Per-fault bars right (columns 7–12), horizontal bars sorted
descending, teal fill, labels in JetBrains Mono.

**Illustration:** none. Draw the bars as a chart, not an image.

---

## Slide 9. How it's built (3:50–4:10, optional, skip if short on time)

**On slide** (one diagram)
`Telemetry (traces, metrics, logs, deploys)` → `FalkorDB graph per environment` → `Agents: triage · investigator ·
skeptic · historian` → `Fault Simulator + deterministic score` → `Verdict as a graph path` → `Slack / Linear`

Three callouts:
- Graph algorithms: bounded path search (6 hops), `algo.pageRank` on a per-incident projection, vector index for memory
- Agents share state through the graph and hold ids only
- The LLM only writes explanations. It never ranks.

**Speaker script**
"Traces roll up into a graph in FalkorDB. Four agents work the incident and hand off through the graph. Ranking is
deterministic, with PageRank on a blame projection and the Fault Simulator. The LLM writes the explanation, and that's
all it does. Every query p95 is under 60 ms."

**Alignment:** horizontal flow diagram across the full width at 45% height, nodes as rounded rectangles (`#0a0a0a`
fill, `#26241f` border), arrows in teal. FalkorDB node highlighted with a gold border. Callouts below in three columns.

**Illustration prompt** (if you want a hero image instead of a flat diagram)
> [base style] Isometric layered stack: a bottom layer of scattered faint data particles (telemetry), a middle layer
> forming a clean glowing teal graph of nodes and edges (the knowledge graph) with one gold-bordered node, a top layer
> of four small abstract agent orbs connected to the graph by thin vertical light beams. Precise, architectural.

---

## Slide 10. Scale & roadmap (4:10–4:30)

**On slide** (three lines)
- **Now:** 26 synthetic incidents, 90 RCAEval faults, a live OpenTelemetry Demo shop. Self-hosted in one Docker Compose.
- **Next:** more telemetry adapters (Datadog, Grafana, CloudWatch), more fault rules, a hosted version for small teams.
- **Business:** open core. The self-hosted engine stays free; paid cloud, SSO, audit and support.

**Speaker script**
"Today it runs on a laptop with one command. Next, more sources: each new tool is one adapter, and each new failure
mode is one rule file. The business is open core: free engine, paid hosted version. Every graph-native competitor is
closed and sales-led. We're the open one whose accuracy you can check."

**Alignment:** three rows, label column (Instrument Serif, gold) in columns 1–3, text in columns 4–12.

**Illustration prompt**
> [base style] Three concentric rings expanding from a small gold center node, each ring slightly brighter teal and
> with more nodes than the last, suggesting growth from one system to many. Placed on the right third, fading out.

---

## Slide 11. Team & close (4:30–4:45)

**On slide**
- **TODO:** names, roles, one line each on why you're the right people (e.g. who has been on call)
- Live demo URL + QR: https://epicenter.13-204-211-105.sslip.io
- Repo: github.com/Prateek1771/epicenter
- Closing line: *Find where every outage started.*

**Speaker script**
"[Team intro]. Epicenter is live right now at this link, and the repo runs on any laptop in ten minutes. Thanks, happy
to take questions."

**Alignment:** team photos/avatars in a row (columns 1–8), QR bottom-right (columns 10–12), closing line bottom-left in
Instrument Serif italic.

**Illustration prompt** (if you don't use photos)
> [base style] Minimal line-art avatars as abstract circles with a single gold ring each, arranged in a row, each
> connected to the next by a thin teal edge like nodes in a graph.

---

## Time budget

| Slide | Time |
|---|---|
| 1 Hook | 0:15 |
| 2 Problem | 0:25 |
| 3 Evidence | 0:20 |
| 4 Cost | 0:15 |
| 5 Solution | 0:25 |
| 6 Live demo | 1:30 |
| 7 Before/after | 0:20 |
| 8 Proof | 0:20 |
| 9 Tech (optional) | 0:20 |
| 10 Scale | 0:20 |
| 11 Team | 0:15 |
| **Total** | **4:45** (4:25 without slide 9) |

---

## Judge Q&A prep

| Question | Honest answer |
|---|---|
| How is this different from Resolve AI / Traversal / Datadog Bits? | They're closed and sales-led. We're open source, self-hostable, deterministic, and we publish our benchmark score, losses included. |
| What happens when it's wrong? | It shows every suspect with the evidence for and against, so a human can check. And it says "no root cause" when nothing fits instead of inventing one. It never acts on production by itself. |
| Is the demo real or mocked? | Synthetic samples have known answers so you can verify them. The 90-case benchmark uses real recorded faults. The OTel Demo runs live faults in a real microservice shop. |
| Where does it fail? | Memory loss and mem faults are weaker (73%). Memory recall is weak (12% precision@3). And on RE2-TT it scores better without the temporal rule; we kept it because the live deploy and flag scenarios need it. |
| Does it scale? | Every traversal starts from an indexed node and stops at 6 hops. PageRank runs on a per-incident projection, never the whole graph. Query p95 is under 60 ms. Huge synthetic (300 services) is our weakest size at 5/9, and that's next on the list. |
| Why a graph, not just an LLM? | The question is "what depends on what", which is a graph question. The graph also holds the agents' shared state and the incident memory. Take FalkorDB out and nothing works. |
| Who pays? | Platform teams at companies with 30+ services. Free self-hosted core; paid hosting, SSO, audit and support. |

---

## Sources

- [New Relic 2025 Observability Forecast: $2M/hour median high-impact outage](https://newrelic.com/press-release/20250917)
- [PagerDuty 2024 survey: incidents up 43%, $4,537/min, ~$794k per incident, 175 min to resolve](https://investor.pagerduty.com/news/news-details/2024/PagerDuty-Survey-Reveals-Customer-Facing-Incidents-Increased-by-43-During-the-Past-Year-Each-Incident-Costs-Nearly-800000/default.aspx)
- [ITIC 2024: one hour of downtime costs over $300k for 90%+ of mid-size and large enterprises](https://www.calyptix.com/wp-content/uploads/Hourly-Cost-of-Downtime-ITIC.pdf)
- [Traversal ORCA-Bench: frontier agents ~25% correct, up to 40% invented causes](https://www.traversal.com/blog/orca-bench-how-ready-are-language-model-agents-for-oncall)
- Epicenter's own numbers: [README §7](../README.md#7-evaluate), [EXAMPLE_RUNS](EXAMPLE_RUNS.md)
- Competitor landscape: [COMPETITORS.md](COMPETITORS.md)
