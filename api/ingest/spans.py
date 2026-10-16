"""Spans → operation-level calls and series (ADR 0006). Pure: parsers and aggregation, no I/O.

Both live modes end here: the OTel Demo's Jaeger traces and flip-commerce's collector file (OTLP JSON) are parsed into
one `Span`, then aggregated exactly like RCAEval's spans (the same `CallAgg` / `Series` the detectors already read).

Which spans are operations: server / consumer spans and roots (an app's operation), and client spans that carry
`db.system` (a datastore operation: `mongodb/find products`, `redis/GET`). Other client spans and internal spans are
plumbing: a server span's caller is its nearest *operation* ancestor, found by walking up through them.
"""

import re
from collections import defaultdict
from dataclasses import dataclass

import numpy as np

from api.ingest.base import CallAgg, Series

OTLP_KIND = {1: "internal", 2: "server", 3: "client", 4: "producer", 5: "consumer"}
_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}
# path segments that are ids, not routes: hex object ids, uuids, numbers, upper-case SKUs with a digit (OTel Demo)
_ID_SEG = re.compile(r"^(?:[0-9a-fA-F]{24}|[0-9a-fA-F-]{32,36}|\d+|(?=[A-Z]*\d)[A-Z0-9]{8,})$")
# static files: one operation per directory, not per hashed bundle or image
_FILE_SEG = re.compile(r"\.(?:js|mjs|css|map|png|jpe?g|gif|svg|ico|webp|woff2?|ttf)$", re.I)


@dataclass(frozen=True)
class Span:
    trace: str
    span: str
    parent: str  # "" for a root
    svc: str
    op: str  # <svc>/<name>
    kind: str  # server · client · internal · producer · consumer
    start: float  # epoch seconds
    dur_ms: float
    error: bool
    datastore: bool = False
    # a proxy's access-log line can't join the trace (nginx sends no traceparent): it names its upstream operation
    # and the time spent there instead, which stand in for the caller link and the child time
    upstream_op: str | None = None
    upstream_ms: float | None = None


def route(path: str) -> str:
    """`/products/64f0c…?x=1` → `/products/{id}`: one operation per route, not per object."""
    path = path.split("?", 1)[0].rstrip("/") or "/"  # `/api/data/` is `/api/data`
    return "/".join("{id}" if _ID_SEG.match(seg) else "{file}" if _FILE_SEG.search(seg) else seg
                    for seg in path.split("/"))  # fmt: skip


def op_name(name: str, attrs: dict) -> str:
    """The operation's name. Bare HTTP-method span names (`GET`, raw node:http has no router) get the route."""
    if name.upper().removeprefix("HTTP ") in _METHODS:
        method = name.upper().removeprefix("HTTP ")
        path = attrs.get("http.route") or attrs.get("url.path") or attrs.get("http.target") or ""
        return f"{method} {route(str(path))}" if path else method
    method, _, path = name.partition(" ")
    return f"{method} {route(path)}" if method in _METHODS and path.startswith("/") else name


def _db_op(attrs: dict, name: str) -> str:
    op = attrs.get("db.operation.name") or attrs.get("db.operation") or ""
    coll = attrs.get("db.collection.name") or attrs.get("db.mongodb.collection") or ""
    return f"{op} {coll}".strip() or name


def _build(trace, span, parent, svc, name, kind, start, dur_ms, attrs, status_error) -> Span:
    db = attrs.get("db.system.name") or attrs.get("db.system")
    code = attrs.get("http.response.status_code") or attrs.get("http.status_code")
    error = bool(status_error) or (code is not None and int(code) >= 500)
    if kind == "client" and db:
        db = str(db)
        return Span(trace, span, parent, db, f"{db}/{_db_op(attrs, name)}", kind, start, dur_ms, error, True)
    return Span(trace, span, parent, svc, f"{svc}/{op_name(name, attrs)}", kind, start, dur_ms, error)


def _attr_value(v: dict):
    for k in ("stringValue", "intValue", "doubleValue", "boolValue"):
        if k in v:
            return int(v[k]) if k == "intValue" else v[k]
    return None


def from_otlp(doc: dict) -> list[Span]:
    """One OTLP JSON export (the collector `file` exporter writes one per line)."""
    out = []
    for rs in doc.get("resourceSpans", []):
        res = {a["key"]: _attr_value(a["value"]) for a in rs.get("resource", {}).get("attributes", [])}
        svc = str(res.get("service.name") or "unknown")
        for ss in rs.get("scopeSpans", []):
            for sp in ss.get("spans", []):
                attrs = {a["key"]: _attr_value(a["value"]) for a in sp.get("attributes", [])}
                start = int(sp["startTimeUnixNano"]) / 1e9
                dur_ms = (int(sp["endTimeUnixNano"]) - int(sp["startTimeUnixNano"])) / 1e6
                kind = OTLP_KIND.get(int(sp.get("kind", 1)), "internal")
                err = sp.get("status", {}).get("code") in (2, "STATUS_CODE_ERROR")
                out.append(
                    _build(
                        sp["traceId"],
                        sp["spanId"],
                        sp.get("parentSpanId", ""),
                        svc,
                        sp["name"],
                        kind,
                        start,
                        dur_ms,
                        attrs,
                        err,
                    )  # fmt: skip
                )
    return out


