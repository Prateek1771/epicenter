import assert from "node:assert/strict";
import { it } from "node:test";

import { keepPlaced, layout } from "./layout.ts";

it("existing nodes keep their position, new ones are placed", () => {
  const prev = { a: { x: 10, y: 20 } };
  const out = keepPlaced(prev, { a: { x: 999, y: 999 }, b: { x: 300, y: 40 } });
  assert.deepEqual(out, { a: { x: 10, y: 20 }, b: { x: 300, y: 40 } });
});

it("elk lays out callers left of callees, deterministically", async () => {
  const g = {
    nodes: [{ id: "front/GET", group: "front" }, { id: "pay/Charge", group: "pay" }, { id: "cart/Get", group: "cart" }],
    edges: [{ src: "front/GET", dst: "pay/Charge" }, { src: "front/GET", dst: "cart/Get" }],
  };
  const a = await layout(g);
  assert.ok(a["front/GET"].x < a["pay/Charge"].x && a["front/GET"].x < a["cart/Get"].x);
  assert.deepEqual(await layout(g), a);
  const grown = await layout({ ...g, nodes: [...g.nodes, { id: "db/Q", group: "db" }],
                               edges: [...g.edges, { src: "pay/Charge", dst: "db/Q" }] }, a); // prettier-ignore
  for (const id of Object.keys(a)) assert.deepEqual(grown[id], a[id]); // nothing that was drawn moves
  assert.ok(grown["db/Q"].x > grown["pay/Charge"].x);
});
