"""`otel` adapter (LLD §3.1): live environments instrumented with OpenTelemetry.

    mode `flip`  flip-commerce: collector file exporter (OTLP JSON lines), winston JSON logs, nginx access log
    mode `demo`  OTel Demo: Jaeger query API, Prometheus `query_range`, OpenSearch logs

Changes come from the fault journal (`changes.py`) in both modes. Read-only towards the monitored system (N4): files
are only read, HTTP sources only queried. A source that can't be read becomes an `Incident.gaps` entry, never an error.
"""

import json
import re
from collections.abc import Callable, Iterator
from datetime import datetime
from pathlib import Path

import httpx
import numpy as np

from api.ingest import spans as sp
from api.ingest.base import CallAgg, ChangeEvent, LogLine, Series
from api.ingest.changes import read_journal

# nginx `log_format epicenter '$msec "$request" $status $request_time $upstream_addr $upstream_response_time'`
_NGINX = re.compile(r'^(?P<msec>\d+\.\d+) "(?P<method>[A-Z]+) (?P<path>\S+)[^"]*" (?P<status>\d{3}) '
                    r'(?P<rt>[\d.]+) (?P<addr>\S+) (?P<urt>[\d.,: -]+)$')  # fmt: skip
_TIMEOUT = 5.0
_RETRIES = 2
SLACK_S = 120  # appended in time order give or take a batch / a slow request: start reading this much early


def lines_since(path: Path, start: int, ts_of: Callable[[str], float | None]) -> Iterator[str]:
    """Lines of an append-only, time-ordered file from shortly before `start` on. A binary search on the byte offset
    parses O(log n) lines, so a window costs its own size, not the file's (these files grow all day: 160 MB after a
    few hours of flip-commerce made every ingest scan ~20 s). `ts_of(line)` → seconds, or None for a line it can't
    read (cut mid-write). Callers still filter to their exact window."""
    with path.open("rb") as f:
        lo, hi = 0, f.seek(0, 2)
        while hi - lo > 65536:
            mid = (lo + hi) // 2
            f.seek(mid)
            f.readline()  # finish the line the seek landed in
            ts = None
            while ts is None and (raw := f.readline()):
                ts = ts_of(raw.decode("utf-8", "replace"))
            if ts is None or ts >= start - SLACK_S:
                hi = mid
            else:
                lo = mid
        f.seek(lo)
        if lo:
            f.readline()
        for raw in f:
            yield raw.decode("utf-8", "replace")


def _otlp_ts(line: str) -> float | None:
    try:
        return min((s.start for s in sp.from_otlp(json.loads(line))), default=None)
    except (ValueError, KeyError):
        return None


def _nginx_ts(line: str) -> float | None:
    head = line.split(" ", 1)[0]
    return float(head) if head.replace(".", "", 1).isdigit() else None


def _winston_ts(line: str) -> float | None:
    ln = parse_winston(line, "")
    return ln.ts if ln else None


def parse_nginx(line: str, prefixes: dict[str, str]) -> sp.Span | None:
    """One access-log line → a proxy root span naming its upstream operation. `prefixes`: `/node/` → `flip-node`
    (nginx strips the prefix, so the upstream's route is the rest of the path)."""
    m = _NGINX.match(line.strip())
    if not m:
        return None
    path, method = m["path"], m["method"]
    upstream_op = None
    for prefix, svc in prefixes.items():
        if path.startswith(prefix):
            upstream_op = f"{svc}/{method} {sp.route('/' + path[len(prefix) :])}"
            break
    urt = m["urt"].split(",")[-1].strip()  # retries list every upstream tried; the last one answered
    up_ms = float(urt) * 1000 if re.fullmatch(r"[\d.]+", urt) else None
    start = float(m["msec"]) - float(m["rt"])
    return sp.Span(
        trace=f"nginx:{m['msec']}:{path}",
        span="0",
        parent="",
        svc="nginx",
        op=f"nginx/{method} {sp.route(path)}",
        kind="server",
        start=start,
        dur_ms=float(m["rt"]) * 1000,
        error=int(m["status"]) >= 500,
        upstream_op=upstream_op,
        upstream_ms=up_ms,
    )


