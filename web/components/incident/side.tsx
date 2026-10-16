"use client";

import { HelpCircle, Loader2, Search } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import { StatusPill } from "@/components/status";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api, ApiError, call, type S } from "@/lib/api";
import { pct, splitOp } from "@/lib/format";
import type { Footprint, Hyp, TimelineItem } from "@/lib/incident-state";
import { cn } from "@/lib/utils";

import { OpLabel } from "./verdict";

const TONE: Record<TimelineItem["tone"], string> = {
  neutral: "bg-muted-foreground/60",
  good: "bg-st-confirmed",
  bad: "bg-st-refuted",
  info: "bg-signal",
  warn: "bg-ov-missed",
};

/** The suspects as a list: the accessible twin of the canvas, sorted the way the scorer ranks them. */
function SuspectRows({ hyps, selected, onSelect, label }: { hyps: Hyp[]; selected: string | null; onSelect: (id: string) => void; label: string }) {
  const sorted = [...hyps].sort((a, b) => (b.score ?? -9) - (a.score ?? -9) || a.id.localeCompare(b.id));
  return (
    <ul className="space-y-1" aria-label={label}>
      {sorted.map((h) => (
        <li key={h.id}>
          <button
            onClick={() => onSelect(h.id)}
            aria-pressed={selected === h.id}
            className={cn(
              "flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-xs hover:bg-accent/60",
              selected === h.id && "bg-accent ring-1 ring-signal/50",
            )}
          >
            <span className="w-9 shrink-0 font-mono text-muted-foreground">{h.id}</span>
            <OpLabel op={h.op} className="min-w-0 flex-1" />
            <span className="w-9 shrink-0 text-right font-mono tabular-nums text-muted-foreground">{h.score != null ? h.score.toFixed(2) : "…"}</span>
            <StatusPill status={h.status} className="shrink-0" />
          </button>
        </li>
      ))}
    </ul>
  );
}

export function SuspectList({ hyps, selected, onSelect }: { hyps: Hyp[]; selected: string | null; onSelect: (id: string) => void }) {
  if (!hyps.length) return <p className="text-xs text-muted-foreground">Suspects appear here as triage finds them.</p>;
  // round 2 is the second-cause search over a narrower symptom set (LLD §7.5): its scores aren't comparable with round 1's
  const r2 = hyps.filter((h) => h.round === 2);
  return (
    <div className="space-y-4">
      <SuspectRows hyps={hyps.filter((h) => h.round !== 2)} selected={selected} onSelect={onSelect} label="Suspects" />
      {r2.length > 0 && (
        <div>
          <h3 className="mb-1 px-2 text-[11px] font-semibold tracking-wide text-muted-foreground uppercase">Second-cause search</h3>
          <p className="mb-1.5 px-2 text-[11px] text-muted-foreground">Scored on the symptoms the root cause leaves unexplained; not ranked against the list above.</p>
          <SuspectRows hyps={r2} selected={selected} onSelect={onSelect} label="Second-cause suspects" />
        </div>
      )}
    </div>
  );
}

export function OverlayLegend({ hyp, fp, onClear }: { hyp: Hyp; fp: (Footprint & { missedOffCanvas: string[] }) | null; onClear: () => void }) {
  return (
    <div className="epi-in rounded-lg border border-border bg-card/95 p-3 text-xs shadow-xl backdrop-blur">
      <div className="flex items-center gap-2">
        <span className="font-semibold">Fault Simulator</span>
        <span className="font-mono text-muted-foreground">{hyp.id}</span>
        <button onClick={onClear} className="ml-auto text-muted-foreground hover:text-foreground" aria-label="Close overlay">
          ✕
        </button>
      </div>
      <OpLabel op={hyp.op} className="mt-1" />
      {fp ? (
        <>
          <p className="mt-2 font-mono text-[11px]">
            explains {fp.matched.length} / {fp.matched.length + fp.unexplained.length} · precision {fp.precision.toFixed(2)} · order {fp.order.toFixed(2)}
          </p>
          <div className="mt-2 grid grid-cols-3 gap-2">
            <span className="flex items-center gap-1.5"><span className="size-2.5 rounded-sm outline-2 outline-ov-matched" /> matched {fp.matched.length}</span>
            <span className="flex items-center gap-1.5"><span className="size-2.5 rounded-sm outline-2 outline-dashed outline-ov-missed" /> missed {fp.missed.length}</span>
            <span className="flex items-center gap-1.5"><span className="size-2.5 rounded-sm outline-2 outline-ov-unexplained" /> unexplained {fp.unexplained.length}</span>
          </div>
          {fp.missedOffCanvas.length > 0 && (
            <p className="mt-2 text-[11px] text-muted-foreground">
              Predicted but quiet, off canvas: {fp.missedOffCanvas.slice(0, 4).map((o) => splitOp(o)[0]).join(", ")}
              {fp.missedOffCanvas.length > 4 && ` +${fp.missedOffCanvas.length - 4}`}
            </p>
          )}
        </>
      ) : (
        <p className="mt-2 flex items-center gap-1.5 text-muted-foreground"><Loader2 className="size-3 animate-spin" /> loading prediction…</p>
      )}
    </div>
  );
}

