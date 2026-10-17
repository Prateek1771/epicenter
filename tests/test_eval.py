"""RCAEval suite (phase 10): the pure metrics, the grid, memory precision, and one end-to-end run on the synthetic
case from test_rcaeval (base + four ablations, byte-identical on a second run) plus GET /eval."""

import json
import shutil

import pytest

from api import eval as ev
from api.search import score as sc
from tests.test_rcaeval import case_dir  # noqa: F401  (fixture)

W = sc.load_weights("weights.json")["w"]


def test_label_and_split():
    assert ev.label("re2tt_ts-auth-service_cpu_2") == {"service": "ts-auth-service", "fault": "cpu", "rep": 2}
    assert ev.split("re2tt_ts-auth-service_cpu_2") == "dev" and ev.split("re2tt_ts-auth-service_cpu_3") == "test"
    with pytest.raises(ValueError):
        ev.label("re1ob_adservice_cpu_1")


def test_metrics_count_services_not_ops_and_no_root_cause_is_a_miss():
    rows = [
        {"case": "re2tt_a_cpu_1", "ranked": ["a/x", "b/y"]},  # hit @1
        {"case": "re2tt_a_delay_1", "ranked": ["b/y", "b/z", "c/q", "a/x"]},  # a is the 3rd distinct service: hit @3
        {"case": "re2tt_a_mem_1", "ranked": []},  # no root cause
    ]
    m = ev.metrics(rows)
    assert (m["ac1"], m["ac3"]) == (round(1 / 3, 4), round(2 / 3, 4))
    assert m["by_fault"]["cpu"] == {"cases": 1, "ac1": 1.0} and m["by_fault"]["mem"]["ac1"] == 0.0


def test_ranked_ops_drop_refuted_and_lead_with_the_verdict():
    v = {"root_cause": "b/y", "ranking": [{"op": "a/x", "status": "refuted"}, {"op": "b/y", "status": "confirmed"},
                                          {"op": "c/z", "status": "pruned"}]}  # fmt: skip
    assert ev.ranked_ops(v) == ["b/y", "c/z"]
    assert ev.ranked_ops({"root_cause": None, "ranking": v["ranking"]}) == []


def test_rescore_matches_the_scorer():
    f = {k: 0.5 for k in sc.FEATURES} | {"refuted": 0.0}
    g = {k: 0.9 for k in sc.FEATURES} | {"refuted": 1.0}  # high features, but refuted
    parts = [{"op": "a/x", "onset": 10, "parts": f}, {"op": "b/y", "onset": 5, "parts": g}]
    assert ev.rescore(parts, {"w": W}) == ["a/x", "b/y"]
    assert sc.score(f, {"w": W}) > sc.score(g, {"w": W})


def test_simplex_sums_to_one_and_grid_prefers_the_base_on_ties():
    ws = ev.simplex(["a", "b", "c"], 0.25)
    assert len(ws) == 15 and all(abs(sum(w.values()) - 1) < 1e-9 for w in ws)
    parts = [{"op": "a/x", "onset": 1, "parts": {k: 1.0 for k in sc.FEATURES} | {"refuted": 0.0}}]
    g = ev.grid([{"case": "re2tt_a_cpu_1", "parts": parts}], W, step=0.5)
    assert g["ac1"] == g["base_ac1"] == 1.0


def test_precision_at_3_is_leave_one_out():
    sigs = {
        "re2tt_a_cpu_1": [1.0, 0.0],
        "re2tt_a_cpu_2": [0.9, 0.1],
        "re2tt_a_cpu_3": [0.8, 0.2],
        "re2tt_b_delay_1": [0.0, 1.0],
        "re2tt_b_delay_2": [0.0, 0.0],  # empty signature: no recall
    }
    m = ev.precision_at_3(sigs)
    assert m["cases"] == 4
    # each a-case finds its 2 siblings + b_delay_1 (2/3); b_delay_1 finds 3 a-cases (0/3)
    assert m["p_at_3"] == round((2 / 3 * 3 + 0) / 4, 4)


