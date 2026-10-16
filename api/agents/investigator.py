"""investigator (no LLM in this phase): Q3, Q2 and the Fault Simulator for one hypothesis, LLD §5.3.

Runs once per hypothesis via LangGraph `Send`, in parallel. Writes only under its own hypothesis; status comes from
the deterministic rules, never from a model. Phase 7 may add optional context calls (recent_changes, who_knows).
"""

from api.events import publish
from api.models import local_id
from api.search import causal


def investigate(r: causal.Run, hypothesis_id: str) -> dict:
    out = causal.investigate(r, hypothesis_id)
    hid = local_id(hypothesis_id)
    for e in out["evidence"]:
        publish(
            r.incident,
            "evidence.added",
            {
                "id": local_id(e["id"]),
                "hypothesis_id": hid,
                "kind": e["kind"],
                "verdict": "supports" if e["rel"] == "support" else "refutes",
                "path": e["path"],
            },
        )
    if out["footprint"] is not None:
        fp = out["footprint"]
        publish(
            r.incident,
            "footprint",
            {"hypothesis_id": hid}
            | {k: fp[k] for k in ("coverage", "precision", "order", "matched", "missed", "unexplained")},
        )
    publish(r.incident, "hypothesis.status", {"id": hid, "status": out["status"]})
    return {}
