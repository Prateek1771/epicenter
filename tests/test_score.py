"""Scorer unit tests (LLD §6). Pure functions, no FalkorDB."""

import json
from pathlib import Path

import pytest

from api.search import score as sc

ROOT = Path(__file__).resolve().parents[1]
W = sc.load_weights(str(ROOT / "weights.json"))


def _h(op, onset, strength=0.5, kinds=("latency",), victim=False, self_caused=None, change=False, pr=0.1, ref=False):
    return {
        "op": op,
        "onset": onset,
        "strength": strength,
        "kinds": list(kinds),
        "victim": victim,
        "self_caused": self_caused,
        "change": change,
        "pagerank": pr,
        "footprint": 0.0,
        "refuted": ref,
    }


@pytest.mark.parametrize(
    "values, expected",
    [
        ([3.0, 1.0, 2.0], [1.0, 0.0, 0.5]),
        ([1.0, 1.0, 2.0], [0.25, 0.25, 1.0]),  # ties share the average rank
        ([None, 1.0, 2.0], [0.0, 0.0, 1.0]),  # None ranks last
        ([7.0], [1.0]),
        ([None, None], [0.0, 0.0]),
    ],
)
def test_rank_normalize(values, expected):
    assert sc.rank_normalize(values) == expected


@pytest.mark.parametrize(
    "kinds, victim, self_caused, fit",
    [
        (["latency"], True, True, 0.0),  # victim wins over everything
        (["latency"], False, True, 1.0),  # self time grew
        (["errors"], False, None, 1.0),  # its own mechanism
        (["latency"], False, None, 0.5),  # no ratios: mixed
        (["latency"], False, False, 0.5),
    ],
)
def test_mechanism_fit(kinds, victim, self_caused, fit):
    assert sc.mechanism_fit(kinds, victim, self_caused) == fit


def test_refuted_loses_one_point():
    a, b = sc.features([_h("a/x", 10), _h("b/y", 10)])
    b_ref = sc.features([_h("a/x", 10), _h("b/y", 10, ref=True)])[1]
    assert sc.score(b, W) - sc.score(b_ref, W) == pytest.approx(1.0)


def test_earlier_onset_and_change_raise_the_score():
    early, late = sc.features([_h("a/x", 10, change=True), _h("b/y", 50)])
    assert early["onset_earliness"] == 1.0 and late["onset_earliness"] == 0.0
    assert sc.score(early, W) > sc.score(late, W)


def test_confidence():
    assert sc.confidence([0.5, 0.5], W["k"]) == 0.5
    assert sc.confidence([0.9, 0.1], W["k"]) > 0.99
    assert sc.confidence([0.4], W["k"]) == pytest.approx(1 / (1 + 2.718281828 ** (-W["k"] * 0.4)), abs=1e-6)
    assert sc.confidence([], W["k"]) == 0.0


def test_tie_break_score_then_onset_then_id():
    hs = [
        {"op": "b/x", "onset": 5, "score": 0.5},
        {"op": "a/x", "onset": 5, "score": 0.5},
        {"op": "c/x", "onset": 1, "score": 0.5},
        {"op": "d/x", "onset": None, "score": 0.9},
    ]
    assert [h["op"] for h in sc.ranking(hs)] == ["d/x", "c/x", "a/x", "b/x"]


def test_score_parts_json_is_byte_stable():
    f = sc.features([_h("a/x", 10), _h("b/y", 20)])[0]
    a = sc.score_parts_json(f, {"pagerank_impl": "falkordb"})
    b = sc.score_parts_json(dict(reversed(list(f.items()))), {"pagerank_impl": "falkordb"})
    assert a == b and json.loads(a)["pagerank_impl"] == "falkordb"


def test_weights_files_are_valid():
    v1 = sc.load_weights(str(ROOT / "weights.v1.json"))
    assert "footprint" not in v1["w"] and W["w"]["footprint"] > 0


def test_weights_validation_rejects_bad_files(tmp_path):
    bad = dict(W, w=dict(W["w"], strength=0.9))
    p = tmp_path / "w.json"
    p.write_text(json.dumps(bad))
    with pytest.raises(ValueError, match="sum"):
        sc.load_weights(str(p))
