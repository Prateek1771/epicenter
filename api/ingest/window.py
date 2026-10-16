"""One ingest window, any adapter (LLD §3.1): baseline + incident window → detectors → graph.

RCAEval replay and live environments run the same steps; only the adapter differs. The adapter brings `calls`,
`series`, `logs`, `entry_ops()` (service → its busiest inbound op, where log anomalies attach), `gaps` and
`source` (the prefix of every anomaly `ref`).
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd

from api.config import get_settings
from api.graph import Graph
from api.ingest import detect, logs, write
from api.ingest.base import AnomalyRow, Series
from api.ingest.seed import seed_indexes


def ingest_window(
    ad, env_name: str, graph: Graph, incident: str, symptom: str, t: int, until: int | None = None
) -> dict:
    """The window ends on the last *complete* bucket: at `t + WINDOW_AFTER_S`, or at `until` for a live env whose data
    ends now. Either edge can fall mid-bucket, and a half-filled last bucket reads as a traffic drop on every busy
    operation (a false `down` everywhere)."""
    s = get_settings()
    weights = json.loads(Path(s.weights_path).read_text(encoding="utf-8"))
    cfg = weights["detect"]
    base = (t - s.baseline_s - 120, t - 120)
    end = min(t + s.window_after_s, until) if until is not None else t + s.window_after_s
    end = end // cfg["bucket_s"] * cfg["bucket_s"] - 1
    window = (t - 120, end)

    calls = list(ad.calls(*base))
    series = list(ad.series(base[0], window[1]))
    rows = detect.detect_window(series, t, cfg, s.baseline_s, window[1] - t)

    slow_kinds = set(s.slow_burn_kinds.split(","))
    lookback = (t - s.slow_burn_lookback_s, t)
    for sr in series:
        if sr.kind in slow_kinds and sr.metric.startswith("metric:"):
            keep = (sr.ts >= lookback[0]) & (sr.ts <= lookback[1])
            minute = sr.ts[keep] // 60 * 60
            if len(minute) == 0:
                continue
            per_min = pd.Series(sr.values[keep]).groupby(minute).mean()
            one_min = Series(
                sr.op, sr.metric, sr.kind, per_min.index.to_numpy(dtype=np.int64), per_min.to_numpy(), sr.ref
            )
            if hit := detect.detect_slow_burn(one_min, t, cfg):
                rows.append(hit)

    entry = ad.entry_ops()
    for la in logs.detect_logs(ad.logs(base[0], window[1]), base, window, cfg):
        if la.service in entry:
            ref = f"{ad.source}:logs:{la.service}"
            rows.append(
                AnomalyRow(
                    entry[la.service], la.kind, la.onset, la.score, ref=ref, signal=la.signal, signal_text=la.template
                )
            )

    rows = detect.assign_ids(incident, detect.merge(rows))

    env = graph.env(env_name)
    seed_indexes(env)
    n_calls = write.write_topology(env, calls, ts=base[1])
    # changes before anomalies' readers run: the scorer's change_match looks back from the onset
    n_changes = 0
    for ch in sorted(ad.changes(base[0]), key=lambda c: (c.ts, c.id)):
        write.write_change(env, ch)
        n_changes += 1
    write.open_incident(env, incident, symptom, t, weights["version"], ad.gaps)
    ingest = write.new_ingest(env, incident)
    write.write_anomalies(env, incident, rows)
    top = sorted(rows, key=lambda r: (-r.score, r.op, r.kind))[:5]
    return {
        "incident": incident,
        "env": f"env:{env_name}",
        "alert_ts": t,
        "symptom": symptom,
        "ingest": ingest,
        "calls": n_calls,
        "changes": n_changes,
        "anomalies": len(rows),
        "by_kind": {k: sum(r.kind == k for r in rows) for k in sorted({r.kind for r in rows})},
        "top": [f"{r.op} {r.kind} {r.score}" for r in top],
        "gaps": ad.gaps,
    }
