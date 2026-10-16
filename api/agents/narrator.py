"""narrator (GPT-4o) + jev_gate (Jev Noul): a cited explanation of the verdict, unsupported claims dropped, LLD §5.3.

Runs after the verdict is published and writes only `Explanation` (rule 4: never read by the scorer).
- The verdict and evidence go to the model as one delimited JSON *data* block (HLD §9 prompt-injection guard).
- Output is a JSON-schema'd `{what, where, why}` of `{text, cites}`; a claim citing an id that isn't in the input, or
  citing nothing, is dropped and counted.
- No key / model down / invalid output → a deterministic template built from the evidence (source `template`,
  "AI explanation unavailable" in the UI). The verdict is the same either way (N7).
- jev_gate asks Jev, per claim, "does the cited evidence support it?" and drops claims under `min_support`; Jev down →
  cited claims are kept and marked `unverified`.
"""

import json
from pathlib import Path

from pydantic import BaseModel, ValidationError

from api.ai import jev, openrouter
from api.events import publish
from api.models import local_id, scoped_id
from api.search import causal

PROMPT = (Path(__file__).parent / "prompts" / "narrator.md").read_text(encoding="utf-8")
SECTIONS = ("what", "where", "why")
MAX_HYPOTHESES = 4  # evidence of the top-ranked hypotheses goes in; keeps the prompt small and the cost fixed

_claim = {
    "type": "object",
    "properties": {"text": {"type": "string"}, "cites": {"type": "array", "items": {"type": "string"}}},
    "required": ["text", "cites"],
    "additionalProperties": False,
}
SCHEMA = {
    "type": "object",
    "properties": {s: {"type": "array", "items": _claim} for s in SECTIONS},
    "required": list(SECTIONS),
    "additionalProperties": False,
}


class Claim(BaseModel):
    text: str
    cites: list[str]


class Narration(BaseModel):
    what: list[Claim]
    where: list[Claim]
    why: list[Claim]


def explanation_id(r: causal.Run) -> str:
    return scoped_id(r.incident, f"r{r.run}:X")


def narrator_input(r: causal.Run) -> dict:
    """The verdict and the evidence behind the top hypotheses, with the local ids the API shows (E2.1, h-2)."""
    v = causal.read_verdict(r)
    ranked = v["ranking"][:MAX_HYPOTHESES]
    keep = {h["id"] for h in ranked} | {
        local_id(c["hypothesis"]) for c in r.env.ro("root_causes", inc=r.incident)
    }  # the committed causes, even if round 2 ranked them elsewhere
    evidence = []
    for hid in sorted(keep):
        sid = scoped_id(r.incident, f"r{r.run}:{hid}")
        [h] = r.env.ro("hypothesis", id=sid)
        for e in r.env.ro("hypothesis_evidence", id=sid):
            evidence.append(
                {
                    "id": local_id(e["id"]),
                    "hypothesis": hid,
                    "op": h["op"],  # what the evidence is about: "explains 1 of 15 symptoms" alone names nothing
                    "kind": e["kind"],
                    "verdict": "supports" if e["rel"] == "SUPPORTED_BY" else "refutes",
                    "summary": e["summary"],
                    "path": e["path"] or [],
                }
            )
    return {
        "incident": r.incident,
        "symptom": r.symptom,
        "status": v["status"],
        "root_cause": v["root_cause"],
        "second_cause": v["second_cause"],
        # 2 decimals: the model quotes numbers verbatim, and "0.576323" reads as noise
        "confidence": None if v["confidence"] is None else round(v["confidence"], 2),
        "explains": v["explains"],
        "summary": v["summary"],
        # scores stay unrounded: at 2 decimals the model quotes the winner's score (0.62) as the confidence (0.58)
        "hypotheses": [{k: h[k] for k in ("id", "op", "status", "score", "coverage")} for h in ranked],
        "evidence": evidence,
    }


def check_claims(raw: dict, known: set[str]) -> tuple[list[dict], int]:
    """Keep claims whose cites are all known evidence ids (and at least one); count the rest as dropped."""
    out, dropped = [], 0
    for section in SECTIONS:
        for c in raw[section]:
            if c.text.strip() and c.cites and set(c.cites) <= known:
                out.append({"section": section, "text": c.text.strip(), "cites": c.cites})
            else:
                dropped += 1
    return out, dropped


