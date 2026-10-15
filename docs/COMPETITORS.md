# Competitors: AI SRE / root cause analysis

**Researched:** 2026-10-15 · **Method:** web search; most comparison sites are written by competing vendors, and no vendor
pricing page was checked directly, so prices come from third-party sites and may be stale. Re-check before using a
number in a pitch. Anything unverified is marked `unknown`.

**Assumed frame:** category = finding the root cause of production incidents (AI SRE); segment = mid-market to enterprise
engineering teams; geography = global; purpose = positioning and pitch.

**Short answer:** the space is crowded, and **several funded companies already use a graph of production**. Epicenter's
real opening is narrower: an **open, self-hostable, graph-native** tool that **publishes its accuracy**. That
combination appears to be unclaimed.

---

## 1. Who's working on the same thing

### Direct: AI SRE startups that find the root cause

| Company | How it works | Graph? | Funding / traction |
|---|---|---|---|
| **Resolve AI** | A planner agent with sub-agents across code, infrastructure and telemetry; can take actions | Yes, a knowledge graph of production | $125M Series A at $1B (Feb 2026); reported extension to $1.5B, $190M+ total |
| **Traversal** | "Causal search engine" over a "production world model"; on-prem / BYOC option | Yes, causal graph; claims 1.7M+ nodes | $48M (Jun 2025, Kleiner + Sequoia) |
| **Causely** | Causal model of the environment that maps "A caused B" mathematically | Yes; most explicitly causal, has an arXiv paper | `unknown` |
| **Anyshift** | Versioned graph of cloud resources, k8s objects and git commits; asks "what changed?" | Yes, built from infrastructure rather than telemetry | Founders built driftctl (acquired by Snyk) |
| **Cleric** | Read-only by design; captures team knowledge from each incident | Yes, knowledge graph of infrastructure | $9.8M seed (reported) |
| **NeuBird (Hawkeye)** | Enterprise IT operations agent | "Dynamic knowledge graph" | `unknown` |

**Smaller and newer:** Ciroos ($21M), Hyground (€3M pre-seed, Mar 2026, "sovereign SRE agent"), Deductive AI (diagnosis only).

### Adjacent: bigger vendors adding AI SRE features

| Vendor | Product | Why it matters |
|---|---|---|
| Datadog | Bits AI SRE | "We already use Datadog for this" is the #1 objection |
| PagerDuty | SRE Agent / AIOps | Owns the paging workflow |
| incident.io, Rootly | AI SRE add-ons | Own the incident workflow |
| Sumo Logic | Root Cause Agent (preview, 13 Oct 2026) | Shows the big vendors are still adding this right now |

### Open source

| Project | Notes |
|---|---|
| **HolmesGPT** (Robusta, CNCF Sandbox, Apache-2.0) | The main open-source AI SRE. The agent fetches telemetry fresh on every step; no graph and no memory |
| **K8sGPT** | Kubernetes-only analyzer; simple, works from the command line |
| **RunLore** (Go) | Read-only; stores past investigations as memory |
| **Coroot** | Open-source service map; its AI root-cause analysis is paid / cloud only |

**Left out:** Metoro, Komodor, Lightrun and the older AIOps tools (Moogsoft, BigPanda). They're either Kubernetes-only,
debugging-focused, or about alert noise rather than diagnosis.

---

## 2. Pricing (third-party sources, not checked on vendor sites)

| Product | Public price | Model | What unlocks more |
|---|---|---|---|
| Datadog Bits AI SRE | $500/mo for 500 AI credits (annual), or $1.30/credit; about 6.5 credits per investigation | Usage | Number of investigations |
| PagerDuty AIOps | From $699/mo (annual), plus Advance at $415/mo | Add-on, per event | Event volume |
| incident.io AI SRE | Contact sales (base platform $15–45/user/mo) | Per seat + add-on | Sales call |
| Rootly AI SRE | Contact sales (base $20/user/mo) | Per seat + add-on | Sales call |
| Resolve AI | Enterprise, contact sales | Sales-led | `unknown` |
| Traversal | Not disclosed | Sales-led | `unknown` |
| Cleric | Free tier reported; paid not disclosed | Freemium | `unknown` |
| Causely, NeuBird, Anyshift | `unknown` | — | — |

**Takeaway:** only Datadog publishes a usage price, at roughly $6–8 per investigation. Every graph-native startup is sales-led.

---

## 3. Who wins on what

- **Resolve AI:** autonomy and breadth (it takes actions), for large enterprises.
- **Traversal:** causal search at huge scale, plus on-prem, for regulated enterprises.
- **Causely:** a mathematical causal model, for teams that distrust LLM guesses.
- **Anyshift:** the "what changed?" angle, from an infrastructure graph.
- **Cleric:** read-only safety and team knowledge, for cautious teams.
- **Datadog / PagerDuty:** convenience, because you already pay them.
- **HolmesGPT:** free and open, but no graph and no memory.

