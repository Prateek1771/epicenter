"use client";

import { ArrowRight, CircleHelp, Crown, Lightbulb, Sparkles } from "lucide-react";

import { Meter } from "@/components/status";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import type { S } from "@/lib/api";
import { pct, serviceColor, splitOp } from "@/lib/format";
import { cn } from "@/lib/utils";

const PARTS: [string, string][] = [
  ["onset_earliness", "Went bad first"],
  ["footprint", "Explains the symptoms"],
  ["mechanism_fit", "Self-caused, not a victim"],
  ["strength", "Anomaly strength"],
  ["change_match", "Recent change"],
  ["pagerank", "Graph centrality"],
];

function Ring({ value }: { value: number }) {
  const r = 26;
  const c = 2 * Math.PI * r;
  return (
    <div className="relative grid size-[68px] place-items-center" role="img" aria-label={`confidence ${pct(value)}`}>
      <svg viewBox="0 0 64 64" className="absolute inset-0 -rotate-90">
        <circle cx="32" cy="32" r={r} fill="none" stroke="var(--muted)" strokeWidth="6" />
        <circle
          cx="32"
          cy="32"
          r={r}
          fill="none"
          stroke="var(--color-st-confirmed)"
          strokeWidth="6"
          strokeLinecap="round"
          strokeDasharray={c}
          strokeDashoffset={c * (1 - value)}
          className="transition-[stroke-dashoffset] duration-700"
        />
      </svg>
      <span className="font-mono text-sm font-semibold tabular-nums">{pct(value)}</span>
    </div>
  );
}

export function OpLabel({ op, className }: { op: string; className?: string }) {
  const [svc, name] = splitOp(op);
  return (
    <span className={cn("flex max-w-full min-w-0 items-center gap-1.5 font-mono", className)} title={op}>
      <span className="size-2 shrink-0 rounded-full" style={{ background: serviceColor(svc) }} aria-hidden />
      <span className="truncate">
        {svc}
        <span className="text-muted-foreground">/{name}</span>
      </span>
    </span>
  );
}

export function PathChips({ path, onClick }: { path: string[]; onClick?: () => void }) {
  // evidence paths run alerting operation → … → cause; show them cause-first, the way the failure travelled
  const chain = [...path].reverse();
  return (
    <button
      onClick={onClick}
      className="flex w-full flex-wrap items-center gap-1 rounded-md p-1 text-left text-[11px] hover:bg-accent/50"
      title="Highlight this path on the graph"
    >
      {chain.map((op, i) => (
        <span key={op + i} className="flex min-w-0 items-center gap-1">
          <span className="max-w-[150px] truncate rounded bg-muted px-1.5 py-0.5 font-mono" title={op}>
            {splitOp(op)[0]}
            <span className="text-muted-foreground">/{splitOp(op)[1]}</span>
          </span>
          {i < chain.length - 1 && <ArrowRight className="size-3 text-muted-foreground" aria-hidden />}
        </span>
      ))}
    </button>
  );
}

export function VerdictCard({ v, onPath }: { v: NonNullable<S["IncidentOut"]["verdict"]>; onPath: (p: string[]) => void }) {
  const rc = v.root_cause;
  const parts = rc.score_parts as Record<string, number | string>;
  return (
    <section className="epi-in rounded-xl border border-st-confirmed/30 bg-gradient-to-b from-st-confirmed/[0.07] to-transparent p-4" aria-labelledby="verdict-h">
      <div className="flex items-start gap-3">
        <div className="min-w-0 flex-1 overflow-hidden">
          <h2 id="verdict-h" className="flex items-center gap-1.5 text-xs font-semibold tracking-wide text-st-confirmed uppercase">
            <Crown className="size-3.5" aria-hidden /> Root cause
          </h2>
          <OpLabel op={rc.target} className="mt-1.5 text-[15px] font-semibold" />
          {v.footprint && (
            <p className="mt-1.5 text-xs text-muted-foreground">
              {v.footprint.summary} · precision {v.footprint.precision.toFixed(2)} · order {v.footprint.order.toFixed(2)}
            </p>
          )}
        </div>
        <Ring value={v.confidence} />
      </div>
      <PathChips path={v.path} onClick={() => onPath(v.path)} />
      <dl className="mt-3 space-y-1.5">
        {PARTS.filter(([k]) => typeof parts[k] === "number").map(([k, label]) => (
          <div key={k} className="grid grid-cols-[150px_1fr_36px] items-center gap-2 text-xs">
            <dt className="truncate text-muted-foreground">{label}</dt>
            <dd><Meter value={parts[k] as number} label={label} className="bg-st-confirmed/80" /></dd>
            <dd className="text-right font-mono tabular-nums">{(parts[k] as number).toFixed(2)}</dd>
          </div>
        ))}
      </dl>
      {(v.runner_up || v.second_root_cause) && (
        <div className="mt-3 space-y-1.5 border-t border-border pt-3 text-xs">
          {v.second_root_cause && (
            <p className="flex items-center gap-2">
              <span className="shrink-0 rounded bg-st-confirmed/15 px-1.5 py-0.5 font-medium text-st-confirmed">2nd cause</span>
              <OpLabel op={v.second_root_cause.target} />
            </p>
          )}
          {v.runner_up && (
            <p className="flex items-center gap-2 text-muted-foreground">
              <span className="shrink-0">Runner-up</span>
              <OpLabel op={v.runner_up.target} className="text-foreground" />
              {v.runner_up.score != null && <span className="ml-auto font-mono">{v.runner_up.score.toFixed(2)}</span>}
            </p>
          )}
        </div>
      )}
    </section>
  );
}

