"""RCAEval accuracy suite (phase 10, LLD §12 eval row).

    python -m api.eval --suite re2 --system tt [--weights weights.json] [--cases 're2tt_ts-auth*'] [--download]
    python -m api.eval --grid data/eval/0001-re2-tt-….json        # dev-split weight search on a stored run
    python -m api.eval --suite synth [--size small,medium] [--seed 1] # synthetic samples (phase 11), base weights only

Per case: a fresh scratch graph `env:eval-<system>`, one replay, then one diagnosis per weights variant (the base
weights plus four ablations; every diagnosis is a new kept run, so one replay serves all five). The label is the
case name (`<suite><system>_<service>_<fault>_<n>`): a hit means the verdict's root-cause operation belongs to the
labelled service. `no_root_cause` is a miss at every k. Reps 1–2 are the dev split (weights are tuned there), rep 3
is held out.

Results go to `data/eval/<n>-re2-<system>-<weights>-<rules>.json` (numbered, never overwritten). That file holds no
wall-clock values, so two runs of the same code and data are byte-identical; timings go to the sibling
`.timing.json`. Engine only: no LLM is called, so the number is the deterministic scorer's (ADR 0002).
"""

import argparse
import fnmatch
import importlib.util
import itertools
import json
import math
import sys
import time
import urllib.request
from pathlib import Path

from api.config import get_settings
from api.graph import Graph, query_stats
from api.ingest.rcaeval import download, replay
from api.runs import _CASE
from api.search import causal
from api.search import score as sc
from api.search.simulate import load_rules

HF_TREE = "https://huggingface.co/api/datasets/phamquiluan/RCAEval/tree/main"
OUT = Path("data/eval")
N2_QUERIES = ("Q1", "Q2", "Q3", "Q3b", "Q4a", "Q4_blame", "Q4b", "Q5")  # Q4 runs as its three parts
GRID_STEP = 0.05


# --- pure ---


def label(case: str) -> dict:
    m = _CASE.match(case)
    if not m:
        raise ValueError(f"not an RCAEval RE2 case name: {case}")
    return {"service": m["svc"], "fault": m["fault"], "rep": int(m["n"])}


def split(case: str) -> str:
    """Rep 3 is held out; reps 1–2 are where weights may be tuned."""
    return "test" if label(case)["rep"] >= 3 else "dev"


def services(ops: list[str]) -> list[str]:
    """Distinct services in rank order."""
    out: list[str] = []
    for op in ops:
        s = op.split("/", 1)[0]
        if s not in out:
            out.append(s)
    return out


def hit_at(row: dict, k: int) -> bool:
    return label(row["case"])["service"] in services(row["ranked"])[:k]


def metrics(rows: list[dict]) -> dict:
    """AC@1 / AC@3 over `rows` (case, ranked ops with the verdict first; empty when no root cause), plus AC@1 per
    fault kind."""
    if not rows:
        return {"cases": 0, "ac1": None, "ac3": None, "by_fault": {}}
    faults = sorted({label(r["case"])["fault"] for r in rows})
    by_fault = {}
    for f in faults:
        xs = [r for r in rows if label(r["case"])["fault"] == f]
        by_fault[f] = {"cases": len(xs), "ac1": round(sum(hit_at(r, 1) for r in xs) / len(xs), 4)}
    return {
        "cases": len(rows),
        "ac1": round(sum(hit_at(r, 1) for r in rows) / len(rows), 4),
        "ac3": round(sum(hit_at(r, 3) for r in rows) / len(rows), 4),
        "by_fault": by_fault,
    }


def ranked_ops(verdict: dict) -> list[str]:
    """The verdict's root cause, then the rest of the round-1 ranking minus refuted hypotheses."""
    if verdict["root_cause"] is None:
        return []
    rest = [h["op"] for h in verdict["ranking"] if h["status"] != "refuted" and h["op"] != verdict["root_cause"]]
    return [verdict["root_cause"], *rest]


