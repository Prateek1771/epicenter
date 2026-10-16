import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { hydrate } from "./incident-state.ts";
import { ago, explainers, lanes, notYet, ruledOut, timeAxis, tMinus } from "./investigation.ts";

const v = hydrate({
  incident: "inc-1",
  run: 2,
  status: "diagnosed",
  symptom: "frontend/GET /checkout",
  root_cause: "payment/Charge",
  second_cause: null,
  last_seq: 9,
  alert_ts: 130,
  changes: [{ id: "ch-1", service: "payment", type: "flag", ts: 60, summary: "flag paymentFailure on" }],
  hypotheses: [
    { id: "h-1", op: "payment/Charge", status: "confirmed", score: 0.9, hops: 2, round: 1, evidence: [] },
    { id: "h-2", op: "checkout/PlaceOrder", status: "refuted", score: 0.4, hops: 1, round: 1,
      evidence: [{ id: "E2", kind: "victim", verdict: "refutes", summary: "checkout is a victim of its callee", path: ["checkout/PlaceOrder", "payment/Charge"] }] },
    { id: "h-3", op: "cart/Get", status: "pruned", score: 0.2, hops: 1, round: 1, evidence: [] },
  ], // prettier-ignore
  nodes: [
    { id: "frontend/GET /checkout", service: "frontend", service_kind: "app", anomaly: { kind: "latency", onset: 120, score: 0.8 } },
    { id: "checkout/PlaceOrder", service: "checkout", service_kind: "app", anomaly: { kind: "errors", onset: 110, score: 0.9 } },
    { id: "payment/Charge", service: "payment", service_kind: "app", anomaly: { kind: "errors", onset: 100, score: 0.99 } },
    { id: "cart/Get", service: "cart", service_kind: "app", anomaly: null },
  ],
  edges: [],
});

describe("investigation views", () => {
  it("ruled out: refuted and pruned suspects with the engine's own reason, best score first", () => {
    const r = ruledOut(v);
    assert.deepEqual(r.map((x) => [x.hyp.id, x.reason]), [["h-2", "checkout is a victim of its callee"], ["h-3", "lost on score to the root cause"]]);
    assert.deepEqual(r[0].path, ["checkout/PlaceOrder", "payment/Charge"]);
  });

  it("lanes: anomalous ops by onset, with their role", () => {
    assert.deepEqual(lanes(v).map((l) => [l.op, l.onset, l.role]), [
      ["payment/Charge", 100, "root"], ["checkout/PlaceOrder", 110, null], ["frontend/GET /checkout", 120, "symptom"],
    ]); // prettier-ignore
  });

  it("time axis spans changes, onsets and the alert, padded", () => {
    assert.deepEqual(timeAxis(v), { t0: 30, t1: 160 });
  });

  it("the slicer hides what hasn't started yet", () => {
    assert.deepEqual([...notYet(v, 105)].sort(), ["checkout/PlaceOrder", "frontend/GET /checkout"]);
    assert.equal(notYet(v, null).size, 0);
  });

  it("T-minus: change and root onset as seconds before the alert", () => {
    const t = tMinus(v, v.changes[0])!;
    assert.deepEqual([t.change?.offset, t.onset?.offset, t.alert], [70, 30, 130]);
    assert.equal(ago(70), "1m 10s");
    assert.equal(ago(-20), "+20s");
  });

  it("explainers: which suspects' footprints match a symptom, matching ones first", () => {
    const fps = { "h-1": { matched: ["frontend/GET /checkout"] }, "h-2": { matched: [] } };
    assert.deepEqual(explainers(v, "frontend/GET /checkout", fps).map((e) => [e.hyp.id, e.explains]), [["h-1", true], ["h-2", false]]);
  });
});
