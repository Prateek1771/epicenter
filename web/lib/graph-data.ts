/**
 * The "Data" half of every Graph | Data toggle (phase 12): the same nodes and edges a graph view draws, as tables.
 * Pure (unit-tested): rows from each view's API payload, filtering, sorting, CSV.
 */
import type { S } from "./api";
import type { View } from "./incident-state";

export type Cell = string | number | null;
export type Row = Record<string, Cell> & { id: string };

export interface Column {
  key: string;
  label: string;
  numeric?: boolean;
}

export interface Table {
  columns: Column[];
  rows: Row[];
}

export interface GraphData {
  nodes: Table;
  edges: Table;
  raw: unknown; // the payload as the API sent it, for the JSON tab and download
}

const round = (x: number | null | undefined, d = 3): number | null =>
  x === null || x === undefined ? null : Math.round(x * 10 ** d) / 10 ** d;

/** Seconds from the alert (`+12`, `-30`), the way the canvas and the lanes show time. */
export const relSeconds = (ts: number | null | undefined, base: number | null | undefined): number | null =>
  ts === null || ts === undefined || base === null || base === undefined ? null : ts - base;

const EDGE_COLS: Column[] = [
  { key: "src", label: "caller" },
  { key: "dst", label: "callee" },
  { key: "rps", label: "rps", numeric: true },
  { key: "err_rate", label: "err rate", numeric: true },
  { key: "p95_ms", label: "p95 ms", numeric: true },
];

function edgeRows(edges: { src: string; dst: string; rps?: number | null; err_rate?: number | null; p95_ms?: number | null }[]): Row[] {
  return edges.map((e) => ({ id: `${e.src}>${e.dst}`, src: e.src, dst: e.dst, rps: round(e.rps), err_rate: round(e.err_rate), p95_ms: round(e.p95_ms, 1) }));
}

/** Incident canvas: every operation with its anomaly and its suspect, every call between them. */
export function fromView(v: View): GraphData {
  const hypByOp: Record<string, View["hyps"][string]> = {};
  for (const h of Object.values(v.hyps)) if (!hypByOp[h.op] || h.round >= hypByOp[h.op].round) hypByOp[h.op] = h;
  const rows: Row[] = Object.values(v.nodes)
    .sort((a, b) => a.id.localeCompare(b.id))
    .map((n) => {
      const h = hypByOp[n.id];
      const role = n.id === v.rootCause ? "root cause" : n.id === v.secondCause ? "2nd cause" : n.id === v.symptom ? "alert" : null;
      return {
        id: n.id,
        op: n.id,
        service: n.service,
        role,
        anomaly: n.anomaly?.kind ?? null,
        onset_s: relSeconds(n.anomaly?.onset, v.alertTs),
        anomaly_score: round(n.anomaly?.score),
        suspect: h?.id ?? null,
        status: h?.status ?? null,
        score: round(h?.score),
        hops: h?.hops ?? null,
      };
    });
  return {
    nodes: {
      columns: [
        { key: "op", label: "operation" },
        { key: "service", label: "service" },
        { key: "role", label: "role" },
        { key: "anomaly", label: "anomaly" },
        { key: "onset_s", label: "onset (s vs alert)", numeric: true },
        { key: "anomaly_score", label: "anomaly score", numeric: true },
        { key: "suspect", label: "suspect" },
        { key: "status", label: "status" },
        { key: "score", label: "score", numeric: true },
        { key: "hops", label: "hops", numeric: true },
      ],
      rows,
    },
    edges: { columns: EDGE_COLS.slice(0, 4), rows: edgeRows(Object.values(v.edges).sort((a, b) => a.src.localeCompare(b.src) || a.dst.localeCompare(b.dst))) },
    raw: {
      incident: v.incident,
      run: v.run,
      status: v.status,
      symptom: v.symptom,
      root_cause: v.rootCause,
      alert_ts: v.alertTs,
      nodes: Object.values(v.nodes),
      edges: Object.values(v.edges),
      hypotheses: Object.values(v.hyps).map((h) => ({ ...h, evidence: Object.values(h.evidence) })),
      changes: v.changes,
    },
  };
}