def rescore(parts: list[dict], w: dict) -> list[str]:
    """Re-rank stored round-1 hypotheses (op, onset, score_parts) under other weights → ops in rank order.
    Limit: ignores the skeptic re-rank and the no-root-cause decision; the grid's pick is confirmed by a real run."""
    hyps = [{"op": p["op"], "onset": p["onset"], "score": sc.score(p["parts"], w)} for p in parts if p["parts"]]
    return [h["op"] for h in sc.ranking(hyps)]


def simplex(features: list[str], step: float) -> list[dict[str, float]]:
    """Every weight vector on a `step` grid that sums to 1, in a fixed order."""
    n = round(1 / step)
    out = []
    for cut in itertools.combinations(range(n + len(features) - 1), len(features) - 1):
        bounds = (-1, *cut, n + len(features) - 1)
        out.append({f: round((bounds[i + 1] - bounds[i] - 1) * step, 6) for i, f in enumerate(features)})
    return out


def grid(rows: list[dict], base: dict[str, float], step: float = GRID_STEP) -> dict:
    """Best AC@1 on the given rows over the weight simplex; ties go to the vector closest (L1) to `base`."""
    feats = sorted(base)
    best = None
    for w in simplex(feats, step):
        ac1 = sum(
            label(r["case"])["service"] in services(rescore(r["parts"], {"w": w}))[:1] for r in rows if r["parts"]
        )
        key = (-ac1, round(sum(abs(w[f] - base[f]) for f in feats), 6), [w[f] for f in feats])
        if best is None or key < best[0]:
            best = (key, w, ac1)
    assert best is not None
    return {"w": best[1], "ac1": round(best[2] / max(1, len(rows)), 4), "base_ac1": round(sum(
        label(r["case"])["service"] in services(rescore(r["parts"], {"w": base}))[:1] for r in rows if r["parts"]
    ) / max(1, len(rows)), 4)}  # fmt: skip


def precision_at_3(sigs: dict[str, list[float]]) -> dict:
    """Leave-one-out memory recall: for each case, the 3 most similar other cases by cosine; a neighbour is relevant
    when it has the same service and fault. Cases with an empty signature get no recall (as in `historian.remember`).
    Limit: measures the signature, not Q5's vector index + re-rank; Q5 has its own test (test_memory)."""
    live = {c: v for c, v in sorted(sigs.items()) if any(v)}

    def cos(a: list[float], b: list[float]) -> float:
        na, nb = math.sqrt(sum(x * x for x in a)), math.sqrt(sum(x * x for x in b))
        return sum(x * y for x, y in zip(a, b, strict=True)) / (na * nb)

    precs = []
    for c, v in live.items():
        near = sorted((o for o in live if o != c), key=lambda o: (-round(cos(v, live[o]), 9), o))[:3]
        if not near:
            continue  # nothing else to recall
        lc = label(c)
        precs.append(sum((label(o)["service"], label(o)["fault"]) == (lc["service"], lc["fault"]) for o in near) / 3)
    return {"cases": len(precs), "p_at_3": round(sum(precs) / len(precs), 4) if precs else None}


def pct(xs: list[float], q: float) -> float | None:
    xs = sorted(xs)
    return round(xs[min(len(xs) - 1, int(len(xs) * q))], 1) if xs else None


# --- weights variants ---


