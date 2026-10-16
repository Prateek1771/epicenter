"""Causal search (LLD §2.2): hypotheses from Q1, onset order (Q2), mechanism and changes (Q3), PageRank (Q4), score.

    python -m api.search.causal --env rcaeval-tt --incident rc-re2tt_ts-auth-service_cpu_2

Every diagnosis is a kept, numbered run (`Incident.run`); its hypotheses and evidence carry ids
`<incident>:r<run>:h-<n>` / `:E<n>`, so earlier runs stay in the graph as history. No LLM in this module.
"""

import argparse
import json
import sys
import time

import networkx

from api.config import get_settings
from api.graph import EnvGraph, Graph, GraphUnavailable
from api.models import scoped_id
from api.search import score as sc

# --- Pure rules (table-tested in tests/test_causal.py) ---


def propagation_passes(onsets: list[int | None], skew_s: int) -> bool:
    """Q2 rule. `onsets` run from the symptom (index 0) to the candidate: the problem must have started at the candidate
    end and moved towards the symptom, i.e. onsets[i+1] <= onsets[i] + skew. A missing onset on the symptom itself is
    skipped (an alert can fire on an operation with no anomaly of its own, e.g. a load generator); anywhere else it
    fails the path (the problem didn't pass through that operation)."""
    seq = onsets[1:] if onsets and onsets[0] is None else onsets
    if any(o is None for o in seq):
        return False
    return all(seq[i + 1] <= seq[i] + skew_s for i in range(len(seq) - 1))


def best_path(paths: list[dict], skew_s: int) -> tuple[dict | None, bool]:
    """Best Q2 path: passing first, then fewest hops, then lexicographic."""
    if not paths:
        return None, False
    best = min(paths, key=lambda p: (not propagation_passes(p["onsets"], skew_s), len(p["path"]), p["path"]))
    return best, propagation_passes(best["onsets"], skew_s)


def is_victim(self_ratio: float | None, child_ratio: float | None) -> bool:
    """Q3 victim rule: the time is spent in its callees, so a callee explains it."""
    if self_ratio is None or child_ratio is None:
        return False
    return child_ratio >= 2 * self_ratio and child_ratio > 1.5


# --- Graph steps ---


def make_hypotheses(env: EnvGraph, incident: str, run: int, symptom: str) -> list[dict]:
    """Q1 candidates plus the symptom itself (hops 0) when it has an anomaly of its own."""
    rows = []
    own = env.ro("op_anomalies", inc=incident, op=symptom)
    if own and own[0]["kinds"]:
        rows.append({"op": symptom, "hops": 0, "onset": own[0]["onset"], "strength": own[0]["strength"]} | own[0])
    rows += [r for r in env.ro("Q1", symptom=symptom, inc=incident) if r["op"] != symptom]  # a call cycle can return it
    hyps = []
    for n, r in enumerate(rows, 1):
        hyps.append(
            {
                "id": scoped_id(incident, f"r{run}:h-{n}"),
                "op": r["op"],
                "hops": r["hops"],
                "onset": r["onset"],
                "strength": r["strength"],
                "kinds": sorted(r["kinds"]),
            }
        )
    return hyps


