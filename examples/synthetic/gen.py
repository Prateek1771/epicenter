"""Synthetic samples with a known answer (phase 11, EXAMPLE_RUNS §4), in the RCAEval layout.

    docker compose exec api python examples/synthetic/gen.py --size small|medium|huge --fault <kind> --seed <n> [--run]

Writes data/rcaeval/synth-<size>_<svc>_<fault>_<seed>/: traces.parquet, metrics.parquet, logs.parquet, inject_time.txt,
labels.json (the answer; read by eval only, never ingested) and, for `config`, changes.jsonl. `--run` also replays it
into its own throwaway graph (env:synth-check, deleted after: cases share timestamps and names, so they must not share a
graph), diagnoses it and prints one JSON line {case, expected, got, ok} (syscheck reads it). For the UI, replay one
case at a time into env:synthetic (`python -m api.ingest.rcaeval --case <id> --env synthetic`).

Honesty: the faults spread the way our own propagation rules say, so this is easier than real data. It tests scale and
code paths; its accuracy is reported apart from RCAEval, never mixed in. Same seed → byte-identical files.
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
SIZES = {  # services, ops per service, traces / s; traces cover the replay's window (t−600 … t+300)
    "small": (5, (2, 4), 5),
    "medium": (30, (3, 7), 20),
    "huge": (300, (4, 9), 50),
}
FAULTS = ["cpu", "mem", "delay", "error", "down", "config", "two", "loud-victim", "healthy"]
BEFORE_S, AFTER_S = 600, 300
SLOW_BURN_S = 3 * 3600  # `mem`: the climb starts 3 h before the alert; metrics then cover 6 h
T0 = 1_780_000_000  # inject times: fixed (byte-identical per seed), one day apart per (size, fault), so cases replayed
# into the shared env:synthetic never overlap in time (a change or a baseline would leak into the next case)
SATURATED = 20  # self time at 95% CPU: M/M/1 response = service / (1 − ρ) = 20×


def topology(rng: np.random.Generator, size: str) -> dict:
    """Layered call graph: edge → api → domain → datastores. Each op calls 1–3 ops one or two tiers down."""
    n, (lo, hi), _ = SIZES[size]
    n_store = max(2, n // 10)
    n_edge = 1 if n < 20 else 2
    n_api = max(1, n // 7)
    n_dom = n - n_store - n_edge - n_api
    stores = ["mongodb", "redis", "mysql"][:n_store] + [f"store-{i}" for i in range(n_store - 3)]
    tiers = [[f"edge-{i}" for i in range(n_edge)], [f"api-{i}" for i in range(n_api)],
             [f"svc-{i}" for i in range(n_dom)], stores]  # fmt: skip
    ops: dict[str, list[str]] = {}
    tier_of: dict[str, int] = {}
    for k, svcs in enumerate(tiers):
        for s in svcs:
            m = 2 if k == 3 else int(rng.integers(lo, hi + 1))
            ops[s] = [f"{s}/{'GET' if k < 2 else 'op'} /{s}/r{j}" if k < 3 else f"{s}/{['find', 'get'][j % 2]} {j}"
                      for j in range(m)]  # fmt: skip
            for o in ops[s]:
                tier_of[o] = k
    calls: dict[str, list[str]] = {}
    for o, k in sorted(tier_of.items()):
        if k == 3:
            calls[o] = []
            continue
        below = [x for x, kk in sorted(tier_of.items()) if kk in (k + 1, k + 2) and kk <= 3]
        nxt = [x for x in below if tier_of[x] == k + 1] or below
        calls[o] = sorted(set(rng.choice(nxt, size=min(len(nxt), int(rng.integers(1, 4))), replace=False)))
    base = {o: float(rng.uniform(2, 25)) for o in sorted(tier_of)}  # self ms
    return {
        "ops": ops,
        "tier": tier_of,
        "calls": calls,
        "base": base,
        "roots": sorted(o for o, k in tier_of.items() if k == 0),
    }


def choose(rng: np.random.Generator, topo: dict, fault: str) -> dict:
    """The fault's target(s) and the label."""
    tier, calls = topo["tier"], topo["calls"]
    live, todo = set(), list(topo["roots"])  # only ops traffic reaches: huge has unreachable services
    while todo:
        if (o := todo.pop()) not in live:
            live.add(o)
            todo += calls[o]
    domain = sorted(o for o, k in tier.items() if k == 2 and o in live)
    stores = sorted(o for o, k in tier.items() if k == 3 and o in live)
    if fault == "healthy":
        return {"fault": fault, "target": None, "wobble": str(rng.choice(domain))}
    if fault in ("down",):
        return {"fault": fault, "target": str(rng.choice(stores))}
    if fault == "loud-victim":
        return {"fault": fault, "target": str(rng.choice(stores))}
    if fault == "two":
        a = str(rng.choice(domain))

        def related(x: str, y: str) -> bool:  # same subtree: one reaches the other
            seen, todo = set(), [x]
            while todo:
                n = todo.pop()
                if n == y:
                    return True
                if n not in seen:
                    seen.add(n)
                    todo += calls[n]
            return False

        # disjoint: no op of a's (saturated) service reaches b, b reaches none of them: neither is the other's effect
        mine = [o for o in tier if o.split("/")[0] == a.split("/")[0]]
        b = [o for o in domain + stores if o.split("/")[0] != a.split("/")[0]
             and not any(related(m, o) or related(o, m) for m in mine)]  # fmt: skip
        if not b:
            raise SystemExit(f"two: no fault independent of {a} in this topology; try another --seed")
        return {"fault": fault, "target": a, "second": str(rng.choice(b))}
    return {"fault": fault, "target": str(rng.choice(domain))}