export function NoRootCauseCard({ n }: { n: NonNullable<S["IncidentOut"]["no_root_cause"]> }) {
  return (
    <section className="epi-in rounded-xl border border-ov-missed/35 bg-ov-missed/[0.06] p-4" aria-labelledby="nrc-h">
      <h2 id="nrc-h" className="flex items-center gap-1.5 text-xs font-semibold tracking-wide text-ov-missed uppercase">
        <CircleHelp className="size-3.5" aria-hidden /> No root cause
      </h2>
      <p className="mt-2 text-sm">{n.summary}</p>
      <p className="mt-2 text-xs text-muted-foreground">
        Checked {n.checked.length} suspects; the best explains {pct(n.max_coverage)} of the symptoms. No cause is invented.
      </p>
      <p className="mt-3 flex items-center gap-1.5 text-xs">
        <Lightbulb className="size-3.5 text-ov-missed" aria-hidden /> Check the alert threshold against the baseline.
      </p>
    </section>
  );
}

type Claim = { section: string; text: string; cites: string[]; support_p?: number | null; status?: string | null };

export function ExplanationPanel({
  explanation,
  onCite,
  activeCite,
}: {
  explanation: { claims: Claim[]; dropped: number; verified: boolean; source: string } | null | undefined;
  onCite: (id: string) => void;
  activeCite: string | null;
}) {
  if (!explanation) {
    return <p className="text-xs text-muted-foreground">The explanation is written once the verdict is in.</p>;
  }
  const sections = ["what", "where", "why"] as const;
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-1.5">
        {explanation.source === "template" ? (
          <span className="rounded-full bg-muted px-2 py-0.5 text-[11px] text-muted-foreground">AI explanation unavailable: built from the evidence</span>
        ) : explanation.verified ? (
          <span className="inline-flex items-center gap-1 rounded-full bg-st-confirmed/12 px-2 py-0.5 text-[11px] text-st-confirmed">
            <Sparkles className="size-3" aria-hidden /> GPT-4o · every claim checked by Jev
          </span>
        ) : (
          <span className="rounded-full bg-ov-missed/12 px-2 py-0.5 text-[11px] text-ov-missed">Claims not verified</span>
        )}
        {explanation.dropped > 0 && (
          <span className="rounded-full bg-muted px-2 py-0.5 text-[11px] text-muted-foreground">
            {explanation.dropped} unsupported claim{explanation.dropped > 1 ? "s" : ""} removed
          </span>
        )}
      </div>
      {sections.map((s) => {
        const claims = explanation.claims.filter((c) => c.section === s);
        if (!claims.length) return null;
        return (
          <div key={s}>
            <h3 className="mb-1 text-[11px] font-semibold tracking-wide text-muted-foreground uppercase">{s}</h3>
            <ul className="space-y-1.5">
              {claims.map((c, i) => (
                <li key={i} className="text-sm leading-relaxed">
                  {c.text}{" "}
                  {c.cites.map((id) => (
                    <button
                      key={id}
                      onClick={() => onCite(id)}
                      aria-pressed={activeCite === id}
                      className={cn(
                        "mx-0.5 rounded bg-primary/12 px-1 py-px font-mono text-[11px] text-primary ring-primary/50 hover:bg-primary/25",
                        activeCite === id && "ring-1",
                      )}
                    >
                      {id}
                    </button>
                  ))}
                  {c.status && c.status !== "verified" && explanation.source !== "template" && (
                    <span className="ml-1 text-[10px] text-muted-foreground">({c.status})</span>
                  )}
                  {c.support_p != null && (
                    <Tooltip>
                      <TooltipTrigger className="ml-1 text-[10px] text-st-confirmed">✓ {c.support_p.toFixed(2)}</TooltipTrigger>
                      <TooltipContent>Jev: probability the cited evidence supports this claim</TooltipContent>
                    </Tooltip>
                  )}
                </li>
              ))}
            </ul>
          </div>
        );
      })}
    </div>
  );
}
