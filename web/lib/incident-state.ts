/**
 * Incident view state: the `/incidents/{id}/graph` snapshot, patched by SSE events (LLD §9).
 *
 * Pure and idempotent: every event is applied by id, and an event whose seq is not newer than the last one applied is
 * ignored, so a reconnect that replays events (or a duplicate) can't add a node twice or roll a status back.
 * A new diagnosis run (`incident.status` with a higher run) clears the run's hypotheses but keeps the topology.
 */
import type { S } from "./api";

export type Status = S["GraphHypothesis"]["status"];

export interface Evidence {
  id: string;
  kind: string;
  verdict: "supports" | "refutes";
  summary?: string;
  path: string[];
}

export interface Hyp {
  id: string;
  op: string;
  status: Status;
  score: number | null;
  hops: number;
  round: number;
  evidence: Record<string, Evidence>;
}

export interface Node {
  id: string;
  service: string;
  service_kind: string | null;
  anomaly: { kind: string; onset: number | null; score: number | null } | null;
}

export interface Edge {
  src: string;
  dst: string;
  rps: number | null;
  err_rate: number | null;
}

export interface Footprint {
  hypothesis_id: string;
  coverage: number;
  precision: number;
  order: number;
  matched: string[];
  missed: string[];
  unexplained: string[];
}

export interface Claim {
  section: "what" | "where" | "why";
  text: string;
  cites: string[];
  support_p?: number | null;
  status?: string | null;
}

export interface TimelineItem {
  seq: number;
  event: string;
  text: string;
  tone: "neutral" | "good" | "bad" | "info" | "warn";
}

export interface View {
  incident: string;
  run: number | null;
  status: string;
  symptom: string | null;
  rootCause: string | null;
  secondCause: string | null;
  confidence: number | null;
  lastSeq: number;
  hyps: Record<string, Hyp>;
  nodes: Record<string, Node>;
  edges: Record<string, Edge>;
  footprints: Record<string, Footprint>;
  noRootCause: { summary: string; checked: string[]; max_coverage: number } | null;
  explanation: { claims: Claim[]; dropped: number; verified: boolean; source: string } | null;
  similar: { incident: string; score: number; cause: string | null; fixes: string[] }[] | null;
  actions: Record<string, { id: string; name: string; rank: number; chosen_by: string }>;
  errors: { code: string; message: string }[];
  timeline: TimelineItem[];
}

export interface StreamEvent {
  seq: number;
  event: string;
  data: Record<string, unknown>;
}

const TIMELINE_MAX = 400;
export const edgeKey = (src: string, dst: string) => `${src}>${dst}`;
export const serviceOf = (op: string) => op.split("/", 1)[0];

export function hydrate(g: S["IncidentGraph"]): View {
  const hyps: Record<string, Hyp> = {};
  for (const h of g.hypotheses) {
    hyps[h.id] = { ...h, evidence: Object.fromEntries(h.evidence.map((e) => [e.id, e])) };
  }
  return {
    incident: g.incident,
    run: g.run,
    status: g.status,
    symptom: g.symptom,
    rootCause: g.root_cause,
    secondCause: g.second_cause,
    confidence: null,
    lastSeq: g.last_seq,
    hyps,
    nodes: Object.fromEntries(g.nodes.map((n) => [n.id, n])),
    edges: Object.fromEntries(g.edges.map((e) => [edgeKey(e.src, e.dst), e])),
    footprints: {},
    noRootCause: null,
    explanation: null,
    similar: null,
    actions: {},
    errors: [],
    timeline: [],
  };
}

/** Re-hydrate from a fresh snapshot (after a verdict) without losing what only the stream knows. */
export function merge(v: View, g: S["IncidentGraph"]): View {
  const fresh = hydrate(g);
  return {
    ...fresh,
    lastSeq: Math.max(v.lastSeq, fresh.lastSeq),
    confidence: v.confidence,
    footprints: g.run === v.run ? v.footprints : {},
    noRootCause: v.noRootCause,
    explanation: g.run === v.run ? v.explanation : null,
    similar: g.run === v.run ? v.similar : null,
    actions: g.run === v.run ? v.actions : {},
    errors: v.errors,
    timeline: v.timeline,
  };
}

function ensureNode(nodes: Record<string, Node>, op: string): Record<string, Node> {
  return nodes[op] ? nodes : { ...nodes, [op]: { id: op, service: serviceOf(op), service_kind: null, anomaly: null } };
}

const fmt = (x: unknown) => (typeof x === "number" ? (Math.round(x * 100) / 100).toString() : String(x ?? ""));

export function describe(e: StreamEvent): Omit<TimelineItem, "seq" | "event"> {
  const d = e.data;
  switch (e.event) {
    case "incident.status":
      return { text: `Incident ${d.status}${d.run ? ` · run ${d.run}` : ""}`, tone: "info" };
    case "hypothesis.created":
      return { text: `Suspect ${d.id}: ${d.target} (${d.hops} hops)`, tone: "neutral" };
    case "evidence.added":
      return {
        text: `${d.id} ${d.kind} ${d.verdict === "supports" ? "supports" : "refutes"} ${d.hypothesis_id}`,
        tone: d.verdict === "supports" ? "good" : "bad",
      };
    case "footprint":
      return {
        text: `${d.hypothesis_id} explains ${Math.round(Number(d.coverage) * 100)}% of symptoms`,
        tone: "info",
      };
    case "hypothesis.status":
      return {
        text: `${d.id} → ${d.status}${d.score != null ? ` (score ${fmt(d.score)})` : ""}`,
        tone: d.status === "refuted" ? "bad" : d.status === "confirmed" ? "good" : "neutral",
      };
    case "verdict":
      return { text: `Verdict: ${d.root_cause ?? "none"}`, tone: "good" };
    case "no_root_cause":
      return { text: "Nothing in the graph explains this alert", tone: "warn" };
    case "memory.similar":
      return { text: `Memory: ${(d.similar as unknown[] | undefined)?.length ?? 0} similar past incidents`, tone: "info" };
    case "explanation":
      return { text: `Explanation ready (${d.source}${d.verified ? ", verified" : ""})`, tone: "info" };
    case "action":
      return { text: `Proposed: ${d.name}`, tone: "neutral" };
    case "error":
      return { text: `Error: ${d.code}`, tone: "bad" };
    default:
      return { text: e.event, tone: "neutral" };
  }
}

