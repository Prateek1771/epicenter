"""Live environments (phase 9): which adapter an env gets, and the alert-time ingest that runs before diagnosis.

An env is live only if it's listed in `LIVE_ENVS`; everything else (RCAEval replays, test envs) is diagnosed from
what is already in its graph.
"""

import json
import logging
import time
from pathlib import Path

from api.config import get_settings
from api.graph import EnvGraph, Graph
from api.ingest import write
from api.ingest.otel import OtelAdapter
from api.ingest.window import ingest_window

log = logging.getLogger("epicenter.live")

# flip-commerce: nginx strips the prefix, so /node/products is flip-node's GET /products
FLIP_PREFIXES = {"/node/": "flip-node", "/fastapi/": "flip-fastapi"}
FLIP_KINDS = {"nginx": "proxy"}
# OTel Demo resource series: the collector's docker_stats receiver, one series per container (named after its
# service). Demo 3.1.0's SDK process_* metrics carry no service label. Checked against its Prometheus (LLD §3.1).
# cpu is cores from the usage counter: container_cpu_utilization_ratio is smoothed, and took 3 min to climb a jump
# from 0.02 to 3 cores that the counter shows within one scrape.
DEMO_PROM = {
    "cpu": "sum by (container_name) (rate(container_cpu_usage_nanoseconds_total[1m])) / 1e9",
    "mem": "sum by (container_name) (container_memory_usage_total_bytes)",
}
MODES = {"flip-commerce": "flip", "astronomy-shop": "demo"}


def live_envs() -> set[str]:
    return {e.strip() for e in get_settings().live_envs.split(",") if e.strip()}


def adapter_for(env_name: str) -> OtelAdapter | None:
    if env_name not in live_envs() or env_name not in MODES:
        return None
    s = get_settings()
    cfg = json.loads(Path(s.weights_path).read_text(encoding="utf-8"))["detect"]
    mode = MODES[env_name]
    if mode == "flip":
        conf = {"otel_file": s.flip_otel_file, "log_dir": s.flip_log_dir, "nginx_log": s.flip_nginx_log,
                "prefixes": FLIP_PREFIXES, "kinds": FLIP_KINDS, "journal": s.change_journal}  # fmt: skip
    else:
        conf = {"jaeger_url": s.jaeger_url, "prometheus_url": s.prometheus_url, "opensearch_url": s.opensearch_url,
                "prom_queries": DEMO_PROM, "journal": s.change_journal}  # fmt: skip
    return OtelAdapter(env_name, mode, conf, cfg["bucket_s"])


FLUSH_S = 3  # spans of the last seconds may still sit in the collector's batch / the SDK's export queue


def ingest_for_alert(
    graph: Graph, env_name: str, incident: str, again: bool = False, as_of_alert: bool = False
) -> dict | None:
    """Before diagnosing a live env's incident: read the window around its alert into the graph, once. A rerun keeps
    the anomalies it already has, like a replayed case; `again` re-ingests (the previous anomalies are retired).
    `as_of_alert`: see the data as the alert-time ingest did (it runs at alert + FLUSH_S + a few s), not as of now."""
    ad = adapter_for(env_name)
    if ad is None:
        return None
    env = graph.env(env_name)
    [inc] = env.ro("incident", inc=incident) or [None]
    # "ingested" is the incident's ingest counter, not "has anomalies": a healthy window has none, and re-reading it
    # later (a rerun) saw whatever happened after the alert, e.g. the env being stopped, as the incident
    if inc is None or (inc.get("ingest") and not again):
        return None
    until = int(inc["opened_at"]) + 2 if as_of_alert else int(time.time()) - FLUSH_S
    out = ingest_window(ad, env_name, graph, incident, inc["symptom"], int(inc["opened_at"]), until=until)
    log.info(json.dumps({"incident_id": incident, "agent": "live_ingest"} | {k: out[k] for k in
                        ("calls", "changes", "anomalies", "gaps")}))  # fmt: skip
    return out


def tick(graph: Graph, env_name: str, span_s: int = 60) -> int:
    """One topology roll-up for a live env (blast radius and what-if work before any incident)."""
    ad = adapter_for(env_name)
    if ad is None:
        return 0
    t = int(time.time())
    env: EnvGraph = graph.env(env_name)
    return write.write_topology(env, ad.calls(t - span_s, t), ts=t)


def main(argv: list[str] | None = None) -> int:
    """python -m api.ingest.live --env flip-commerce --incident inc-run-… : re-ingest a live incident's window."""
    import argparse

    p = argparse.ArgumentParser(description=main.__doc__)
    p.add_argument("--env", required=True)
    p.add_argument("--incident", required=True)
    p.add_argument("--as-of-alert", action="store_true", help="the window the alert-time ingest saw, not up to now")
    a = p.parse_args(argv)
    s = get_settings()
    out = ingest_for_alert(Graph(s.falkordb_url, s.query_timeout_s), a.env, a.incident, again=True,
                           as_of_alert=a.as_of_alert)  # fmt: skip
    print(json.dumps(out, indent=2))
    return 0 if out else 2


if __name__ == "__main__":
    raise SystemExit(main())
