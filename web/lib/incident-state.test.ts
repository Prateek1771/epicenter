import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { apply, edgeKey, evidenceIndex, hydrate, merge, type StreamEvent, winningPath } from "./incident-state.ts";

const snapshot = {
  incident: "inc-1",
  run: 1,
  status: "diagnosing" as const,
  symptom: "frontend/GET /checkout",
  root_cause: null,
  second_cause: null,
  last_seq: 10,
  hypotheses: [],
  nodes: [{ id: "frontend/GET /checkout", service: "frontend", service_kind: "app", anomaly: null }],
  edges: [],
  changes: [],
};

const run: StreamEvent[] = [
  { seq: 11, event: "hypothesis.created", data: { id: "h-2", target: "payment/Charge", hops: 2, onset: 100, round: 1 } },
  {
    seq: 12,
    event: "evidence.added",
    data: {
      id: "E2.1",
      hypothesis_id: "h-2",
      kind: "propagation",
      verdict: "supports",
      path: ["frontend/GET /checkout", "checkout/PlaceOrder", "payment/Charge"],
    },
  },
  {
    seq: 13,
    event: "footprint",
    data: { hypothesis_id: "h-2", coverage: 0.75, precision: 1, order: 1, matched: ["a"], missed: [], unexplained: ["b"] },
  },
  { seq: 14, event: "hypothesis.status", data: { id: "h-2", status: "confirmed", score: 0.9 } },
  { seq: 15, event: "verdict", data: { status: "diagnosed", root_cause: "payment/Charge", confidence: 0.99 } },
];

const play = (events: StreamEvent[]) => events.reduce(apply, hydrate(snapshot));

describe("incident state reducer", () => {
  it("builds the canvas from the stream", () => {
    const v = play(run);
    assert.deepEqual(Object.keys(v.nodes).sort(), ["checkout/PlaceOrder", "frontend/GET /checkout", "payment/Charge"]);
    assert.deepEqual(Object.keys(v.edges).sort(), [
      edgeKey("checkout/PlaceOrder", "payment/Charge"),
      edgeKey("frontend/GET /checkout", "checkout/PlaceOrder"),
    ]);
    assert.equal(v.hyps["h-2"].status, "confirmed");
    assert.equal(v.rootCause, "payment/Charge");
    assert.equal(v.footprints["h-2"].coverage, 0.75);
    assert.deepEqual(v.timeline.map((t) => t.seq), [11, 12, 13, 14, 15]);
    assert.equal(winningPath(v).ops.has("checkout/PlaceOrder"), true);
    assert.equal(evidenceIndex(v)["E2.1"].hypothesis, "h-2");
  });

  it("is idempotent: a replay or duplicate changes nothing", () => {
    const once = play(run);
    assert.deepEqual(play([...run, ...run]), once);
    assert.equal(run.reduce(apply, once), once); // same object: nothing applied
  });

  it("ignores events the snapshot already contains", () => {
    const old = { seq: 9, event: "hypothesis.created", data: { id: "h-9", target: "x/y", hops: 1, round: 1 } };
    assert.equal(apply(hydrate(snapshot), old).hyps["h-9"], undefined);
  });

  it("only propagation paths become call edges", () => {
    const v = play([
      run[0],
      { seq: 12, event: "evidence.added", data: { id: "E2.s", hypothesis_id: "h-2", kind: "footprint", verdict: "refutes",
                                                   path: ["payment/Charge", "frontend/GET /checkout"] } }, // prettier-ignore
    ]);
    assert.deepEqual(Object.keys(v.edges), []);
  });

  it("a new run starts the run state over but keeps the topology", () => {
    const v = apply(play(run), { seq: 16, event: "incident.status", data: { status: "diagnosing", run: 2 } });
    assert.equal(v.run, 2);
    assert.deepEqual(v.hyps, {});
    assert.equal(v.rootCause, null);
    assert.equal(Object.keys(v.nodes).length, 3);
  });

  it("merging a fresh snapshot keeps stream-only state of the same run", () => {
    const v = play(run);
    const m = merge(v, { ...snapshot, status: "diagnosed", root_cause: "payment/Charge", last_seq: 12 });
    assert.equal(m.lastSeq, 15);
    assert.notEqual(m.footprints["h-2"], undefined);
    assert.equal(m.timeline.length, 5);
  });
});
