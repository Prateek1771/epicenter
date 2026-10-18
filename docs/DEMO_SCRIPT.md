# Demo script (3 minutes + 2 minutes of explanation)

This is one path through the product. We built it around the thing only Epicenter does, which is the Fault Simulator
**refuting** a plausible suspect. Slack, the eval and the live shop are there for follow-up questions.

Before recording:
- run `docker compose up -d`, and open http://localhost:3001 in a 1440 px window;
- optionally set `OPENROUTER_API_KEY` so the AI writes the explanation. Without it you get the template explanation,
  so say so;
- for step 6 only, make sure the OTel Demo has been up for at least 25 minutes (`python examples/otel-demo/run.py status`).

## The recording

| # | Time | Do | Say |
|---|---|---|---|
| 1 | 0:00 | Landing page, scroll once | "When production breaks, the loudest service is rarely the cause. Epicenter keeps a live FalkorDB graph of the system and finds where the failure started." |
| 2 | 0:20 | `/runs` → *Demo 1 · Synthetic* → `loud-victim` → **Run** | "This is a generated system with a known answer. A datastore slows down, and the service in front of it fails loudly." |
| 3 | 0:35 | The incident page opens. Point at the canvas: alert → path → root cause | "From the alert, it walks the call graph upstream in FalkorDB, at most six hops. Every operation that misbehaved becomes a suspect." |
| 4 | 1:00 | Right panel → **Suspects**: `svc-0` refuted, `mongodb/find` confirmed | "The loud one, svc-0, is refuted. The Fault Simulator asked what we would see if svc-0 were the cause, and its predicted footprint doesn't match what broke. `mongodb/find` explains the symptoms, so it wins at 99.5%." |
| 5 | 1:40 | Verdict card: score parts, path, evidence. Then the **AGENTS.md** download | "A deterministic score with versioned weights does the ranking, never the LLM. The same input gives the same answer, byte for byte. The answer is a graph path you can check, and it exports as a context file for a coding agent." |
| 6 | 2:10 | (If warm) `/runs` → OTel Demo → `paymentFailure` → wait for the alert | "Now a real microservice shop with a live feature-flag fault. It finds `payment/Charge` and the flag change just before it." |
| 7 | 2:40 | `/simulate` → `payment` → **Run experiment** → "Did it happen before?" | "The same simulator answers what-ifs before you ship, and checks them against past incidents." |
| 8 | 2:55 | `/eval` | "On the public RCAEval benchmark we measured 87.8% top-1, and 90% on the held-out cases." |

If the live shop isn't warm, skip step 6. Steps 1–5 are the demo.

## The 2-minute explanation (graph model, queries, architecture)

1. The model.
   - Services own operations, and operations `CALLS` each other with rps, error rate and p95 rolled up from traces.
   - Changes, owners and runbooks hang off services.
   - An incident's hypotheses `BLAME` operations and are `SUPPORTED_BY` / `REFUTED_BY` evidence.

   We keep one graph per environment. ([GRAPH_SCHEMA](GRAPH_SCHEMA.md))
2. The queries ([README](../README.md#graph-model-and-queries), [LLD §2](LLD.md#2-graphpy)).
   - Q1 finds suspects with a bounded variable-length `CALLS` walk.
   - Q2 and Q3 get each suspect's path, onsets, self-time and recent changes.
   - Q4 runs `algo.pageRank` on a blame projection in a scratch graph.
   - Q6 gives the simulator its caller paths.
   - Q5 is the vector index over incident signatures, used for memory.
3. The architecture.
   - FastAPI and LangGraph agents (triage, investigator, skeptic, historian) share state through the graph and hold
     ids only.
   - Only `api/graph.py` talks to FalkorDB, and only with parameterized Cypher.
   - The LLM writes explanations and proposed actions only. The scorer never reads them.

   ([ARCHITECTURE](ARCHITECTURE.md))