def variants(base_path: str, out_dir: Path) -> dict[str, str]:
    """Base weights plus the four ablations, written next to the results so every run is reproducible."""
    base = sc.load_weights(base_path)
    out_dir.mkdir(parents=True, exist_ok=True)

    def renorm(w: dict[str, float]) -> dict[str, float]:
        t = sum(w.values())
        return {k: round(v / t, 6) for k, v in w.items()}

    def drop(*keys: str) -> dict[str, float]:
        return renorm({k: v for k, v in base["w"].items() if k not in keys})

    def zero(key: str) -> dict[str, float]:
        return renorm({k: 0.0 if k == key else v for k, v in base["w"].items()})

    specs = {
        "no_pagerank": {"w": zero("pagerank")},
        "no_temporal": {"ablate": ["temporal"]},
        "no_mechanism": {"w": zero("mechanism_fit"), "ablate": ["mechanism"]},
        "no_footprint": {"w": drop("footprint")},  # no footprint term → the simulator is off (v1)
    }
    paths = {"base": base_path}
    for name, spec in specs.items():
        w = base | spec | {"version": f"{base['version']}+{name}"}
        w["w"] = {k: round(v, 6) for k, v in w["w"].items()}
        drift = round(1.0 - sum(w["w"].values()), 6)  # rounding leftovers go to the largest weight
        top = max(sorted(w["w"]), key=lambda k: w["w"][k])
        w["w"][top] = round(w["w"][top] + drift, 6)
        p = out_dir / f"{name}.json"
        p.write_text(json.dumps(w, indent=1, sort_keys=True), encoding="utf-8")
        paths[name] = str(p)
    return paths


# --- graph steps ---


def run_case(graph: Graph, env_name: str, case_dir: Path, paths: dict[str, str]) -> tuple[dict, dict]:
    """Replay one case into a fresh scratch graph and diagnose it once per weights variant → (row, timing)."""
    env = graph.env(env_name)
    env.delete()
    try:
        t0 = time.perf_counter()
        inc = replay(case_dir, env_name, graph)["incident"]
        t_replay = time.perf_counter() - t0
        row: dict = {"case": case_dir.name, "split": split(case_dir.name) if _CASE.match(case_dir.name) else None,
                     "variants": {}}  # fmt: skip
        timing = {"case": case_dir.name, "replay_ms": round(t_replay * 1000, 1)}
        for name, path in paths.items():
            t1 = time.perf_counter()
            v = causal.diagnose(graph, env_name, inc, path)
            if name == "base":
                timing["diagnose_ms"] = round((time.perf_counter() - t1) * 1000, 1)
                r = causal.open_run(graph, env_name, inc, path)
                row["signature"] = [round(x, 6) for x in causal.incident_signature(r)]
                row["parts"] = [
                    {"op": h["op"], "onset": h["onset"], "parts": json.loads(h["score_parts"]) if h["score_parts"]
                     else None}
                    for h in env.ro("run_hypotheses", inc=inc, run=v["run"])
                    if h["id"] in {x["id"] for x in env.ro("round_hypotheses", inc=inc, run=v["run"], round=1)}
                ]  # fmt: skip
            row["variants"][name] = {
                "status": v["status"],
                "root_cause": v["root_cause"],
                "second_cause": v["second_cause"],
                "confidence": v["confidence"],
                "ranked": ranked_ops(v),
                "weights_version": v["weights_version"],
            }
        return row, timing
    finally:
        env.delete()


def summarize(rows: list[dict], system: str, rules_version: str) -> dict:
    def per(name: str, which: str | None = None) -> dict:
        xs = [{"case": r["case"], "ranked": r["variants"][name]["ranked"]} for r in rows
              if which is None or r["split"] == which]  # fmt: skip
        return metrics(xs)

    base = per("base")
    names = [n for n in rows[0]["variants"] if n != "base"] if rows else []
    return {
        "suite": "re2",
        "system": system,
        "cases": base["cases"],
        "ac1": base["ac1"],
        "ac3": base["ac3"],
        "by_fault": base["by_fault"],
        "split": {s: {k: per("base", s)[k] for k in ("cases", "ac1", "ac3")} for s in ("dev", "test")},
        "ablations": {n: {k: per(n)[k] for k in ("ac1", "ac3")} for n in names},
        "memory": precision_at_3({r["case"]: r["signature"] for r in rows}),
        "weights_version": rows[0]["variants"]["base"]["weights_version"] if rows else None,
        "rules_version": rules_version,
    }