export function fromTopology(t: S["Topology"]): GraphData {
  return {
    nodes: {
      columns: [
        { key: "id", label: t.level === "service" ? "service" : "operation" },
        ...(t.level === "operation" ? [{ key: "service", label: "service" }] : []),
        { key: "kind", label: "kind" },
        { key: "owner", label: "owner" },
        ...(t.level === "service" ? [{ key: "ops", label: "ops", numeric: true }] : []),
        { key: "in_rps", label: "inbound rps", numeric: true },
        { key: "anomalies", label: "anomalies (open incidents)" },
        { key: "root_cause_of", label: "root cause of" },
      ],
      rows: t.nodes.map((n) => ({
        id: n.id,
        service: n.service,
        kind: n.kind ?? null,
        owner: n.owner ?? null,
        ops: n.ops ?? null,
        in_rps: round(t.edges.filter((e) => e.dst === n.id).reduce((s, e) => s + (e.rps ?? 0), 0)),
        anomalies: n.anomalies.map((a) => `${a.kind}@${a.incident}`).join(", ") || null,
        root_cause_of: n.root_cause_of.join(", ") || null,
      })),
    },
    edges: { columns: EDGE_COLS, rows: edgeRows(t.edges) },
    raw: t,
  };
}

export function fromBlastRadius(b: S["BlastRadius"]): GraphData {
  const rows: Row[] = [
    ...(b.sources ?? []).map((op) => ({ id: op, op, service: b.service, hops: 0, owner: null, role: "fails" })),
    ...b.affected.map((a) => ({ id: a.operation, op: a.operation, service: a.service, hops: a.hops, owner: a.owner ?? null, role: "affected" })),
  ];
  return {
    nodes: {
      columns: [
        { key: "op", label: "operation" },
        { key: "service", label: "service" },
        { key: "role", label: "role" },
        { key: "hops", label: "hops away", numeric: true },
        { key: "owner", label: "owner" },
      ],
      rows,
    },
    edges: { columns: EDGE_COLS, rows: edgeRows(b.edges ?? []) },
    raw: b,
  };
}

export function fromSimulation(s: S["SimulateOut"]): GraphData {
  return {
    nodes: {
      columns: [
        { key: "op", label: "operation" },
        { key: "service", label: "service" },
        { key: "kind", label: "predicted kind" },
        { key: "p", label: "p", numeric: true },
        { key: "hops", label: "hops", numeric: true },
        { key: "expected_delay_s", label: "≤ delay s", numeric: true },
        { key: "owner", label: "owner" },
      ],
      rows: s.predicted.map((p) => ({ id: `${p.op}:${p.kind}`, op: p.op, service: p.service ?? null, kind: p.kind, p: round(p.p),
                                      hops: p.hops, expected_delay_s: p.expected_delay_s, owner: p.owner ?? null })), // prettier-ignore
    },
    edges: { columns: EDGE_COLS, rows: edgeRows(s.edges ?? []) },
    raw: s,
  };
}

/** Case-insensitive match on any cell; several words must all match (`payment errors`). */
export function filterRows(rows: Row[], q: string): Row[] {
  const words = q.toLowerCase().split(/\s+/).filter(Boolean);
  if (!words.length) return rows;
  return rows.filter((r) => {
    const text = Object.values(r).filter((c) => c !== null).join(" ").toLowerCase();
    return words.every((w) => text.includes(w));
  });
}

/** Stable sort on one column; empty cells last whatever the direction, ties broken by id. */
export function sortRows(rows: Row[], key: string, dir: "asc" | "desc"): Row[] {
  const sign = dir === "asc" ? 1 : -1;
  return [...rows].sort((a, b) => {
    const x = a[key];
    const y = b[key];
    if (x === null || x === undefined) return y === null || y === undefined ? a.id.localeCompare(b.id) : 1;
    if (y === null || y === undefined) return -1;
    const c = typeof x === "number" && typeof y === "number" ? x - y : String(x).localeCompare(String(y));
    return c !== 0 ? sign * c : a.id.localeCompare(b.id);
  });
}

/** RFC 4180: quote cells with a comma, quote or newline; double the quotes inside. */
export function toCsv(t: Table): string {
  const esc = (c: Cell | undefined) => {
    const s = c === null || c === undefined ? "" : String(c);
    return /[",\r\n]/.test(s) ? `"${s.replaceAll('"', '""')}"` : s;
  };
  return [t.columns.map((c) => esc(c.label)).join(","), ...t.rows.map((r) => t.columns.map((c) => esc(r[c.key])).join(","))].join("\r\n") + "\r\n";
}
