"""Fault Simulator (LLD §7, ADR 0011): "if this were the cause, what would we see?"

    python -m api.search.simulate --env rcaeval-tt --target ts-auth-service --kind cpu [--save]

`simulate` and `match` are pure (rules, paths, observations in → predictions, scores out); the graph wrappers only
fetch Q6 paths, per-op traffic and rules. Deterministic: inputs sorted, ties broken on op id, no randomness.
"""

import argparse
import json
import sys
import time
from dataclasses import dataclass

import numpy as np

from api.config import get_settings
from api.graph import EnvGraph, Graph


@dataclass(frozen=True)
class Rule:
    id: str
    cause_kinds: tuple[str, ...]
    symptom_kind: str
    direction: str  # upstream · self
    p: float
    delay_s_max: int
    service_kind: str | None


@dataclass(frozen=True)
class Prediction:
    op: str
    kind: str
    p: float
    hops: int
    path: tuple[str, ...]  # candidate … op
    onset_window: tuple[int, int]


def load_rules(kb: EnvGraph) -> tuple[list[Rule], str]:
    """Rules from kb:propagation, sorted by id, plus their version (recorded on every footprint)."""
    rows = kb.ro("rules")
    rules = [
        Rule(
            r["id"],
            tuple(r["cause_kinds"]),
            r["symptom_kind"],
            r["direction"],
            r["p"],
            r["delay_s_max"],
            r["service_kind"],
        )
        for r in rows
    ]
    versions = sorted({r["version"] for r in rows})
    return rules, ",".join(versions)


def _applies(rule: Rule, cause_kind: str, direction: str, service_kind: str | None) -> bool:
    return (
        rule.direction == direction
        and cause_kind in rule.cause_kinds
        and (rule.service_kind is None or rule.service_kind == service_kind)
    )


def simulate(
    cand: str,
    cause_kinds: list[str],
    t_cause: int,
    paths: list[dict],
    op_info: dict[str, dict],
    rules: list[Rule],
    min_p: float,
    skew_s: int,
) -> list[Prediction]:
    """Predicted footprint of a fault of `cause_kinds` on `cand` (LLD §7.2).

    paths: Q6 rows (`path` = caller … cand, `rps` per hop); op_info: op → {service_kind, in_rps}.
    Hop by hop from the candidate outwards: p'[k2] = max over k1 of p[k1] · rule(k1→k2).p · share, with
    share = min(1, call.rps / Σ inbound rps of the caller). An entry point (no inbound calls) gets share 1: Operation
    stores no rps of its own, so its whole load is taken to depend on the call.
    """
    best: dict[tuple[str, str], Prediction] = {}

    def keep(pred: Prediction) -> None:
        k = (pred.op, pred.kind)
        old = best.get(k)
        if old is None or (pred.p, -pred.hops, pred.path) > (old.p, -old.hops, old.path):
            best[k] = pred

    cand_kind = op_info.get(cand, {}).get("service_kind")
    for kind in sorted(set(cause_kinds)):
        keep(Prediction(cand, kind, 1.0, 0, (cand,), (t_cause - skew_s, t_cause)))
        for r in rules:
            if _applies(r, kind, "self", cand_kind):
                keep(Prediction(cand, r.symptom_kind, r.p, 0, (cand,), (t_cause - skew_s, t_cause + r.delay_s_max)))

    for row in sorted(paths, key=lambda r: (len(r["path"]), r["path"])):
        chain = list(reversed(row["path"]))  # cand, first caller, …
        rps = list(reversed(row["rps"]))  # rps[i] = call from chain[i+1] into chain[i]
        state = {k: (1.0, 0) for k in sorted(set(cause_kinds))}  # kind → (p, accumulated max delay)
        for hop in range(1, len(chain)):
            callee, caller = chain[hop - 1], chain[hop]
            in_rps = op_info.get(caller, {}).get("in_rps") or 0.0
            share = 1.0 if in_rps <= 0 else min(1.0, rps[hop - 1] / in_rps)
            callee_kind = op_info.get(callee, {}).get("service_kind")
            nxt: dict[str, tuple[float, int]] = {}
            for k1, (p1, delay) in state.items():
                for r in rules:
                    if not _applies(r, k1, "upstream", callee_kind):
                        continue
                    p2 = round(p1 * r.p * share, 6)
                    if p2 >= min_p and p2 > nxt.get(r.symptom_kind, (0.0, 0))[0]:
                        nxt[r.symptom_kind] = (p2, delay + r.delay_s_max)
            if not nxt:
                break
            state = nxt
            for k2, (p2, delay) in sorted(state.items()):
                keep(Prediction(caller, k2, p2, hop, tuple(chain[: hop + 1]), (t_cause - skew_s, t_cause + delay)))

    return sorted(best.values(), key=lambda p: (p.hops, p.op, p.kind))


def spearman(x: list[float], y: list[float]) -> float | None:
    """Spearman rank correlation (average ranks for ties); None if either side has no variance."""

    def ranks(v: list[float]) -> np.ndarray:
        a = np.asarray(v, dtype=float)
        order = a.argsort(kind="stable")
        r = np.empty(len(a))
        r[order] = np.arange(len(a))
        for val in np.unique(a):  # average the ranks of ties
            r[a == val] = r[a == val].mean()
        return r

    rx, ry = ranks(x), ranks(y)
    if rx.std() == 0 or ry.std() == 0:
        return None
    return float(np.corrcoef(rx, ry)[0, 1])


