---
title: The loudest service is usually innocent. How we built a graph-based root-cause finder on FalkorDB
published: false
description: Epicenter keeps a production system in a FalkorDB graph, walks upstream from an alert, and checks every suspect by asking what it would have broken. 87.8% top-1 on RCAEval RE2-TT.
tags: ai, sre, devops, database
cover_image: https://raw.githubusercontent.com/Prateek1771/epicenter/main/docs/blog/cover.jpg
---

**TL;DR.** When production breaks, the loudest service is usually a victim. Epicenter keeps a live call graph in [FalkorDB](https://www.falkordb.com/), searches upstream from the alert, and runs a Fault Simulator on every suspect: "if this were the cause, what would we see?" A deterministic scorer, never an LLM, picks the root cause. On the RCAEval RE2-TT benchmark it gets 87.8% top-1 overall and 90.0% on held-out cases. It's open source, and there's a [live demo](https://epicenter.13-204-211-105.sslip.io).

It's 3 a.m. and checkout is down. You open the dashboards and half of them are red. The payment service is throwing errors, the cart is timing out, the frontend's latency graph looks like a cliff. Which one started it?

Most of the time the answer is none of the red ones. A database three hops back got slow, and everything in front of it started failing. The service that failed loudest is the victim. The one that started it is often quiet, because it isn't throwing errors. It's just slow, and everyone upstream is paying for it.

We spent a hackathon building a tool that gets this right more often than it gets it wrong, and that tells you when it doesn't know. This post covers how it works, what the benchmark says, and the parts that didn't go the way we planned.

## Why AI agents miss it

There's a wave of "AI SRE" products right now. Most of them hand an LLM your logs and metrics and ask it what broke. That works sometimes. The published numbers are rough, though. ORCA-bench, a 2026 benchmark of 884 on-call tasks, found the best model reached 30.9% when it had to name every root cause ([ORCA-bench](https://arxiv.org/pdf/2607.28545)). A Waterloo study that ran 48,000 simulated failures across six models found accuracy stayed low, and that adding more agent steps often made errors worse ([Riddell, 2026](https://uwspace.uwaterloo.ca/items/2a455ecf-a18d-40a3-8cdb-6fa67e7a67c3/full)). The same study calls out the core difficulty. In a multi-hop failure, the symptoms show up far from the cause.

An LLM reading a wall of red reaches for the reddest thing. That's the failure we wanted to design against.

So we made one rule early and never broke it. **The LLM never ranks suspects.** It writes the explanation at the end, and it drafts proposed actions. A deterministic scorer picks the root cause, from features computed on a graph. Same input, same answer, byte for byte. If every LLM provider is down, you still get a verdict.

## The graph is the system of record

![The service map: client, edge, api, svc and two datastores, with traffic on every edge](https://raw.githubusercontent.com/Prateek1771/epicenter/main/docs/blog/map.jpg)

Epicenter keeps one FalkorDB graph per environment. Every 30 seconds it rolls traces up into a call graph:

```
(:Service)-[:HAS_OP]->(:Operation)-[:CALLS {rps, err_rate, p95_ms}]->(:Operation)
(:Change)-[:CHANGED]->(:Service)
(:Service)-[:OWNED_BY]->(:Team)
```

We aggregate at the operation level, not the span level. Raw spans never enter the graph. Each anomaly keeps a reference back to its source, so the graph stays small enough that a 6-hop traversal is cheap. Deploys, flag flips and config changes go in as `Change` nodes when they happen, because "what changed right before it broke?" is the oldest question in incident response, and it should be one hop away.

When an alert fires, the incident goes into the same graph:

```
(:Incident)-[:HAS_HYPOTHESIS]->(:Hypothesis)-[:BLAMES]->(:Operation)
(:Hypothesis)-[:SUPPORTED_BY|REFUTED_BY]->(:Evidence)
(:Anomaly)-[:ON]->(:Operation)
```

We picked FalkorDB because it stores graphs as sparse adjacency matrices and runs queries as GraphBLAS linear algebra ([FalkorDB design docs](https://docs.falkordb.com/design)). Bounded variable-length paths are what we do all day, and they're fast there. It also has a vector index in the same engine, which mattered for incident memory. We didn't want a second database just to store embeddings.

Every query the product runs lives in one Python dictionary, `QUERIES` in `api/graph.py`. Nothing else in the codebase talks to FalkorDB, every query is parameterized, and every traversal stops at 6 hops. That sounds bureaucratic. It paid for itself the first time a query got slow, because there was exactly one place to look.

## How a diagnosis runs

1. **Suspects.** Query Q1 walks upstream from the alerting operation, up to 6 `CALLS` hops, and returns every operation that has an anomaly in this incident window. Those are the suspects.
2. **Evidence.** For each suspect, Q2 pulls the path back to the alert with each hop's onset time, and Q3 pulls the suspect's own anomalies and any change on its service just before onset. Did it go bad first? Is it slow by itself, or is it waiting on something below it? For a datastore, we look at its callers' wait time instead.
3. **Centrality.** Q4 builds a "blame" projection of the anomalous call graph in a scratch graph, `scratch:<incident>`, and runs `algo.pageRank` on it. The scratch graph is deleted when the diagnosis ends.
4. **Simulation.** The Fault Simulator, below, which is the part we care most about.
5. **Score.** Six features, fixed weights from a versioned `weights.json`, ties broken on id.

Four agents run this, built on LangGraph. Triage turns the suspects into hypotheses. One investigator per hypothesis runs in parallel, gathering evidence and running the Fault Simulator. A skeptic challenges the provisional winner by asking what it doesn't explain. After the verdict is out, a historian looks up similar past incidents, so memory never slows the diagnosis. None of their decisions come from a model. They don't pass content to each other. Agent state holds ids only, and everything they find goes into the incident subgraph. When the skeptic wants to know what the investigator found, it reads the graph. This made the agents easy to debug, because you can open the FalkorDB browser mid-incident and see exactly what each one wrote.

## The Fault Simulator

![An incident page: the verdict card on the left with its score breakdown, the causal path on the canvas, and timeline lanes underneath](https://raw.githubusercontent.com/Prateek1771/epicenter/main/docs/blog/verdict.jpg)

Upstream search tells you a suspect is in the right place. Onset times tell you it went bad early. Neither tells you whether it explains *the whole pattern* of what broke.

So for every suspect, Epicenter asks "if this were the cause, what would we expect to see?"

It takes a small set of propagation rules, stored in their own graph, `kb:propagation`. A callee's errors become its callers' errors with probability 0.8. A slow callee makes its callers slow. A dead datastore takes down everything that reads from it. The simulator applies those rules hop by hop along the `CALLS` edges that actually carried traffic in the window, weighted by traffic share. Out comes a predicted footprint: which operations should break, how, and in what order.

Then it compares the prediction with what really broke and scores the match. The UI says it in plain words, "explains 5 of 9 symptoms, precision 0.73."

This is what catches the loud victim. If the payment service were the real cause, it would predict errors upstream of itself, toward the frontend. It wouldn't predict the slow database calls *below* it. Its coverage stays low and it gets refuted, with a reason you can read. The quiet database predicts the whole cascade.

The same check gives us two answers most tools can't produce:

- **"No root cause."** If nothing explains at least half of the symptoms and the anomalies are weak, the incident ends as `no_root_cause`. Our synthetic suite has a healthy system in every size, and the right answer there is to name nobody.
- **A second fault.** Symptoms the winner doesn't explain seed one more search. If two things broke at once, you hear about both.

The simulator also works without an incident. The What-if page breaks any service six ways (down, errors, latency, CPU, memory, saturation) and shows who gets hit and when, plus whether that pattern matches a past incident. It's meant for the question you should ask before a risky deploy.

![The What-if lab: svc-0 broken six ways, the predicted spread on the graph, a spread timeline and a match against a past incident](https://raw.githubusercontent.com/Prateek1771/epicenter/main/docs/blog/what-if.jpg)

## What the benchmark says

We tested on RCAEval, a public benchmark for microservice root-cause analysis ([Pham et al.](https://arxiv.org/pdf/2412.17015)). Its RE2 dataset has real injected faults in three systems with metrics, logs and traces, across four resource fault types and two network fault types. We used the 90 Train Ticket cases (RE2-TT).

To keep ourselves honest, we tuned weights on repetitions 1 and 2 only and held out repetition 3. We never tuned on those 30 cases.

| | AC@1 |
|---|---|
| All 90 cases | 87.8% |
| Held-out 30 cases | 90.0% |
| Dev 60 cases | 86.7% |

AC@3 on all 90 is 88.9%. Per fault type, CPU and delay faults hit 100%, socket 93%, disk 87%, and packet loss and memory both 73%. Loss and memory are where we'd dig next. The per-case drill-down on `/eval` shows where each miss pointed.

Median diagnosis time is 314 ms once the data is in the graph. Alert to verdict, including ingesting the replayed telemetry, is 20.2 s at p95.

A caveat, so nobody has to find it for us. RE2-TT is one system with single faults. We also built a synthetic suite at three sizes (5, 30 and 300 services) with known answers, including loud-victim traps, two simultaneous faults and healthy systems. Accuracy drops as the graph grows. Top-1 is 100% at 5 services, 78% at 30, 56% at 300. Top-3 holds better, at 100%, 100% and 67%. We haven't cracked the large graphs yet. The `/eval` page shows all of this, misses included, with a per-case drill-down.

![The /eval page: 87.8% top-1 overall, 90.0% held-out, run history and ablations](https://raw.githubusercontent.com/Prateek1771/epicenter/main/docs/blog/eval.jpg)

## The ablation table that surprised us

We expected the Fault Simulator to be the star of the scoring. The ablation table disagreed.

| Feature switched off | AC@1 change |
|---|---|
| PageRank on the blame graph | −11.1 points |
| Footprint (Fault Simulator) | −4.4 |
| Mechanism fit | −4.4 |
| Onset earliness ("went bad first") | **+4.4** |

PageRank on the per-incident blame graph carries the most weight. The simulator's footprint helps, but less than we hoped. Our guess is that RE2-TT faults are single and strong enough that centrality alone finds most of them.

The onset feature went the other way, and that one stung. "Went bad first" is the most intuitive signal in root cause analysis. Our best explanation is that metrics on this benchmark are sampled at intervals, so the cause and its first victim often land in the same time bucket, or in the wrong order. Turning the feature off made accuracy better. So its weight in `weights.json` is zero, and the `/eval` page shows the bar going the "wrong" way with a note under it. We could have hidden it. We think a root-cause tool that hides its own failures is a bad sign.

The footprint score still earns its place, mostly in places a top-1 number doesn't reach. It's what produces "no root cause" on healthy systems and refutes loud victims in the synthetic traps. And it gives a human a reason they can check.

## Memory

Every resolved incident gets a 64-dimension signature, computed deterministically from the shape of the incident (which kinds of anomalies, on which kinds of operations, how they spread). No embeddings model and no randomness. It goes into a FalkorDB vector index, linked to the action that fixed it.

When a new incident comes in, query Q5 finds the closest resolved ones and shows their fixes next to the verdict. P@3 is 12.2% on RE2-TT, which is low. One likely reason is that faults of the same type look alike across Train Ticket services, so the nearest match is often the same kind of fault on a different service. It's useful as a hint ("last time a disk fault looked like this, someone cleared the log volume") and not as an answer.

## Acting, carefully

Epicenter proposes actions and doesn't run them. Each verdict comes with a ranked list built from the graph: the runbook for that service and fault kind, plus the fixes that resolved similar past incidents. You can send it to Slack or Linear, or download `incident_info.md` for a person, or an agent context file for Claude Code, Codex or Cursor.

It's read-only towards the systems it watches, on purpose. A root-cause tool that restarts services on a wrong guess turns one outage into two.

The LLM, when it's configured, writes the explanation and cites the evidence. We run a claim check over its output and drop any sentence the evidence doesn't support. The scorer never reads what the LLM wrote.

## Things we'd do differently

- **We wrote the design down before the code.** Fourteen ADRs sounds like too much for a hackathon. It wasn't. Each one forced us to write what we'd lose, like ADR 0004, where we chose not to use Graphiti for agent memory because the graph we already had could hold it.
- **Determinism is a pain, and worth it.** No Python `hash()` for features, sort every input by key, tie-break on id. It also meant that when accuracy moved, we knew it was the weights and not the dice.
- **Synthetic data with known answers is underrated.** RCAEval tells you how you do on real faults. The synthetic suite tells you *why* you fail, because you control the trap. The loud-victim trap is in every size of the suite for that reason.
- **Big graphs need more than local evidence.** At 300 services our accuracy falls off. The next thing we'd try is making the simulator's rules probabilistic per service type, closer to a Bayesian codebook, using the RCAEval traces to fit them.

## Try it

{% github Prateek1771/epicenter %}

The live demo has one example incident ready, a CPU fault on `svc-0` in a small synthetic system. Open it and you'll see the verdict, the path from the alert back to the cause, and the 11 suspects that were ruled out with reasons. Then go to **Runs** and start a loud-victim case, or one of the RCAEval replays, which download about 25 MB of real recorded telemetry the first time. A short tour runs on your first visit, and the **?** button replays it.

To run it yourself, clone the repo, copy `.env.example`, set two passwords and `docker compose up -d`. The 26 synthetic incidents ship with the repo, so nothing has to download.

We built Epicenter for Graph Hacks, FalkorDB's hackathon, in the "Agents that act on connected data" track. We used AI coding assistants to write a lot of the code and docs. We made the design calls, reviewed the changes, and ran every number in this post ourselves.

The loudest service is usually innocent. It's nice to have a tool that can prove it.
