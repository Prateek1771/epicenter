"""Replay a tiny synthetic RCAEval case (same Parquet layout as the real dataset) into a throwaway env graph."""

import numpy as np
import pandas as pd
import pytest

from api.ingest.rcaeval import replay

T = 1_700_000_000  # inject time
ENV = "test-rcaeval"


@pytest.fixture
def case_dir(tmp_path):
    """front/GET / → back/Call → db/Find, one trace per second for 24 min; db/Find slows down 10× after T."""
    d = tmp_path / "re2tt_back_delay_1"
    d.mkdir()
    (d / "inject_time.txt").write_text(str(T))
    rows = []
    for sec in range(T - 720, T + 720):
        slow = sec >= T
        db = 200_000 if slow else 20_000
        back = db + 5_000
        front = back + 5_000
        tid = f"t{sec}"
        rows += [
            (tid, f"{tid}-a", None, "front", "GET /", sec * 1_000_000, front, 200),
            (tid, f"{tid}-b", f"{tid}-a", "back", "Call", sec * 1_000_000 + 10, back, 200),
            (tid, f"{tid}-c", f"{tid}-b", "db", "Find", sec * 1_000_000 + 20, db, None),
            # orphan: its parent span is missing from the data. Slows down 50×, but it is not an entry point.
            (tid, f"{tid}-o", f"{tid}-lost", "back", "Orphan", sec * 1_000_000 + 30, 50_000 if slow else 1_000, None),
        ]
    cols = ["traceID", "spanID", "parentSpanID", "serviceName", "operationName", "startTime", "duration", "statusCode"]
    traces = pd.DataFrame(rows, columns=cols)
    traces["statusCode"] = traces["statusCode"].astype("Int64")
    traces.to_parquet(d / "traces.parquet")
    secs = np.arange(T - 720, T + 720)
    cpu = np.where(secs >= T, 0.9, 0.2) + np.sin(secs) * 0.01  # deterministic wobble
    pd.DataFrame({"time": secs, "db_cpu": cpu, "front_workload": np.full(len(secs), 1.0)}).to_parquet(
        d / "metrics.parquet"
    )
    return d  # no logs.parquet: the replay must record the gap


def test_replay_builds_topology_and_anomalies(graph, case_dir):
    env = graph.env(ENV)
    env.delete()
    try:
        summary = replay(case_dir, ENV, graph)
        first = env.ro("incident_anomalies", inc=summary["incident"])
        replay(case_dir, ENV, graph)
        second = env.ro("incident_anomalies", inc=summary["incident"])
        labels = {r["label"]: r["n"] for r in env.ro("label_counts")}
    finally:
        env.delete()

    assert first == second  # replay is idempotent and deterministic
    assert summary["symptom"] == "front/GET /"
    assert summary["gaps"] == ["logs"]
    assert summary["calls"] == 2
    assert set(labels) == {"Anomaly", "Incident", "Operation", "Service"}  # no span-level nodes
    assert labels["Operation"] == 4  # 3 in call pairs + the orphan, upserted so its anomaly isn't dropped
    found = {(r["op"], r["kind"]) for r in first}
    assert {("db/Find", "latency"), ("db/Find", "cpu"), ("back/Orphan", "latency")} <= found
    assert len(first) == summary["anomalies"]  # every detected anomaly reached the graph
    db_lat = next(r for r in first if (r["op"], r["kind"]) == ("db/Find", "latency"))
    assert abs(db_lat["onset"] - T) <= 10 and db_lat["self_ratio"] > 5


def test_inject_time_is_not_a_change(graph, case_dir):
    env = graph.env(ENV)
    env.delete()
    try:
        replay(case_dir, ENV, graph)
        labels = {r["label"] for r in env.ro("label_counts")}
    finally:
        env.delete()
    assert "Change" not in labels
