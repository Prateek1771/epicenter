"""Fake HTTP backends for the offline tests: OpenRouter (GPT-4o chat + Jev decisions), OpenConnector, falkordb-mcp.

Each fake is an httpx.MockTransport handler that records the requests it got and answers from a script.
"""

import json

import httpx


class FakeOpenRouter:
    """`chat`: queued chat responses (dicts with `content` and/or `tool_calls`), or an int HTTP status.
    `noul`: question name → P(yes) (default 0.5), or an int HTTP status for the whole decisions call."""

    def __init__(self, chat=None, noul=None):
        self.chat = list(chat or [])
        self.noul = noul
        self.requests: list[tuple[str, dict]] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        self.requests.append((request.url.path, body))
        if request.url.path.endswith("/chat/completions"):
            if not self.chat:
                return httpx.Response(500, json={"error": "no scripted chat response"})
            nxt = self.chat.pop(0)
            if isinstance(nxt, int):
                return httpx.Response(nxt, json={"error": "scripted failure"})
            msg = {"role": "assistant", "content": nxt.get("content")}
            if nxt.get("tool_calls"):
                msg["tool_calls"] = [
                    {"id": f"call-{i}", "type": "function",
                     "function": {"name": n, "arguments": json.dumps(a)}}
                    for i, (n, a) in enumerate(nxt["tool_calls"])
                ]  # fmt: skip
            usage = {"prompt_tokens": 100, "completion_tokens": 20}
            return httpx.Response(200, json={"model": "openai/gpt-4o-2024-11-20", "choices": [{"message": msg}],
                                             "usage": usage})  # fmt: skip
        if request.url.path.endswith("/alpha/decisions"):
            answers = {}
            if isinstance(self.noul, int) or self.noul is None:
                return httpx.Response(self.noul or 503, json={"error": "jev down"})
            for name in body["questions"]:
                answers[name] = {"type": "noul", "noul": self.noul.get(name, 0.5)}
            usage = {"input_tokens": 300, "output_tokens": 10, "cost": 1e-05}
            return httpx.Response(200, json={"model": "typesafe/jev-1.13-20260917", "answers": answers, "usage": usage})
        return httpx.Response(404, json={"error": f"unexpected {request.url.path}"})

    def bodies(self, suffix: str) -> list[dict]:
        return [b for p, b in self.requests if p.endswith(suffix)]


def use_openrouter(monkeypatch, fake: FakeOpenRouter) -> FakeOpenRouter:
    from api.ai import openrouter
    from api.config import get_settings

    monkeypatch.setattr(get_settings(), "openrouter_api_key", "test-key")
    monkeypatch.setattr(openrouter, "_transport", httpx.MockTransport(fake))
    return fake


class FakeConnector:
    """OpenConnector runtime: `fail` = action ids that answer {success: false}."""

    def __init__(self, fail=()):
        self.fail = set(fail)
        self.requests: list[tuple[str, dict, dict]] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        action = request.url.path.rsplit("/", 1)[1]
        self.requests.append((action, json.loads(request.content)["input"], dict(request.headers)))
        if action in self.fail:
            return httpx.Response(403, json={"success": False, "message": "connection_not_allowed"})
        data = {
            "slack.post_message": {"ts": "1729.0001", "channelId": "C1"},
            "slack.get_message_permalink": {"permalink": "https://slack.example/archives/C1/p17290001"},
            "linear.create_linear_issue": {
                "id": "x",
                "identifier": "OPS-7",
                "ticket_url": "https://linear.example/OPS-7",
            },
        }.get(action, {})
        return httpx.Response(200, json={"success": True, "message": "OK", "data": data, "meta": {}})


class FakeMcp:
    """falkordb-mcp: answers initialize and tools/call (SSE framed like the real server)."""

    def __init__(self, text: str = '[{"o.id": "checkout/PlaceOrder", "callers": 2}]'):
        self.text = text
        self.calls: list[dict] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        msg = json.loads(request.content)
        if msg.get("method") == "initialize":
            return httpx.Response(200, headers={"mcp-session-id": "s-1"},
                                  text='event: message\ndata: {"jsonrpc":"2.0","id":1,"result":{}}\n\n')  # fmt: skip
        if msg.get("method") == "tools/call":
            self.calls.append(msg["params"])
            res = {"content": [{"type": "text", "text": self.text}], "isError": False}
            return httpx.Response(
                200, text=f"event: message\ndata: {json.dumps({'jsonrpc': '2.0', 'id': 2, 'result': res})}\n\n"
            )
        return httpx.Response(202)