def from_jaeger(trace: dict) -> list[Span]:
    """One trace from Jaeger's query API (`/api/traces` → `data[]`)."""
    procs = {pid: p["serviceName"] for pid, p in trace.get("processes", {}).items()}
    out = []
    for sp in trace.get("spans", []):
        tags = {t["key"]: t["value"] for t in sp.get("tags", [])}
        parent = next((r["spanID"] for r in sp.get("references", []) if r.get("refType") == "CHILD_OF"), "")
        kind = str(tags.get("span.kind", "internal"))
        err = tags.get("error") in (True, "true") or tags.get("otel.status_code") == "ERROR"
        out.append(
            _build(
                sp["traceID"],
                sp["spanID"],
                parent,
                procs.get(sp["processID"], "unknown"),
                sp["operationName"],
                kind,
                sp["startTime"] / 1e6,
                sp["duration"] / 1e3,
                tags,
                err,
            )  # fmt: skip
        )
    return out


def is_op(s: Span) -> bool:
    return s.datastore or s.kind in ("server", "consumer") or not s.parent


def _resolve(spans: list[Span]) -> tuple[dict[str, Span | None], dict[str, float]]:
    """For every operation span: its caller operation span (or None), and the time spent in its outgoing calls."""
    by_id = {(s.trace, s.span): s for s in spans}
    caller: dict[str, Span | None] = {}
    child_ms: dict[str, float] = defaultdict(float)
    for s in spans:
        if not is_op(s):
            continue
        p = by_id.get((s.trace, s.parent))
        exit_dur = None  # the outermost plumbing span on the way up: the caller's view of this call
        while p is not None and not is_op(p):
            exit_dur = p.dur_ms
            p = by_id.get((p.trace, p.parent))
        caller[s.trace + s.span] = p
        if p is not None:
            child_ms[p.trace + p.span] += exit_dur if exit_dur is not None else s.dur_ms
    return caller, child_ms


def _kind(s: Span) -> str:
    return "datastore" if s.datastore else "app"


def calls(spans: list[Span], since: int, until: int, kinds: dict[str, str] | None = None) -> list[CallAgg]:
    """caller→callee operation pairs over [since, until). Roots have no caller and add no edge. `kinds` overrides a
    service's kind (nginx is a proxy)."""
    kinds = kinds or {}
    caller, _ = _resolve(spans)
    groups: dict[tuple, list[Span]] = defaultdict(list)
    for s in spans:
        if not (since <= s.start < until) or not is_op(s):
            continue
        p = caller.get(s.trace + s.span)
        if p is not None and p.op != s.op:
            groups[(p.svc, p.op, kinds.get(p.svc, _kind(p)), s.svc, s.op, kinds.get(s.svc, _kind(s)))].append(s)
        if s.upstream_op:
            usvc = s.upstream_op.split("/", 1)[0]
            groups[(s.svc, s.op, kinds.get(s.svc, _kind(s)), usvc, s.upstream_op, kinds.get(usvc, "app"))].append(s)
    secs = max(until - since, 1)
    out = []
    for (psvc, pop, pkind, svc, op, kind), g in sorted(groups.items()):
        out.append(
            CallAgg(
                caller_svc=psvc,
                caller_op=pop,
                caller_kind=pkind,
                callee_svc=svc,
                callee_op=op,
                callee_kind=kind,
                rps=round(len(g) / secs, 4),
                p95_ms=round(float(np.percentile([x.dur_ms for x in g], 95)), 3),
                err_rate=round(sum(x.error for x in g) / len(g), 4),
            )
        )
    return out


def series(spans: list[Span], start: int, end: int, bucket_s: int, source: str) -> list[Series]:
    """Per operation, per bucket: p95 latency, error rate, count, and p95 self / child time (aux).

    A span lands in the bucket where it **ends**: its error and latency are known only then, and a parent always ends
    after the child that failed it. By start time, a slow parent (checkout waits seconds on product-catalog before it
    calls payment) put its error buckets *before* its child's and the propagation check refuted the real cause."""
    _, child_ms = _resolve(spans)
    cells: dict[str, dict[int, list[Span]]] = defaultdict(lambda: defaultdict(list))
    for s in spans:
        t = s.start + s.dur_ms / 1000
        if is_op(s) and start <= t <= end:
            cells[s.op][int(t) // bucket_s * bucket_s].append(s)
    out = []
    for op in sorted(cells):
        ts = np.array(sorted(cells[op]), dtype=np.int64)
        rows = [cells[op][t] for t in ts]
        child = [[x.upstream_ms if x.upstream_ms is not None else child_ms.get(x.trace + x.span, 0.0) for x in r]
                 for r in rows]  # fmt: skip
        metrics = {
            "latency": ("latency", [np.percentile([x.dur_ms for x in r], 95) for r in rows]),
            "errors": ("errors", [sum(x.error for x in r) / len(r) for r in rows]),
            "count": ("aux", [len(r) for r in rows]),
            "self_ms": (
                "aux",
                [
                    np.percentile([max(x.dur_ms - c, 0.0) for x, c in zip(r, cr, strict=True)], 95)
                    for r, cr in zip(rows, child, strict=True)
                ],
            ),  # fmt: skip
            "child_ms": ("aux", [np.percentile(cr, 95) for cr in child]),
        }
        for metric, (kind, vals) in metrics.items():
            out.append(Series(op, metric, kind, ts, np.asarray(vals, dtype=float), f"{source}:traces:{op}:{metric}"))
    return out


def entry_ops(spans: list[Span]) -> dict[str, str]:
    """service → its busiest inbound operation (a root, or called from another service); tie → id."""
    caller, _ = _resolve(spans)
    n: dict[tuple[str, str], int] = defaultdict(int)
    for s in spans:
        if not is_op(s):
            continue
        p = caller.get(s.trace + s.span)
        if p is None or p.svc != s.svc:
            n[(s.svc, s.op)] += 1
    best: dict[str, tuple[int, str]] = {}
    for (svc, op), k in n.items():
        if svc not in best or (-k, op) < (-best[svc][0], best[svc][1]):
            best[svc] = (k, op)
    return {svc: op for svc, (_, op) in sorted(best.items())}
