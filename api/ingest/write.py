"""The only place ingest writes to the graph. Every adapter's output goes through these functions (U1–U5)."""

from collections.abc import Iterable

from api.graph import EnvGraph
from api.ingest.base import AnomalyRow, CallAgg, ChangeEvent


def _name(op_id: str) -> str:
    return op_id.split("/", 1)[1]


def write_topology(env: EnvGraph, calls: Iterable[CallAgg], ts: int) -> int:
    """One roll-up tick: every caller→callee pair in one batched U1 (FalkorDB serializes writes per graph)."""
    rows = [
        {
            "caller_svc": c.caller_svc,
            "caller_op": c.caller_op,
            "caller_name": _name(c.caller_op),
            "caller_kind": c.caller_kind,
            "callee_svc": c.callee_svc,
            "callee_kind": c.callee_kind,
            "callee_op": c.callee_op,
            "callee_name": _name(c.callee_op),
            "rps": c.rps,
            "p95_ms": c.p95_ms,
            "err_rate": c.err_rate,
        }
        for c in sorted(calls, key=lambda c: (c.caller_op, c.callee_op))
    ]
    for i in range(0, len(rows), 500):
        env.rw("U1_batch", rows=rows[i : i + 500], ts=ts)
    return len(rows)


def open_incident(env: EnvGraph, incident: str, symptom: str, opened_at: int, weights_version: str, gaps: list[str]):
    env.rw(
        "U4_open_incident",
        id=incident,
        symptom=symptom,
        opened_at=opened_at,
        weights_version=weights_version,
        gaps=sorted(gaps),
    )


def new_ingest(env: EnvGraph, incident: str) -> int:
    """Start a new ingest of the incident's anomalies. The previous ingest's anomalies are retired, not deleted:
    re-keyed `<incident>@i<k>`, so readers only see the new ones and older diagnosis runs keep their ABOUT edges."""
    [row] = env.rw("next_ingest", inc=incident)
    env.rw("retire_anomalies", inc=incident, suffix=f"@i{row['retired']}")
    return row["ingest"]


def write_anomalies(env: EnvGraph, incident: str, rows: list[AnomalyRow]) -> int:
    ops = sorted({r.op for r in rows})
    if ops:
        env.rw("U6_ops", rows=[{"svc": op.split("/", 1)[0], "op": op, "name": _name(op)} for op in ops])
    payload = [
        {
            "id": r.id,
            "op": r.op,
            "kind": r.kind,
            "onset": r.onset,
            "score": r.score,
            "self_ratio": r.self_ratio,
            "child_ratio": r.child_ratio,
            "ref": r.ref,
            "detector": r.detector,
        }
        for r in rows
    ]
    for i in range(0, len(payload), 500):
        env.rw("U2_batch", rows=payload[i : i + 500], incident=incident)
    signals = [{"anomaly": r.id, "signal": r.signal, "text": r.signal_text} for r in rows if r.signal]
    if signals:
        env.rw("U5_signal", rows=signals, incident=incident)
    return len(payload)


def write_change(env: EnvGraph, ch: ChangeEvent) -> None:
    env.rw(
        "U3",
        service=ch.service,
        service_kind=ch.service_kind,
        id=ch.id,
        type=ch.type,
        ts=ch.ts,
        summary=ch.summary,
        ref=ch.ref,
    )