def generate(size: str, fault: str, seed: int, out_root: Path) -> Path:
    # one topology per (size, seed): every fault of a size runs on the same system
    topo = topology(np.random.default_rng([seed, list(SIZES).index(size)]), size)
    rng = np.random.default_rng([seed, list(SIZES).index(size), FAULTS.index(fault)])
    T = T0 + 86400 * (len(FAULTS) * list(SIZES).index(size) + FAULTS.index(fault))
    f = choose(rng, topo, fault)
    tgt, svc_of = f["target"], (lambda o: o.split("/", 1)[0])
    case = f"synth-{size}_{svc_of(tgt) if tgt else 'none'}_{fault}_{seed}"
    d = out_root / case
    d.mkdir(parents=True, exist_ok=True)
    calls, base = topo["calls"], topo["base"]
    second = f.get("second")

    def self_ms(op: str, t: float) -> tuple[float, bool]:
        ms = base[op] * float(rng.lognormal(0, 0.25))
        err = rng.random() < 0.003
        after = t >= T
        if after and tgt and fault in ("cpu",) and svc_of(op) == svc_of(tgt):
            ms *= SATURATED
        if after and op == tgt and fault in ("delay", "config", "loud-victim"):
            ms += 300 if fault != "loud-victim" else 150
        if after and op == tgt and fault == "error":
            err = err or rng.random() < 0.3
        if after and op == tgt and fault == "down":
            ms, err = 1000.0, True  # timeout
        if after and fault == "two" and svc_of(op) == svc_of(tgt):
            ms *= SATURATED
        if t >= T + 30 and fault == "two" and op == second:
            err = err or rng.random() < 0.4
        if fault == "healthy" and op == f["wobble"] and T - 30 <= t < T + 30:
            ms *= 1.15  # a weak, unrelated wobble
        return ms, err

    rows: list[tuple] = []
    _, _, tps = SIZES[size]
    n = 0

    def span(trace: str, parent: str | None, op: str, t: float) -> tuple[float, bool]:
        nonlocal n
        n += 1
        sid = f"{trace}-{n}"
        own, err = self_ms(op, t)
        cur = t + own / 2000
        child_err = False
        kids = list(calls[op])
        if kids:
            k = int(rng.integers(1, min(2, len(kids)) + 1))
            kids = [kids[i] for i in sorted(rng.choice(len(kids), size=k, replace=False))]
        for c in kids:
            reps = 3 if fault == "loud-victim" and c == tgt and t >= T else 1  # the caller retries: louder upstream
            for _ in range(reps):
                dur, e = span(trace, sid, c, cur)
                cur += dur / 1000
                child_err = child_err or e
        err = err or (child_err and rng.random() < 0.7)
        dur = (cur - t) * 1000 + own / 2
        rows.append((trace, sid, parent, svc_of(op), op.split("/", 1)[1], int(t * 1e6), int(dur * 1000),
                     500 if err else None))  # fmt: skip
        return dur, err

    roots = topo["roots"]
    for sec in range(T - BEFORE_S, T + AFTER_S):
        for i in range(tps):
            t = sec + i / tps
            span(f"t{sec}-{i}", None, roots[(sec + i) % len(roots)], t)
    cols = ["traceID", "spanID", "parentSpanID", "serviceName", "operationName", "startTime", "duration", "statusCode"]
    traces = pd.DataFrame(rows, columns=cols).sort_values(["startTime", "traceID", "spanID"], kind="stable")
    traces["statusCode"] = traces["statusCode"].astype("Int64")
    traces.to_parquet(d / "traces.parquet", index=False)

    # metrics: per service cpu and mem, 1 s steps (5 s for the 6 h slow-burn window)
    start = T - (2 * SLOW_BURN_S if fault == "mem" else BEFORE_S + 300)
    step = 5 if fault == "mem" else 1
    secs = np.arange(start, T + AFTER_S, step)
    met = {"time": secs}
    for s in sorted(topo["ops"]):
        cpu = 0.25 + 0.03 * rng.standard_normal(len(secs))
        mem = 0.40 + 0.01 * rng.standard_normal(len(secs))
        if tgt and svc_of(tgt) == s and fault in ("cpu", "two"):
            cpu = np.where(secs >= T, 0.95, cpu)
        if tgt and svc_of(tgt) == s and fault == "mem":
            mem = mem + np.clip((secs - (T - SLOW_BURN_S)) / SLOW_BURN_S, 0, None) * 0.5
        met[f"{s}_cpu"], met[f"{s}_mem"] = np.round(cpu, 4), np.round(mem, 4)
    pd.DataFrame(met).to_parquet(d / "metrics.parquet", index=False)

    logs = []
    for sec in range(T - BEFORE_S, T + AFTER_S, 5):
        for s in sorted(topo["ops"])[:20]:
            logs.append((sec, s, f"{s} 2026-01-01 INFO request handled"))
    if tgt and fault in ("error", "down"):
        logs += [(sec, svc_of(tgt), f"{svc_of(tgt)} 2026-01-01 ERROR request failed: upstream timeout")
                 for sec in range(T, T + AFTER_S, 2)]  # fmt: skip
    pd.DataFrame(logs, columns=["timestamp", "container_name", "message"]).to_parquet(d / "logs.parquet", index=False)
    (d / "inject_time.txt").write_text(str(T))

    if fault == "config":
        change = {
            "id": f"chg-{case}",
            "env": "synthetic",
            "service": svc_of(tgt),
            "service_kind": "app",
            "type": "config",
            "ts": T - 60,
            "summary": f"config change on {svc_of(tgt)}",
            "ref": f"synthetic:{case}",
        }
        (d / "changes.jsonl").write_text(json.dumps(change, sort_keys=True) + "\n")
    label = {"case": case, "fault": fault, "seed": seed, "size": size,
             "status": "no_root_cause" if fault == "healthy" else "diagnosed",
             "service": svc_of(tgt) if tgt else None, "op": tgt, "second_service": svc_of(second) if second else None,
             "ops": len(topo["tier"]), "services": len(topo["ops"]), "spans": len(rows)}  # fmt: skip
    (d / "labels.json").write_text(json.dumps(label, indent=1, sort_keys=True) + "\n")
    return d


