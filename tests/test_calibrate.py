"""Jev cutoff calibration (pure parts): labelled claims and the cutoff picker."""

from api.agents.calibrate import false_claims, perturb, pick_cutoff, true_claims

DATA = {
    "status": "diagnosed",
    "symptom": "frontend/GET /checkout",
    "root_cause": "payment/Charge",
    "second_cause": None,
    "confidence": 0.99,
    "summary": None,
    "hypotheses": [
        {"id": "h-2", "op": "payment/Charge", "status": "confirmed", "score": 0.9, "coverage": 0.75},
        {"id": "h-3", "op": "checkout/PlaceOrder", "status": "refuted", "score": 0.1, "coverage": 0.5},
    ],
    "evidence": [
        {"id": "E2.1", "hypothesis": "h-2", "op": "payment/Charge", "kind": "propagation", "verdict": "supports",
         "summary": "payment/Charge went bad 20 s before frontend/GET /checkout",
         "path": ["frontend/GET /checkout", "checkout/PlaceOrder", "payment/Charge"]},
        {"id": "E2.3", "hypothesis": "h-2", "op": "payment/Charge", "kind": "footprint", "verdict": "supports",
         "summary": "explains 3 of 4 symptoms (precision 1.00, order 1.00)", "path": ["payment/Charge"]},
        {"id": "E3.2", "hypothesis": "h-3", "op": "checkout/PlaceOrder", "kind": "victim", "verdict": "refutes",
         "summary": "checkout/PlaceOrder is a victim: time in its callees grew ×2.5",
         "path": ["checkout/PlaceOrder", "cart/GetCart"]},
    ],
}  # fmt: skip


def test_true_claims_restate_evidence_with_their_subject():
    t = true_claims(DATA)
    texts = [c["text"] for c in t]
    assert texts[0].startswith("payment/Charge is the root cause")  # the template headline
    assert "payment/Charge: explains 3 of 4 symptoms (precision 1.00, order 1.00)" in texts
    assert len(texts) == len(set(texts)) and all(c["cites"] for c in t)


def test_perturbations_are_false_and_keep_the_cites():
    claim = {"text": "payment/Charge went bad 20 s before frontend/GET /checkout", "cites": ["E2.1"]}
    variants = [v["text"] for v in perturb(claim, DATA)]
    # another operation, one with no evidence of its own: PlaceOrder has some, so the claim might be true of it
    assert "cart/GetCart went bad 20 s before frontend/GET /checkout" in variants
    assert not any(v.startswith("checkout/PlaceOrder went bad") for v in variants)
    assert "payment/Charge went bad 27 s before frontend/GET /checkout" in variants  # another number
    assert "payment/Charge went bad 20 s after frontend/GET /checkout" in variants  # reversed order
    assert all(v["cites"] == ["E2.1"] for v in perturb(claim, DATA))
    f = [c["text"] for c in false_claims(DATA, true_claims(DATA))]
    assert "checkout/PlaceOrder is the root cause." in f  # a refuted hypothesis
    assert any(t.startswith("A deploy of payment") for t in f)  # a change that isn't in the evidence
    assert not set(f) & {c["text"] for c in true_claims(DATA)}


def test_picker_takes_the_lowest_safe_cutoff_plus_margin():
    trues = [[0.9, 0.85], [0.45, 0.5], [0.62, 0.58]]
    falses = [[0.02, 0.03], [0.19, 0.22], [0.05, 0.04]]
    rep = pick_cutoff(trues, falses)
    assert rep["recommended"] == 0.3 and rep["max_false"] == 0.22 and rep["min_true"] == 0.45
    row = {r["cutoff"]: r for r in rep["table"]}
    assert row[0.2]["false_accepts"] == 1 and row[0.25]["false_accepts"] == 0  # 0.22 in one pass counts
    assert row[0.7]["true_kept"] == round(2 / 6, 3) and row[0.3]["true_kept"] == 1.0
    assert pick_cutoff([[0.9]], [[0.96]])["recommended"] is None  # nothing safe: don't recommend
