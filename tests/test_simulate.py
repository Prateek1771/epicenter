"""Fault Simulator tests (LLD §7, §12): pure propagation and matching, then full diagnoses on the fixtures."""

import json
from pathlib import Path

import pytest

from api.ingest.seed import seed_indexes
from api.search.causal import diagnose
from api.search.simulate import Prediction, Rule, match, simulate, spearman, what_if

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).parent / "fixtures"
RULES = [  # the seeded rule table (seed/propagation_rules.yaml), as Rule records
    Rule("down->errors:upstream@datastore", ("down",), "errors", "upstream", 0.95, 15, "datastore"),
    Rule("errors+down->errors:upstream", ("errors", "down"), "errors", "upstream", 0.80, 30, None),
    Rule("errors+down->latency:upstream", ("errors", "down"), "latency", "upstream", 0.30, 30, None),
    Rule(
        "latency+cpu+saturation->errors:upstream",
        ("latency", "cpu", "saturation"),
        "errors",
        "upstream",
        0.25,
        60,
        None,
    ),
    Rule(
        "latency+cpu+saturation->latency:upstream",
        ("latency", "cpu", "saturation"),
        "latency",
        "upstream",
        0.90,
        20,
        None,
    ),
    Rule("mem->down:self", ("mem",), "down", "self", 0.40, 300, None),
    Rule("mem->latency:self", ("mem",), "latency", "self", 0.60, 120, None),
]
# c/C is called by m/M (15 rps); m/M takes 20 rps in total (10 from the entry point x/E, 10 from y/Y)
PATHS = [{"path": ["m/M", "c/C"], "rps": [15.0]}, {"path": ["x/E", "m/M", "c/C"], "rps": [10.0, 15.0]}]
INFO = {
    "c/C": {"service_kind": "app", "in_rps": 15.0},
    "m/M": {"service_kind": "app", "in_rps": 20.0},
    "x/E": {"service_kind": "app", "in_rps": 0.0},
}


def _p(preds, op, kind):
    return next((p for p in preds if (p.op, p.kind) == (op, kind)), None)


def test_hand_computed_two_hop_probability():
    preds = simulate("c/C", ["errors"], 100, PATHS, INFO, RULES, min_p=0.3, skew_s=15)
    # hop 1: share = 15 / 20 = 0.75 → 0.8 × 0.75 = 0.6; hop 2: x/E is an entry point → share 1 → 0.6 × 0.8 = 0.48
    assert _p(preds, "m/M", "errors").p == pytest.approx(0.6)
    assert _p(preds, "x/E", "errors").p == pytest.approx(0.48)
    assert _p(preds, "m/M", "latency") is None  # 0.3 × 0.75 = 0.225 < min_p: pruned
    assert _p(preds, "x/E", "errors").onset_window == (85, 160)  # [t − skew, t + 30 + 30]
    assert _p(preds, "c/C", "errors") == Prediction("c/C", "errors", 1.0, 0, ("c/C",), (85, 100))


def test_datastore_rule_needs_a_datastore():
    app = simulate("c/C", ["down"], 0, PATHS[:1], INFO, RULES, 0.3, 15)
    store = simulate("c/C", ["down"], 0, PATHS[:1], INFO | {"c/C": {"service_kind": "datastore"}}, RULES, 0.3, 15)
    assert _p(app, "m/M", "errors").p == pytest.approx(0.8 * 0.75)
    assert _p(store, "m/M", "errors").p == pytest.approx(0.95 * 0.75)


def test_self_rules_and_determinism():
    a = simulate("c/C", ["mem"], 0, PATHS, INFO, RULES, 0.3, 15)
    b = simulate("c/C", ["mem"], 0, list(reversed(PATHS)), INFO, RULES, 0.3, 15)
    assert a == b  # input order doesn't matter
    assert {(p.op, p.kind) for p in a if p.hops == 0} == {("c/C", "mem"), ("c/C", "latency"), ("c/C", "down")}


@pytest.mark.parametrize(
    "onsets, expected",
    [([10, 20, 30], 1.0), ([30, 20, 10], -1.0), ([10, 10, 10], None)],
)
def test_spearman(onsets, expected):
    assert spearman([1, 2, 3], onsets) == expected