def check(env: EnvGraph, incident: str, symptom: str, h: dict, w: dict) -> list[dict]:
    """Q3 + Q2 for one hypothesis → evidence dicts (without ids). Reads only; phase 5 runs these in parallel."""
    ev = []
    # Q3 first: its rows carry the candidate's anomaly ids, which the propagation evidence cites (ABOUT edges)
    mech = env.ro("Q3", cand=h["op"], inc=incident, lookback_s=w["lookback_s"])
    cand_anomalies = sorted({row["anomaly"] for row in mech})
    if h["hops"] == 0:
        ev.append(
            {
                "rel": "support",
                "kind": "propagation",
                "summary": f"{symptom} is the alerting operation and has its own anomaly ({', '.join(h['kinds'])})",
                "path": [symptom],
                "value": json.dumps({"onsets": [h["onset"]]}),
                "anomalies": cand_anomalies,
            }
        )
    else:
        best, ok = best_path(env.ro("Q2", symptom=symptom, cand=h["op"], inc=incident), w["skew_s"])
        if best and ok:
            i, first = next((i, o) for i, o in enumerate(best["onsets"]) if o is not None)
            ev.append(
                {
                    "rel": "support",
                    "kind": "propagation",
                    "summary": f"{h['op']} went bad {first - h['onset']} s before {best['path'][i]}; onset order holds"
                    f" along {len(best['path']) - 1} hops to {symptom}",
                    "path": best["path"],
                    "value": json.dumps({"onsets": best["onsets"]}),
                    "anomalies": cand_anomalies,
                }
            )
        else:
            ev.append(
                {
                    "rel": "refute",
                    "kind": "propagation",
                    "summary": f"no path from {h['op']} to {symptom} where the problem started at {h['op']} and moved"
                    f" towards the symptom (onsets along the best path: {best['onsets'] if best else []})",
                    "path": best["path"] if best else [],
                    "value": json.dumps({"onsets": best["onsets"] if best else []}),
                    "anomalies": cand_anomalies,
                }
            )

    h["victim"] = False
    h["self_caused"] = None
    h["change"] = False
    for row in mech:
        if is_victim(row["self_ratio"], row["child_ratio"]):
            h["victim"] = True
            ev.append(
                {
                    "rel": "refute",
                    "kind": "victim",
                    "summary": f"{h['op']} is a victim: time in its callees grew ×{row['child_ratio']}, its own time"
                    f" ×{row['self_ratio']}",
                    "path": [h["op"]],
                    "value": json.dumps({"self_ratio": row["self_ratio"], "child_ratio": row["child_ratio"]}),
                    "anomalies": [row["anomaly"]],
                }
            )
        elif row["self_ratio"] is not None and row["child_ratio"] is not None:
            h["self_caused"] = h["self_caused"] or row["self_ratio"] >= row["child_ratio"]
    changes = sorted({c["id"]: c for row in mech for c in row["changes"]}.values(), key=lambda c: (c["ts"], c["id"]))
    if changes:
        h["change"] = True
        c = changes[-1]  # the latest change before the onset
        ev.append(
            {
                "rel": "support",
                "kind": "change",
                "summary": f"{c['summary']} ({c['type']}) {h['onset'] - c['ts']} s before {h['op']} went bad",
                "path": [h["op"]],
                "value": json.dumps({"change": c["id"], "ts": c["ts"]}),
                "anomalies": [],
                "changes": [c["id"] for c in changes],
            }
        )
    return ev


def pagerank(graph: Graph, env: EnvGraph, incident: str) -> tuple[dict[str, float], str]:
    """Q4: project the anomalous ops and the calls among them into scratch:<incident>, rank, delete the scratch graph.
    Falls back to networkx on the same edge list if FalkorDB's algo.pageRank fails."""
    edges = env.ro("Q4a", inc=incident)
    if not edges:
        return {}, "none"
    scratch = graph.scratch(incident)
    try:
        scratch.delete()
        scratch.rw("Q4_blame", edges=[{"caller": e["caller"], "callee": e["callee"], "w": 1.0} for e in edges])
        return {r["op"]: r["score"] for r in scratch.ro("Q4b")}, "falkordb"
    except GraphUnavailable:
        raise
    except Exception:
        g = networkx.DiGraph()
        g.add_edges_from(sorted((e["caller"], e["callee"]) for e in edges))
        return dict(networkx.pagerank(g)), "networkx"
    finally:
        scratch.delete()


