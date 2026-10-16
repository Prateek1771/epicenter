"""Detector unit tests (LLD §12 slow-burn row, phase 2 acceptance). Pure functions, no FalkorDB."""

import json
from pathlib import Path

import numpy as np
import pytest

from api.ingest.base import AnomalyRow, LogLine, Series
from api.ingest.detect import (
    assign_ids,
    detect_down,
    detect_series,
    detect_slow_burn,
    detect_window,
    merge,
    ratio_p95,
    to_score,
)
from api.ingest.logs import detect_logs

CFG = json.loads((Path(__file__).resolve().parents[1] / "weights.json").read_text())["detect"]
T = 10_000  # alert time
BASE = (T - 600, T - 120)
WINDOW = (T - 120, T + 300)
rng = np.random.default_rng(0)  # tests only; product code never uses randomness


def _series(values, step=5, start=T - 600, kind="latency", op="svc/op", metric="latency"):
    ts = np.arange(start, start + step * len(values), step, dtype=np.int64)
    return Series(op, metric, kind, ts, np.asarray(values, dtype=float))


def test_flat_series_is_not_an_anomaly():
    s = _series(100 + rng.normal(0, 1, 180))
    assert detect_series(s, BASE, WINDOW, CFG) is None


def test_step_change_onset_at_the_step():
    values = 100 + rng.normal(0, 1, 180)
    step_at = T + 30
    s = _series(values)
    values[s.ts >= step_at] += 200
    row = detect_series(_series(values), BASE, WINDOW, CFG)
    assert row is not None and row.kind == "latency"
    assert abs(row.onset - step_at) <= 2 * CFG["bucket_s"]
    assert row.score > 0.8


def test_single_spike_is_ignored():
    values = 100 + rng.normal(0, 1, 180)
    values[150] += 500  # one noisy bucket in the window
    assert detect_series(_series(values), BASE, WINDOW, CFG) is None


def test_drop_is_not_an_anomaly():
    values = 100 + rng.normal(0, 1, 180)
    s = _series(values)
    values[s.ts >= T] -= 80
    assert detect_series(_series(values), BASE, WINDOW, CFG) is None


def test_slow_burn_found_only_by_the_slow_pass():
    # 6 h of 1-minute memory samples: flat for 3 h, then a steady 3 h climb up to the alert
    minutes = np.arange(T - 6 * 3600, T + 60, 60, dtype=np.int64)
    climb_start = T - 3 * 3600
    values = 100 + rng.normal(0, 3, len(minutes))
    rising = minutes >= climb_start
    values[rising] += (minutes[rising] - climb_start) / 60 * (300 / 180)
    s = Series("svc/op", "metric:mem", "mem", minutes, values)

    assert detect_series(s, BASE, WINDOW, CFG) is None  # the 10-minute baseline already looks "normal"
    row = detect_slow_burn(s, T, CFG)
    assert row is not None and row.detector == "slow_burn" and row.kind == "mem"
    assert abs(row.onset - climb_start) <= 300


def test_slow_burn_ignores_flat_series():
    minutes = np.arange(T - 6 * 3600, T + 60, 60, dtype=np.int64)
    s = Series("svc/op", "metric:mem", "mem", minutes, 100 + rng.normal(0, 3, len(minutes)))
    assert detect_slow_burn(s, T, CFG) is None


def test_merge_keeps_earlier_onset_and_higher_score():
    short = AnomalyRow("svc/op", "mem", onset=T, score=0.9, detector="short", self_ratio=1.2)
    slow = AnomalyRow("svc/op", "mem", onset=T - 3600, score=0.7, detector="slow_burn")
    [m] = merge([short, slow])
    assert (m.onset, m.score, m.detector, m.self_ratio) == (T - 3600, 0.9, "slow_burn", 1.2)


def test_down_needs_a_long_silence_for_the_rate():
    busy = np.where(np.arange(T - 600, T + 300, 5) < T + 60, 10.0, 0.0)  # 2 rps, stops 60 s after the alert
    row = detect_down(_series(busy, kind="aux", metric="count"), BASE, T, WINDOW[1], 5, CFG)
    assert row is not None and row.onset == T + 60
    sparse = np.zeros(180)
    sparse[::12] = 1.0  # one call a minute: a 60 s gap is normal
    sparse[np.arange(T - 600, T + 300, 5) >= T + 200] = 0
    assert detect_down(_series(sparse, kind="aux", metric="count"), BASE, T, WINDOW[1], 5, CFG) is None


def test_self_child_ratio():
    base = np.r_[np.full(96, 10.0), np.full(84, 40.0)]
    assert ratio_p95(_series(base), BASE, WINDOW) == pytest.approx(4.0, rel=0.01)


def test_detect_window_attaches_ratios_to_latency():
    lat = 100 + rng.normal(0, 1, 180)
    s = _series(lat)
    lat[s.ts >= T] += 300
    self_ms = np.r_[np.full(96, 10.0), np.full(84, 50.0)]
    child_ms = np.full(180, 90.0)
    rows = detect_window(
        [
            _series(lat),
            _series(self_ms, kind="aux", metric="self_ms"),
            _series(child_ms, kind="aux", metric="child_ms"),
        ],
        T,
        CFG,
        baseline_s=480,
        after_s=300,
    )
    [row] = rows
    assert row.self_ratio == pytest.approx(5.0, rel=0.01) and row.child_ratio == pytest.approx(1.0)


def test_logs_new_template_and_burst():
    lines = [LogLine("svc", T - 500 + i, "INFO", f"user {i} logged in") for i in range(0, 400, 10)]
    lines += [LogLine("svc", T - 400 + i, "WARN", f"slow query took {i} ms") for i in (0, 200)]
    lines += [LogLine("svc", T + i, "WARN", f"slow query took {i} ms") for i in range(40)]
    lines += [LogLine("svc", T + 10 + i, "ERROR", f"connection refused to db-{i}:27017") for i in range(12)]
    found = {(a.kind, a.template) for a in detect_logs(lines, BASE, WINDOW, CFG)}
    kinds = sorted(k for k, _ in found)
    assert kinds == ["log_burst", "new_template"]
    assert any("connection refused" in t for k, t in found if k == "new_template")


def test_log_burst_onset_is_when_the_rate_rose():
    # a template logged every 20 s all along, then 10 lines a second from T + 60
    steady = [LogLine("svc", t, "INFO", f"heartbeat seq {t}") for t in range(BASE[0], WINDOW[1], 20)]
    burst = [LogLine("svc", T + 60 + i // 10, "INFO", f"heartbeat seq {i}") for i in range(200)]
    [a] = detect_logs(steady + burst, BASE, WINDOW, CFG)
    assert a.kind == "log_burst"
    assert T + 55 <= a.onset <= T + 65  # not the window start (T − 120), where the template first appears


def test_ids_follow_sorted_order():
    rows = [AnomalyRow("b/op", "errors", 20, 0.5), AnomalyRow("a/op", "latency", 20, 0.5), AnomalyRow("c", "cpu", 5, 1)]
    assert [(r.op, r.id) for r in assign_ids("inc-9", rows)] == [
        ("c", "an-inc-9-1"),
        ("a/op", "an-inc-9-2"),
        ("b/op", "an-inc-9-3"),
    ]


def test_score_mapping():
    assert [to_score(z) for z in (0, 4, 8, 16)] == [0.0, 0.3935, 0.6321, 0.8647]
