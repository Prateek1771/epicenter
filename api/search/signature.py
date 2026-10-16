"""Deterministic 64-dim incident signature (ADR 0008). Pure: graph rows in, vector out, no I/O.

    dims  0–7   anomaly kind histogram on the root cause            (KINDS order)
    dims  8–15  anomaly kind histogram across the run's hypotheses  (KINDS order)
    dims 16–19  root-cause hop distance one-hot (0, 1, 2, 3+)
    dims 20–24  change types cited by the root cause's evidence     (CHANGE_TYPES order)
    dims 25–27  root-cause service kind one-hot                     (SERVICE_KINDS order)
    dims 28–30  share of anomalous operations per service kind      (SERVICE_KINDS order)
    dim  31     a second, independent root cause was found
    dims 32–63  log templates on the root cause, feature-hashed with blake2b (stable across processes and machines;
                Python's hash() is salted per process, so it would break recall between restarts)

Each block is scaled to [0, 1] before the L2 normalization, so no block dominates by raw counts.
"""

import hashlib
import math

KINDS = ["latency", "errors", "cpu", "mem", "saturation", "log_burst", "new_template", "down"]
CHANGE_TYPES = ["deploy", "flag", "config", "infra", "manual"]
SERVICE_KINDS = ["datastore", "app", "proxy"]
DIMS = 64
TEMPLATE_DIMS = 32


def _hist(kinds: list[str]) -> list[float]:
    counts = [float(kinds.count(k)) for k in KINDS]
    top = max(counts, default=0.0)
    return [c / top for c in counts] if top else counts


def template_slot(text: str) -> int:
    return int.from_bytes(hashlib.blake2b(text.encode(), digest_size=8).digest(), "big") % TEMPLATE_DIMS


def signature(
    root_kinds: list[str],
    hops: int | None,
    root_service_kind: str | None,
    change_types: list[str],
    run_kinds: list[str],
    op_service_kinds: list[str | None],
    templates: list[str],
    second_cause: bool,
) -> list[float]:
    """The incident's signature; all-zero when there is nothing to describe (callers then skip writing it)."""
    v = _hist(root_kinds) + _hist(run_kinds)
    v += [1.0 if hops is not None and min(hops, 3) == i else 0.0 for i in range(4)]
    v += [1.0 if t in change_types else 0.0 for t in CHANGE_TYPES]
    v += [1.0 if root_service_kind == k else 0.0 for k in SERVICE_KINDS]
    n = len(op_service_kinds)
    v += [op_service_kinds.count(k) / n if n else 0.0 for k in SERVICE_KINDS]
    v.append(1.0 if second_cause else 0.0)
    t = [0.0] * TEMPLATE_DIMS
    for text in sorted(set(templates)):
        t[template_slot(text)] += 1.0
    top = max(t)
    v += [x / top for x in t] if top else t
    assert len(v) == DIMS
    norm = math.sqrt(sum(x * x for x in v))
    return [round(x / norm, 6) for x in v] if norm else v