def match(predictions: list[Prediction], observed: dict[str, dict]) -> dict:
    """Predicted vs observed (LLD §7.4). observed: op → {kinds, onset, score}. An observed op is matched when any of
    its kinds is predicted on it with its onset inside that prediction's window."""
    by_op: dict[str, list[Prediction]] = {}
    for p in predictions:
        by_op.setdefault(p.op, []).append(p)
    matched: dict[str, Prediction] = {}
    for op in sorted(observed):
        o = observed[op]
        hits = [
            p
            for p in by_op.get(op, [])
            if p.kind in o["kinds"] and p.onset_window[0] <= o["onset"] <= p.onset_window[1]
        ]
        if hits:
            matched[op] = max(hits, key=lambda p: (p.p, -p.hops))
    unexplained = sorted(set(observed) - set(matched))
    missed = sorted({p.op for p in predictions} - set(observed))
    coverage = len(matched) / len(observed) if observed else 0.0
    total_p = sum(max(p.p for p in ps) for ps in by_op.values())
    precision = sum(m.p for m in matched.values()) / total_p if total_p else 0.0
    rho = (
        spearman([m.hops for m in matched.values()], [observed[op]["onset"] for op in matched])
        if len(matched) >= 3
        else None
    )
    order = 0.5 if rho is None else (rho + 1) / 2
    footprint = 0.5 * coverage + 0.3 * precision + 0.2 * order
    return {
        "coverage": round(coverage, 6),
        "precision": round(precision, 6),
        "order": round(order, 6),
        "footprint": round(footprint, 6),
        "matched": sorted(matched),
        "missed": missed,
        "unexplained": unexplained,
        "explains": f"explains {len(matched)} of {len(observed)} symptoms",
    }


def observed_set(rows: list[dict]) -> dict[str, dict]:
    """`observed` query rows → op → {kinds, onset, score, anomalies}."""
    return {
        r["op"]: {
            "kinds": sorted(r["kinds"]),
            "onset": r["onset"],
            "score": r["score"],
            "anomalies": sorted(r["anomalies"]),
        }
        for r in rows
    }


class Simulator:
    """Graph access for one diagnosis or what-if: rules, Q6 paths and per-op traffic are fetched once and cached."""

    def __init__(self, graph: Graph, env: EnvGraph, sim_cfg: dict, skew_s: int):
        self.env = env
        self.cfg = sim_cfg
        self.skew_s = skew_s
        self.rules, self.rules_version = load_rules(graph.kb())
        self._paths: dict[str, list[dict]] = {}
        self._info: dict[str, dict] = {}

    def paths(self, op: str) -> list[dict]:
        if op not in self._paths:
            self._paths[op] = self.env.ro("Q6", cand=op)
        return self._paths[op]

    def info(self, ops: list[str]) -> dict[str, dict]:
        missing = sorted(set(ops) - set(self._info))
        if missing:
            for r in self.env.ro("op_info", ops=missing):
                self._info[r["op"]] = {"service_kind": r["service_kind"], "in_rps": r["in_rps"] or 0.0}
        return {op: self._info.get(op, {}) for op in ops}

    def predict(self, cand: str, cause_kinds: list[str], t_cause: int) -> list[Prediction]:
        paths = self.paths(cand)
        ops = sorted({cand} | {op for r in paths for op in r["path"]})
        return simulate(cand, cause_kinds, t_cause, paths, self.info(ops), self.rules, self.cfg["min_p"], self.skew_s)


def what_if(graph: Graph, env_name: str, target: str, kind: str, save: bool = False) -> dict:
    """ "What breaks if `target` (an operation, or every operation of a service) fails with `kind`?" No incident."""
    s = get_settings()
    w = json.loads(open(s.weights_path, encoding="utf-8").read())
    env = graph.env(env_name)
    sim = Simulator(graph, env, w["simulator"], w["skew_s"])
    ops = [target] if "/" in target else [r["op"] for r in env.ro("service_ops", svc=target)]
    merged: dict[tuple[str, str], Prediction] = {}
    for op in ops:
        for p in sim.predict(op, [kind], 0):
            k = (p.op, p.kind)
            if k not in merged or (p.p, -p.hops) > (merged[k].p, -merged[k].hops):
                merged[k] = p
    preds = sorted(merged.values(), key=lambda p: (p.hops, p.op, p.kind))
    owners = {r["op"]: r for r in env.ro("op_owners", ops=sorted({p.op for p in preds}))} if preds else {}
    out = [
        {
            "op": p.op,
            "kind": p.kind,
            "p": p.p,
            "hops": p.hops,
            "expected_delay_s": p.onset_window[1],
            "service": owners.get(p.op, {}).get("service"),
            "team": owners.get(p.op, {}).get("team"),
        }
        for p in preds
    ]
    result = {"target": target, "kind": kind, "rules_version": sim.rules_version, "predictions": out}
    if save and preds:
        ts = int(time.time())
        result["simulation"] = sim_id = f"sim-{target}-{kind}-{ts}"
        env.rw(
            "save_simulation",
            id=sim_id,
            target=target,
            kind=kind,
            ts=ts,
            rules_version=sim.rules_version,
            rows=[{"op": p.op, "p": p.p, "hops": p.hops, "kind": p.kind} for p in preds],
        )
    return result


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="What breaks if this operation or service fails?")
    p.add_argument("--env", required=True)
    p.add_argument("--target", required=True, help="operation id (svc/op) or service name")
    p.add_argument("--kind", required=True, help="errors · down · latency · cpu · mem · saturation")
    p.add_argument("--save", action="store_true", help="store it as a Simulation node")
    a = p.parse_args(argv)
    s = get_settings()
    print(json.dumps(what_if(Graph(s.falkordb_url, s.query_timeout_s), a.env, a.target, a.kind, a.save), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
