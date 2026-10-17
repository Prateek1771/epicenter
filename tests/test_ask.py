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
        _answer("Page alice or bob: they own payment.",
                ["payment", "OWNED_BY", "payments", "MEMBER_OF", "alice", "team-ghost", "bob"]),
    ]))  # fmt: skip
    r = client.post("/api/v1/ask", params=Q, json={"question": "who should I page for payment?"})
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["tools_used"] == [{"tool": "who_knows", "args": {"service": "payment"}}] and out["cypher"] is None
    # the asked-about service and its team are citable; team-ghost never appeared in a tool call or result
    assert out["path"] == ["payment", "OWNED_BY", "payments", "MEMBER_OF", "alice", "bob"]
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


def test_conversation_keeps_history_attachments_and_survives_a_502(client, monkeypatch):
    """Ask as a chat: a conversation saves every turn in the graph, sends the last turns back as history, quotes
    attachments as data (never stores their text), and keeps the question when the LLM is down."""
    c = client.post("/api/v1/conversations", params=Q, json={"incident_id": "inc-1"})
    assert c.status_code == 201, c.text
    cid = c.json()["id"]
    assert c.json()["incident"] == "inc-1" and c.json()["messages"] == 0
    fake = use_openrouter(monkeypatch, FakeOpenRouter(chat=[_answer("payments owns it.", ["payment"]),
                                                           _answer("Yes, the flag changed first.", [])]))  # fmt: skip
    files = [{"name": "notes.md", "text": "flag flipped 14:03"}]
    body = {"question": "who owns payment?", "conversation_id": cid, "attachments": files}
    r = client.post("/api/v1/ask", params=Q, json=body)
    assert r.status_code == 200 and r.json()["conversation_id"] == cid and r.json()["message_id"] == f"{cid}:m0002"
    client.post("/api/v1/ask", params=Q, json={"question": "did a change come first?", "conversation_id": cid})
    first, second = fake.bodies("/chat/completions")
    assert "Attached file `notes.md`" in first["messages"][-1]["content"]
    assert [m["role"] for m in second["messages"][1:3]] == ["user", "assistant"]  # the first turn, as history
    assert second["messages"][2]["content"] == "payments owns it."
    d = client.get(f"/api/v1/conversations/{cid}", params=Q).json()
    assert d["title"] == "who owns payment?" and d["messages"] == 4
    assert [m["role"] for m in d["message_list"]] == ["user", "assistant", "user", "assistant"]
    assert d["message_list"][0]["attachments"] == ["notes.md"] and "14:03" not in d["message_list"][0]["text"]
    use_openrouter(monkeypatch, FakeOpenRouter(chat=[]))  # the model is down now
    monkeypatch.setattr(get_settings(), "openrouter_api_key", "")
    down = client.post("/api/v1/ask", params=Q, json={"question": "and now?", "conversation_id": cid})
    assert down.status_code == 502
    assert client.get(f"/api/v1/conversations/{cid}", params=Q).json()["message_list"][-1]["text"] == "and now?"
    listed = client.get("/api/v1/conversations", params=Q | {"incident": "inc-1"}).json()["items"]
    assert [x["id"] for x in listed] == [cid]
    assert client.delete(f"/api/v1/conversations/{cid}", params=Q).status_code == 204
    assert client.get(f"/api/v1/conversations/{cid}", params=Q).status_code == 404
