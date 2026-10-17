import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { activation, buildGraph, hops } from "./shockwave.ts";

describe("landing shockwave", () => {
  it("is deterministic: the same seed gives the same graph", () => {
    assert.deepEqual(buildGraph(7), buildGraph(7));
    assert.notDeepEqual(buildGraph(7).edges, buildGraph(8).edges);
  });

  it("reaches every node from the epicenter", () => {
    const g = buildGraph(7);
    assert.ok(hops(g).every(Number.isFinite));
    assert.equal(hops(g)[g.epicenter], 0);
  });

  it("lights nodes in hop order, everything by the end of the wave, then fades", () => {
    const g = buildGraph(7);
    const d = hops(g);
    for (const t of [0.1, 0.3, 0.5, 0.7]) {
      const a = activation(g, d, t);
      for (let i = 0; i < d.length; i++) for (let j = 0; j < d.length; j++) if (d[i] < d[j]) assert.ok(a[i] >= a[j]);
    }
    assert.ok(activation(g, d, 0.85).every((x) => x > 0.99));
    assert.ok(activation(g, d, 0.999).every((x) => x < 0.02));
  });
});
