"""Causal search (LLD §2.2): hypotheses from Q1, onset order (Q2), mechanism and changes (Q3), Fault Simulator
footprint (Q6, LLD §7), PageRank (Q4), score.

    python -m api.search.causal --env rcaeval-tt --incident rc-re2tt_ts-auth-service_cpu_2

Every diagnosis is a kept, numbered run (`Incident.run`); its hypotheses and evidence carry ids
`<incident>:r<run>:h-<n>` / `:E<n>.<k>` (k-th evidence of hypothesis n), so earlier runs stay in the graph as history.

The diagnosis is a set of steps that share state through the graph only (ADR 0007): `start_run`, `triage`,
`investigate` (one per hypothesis, safe to run in parallel), `score_round`, `skeptic`, `decide`, `finalize`.
`diagnose()` runs them in order; `api/agents/flow.py` runs the same steps as a LangGraph flow. No LLM in this module.
"""

import argparse
import json
import sys
import time
from dataclasses import dataclass, field

import networkx

from api.config import get_settings
from api.graph import EnvGraph, Graph, GraphUnavailable
from api.models import local_id, scoped_id
from api.search import score as sc
from api.search.simulate import Simulator, match, observed_set

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


@dataclass
class Run:
    """Handle on one diagnosis run. Holds only what can be re-read from the graph, so any process can rebuild it."""

    graph: Graph
    env: EnvGraph
    incident: str
    run: int
    ingest: int
    symptom: str
    w: dict
    _sim: "Simulator | None" = field(default=None, repr=False)
    _observed: dict | None = field(default=None, repr=False)
    _ranks: tuple | None = field(default=None, repr=False)

    @property
    def use_sim(self) -> bool:
        return "footprint" in self.w["w"]

    @property
    def sim(self) -> "Simulator | None":
        if self.use_sim and self._sim is None:
            self._sim = Simulator(self.graph, self.env, self.w["simulator"], self.w["skew_s"])
        return self._sim

    @property
    def observed(self) -> dict[str, dict]:
        if self._observed is None:
            self._observed = observed_set(self.env.ro("observed", inc=self.incident))
        return self._observed

    @property
    def ranks(self) -> tuple[dict[str, float], str]:
        if self._ranks is None:
            self._ranks = pagerank(self.graph, self.env, self.incident)
        return self._ranks


def start_run(graph: Graph, env_name: str, incident: str, weights_path: str | None = None) -> Run:
    """Open a new, kept diagnosis run (Incident.run + 1, status diagnosing)."""
    env = graph.env(env_name)
    [inc] = env.rw("next_run", inc=incident)
    w = sc.load_weights(weights_path or get_settings().weights_path)
    return Run(graph, env, incident, inc["run"], inc["ingest"], inc["symptom"], w)


def open_run(graph: Graph, env_name: str, incident: str, weights_path: str | None = None) -> Run:
    """The incident's current run, rebuilt from the graph (used by agent nodes and resume)."""
    env = graph.env(env_name)
    [inc] = env.ro("incident", inc=incident)
    w = sc.load_weights(weights_path or get_settings().weights_path)
    return Run(graph, env, incident, inc["run"], inc["ingest"] or 1, inc["symptom"], w)


def _hyp_no(hyp_id: str) -> int:
    return int(hyp_id.rsplit("h-", 1)[1])


def triage(
    r: Run, round_: int = 1, seed: str | None = None, scope: list[str] | None = None, exclude: str | None = None
) -> list[dict]:
    """Hypotheses: Q1 candidates upstream of `seed` (default: the symptom) plus the seed itself when it has an anomaly
    of its own. Round 2 (second cause) is scoped to the symptoms the winner left unexplained. Written with MERGE."""
    seed = seed or r.symptom
    rows = []
    own = r.env.ro("op_anomalies", inc=r.incident, op=seed)
    if own and own[0]["kinds"]:
        rows.append({"op": seed, "hops": 0, "onset": own[0]["onset"], "strength": own[0]["strength"]} | own[0])
    rows += [x for x in r.env.ro("Q1", symptom=seed, inc=r.incident) if x["op"] != seed]  # a call cycle can return it
    rows = [x for x in rows if x["op"] != exclude]
    start = 1 + max((_hyp_no(h["id"]) for h in r.env.ro("run_hypotheses", inc=r.incident, run=r.run)), default=0)
    hyps = [
        {
            "id": scoped_id(r.incident, f"r{r.run}:h-{n}"),
            "op": x["op"],
            "hops": x["hops"],
            "onset": x["onset"],
            "strength": x["strength"],
            "kinds": sorted(x["kinds"]),
            "round": round_,
            "seed": seed,
            "scope": sorted(scope) if scope is not None else None,
        }
        for n, x in enumerate(rows, start)
    ]
    if hyps:
        r.env.rw("H_create", inc=r.incident, run=r.run, ingest=r.ingest, rows=hyps)
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


