/**
 * Canvas layout: elk "layered", left → right along CALLS, so the alerting operation sits on the left and the causes
 * fan out to the right. Incremental: nodes that already have a position keep it, so the canvas never jumps while
 * events arrive; only new nodes take the position elk gives them.
 */
export type XY = { x: number; y: number };

export const NODE_W = 236;
export const NODE_H = 64;

export interface LayoutInput {
  nodes: { id: string; group: string }[];
  edges: { src: string; dst: string }[];
}

/** Keep every known position; take the computed one only for nodes that are new. Pure (unit-tested). */
export function keepPlaced(prev: Record<string, XY>, computed: Record<string, XY>): Record<string, XY> {
  const out: Record<string, XY> = {};
  for (const [id, xy] of Object.entries(computed)) out[id] = prev[id] ?? xy;
  return out;
}

type Elk = { layout: (g: unknown) => Promise<{ children?: { id: string; x?: number; y?: number }[] }> };
let elk: Promise<Elk> | null = null;

async function engine(): Promise<Elk> {
  // loaded on demand: elk is ~1 MB and only the incident and what-if canvases need it
  elk ??= import("elkjs/lib/elk.bundled.js").then((m) => new m.default() as Elk);
  return elk;
}

/** `direction` LEFT puts callees on the left: blast radius reads failing service → its callers, left to right. */
export async function layout(input: LayoutInput, prev: Record<string, XY> = {}, direction: "RIGHT" | "LEFT" = "RIGHT"): Promise<Record<string, XY>> {
  const ids = new Set(input.nodes.map((n) => n.id));
  const graph = {
    id: "root",
    layoutOptions: {
      "elk.algorithm": "layered",
      "elk.direction": direction,
      "elk.layered.spacing.nodeNodeBetweenLayers": "90",
      "elk.spacing.nodeNode": "28",
      "elk.layered.nodePlacement.strategy": "BRANDES_KOEPF",
      "elk.layered.crossingMinimization.semiInteractive": "true",
    },
    // sorted, so the same graph always lays out the same way
    children: [...input.nodes]
      .sort((a, b) => a.group.localeCompare(b.group) || a.id.localeCompare(b.id))
      .map((n) => ({ id: n.id, width: NODE_W, height: NODE_H })),
    edges: input.edges
      .filter((e) => ids.has(e.src) && ids.has(e.dst) && e.src !== e.dst)
      .map((e, i) => ({ id: `e${i}`, sources: [e.src], targets: [e.dst] })),
  };
  const res = await (await engine()).layout(graph);
  const computed: Record<string, XY> = {};
  for (const c of res.children ?? []) computed[c.id] = { x: c.x ?? 0, y: c.y ?? 0 };
  return keepPlaced(prev, computed);
}