def check(label: dict, status: str, root_cause: str | None, second: str | None) -> bool:
    """Synthetic hit: `no_root_cause` for healthy; else the root cause's service (and the second's, for `two`)."""
    if label["status"] == "no_root_cause":
        return status == "no_root_cause"
    ok = root_cause is not None and root_cause.split("/", 1)[0] == label["service"]
    if label.get("second_service"):
        ok = ok and second is not None and second.split("/", 1)[0] == label["second_service"]
    return ok


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Generate a synthetic case with a known answer (RCAEval layout)")
    p.add_argument("--size", choices=list(SIZES), default="small")
    p.add_argument("--fault", choices=FAULTS, default="cpu")
    p.add_argument("--seed", type=int, default=1)
    p.add_argument("--out", default=str(ROOT / "data" / "rcaeval"))
    p.add_argument("--run", action="store_true", help="also replay into a throwaway graph, diagnose, print the verdict")
    a = p.parse_args(argv)
    d = generate(a.size, a.fault, a.seed, Path(a.out))
    label = json.loads((d / "labels.json").read_text())
    if not a.run:
        print(json.dumps(label))
        return 0
    sys.path.insert(0, str(ROOT))
    from api.config import get_settings
    from api.graph import Graph
    from api.ingest.rcaeval import replay
    from api.search.causal import diagnose

    s = get_settings()
    g = Graph(s.falkordb_url, s.query_timeout_s)
    env = g.env("synth-check")
    env.delete()
    try:
        inc = replay(d, "synth-check", g)["incident"]
        v = diagnose(g, "synth-check", inc)
    finally:
        env.delete()
    expected = "no_root_cause" if label["status"] == "no_root_cause" else f"{label['service']}/*"
    ok = check(label, v["status"], v["root_cause"], v["second_cause"])
    got = v["root_cause"] or v["status"]
    print(json.dumps({"case": label["case"], "expected": expected, "got": got, "second": v["second_cause"], "ok": ok}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
