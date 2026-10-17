"use client";

import { ChevronDown, ChevronRight, Receipt } from "@/components/icons";
import { useMemo, useState } from "react";

import type { Receipts as R } from "@/lib/incident-state";
import { cn } from "@/lib/utils";

const SLOW_MS = 50; // N2 budget is p95 < 200 ms; anything over 50 ms in one run is worth a look

/**
 * Numbered receipts of every graph query the run made (HolmesGPT's tool receipts, research §8.1 #6):
 * `#3 Q2 · 14 ms · 6 rows`. The query ids are the `QUERIES` keys in api/graph.py, so each line is traceable.
 */
export function QueryReceipts({ r }: { r: R | null }) {
  const [open, setOpen] = useState(false);
  const [slowFirst, setSlowFirst] = useState(false);
  const rows = useMemo(() => (r ? (slowFirst ? [...r.queries].sort((a, b) => b.ms - a.ms || a.n - b.n) : r.queries) : []), [r, slowFirst]);
  if (!r) return <p className="text-xs text-muted-foreground">Query receipts appear when a diagnosis run finishes.</p>;
  const slow = r.queries.filter((q) => q.ms >= SLOW_MS).length;
  return (
    <div className="rounded-lg border border-border bg-background/40">
      <button onClick={() => setOpen((o) => !o)} className="flex w-full items-center gap-2 px-2.5 py-2 text-left text-xs" aria-expanded={open}>
        {open ? <ChevronDown className="size-3.5" aria-hidden /> : <ChevronRight className="size-3.5" aria-hidden />}
        <Receipt className="size-3.5 text-signal" aria-hidden />
        <span className="font-medium">Query receipts</span>
        <span className="ml-auto font-mono text-[11px] text-muted-foreground">run {r.run}</span>
      </button>
      <dl className="grid grid-cols-2 gap-x-3 gap-y-0.5 px-2.5 pb-2 font-mono text-[11px]">
        <dt className="text-muted-foreground">graph queries</dt>
        <dd className="text-right tabular-nums">{r.queries.length + r.dropped}{slow ? <span className="text-ov-missed"> · {slow} slow</span> : null}</dd>
        <dt className="text-muted-foreground">time in FalkorDB</dt>
        <dd className="text-right tabular-nums">{r.total_query_ms.toFixed(0)} ms</dd>
        {r.verdict_ms != null && (
          <>
            <dt className="text-muted-foreground">verdict after</dt>
            <dd className="text-right tabular-nums">{(r.verdict_ms / 1000).toFixed(1)} s</dd>
          </>
        )}
        <dt className="text-muted-foreground" title="incl. memory, explanation and actions">whole run</dt>
        <dd className="text-right tabular-nums">{(r.run_ms / 1000).toFixed(1)} s</dd>
      </dl>
      {open && (
        <>
          <div className="flex items-center gap-2 border-t border-border px-2.5 py-1.5 text-[11px]">
            <label className="flex items-center gap-1.5 text-muted-foreground">
              <input type="checkbox" checked={slowFirst} onChange={(e) => setSlowFirst(e.target.checked)} className="accent-[var(--color-signal)]" /> slowest first
            </label>
            {r.dropped > 0 && <span className="ml-auto text-muted-foreground">+{r.dropped} not listed</span>}
          </div>
          <ol className="max-h-72 overflow-y-auto border-t border-border font-mono text-[11px]">
            {rows.map((q) => (
              <li key={q.n} className={cn("grid grid-cols-[40px_1fr_64px_56px] gap-2 px-2.5 py-0.5 odd:bg-muted/20", q.ms >= SLOW_MS && "text-ov-missed")}>
                <span className="text-muted-foreground">#{q.n}</span>
                <span className="truncate" title={q.qid}>{q.qid}</span>
                <span className="text-right tabular-nums">{q.ms.toFixed(1)} ms</span>
                <span className="text-right text-muted-foreground tabular-nums">{q.rows} row{q.rows === 1 ? "" : "s"}</span>
              </li>
            ))}
          </ol>
        </>
      )}
    </div>
  );
}
