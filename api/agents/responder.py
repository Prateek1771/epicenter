"""responder: proposed actions for the verdict, LLD §5.3. Writes only `Action {status:'proposed'}` (rule 4).

Candidates: the steps of the runbooks FOR the root-cause service whose kind matches the root cause's anomaly kinds,
plus the fixes of similar past incidents (historian). Order:
  1. procedural memory: how often an action with that name resolved an incident here (`RESOLVED_BY`), most first;
  2. the rest in runbook order, except
  3. the ones Jev judges irrelevant to the cause the evidence shows (Noul per action < `actions.min_relevance`),
     which go last (`chosen_by: demoted`). Jev rules actions out rather than picking a winner: one Choice over
     near-equal options flipped between runs, independent per-action questions don't. Jev down → 1 and 2 only.
`no_root_cause` → one action: check the alert threshold.
"""

from api.ai import jev
from api.events import publish
from api.models import local_id, scoped_id
from api.search import causal

NO_ROOT_CAUSE_ACTION = "Check the alert threshold against the baseline"
MAX_ACTIONS = 8


def candidates(r: causal.Run) -> tuple[list[dict], dict | None]:
    [inc] = r.env.ro("incident", inc=r.incident)
    if inc["status"] == "no_root_cause":
        return [{"name": NO_ROOT_CAUSE_ACTION, "runbook": None, "step": None}], None
    roots = [x for x in r.env.ro("signature_roots", inc=r.incident) if x["rank"] == 1]
    if not roots:
        return [], None
    root = roots[0]
    out, seen = [], set()
    kinds = sorted(set(root["kinds"]))
    for rb in r.env.ro("runbook_steps", svc=root["op"].split("/", 1)[0], kinds=kinds):
        for i, step in enumerate(rb["steps"]):
            if step not in seen:
                seen.add(step)
                out.append({"name": step, "runbook": rb["id"], "step": i})
    for past in r.env.ro("similar_of_run", inc=r.incident):
        for fix in past["fixes"]:
            if fix not in seen:
                seen.add(fix)
                out.append({"name": fix, "runbook": None, "step": None})
    return out[:MAX_ACTIONS], root | {"kinds": kinds}


def relevance(r: causal.Run, root: dict, cands: list[dict]) -> dict[str, float]:
    """Jev Noul per candidate: does it address the cause the evidence shows? One request, independent questions."""
    support = [e["summary"] for e in r.env.ro("hypothesis_evidence", id=root["hypothesis"])
               if e["rel"] == "SUPPORTED_BY"]  # fmt: skip
    state = {
        "root_cause": root["op"],
        "anomaly_kinds": root["kinds"],
        "alerting_operation": r.symptom,
        "evidence": support,
    }
    questions = {
        f"a{i}": {
            "instructions": f"Action: {c['name']}\nDoes this action address the cause shown in the evidence?",
            "criteria": {
                "true": "Doing this action deals with, or directly checks, what the evidence shows went wrong.",
                "false": "The action is unrelated to what the evidence shows, or targets a different cause.",
            },
        }
        for i, c in enumerate(cands)
    }
    p, _ = jev.noul(state, questions)
    return {c["name"]: round(p[f"a{i}"], 4) for i, c in enumerate(cands)}


def order(r: causal.Run, cands: list[dict], root: dict | None) -> list[dict]:
    history = {x["name"]: x["n"] for x in r.env.ro("fix_counts", names=[c["name"] for c in cands])}
    known = sorted((c for c in cands if history.get(c["name"])), key=lambda c: -history[c["name"]])  # stable
    rest = [c for c in cands if not history.get(c["name"])]
    out = [c | {"chosen_by": "history", "p": None, "worked": history[c["name"]]} for c in known]
    p: dict[str, float] = {}
    if rest and root:
        try:
            p = relevance(r, root, rest)
        except jev.JevUnavailable:
            pass
    cut = r.w["actions"]["min_relevance"]
    keep = [c for c in rest if p.get(c["name"], 1.0) >= cut]  # unscored (Jev down) keeps runbook order
    out += [c | {"chosen_by": "runbook", "p": p.get(c["name"]), "worked": 0} for c in keep]
    out += [c | {"chosen_by": "demoted", "p": p[c["name"]], "worked": 0} for c in rest if c not in keep]
    return out


def respond(r: causal.Run) -> dict:
    cands, root = candidates(r)
    if not cands:
        return {"action_ids": []}
    ranked = order(r, cands, root)
    rows = [
        {
            "id": scoped_id(r.incident, f"r{r.run}:a-{n}"),
            "name": c["name"],
            "rank": n,
            "chosen_by": c["chosen_by"],
            "p": c["p"],
            "runbook": c["runbook"],
            "step": c["step"],
        }
        for n, c in enumerate(ranked, 1)
    ]
    r.env.rw("actions_save", inc=r.incident, run=r.run, rows=rows)
    for row, c in zip(rows, ranked, strict=True):
        publish(r.env.key, r.incident, "action", {"id": local_id(row["id"]), "name": row["name"], "rank": row["rank"],
                "chosen_by": row["chosen_by"], "worked": c["worked"], "delivery": None})  # fmt: skip
    return {"action_ids": [row["id"] for row in rows]}
