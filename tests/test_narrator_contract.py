"""Narrator + Jev gate (LLD §12 "agent contract"), offline: fake GPT-4o and Jev behind httpx.MockTransport."""

import json
from pathlib import Path

import pytest

from api.agents import flow, narrator
from api.config import get_settings
from api.ingest.seed import seed_indexes
from api.search import causal
from api.search.causal import diagnose
from api.tools import graph_tools
from tests.fakes import FakeOpenRouter, use_openrouter

FIXTURES = Path(__file__).parent / "fixtures"
ENV = "test-narr"


@pytest.fixture
def run(graph, monkeypatch, tmp_path):
    monkeypatch.setattr(graph_tools, "get_graph", lambda: graph)
    monkeypatch.setattr(flow, "get_graph", lambda: graph)
    g = graph.env(ENV)
    g.delete()
    seed_indexes(g)
    g.load_cypher(FIXTURES / "mini_graph.cypher")
    diagnose(graph, ENV, "inc-1")
    r = causal.open_run(graph, ENV, "inc-1")
    r.db = str(tmp_path / "cp.db")
    yield r
    g.delete()


def _ids(r) -> dict[str, str]:
    """kind → evidence id of the root cause (payment/Charge)."""
    ev = narrator.narrator_input(r)["evidence"]
    return {e["kind"]: e["id"] for e in ev if e["hypothesis"] == "h-2"}


def _llm(claims: dict) -> dict:
    return {"content": json.dumps({s: claims.get(s, []) for s in narrator.SECTIONS})}


def test_valid_output_keeps_cited_claims_and_drops_the_rest(run, monkeypatch):
    e = _ids(run)
    fake = use_openrouter(monkeypatch, FakeOpenRouter(chat=[_llm({
        "what": [{"text": "payment/Charge is the root cause.", "cites": [e["propagation"]]}],
        "where": [{"text": "It spread up to the checkout page.", "cites": ["E99"]}],  # not in the input
        "why": [{"text": "A flag flipped just before.", "cites": [e["change"]]},
                {"text": "Something unsupported.", "cites": []}],  # cites nothing
    })]))  # fmt: skip
    x = narrator.narrate(run)
    [saved] = run.env.ro("explanation", inc="inc-1", id=x["explanation_id"])
    claims = json.loads(saved["claims"])
    assert [c["section"] for c in claims] == ["what", "why"] and saved["dropped"] == 2 and saved["source"] == "llm"
    [req] = fake.bodies("/chat/completions")
    assert req["temperature"] == 0 and req["model"] == "openai/gpt-4o-2024-11-20"
    assert req["response_format"]["json_schema"]["schema"] == narrator.SCHEMA
    user = req["messages"][1]["content"]
    assert user.startswith("<verdict_json>") and user.endswith("</verdict_json>")  # data, delimited (HLD §9)
    assert "DATA" in req["messages"][0]["content"]
    assert json.loads(saved["ai_calls"])[0]["model"] == "openai/gpt-4o-2024-11-20"


def test_schema_invalid_output_and_no_key_fall_back_to_the_template(run, monkeypatch):
    use_openrouter(monkeypatch, FakeOpenRouter(chat=[{"content": '{"what": "not a list"}'}]))
    x = narrator.narrate(run)
    [bad] = run.env.ro("explanation", inc="inc-1", id=x["explanation_id"])
    assert bad["source"] == "template"
    monkeypatch.setattr(get_settings(), "openrouter_api_key", None)  # no key at all
    narrator.narrate(run)
    [tpl] = run.env.ro("explanation", inc="inc-1", id=x["explanation_id"])
    claims = json.loads(tpl["claims"])
    known = {e["id"] for e in narrator.narrator_input(run)["evidence"]}
    assert tpl["source"] == "template" and claims and all(c["cites"] and set(c["cites"]) <= known for c in claims)
    assert claims[0]["text"].startswith("payment/Charge is the root cause")


