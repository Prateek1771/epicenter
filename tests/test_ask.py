"""POST /ask (USER_FLOW Flow 4), offline: fake GPT-4o tool calls, fake falkordb-mcp."""

import json

import httpx

from api.config import get_settings
from api.tools import falkordb_mcp
from tests.conftest import API_ENV
from tests.fakes import FakeMcp, FakeOpenRouter, use_openrouter

Q = {"env": API_ENV}


def _answer(text: str, path: list[str]) -> dict:
    return {"content": json.dumps({"answer": text, "path": path})}


def test_typed_tool_first_and_path_keeps_only_seen_ids(client, monkeypatch):
    fake = use_openrouter(monkeypatch, FakeOpenRouter(chat=[
        {"tool_calls": [("who_knows", {"service": "payment"})]},
        _answer("Page alice or bob: they own payment.", ["alice", "MEMBER_OF", "team-ghost", "bob"]),
    ]))  # fmt: skip
    r = client.post("/api/v1/ask", params=Q, json={"question": "who should I page for payment?"})
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["tools_used"] == [{"tool": "who_knows", "args": {"service": "payment"}}] and out["cypher"] is None
    assert out["path"] == ["alice", "MEMBER_OF", "bob"]  # team-ghost never appeared in a tool result
    first, second = fake.bodies("/chat/completions")
    names = {t["function"]["name"] for t in first["tools"]}
    assert {"who_knows", "blast_radius", "graph_schema", "cypher_readonly"} <= names
    assert not names & {"query_graph", "delete_graph"}  # write tools are never offered
    tool_msg = second["messages"][-1]
    assert tool_msg["role"] == "tool" and "alice" in tool_msg["content"]


def test_cypher_fallback_is_read_only_on_the_env_graph(client, monkeypatch):
    mcp = FakeMcp()
    monkeypatch.setattr(falkordb_mcp, "_transport", httpx.MockTransport(mcp))
    monkeypatch.setattr(get_settings(), "falkordb_mcp_url", "http://mcp.test/mcp")
    query = "MATCH (o:Operation)<-[:CALLS]-(c) RETURN o.id, count(c) AS callers ORDER BY callers DESC LIMIT 1"
    use_openrouter(monkeypatch, FakeOpenRouter(chat=[
        {"tool_calls": [("cypher_readonly", {"query": query, "graphName": "env:other"})]},
        _answer("checkout/PlaceOrder has the most callers.", ["checkout/PlaceOrder"]),
    ]))  # fmt: skip
    out = client.post("/api/v1/ask", params=Q, json={"question": "which operation has the most callers?"}).json()
    assert out["cypher"] == query and out["path"] == ["checkout/PlaceOrder"]
    [call] = mcp.calls
    assert call["name"] == "query_graph_readonly" and call["arguments"]["graphName"] == f"env:{API_ENV}"  # pinned


def test_unknown_or_write_tools_are_refused(client, monkeypatch):
    mcp = FakeMcp()
    monkeypatch.setattr(falkordb_mcp, "_transport", httpx.MockTransport(mcp))
    fake = use_openrouter(monkeypatch, FakeOpenRouter(chat=[
        {"tool_calls": [("delete_graph", {"graphName": f"env:{API_ENV}", "confirmDelete": True})]},
        _answer("I can't do that.", []),
    ]))  # fmt: skip
    out = client.post("/api/v1/ask", params=Q, json={"question": "delete the graph"}).json()
    assert out["tools_used"] == [] and mcp.calls == []
    assert "unknown tool" in fake.bodies("/chat/completions")[1]["messages"][-1]["content"]
    assert client.app.state.graph.env(API_ENV).ro("count_nodes")[0]["n"] > 0  # still there


def test_ask_needs_the_llm(client):
    r = client.post("/api/v1/ask", params=Q, json={"question": "who owns payment?"})  # offline: no key
    assert r.status_code == 502 and r.json()["error"]["code"] == "UPSTREAM_ERROR"
