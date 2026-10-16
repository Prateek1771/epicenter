import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { filterRows, fromBlastRadius, fromView, relSeconds, type Row, sortRows, toCsv } from "./graph-data.ts";
import { hydrate } from "./incident-state.ts";

const view = hydrate({
  incident: "inc-1",
  run: 2,
  status: "diagnosed",
  symptom: "frontend/GET /checkout",
  root_cause: "payment/Charge",
  second_cause: null,
  last_seq: 9,
  alert_ts: 130,
  changes: [{ id: "ch-1", service: "payment", type: "flag", ts: 60, summary: "flag on" }],
  hypotheses: [{ id: "h-1", op: "payment/Charge", status: "confirmed", score: 0.91234, hops: 2, round: 1, evidence: [] }],
  nodes: [
    { id: "frontend/GET /checkout", service: "frontend", service_kind: "app", anomaly: { kind: "latency", onset: 120, score: 0.8 } },
    { id: "payment/Charge", service: "payment", service_kind: "app", anomaly: { kind: "errors", onset: 100, score: 0.99 } },
  ],
  edges: [{ src: "frontend/GET /checkout", dst: "payment/Charge", rps: 3.5, err_rate: 0.4, p95_ms: null }],
});

describe("graph data tables", () => {
  it("lists every canvas node with its anomaly, onset vs the alert, and suspect", () => {
    const d = fromView(view);
    const pay = d.nodes.rows.find((r) => r.id === "payment/Charge")!;
    assert.deepEqual([pay.role, pay.anomaly, pay.onset_s, pay.suspect, pay.status, pay.score], ["root cause", "errors", -30, "h-1", "confirmed", 0.912]);
    assert.equal(d.nodes.rows.find((r) => r.id === "frontend/GET /checkout")!.role, "alert");
    assert.deepEqual(d.edges.rows.map((r) => [r.src, r.dst, r.err_rate]), [["frontend/GET /checkout", "payment/Charge", 0.4]]);
    assert.equal((d.raw as { changes: unknown[] }).changes.length, 1);
  });

  it("relSeconds is null without a base", () => {
    assert.equal(relSeconds(100, null), null);
    assert.equal(relSeconds(100, 130), -30);
  });

  it("blast radius rows include the failing service's own ops at 0 hops", () => {
    const d = fromBlastRadius({ service: "redis", sources: ["redis/GET"], counts: {}, past_incidents: [],
      affected: [{ service: "cart", operation: "cart/Get", hops: 1, owner: "platform" }], edges: [] }); // prettier-ignore
    assert.deepEqual(d.nodes.rows.map((r) => [r.op, r.role, r.hops]), [["redis/GET", "fails", 0], ["cart/Get", "affected", 1]]);
  });

  it("filters on every word, any column", () => {
    const rows = fromView(view).nodes.rows;
    assert.deepEqual(filterRows(rows, "payment errors").map((r) => r.id), ["payment/Charge"]);
    assert.equal(filterRows(rows, "  ").length, 2);
  });

  it("sorts numbers numerically, empty cells last either way, ties by id", () => {
    const rows: Row[] = [{ id: "c", v: null }, { id: "b", v: 10 }, { id: "a", v: 9 }, { id: "d", v: 10 }];
    assert.deepEqual(sortRows(rows, "v", "asc").map((r) => r.id), ["a", "b", "d", "c"]);
    assert.deepEqual(sortRows(rows, "v", "desc").map((r) => r.id), ["b", "d", "a", "c"]);
  });

  it("escapes CSV cells per RFC 4180", () => {
    const csv = toCsv({ columns: [{ key: "a", label: "op" }, { key: "b", label: "note" }], rows: [{ id: "1", a: "GET /x,y", b: 'say "hi"' }, { id: "2", a: null, b: 3 }] });
    assert.equal(csv, 'op,note\r\n"GET /x,y","say ""hi"""\r\n,3\r\n');
  });
});
