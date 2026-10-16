"""Incident signature (ADR 0008): layout, normalization, determinism across processes."""

import math
import subprocess
import sys

from api.search.signature import CHANGE_TYPES, DIMS, KINDS, signature, template_slot

ARGS = {
    "root_kinds": ["errors", "errors", "latency"],
    "hops": 2,
    "root_service_kind": "app",
    "change_types": ["flag"],
    "run_kinds": ["errors", "errors", "latency", "cpu"],
    "op_service_kinds": ["app", "app", "datastore"],
    "templates": ["payment failed: <*>", "retrying <*>"],
    "second_cause": False,
}


def test_layout_and_norm():
    v = signature(**ARGS)
    assert len(v) == DIMS and math.isclose(sum(x * x for x in v), 1.0, abs_tol=1e-4)
    assert v[KINDS.index("errors")] > v[KINDS.index("latency")] > 0 and v[KINDS.index("down")] == 0  # root kinds
    assert v[8 + KINDS.index("cpu")] > 0  # run kinds
    assert [v[16 + i] > 0 for i in range(4)] == [False, False, True, False]  # hops one-hot
    assert [v[20 + i] > 0 for i in range(5)] == [t == "flag" for t in CHANGE_TYPES]
    assert v[26] > 0 and v[25] == v[27] == 0  # root on an app service
    assert v[28] > 0 and v[29] > v[28] and v[31] == 0  # share of datastore vs app ops; no second cause
    assert sum(1 for x in v[32:] if x > 0) == len({template_slot(t) for t in ARGS["templates"]})


def test_deterministic_and_order_independent():
    assert signature(**ARGS) == signature(**ARGS)
    shuffled = ARGS | {"templates": list(reversed(ARGS["templates"])), "op_service_kinds": ["datastore", "app", "app"]}
    assert signature(**shuffled) == signature(**ARGS)
    assert signature(**(ARGS | {"hops": 7}))[19] > 0  # 3+ bucket


def test_template_hash_is_stable_across_processes():
    # Python's hash() is salted per process; blake2b isn't, so recall survives restarts and works across machines
    code = "from api.search.signature import template_slot; print(template_slot('payment failed: <*>'))"
    other = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True).stdout.strip()
    assert int(other) == template_slot("payment failed: <*>")


def test_nothing_to_describe_is_all_zero():
    empty = signature([], None, None, [], [], [], [], False)
    assert empty == [0.0] * DIMS
