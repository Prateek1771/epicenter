"""OpenRouter chat client (LLD §10: 20 s timeout, 1 retry). Pinned model (GPT-4o snapshot), temperature 0.

Only the narrator and the ask agent use it, both after the verdict exists; nothing here is read by the scorer (rule 4).
Raises `LLMUnavailable` when there is no key or the call fails twice; callers fall back (template, 502).
"""

import json
import logging
import time
from dataclasses import dataclass, field

import httpx

from api.config import get_settings

log = logging.getLogger("epicenter.ai")

TIMEOUT_S = 20.0
RETRIES = 1
_transport: httpx.BaseTransport | None = None  # tests swap in an httpx.MockTransport


class LLMUnavailable(Exception):
    pass


@dataclass
class ChatResult:
    content: str | None
    tool_calls: list[dict] = field(default_factory=list)
    message: dict = field(default_factory=dict)  # the raw assistant message, to append in a tool loop
    call: dict = field(default_factory=dict)  # model, tokens, ms → Explanation.ai_calls


def post(path: str, body: dict, timeout_s: float, retries: int) -> tuple[dict, float]:
    """POST to OpenRouter with the key; returns (json, ms). Shared with the Jev client."""
    s = get_settings()
    if not s.openrouter_api_key:
        raise LLMUnavailable("OPENROUTER_API_KEY not set")
    headers = {"Authorization": f"Bearer {s.openrouter_api_key}", "X-Title": "Epicenter"}
    last: Exception | None = None
    for _ in range(1 + retries):
        t0 = time.perf_counter()
        try:
            with httpx.Client(transport=_transport, timeout=timeout_s) as c:
                r = c.post(f"{s.openrouter_url.rstrip('/')}{path}", json=body, headers=headers)
            r.raise_for_status()
            return r.json(), round((time.perf_counter() - t0) * 1000, 1)
        except (httpx.HTTPError, ValueError) as e:
            last = e
    raise LLMUnavailable(f"{path}: {last}") from last


def chat(
    messages: list[dict], *, schema: dict | None = None, tools: list[dict] | None = None, max_tokens: int = 1200
) -> ChatResult:
    s = get_settings()
    body: dict = {"model": s.llm_model, "messages": messages, "temperature": 0, "seed": 0, "max_tokens": max_tokens}
    if schema:
        body["response_format"] = {
            "type": "json_schema",
            "json_schema": {"name": "out", "strict": True, "schema": schema},
        }
    if tools:
        body["tools"] = tools
    data, ms = post("/v1/chat/completions", body, TIMEOUT_S, RETRIES)
    try:
        msg = data["choices"][0]["message"]
    except (KeyError, IndexError, TypeError) as e:
        raise LLMUnavailable(f"bad response: {str(data)[:200]}") from e
    usage = data.get("usage") or {}
    call = {
        "model": data.get("model", s.llm_model),
        "prompt_tokens": usage.get("prompt_tokens"),
        "completion_tokens": usage.get("completion_tokens"),
        "ms": ms,
    }
    log.info(json.dumps({"event": "llm_call"} | call))
    return ChatResult(msg.get("content"), msg.get("tool_calls") or [], msg, call)
