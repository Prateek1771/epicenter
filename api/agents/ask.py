"""ask agent (GPT-4o tool loop), HLD §3.2: the typed tools first, read-only Cypher through falkordb-mcp as a fallback.

The model sees only these tools, all bound to one env; it never writes and never picks a graph. The answer's `path`
keeps only ids that actually appeared in tool results, so the UI never highlights an invented node.
"""

import inspect
import json
import re
from pathlib import Path

from pydantic import create_model

from api.ai import openrouter
from api.tools import falkordb_mcp, graph_tools

PROMPT = (Path(__file__).parent / "prompts" / "ask.md").read_text(encoding="utf-8")
MAX_STEPS = 4
MAX_TOOL_CHARS = 6000  # per tool result fed back to the model
ANSWER = {
    "type": "object",
    "properties": {"answer": {"type": "string"}, "path": {"type": "array", "items": {"type": "string"}}},
    "required": ["answer", "path"],
    "additionalProperties": False,
}
REL = re.compile(r"^[A-Z][A-Z_]+$")


def _arg_model(fn):
    params = {
        n: (p.annotation, ... if p.default is inspect.Parameter.empty else p.default)
        for n, p in inspect.signature(fn).parameters.items()
        if n != "env"
    }
    return create_model(f"{fn.__name__}_args", **params)


TYPED = {fn.__name__: (fn, _arg_model(fn)) for fn in graph_tools.TOOLS}


def tool_specs() -> list[dict]:
    specs = [
        {"type": "function", "function": {"name": name, "description": (fn.__doc__ or "").strip().split("\n")[0],
                                          "parameters": model.model_json_schema()}}
        for name, (fn, model) in TYPED.items()
    ]  # fmt: skip
    specs.append({"type": "function", "function": {"name": "graph_schema", "description": "Labels, relationship "
                  "types and properties of this environment's graph.", "parameters": {"type": "object",
                  "properties": {}}}})  # fmt: skip
    specs.append({"type": "function", "function": {"name": "cypher_readonly", "description": "Run one read-only "
                  "OpenCypher query on this environment's graph (fallback when no typed tool fits).",
                  "parameters": {"type": "object", "properties": {"query": {"type": "string"}},
                                 "required": ["query"]}}})  # fmt: skip
    return specs


def run_tool(name: str, args: dict, env: str) -> tuple[str, str | None]:
    """→ (result text for the model, the Cypher it ran if any). Unknown tools are refused, not executed."""
    if name in TYPED:
        fn, model = TYPED[name]
        out = fn(**model(**args).model_dump(), env=env)
        data = [x.model_dump() for x in out] if isinstance(out, list) else out.model_dump()
        return json.dumps(data, default=str), None
    if name == "graph_schema":
        return falkordb_mcp.call("get_graph_schema", {}, f"env:{env}"), None
    if name == "cypher_readonly":
        q = str(args.get("query", ""))
        return falkordb_mcp.call("query_graph_readonly", {"query": q}, f"env:{env}"), q
    raise ValueError(f"unknown tool {name!r}")


def _strings(text: str) -> set[str]:
    """Every string value in a tool result: the ids a `path` may cite."""
    try:
        data = json.loads(text)
    except ValueError:
        return set(re.findall(r"[\w./{}:@ -]+", text))
    out, stack = set(), [data]
    while stack:
        x = stack.pop()
        if isinstance(x, str):
            out.add(x)
        elif isinstance(x, dict):
            stack += list(x.values())
        elif isinstance(x, list):
            stack += x
    return out


def answer(question: str, env: str, incident_id: str | None = None) -> dict:
    """Raises openrouter.LLMUnavailable when the model can't be reached (the route answers 502)."""
    context = f"\nThe question is about incident {incident_id}." if incident_id else ""
    messages = [{"role": "system", "content": PROMPT}, {"role": "user", "content": question + context}]
    used, seen, cypher = [], set(), None
    for _ in range(MAX_STEPS):
        res = openrouter.chat(messages, tools=tool_specs(), schema=ANSWER)
        if not res.tool_calls:
            out = json.loads(res.content or "{}")
            path = [p for p in out.get("path", []) if p in seen or REL.match(p)]
            return {"answer": out.get("answer", ""), "path": path, "tools_used": used, "cypher": cypher}
        messages.append(res.message)
        for tc in res.tool_calls:
            name = tc["function"]["name"]
            try:
                args = json.loads(tc["function"].get("arguments") or "{}")
                text, q = run_tool(name, args, env)
                cypher = q or cypher
                used.append({"tool": name, "args": args})
                seen |= _strings(text)
            except Exception as e:  # a bad tool call goes back to the model as an error, never crashes the request
                text = json.dumps({"error": f"{type(e).__name__}: {str(e)[:200]}"})
            messages.append({"role": "tool", "tool_call_id": tc["id"], "content": text[:MAX_TOOL_CHARS]})
    return {
        "answer": "I couldn't answer that within the tool budget.",
        "path": [],
        "tools_used": used,
        "cypher": cypher,
    }
