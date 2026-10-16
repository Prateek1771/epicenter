/**
 * Derived views of an incident for the investigation UI (phase 12, COMPETITOR_UI_RESEARCH §8.1). Pure and
 * unit-tested; everything here is read off the engine's own output, nothing is ranked or re-scored (AGENTS rule 4).
 */
import type { Hyp, View } from "./incident-state";

export interface RuledOut {
  hyp: Hyp;
  reason: string;
  path: string[];
}

const PRUNED = "lost on score to the root cause";

/** Refuted and pruned suspects, each with the one-line reason the engine recorded (its refuting evidence). */
export function ruledOut(v: View): RuledOut[] {
  return Object.values(v.hyps)
    .filter((h) => h.status === "refuted" || h.status === "pruned")
    .sort((a, b) => (b.score ?? -1) - (a.score ?? -1) || a.id.localeCompare(b.id))
    .map((h) => {
      const ev = Object.values(h.evidence)
        .filter((e) => e.verdict === "refutes")
        .sort((a, b) => a.id.localeCompare(b.id))[0];
      return {
        hyp: h,
        reason: ev?.summary || (ev ? `${ev.kind} evidence refutes it` : h.status === "pruned" ? PRUNED : "refuted"),
        path: ev?.path.length ? ev.path : [h.op],
      };
    });
}

export interface Lane {
  op: string;
  service: string;
  kind: string;
  onset: number;
  score: number | null;
  role: "root" | "second" | "symptom" | null;
}

/** One lane per anomalous operation on the canvas, earliest onset first (ties: id). */
export function lanes(v: View): Lane[] {
  return Object.values(v.nodes)
    .filter((n) => n.anomaly?.onset != null)
    .map((n) => ({
      op: n.id,
      service: n.service,
      kind: n.anomaly!.kind,
      onset: n.anomaly!.onset!,
      score: n.anomaly!.score,
      role: (n.id === v.rootCause ? "root" : n.id === v.secondCause ? "second" : n.id === v.symptom ? "symptom" : null) as Lane["role"],
    }))
    .sort((a, b) => a.onset - b.onset || a.op.localeCompare(b.op));
}

/** The time axis: every onset, change and the alert, padded 10% each side (≥ 30 s). */
export function timeAxis(v: View): { t0: number; t1: number } | null {
  const ts = [...lanes(v).map((l) => l.onset), ...v.changes.map((c) => c.ts), ...(v.alertTs != null ? [v.alertTs] : [])];
  if (!ts.length) return null;
  const lo = Math.min(...ts);
  const hi = Math.max(...ts);
  const pad = Math.max(30, (hi - lo) * 0.1);
  return { t0: lo - pad, t1: hi + pad };
}

/** Operations whose anomaly hasn't started yet at time `t`: faded while the slicer plays the spread. */
export function notYet(v: View, t: number | null): Set<string> {
  if (t === null) return new Set();
  return new Set(lanes(v).filter((l) => l.onset > t).map((l) => l.op));
}

export interface TMinus {
  change: { ts: number; label: string; offset: number } | null;
  onset: { ts: number; offset: number } | null;
  alert: number;
}

/** change −Nm → root onset → alert, offsets in seconds before the alert (Rootly's strip, from the engine's data). */
export function tMinus(v: View, change: { ts: number; summary?: string | null; type: string } | null): TMinus | null {
  if (v.alertTs == null) return null;
  const root = v.rootCause ? v.nodes[v.rootCause]?.anomaly?.onset ?? null : null;
  return {
    change: change ? { ts: change.ts, label: change.summary || change.type, offset: v.alertTs - change.ts } : null,
    onset: root != null ? { ts: root, offset: v.alertTs - root } : null,
    alert: v.alertTs,
  };
}

/** `90` → `1m 30s`, `45` → `45s`, `-20` → `+20s` (after the alert). */
export function ago(s: number): string {
  if (s < 0) return `+${ago(-s)}`;
  const m = Math.floor(s / 60);
  const r = Math.round(s % 60);
  return m ? (r ? `${m}m ${r}s` : `${m}m`) : `${r}s`;
}

export interface Explainer {
  hyp: Hyp;
  explains: boolean;
}

/** Signals → diagnoses (Causely's two-way link): which suspects' footprints match this symptom, which don't. */
export function explainers(v: View, op: string, footprints: Record<string, { matched: string[] } | undefined>): Explainer[] {
  return Object.values(v.hyps)
    .filter((h) => footprints[h.id])
    .map((h) => ({ hyp: h, explains: footprints[h.id]!.matched.includes(op) }))
    .sort((a, b) => Number(b.explains) - Number(a.explains) || (b.hyp.score ?? -1) - (a.hyp.score ?? -1) || a.hyp.id.localeCompare(b.hyp.id));
}
