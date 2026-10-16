"""skeptic: challenges the provisional winner, LLD §5.3. Leads with "what doesn't the winner explain?".

The decision is a deterministic tool (`causal.skeptic`). Phase 7 adds the LLM that picks *which* check to run first;
every check it can pick is deterministic, so the verdict is the same with or without a model (N7).
"""

import json

from api.events import publish
from api.models import local_id
from api.search import causal


def challenge(r: causal.Run, winner_id: str) -> bool:
    [h] = r.env.ro("hypothesis", id=winner_id)
    winner = {"id": h["id"], "op": h["op"], "unexplained": json.loads(h["facts"] or "{}").get("unexplained", [])}
    refuted = causal.skeptic(r, winner)
    if refuted:
        publish(
            r.env.key,
            r.incident,
            "evidence.added",
            {
                "id": f"E{winner_id.rsplit('h-', 1)[1]}.s",  # causal.skeptic writes <run>:E<n>.s
                "hypothesis_id": local_id(winner_id),
                "kind": "footprint",
                "verdict": "refutes",
                "path": [h["op"], r.symptom],
            },
        )
        publish(r.env.key, r.incident, "hypothesis.status", {"id": local_id(winner_id), "status": "refuted"})
    return refuted