def next_path(out: Path, stem: str) -> Path:
    out.mkdir(parents=True, exist_ok=True)
    n = 1 + max((int(p.name.split("-", 1)[0]) for p in out.glob("[0-9]*-*.json")), default=0)
    return out / f"{n:04d}-{stem}.json"


def run_suite(graph: Graph, case_dirs: list[Path], system: str, weights_path: str, out: Path = OUT) -> Path:
    paths = variants(weights_path, out / "weights")
    rules_version = load_rules(graph.kb())[1]
    rows, timings = [], []
    for i, d in enumerate(sorted(case_dirs, key=lambda p: p.name), 1):
        row, t = run_case(graph, f"eval-{system}", d, paths)
        rows.append(row)
        timings.append(t)
        print(f"[{i}/{len(case_dirs)}] {d.name}: {row['variants']['base']['root_cause']}", file=sys.stderr, flush=True)
    summary = summarize(rows, system, rules_version)
    wv = summary["weights_version"] or "none"
    path = next_path(out, f"re2-{system}-{wv}-{rules_version}".replace(",", "_"))
    path.write_text(json.dumps({"summary": summary, "rows": rows}, indent=1, sort_keys=True), encoding="utf-8")
    n1 = [t["replay_ms"] + t["diagnose_ms"] for t in timings]
    stats = query_stats()
    timing = {
        "n1_ms": {"p50": pct(n1, 0.5), "p95": pct(n1, 0.95), "max": max(n1, default=None)},
        "diagnose_ms": {
            "p50": pct([t["diagnose_ms"] for t in timings], 0.5),
            "p95": pct([t["diagnose_ms"] for t in timings], 0.95),
        },  # fmt: skip
        "n2_p95_ms": {q: stats[q]["p95"] for q in N2_QUERIES if q in stats},
        "cases": timings,
    }
    path.with_suffix(".timing.json").write_text(json.dumps(timing, indent=1, sort_keys=True), encoding="utf-8")
    return path


def latest(out: Path | None = None) -> dict | None:
    """The newest result's summary with its timings, every earlier RE2 run's headline, and the newest synthetic
    result (GET /eval)."""
    out = out or OUT
    files = sorted(p for p in out.glob("[0-9]*-re2-*.json") if not p.name.endswith(".timing.json"))
    if not files:
        return None
    res = json.loads(files[-1].read_text(encoding="utf-8"))
    t = files[-1].with_suffix(".timing.json")
    timing = json.loads(t.read_text(encoding="utf-8")) if t.exists() else {}
    ms = {c["case"]: c.get("diagnose_ms") for c in timing.get("cases", [])}
    history = []
    for f in files:
        s = json.loads(f.read_text(encoding="utf-8"))["summary"]
        history.append({"run": f.stem, "ac1": s["ac1"], "ac3": s["ac3"], "cases": s["cases"],
                        "weights_version": s.get("weights_version")})  # fmt: skip
    synth = sorted(p for p in out.glob("[0-9]*-synth-*.json") if not p.name.endswith(".timing.json"))
    extra = {
        "run": files[-1].stem,
        "n1_ms": timing.get("n1_ms"),
        "n2_p95_ms": timing.get("n2_p95_ms"),
        "history": history,
        "synth": {"run": synth[-1].stem} | json.loads(synth[-1].read_text(encoding="utf-8"))["summary"]
        if synth
        else None,
    }
    return res["summary"] | extra | {"per_case": per_case(res["rows"], ms)}


