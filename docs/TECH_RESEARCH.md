# Technical research: how competitors find root causes

**Researched:** 2026-10-15 · **Purpose:** find one key feature to add to GraphRCA.
Market and pricing view: [COMPETITORS.md](COMPETITORS.md). Result: the **Fault Simulator**
([ADR 0011](adr/0011-fault-simulator.md), [LLD §7](../LLD.md#7-fault-simulator)).

Most sources are the vendors' own blogs or papers, so performance numbers are self-reported. Where a source didn't
describe something, this doc says so rather than guessing.

---

## 1. What each competitor has shared

### Causely: a causal knowledge base plus a "no root cause" answer
Source: Causely white paper, [arXiv 2605.18327](https://arxiv.org/html/2605.18327v1) (written by Causely staff; small benchmark).

- **Four structures:**
  - **topology graph:** entities, plus connectivity, layering and containment relations;
  - **causal knowledge base:** environment-agnostic, maps each entity type's root causes to the symptoms they produce, with *propagation rules* per relation type;
  - **causality graph:** the knowledge base applied to one environment's topology, with P(symptom | cause) on every edge;
  - **attribute dependency graph:** latency depends on queue length, and so on.
- **Inference:** abductive. Pick the root cause r that maximizes P(S⁺ | r)·P(r) over the active symptoms. This is naive-Bayes-style reasoning over the causal graph.
- **Negative answer as a first-class result:** on a healthy cluster, plain agents kept searching (up to 7.2× more tokens than on a faulted one). Adding a typed "no active root cause" answer cut HolmesGPT's false-positive rate from 67% to 0%.
- **Precompute state outside the agent loop:** −63% time to diagnosis, −60% tokens, −78% tool calls in their benchmark.
- **Evidence caveat:** 72 runs, one fault type, a local kind cluster, no confidence intervals.

### Traversal: causal consistency, and why agents fail
Sources: [causal search engine](https://www.traversal.com/blog/introducing-causal-search-engine-from-correlated-alerts-to-causally-consistent-diagnoses),
[ORCA-Bench](https://www.traversal.com/blog/orca-bench-how-ready-are-language-model-agents-for-oncall).

- **Production World Model:** telemetry, code and team knowledge reorganized into an indexed structure covering every service, dependency and behavioural baseline.
- **Causal search:** evaluates "hundreds or thousands" of hypotheses in parallel. It eliminates any hypothesis that isn't consistent with **dependency structure, timing and propagation patterns**, and returns *one* causally consistent diagnosis rather than a ranked list. The blog doesn't say how the constraints are weighted, or what the LLM does versus the algorithms.
- **ORCA-Bench failure modes:**
  - **Symptom anchoring:** agents fixate on the most visible downstream symptom, which is worst in multi-hop incidents.
  - **Hallucination:** the weakest model proposed an implausible root cause in about 40% of runs.
  - **Vague reports:** with an alert like "users report site issues", the best model reached 10% on the hardest tasks.
  - **Source code helps:** removing it cost every frontier model 9–16 points of accuracy.

### Datadog Bits AI SRE: hypothesis tree, scoped steps
Sources: [Building Bits AI SRE](https://www.datadoghq.com/blog/building-bits-ai-sre/), [docs](https://docs.datadoghq.com/bits_ai/bits_ai_sre/investigate_alerts).

- **Hypothesis loop:** form a hypothesis, then run targeted queries to validate or reject it. Hypotheses run in parallel and end as **validated, invalidated or inconclusive**.
- **Recursive sub-hypotheses:** for example "pod out of memory", then "why?", leading to "abnormally large Kafka payloads".
- **Lesson:** the first design made many tool calls and asked an LLM to summarize everything, so prompt size grew with every call. Noisy upstream errors then pushed the summary to the wrong answer even when one call had found the true cause. **Scoping each step to one hypothesis** fixed this.
- **Evaluation:** real incidents labelled by responders, archived telemetry replayed to the agent, and an LLM judge calibrated against human judgments.

### Meta: retrieve, then rank, then abstain
Source: [Meta engineering blog (2024)](https://engineering.fb.com/2024/06/24/data-infrastructure/leveraging-ai-for-efficient-incident-response/).

- **Retrieval:** heuristics (code and directory ownership, the runtime code graph) cut thousands of changes down to a few hundred.
- **Ranking:** Llama 2 7B fine-tuned on about 5,000 past investigations runs an "election". Prompts of up to 20 changes each pick a top 5, repeated until 5 remain.
- **Result:** the true cause is in the top 5 for 42% of investigations.
- **Low-confidence answers are withheld** ("sacrificing reach in favor of precision"), and every candidate comes with an explanation.

### Resolve AI: a big graph behind a safe query language
Source: [Resolve AI knowledge graph blog](https://resolve.ai/blog/knowledge-graph-agentic-ai-incident-response).
- **Graph scale:** about 50,000 nodes and 500,000 edges in enterprise environments; maintained automatically.
- **Safe queries:** agents query it through **"Gragg"**, a custom query language built so the AI can query safely and efficiently.

### Cleric: memory and confidence
Sources: [launch announcement](https://businesswire.com/news/home/20251209625361/en/Cleric-Launches-the-First-Self-Learning-AI-SRE),
[ZenML case study](https://www.zenml.io/llmops-database/ai-powered-sre-agent-for-production-infrastructure-management).
- **Memory and learning:** keeps memory of past investigations and resolutions, and learns from every incident and from human decisions.
- **Confidence:** a confidence score on every output.

### incident.io: evaluating many prompts
Sources: [Lawrence Jones's blog](https://blog.lawrencejones.dev/2025/), [AI Engineer talk](https://ai.engineer/talks/lawrence-jones-fighting-ai-with-ai),
[ZenML summary](https://www.zenml.io/llmops-database/ai-powered-incident-response-system-with-multi-agent-investigation).
- **Prompt evals:** about 50 interacting prompts; changing one silently broke others. The fix was YAML prompt evals kept next to the code as unit tests, plus backtests on past incidents and red-green eval loops.
- **Inputs:** searches GitHub PRs, Slack, past incidents and telemetry, and aims to post findings within 1–2 minutes.

---

## 2. What GraphRCA already matches

| Idea | Who | GraphRCA |
|---|---|---|
| Precomputed state, so the agent doesn't re-fetch telemetry | Causely, Traversal | Ingest builds the graph before agents run ([ADR 0006](adr/0006-operation-level-aggregation.md)) |
| Prune by dependency structure + timing | Traversal | Q1 (upstream) + Q2 (onset order) ([LLD §2.2](../LLD.md#22-causal-search-queries)) |
| Parallel hypotheses with validated / invalidated / inconclusive | Datadog | `supported` / `refuted` / `inconclusive` ([LLD §8](../LLD.md#8-state-machines)) |
| Safe, restricted query surface for agents | Resolve | Typed tools ([ADR 0003](adr/0003-typed-mcp-tools.md)) |
| Memory of past incidents and fixes | Cleric | Q5 + `RESOLVED_BY` ([ADR 0008](adr/0008-deterministic-incident-signature.md)) |
| Confidence on every answer | Cleric, Meta | Score-margin confidence ([LLD §6](../LLD.md#6-scoring-searchscorepy)) |

## 3. What was missing, and the feature that fills it

| Gap in our design | Who shows it matters | Fix |
|---|---|---|
| We check that a cause is **upstream and earlier**, but not that it **explains the whole pattern** of symptoms | Traversal (propagation patterns), Causely (P(S \| r)), ORCA-Bench (symptom anchoring) | **Fault Simulator**: predict the footprint, compare with what we observed |
| We always name a cause, even when nothing explains the alert | Causely (67% → 0% false positives) | Typed `no_root_cause` answer |
| One root cause per incident | Datadog (multi-component failures) | Unexplained symptoms seed a second search |
| Blast radius = reachability only | Traversal glossary (blast radius from graph + traffic + changes) | Same simulator, run as "what if X fails?" |

**Chosen:** the Fault Simulator ([ADR 0011](adr/0011-fault-simulator.md)). One deterministic, graph-native mechanism closes all four gaps.

## 4. Considered and not adopted (yet)

| Idea | Why not now |
|---|---|
| Recursive sub-hypotheses (Datadog) | Already shipped by Datadog; our skeptic + second-cause search cover the common case. Revisit after the hackathon |
| LLM election ranking over code changes (Meta) | Needs a rich change / PR feed and a fine-tuned model; breaks our "LLM never ranks" rule ([ADR 0002](adr/0002-deterministic-ingestion-and-scoring.md)) |
| Full Bayesian codebook (Causely) | Needs per-type symptom probabilities we can't calibrate in time; our rule propagation is the simpler first step towards it |
| LLM-as-judge eval calibrated to humans (Datadog) | Our verdicts are deterministic and labelled by RCAEval; use it later for the narrator only |
| YAML prompt evals (incident.io) | Worth adopting for the narrator / skeptic prompts during the build |
