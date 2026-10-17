/**
 * The landing hero's "shockwave over a call graph": a failure starting at one operation and spreading to its callers,
 * hop by hop. Pure and deterministic (a seeded LCG, no Math.random), so the hero looks the same on every load and in
 * tests.
 */

export interface SNode {
  id: number;
  x: number; // 0..1
  y: number; // 0..1
  layer: number;
}

export interface SGraph {
  nodes: SNode[];
  edges: [number, number][]; // [caller, callee]
  epicenter: number;
}

/** Numerical Recipes LCG: deterministic and good enough for layout jitter. */
function lcg(seed: number): () => number {
  let s = seed >>> 0;
  return () => {
    s = (Math.imul(s, 1664525) + 1013904223) >>> 0;
    return s / 2 ** 32;
  };
}

/** Layers left → right (entry points … datastores); each node calls 1–3 nodes in the next layer. */
export function buildGraph(seed = 7, layers = [5, 8, 9, 7, 4]): SGraph {
  const rnd = lcg(seed);
  const nodes: SNode[] = [];
  layers.forEach((n, li) => {
    for (let i = 0; i < n; i++) {
      nodes.push({
        id: nodes.length,
        layer: li,
        x: (li + 0.5) / layers.length + (rnd() - 0.5) * 0.06,
        y: (i + 0.5) / n + (rnd() - 0.5) * (0.6 / n),
      });
    }
  });
  const byLayer = layers.map((_, li) => nodes.filter((n) => n.layer === li));
  const edges: [number, number][] = [];
  for (let li = 0; li + 1 < layers.length; li++) {
    for (const a of byLayer[li]) {
      const next = byLayer[li + 1];
      const k = 1 + Math.floor(rnd() * 3);
      const near = [...next].sort((p, q) => Math.abs(p.y - a.y) - Math.abs(q.y - a.y) || p.id - q.id).slice(0, k);
      for (const b of near) edges.push([a.id, b.id]);
    }
    // every callee has at least one caller, so the wave can reach the whole graph from any datastore
    for (const b of byLayer[li + 1]) {
      if (!edges.some(([, d]) => d === b.id)) {
        const a = [...byLayer[li]].sort((p, q) => Math.abs(p.y - b.y) - Math.abs(q.y - b.y) || p.id - q.id)[0];
        edges.push([a.id, b.id]);
      }
    }
  }
  // the epicenter: a datastore-layer node, so the failure travels up the callers (right → left)
  const last = byLayer[layers.length - 1];
  return { nodes, edges, epicenter: last[Math.floor(last.length / 2)].id };
}

/** Hop distance from the epicenter over the undirected call graph (BFS); unreachable = Infinity. */
export function hops(g: SGraph): number[] {
  const adj: number[][] = g.nodes.map(() => []);
  for (const [a, b] of g.edges) {
    adj[a].push(b);
    adj[b].push(a);
  }
  const d = g.nodes.map(() => Infinity);
  d[g.epicenter] = 0;
  const q = [g.epicenter];
  for (let i = 0; i < q.length; i++) {
    for (const n of adj[q[i]]) {
      if (d[n] === Infinity) {
        d[n] = d[q[i]] + 1;
        q.push(n);
      }
    }
  }
  return d;
}

/**
 * How lit each node is at phase `t` ∈ [0, 1) of one cycle: the wave front reaches hop h at t = h / (maxHop + 1);
 * after it passes, a node stays lit (0..1 ramp), then the whole graph fades in the last 15% of the cycle.
 */
export function activation(g: SGraph, d: number[], t: number): number[] {
  const max = Math.max(...d.filter(Number.isFinite));
  const span = 0.85 / (max + 1);
  const fade = t > 0.85 ? 1 - (t - 0.85) / 0.15 : 1;
  return d.map((h) => (Number.isFinite(h) ? Math.max(0, Math.min(1, (t - h * span) / span)) * fade : 0));
}