def per_case(rows: list[dict], diagnose_ms: dict[str, float] | None = None) -> list[dict]:
    """One line per case for the /eval table: label, our top-3 services (verdict first), hit@1 / hit@3, plus what
    the drill-down needs: confidence, time, each ablation's top-1 service and the verdict's score parts."""
    out = []
    for r in sorted(rows, key=lambda r: r["case"]):
        base = r["variants"]["base"]
        row = {"case": r["case"], "ranked": base["ranked"]}
        lab = label(r["case"])
        top = base["ranked"][0] if base["ranked"] else None
        parts = next((p["parts"] for p in r.get("parts", []) if p["op"] == top), {})
        out.append({
            "case": r["case"], "split": r["split"], "service": lab["service"], "fault": lab["fault"],
            "top3": services(row["ranked"])[:3], "hit1": hit_at(row, 1), "hit3": hit_at(row, 3),
            "confidence": base.get("confidence"), "diagnose_ms": (diagnose_ms or {}).get(r["case"]),
            "variants": {k: (services(v["ranked"]) or [None])[0]
                         for k, v in sorted(r["variants"].items()) if k != "base"},
            "parts": {k: v for k, v in sorted(parts.items()) if isinstance(v, int | float)},
        })  # fmt: skip
    return out


def synth_gen():
    """examples/synthetic/gen.py, loaded by path: it is a sample generator, not part of the api package."""
    spec = importlib.util.spec_from_file_location("synth_gen", Path(__file__).resolve().parents[1] / "examples" /
                                                  "synthetic" / "gen.py")  # fmt: skip
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def run_synth(graph: Graph, sizes: list[str], seed: int, weights_path: str, root: Path, out: Path = OUT) -> Path:
    """Every fault per size: generate (byte-identical per seed) → replay into `env:eval-synth` → diagnose → check.
    Reported apart from RCAEval, never mixed in (EXAMPLE_RUNS §4)."""
    gen = synth_gen()
    rules_version = load_rules(graph.kb())[1]
    rows, timings, by_size = [], [], {}
    for size in sizes:
        hits = []
        for fault in gen.FAULTS:
            try:
                d = gen.generate(size, fault, seed, root)
            except SystemExit as e:  # e.g. `two` on a topology with no independent pair
                rows.append({"size": size, "fault": fault, "skipped": str(e)})
                continue
            lab = json.loads((d / "labels.json").read_text(encoding="utf-8"))
            row, tm = run_case(graph, "eval-synth", d, {"base": weights_path})
            v = row["variants"]["base"]
            ok1 = gen.check(lab, v["status"], v["root_cause"], v["second_cause"])
            ok3 = ok1 or (lab["service"] is not None and lab["service"] in services(v["ranked"])[:3])
            rows.append({"size": size, "fault": fault, "case": d.name, "expected": lab["service"] or lab["status"],
                         "got": v["root_cause"] or v["status"], "ac1": ok1, "ac3": ok3, "ops": lab["ops"],
                         "spans": lab["spans"]})  # fmt: skip
            timings.append(tm | {"size": size})
            hits.append((ok1, ok3))
            print(f"{d.name}: {v['root_cause'] or v['status']} {'ok' if ok1 else 'MISS'}", file=sys.stderr, flush=True)
        by_size[size] = {"cases": len(hits), "ac1": round(sum(h[0] for h in hits) / len(hits), 4) if hits else None,
                         "ac3": round(sum(h[1] for h in hits) / len(hits), 4) if hits else None}  # fmt: skip
    wv = sc.load_weights(weights_path)["version"]
    path = next_path(out, f"synth-s{seed}-{wv}-{rules_version}".replace(",", "_"))
    summary = {
        "suite": "synth",
        "seed": seed,
        "by_size": by_size,
        "weights_version": wv,
        "rules_version": rules_version,
    }
    path.write_text(json.dumps({"summary": summary, "rows": rows}, indent=1, sort_keys=True), encoding="utf-8")
    path.with_suffix(".timing.json").write_text(json.dumps({"cases": timings}, indent=1, sort_keys=True),
                                                encoding="utf-8")  # fmt: skip
    return path


# --- CLI ---


def case_list(system: str) -> list[str]:
    """Every RE2 case of `system` on Hugging Face, cached in data/eval so later runs are offline."""
    cache = OUT / f"cases-re2{system}.json"
    if not cache.exists():
        with urllib.request.urlopen(HF_TREE, timeout=60) as r:
            names = sorted(x["path"] for x in json.load(r) if x["path"].startswith(f"re2{system}_"))
        OUT.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(names, indent=1), encoding="utf-8")
    return json.loads(cache.read_text(encoding="utf-8"))


