"""Replay a tiny synthetic RCAEval case (same Parquet layout as the real dataset) into a throwaway env graph."""

import numpy as np
import pandas as pd
import pytest

from api.ingest.rcaeval import RcaevalAdapter, replay
from api.search.causal import diagnose

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
    assert summary["symptom"] == "client/load"  # the load generator, calling every root operation
    assert summary["gaps"] == ["logs"]
    assert summary["calls"] == 3  # client→front, front→back, back→db
    assert set(labels) == {"Anomaly", "Incident", "Operation", "Service"}  # no span-level nodes
    assert labels["Operation"] == 5  # client + 3 in call pairs + the orphan, upserted so its anomaly isn't dropped
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


def test_replay_then_diagnose_is_deterministic(graph, case_dir):
    env = graph.env(ENV)
    env.delete()
    try:
        inc = replay(case_dir, ENV, graph)["incident"]
        a = diagnose(graph, ENV, inc)
        b = diagnose(graph, ENV, inc)
        ra = [{k: v for k, v in r.items() if k != "id"} for r in env.ro("run_hypotheses", inc=inc, run=1)]
        rb = [{k: v for k, v in r.items() if k != "id"} for r in env.ro("run_hypotheses", inc=inc, run=2)]
    finally:
        env.delete()
    assert ra == rb  # identical score_parts JSON and statuses, run after run (N3)
    assert a["root_cause"] == b["root_cause"] == "db/Find"


def test_rereplay_retires_anomalies_and_keeps_old_runs_intact(graph, case_dir):
    env = graph.env(ENV)
    env.delete()
    try:
        first = replay(case_dir, ENV, graph)
        inc = first["incident"]
        current_before = env.ro("incident_anomalies", inc=inc)
        diagnose(graph, ENV, inc)
        cited_before = env.ro("run_evidence_about", inc=inc, run=1)

        second = replay(case_dir, ENV, graph)
        current_after = env.ro("incident_anomalies", inc=inc)
        cited_after = env.ro("run_evidence_about", inc=inc, run=1)
        retired = env.ro("incident_anomalies", inc=f"{inc}@i1")
        v = diagnose(graph, ENV, inc)
        ingests = {r["ingest"] for r in env.ro("run_ingests", inc=inc)}
    finally:
        env.delete()

    assert (first["ingest"], second["ingest"]) == (1, 2)
    assert current_after == current_before  # readers see only the current ingest, unchanged
    retired_set = {tuple(sorted(r.items())) for r in retired}
    assert retired_set == {tuple(sorted(dict(r, id=r["id"] + "@i1").items())) for r in current_before}  # not deleted
    assert cited_before, "run 1 should cite at least one anomaly (victim evidence)"
    # run 1's evidence keeps its ABOUT edges; they now point at the retired ingest
    # (as sets: the "@i1" suffix changes string sort order, e.g. "-1@i1" now sorts after "-10@i1")
    assert {(e["evidence"], e["anomaly"]) for e in cited_after} == {
        (e["evidence"], e["anomaly"] + "@i1") for e in cited_before
    }
    assert {e["anomaly_incident"] for e in cited_after} == {f"{inc}@i1"}
    assert v["run"] == 2 and v["ingest"] == 2 and ingests == {1, 2}


def test_logs_skip_rows_without_a_message(case_dir):
    """Some RE2-TT cases have log rows whose message is null (pd.NA); they carry nothing; skip, no crash."""
    pd.DataFrame(
        {"timestamp": [T, T + 1], "container_name": ["db", "db"], "message": pd.array(["x ERROR boom", pd.NA])}
    ).to_parquet(case_dir / "logs.parquet")
    lines = list(RcaevalAdapter(case_dir, ENV).logs(T - 10, T + 10))
    assert [(ln.level, ln.text) for ln in lines] == [("ERROR", "x ERROR boom")]


def test_download_of_an_unknown_case_fails_clearly(tmp_path, monkeypatch):
    """Every file 404s for a name that isn't in the dataset: say so, don't leave an empty dir behind a 'not found'."""
    import urllib.error

    from api.ingest import rcaeval

    def not_found(url, timeout):
        raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)

    monkeypatch.setattr(rcaeval.urllib.request, "urlopen", not_found)
    with pytest.raises(ValueError, match="inject_time.txt not on Hugging Face"):
        rcaeval.download("re2tt_nope_cpu_1", tmp_path)
