"""Read-only fallback for the ask agent: FalkorDB's own MCP server (`falkordb-mcp`, ADR 0003).

The server also exposes write tools (`query_graph`, `delete_graph`); this client can call only the two allowlisted
read tools, and always on the caller's env graph (rule 8): the model never picks the graph name.
`query_graph_readonly` runs as GRAPH.RO_QUERY, so FalkorDB itself rejects writes as well.
"""

import json

import httpx

from api.config import get_settings

ALLOWED = {"get_graph_schema", "query_graph_readonly"}
TIMEOUT_S = 10.0
_transport: httpx.BaseTransport | None = None  # tests swap in an httpx.MockTransport
HEADERS = {"content-type": "application/json", "accept": "application/json, text/event-stream"}


class McpError(Exception):
    pass


def _result(r: httpx.Response) -> dict:
    """The JSON-RPC result from a plain JSON or an SSE (`data: …`) response."""
    text = r.text
    if "data:" in text and not text.lstrip().startswith("{"):
        text = next(ln[5:].strip() for ln in text.splitlines() if ln.startswith("data:"))
    msg = json.loads(text)
    if "error" in msg:
        raise McpError(str(msg["error"])[:300])
    return msg.get("result") or {}


def call(tool: str, args: dict, graph_key: str) -> str:
    """Run one allowlisted falkordb-mcp tool on `graph_key` (`env:<name>`); returns its text content."""
    if tool not in ALLOWED:
        raise McpError(f"tool {tool!r} is not allowed")
    s = get_settings()
    if not s.falkordb_mcp_url:
        raise McpError("FALKORDB_MCP_URL not set")
    headers = HEADERS | ({"Authorization": f"Bearer {s.mcp_api_key}"} if s.mcp_api_key else {})
    init = {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "epicenter", "version": "1"}}
    try:
        with httpx.Client(transport=_transport, timeout=TIMEOUT_S) as c:
            r = c.post(s.falkordb_mcp_url, json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": init},
                       headers=headers)  # fmt: skip
            r.raise_for_status()
            if sid := r.headers.get("mcp-session-id"):
                headers = headers | {"mcp-session-id": sid}
            c.post(s.falkordb_mcp_url, json={"jsonrpc": "2.0", "method": "notifications/initialized"}, headers=headers)
            params = {"name": tool, "arguments": args | {"graphName": graph_key}}
            r = c.post(s.falkordb_mcp_url, json={"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": params},
                       headers=headers)  # fmt: skip
            r.raise_for_status()
    except httpx.HTTPError as e:
        raise McpError(str(e)) from e
    res = _result(r)
    text = "\n".join(x.get("text", "") for x in res.get("content", []) if x.get("type") == "text")
    if res.get("isError"):
        raise McpError(text[:300] or "tool error")
    return text