def test_match_coverage_precision_order_and_windows():
    preds = simulate("c/C", ["errors"], 100, PATHS, INFO, RULES, 0.3, 15)
    observed = {
        "c/C": {"kinds": ["errors"], "onset": 100, "score": 0.9, "anomalies": []},
        "m/M": {"kinds": ["errors"], "onset": 110, "score": 0.8, "anomalies": []},
        "x/E": {"kinds": ["errors"], "onset": 120, "score": 0.7, "anomalies": []},
        "z/Z": {"kinds": ["cpu"], "onset": 50, "score": 0.5, "anomalies": []},  # not predicted
    }
    m = match(preds, observed)
    assert m["matched"] == ["c/C", "m/M", "x/E"] and m["unexplained"] == ["z/Z"]
    assert m["coverage"] == 0.75 and m["order"] == 1.0  # later hops broke later
    assert m["precision"] == 1.0  # every prediction happened
    assert m["footprint"] == pytest.approx(0.5 * 0.75 + 0.3 + 0.2)
    early = dict(observed, **{"m/M": {"kinds": ["errors"], "onset": 50, "score": 0.8, "anomalies": []}})
    assert "m/M" in match(preds, early)["unexplained"]  # broke before the cause: outside the window


@pytest.fixture
def load(graph):
    made = []

    def _load(name: str, fixture: str):
        g = graph.env(name)
        g.delete()
        seed_indexes(g)
        g.load_cypher(FIXTURES / fixture)
        made.append(g)
        return g

    yield _load
    for g in made:
        g.delete()


def _footprints(env, inc, run):
    out = {}
    for r in env.ro("run_hypotheses", inc=inc, run=run):
        fp = [s for rel, kind, s in r["evidence"] if kind == "footprint"]
        out[r["op"]] = fp[0] if fp else None
    return out


def test_true_cause_explains_more_than_the_loudest_victim(graph, load):
    env = load("test-sim-mini", "mini_graph.cypher")
    v = diagnose(graph, "test-sim-mini", "inc-1")
    cov = {r["op"]: r["coverage"] for r in v["ranking"]}
    # 3 of 4: the 4th anomaly (cart/GetCart) is deliberately unrelated in the fixture
    assert v["root_cause"] == "payment/Charge" and cov["payment/Charge"] == 0.75
    assert cov["checkout/PlaceOrder"] == 0.5 < cov["payment/Charge"]
    assert _footprints(env, "inc-1", v["run"])["payment/Charge"].startswith("explains 3 of 4 symptoms")
    assert v["second_cause"] is None  # one weak unexplained anomaly doesn't trigger round 2


def test_multi_fault_finds_a_second_root_cause(graph, load):
    env = load("test-sim-multi", "multi_fault.cypher")
    v = diagnose(graph, "test-sim-multi", "inc-m")
    assert (v["root_cause"], v["second_cause"]) == ("db/Query", "cache/Get")
    assert [(r["rank"], r["op"]) for r in env.ro("root_causes", inc="inc-m")] == [(1, "db/Query"), (2, "cache/Get")]


def test_healthy_baseline_is_no_root_cause(graph, load):
    env = load("test-sim-healthy", "healthy.cypher")
    v = diagnose(graph, "test-sim-healthy", "inc-h")
    [inc] = env.ro("incident", inc="inc-h")
    assert v["status"] == inc["status"] == "no_root_cause" and v["root_cause"] is None
    assert inc["summary"].startswith("Nothing in the graph explains this alert")
    assert env.ro("root_causes", inc="inc-h") == []


def test_quiet_symptom_with_a_weak_anomaly_is_no_root_cause(graph, load):
    # a lone weak anomaly covers itself 100%; with the alerting operation fine, it explains nothing the alert saw
    env = load("test-sim-quiet", "quiet_symptom.cypher")
    v = diagnose(graph, "test-sim-quiet", "inc-q")
    assert v["status"] == "no_root_cause" and v["root_cause"] is None
    assert env.ro("root_causes", inc="inc-q") == []


def test_a_weak_wobble_on_the_alerting_operation_itself_is_no_root_cause(graph, load):
    load("test-sim-weak-self", "weak_self.cypher")
    v = diagnose(graph, "test-sim-weak-self", "inc-w")
    assert v["status"] == "no_root_cause" and v["root_cause"] is None