def footprint_evidence(h: dict, sim: Simulator, observed: dict[str, dict], cfg: dict) -> dict:
    """Fault Simulator check for one hypothesis (LLD §7): predicted vs observed → footprint feature + evidence."""
    preds = sim.predict(h["op"], h["kinds"], h["onset"])
    m = match(preds, observed)
    h.update(footprint=m["footprint"], coverage=m["coverage"], unexplained=m["unexplained"])
    return {
        "rel": "support" if m["coverage"] >= cfg["refute_below_coverage"] else "refute",
        "kind": "footprint",
        "summary": f"{m['explains']} (precision {m['precision']:.2f}, order {m['order']:.2f})",
        "path": [h["op"]],
        "value": json.dumps(
            m | {"rules_version": sim.rules_version, "predictions": [[p.op, p.kind, p.p, p.hops] for p in preds]},
            sort_keys=True,
        ),
        "anomalies": sorted(a for op in m["matched"] for a in observed[op]["anomalies"]),
    }


def investigate(r: Run, hyp_id: str) -> dict:
    """One investigator: Q3, Q2 and the Fault Simulator for one hypothesis. Writes only under that hypothesis (its
    evidence ids are `E<n>.<k>`, n = the hypothesis number), so investigators can run in parallel; a re-run after a
    crash MERGEs onto what it already wrote. Returns the evidence and the footprint for event publishing."""
    [h] = r.env.ro("hypothesis", id=hyp_id)
    if h["facts"] is not None:  # finished before a crash: nothing to redo
        return {"id": hyp_id, "status": h["status"], "evidence": [], "footprint": None}
    observed = r.observed if h["scope"] is None else {op: r.observed[op] for op in h["scope"] if op in r.observed}
    h = dict(h)
    footprint = None
    try:
        found = check(r.env, r.incident, h["seed"], h, r.w)
        if r.sim is not None:
            fp = footprint_evidence(h, r.sim, observed, r.w["simulator"])
            footprint = json.loads(fp["value"])
            found.append(fp)
    except GraphUnavailable:
        found = []
        h.update(victim=False, self_caused=None, change=False)
    n = _hyp_no(hyp_id)
    for k, e in enumerate(found, 1):
        e.update(id=scoped_id(r.incident, f"r{r.run}:E{n}.{k}"), hyp=hyp_id, by="investigator")
    for rel, qid in (("support", "E_support"), ("refute", "E_refute")):
        rows = [{k: e[k] for k in ("id", "hyp", "by", "kind", "summary", "path", "value", "anomalies")}
                for e in found if e["rel"] == rel]  # fmt: skip
        if rows:
            r.env.rw(qid, inc=r.incident, rows=rows)
    about = [{"evidence": e["id"], "change": c} for e in found for c in e.get("changes", [])]
    if about:
        r.env.rw("E_about_change", rows=about)
    refuted = any(e["rel"] == "refute" for e in found)
    status = "refuted" if refuted else "supported" if any(e["rel"] == "support" for e in found) else "inconclusive"
    facts = {
        "victim": h.get("victim", False),
        "self_caused": h.get("self_caused"),
        "change": h.get("change", False),
        "footprint": h.get("footprint", 0.0),
        "coverage": h.get("coverage", 0.0),
        "unexplained": h.get("unexplained", []),
    }
    r.env.rw("H_facts", id=hyp_id, status=status, facts=json.dumps(facts, sort_keys=True))
    return {"id": hyp_id, "status": status, "evidence": found, "footprint": footprint}


