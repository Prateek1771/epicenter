# Phase 7: Memory, LLM explanation, delivery

**Goal:** the verdict gets a memory ("seen before, fixed by …"), a human-readable explanation where every claim cites
evidence and unsupported claims are dropped, proposed actions ranked by past success, delivery to Slack / Linear, and
the ask box. Everything here is optional to the verdict: with every LLM down, the verdict is unchanged.

**Depends on:** phases 5, 6. **Unblocks:** 8 (memory / explanation panels), 10.

## Spec

- [ADR 0008](../adr/0008-deterministic-incident-signature.md) signature layout, [LLD §2.2 Q5](../LLD.md#22-causal-search-queries), [HLD §3.3 memory recall](../HLD.md#33-memory-recall)
- [LLD §5.3 agent contracts](../LLD.md#53-agent-contracts) (historian, narrator, jev_gate, responder) and the narrator prompt contract
- [HLD §3.2 ask box](../HLD.md#32-ask-box), [ADR 0003](../adr/0003-typed-mcp-tools.md) read-only `falkordb-mcp` fallback
- [API.md](../API.md): `POST /incidents/{id}/deliver`, `POST /ask`; [LLD §10](../LLD.md#10-external-calls-timeouts-and-retries) timeouts
- [USER_FLOW Flow 4 and 5](../USER_FLOW.md)

## Files

```
api/search/signature.py    64-dim deterministic signature
api/agents/historian.py  narrator.py  responder.py  ask.py
api/ai/openrouter.py       chat client (timeout 20 s, 1 retry, pinned model, temperature 0)
api/ai/jev.py              Noul (support_p) + Choice clients (timeout 10 s, 1 retry)
api/deliver/openconnector.py
api/routes/deliver.py  ask.py
tests/test_signature.py  tests/test_narrator_contract.py
```

## Tasks

- [ ] `signature(incident)`: dims exactly as ADR 0008, L2-normalized, deterministic feature hashing for log templates (fixed hash, not Python `hash()`).
- [ ] historian: write `Incident.signature`, run Q5, re-rank by graph overlap (same root-cause op or change type), write `SIMILAR_TO {score}`; emit `memory.similar`.
- [ ] narrator: input = verdict + evidence as JSON **data**; output JSON `{what, where, why}` of `{text, cites}`; validate against a JSON schema; drop claims citing ids not in the input. Template explanation from `score_parts` when OpenRouter fails.
- [ ] jev_gate: per claim + its cited evidence → `support_p`; drop `< 0.7` or uncited; Jev down → keep cited claims marked `unverified`. Write `Explanation {claims, dropped, verified, ai_calls}`; emit `explanation`.
- [ ] responder: candidate steps from `Runbook` for the root-cause kind, ordered by past `RESOLVED_BY` success; Jev Choice picks among them (bounded options only); `Action {status:'proposed'}`; `no_root_cause` → "check the alert threshold".
- [ ] `POST /deliver`: OpenConnector Slack card + Linear issue; per-target result; failure → `Action.delivery = failed`, retry from the UI.
- [ ] `POST /ask`: ask agent with typed tools first, `falkordb-mcp` `query_graph_readonly` fallback (Bearer `MCP_API_KEY`); return `answer`, `path` ids, `tools_used`, `cypher` when the fallback was used.
- [ ] Record model id, tokens, latency per LLM call in `Explanation.ai_calls` ([HLD §10](../HLD.md#10-observability-of-epicenter-itself)).
- [ ] Prompt-injection guard: log text and evidence go to the LLM inside clearly delimited data fields; LLM output is written only to `Explanation` / `Action` and never read by the scorer ([HLD §9](../HLD.md#9-security)).
- [ ] Prompt evals: YAML cases next to the narrator / skeptic prompts, run in pytest ([TECH_RESEARCH §4](../TECH_RESEARCH.md#4-considered-and-not-adopted-yet)).

## Acceptance

- LLD §12 "agent contract": narrator output validates against the schema; an uncited claim is dropped.
- Signature of the same incident computed twice is identical; leave-one-out precision@3 on RCAEval is reported in phase 10.
- With `OPENROUTER_API_KEY` unset: verdict identical, explanation is the template, badge "AI explanation unavailable".
- Resolving an incident with action `a-1` then replaying the same fault ranks that action first (Flow 5).
- Ask: "who should I page for checkout?" uses `who_knows` and returns a path; an open question returns the Cypher it ran.

## Scalability

- **LLM calls only after the verdict, in parallel per claim.** Diagnosis latency never depends on LLM latency (N1, N7).
- **Deterministic signature + vector index** makes recall O(index lookup) and free; no embedding API to rate-limit.
- **External clients behind thin modules** (`ai/`, `deliver/`) with timeouts and retries from config. Swapping OpenRouter for another provider, or OpenConnector for direct Slack, is one module.
- **Bounded LLM choices** (Jev Choice over runbook steps) keep cost and output size fixed per incident.
- Ceiling: LLM calls are synchronous per incident. Under many concurrent incidents add a concurrency limit (semaphore from config) rather than a queue.

## Risks / open questions

- Jev model availability on OpenRouter: confirm the pinned id at kickoff.
- OpenConnector self-host image and action names: confirm against its repo; delivery is optional for the demo.

## Done when

An incident shows memory, a cited and verified explanation, ranked actions, and can be delivered; all of it degrades cleanly with LLMs off.
