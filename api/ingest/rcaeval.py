"""RCAEval file adapter + replay CLI (LLD §3.1, EXAMPLE_RUNS §3).

    python -m api.ingest.rcaeval --case re2tt_ts-auth-service_cpu_2 --env rcaeval-tt [--download]

Dataset: Hugging Face `phamquiluan/RCAEval`, Parquet layout (one directory per case, named
`<suite><system>_<service>_<fault>_<n>`). Column mapping, checked on the RE2-TT cases:
    traces.parquet   traceID, spanID, parentSpanID, serviceName, operationName, startTime (µs), duration (µs),
                     statusCode (often null)
    logs.parquet     timestamp (s), container_name, message            (missing in a few cases → Incident.gaps)
    metrics.parquet  time (s, 1 s steps) + one column per `<service>_<metric>`; metrics are per service, not per op
    inject_time.txt  fault start (unix s). Used as the alert time only, never as a Change (no answer leak).
"""

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd

from api.config import get_settings
from api.graph import Graph
from api.ingest.base import CallAgg, ChangeEvent, LogLine, Series
from api.ingest.changes import read_journal
from api.ingest.window import ingest_window

HF_BASE = "https://huggingface.co/datasets/phamquiluan/RCAEval/resolve/main/"
CASE_FILES = ["inject_time.txt", "metrics.parquet", "traces.parquet", "logs.parquet"]

# metric suffix → anomaly kind; workload (traffic) and latency-50 are not fault signals
METRIC_KIND = {
    "cpu": "cpu",
    "mem": "mem",
    "socket": "saturation",
    "diskio": "saturation",
    "latency-90": "latency",
    "error": "errors",
}
# RCAEval faults are driven by a load generator that calls every entry point but isn't traced. Replay models it as
# one operation calling every root operation and uses it as the alert symptom, so every anomalous operation is
# upstream of the symptom and the scorer, not the symptom pick, decides.
CLIENT_SVC = "client"
CLIENT_OP = "client/load"
_LEVEL = re.compile(r"\s(TRACE|DEBUG|INFO|WARN|WARNING|ERROR|FATAL)\s")


def download(case: str, root: Path) -> Path:
    """Fetch one case from Hugging Face (~25 MB). Files that don't exist for the case (logs) are skipped."""
    dest = root / case
    dest.mkdir(parents=True, exist_ok=True)
    for name in CASE_FILES:
        target = dest / name
        if target.exists():
            continue
        try:
            with urllib.request.urlopen(HF_BASE + f"{case}/{name}", timeout=120) as r:
                target.write_bytes(r.read())
        except urllib.error.HTTPError as e:
            if e.code != 404 or name != "logs.parquet":
                # only logs are missing in a few cases; anything else missing means no such case
                raise ValueError(f"{case}: {name} not on Hugging Face (HTTP {e.code}); check the case name") from e
    return dest


