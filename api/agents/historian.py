"""historian (no LLM): incident signature (ADR 0008) → Q5 similar resolved incidents → SIMILAR_TO, LLD §5.3.

Runs after the verdict is published, so memory never slows the diagnosis. Re-ranks Q5's vector hits by graph overlap
(same root-cause operation, a shared change type) with weights from weights.json `memory`.
"""

from api.events import publish
from api.search import causal


def remember(r: causal.Run) -> dict:
    sig = causal.incident_signature(r)
    if not any(sig):
        return {}  # nothing to describe (no anomalies at all): no signature, no recall
    r.env.rw("incident_set_signature", inc=r.incident, sig=sig)
    cfg = r.w["memory"]
    roots = r.env.ro("signature_roots", inc=r.incident)
    my_op = roots[0]["op"] if roots else None
    my_changes = {x["type"] for x in r.env.ro("root_change_types", inc=r.incident)}
    ranked = []
    for past in r.env.ro("Q5", sig=sig, inc=r.incident):
        overlap_change = bool(my_changes & {x["type"] for x in r.env.ro("root_change_types", inc=past["incident"])})
        score = (
            (1 - past["score"]) + cfg["overlap_op"] * (past["cause"] == my_op) + cfg["overlap_change"] * overlap_change
        )
        ranked.append({"incident": past["incident"], "score": round(score, 6), "cause": past["cause"],
                       "fixes": sorted(past["fixes"])})  # fmt: skip
    ranked = sorted(ranked, key=lambda x: (-x["score"], x["incident"]))[: cfg["top_similar"]]
    if ranked:
        r.env.rw("similar_to", inc=r.incident, run=r.run,
                 rows=[{"incident": x["incident"], "score": x["score"]} for x in ranked])  # fmt: skip
    counts = {x["name"]: x["n"] for x in r.env.ro("fix_counts", names=sorted({f for x in ranked for f in x["fixes"]}))}
    for x in ranked:
        x["worked"] = {f: counts.get(f, 0) for f in x["fixes"]}
    publish(r.env.key, r.incident, "memory.similar", {"similar": ranked})
    return {}