export function apply(v: View, e: StreamEvent): View {
  if (e.seq <= v.lastSeq) return v; // replayed or duplicate
  const d = e.data;
  let next: View = {
    ...v,
    lastSeq: e.seq,
    timeline: [...v.timeline, { seq: e.seq, event: e.event, ...describe(e) }].slice(-TIMELINE_MAX),
  };
  switch (e.event) {
    case "incident.status": {
      const run = typeof d.run === "number" ? d.run : v.run;
      if (run !== null && v.run !== null && run > v.run) {
        // a new diagnosis run: its hypotheses reuse local ids (h-1 …), so start the run's state over
        next = { ...next, hyps: {}, footprints: {}, explanation: null, similar: null, actions: {}, rootCause: null,
                 secondCause: null, confidence: null, noRootCause: null }; // prettier-ignore
      }
      return { ...next, run, status: String(d.status) };
    }
    case "hypothesis.created": {
      const id = String(d.id);
      const op = String(d.target);
      if (next.hyps[id]) return next;
      return {
        ...next,
        nodes: ensureNode(next.nodes, op),
        hyps: {
          ...next.hyps,
          [id]: { id, op, status: "open", score: null, hops: Number(d.hops ?? 0), round: Number(d.round ?? 1), evidence: {} },
        },
      };
    }
    case "evidence.added": {
      const hid = String(d.hypothesis_id);
      const h = next.hyps[hid];
      if (!h || h.evidence[String(d.id)]) return next;
      const path = (d.path as string[]) ?? [];
      let nodes = next.nodes;
      for (const op of path) nodes = ensureNode(nodes, op);
      let edges = next.edges;
      if (d.kind === "propagation") {
        // propagation paths run symptom → … → cause along CALLS; other evidence paths aren't call chains
        for (let i = 0; i + 1 < path.length; i++) {
          const k = edgeKey(path[i], path[i + 1]);
          if (!edges[k]) edges = { ...edges, [k]: { src: path[i], dst: path[i + 1], rps: null, err_rate: null } };
        }
      }
      const ev: Evidence = { id: String(d.id), kind: String(d.kind), verdict: d.verdict as Evidence["verdict"], path };
      return { ...next, nodes, edges, hyps: { ...next.hyps, [hid]: { ...h, evidence: { ...h.evidence, [ev.id]: ev } } } };
    }
    case "footprint": {
      const hid = String(d.hypothesis_id);
      return { ...next, footprints: { ...next.footprints, [hid]: d as unknown as Footprint } };
    }
    case "hypothesis.status": {
      const h = next.hyps[String(d.id)];
      if (!h) return next;
      const score = typeof d.score === "number" ? d.score : h.score;
      return { ...next, hyps: { ...next.hyps, [h.id]: { ...h, status: d.status as Status, score } } };
    }
    case "verdict":
      return {
        ...next,
        status: String(d.status ?? next.status),
        rootCause: (d.root_cause as string | null) ?? null,
        secondCause: (d.second_cause as string | null) ?? null,
        confidence: typeof d.confidence === "number" ? d.confidence : null,
      };
    case "no_root_cause":
      return { ...next, status: "no_root_cause", noRootCause: d as unknown as View["noRootCause"] };
    case "memory.similar":
      return { ...next, similar: (d.similar as View["similar"]) ?? [] };
    case "explanation":
      return { ...next, explanation: d as unknown as View["explanation"] };
    case "action": {
      const a = d as unknown as View["actions"][string];
      return { ...next, actions: { ...next.actions, [a.id]: a } };
    }
    case "error":
      return { ...next, errors: [...next.errors, { code: String(d.code), message: String(d.message ?? "") }] };
    default:
      return next;
  }
}

/** The ops and call edges on the winning path (the root cause's propagation evidence), for the glow. */
export function winningPath(v: View): { ops: Set<string>; edges: Set<string> } {
  const h = Object.values(v.hyps).find((x) => x.op === v.rootCause && x.status === "confirmed");
  const prop = h && Object.values(h.evidence).find((e) => e.kind === "propagation" && e.verdict === "supports");
  return pathSets(prop?.path ?? (h ? [h.op] : []));
}

export function pathSets(path: string[]): { ops: Set<string>; edges: Set<string> } {
  const edges = new Set<string>();
  for (let i = 0; i + 1 < path.length; i++) edges.add(edgeKey(path[i], path[i + 1]));
  return { ops: new Set(path), edges };
}

/** Every evidence item of the run by id, for `[E2.1]` citation chips. */
export function evidenceIndex(v: View): Record<string, Evidence & { hypothesis: string }> {
  const out: Record<string, Evidence & { hypothesis: string }> = {};
  for (const h of Object.values(v.hyps)) for (const e of Object.values(h.evidence)) out[e.id] = { ...e, hypothesis: h.id };
  return out;
}
