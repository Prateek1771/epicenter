"""Jev on OpenRouter (`POST /api/alpha/decisions`, LLD §10: 10 s timeout, 1 retry): typed decisions, not text.

- Noul: a yes/no question → P(yes). The jev_gate asks "does the cited evidence support this claim?" per claim.
  The responder asks, per proposed action, "does it address the cause the evidence shows?" and demotes the ones
  that don't. (Jev's Choice type, one key out of options, was dropped: near-equal options flipped between runs.)
Raises `JevUnavailable`; callers keep cited claims as `unverified` / keep history and runbook order.
"""

import json
import logging

from api.ai import openrouter
from api.config import get_settings

log = logging.getLogger("epicenter.ai")

TIMEOUT_S = 10.0
RETRIES = 1


class JevUnavailable(Exception):
    pass


def _decide(state: dict, questions: dict) -> tuple[dict, dict]:
    body = {"model": get_settings().jev_model, "state": state, "questions": questions}
    try:
        data, ms = openrouter.post("/alpha/decisions", body, TIMEOUT_S, RETRIES)
    except openrouter.LLMUnavailable as e:
        raise JevUnavailable(str(e)) from e
    answers = data.get("answers")
    if not isinstance(answers, dict) or set(answers) != set(questions):
        raise JevUnavailable(f"bad response: {str(data)[:200]}")
    usage = data.get("usage") or {}
    call = {
        "model": data.get("model", body["model"]),
        "prompt_tokens": usage.get("input_tokens"),
        "completion_tokens": usage.get("output_tokens"),
        "cost": usage.get("cost"),
        "ms": ms,
    }
    log.info(json.dumps({"event": "jev_call", "questions": len(questions)} | call))
    return answers, call


def noul(state: dict, questions: dict[str, dict]) -> tuple[dict[str, float], dict]:
    """`questions`: name → {instructions, criteria: {true, false}}. Returns name → P(yes) and the call record."""
    answers, call = _decide(state, {k: {"type": "noul"} | q for k, q in questions.items()})
    try:
        return {k: float(a["noul"]) for k, a in answers.items()}, call
    except (KeyError, TypeError, ValueError) as e:
        raise JevUnavailable(f"bad noul answer: {answers}") from e