def score_round(r: Run, round_: int) -> list[dict]:
    """Scorer: features + scores for one round's hypotheses, read back from the graph. Returns them ranked."""
    ranks, impl = r.ranks
    hyps = []
    for row in r.env.ro("round_hypotheses", inc=r.incident, run=r.run, round=round_):
        f = json.loads(row["facts"]) if row["facts"] else {}
        hyps.append(
            {
                "id": row["id"],
                "op": row["op"],
                "onset": row["onset"],
                "strength": row["strength"],
                "kinds": row["kinds"] or [],
                "status": row["status"],
                "victim": f.get("victim", False),
                "self_caused": f.get("self_caused"),
                "change": f.get("change", False),
                "footprint": f.get("footprint", 0.0),
                "coverage": f.get("coverage", 0.0),
                "unexplained": f.get("unexplained", []),
                "refuted": row["status"] == "refuted",
                "pagerank": ranks.get(row["op"], 0.0),
            }
        )
    for h, f in zip(hyps, sc.features(hyps), strict=True):
        h["score"] = sc.score(f, r.w)
        h["score_parts"] = sc.score_parts_json(f, {"pagerank_impl": impl})
    if hyps:
        r.env.rw("H_score", rows=[{k: h[k] for k in ("id", "score", "score_parts")} for h in hyps])
    return sc.ranking(hyps)


def pick(ordered: list[dict]) -> dict | None:
    return next((h for h in ordered if h["status"] != "refuted"), None)


def skeptic(r: Run, winner: dict) -> bool:
    """Deterministic challenge of the provisional winner: if the alerting operation has an anomaly of its own, the
    winner's footprint must explain it. Returns True if the winner is refuted (the scorer then runs again). The LLM
    (phase 7) may only choose *which* deterministic check to run first, so the verdict never depends on it (N7)."""
    if not r.use_sim or r.symptom not in r.observed or winner["op"] == r.symptom:
        return False
    if r.symptom not in winner["unexplained"]:
        return False
    eid = scoped_id(r.incident, f"r{r.run}:E{_hyp_no(winner['id'])}.s")
    r.env.rw(
        "E_refute",
        inc=r.incident,
        rows=[
            {
                "id": eid,
                "hyp": winner["id"],
                "by": "skeptic",
                "kind": "footprint",
                "summary": f"{winner['op']} does not explain the alerting operation {r.symptom}",
                "path": [winner["op"], r.symptom],
                "value": json.dumps({"symptom": r.symptom}),
                "anomalies": r.observed[r.symptom]["anomalies"],
            }
        ],
    )
    r.env.rw("H_status", id=winner["id"], status="refuted")
    return True


def decide(r: Run, ordered: list[dict]) -> dict:
    """After the scorer and skeptic: `no_root_cause` (§7.6) or commit the winner as ROOT_CAUSE {rank: 1}.
    Returns {no_root_cause, winner, second_seed, second_scope}."""
    top = pick(ordered)
    sim_cfg = r.w["simulator"]
    best_cov = max((h["coverage"] for h in ordered), default=0.0)
    strongest = max((o["score"] for o in r.observed.values()), default=0.0)
    nrc = sim_cfg["no_root_cause"]
    if top is None or (r.use_sim and best_cov < nrc["max_coverage"] and strongest < nrc["max_anomaly"]):
        summary = (
            f"Nothing in the graph explains this alert: checked {len(ordered)} hypotheses upstream of {r.symptom}; "
            f"the best explains {best_cov:.0%} of the symptoms and the strongest anomaly scores {strongest:.2f}"
        )
        r.env.rw("incident_no_root_cause", inc=r.incident, summary=summary, wv=r.w["version"])
        return {"no_root_cause": True, "summary": summary, "winner": None, "max_coverage": best_cov}
    conf = sc.confidence([h["score"] for h in ordered if h["status"] != "refuted"], r.w["k"])
    _commit(r, top, 1, conf)
    out = {"no_root_cause": False, "winner": top | {"confidence": conf}, "second_seed": None, "second_scope": None}
    u = top["unexplained"]
    sc_cfg = sim_cfg["second_cause"]
    if r.use_sim and (
        len(u) >= sc_cfg["min_unexplained_ops"] or any(r.observed[x]["score"] >= sc_cfg["strong_anomaly"] for x in u)
    ):
        out["second_seed"] = min(u, key=lambda x: (r.observed[x]["onset"], x))
        out["second_scope"] = u
    return out