class RcaevalAdapter:
    def __init__(self, case_dir: Path, env: str, bucket_s: int = 5):
        self.case = case_dir.name
        self.dir = case_dir
        self.env = env
        self.bucket_s = bucket_s
        self.t_alert = int((case_dir / "inject_time.txt").read_text().strip())
        self.gaps: list[str] = []
        self.source = f"rcaeval:{self.case}"
        self._spans_df: pd.DataFrame | None = None

    # --- spans ---

    def _spans(self) -> pd.DataFrame:
        if self._spans_df is not None:
            return self._spans_df
        cols = [
            "traceID",
            "spanID",
            "parentSpanID",
            "serviceName",
            "operationName",
            "startTime",
            "duration",
            "statusCode",
        ]
        df = pd.read_parquet(self.dir / "traces.parquet", columns=cols)
        df["sec"] = (df["startTime"] // 1_000_000).astype("int64")
        df["svc"] = df["serviceName"].astype(str)
        df["op"] = df["svc"] + "/" + df["operationName"].astype(str)
        df["err"] = pd.to_numeric(df["statusCode"], errors="coerce").fillna(0) >= 500
        parents = df[["traceID", "spanID", "svc", "op"]].rename(
            columns={"spanID": "parentSpanID", "svc": "parent_svc", "op": "parent_op"}
        )
        df = df.merge(parents.drop_duplicates(["traceID", "parentSpanID"]), on=["traceID", "parentSpanID"], how="left")
        child_us = df.groupby(["traceID", "parentSpanID"])["duration"].sum().rename("child_us")
        df = df.merge(child_us, left_on=["traceID", "spanID"], right_index=True, how="left")
        df["child_us"] = df["child_us"].fillna(0)
        df["self_us"] = (df["duration"] - df["child_us"]).clip(lower=0)
        # Root = no parentSpanID at all. Orphans (parent id set but not in the data) are neither roots nor inbound.
        df["root"] = df["parentSpanID"].isna() | (df["parentSpanID"] == "")
        df["inbound"] = df["root"] | (df["parent_svc"].notna() & (df["parent_svc"] != df["svc"]))
        self._spans_df = df.sort_values(["sec", "traceID", "spanID"], kind="stable").reset_index(drop=True)
        return self._spans_df

    def entry_ops(self) -> dict[str, str]:
        """service → its busiest inbound operation (called from another service, or a root span); tie → id."""
        df = self._spans()
        counts = df[df["inbound"]].groupby(["svc", "op"]).size().reset_index(name="n")
        counts = counts.sort_values(["svc", "n", "op"], ascending=[True, False, True])
        return dict(counts.groupby("svc").first()["op"].items())

    def calls(self, since: int, until: int):
        df = self._spans()
        df = df[(df["sec"] >= since) & (df["sec"] < until) & df["parent_op"].notna() & (df["parent_op"] != df["op"])]
        secs = max(until - since, 1)
        roots = self._spans()
        roots = roots[(roots["sec"] >= since) & (roots["sec"] < until) & roots["root"]]
        for (svc, op), g in roots.groupby(["svc", "op"], sort=True):
            yield CallAgg(
                caller_svc=CLIENT_SVC,
                caller_op=CLIENT_OP,
                caller_kind="external",
                callee_svc=svc,
                callee_op=op,
                callee_kind="app",
                rps=round(len(g) / secs, 4),
                p95_ms=round(float(np.percentile(g["duration"], 95)) / 1000, 3),
                err_rate=round(float(g["err"].mean()), 4),
            )
        for (psvc, pop, svc, op), g in df.groupby(["parent_svc", "parent_op", "svc", "op"], sort=True):
            yield CallAgg(
                caller_svc=psvc,
                caller_op=pop,
                callee_svc=svc,
                callee_op=op,
                callee_kind="app",  # RCAEval spans carry no db.system attribute
                rps=round(len(g) / secs, 4),
                p95_ms=round(float(np.percentile(g["duration"], 95)) / 1000, 3),
                err_rate=round(float(g["err"].mean()), 4),
            )

    def series(self, start: int, end: int):
        yield from self._span_series(start, end)
        yield from self.metric_series(start, end)

    def _span_series(self, start: int, end: int):
        df = self._spans()
        df = df[(df["sec"] >= start) & (df["sec"] <= end)].copy()
        df["bucket"] = df["sec"] // self.bucket_s * self.bucket_s
        g = df.groupby(["op", "bucket"], sort=True)
        agg = pd.DataFrame(
            {
                "count": g.size(),
                "latency": g["duration"].quantile(0.95) / 1000,
                "errors": g["err"].mean(),
                "self_ms": g["self_us"].quantile(0.95) / 1000,
                "child_ms": g["child_us"].quantile(0.95) / 1000,
            }
        ).reset_index()
        kinds = {"latency": "latency", "errors": "errors", "count": "aux", "self_ms": "aux", "child_ms": "aux"}
        for op, rows in agg.groupby("op", sort=True):
            ts = rows["bucket"].to_numpy(dtype=np.int64)
            for metric, kind in kinds.items():
                ref = f"rcaeval:{self.case}:traces:{op}:{metric}"
                yield Series(op, metric, kind, ts, rows[metric].to_numpy(dtype=float), ref)

    def metric_series(self, start: int, end: int):
        df = pd.read_parquet(self.dir / "metrics.parquet")
        df = df[(df["time"] >= start) & (df["time"] <= end)]
        entry = self.entry_ops()
        self.skipped_metric_services = sorted({c.split("_", 1)[0] for c in df.columns if "_" in c} - set(entry))
        for col in sorted(c for c in df.columns if c != "time"):
            svc, _, metric = col.partition("_")
            kind = METRIC_KIND.get(metric)
            if kind is None or svc not in entry:
                continue
            s = df[["time", col]].dropna()
            if s.empty:
                continue
            # 1 s samples → bucket_s means, the same resolution as the span series (less noise, cheaper PELT)
            b = s.groupby(s["time"] // self.bucket_s * self.bucket_s)[col].mean()
            yield Series(
                entry[svc],
                f"metric:{metric}",
                kind,
                b.index.to_numpy(dtype=np.int64),
                b.to_numpy(dtype=float),
                f"rcaeval:{self.case}:metrics:{col}",
            )

    def logs(self, start: int, end: int):
        path = self.dir / "logs.parquet"
        if not path.exists():
            self.gaps.append("logs")
            return
        df = pd.read_parquet(path, columns=["timestamp", "container_name", "message"])
        df = df[(df["timestamp"] >= start) & (df["timestamp"] <= end)].dropna(subset=["message"])  # some rows are NA
        for ts, svc, msg in df.itertuples(index=False):
            m = _LEVEL.search(msg)
            yield LogLine(service=str(svc), ts=int(ts), level=m.group(1) if m else "", text=str(msg))

    def changes(self, since: int) -> list[ChangeEvent]:
        # RCAEval has no change events (inject_time is deliberately not one); a synthetic `config` case ships a journal
        return read_journal(self.dir / "changes.jsonl", "synthetic", since)


def replay(case_dir: Path, env_name: str, graph: Graph) -> dict:
    s = get_settings()
    cfg = json.loads(Path(s.weights_path).read_text(encoding="utf-8"))["detect"]
    ad = RcaevalAdapter(case_dir, env_name, cfg["bucket_s"])
    out = ingest_window(ad, env_name, graph, f"rc-{ad.case}", CLIENT_OP, ad.t_alert)
    return out | {"skipped_metric_services": len(getattr(ad, "skipped_metric_services", []))}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Replay one RCAEval case into env:<env>")
    p.add_argument("--case", required=True, help="e.g. re2tt_ts-auth-service_cpu_2")
    p.add_argument("--env", default="rcaeval-tt")
    p.add_argument("--download", action="store_true", help="fetch the case from Hugging Face first")
    a = p.parse_args(argv)
    s = get_settings()
    root = Path(s.rcaeval_dir)
    try:
        case_dir = download(a.case, root) if a.download else root / a.case
        if not case_dir.exists() and (Path(s.samples_dir) / a.case).exists():  # the committed synthetic samples
            case_dir = Path(s.samples_dir) / a.case
    except ValueError as e:
        print(e, file=sys.stderr)
        return 2
    if not (case_dir / "inject_time.txt").exists():
        print(f"case not found: {case_dir} (add --download)", file=sys.stderr)
        return 2
    print(json.dumps(replay(case_dir, a.env, Graph(s.falkordb_url, s.query_timeout_s)), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
