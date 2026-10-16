"""Deterministic detectors (LLD §3.2). Pure functions: series in, AnomalyRow out, no I/O.

Parameters come from weights.json → "detect" (passed in as `cfg`), so phase 10 can freeze them.

Score mapping: `score = 1 − exp(−z / 8)`, so z 4 → 0.39, 8 → 0.63, 16 → 0.86, 24 → 0.95. Log and slow-burn detectors
feed a ratio into the same curve, so all kinds share one 0..1 scale.
"""

import math
from collections.abc import Iterable

import numpy as np
import ruptures

from api.ingest.base import AnomalyRow, Series

ANOMALY_KINDS = {"latency", "errors", "cpu", "mem", "saturation", "log_burst", "new_template", "down"}


def to_score(z: float) -> float:
    return round(1.0 - math.exp(-max(z, 0.0) / 8.0), 4)


def robust_z(base: np.ndarray, x: np.ndarray, cfg: dict) -> np.ndarray:
    """z = (x − median_base) / (1.4826 · MAD_base + ε), with ε relative to the baseline level so a flat baseline
    doesn't turn noise into huge z."""
    med = float(np.median(base))
    mad = float(np.median(np.abs(base - med)))
    eps = cfg["eps_abs"] + cfg["eps_rel"] * abs(med)
    return (x - med) / (1.4826 * mad + eps)


def pelt_breaks(ts: np.ndarray, x: np.ndarray, cfg: dict) -> list[int]:
    """PELT change points (rbf cost) as timestamps."""
    if len(x) < 4:
        return []
    algo = ruptures.Pelt(model="rbf", min_size=2, jump=1).fit(x.reshape(-1, 1))
    return [int(ts[b]) for b in algo.predict(pen=cfg["pelt_pen"])[:-1]]  # the last breakpoint is always len(x)


def sustained(z: np.ndarray, k: int) -> np.ndarray:
    """z level held for k consecutive points (rolling minimum), aligned to the first point of each run."""
    if k <= 1 or len(z) < k:
        return z if k <= 1 else np.full(1, -np.inf)
    return np.lib.stride_tricks.sliding_window_view(z, k).min(axis=1)


def detect_series(s: Series, base: tuple[int, int], window: tuple[int, int], cfg: dict) -> AnomalyRow | None:
    """Short pass on one series. Upward z only (a drop in latency or CPU isn't a fault), held for `sustain` points
    so one noisy bucket doesn't count."""
    if s.kind not in ANOMALY_KINDS:
        return None
    in_base = (s.ts >= base[0]) & (s.ts < base[1])
    in_win = (s.ts >= window[0]) & (s.ts <= window[1])
    if in_base.sum() < cfg["min_points"] or in_win.sum() == 0:
        return None
    zs = sustained(robust_z(s.values[in_base], s.values[in_win], cfg), cfg["sustain"])
    zmax = float(np.max(zs))
    if zmax < cfg["z"]:
        return None
    first_hit = int(s.ts[in_win][int(np.argmax(zs >= cfg["z"]))])
    # Onset: the last PELT change point between the window start and the first sustained crossing, i.e. where the
    # rise began; the crossing itself if PELT finds none there.
    # PELT is O(n²): fit only from 2 min before the window to 1 min after the crossing, the only place the onset can be
    span = (s.ts >= window[0] - 120) & (s.ts <= first_hit + 60)
    before = [b for b in pelt_breaks(s.ts[span], s.values[span], cfg) if window[0] <= b <= first_hit]
    onset = before[-1] if before else first_hit
    return AnomalyRow(op=s.op, kind=s.kind, onset=onset, score=to_score(zmax), ref=s.ref)


def ratio_p95(s: Series, base: tuple[int, int], window: tuple[int, int]) -> float | None:
    """p95 in the window over p95 in the baseline, for the self/child helper series."""
    b = s.values[(s.ts >= base[0]) & (s.ts < base[1])]
    w = s.values[(s.ts >= window[0]) & (s.ts <= window[1])]
    if len(b) == 0 or len(w) == 0:
        return None
    return round(float(np.percentile(w, 95)) / (float(np.percentile(b, 95)) + 1e-9), 3)


def detect_down(
    count: Series, base: tuple[int, int], t_alert: int, end: int, step: int, cfg: dict
) -> AnomalyRow | None:
    """`down`: the operation had traffic in the baseline, then went silent after the alert for long enough that its
    baseline rate would have produced ≥ `down_min_base` calls in the gap (so sparse operations don't count)."""
    in_base = (count.ts >= base[0]) & (count.ts < base[1])
    base_rate = count.values[in_base].sum() / max(base[1] - base[0], 1)
    after = count.ts[(count.ts >= t_alert) & (count.ts <= end) & (count.values > 0)]
    onset = int(after.max()) + step if len(after) else t_alert
    if base_rate * (end - onset) < cfg["down_min_base"]:
        return None
    return AnomalyRow(op=count.op, kind="down", onset=onset, score=to_score(cfg["down_z"]), ref=count.ref)


