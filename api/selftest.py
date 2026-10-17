"""The small simulation (phase 11, LLD §13): every hand-made fixture graph → diagnose → compare with its known answer.

    docker compose exec api python -m api.selftest [--json]

Each case loads into its own `env:selftest-<name>` graph (diagnose works on env graphs), which is deleted in `finally`.
No telemetry, no LLM, no network: it checks the causal search, the Fault Simulator and the scorer on any machine that
runs the stack. Exit code 0 when every verdict matches.
"""

import argparse
import json
import sys
import time
from pathlib import Path

from api.config import get_settings
from api.graph import Graph
from api.ingest.seed import seed_indexes
from api.search.causal import diagnose

FIXTURES = Path(__file__).resolve().parent.parent / "tests" / "fixtures"

# fixture, incident, expected root cause (None = no_root_cause), expected second cause, placeholder values
CASES = [
    ("mini_graph", "inc-1", "payment/Charge", None, {}),
    ("multi_fault", "inc-m", "db/Query", "cache/Get", {}),
    ("saturated_caller", "inc-s", "api/List", None, {"API_SELF": "40.0", "API_CHILD": "10.0"}),
    ("saturated_caller", "inc-s", "db/Find", None, {"API_SELF": "1.1", "API_CHILD": "10.0"}),
    ("healthy", "inc-h", None, None, {}),
    ("quiet_symptom", "inc-q", None, None, {}),
    ("weak_self", "inc-w", None, None, {}),
]


def run_case(graph: Graph, n: int, fixture: str, incident: str, fill: dict[str, str]) -> dict:
    name = f"selftest-{n}-{fixture.replace('_', '-')}"
    env = graph.env(name)
    env.delete()
    try:
        seed_indexes(env)
        text = (FIXTURES / f"{fixture}.cypher").read_text(encoding="utf-8")
        for k, v in fill.items():
            text = text.replace(k, v)
        tmp = Path(get_settings().rcaeval_dir).parent / f".{name}.cypher"  # data/ is writable; examples/ is not
        tmp.write_text(text, encoding="utf-8")
        try:
            env.load_cypher(tmp)
        finally:
            tmp.unlink(missing_ok=True)
        t0 = time.perf_counter()
        v = diagnose(graph, name, incident)
        return v | {"ms": round((time.perf_counter() - t0) * 1000)}
    finally:
        env.delete()


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Diagnose every fixture graph and compare with its known answer")
    p.add_argument("--json", action="store_true")
    a = p.parse_args(argv)
    s = get_settings()
    graph = Graph(s.falkordb_url, s.query_timeout_s)
    rows = []
    for n, (fixture, incident, want, want2, fill) in enumerate(CASES, 1):
        v = run_case(graph, n, fixture, incident, fill)
        ok = v["root_cause"] == want and (want2 is None or v["second_cause"] == want2)
        label = fixture + (f" ({', '.join(f'{k}={x}' for k, x in fill.items())})" if fill else "")
        rows.append({"case": label, "expected": want or "no_root_cause", "got": v["root_cause"] or v["status"],
                     "second": v["second_cause"], "explains": v["explains"], "ms": v["ms"], "ok": ok})  # fmt: skip
    if a.json:
        print(json.dumps(rows, indent=1))
    else:
        for r in rows:
            mark = "PASS" if r["ok"] else "FAIL"
            print(f"{mark}  {r['case']:<52} expected {r['expected']:<16} got {r['got']:<16} {r['ms']:>5} ms")
        print(f"{sum(r['ok'] for r in rows)}/{len(rows)} PASS")
    return 0 if all(r["ok"] for r in rows) else 1


if __name__ == "__main__":
    sys.exit(main())
