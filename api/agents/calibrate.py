"""Calibrate the jev_gate cutoff (`weights.json` `explanation.min_support`) from labelled claims.

    python -m api.agents.calibrate --env rcaeval-tt [--incident rc-…] [--passes 2] [--out data/calibration/jev.json]

For each incident's current run it builds claims whose truth is known without a model:
- TRUE: the template explanation and one restatement per evidence item, all built from the engine's own evidence;
- FALSE: each TRUE claim perturbed (another operation, a different number, "after" for "before"), plus claims that
  name a refuted hypothesis as the root cause or invent a deploy.
Every claim goes through the production gate (`narrator.gate_state` / `gate_questions` / `evidence_texts`) `passes`
times, because Jev isn't perfectly repeatable. The recommended cutoff is the lowest one that keeps no FALSE claim in
any pass, plus a margin. Reads the graph only; writes the report file. Costs a fraction of a cent per incident.
"""

import argparse
import json
import re
import sys
from pathlib import Path

from api.agents import narrator
from api.ai import jev
from api.graph import get_graph
from api.search import causal

GRID = [round(0.05 * i, 2) for i in range(1, 20)]
MARGIN = 0.05
NUMBER = re.compile(r"\d+(?:\.\d+)?")


def _subject(e: dict) -> str:
    return e["summary"] if e["summary"].startswith(e["op"]) else f"{e['op']}: {e['summary']}"


def true_claims(data: dict) -> list[dict]:
    """Claims that only restate the engine's own evidence (with the operation they are about)."""
    out = [{"text": c["text"], "cites": c["cites"]} for c in narrator.template(data)]
    out += [{"text": _subject(e), "cites": [e["id"]]} for e in data["evidence"]]
    seen, uniq = set(), []
    for c in out:
        if c["text"] not in seen:
            seen.add(c["text"])
            uniq.append(c)
    return uniq


def _bump(m: re.Match) -> str:
    s = m.group(0)
    return f"{float(s) + 7:.{len(s.split('.')[1])}f}" if "." in s else str(int(s) + 7)


def perturb(claim: dict, data: dict) -> list[dict]:
    """False variants of a true claim, same cites: another operation, a changed number, reversed time order."""
    text = claim["text"]
    ops = sorted(
        {h["op"] for h in data["hypotheses"]} | {data["symptom"]} | {o for e in data["evidence"] for o in e["path"]}
    )
    out = []
    found = [op for op in ops if op in text]
    found = [op for op in found if not any(op != o and op in o for o in found)]  # whole names, not a prefix of one
    mentioned = sorted(found, key=text.index)  # the subject comes first
    # swap in only operations with no evidence of their own, or the "false" claim may be true of that operation
    subjects = {e["op"] for e in data["evidence"]}
    others = [op for op in ops if op not in text and op not in subjects]
    if mentioned and others:
        out.append(text.replace(mentioned[0], others[0]))
    if NUMBER.search(text):
        out.append(NUMBER.sub(_bump, text, count=1))
    if " before " in text:
        out.append(text.replace(" before ", " after ", 1))
    return [{"text": t, "cites": claim["cites"]} for t in out if t != text]


def false_claims(data: dict, trues: list[dict]) -> list[dict]:
    out = [f for c in trues for f in perturb(c, data)]
    head = trues[0]["cites"] if trues else [e["id"] for e in data["evidence"][:1]]
    if data["root_cause"] and head:
        for h in [h for h in data["hypotheses"] if h["status"] == "refuted"][:2]:
            out.append({"text": f"{h['op']} is the root cause.", "cites": head})
        if not any(e["kind"] == "change" for e in data["evidence"]):
            svc = data["root_cause"].split("/", 1)[0]
            out.append({"text": f"A deploy of {svc} shortly before the alert caused the failure.", "cites": head})
    seen = {c["text"] for c in trues}
    return [c for c in out if c["text"] not in seen]


def pick_cutoff(trues: list[list[float]], falses: list[list[float]], margin: float = MARGIN) -> dict:
    """`trues` / `falses`: per claim, its score in each pass. A FALSE claim is accepted at cutoff t if any pass ≥ t."""
    table = []
    for t in GRID:
        fa = sum(any(p >= t for p in ps) for ps in falses)
        kept = [p >= t for ps in trues for p in ps]
        table.append({"cutoff": t, "false_accepts": fa, "true_kept": round(sum(kept) / len(kept), 3) if kept else 0.0})
    safe = next((row["cutoff"] for row in table if row["false_accepts"] == 0), None)
    rec = None if safe is None else min(0.95, round(safe + margin, 2))
    return {
        "recommended": rec,
        "max_false": max((max(ps) for ps in falses), default=None),
        "min_true": min((min(ps) for ps in trues), default=None),
        "table": table,
    }


def score(data: dict, claims: list[dict], passes: int) -> tuple[list[list[float]], float]:
    state, texts = narrator.gate_state(data), narrator.evidence_texts(data)
    scores, cost = [[] for _ in claims], 0.0
    for _ in range(passes):
        p, call = jev.noul(state, narrator.gate_questions(claims, texts))
        cost += call.get("cost") or 0.0
        for i in range(len(claims)):
            scores[i].append(round(p[f"c{i}"], 4))
    return scores, cost


def calibrate(env: str, incidents: list[str], passes: int) -> dict:
    graph = get_graph()
    report, all_t, all_f, cost = {"env": env, "passes": passes, "incidents": {}}, [], [], 0.0
    for inc in incidents:
        data = narrator.narrator_input(causal.open_run(graph, env, inc))
        trues = true_claims(data)
        falses = false_claims(data, trues)
        scores, c = score(data, trues + falses, passes)
        cost += c
        t, f = scores[: len(trues)], scores[len(trues) :]
        all_t += t
        all_f += f
        report["incidents"][inc] = {
            "true": [{"text": x["text"], "scores": s} for x, s in zip(trues, t, strict=True)],
            "false": [{"text": x["text"], "scores": s} for x, s in zip(falses, f, strict=True)],
        }
    report |= pick_cutoff(all_t, all_f) | {"n_true": len(all_t), "n_false": len(all_f), "cost_usd": round(cost, 6)}
    return report


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Calibrate the Jev claim cutoff from labelled claims")
    p.add_argument("--env", required=True)
    p.add_argument("--incident", action="append", help="repeatable; default: every diagnosed incident in the env")
    p.add_argument("--passes", type=int, default=2)
    p.add_argument("--out", default="data/calibration/jev.json")
    a = p.parse_args(argv)
    incs = a.incident or sorted(
        i["id"]
        for i in get_graph()
        .env(a.env)
        .ro("incidents_page", status="diagnosed", cause=None, c_ts=None, c_id=None, limit=1000)  # fmt: skip
    )
    rep = calibrate(a.env, incs, a.passes)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(rep, indent=1), encoding="utf-8")
    print(f"{rep['n_true']} true / {rep['n_false']} false claims, {a.passes} passes, ${rep['cost_usd']}")
    print(f"min true {rep['min_true']}  max false {rep['max_false']}  → recommended min_support {rep['recommended']}")
    for row in rep["table"]:
        print(f"  cutoff {row['cutoff']:.2f}  false accepts {row['false_accepts']:3}  true kept {row['true_kept']:.0%}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