def pick_second(r: Run, winner: dict, ordered: list[dict]) -> dict | None:
    """The second cause must be an independent fault: another service, explaining enough of what was left (§7.5)."""
    cfg = r.w["simulator"]["second_cause"]
    svc = winner["op"].split("/", 1)[0]
    second = next(
        (
            h
            for h in ordered
            if h["status"] != "refuted" and h["op"].split("/", 1)[0] != svc and h["coverage"] >= cfg["min_coverage"]
        ),
        None,
    )
    if second:
        conf = sc.confidence([h["score"] for h in ordered if h["status"] != "refuted"], r.w["k"])
        _commit(r, second, 2, conf)
    return second


def _commit(r: Run, h: dict, rank: int, conf: float) -> None:
    r.env.rw(
        "root_cause",
        inc=r.incident,
        hyp=h["id"],
        rank=rank,
        run=r.run,
        ingest=r.ingest,
        confidence=conf,
        wv=r.w["version"],
        ts=int(time.time()),
    )
    h["status"] = "confirmed"


def finalize(r: Run) -> list[str]:
    """Every hypothesis ends terminal: supported / inconclusive ones that didn't win become pruned."""
    return [x["id"] for x in r.env.rw("H_prune", inc=r.incident, run=r.run)]


def read_verdict(r: Run) -> dict:
    """The run's verdict, read back from the graph. The sequential `diagnose()` and the agent flow both return this, so
    they can't disagree about what was written."""
    [inc] = r.env.ro("incident", inc=r.incident)
    hyps = r.env.ro("round_hypotheses", inc=r.incident, run=r.run, round=1)
    for h in hyps:
        h["coverage"] = json.loads(h["facts"] or "{}").get("coverage", 0.0)
    causes = {c["rank"]: c for c in r.env.ro("root_causes", inc=r.incident)}
    top = next((h for h in hyps if causes.get(1) and h["id"] == causes[1]["hypothesis"]), None)
    final = [x["status"] for x in r.env.ro("run_hypotheses", inc=r.incident, run=r.run)]
    impl = next((json.loads(h["score_parts"])["pagerank_impl"] for h in r.env.ro("run_hypotheses", inc=r.incident,
                 run=r.run) if h["score_parts"]), "none")  # fmt: skip
    return {
        "incident": r.incident,
        "run": r.run,
        "ingest": r.ingest,
        "symptom": r.symptom,
        "status": inc["status"],
        "summary": inc["summary"],
        "root_cause": causes[1]["op"] if 1 in causes else None,
        "confidence": causes[1]["confidence"] if 1 in causes else None,
        "explains": f"{top['coverage']:.0%} of symptoms" if top and r.use_sim else None,
        "second_cause": causes[2]["op"] if 2 in causes else None,
        "weights_version": r.w["version"],
        "pagerank_impl": impl,
        "hypotheses": len(final),
        "statuses": {s: final.count(s) for s in sorted(set(final))},
        "ranking": [
            {
                "id": local_id(h["id"]),
                "op": h["op"],
                "status": h["status"],
                "score": h["score"],
                "coverage": h["coverage"],
            }
            for h in sc.ranking([h | {"score": h["score"] if h["score"] is not None else -9.0} for h in hyps])
        ],
    }


def score_and_challenge(r: Run) -> list[dict]:
    """Scorer ↔ skeptic loop: up to 2 skeptic challenges; after a refutation the scorer ranks again."""
    for i in range(3):
        ordered = score_round(r, 1)
        top = pick(ordered)
        if top is None or i == 2 or not skeptic(r, top):
            return ordered
    return ordered


def diagnose(graph: Graph, env_name: str, incident: str, weights_path: str | None = None) -> dict:
    """One full, deterministic diagnosis run, step by step in this process (the agent flow runs the same steps)."""
    r = start_run(graph, env_name, incident, weights_path)
    for h in triage(r):
        investigate(r, h["id"])
    ordered = score_and_challenge(r)
    decision = decide(r, ordered)
    if decision.get("second_seed"):
        w = decision["winner"]
        round2 = triage(r, 2, decision["second_seed"], decision["second_scope"], exclude=w["op"])
        for h in round2:
            investigate(r, h["id"])
        if round2:
            pick_second(r, w, score_round(r, 2))
    finalize(r)
    return read_verdict(r)


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
