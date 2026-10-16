"""The typed tools over MCP at /mcp (JSON-RPC over streamable HTTP, stateless, JSON responses)."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.ingest.seed import seed_indexes
from api.main import app
from api.tools import graph_tools

FIXTURES = Path(__file__).parent / "fixtures"
HEADERS = {"content-type": "application/json", "accept": "application/json, text/event-stream"}


def _rpc(client: TestClient, method: str, params: dict, n: int = 1) -> dict:
    r = client.post("/mcp", json={"jsonrpc": "2.0", "id": n, "method": method, "params": params}, headers=HEADERS)
    assert r.status_code == 200, r.text
    return r.json()["result"]


@pytest.fixture
def mcp_env(graph):
    g = graph.env("test-mcp")
    g.delete()
    seed_indexes(g)
    g.load_cypher(FIXTURES / "mini_graph.cypher")
    yield "test-mcp"
    g.delete()


def test_mcp_lists_and_calls_the_same_tools(mcp_env):
    with TestClient(app) as client:
        init = _rpc(
            client,
            "initialize",
            {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "pytest", "version": "0"}},
        )
        assert init["serverInfo"]["name"] == "epicenter"
        names = [tool["name"] for tool in _rpc(client, "tools/list", {}, 2)["tools"]]
        assert names == [fn.__name__ for fn in graph_tools.TOOLS]
        out = _rpc(client, "tools/call", {"name": "blast_radius", "arguments": {"service": "redis", "env": mcp_env}}, 3)
    assert not out.get("isError")
    rows = out["structuredContent"]["result"]
    assert rows == [c.model_dump() for c in graph_tools.blast_radius("redis", env=mcp_env)]
