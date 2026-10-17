"use client";

import { Check, Loader2, X } from "@/components/icons";

import { StatusPill } from "@/components/status";
import type { View } from "@/lib/incident-state";
import { explainers } from "@/lib/investigation";

import { OpLabel } from "./verdict";

/**
 * Signal → diagnoses (Causely's two-way link, research §8.1 #14): click a broken operation that isn't a suspect and
 * see which suspects' predicted footprints include it. The click on a suspect does the reverse (the overlay).
 */
export function ExplainersCard({
  view,
  op,
  footprints,
  loading,
  onPick,
  onClose,
}: {
  view: View;
  op: string;
  footprints: Record<string, { matched: string[] } | undefined>;
  loading: boolean;
  onPick: (hid: string) => void;
  onClose: () => void;
}) {
  const list = explainers(view, op, footprints);
  const yes = list.filter((x) => x.explains);
  return (
    <div className="epi-in rounded-lg border border-border bg-card/95 p-3 text-xs shadow-xl backdrop-blur">
      <div className="flex items-center gap-2">
        <span className="font-semibold">Who explains this symptom?</span>
        <button onClick={onClose} className="ml-auto text-muted-foreground hover:text-foreground" aria-label="Close">✕</button>
      </div>
      <OpLabel op={op} className="mt-1" />
      <p className="mt-1 text-[11px] text-muted-foreground">
        {view.nodes[op]?.anomaly ? `${view.nodes[op]!.anomaly!.kind} · ` : ""}
        {loading ? "loading every suspect's footprint…" : `${yes.length} of ${list.length} suspects predict it`}
      </p>
      {loading && <Loader2 className="mt-2 size-3.5 animate-spin text-muted-foreground" />}
      <ul className="mt-2 space-y-0.5">
        {list.map(({ hyp, explains }) => (
          <li key={hyp.id}>
            <button onClick={() => onPick(hyp.id)} className="flex w-full items-center gap-2 rounded px-1 py-0.5 text-left hover:bg-accent/50" title="Show this suspect's footprint">
              {explains ? <Check className="size-3.5 shrink-0 text-ov-matched" aria-label="predicts it" /> : <X className="size-3.5 shrink-0 text-muted-foreground" aria-label="doesn't predict it" />}
              <span className="w-8 shrink-0 font-mono text-muted-foreground">{hyp.id}</span>
              <OpLabel op={hyp.op} className="min-w-0 flex-1" />
              <StatusPill status={hyp.status} className="shrink-0 scale-90" />
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