def test_suite_end_to_end_is_deterministic(graph, case_dir, tmp_path):  # noqa: F811
    out = tmp_path / "eval"
    case = shutil.copytree(case_dir, tmp_path / "re2tt_db_delay_1")  # the fixture's fault is in db: label it so
    a = ev.run_suite(graph, [case], "tt", "weights.json", out)
    b = ev.run_suite(graph, [case], "tt", "weights.json", out)
    assert a.name.startswith("0001-re2-tt-") and b.name.startswith("0002-")
    assert a.read_bytes() == b.read_bytes()  # same code + data → byte-identical results
    res = json.loads(a.read_text(encoding="utf-8"))
    s = res["summary"]
    assert s["cases"] == 1 and set(s["ablations"]) == {"no_pagerank", "no_temporal", "no_mechanism", "no_footprint"}
    [row] = res["rows"]
    assert row["variants"]["base"]["root_cause"].startswith("db/")  # the synthetic case's fault is in db
    assert s["ac1"] == 1.0 and len(row["signature"]) == 64
    assert row["variants"]["no_footprint"]["weights_version"].endswith("+no_footprint")
    t = json.loads(a.with_suffix(".timing.json").read_text(encoding="utf-8"))
    assert t["n1_ms"]["p50"] > 0 and "Q1" in t["n2_p95_ms"]
    assert not graph.env("eval-tt").ro("label_counts")  # the scratch graph is gone
    latest = ev.latest(out)
    assert latest is not None and latest["run"] == b.stem


def test_get_eval(client, tmp_path, monkeypatch):
    monkeypatch.setattr(ev, "OUT", tmp_path)
    r = client.get("/api/v1/eval")
    assert r.status_code == 404 and r.json()["error"]["code"] == "EVAL_NOT_FOUND"
    summary = {"suite": "re2", "system": "tt", "cases": 2, "ac1": 0.5, "ac3": 1.0, "by_fault": {}, "split": {},
               "ablations": {"no_pagerank": {"ac1": 0.5, "ac3": 1.0}}, "memory": {"cases": 0, "p_at_3": None},
               "weights_version": "v", "rules_version": "r"}  # fmt: skip
    (tmp_path / "0001-re2-tt-v-r.json").write_text(json.dumps({"summary": summary | {"ac1": 0.0}, "rows": []}))
    rows = [{"case": "re2tt_a_cpu_3", "split": "test",
             "variants": {"base": {"ranked": ["b/x", "a/y"], "confidence": 0.4}, "no_pagerank": {"ranked": ["a/y"]}},
             "parts": [{"op": "b/x", "parts": {"pagerank": 0.5, "pagerank_impl": "falkordb"}}]},
            {"case": "re2tt_a_cpu_1", "split": "dev", "variants": {"base": {"ranked": []}}}]  # fmt: skip
    (tmp_path / "0002-re2-tt-v-r.json").write_text(json.dumps({"summary": summary, "rows": rows}))
    (tmp_path / "0002-re2-tt-v-r.timing.json").write_text(
        json.dumps(
            {"n1_ms": {"p50": 1.0}, "n2_p95_ms": {"Q1": 2.0}, "cases": [{"case": "re2tt_a_cpu_3", "diagnose_ms": 12.5}]}
        )
    )
    (tmp_path / "0003-synth-s1-v-r.json").write_text(json.dumps({"summary": {"by_size": {"small": {"ac1": 1.0}}}}))
    body = client.get("/api/v1/eval").json()
    assert body["run"] == "0002-re2-tt-v-r" and body["ac1"] == 0.5 and body["n2_p95_ms"] == {"Q1": 2.0}
    # the per-case table: sorted by case; a miss at @1 that hits @3; no_root_cause misses both
    assert body["per_case"] == [
        {"case": "re2tt_a_cpu_1", "split": "dev", "service": "a", "fault": "cpu", "top3": [], "hit1": False,
         "hit3": False, "confidence": None, "diagnose_ms": None, "variants": {}, "parts": {}},
        {"case": "re2tt_a_cpu_3", "split": "test", "service": "a", "fault": "cpu", "top3": ["b", "a"], "hit1": False,
         "hit3": True, "confidence": 0.4, "diagnose_ms": 12.5, "variants": {"no_pagerank": "a"},
         "parts": {"pagerank": 0.5}},
    ]  # fmt: skip
    # the run history (oldest first) and the synthetic suite, reported apart
    assert [h["run"] for h in body["history"]] == ["0001-re2-tt-v-r", "0002-re2-tt-v-r"] and body["history"][0][
        "ac1"
    ] == 0.0
    assert body["synth"]["run"] == "0003-synth-s1-v-r" and body["synth"]["by_size"]["small"]["ac1"] == 1.0