def template(data: dict) -> list[dict]:
    """Deterministic explanation from the evidence alone, used whenever the model can't be."""
    ev = data["evidence"]
    claims = []
    by_hyp = {}
    for e in ev:
        by_hyp.setdefault(e["hypothesis"], []).append(e)
    if data["status"] == "no_root_cause":
        best = [e for h in data["hypotheses"][:2] for e in by_hyp.get(h["id"], []) if e["kind"] == "footprint"]
        if best:
            claims.append({"section": "what", "text": data["summary"] or "Nothing in the graph explains this alert.",
                           "cites": [e["id"] for e in best]})  # fmt: skip
        return claims
    root = next((h for h in data["hypotheses"] if h["op"] == data["root_cause"]), None)
    mine = [e for e in by_hyp.get(root["id"], [])] if root else []
    support = [e for e in mine if e["verdict"] == "supports"]
    prop = next((e for e in support if e["kind"] == "propagation"), None)
    if support:
        conf = f" (confidence {data['confidence']:.0%})" if data["confidence"] is not None else ""
        claims.append({"section": "what", "text": f"{data['root_cause']} is the root cause{conf}.",
                       "cites": [(prop or support[0])["id"]]})  # fmt: skip
    if prop and len(prop["path"]) > 1:
        route = " → ".join(reversed(prop["path"]))
        text = f"The problem started at {data['root_cause']} and reached {data['symptom']} along {route}."
        claims.append({"section": "where", "text": text, "cites": [prop["id"]]})
    for e in support:
        if e["kind"] in ("change", "footprint"):
            claims.append({"section": "why", "text": e["summary"], "cites": [e["id"]]})
    if data["second_cause"]:
        second = next((h for h in data["hypotheses"] if h["op"] == data["second_cause"]), None)
        cites = [e["id"] for e in by_hyp.get(second["id"], []) if e["verdict"] == "supports"] if second else []
        if cites:
            claims.append({"section": "what", "text": f"A second, independent fault: {data['second_cause']}.",
                           "cites": cites[:1]})  # fmt: skip
    return claims


def _save(r: causal.Run, claims: list[dict], dropped: int, verified: bool, source: str, calls: list[dict]) -> str:
    xid = explanation_id(r)
    r.env.rw(
        "explanation_save",
        inc=r.incident,
        id=xid,
        run=r.run,
        claims=json.dumps(claims, sort_keys=True),
        dropped=dropped,
        verified=verified,
        source=source,
        ai_calls=json.dumps(calls, sort_keys=True),
    )
    return xid


def narrate(r: causal.Run) -> dict:
    data = narrator_input(r)
    known = {e["id"] for e in data["evidence"]}
    user = f"<verdict_json>\n{json.dumps(data, sort_keys=True)}\n</verdict_json>"
    try:
        res = openrouter.chat([{"role": "system", "content": PROMPT}, {"role": "user", "content": user}], schema=SCHEMA)
        n = Narration.model_validate_json(res.content or "")
        claims, dropped = check_claims({s: getattr(n, s) for s in SECTIONS}, known)
        source, calls = "llm", [res.call | {"agent": "narrator"}]
    except (openrouter.LLMUnavailable, ValidationError):
        claims, dropped, source, calls = [], 0, "template", []
    if not claims:  # nothing usable from the model: the template still explains the verdict
        claims, source = template(data), "template"
    return {"explanation_id": _save(r, claims, dropped, False, source, calls)}


