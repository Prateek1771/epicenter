"use client";

import { ChevronDown, ChevronUp, Pause, Play, RotateCcw } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { splitOp } from "@/lib/format";
import type { View } from "@/lib/incident-state";
import { ago, lanes as toLanes, timeAxis } from "@/lib/investigation";
import { cn } from "@/lib/utils";

const KIND: Record<string, string> = {
  errors: "bg-st-refuted",
  down: "bg-st-refuted",
  latency: "bg-ov-missed",
  saturation: "bg-ov-missed",
  cpu: "bg-iris-violet",
  mem: "bg-lavender",
};
const PLAY_MS = 12_000; // the whole axis plays in 12 s
const TICK_MS = 100;

/**
 * Entity × time lanes under the canvas (Grafana Asserts / Dynatrace, COMPETITOR_UI_RESEARCH §8.1 #9) with an onset
 * slicer (Neo4j Bloom, #13): drag or Play, and operations whose anomaly hasn't started yet fade on the canvas.
 */
export function Lanes({ view, cutoff, onCutoff, onLane, active }: {
  view: View;
  cutoff: number | null;
  onCutoff: (t: number | null) => void;
  onLane: (op: string) => void;
  active: string | null;
}) {
  const [open, setOpen] = useState(true);
  const [playing, setPlaying] = useState(false);
  const rows = useMemo(() => toLanes(view), [view]);
  const axis = useMemo(() => timeAxis(view), [view]);

  useEffect(() => {
    if (!playing || !axis) return;
    const step = ((axis.t1 - axis.t0) * TICK_MS) / PLAY_MS;
    const t = setInterval(() => {
      const next = (cutoff ?? axis.t0) + step;
      if (next >= axis.t1) {
        setPlaying(false);
        onCutoff(null);
      } else onCutoff(next);
    }, TICK_MS);
    return () => clearInterval(t);
  }, [playing, axis, cutoff, onCutoff]);

  if (!axis || (!rows.length && !view.changes.length)) return null;
  const x = (t: number) => `${((t - axis.t0) / (axis.t1 - axis.t0)) * 100}%`;
  const alert = view.alertTs;
  const rel = (t: number) => (alert != null ? (t <= alert ? `−${ago(alert - t)}` : ago(alert - t)) : new Date(t * 1000).toLocaleTimeString());

  return (
    <section className="border-t border-border bg-card/70 backdrop-blur" aria-label="Anomaly onsets over time">
      <div className="flex items-center gap-3 px-3 py-1.5 text-xs">
        <button onClick={() => setOpen((o) => !o)} className="flex items-center gap-1 font-semibold tracking-wider text-muted-foreground uppercase hover:text-foreground" aria-expanded={open}>
          {open ? <ChevronDown className="size-3.5" /> : <ChevronUp className="size-3.5" />} Timeline lanes
        </button>
        <span className="text-muted-foreground">{rows.length} anomalous · {view.changes.length} change{view.changes.length === 1 ? "" : "s"}</span>
        <div className="ml-auto flex items-center gap-2">
          <button
            onClick={() => {
              if (!playing && (cutoff === null || cutoff >= axis.t1)) onCutoff(axis.t0);
              setPlaying((p) => !p);
            }}
            className="inline-flex items-center gap-1 rounded-md bg-acid-lime px-2 py-0.5 font-medium text-void shadow-cta hover:brightness-110"
            aria-label={playing ? "Pause playback" : "Play the onsets in order"}
          >
            {playing ? <Pause className="size-3" /> : <Play className="size-3" />} {playing ? "Pause" : "Play spread"}
          </button>
          <input
            type="range"
            min={Math.floor(axis.t0)}
            max={Math.ceil(axis.t1)}
            value={Math.round(cutoff ?? axis.t1)}
            onChange={(e) => { setPlaying(false); onCutoff(Number(e.target.value) >= axis.t1 ? null : Number(e.target.value)); }}
            className="w-40"
            aria-label="Show the canvas as it was at this time"
          />
          <span className="w-20 text-right font-mono tabular-nums text-muted-foreground">{cutoff === null ? "all" : rel(cutoff)}</span>
          {cutoff !== null && (
            <button onClick={() => { setPlaying(false); onCutoff(null); }} className="text-muted-foreground hover:text-foreground" aria-label="Show everything">
              <RotateCcw className="size-3.5" />
            </button>
          )}
        </div>
      </div>
      {open && (
        <div className="relative max-h-44 overflow-y-auto px-3 pb-2">
          <div className="grid grid-cols-[180px_1fr]">
            <span />
            <div className="flex h-4 items-end justify-between font-mono text-[10px] text-muted-foreground">
              <span>{rel(axis.t0)}</span>
              <span>{rel(axis.t1)}</span>
            </div>
          </div>
          {/* over every lane: changes as blue ticks, the alert in the accent colour, the slicer cursor */}
          <div className="pointer-events-none absolute inset-y-0 right-3 left-[calc(180px+0.75rem)]">
            {view.changes.map((c) => (
              <Tooltip key={c.id}>
                <TooltipTrigger asChild>
                  <span className="pointer-events-auto absolute top-1 bottom-1 z-10 w-0.5 cursor-help rounded bg-st-supported" style={{ left: x(c.ts) }} aria-label={`change ${c.summary ?? c.type}`} />
                </TooltipTrigger>
                <TooltipContent className="text-xs">
                  <b>{c.type}</b> on {c.service}: {c.summary ?? c.id} · {rel(c.ts)}
                </TooltipContent>
              </Tooltip>
            ))}
            {alert != null && (
              <span className="absolute top-1 bottom-1 z-10 w-0.5 rounded bg-signal" style={{ left: x(alert) }}>
                <span className="absolute -top-1 right-1 font-mono text-[10px] text-signal">alert</span>
              </span>
            )}
            {cutoff !== null && <span className="absolute inset-y-0 z-20 w-px bg-acid-lime shadow-[0_0_6px_var(--color-acid-lime)]" style={{ left: x(cutoff) }} />}
          </div>
          <ul className="space-y-0.5">
            {rows.map((l) => (
              <li key={l.op}>
                <button onClick={() => onLane(l.op)} className={cn("grid w-full grid-cols-[180px_1fr] items-center rounded text-left hover:bg-accent/50", active === l.op && "bg-signal/10")} title={`${l.op} · ${l.kind} from ${rel(l.onset)}`}>
                  <span className="flex min-w-0 items-center gap-1.5 pr-2 font-mono text-[11px]">
                    {l.role === "root" && <span className="text-st-confirmed" aria-label="root cause">♛</span>}
                    {l.role === "symptom" && <span className="text-signal" aria-label="alert">●</span>}
                    <span className="truncate">{splitOp(l.op)[0]}<span className="text-muted-foreground">/{splitOp(l.op)[1]}</span></span>
                  </span>
                  <span className="relative h-3.5 rounded-sm bg-muted/40">
                    <span
                      className={cn("absolute inset-y-0.5 right-0 rounded-sm opacity-80 transition-opacity", KIND[l.kind] ?? "bg-muted-foreground", cutoff !== null && l.onset > cutoff && "opacity-15")}
                      style={{ left: x(l.onset) }}
                    />
                    <span className="absolute top-1/2 -translate-y-1/2 pl-1 font-mono text-[9px] text-foreground/80" style={{ left: x(l.onset) }}>{l.kind}</span>
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
