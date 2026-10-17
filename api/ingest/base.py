"""Adapter protocol (LLD §3.1) and the plain records adapters return. Adapters never import graph.py.

Times are epoch seconds (`int`), the same unit the graph stores (GRAPH_SCHEMA §3 `ts`).
"""

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Protocol

import numpy as np


@dataclass(frozen=True)
class CallAgg:
    """One caller→callee operation pair aggregated over a tick (ADR 0006)."""

    caller_svc: str
    caller_op: str  # <service>/<operation>
    callee_svc: str
    callee_op: str
    callee_kind: str  # app · datastore · proxy · external
    rps: float
    p95_ms: float
    err_rate: float
    caller_kind: str = "app"


@dataclass
class Series:
    """One time series already attached to an operation. `kind` is an anomaly kind, or `aux` for helper series
    (`self_ms`, `child_ms`, `count`) that detectors read but never turn into anomalies on their own."""

    op: str
    metric: str
    kind: str
    ts: np.ndarray  # int epoch seconds, ascending
    values: np.ndarray  # float
    ref: str | None = None


@dataclass(frozen=True)
class LogLine:
    service: str
    ts: int
    level: str
    text: str


@dataclass(frozen=True)
class ChangeEvent:
    id: str
    service: str
    type: str  # deploy · flag · config · infra · manual
    ts: int
    summary: str
    ref: str | None = None
    service_kind: str = "app"  # only used if the change creates the Service (U3)


@dataclass
class AnomalyRow:
    """Detector output, before ids are assigned (`detect.assign_ids`)."""

    op: str
    kind: str
    onset: int
    score: float
    detector: str = "short"  # short · slow_burn
    self_ratio: float | None = None
    child_ratio: float | None = None
    ref: str | None = None
    signal: str | None = None  # Signal id for log anomalies
    signal_text: str | None = None
    id: str = field(default="")


class Adapter(Protocol):
    env: str

    def calls(self, since: int, until: int) -> Iterable[CallAgg]: ...

    def series(self, start: int, end: int) -> Iterable[Series]: ...

    def metric_series(self, start: int, end: int) -> Iterable[Series]: ...  # resource metrics only: the slow-burn fetch

    def logs(self, start: int, end: int) -> Iterable[LogLine]: ...

    def changes(self, since: int) -> Iterable[ChangeEvent]: ...