**Positions nobody seems to claim:** open source *and* graph-native; accuracy published on a public benchmark;
self-serve pricing for the graph-native tools.

---

## 4. Gaps

| Gap | Evidence | Why it's open | Verdict |
|---|---|---|---|
| **Open-source, self-hostable, graph-native AI SRE** | Graph players are closed (Resolve, Traversal, Causely, Anyshift, Cleric); the open-source leader HolmesGPT has no graph or memory | Venture-backed companies keep their core closed to protect revenue | **Wedge, real.** Defensible through community and integrations, not the algorithm |
| **Published, reproducible accuracy** | Traversal's own ORCA-Bench: frontier models find the right root cause about 25% of the time and invent a cause in up to 40% of incidents. Competitors cite their own MTTR numbers, not benchmarks | Publishing accuracy is risky when the numbers are low | **Wedge.** A deterministic "same input → same answer" engine plus a published RCAEval score is a credible trust story |
| **"Every answer is a clickable path"** | Competitors explain in prose; Causely is the closest | Mostly a UI and design choice | **Feature gap.** Copyable within a quarter, but a strong demo |
| **Self-serve / transparent pricing for graph-native RCA** | All the graph players are contact-sales | High-value deals pay for their sales teams | **Wedge for small and mid-size companies**, if you can sell without a sales team |
| **Deterministic causal reasoning** | Causely already does this | — | **Not a gap.** Don't claim it as unique; claim "open + deterministic" |
| **Memory across incidents** | Cleric, RunLore, Resolve all advertise it | — | **Not a gap.** Table stakes |

---

## 5. Positioning for Epicenter

Don't pitch "AI SRE with a knowledge graph"; five funded companies already say that.

Pitch: **"The open, self-hostable, graph-native AI SRE whose accuracy you can check."**

Business model: **open-core**: free self-hosted core, paid cloud and enterprise features (SSO, multi-tenant, audit, support).

---

## Sources

- [Metoro: Traversal alternatives](https://metoro.io/comparisons/ai-sre/traversal-ai-alternatives)
- [Mezmo: 2026 AI SRE market map](https://www.mezmo.com/learn/the-2026-ai-sre-market-map-agents-harnesses-and-the-data-layer)
- [wetheflywheel: best AI SRE tools 2026](https://wetheflywheel.com/en/guides/best-ai-sre-tools-2026/)
- [Anyshift: top 10 AI SRE tools 2026](https://www.anyshift.io/blog/top-10-ai-sre-tools-2026-comparison)
- [Built In NYC: Traversal raises $48M](https://www.builtinnyc.com/articles/traversal-raises-48m-to-launch-ai-sre-20250620)
- [Beri: Resolve AI at $1.5B](https://www.beri.net/article/resolve-ai-190m-ai-sre-production-incidents-2026)
- [Partech: Hyground pre-seed](https://partechpartners.com/news/hyground-raises-3m-pre-seed-round-to-build-the-sovereign-sre-agent-for-enterprise-it-operatons)
- [Ciroos launch](https://ciroos.ai/blogs/launching-ciroos-ai-your-ai-sre-teammate)
- [Sumo Logic Root Cause Agent](https://finance.yahoo.com/technology/ai/articles/sumo-logic-expands-dojoai-root-130000197.html)
- [Aurora: AI SRE and incident tool pricing 2026](https://www.aurorasre.ai/blog/ai-sre-incident-tool-pricing-2026)
- [Better Stack: Bits AI SRE alternatives](https://betterstack.com/community/comparisons/bits-ai-sre-alternatives/)
- [Better Stack: incident.io AI SRE alternatives](https://betterstack.com/community/comparisons/incidentio-ai-sre-alternatives/)
- [Ajay Kumar: AIOps in 2026](https://www.ajayk.sh/blog/aiops-2026-incident-response-agents-mttr/)
- [Traversal: ORCA-Bench](https://www.traversal.com/blog/orca-bench-how-ready-are-language-model-agents-for-oncall)
- [Rootly: do AI SRE agents actually work](https://rootly.com/blog/do-ai-sre-agents-actually-work)
- [ClickHouse: can LLMs replace on-call SREs](https://clickhouse.com/blog/llm-observability-challenge)
- [Causely arXiv paper](https://arxiv.org/html/2605.18327v1)
- [Metoro: top 17 AI SRE tools](https://metoro.io/blog/top-ai-sre-tools)
- [Corelayer: best AI SRE tools for RCA](https://www.corelayer.com/guides/best-ai-sre-tools-root-cause-analysis-2026)
- [Metoro: HolmesGPT alternatives](https://metoro.io/comparisons/ai-sre/holmesgpt-alternatives)
- [RunLore](https://pkg.go.dev/github.com/Smana/runlore)
- [neuronfeed: Cleric vs Traversal](https://neuronfeed.com/compare/cleric-vs-traversal)
- [Better Stack: Traversal alternatives](https://betterstack.com/community/comparisons/traversal-alternatives/)