def print_table(s: dict) -> None:
    f = lambda x: "  —  " if x is None else f"{x:.1%}"  # noqa: E731
    print(f"RE2-{s['system'].upper()}  {s['cases']} cases  weights {s['weights_version']}  rules {s['rules_version']}")
    print(f"  all        AC@1 {f(s['ac1'])}  AC@3 {f(s['ac3'])}")
    for k, v in s["split"].items():
        print(f"  {k:<10} AC@1 {f(v['ac1'])}  AC@3 {f(v['ac3'])}  ({v['cases']} cases)")
    print("  ablations")
    for k, v in s["ablations"].items():
        print(f"    {k:<14} AC@1 {f(v['ac1'])}  AC@3 {f(v['ac3'])}")
    print("  by fault   " + "  ".join(f"{k} {f(v['ac1'])}" for k, v in s["by_fault"].items()))
    print(f"  memory     P@3 {f(s['memory']['p_at_3'])} ({s['memory']['cases']} cases with a signature)")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="RCAEval accuracy suite with ablations")
    p.add_argument("--suite", default="re2", choices=["re2", "synth"])
    p.add_argument("--system", default="tt", choices=["tt", "ob"])
    p.add_argument("--weights", help="weights file (default: WEIGHTS_PATH)")
    p.add_argument("--cases", default="*", help="glob over case names")
    p.add_argument("--download", action="store_true", help="fetch missing cases from Hugging Face")
    p.add_argument("--grid", metavar="RESULT", help="search weights on the dev split of a stored result file")
    p.add_argument("--size", default="small,medium", help="synth: comma-separated sizes (small, medium, huge)")
    p.add_argument("--seed", type=int, default=1, help="synth: generator seed")
    a = p.parse_args(argv)
    s = get_settings()

    if a.suite == "synth":
        g = Graph(s.falkordb_url, s.query_timeout_s)
        path = run_synth(g, a.size.split(","), a.seed, a.weights or s.weights_path, Path(s.rcaeval_dir))
        res = json.loads(path.read_text(encoding="utf-8"))
        for r in res["rows"]:
            mark = "skip" if "skipped" in r else ("PASS" if r["ac1"] else "MISS")
            print(
                f"{mark}  {r['size']:<7} {r['fault']:<12} expected {r.get('expected', '-'):<14} got {r.get('got', '-')}"
            )
        for size, m in res["summary"]["by_size"].items():
            print(f"{size:<7} AC@1 {m['ac1']:.1%}  AC@3 {m['ac3']:.1%}  ({m['cases']} cases)")
        print(f"→ {path}")
        return 0

    if a.grid:
        res = json.loads(Path(a.grid).read_text(encoding="utf-8"))
        base = sc.load_weights(a.weights or s.weights_path)["w"]
        dev = [r for r in res["rows"] if r["split"] == "dev"]
        g = grid(dev, base)
        print(json.dumps({"dev_cases": len(dev), **g}, indent=1, sort_keys=True))
        return 0

    root = Path(s.rcaeval_dir)
    names = [c for c in case_list(a.system) if fnmatch.fnmatch(c, a.cases)]
    if a.download:
        for c in names:
            download(c, root)
    dirs = [root / c for c in names if (root / c / "inject_time.txt").exists()]
    if len(dirs) < len(names):
        print(f"{len(names) - len(dirs)} of {len(names)} cases not on disk (add --download)", file=sys.stderr)
    if not dirs:
        return 2
    path = run_suite(Graph(s.falkordb_url, s.query_timeout_s), dirs, a.system, a.weights or s.weights_path)
    print_table(json.loads(path.read_text(encoding="utf-8"))["summary"])
    print(f"→ {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
