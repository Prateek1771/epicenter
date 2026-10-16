"""Live prompt evals (phase 7): the real GPT-4o narrator + Jev gate on fixtures, checked against prompt_evals/*.yaml.

    docker compose exec -e EPICENTER_LIVE=1 api pytest tests/test_prompt_evals.py -v

Skipped unless EPICENTER_LIVE=1 and OPENROUTER_API_KEY are set: they spend (a fraction of a cent per case) and depend
on a remote model, so they never run in CI or in the default suite.
"""

import json
import os
from pathlib import Path

import pytest
import yaml

from api.agents import narrator
from api.config import get_settings
from api.ingest.seed import seed_indexes
from api.search import causal
from api.search.causal import diagnose

HERE = Path(__file__).parent
CASES = yaml.safe_load((HERE / "prompt_evals" / "narrator.yaml").read_text(encoding="utf-8"))["cases"]
ENV = "test-evals"

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(os.environ.get("EPICENTER_LIVE") != "1", reason="live LLM evals: set EPICENTER_LIVE=1"),
]


@pytest.mark.parametrize("case", CASES, ids=[c["name"] for c in CASES])
def test_narrator_case(graph, case):
    if not get_settings().openrouter_api_key:
        pytest.skip("OPENROUTER_API_KEY not set")
    g = graph.env(ENV)
    g.delete()
    seed_indexes(g)
    g.load_cypher(HERE / "fixtures" / case["fixture"])
    try:
        before = diagnose(graph, ENV, case["incident"])
        r = causal.open_run(graph, ENV, case["incident"])
        x = narrator.narrate(r)
        narrator.jev_gate(r, x["explanation_id"], r.w["explanation"]["min_support"])
        [saved] = g.ro("explanation", inc=case["incident"], id=x["explanation_id"])
        claims = json.loads(saved["claims"])
        known = {e["id"] for e in narrator.narrator_input(r)["evidence"]}
        exp = case["expect"]
        report = json.dumps({"source": saved["source"], "dropped": saved["dropped"], "claims": claims}, indent=1)
        assert causal.read_verdict(r)["root_cause"] == before["root_cause"], "the explanation changed the verdict"
        if "source" in exp:
            assert saved["source"] == exp["source"], report
        assert len(claims) >= exp.get("min_claims", 1), report
        assert all(c["cites"] and set(c["cites"]) <= known for c in claims), report  # only real evidence ids
        for section in exp.get("sections_present", []):
            assert any(c["section"] == section for c in claims), report
        for section, words in exp.get("mention_any", {}).items():
            text = " ".join(c["text"] for c in claims if c["section"] == section)
            assert any(w.lower() in text.lower() for w in words), f"{section} lacks {words}\n{report}"
        everything = " ".join(c["text"] for c in claims).lower()
        assert not [w for w in exp.get("forbid", []) if w.lower() in everything], report
        if saved["source"] == "llm":
            calls = json.loads(saved["ai_calls"])
            assert calls[0]["model"].startswith("openai/gpt-4o") and calls[0]["prompt_tokens"], report
    finally:
        g.delete()
