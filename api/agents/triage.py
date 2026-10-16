"""triage (no LLM): hypotheses upstream of the symptom (Q1 + the symptom itself), LLD §5.3."""

from api.events import publish
from api.models import local_id
from api.search import causal


def triage(state: dict, r: causal.Run) -> dict:
    hyps = causal.triage(r)
    publish(r.env.key, r.incident, "incident.status", {"status": "diagnosing", "run": r.run})
    for h in hyps:
        publish(
            r.env.key,
            r.incident,
            "hypothesis.created",
            {"id": local_id(h["id"]), "target": h["op"], "hops": h["hops"], "onset": h["onset"], "round": 1},
        )
    return {"hypothesis_ids": [h["id"] for h in hyps]}
