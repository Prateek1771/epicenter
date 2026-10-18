# Demo script (3 minutes + 2 minutes of explanation)

One path through the product, built around the thing only Epicenter does: the Fault Simulator **refuting** a
plausible suspect. Everything else (Slack, eval, the live shop) is for follow-up questions.

**Before recording:**
- `docker compose up -d`, and open http://localhost:3001 in a 1440 px window.
- Optional: `OPENROUTER_API_KEY` set, so the explanation is AI-written. Without it the template explanation is shown;
  say so.
- For step 5 only: the OTel Demo has been up for at least 25 minutes (`python examples/otel-demo/run.py status`).

## The recording

| # | Time | Do | Say |
|---|---|---|---|
| 1 | 0:00 | Landing page, scroll once | "When production breaks, the loudest service is rarely the cause. Epicenter keeps a live FalkorDB graph of the system and finds where the failure started." |
| 2 | 0:20 | `/runs` → *Demo 1 · Synthetic* → `loud-victim` → **Run** | "A generated system with a known answer: a datastore slows down, and the service in front of it fails loudly." |
| 3 | 0:35 | The incident page opens. Point at the canvas: alert → path → root cause | "From the alert, it walks the call graph upstream in FalkorDB, at most six hops, and every operation that misbehaved becomes a suspect." |
| 4 | 1:00 | Right panel → **Suspects**: `svc-0` refuted, `mongodb/find` confirmed | "The loud one, svc-0, is refuted. The Fault Simulator asked: if svc-0 were the cause, what would we see? Its predicted footprint doesn't match what broke. `mongodb/find` explains the symptoms, so it wins at 99.5%." |
| 5 | 1:40 | Verdict card: score parts, path, evidence; then **AGENTS.md** download | "The ranking is a deterministic score with versioned weights, never the LLM. The same input gives the same answer, byte for byte. The answer is a graph path you can check, and it exports as a context file for a coding agent." |
| 6 | 2:10 | (If warm) `/runs` → OTel Demo → `paymentFailure` → wait for the alert | "Now a real microservice shop, a live feature-flag fault: it finds `payment/Charge` and the flag change just before it." |
| 7 | 2:40 | `/simulate` → `payment` → **Run experiment** → "Did it happen before?" | "The same simulator answers what-ifs before you ship, and checks them against past incidents." |
| 8 | 2:55 | `/eval` | "Measured on the public RCAEval benchmark: 87.8% top-1, 90% on the held-out cases." |

If the live shop isn't warm, skip step 6. Steps 1–5 are the demo.

## The 2-minute explanation (graph model, queries, architecture)

1. **Model:**
   - services own operations, and operations `CALLS` each other with rps, error rate and p95 rolled up from traces;
   - changes, owners and runbooks hang off services;
   - an incident's hypotheses `BLAME` operations and are `SUPPORTED_BY` / `REFUTED_BY` evidence.

   One graph per environment. ([GRAPH_SCHEMA](GRAPH_SCHEMA.md))
2. **Queries** ([README](../README.md#graph-model-and-queries), [LLD §2](LLD.md#2-graphpy)):
   - Q1 finds suspects with a bounded variable-length `CALLS` walk;
   - Q2 and Q3 get each suspect's path, onsets, self-time and recent changes;
   - Q4 runs `algo.pageRank` on a blame projection in a scratch graph;
   - Q6 gives the simulator its caller paths;
   - Q5 is the vector index over incident signatures for memory.
3. **Architecture:**
   - FastAPI and LangGraph agents (triage, investigator, skeptic, historian) share state through the graph, holding
     ids only;
   - only `api/graph.py` talks to FalkorDB, with parameterized Cypher;
   - the LLM writes explanations and proposed actions only, and is never read by the scorer.

   ([ARCHITECTURE](ARCHITECTURE.md))