export function Timeline({ items }: { items: TimelineItem[] }) {
  const end = useRef<HTMLDivElement>(null);
  useEffect(() => end.current?.scrollIntoView({ block: "nearest" }), [items.length]);
  if (!items.length) return <p className="text-xs text-muted-foreground">Live events appear here while the agents work. Rerun the diagnosis to watch.</p>;
  return (
    <ol className="relative space-y-1.5 border-l border-border pl-3" aria-live="polite" aria-label="Investigation timeline">
      {items.map((t) => (
        <li key={t.seq} className="epi-in relative text-xs [overflow-wrap:anywhere]">
          <span className={cn("absolute top-1.5 -left-[16.5px] size-2 rounded-full ring-2 ring-background", TONE[t.tone])} aria-hidden />
          <span className="mr-1.5 font-mono text-[10px] text-muted-foreground">#{t.seq}</span>
          {t.text}
        </li>
      ))}
      <div ref={end} />
    </ol>
  );
}

export function WhyNot({
  incident,
  env,
  services,
  onPath,
}: {
  incident: string;
  env: string | null;
  services: string[];
  onPath: (ops: string[], label: string) => void;
}) {
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState(false);
  const [ans, setAns] = useState<S["WhyNot"] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const opts = useMemo(() => [...new Set(services)].sort(), [services]);
  const ask = async (svc: string) => {
    if (!svc) return;
    setBusy(true);
    setErr(null);
    try {
      const a = await call(
        api.GET("/api/v1/incidents/{incident_id}/why-not/{service}", {
          params: { path: { incident_id: incident, service: svc }, query: { env: env ?? undefined } },
        }),
      );
      setAns(a);
      const ops = [...new Set(a.evidence.flatMap((e) => e.path))];
      if (ops.length) onPath(ops, `why not ${svc}`);
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="space-y-2">
      <form
        className="flex gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          ask(q.trim());
        }}
      >
        <Input list="why-not-services" aria-label="Service" placeholder="why not… cart" value={q} onChange={(e) => setQ(e.target.value)} className="h-8 font-mono text-sm" />
        <datalist id="why-not-services">{opts.map((s) => <option key={s} value={s} />)}</datalist>
        <Button size="sm" variant="secondary" type="submit" disabled={!q.trim() || busy} aria-label="Ask why not">
          {busy ? <Loader2 className="size-3.5 animate-spin" /> : <Search className="size-3.5" />}
        </Button>
      </form>
      {err && <p className="text-xs text-st-refuted">{err}</p>}
      {ans && (
        <div className="epi-in rounded-lg border border-border bg-background/40 p-2.5 text-sm">
          <p className="flex items-center gap-1.5 text-[11px] font-semibold tracking-wide text-muted-foreground uppercase">
            <HelpCircle className="size-3.5" aria-hidden /> {ans.service}: {ans.answer.replaceAll("_", " ")}
          </p>
          <p className="mt-1 leading-relaxed">{ans.summary}</p>
          {ans.evidence.length > 0 && (
            <p className="mt-1.5 font-mono text-[11px] text-muted-foreground">
              {ans.evidence.map((e) => `${e.id} ${e.kind}`).join(" · ")}
            </p>
          )}
        </div>
      )}
    </div>
  );
}

export function IncidentFacts({ inc }: { inc: S["IncidentOut"] }) {
  return (
    <dl className="grid grid-cols-2 gap-x-3 gap-y-1 text-xs">
      <dt className="text-muted-foreground">Alerts</dt>
      <dd className="font-mono">{inc.alert_count}</dd>
      <dt className="text-muted-foreground">Diagnosis run</dt>
      <dd className="font-mono">{inc.run ?? "—"}</dd>
      <dt className="text-muted-foreground">Weights</dt>
      <dd className="truncate font-mono" title={inc.weights_version ?? ""}>{inc.weights_version ?? "—"}</dd>
      <dt className="text-muted-foreground">Coverage</dt>
      <dd className="font-mono">{inc.verdict?.footprint ? pct(inc.verdict.footprint.coverage) : "—"}</dd>
    </dl>
  );
}