@pytest.mark.parametrize(("api_self", "api_child", "cause"), [(40.0, 10.0, "api/List"), (1.1, 10.0, "db/Find")])
def test_datastore_latency_measured_inside_a_saturated_caller(graph, tmp_path, api_self, api_child, cause):
    # a client span carries its caller's scheduling lag: when the caller's own time grew far more than its waiting,
    # the datastore's "latency" is the caller's; when the caller only waited, the datastore really was slow
    text = (FIXTURES / "saturated_caller.cypher").read_text(encoding="utf-8")
    f = tmp_path / "case.cypher"
    f.write_text(text.replace("API_SELF", str(api_self)).replace("API_CHILD", str(api_child)), encoding="utf-8")
    env = graph.env("test-sim-saturated")
    env.delete()
    seed_indexes(env)
    env.load_cypher(f)
    try:
        v = diagnose(graph, "test-sim-saturated", "inc-s")
    finally:
        env.delete()
    assert v["root_cause"] == cause


def test_a_proxy_in_front_of_a_slow_app_fails_instead_of_waiting():
    # nginx ejects an overloaded upstream and answers 502: latency upstream → errors at a proxy, not latency
    proxy = Rule("latency+cpu+saturation->errors:upstream<proxy", ("latency", "cpu", "saturation"), "errors",
                 "upstream", 0.70, 30, None, "proxy")  # fmt: skip
    paths = [{"path": ["web/GET /", "api/List"], "rps": [20.0]}]
    info = {"web/GET /": {"service_kind": "proxy", "in_rps": 0.0}, "api/List": {"service_kind": "app", "in_rps": 20.0}}
    preds = simulate("api/List", ["latency"], 100, paths, info, [*RULES, proxy], 0.3, 15)
    assert {(p.op, p.kind) for p in preds if p.op == "web/GET /"} >= {("web/GET /", "errors")}
    app = {"web/GET /": {"service_kind": "app", "in_rps": 0.0}, "api/List": info["api/List"]}  # an app caller waits
    assert ("web/GET /", "errors") not in {(p.op, p.kind) for p in simulate("api/List", ["latency"], 100, paths, app,
                                                                         [*RULES, proxy], 0.3, 15)}  # fmt: skip


def test_what_if_matches_reverse_calls_with_traffic(graph, load):
    env = load("test-sim-whatif", "mini_graph.cypher")
    r = what_if(graph, "test-sim-whatif", "redis", "down", save=True)
    preds = r["predictions"]
    assert {p["op"] for p in preds if p["hops"] > 0} == {row["op"] for row in env.ro("Q6", cand="redis/GET")}
    assert preds == sorted(preds, key=lambda p: (p["hops"], p["op"], p["kind"]))
    first = next(p for p in preds if p["op"] == "cart/GetCart" and p["kind"] == "errors")
    assert (first["p"], first["team"]) == (0.95, "platform")  # datastore down rule, full traffic share
    saved = env.ro("simulation_predictions", id=r["simulation"])
    assert len(saved) == len(preds)


def test_v1_weights_skip_the_simulator(graph, load):
    env = load("test-sim-v1", "mini_graph.cypher")
    v = diagnose(graph, "test-sim-v1", "inc-1", weights_path=str(ROOT / "weights.v1.json"))
    assert v["root_cause"] == "payment/Charge" and v["explains"] is None
    assert all(fp is None for fp in _footprints(env, "inc-1", v["run"]).values())


def test_footprint_evidence_value_is_complete(graph, load):
    env = load("test-sim-value", "mini_graph.cypher")
    v = diagnose(graph, "test-sim-value", "inc-1")
    rows = env.ro("footprint_values", inc="inc-1", run=v["run"])
    charge = json.loads(next(r["value"] for r in rows if r["op"] == "payment/Charge"))
    assert {
        "coverage",
        "precision",
        "order",
        "matched",
        "missed",
        "unexplained",
        "predictions",
        "rules_version",
    } <= set(charge)
    assert charge["unexplained"] == ["cart/GetCart"]


def test_scattered_noise_does_not_make_a_second_cause(graph, load):
    env = load("test-sim-noise", "mini_graph.cypher")
    for n, (op, kind, onset) in enumerate([("checkout/GetQuote", "latency", 300), ("payment/Refund", "errors", 310)]):
        env.rw(
            "U2",
            op=op,
            id=f"an-inc-1-noise-{n}",
            incident="inc-1",
            kind=kind,
            onset=onset,
            score=0.5,
            self_ratio=None,
            child_ratio=None,
            ref=None,
            detector="short",
        )
    v = diagnose(graph, "test-sim-noise", "inc-1")
    # 3 unexplained anomalies trigger round 2, but no candidate explains half of them: no second cause
    assert v["root_cause"] == "payment/Charge" and v["second_cause"] is None
    assert any(r["round"] == 2 for r in env.ro("run_rounds", inc="inc-1", run=v["run"]))
