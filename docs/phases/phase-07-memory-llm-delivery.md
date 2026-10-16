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
api/agents/historian.py  narrator.py  responder.py  ask.py   prompts/narrator.md  prompts/ask.md
api/ai/openrouter.py       chat client: GPT-4o snapshot (timeout 20 s, 1 retry, temperature 0, seed 0)
api/ai/jev.py              Noul client: claim support + action relevance (timeout 10 s, 1 retry)
api/agents/calibrate.py    Jev cutoff calibration CLI (labelled claims → recommended min_support)
api/deliver/openconnector.py
api/tools/falkordb_mcp.py  allowlisted read-only client for the ask fallback
api/routes/deliver.py  ask.py
tests/test_signature.py  test_narrator_contract.py  test_memory.py  test_deliver.py  test_ask.py
tests/test_prompt_evals.py + prompt_evals/narrator.yaml   (live, opt-in: EPICENTER_LIVE=1)
tests/fakes.py             fake OpenRouter / Jev / OpenConnector / falkordb-mcp (httpx.MockTransport)
```

## Tasks

- [x] `signature(incident)`: dims exactly as ADR 0008, L2-normalized, deterministic feature hashing for log templates (fixed hash, not Python `hash()`).
- [x] historian: write `Incident.signature`, run Q5, re-rank by graph overlap (same root-cause op or change type), write `SIMILAR_TO {score}`; emit `memory.similar`.
- [x] narrator: input = verdict + evidence as JSON **data**; output JSON `{what, where, why}` of `{text, cites}`; validate against a JSON schema; drop claims citing ids not in the input. Template explanation from `score_parts` when OpenRouter fails.
- [x] jev_gate: per claim + its cited evidence → `support_p`; drop `< 0.7` or uncited; Jev down → keep cited claims marked `unverified`. (Cutoff calibrated to 0.65, see Results.) Write `Explanation {claims, dropped, verified, ai_calls}`; emit `explanation`.
- [x] responder: candidate steps from `Runbook` for the root-cause kind, ordered by past `RESOLVED_BY` success; Jev demotes the ones that don't address the cause (Noul per action; replaced the planned Choice, see Results); `Action {status:'proposed'}`; `no_root_cause` → "check the alert threshold".
- [x] `POST /deliver`: OpenConnector Slack card + Linear issue; per-target result; failure → `Action.delivery = failed`, retry from the UI.
- [x] `POST /ask`: ask agent with typed tools first, `falkordb-mcp` `query_graph_readonly` fallback (Bearer `MCP_API_KEY`); return `answer`, `path` ids, `tools_used`, `cypher` when the fallback was used.
- [x] Record model id, tokens, latency per LLM call in `Explanation.ai_calls` ([HLD §10](../HLD.md#10-observability-of-epicenter-itself)).
- [x] Prompt-injection guard: log text and evidence go to the LLM inside clearly delimited data fields; LLM output is written only to `Explanation` / `Action` and never read by the scorer ([HLD §9](../HLD.md#9-security)).
- [x] Prompt evals: YAML cases next to the narrator / skeptic prompts, run in pytest ([TECH_RESEARCH §4](../TECH_RESEARCH.md#4-considered-and-not-adopted-yet)).

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
- **Bounded LLM decisions** (one Jev Noul per claim / per runbook step, never free text) keep cost and output size
  fixed per incident.
- Ceiling: LLM calls are synchronous per incident. Under many concurrent incidents add a concurrency limit (semaphore from config) rather than a queue.

## Risks / open questions

- ~~Jev model availability~~ **Confirmed:** `typesafe/jev-1.13` answers on OpenRouter `POST /api/alpha/decisions`
  (Noul → `answers.<q>.noul`, Choice → `choice` + `probabilities`); `jev-1.14` / `~typesafe/jev-latest` also exist.
- ~~OpenConnector action names~~ **Confirmed** on the running v1.9.0: `slack.post_message`,
  `slack.get_message_permalink`, `linear.create_linear_issue`. Real posting needs Slack / Linear connected in
  OpenConnector and `SLACK_CHANNEL` / `LINEAR_TEAM_ID` set.
- ~~Jev threshold~~ **Calibrated (Q-g):** `python -m api.agents.calibrate` → `min_support` 0.65 (was 0.7). See
  Results; phase 10 reruns the calibration on the full RE2 suite.
- The skeptic LLM hook noted in phase 5 is not built: every skeptic check runs and is deterministic, so a model
  choosing their order can't change the verdict.
- Found while building: Docker Compose's `env_file` passes `KEY=   # comment` as the value `# comment`; `.env.example`
  moved its comments to their own lines and `config.py` treats `#…` values as unset.