def diagnose(graph: Graph, env_name: str, incident: str, weights_path: str | None = None) -> dict:
    """One full, deterministic diagnosis run. Returns the verdict; everything is also written to the graph."""
    w = sc.load_weights(weights_path or get_settings().weights_path)
    env = graph.env(env_name)
    [inc] = env.rw("next_run", inc=incident)
    run, symptom, ingest = inc["run"], inc["symptom"], inc["ingest"]

    hyps = make_hypotheses(env, incident, run, symptom)
    env.rw(
        "H_create",
        inc=incident,
        run=run,
        ingest=ingest,
        rows=[{k: h[k] for k in ("id", "op", "hops", "onset")} for h in hyps],
    )

    evidence, n = [], 0
    for h in hyps:
        try:
            found = check(env, incident, symptom, h, w)
        except GraphUnavailable:
            h.update(victim=False, self_caused=None, change=False)  # no evidence → inconclusive below
            found = []
        for e in found:
            n += 1
            e.update(id=scoped_id(incident, f"r{run}:E{n}"), hyp=h["id"], by="investigator")
        evidence += found
        h["refuted"] = any(e["rel"] == "refute" for e in found)
        h["status"] = (
            "refuted" if h["refuted"] else "supported" if any(e["rel"] == "support" for e in found) else "inconclusive"
        )
    for rel, qid in (("support", "E_support"), ("refute", "E_refute")):
        rows = [{k: e[k] for k in ("id", "hyp", "by", "kind", "summary", "path", "value", "anomalies")}
                for e in evidence if e["rel"] == rel]  # fmt: skip
        if rows:
            env.rw(qid, inc=incident, rows=rows)
    about = [{"evidence": e["id"], "change": c} for e in evidence for c in e.get("changes", [])]
    if about:
        env.rw("E_about_change", rows=about)

    ranks, impl = pagerank(graph, env, incident)
    for h in hyps:
        h["pagerank"] = ranks.get(h["op"], 0.0)
        h["footprint"] = 0.0  # phase 4 (Fault Simulator)
    for h, f in zip(hyps, sc.features(hyps), strict=True):
        h["features"] = f
        h["score"] = sc.score(f, w)
        h["score_parts"] = sc.score_parts_json(f, {"pagerank_impl": impl})

    ordered = sc.ranking(hyps)
    top = next((h for h in ordered if h["status"] != "refuted"), None)
    conf = sc.confidence([h["score"] for h in hyps if h["status"] != "refuted"], w["k"])
    for h in hyps:
        if h is top:
            h["status"] = "confirmed"
        elif h["status"] in ("supported", "inconclusive"):
            h["status"] = "pruned"
    env.rw("H_score", rows=[{k: h[k] for k in ("id", "status", "score", "score_parts")} for h in hyps])
    if top:
        env.rw(
            "root_cause",
            inc=incident,
            hyp=top["id"],
            rank=1,
            run=run,
            ingest=ingest,
            confidence=conf,
            wv=w["version"],
            ts=int(time.time()),
        )

    return {
        "incident": incident,
        "run": run,
        "ingest": ingest,
        "symptom": symptom,
        "root_cause": top["op"] if top else None,
        "confidence": conf if top else None,
        "weights_version": w["version"],
        "pagerank_impl": impl,
        "hypotheses": len(hyps),
        "statuses": {s: sum(h["status"] == s for h in hyps) for s in sorted({h["status"] for h in hyps})},
        "ranking": [
            {"id": h["id"].rsplit(":", 1)[-1], "op": h["op"], "status": h["status"], "score": h["score"]}
            for h in ordered
        ],
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Diagnose one incident (a new, kept run)")
    p.add_argument("--env", required=True)
    p.add_argument("--incident", required=True)
    p.add_argument("--weights", help="weights file (default: WEIGHTS_PATH)")
    p.add_argument("--top", type=int, default=10)
    a = p.parse_args(argv)
    s = get_settings()
    v = diagnose(Graph(s.falkordb_url, s.query_timeout_s), a.env, a.incident, a.weights)
    v["ranking"] = v["ranking"][: a.top]
    print(json.dumps(v, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