def test_jev_gate_drops_unsupported_claims(run, monkeypatch):
    e = _ids(run)
    fake = use_openrouter(monkeypatch, FakeOpenRouter(
        chat=[_llm({"what": [{"text": "payment/Charge failed first.", "cites": [e["propagation"]]}],
                    "why": [{"text": "Because of a deploy.", "cites": [e["change"]]}]})],
        noul={"c0": 0.93, "c1": 0.41},
    ))  # fmt: skip
    x = narrator.narrate(run)
    narrator.jev_gate(run, x["explanation_id"], min_support=0.7)
    [saved] = run.env.ro("explanation", inc="inc-1", id=x["explanation_id"])
    claims = json.loads(saved["claims"])
    assert [(c["text"], c.get("support_p"), c["status"]) for c in claims][0] == (
        "payment/Charge failed first.",
        0.93,
        "verified",
    )
    # the dropped change claim (0.41) comes back as the template's own change claim, marked as such
    assert [(c["section"], c["status"]) for c in claims[1:]] == [("why", "template")] and claims[1]["cites"] == [
        e["change"]
    ]
    assert saved["dropped"] == 1 and saved["verified"] is True
    [jev_req] = fake.bodies("/alpha/decisions")
    assert set(jev_req["questions"]) == {"c0", "c1"} and all(q["type"] == "noul" for q in jev_req["questions"].values())
    assert [c["agent"] for c in json.loads(saved["ai_calls"])] == ["narrator", "jev_gate"]


def test_jev_down_keeps_cited_claims_unverified(run, monkeypatch):
    e = _ids(run)
    claim = {"text": "payment/Charge failed first.", "cites": [e["propagation"]]}
    use_openrouter(monkeypatch, FakeOpenRouter(chat=[_llm({"what": [claim]})], noul=503))
    x = narrator.narrate(run)
    narrator.jev_gate(run, x["explanation_id"], min_support=0.7)
    [saved] = run.env.ro("explanation", inc="inc-1", id=x["explanation_id"])
    assert [c["status"] for c in json.loads(saved["claims"])] == ["unverified", "template"] and saved[
        "verified"
    ] is False


def test_the_llm_never_changes_the_verdict(graph, run, monkeypatch):
    """N7 / rule 4: the full agent flow with GPT-4o and Jev answering gives the verdict the sequential path gives."""
    e = _ids(run)
    use_openrouter(monkeypatch, FakeOpenRouter(
        chat=[_llm({"what": [{"text": "cart/GetCart is the real root cause!", "cites": [e["propagation"]]}]})],
        noul={"c0": 0.99}))  # fmt: skip
    seq = diagnose(graph, ENV, "inc-1")
    agents = flow.run("inc-1", ENV, db_path=run.db)
    keys = ("status", "root_cause", "second_cause", "confidence", "statuses")
    assert {k: agents[k] for k in keys} == {k: seq[k] for k in keys}
    assert [(h["op"], h["score"]) for h in agents["ranking"]] == [(h["op"], h["score"]) for h in seq["ranking"]]


def test_headline_and_change_never_depend_on_the_model(run, monkeypatch):
    e = _ids(run)
    use_openrouter(monkeypatch, FakeOpenRouter(
        chat=[_llm({"where": [{"text": "It started at payment/Charge.", "cites": [e["propagation"]]}]})],
        noul={"c0": 0.95}))  # fmt: skip
    x = narrator.narrate(run)
    narrator.jev_gate(run, x["explanation_id"], min_support=0.7)
    [saved] = run.env.ro("explanation", inc="inc-1", id=x["explanation_id"])
    claims = json.loads(saved["claims"])
    assert [(c["section"], c["status"]) for c in claims] == [("what", "template"), ("where", "verified"),
                                                             ("why", "template")]  # fmt: skip
    assert claims[0]["text"].startswith("payment/Charge is the root cause") and claims[2]["cites"] == [e["change"]]