def jev_gate(r: causal.Run, xid: str, min_support: float) -> dict:
    [x] = r.env.ro("explanation", inc=r.incident, id=xid)
    claims, dropped, calls = json.loads(x["claims"]), x["dropped"], json.loads(x["ai_calls"] or "[]")
    verified = False
    source = x["source"]
    if source == "llm" and claims:
        data = narrator_input(r)
        try:
            p, call = jev.noul(gate_state(data), gate_questions(claims, evidence_texts(data)))
            calls.append(call | {"agent": "jev_gate"})
            kept = []
            for i, c in enumerate(claims):
                c["support_p"] = round(p[f"c{i}"], 4)
                if c["support_p"] >= min_support:
                    kept.append(c | {"status": "verified"})
                else:
                    dropped += 1
            claims, verified = kept, True
            if not claims:  # every model claim failed the gate: explain from the evidence instead
                claims, source, verified = [c | {"status": "template"} for c in template(data)], "template", False
        except jev.JevUnavailable:
            claims = [c | {"status": "unverified"} for c in claims]
        if source == "llm":
            claims = fill_gaps(claims, data)
    else:
        claims = [c | {"status": source} for c in claims]  # template claims quote the evidence directly
    _save(r, claims, dropped, verified, source, calls)
    publish(r.env.key, r.incident, "explanation",
            {"claims": claims, "dropped": dropped, "verified": verified, "source": source})  # fmt: skip
    return {}


def fill_gaps(claims: list[dict], data: dict) -> list[dict]:
    """The facts an on-call engineer must always see don't depend on the model: if no kept claim states the headline
    (root cause, or "nothing explains it") or cites the root cause's change, the template's claim for it is added,
    marked `status: template` so the UI shows where each sentence came from."""
    tpl = template(data)
    out = list(claims)
    headline = data["root_cause"] or ""
    has_headline = any(c["section"] == "what" and (headline and headline in c["text"]) for c in claims)
    if data["status"] == "no_root_cause":
        has_headline = any(c["section"] == "what" and "explain" in c["text"].lower() for c in claims)
    if not has_headline and tpl and tpl[0]["section"] == "what":
        out.insert(0, tpl[0] | {"status": "template"})
    root_hyps = {h["id"] for h in data["hypotheses"] if h["op"] == data["root_cause"]}
    change_ids = {e["id"] for e in data["evidence"]
                  if e["kind"] == "change" and e["verdict"] == "supports" and e["hypothesis"] in root_hyps}  # fmt: skip
    cited = {i for c in out if c["section"] == "why" for i in c["cites"]}  # a headline citing it doesn't explain it
    for c in tpl:
        if set(c["cites"]) & (change_ids - cited):
            out.append(c | {"status": "template"})
    return out


def gate_state(data: dict) -> dict:
    """What Jev may treat as true besides the cited evidence: the engine's own verdict (not the model's words)."""
    if data["status"] == "no_root_cause":
        verdict = f"status no_root_cause: {data['summary']}"
    else:
        # both forms: the model may quote the raw number from the input or a percentage
        conf = (
            f" (confidence {data['confidence']} = {data['confidence']:.0%})" if data["confidence"] is not None else ""
        )
        second = f", second cause {data['second_cause']}" if data["second_cause"] else ""
        verdict = f"root cause {data['root_cause']}{conf}{second}, status {data['status']}"
    return {"task": "Fact-check claims about an incident.",
            "verdict": f"Engine verdict: {verdict}; alerting operation {data['symptom']}."}  # fmt: skip


def evidence_texts(data: dict) -> dict[str, str]:
    """Evidence as Jev reads it: kind, verdict, summary and the operations on its path (claims often name them)."""
    return {
        e["id"]: f"[{e['kind']} evidence about {e['op']}, {e['verdict']} it as the cause] {e['summary']}"
        + (f" (path: {' -> '.join(e['path'])})" if len(e["path"]) > 1 else "")
        for e in data["evidence"]
    }


def gate_questions(claims: list[dict], summaries: dict[str, str]) -> dict:
    """One Noul per claim, each carrying its own claim and cited evidence (one shared question text can't tell Jev
    which claim it is about: every claim then scores the same)."""
    return {
        f"c{i}": {
            "instructions": f"Claim: {c['text']}\nCited evidence:\n"
            + "\n".join(f"- {k}: {summaries.get(k, '')}" for k in c["cites"])
            + "\nIs every statement in the claim supported by the engine verdict and the cited evidence?",
            "criteria": {
                "true": "Every statement in the claim is stated or directly implied by the engine verdict or the "
                "cited evidence.",
                "false": "The claim says something the verdict and the cited evidence do not state, or contradicts "
                "them.",
            },
        }
        for i, c in enumerate(claims)
    }