def parse_winston(line: str, service: str) -> LogLine | None:
    try:
        d = json.loads(line)
        ts = int(datetime.fromisoformat(str(d["timestamp"]).replace("Z", "+00:00")).timestamp())
    except (ValueError, KeyError, TypeError):
        return None
    return LogLine(service=service, ts=ts, level=str(d.get("level", "")).upper(), text=str(d.get("message", "")))


def _get(client: httpx.Client, url: str, params: dict | None = None) -> dict:
    last: Exception | None = None
    for _ in range(_RETRIES + 1):
        try:
            r = client.get(url, params=params, timeout=_TIMEOUT)
            r.raise_for_status()
            return r.json()
        except (httpx.HTTPError, ValueError) as e:
            last = e
    raise last  # type: ignore[misc]


class OtelAdapter:
    def __init__(self, env: str, mode: str, cfg: dict, bucket_s: int = 5, client: httpx.Client | None = None):
        self.env = env
        self.mode = mode
        self.cfg = cfg
        self.bucket_s = bucket_s
        self.source = f"otel:{env}"
        self.gaps: list[str] = []
        self.client = client or httpx.Client()
        self._spans: list[sp.Span] | None = None
        self._range: tuple[int, int] | None = None

    def _gap(self, name: str) -> None:
        if name not in self.gaps:
            self.gaps.append(name)

    # --- spans ---

    def load(self, start: int, end: int) -> list[sp.Span]:
        """All spans in [start, end], read once per adapter (ingest asks for calls and series over one range)."""
        if self._spans is None or self._range is None or start < self._range[0] or end > self._range[1]:
            out = self._flip_spans(start, end) if self.mode == "flip" else self._jaeger_spans(start, end)
            self._spans = sorted(out, key=lambda s: (s.start, s.trace, s.span))
            self._range = (start, end)
        return [s for s in self._spans if start <= s.start <= end]

    def _flip_spans(self, start: int, end: int) -> list[sp.Span]:
        out: list[sp.Span] = []
        traces = Path(self.cfg["otel_file"]) if self.cfg.get("otel_file") else None
        # the collector rotates `spans.jsonl` into `spans-<time>.jsonl` backups: a window can span both
        files = []
        if traces and traces.parent.exists():
            files = sorted(traces.parent.glob(f"{traces.stem}*{traces.suffix}"))
        for path in (p for p in files if p.stat().st_mtime >= start):
            for line in lines_since(path, start, _otlp_ts):
                if line.strip():
                    try:
                        out += [s for s in sp.from_otlp(json.loads(line)) if start <= s.start <= end]
                    except (ValueError, KeyError):
                        continue  # a line cut mid-write by the collector
        if not files:
            self._gap("traces")
        nginx = Path(self.cfg["nginx_log"]) if self.cfg.get("nginx_log") else None
        if nginx and nginx.exists():
            pre = self.cfg.get("prefixes", {})
            out += [s for line in lines_since(nginx, start, _nginx_ts) if (s := parse_nginx(line, pre))]
        else:
            self._gap("proxy")
        return [s for s in out if start <= s.start <= end]

    def _jaeger_spans(self, start: int, end: int) -> list[sp.Span]:
        base = self.cfg["jaeger_url"].rstrip("/")
        out: list[sp.Span] = []
        try:
            services = sorted(_get(self.client, f"{base}/api/services").get("data") or [])
            for svc in services:
                params = {"service": svc, "start": start * 1_000_000, "end": end * 1_000_000,
                          "limit": self.cfg.get("jaeger_limit", 2000)}  # fmt: skip
                for tr in _get(self.client, f"{base}/api/traces", params).get("data") or []:
                    out += sp.from_jaeger(tr)
        except (httpx.HTTPError, ValueError):
            self._gap("traces")
        # the same trace comes back once per service it touches
        return list({(s.trace, s.span): s for s in out}.values())

    def calls(self, since: int, until: int) -> list[CallAgg]:
        return sp.calls(self.load(since, until), since, until, self.cfg.get("kinds", {}))

    def entry_ops(self) -> dict[str, str]:
        return sp.entry_ops(self._spans or [])

    def series(self, start: int, end: int) -> list[Series]:
        out = sp.series(self.load(start, end), start, end, self.bucket_s, self.source)
        return out + self.metric_series(start, end, self.bucket_s)

    def metric_series(self, start: int, end: int, step: int = 60) -> list[Series]:
        """Resource series per service (cpu, mem) from Prometheus, attached to the service's entry operation like
        RCAEval metrics. The slow-burn pass reads 6 h at the default 1-minute step (LLD §3.2)."""
        if self.mode != "demo" or not self.cfg.get("prometheus_url"):
            return []
        base = self.cfg["prometheus_url"].rstrip("/")
        entry = self.entry_ops()
        out = []
        try:
            for kind, query in sorted(self.cfg.get("prom_queries", {}).items()):
                params = {"query": query, "start": start, "end": end, "step": step}
                for r in _get(self.client, f"{base}/api/v1/query_range", params)["data"]["result"]:
                    m = r["metric"]
                    svc = m.get("service_name") or m.get("container_name") or m.get("job", "").split("/")[-1]
                    if svc not in entry or not r["values"]:
                        continue
                    ts = np.array([int(float(t)) for t, _ in r["values"]], dtype=np.int64)
                    vals = np.array([float(v) for _, v in r["values"]], dtype=float)
                    out.append(Series(entry[svc], f"metric:{kind}", kind, ts, vals, f"{self.source}:prom:{svc}:{kind}"))
        except (httpx.HTTPError, ValueError, KeyError):
            self._gap("metrics")
        return out

    # --- logs ---

    def logs(self, start: int, end: int):
        if self.mode == "flip":
            yield from self._flip_logs(start, end)
        else:
            yield from self._opensearch_logs(start, end)

    def _flip_logs(self, start: int, end: int):
        d = Path(self.cfg["log_dir"]) if self.cfg.get("log_dir") else None
        f = d / "combined.log" if d else None
        if not f or not f.exists():
            self._gap("logs")
            return
        svc = self.cfg.get("log_service", "flip-node")
        for line in lines_since(f, start, _winston_ts):
            if (ln := parse_winston(line, svc)) and start <= ln.ts <= end:
                yield ln

    def _opensearch_logs(self, start: int, end: int):
        url = self.cfg.get("opensearch_url")
        if not url:
            self._gap("logs")
            return
        body = {
            "size": self.cfg.get("log_limit", 5000),
            "sort": [{"@timestamp": "asc"}],
            "query": {"range": {"@timestamp": {"gte": start * 1000, "lte": end * 1000, "format": "epoch_millis"}}},
        }
        try:
            r = self.client.post(f"{url.rstrip('/')}/{self.cfg.get('log_index', 'otel-logs-*')}/_search",
                                 json=body, timeout=_TIMEOUT)  # fmt: skip
            r.raise_for_status()
            hits = r.json()["hits"]["hits"]
        except (httpx.HTTPError, ValueError, KeyError):
            self._gap("logs")
            return
        for h in hits:
            src = h["_source"]
            svc = (src.get("resource") or {}).get("service.name") or src.get("service.name") or ""
            ts = src.get("@timestamp", "")
            try:
                t = int(datetime.fromisoformat(str(ts).replace("Z", "+00:00")).timestamp())
            except ValueError:
                continue
            sev = src.get("severity")  # the demo's OpenSearch exporter nests it: {text, number}
            level = sev.get("text", "") if isinstance(sev, dict) else src.get("severityText", "")
            yield LogLine(service=str(svc), ts=t, level=str(level).upper(),
                          text=str(src.get("body", "")))  # fmt: skip

    # --- changes ---

    def changes(self, since: int) -> list[ChangeEvent]:
        j = self.cfg.get("journal")
        return read_journal(Path(j), self.env, since) if j else []