def detect_window(series: Iterable[Series], t_alert: int, cfg: dict, baseline_s: int, after_s: int) -> list[AnomalyRow]:
    """Short pass over every series: baseline [t − baseline_s − 120, t − 120], window [t − 120, t + after_s]."""
    base = (t_alert - baseline_s - 120, t_alert - 120)
    window = (t_alert - 120, t_alert + after_s)
    by_key = sorted(series, key=lambda s: (s.op, s.metric))
    aux = {(s.op, s.metric): s for s in by_key if s.kind == "aux"}
    rows = []
    for s in by_key:
        if s.kind == "aux":
            if s.metric == "count" and (row := detect_down(s, base, t_alert, window[1], cfg["bucket_s"], cfg)):
                rows.append(row)
            continue
        row = detect_series(s, base, window, cfg)
        if row is None:
            continue
        if row.kind == "latency" and (s.op, "self_ms") in aux and (s.op, "child_ms") in aux:
            row.self_ratio = ratio_p95(aux[(s.op, "self_ms")], base, window)
            row.child_ratio = ratio_p95(aux[(s.op, "child_ms")], base, window)
        rows.append(row)
    return merge(rows)


# --- Slow-burn pass (LLD §3.2): problems that build over hours ---


def mann_kendall_p(x: np.ndarray) -> float:
    """One-sided p-value for a monotonic increase (normal approximation, ties ignored)."""
    n = len(x)
    if n < 10:
        return 1.0
    i, j = np.triu_indices(n, k=1)
    s = float(np.sign(x[j] - x[i]).sum())
    var = n * (n - 1) * (2 * n + 5) / 18.0
    if s <= 0:
        return 1.0
    z = (s - 1) / math.sqrt(var)
    return 0.5 * math.erfc(z / math.sqrt(2))


def theil_sen(ts: np.ndarray, x: np.ndarray) -> float:
    """Median of pairwise slopes (units per second)."""
    i, j = np.triu_indices(len(x), k=1)
    dt = (ts[j] - ts[i]).astype(float)
    return float(np.median((x[j] - x[i]) / np.where(dt == 0, 1.0, dt)))


def hinge_onset(ts: np.ndarray, x: np.ndarray) -> int:
    """Where a climb started: the split that best fits "flat, then linear". PELT's rbf cost reacts to level shifts and
    places the start of a gentle ramp tens of minutes late, so the slow-burn pass uses this instead."""
    t = (ts - ts[0]).astype(float)
    best, best_k = np.inf, 0
    for k in range(2, len(x) - 2):
        flat = x[:k] - x[:k].mean()
        coef = np.polyfit(t[k:], x[k:], 1)
        sse = float(flat @ flat) + float(np.sum((x[k:] - np.polyval(coef, t[k:])) ** 2))
        if coef[0] > 0 and sse < best:
            best, best_k = sse, k
    return int(ts[best_k])


def detect_slow_burn(s: Series, t_alert: int, cfg: dict, limit: float | None = None) -> AnomalyRow | None:
    """`s` is a 1-minute series over [t − SLOW_BURN_LOOKBACK_S, t]. Anomaly if the trend is significant (Mann-Kendall,
    Theil-Sen slope > 0) and the value grew ≥ ratio× or crossed `limit_frac` of a known limit. Onset = hinge fit."""
    keep = s.ts <= t_alert
    ts, x = s.ts[keep], s.values[keep]
    if len(x) < 10 or mann_kendall_p(x) >= cfg["slow_burn_p"] or theil_sen(ts, x) <= 0:
        return None
    head, tail = float(np.median(x[:5])), float(np.median(x[-5:]))
    ratio = tail / (abs(head) + 1e-9)
    if ratio < cfg["slow_burn_ratio"] and not (limit and tail >= cfg["slow_burn_limit_frac"] * limit):
        return None
    onset = hinge_onset(ts, x)
    # ratio 1.5 → z-equivalent 8 → 0.63; ratio 3 → ~0.92
    return AnomalyRow(
        op=s.op, kind=s.kind, onset=onset, score=to_score(16 * (ratio - 1)), detector="slow_burn", ref=s.ref
    )


def merge(rows: Iterable[AnomalyRow]) -> list[AnomalyRow]:
    """One anomaly per (op, kind): earliest onset (with its detector and ref), highest score, any self/child ratios."""
    out: dict[tuple[str, str], AnomalyRow] = {}
    for r in sorted(rows, key=lambda r: (r.op, r.kind, r.onset, -r.score, r.detector)):
        k = (r.op, r.kind)
        if k not in out:
            out[k] = r
            continue
        kept = out[k]
        kept.score = max(kept.score, r.score)
        kept.self_ratio = kept.self_ratio if kept.self_ratio is not None else r.self_ratio
        kept.child_ratio = kept.child_ratio if kept.child_ratio is not None else r.child_ratio
    return list(out.values())


def assign_ids(incident: str, rows: Iterable[AnomalyRow]) -> list[AnomalyRow]:
    """`an-<incident>-<n>` in (onset, op, kind) order, so the same input always yields the same ids (N3)."""
    ordered = sorted(rows, key=lambda r: (r.onset, r.op, r.kind))
    for n, r in enumerate(ordered, 1):
        r.id = f"an-{incident}-{n}"
    return ordered