## Done when

An incident shows memory, a cited and verified explanation, ranked actions, and can be delivered; all of it degrades cleanly with LLMs off.

## Results (2026-10-16)

- Offline suite: 142 passed (+2 live evals skipped by default). Contract: an uncited claim and a claim citing `E99`
  are dropped and counted; invalid output and no key → template; Jev `0.41` dropped / `0.93` kept; Jev down →
  `unverified`; the full flow with GPT-4o + Jev answering gives the same verdict as the sequential path.
- Flow 5 (`test_memory.py`): resolve inc-1 with "Turn the flag off", replay the same fault as inc-2 → memory lists
  inc-1 first (identical signature), and "Turn the flag off" ranks first (`chosen_by: history`).
- Live (real GPT-4o `openai/gpt-4o-2024-11-20` + Jev `typesafe/jev-1.13-20260917`), 3 RE2-TT cases through the API:
  explanations with `source: llm`, every kept claim cites real evidence, `ai_calls` records model / tokens / ms
  (narrator ~1.6k prompt tokens, ~2–4 s; Jev ~1.1k tokens, ~0.5–0.9 s, ~$0.00004). Verdict and `score_parts`
  byte-identical with the LLM on and off. Prompt evals: 5 consecutive live runs green.
- Ask (live): "who should I page for payment?" → `who_knows`; "which operation has the most callers?" →
  `graph_schema` + `cypher_readonly` (Cypher returned); "how was inc-0 fixed?" → `incident_summary` (tool added after
  GPT-4o misread `similar_incidents` for that question).
- Deliver (live OpenConnector, nothing connected): per-target `UPSTREAM_ERROR` ("Configure slack credentials first",
  "LINEAR_TEAM_ID not set"), recorded on the incident, status stays `diagnosed`.

### Quality follow-up (2026-10-16)

- **Jev cutoff calibrated.** A first 10-claim probe suggested ~0.3. The calibration set (3 RE2-TT cases +
  mini_graph: 48 TRUE claims built from the engine's own evidence, 96 FALSE perturbations, 2 passes, $0.003) said
  otherwise: at 0.3, 12 false claims pass. It also found a gate gap: footprint evidence ("explains 1 of 15 symptoms")
  didn't name its operation, so a claim about the wrong operation couldn't be refuted; each evidence item now carries
  its operation for GPT-4o and Jev. After that fix: no false accept from 0.60; `min_support` = **0.65** keeps 38% of
  true claims (26% at 0.7). Report: [docs/calibration/jev-2026-10-16.json](../calibration/jev-2026-10-16.json).
  Jev's separation on RE2-TT's long operation names is the limit (true claims as low as 0.18, false up to 0.57);
  the template fill keeps the headline and the change in every explanation regardless.
- **Action ranking.** Jev Choice was replaced by a Noul per action ("does it address the cause shown in the
  evidence?"), with the root cause's supporting evidence in the state. Unrelated actions go last (`demoted`);
  history and runbook order stay deterministic. Probe that motivated it: without evidence, Choice put
  "Restart payment" first for a flag fault; with evidence it dropped to 0.05 but the two flag steps tied and the pick
  flipped between runs. The Noul relevance is stable between runs but not much smarter: live on mini_graph it scored
  "Turn the flag off" 0.31–0.35 and "Restart payment" 0.73. So `actions.min_relevance` is 0.15: Jev only demotes
  clearly unrelated actions, and the order that matters comes from history (what fixed it before) and the runbook.
  Better action ranking needs labelled data (phase 10) or runbook steps tagged with the change types they address.
