"""The typed tools over MCP (ADR 0003), mounted on the API at /mcp. Generated from `graph_tools.TOOLS`, so the MCP
surface and the in-process tools can't drift apart. Read-only: no tool writes, none accepts Cypher.
"""

from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings

from api.config import get_settings
from api.tools.graph_tools import TOOLS

server = MCPServer(
    "epicenter",
    instructions="Root-cause tools over the Epicenter incident graph. Every tool takes an optional `env` "
    "(default: the configured environment) and returns typed JSON.",
)
for fn in TOOLS:
    server.add_tool(fn, structured_output=True)


def asgi_app():
    """Streamable HTTP, stateless with plain JSON responses (one request, one answer; no server-initiated calls).
    DNS-rebinding protection allows the local hosts and the web origin only."""
    s = get_settings()
    return server.streamable_http_app(
        streamable_http_path="/mcp",
        stateless_http=True,
        json_response=True,
        transport_security=TransportSecuritySettings(
            allowed_hosts=["localhost:*", "127.0.0.1:*", "api:*", "testserver"],
            allowed_origins=[s.web_origin, "http://localhost:*", "http://127.0.0.1:*"],
        ),
    )
