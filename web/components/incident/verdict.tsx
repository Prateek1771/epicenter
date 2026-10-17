"use client";

import { ArrowRight, CircleHelp, CircleX, Clock, Crown, EyeOff, GitCommitHorizontal, Lightbulb, Sparkles, Users } from "@/components/icons";

import { Meter } from "@/components/status";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import type { S } from "@/lib/api";
import { pct, serviceColor, splitOp } from "@/lib/format";
import { ago, type RuledOut, type TMinus } from "@/lib/investigation";
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
    <div className="relative grid size-[68px] shrink-0 place-items-center" role="img" aria-label={`confidence ${pct(value)}`}>
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

/** Confidence that says what it is (Traversal defines its label; we can show the parts, research §6.2). */
function ConfidenceRing({ value, parts, weights }: { value: number; parts: number; weights: string | null | undefined }) {
  return (
    <Tooltip>
      <TooltipTrigger className="cursor-help rounded-full" aria-label="What this number means">
        <Ring value={value} />
      </TooltipTrigger>
      <TooltipContent side="left" className="max-w-[260px] text-xs leading-relaxed">
        <b>Deterministic score</b>, not a model&apos;s self-rating: {parts} weighted parts (the bars below), weights{" "}
        <span className="font-mono">{weights ?? "?"}</span>, lowered when the runner-up is close. Same input → same score,
        byte for byte.
      </TooltipContent>
    </Tooltip>
  );
}

function ms(x: number) {
  return x < 1000 ? `${x} ms` : `${(x / 1000).toFixed(x < 10_000 ? 1 : 0)} s`;
}

/** Owner · contributing change · found in Ns: the facts a responder needs next to the answer (Causely, NeuBird). */
function Facts({ v }: { v: NonNullable<S["IncidentOut"]["verdict"]> }) {
  if (!v.owner && !v.change && v.found_in_ms == null) return null;
  return (
    <div className="mt-2 flex flex-wrap gap-1.5 text-[11px]">
      {v.owner && (
        <span className="inline-flex items-center gap-1 rounded-md bg-muted px-1.5 py-0.5" title="Team that owns the root cause's service">
          <Users className="size-3 text-muted-foreground" aria-hidden /> {v.owner}
        </span>
      )}
      {v.change && (
        <span className="inline-flex max-w-full items-center gap-1 rounded-md bg-st-supported/12 px-1.5 py-0.5 text-st-supported" title={`${v.change.type} change on ${v.change.service} · ${v.change.id}`}>
          <GitCommitHorizontal className="size-3 shrink-0" aria-hidden /> <span className="truncate">{v.change.summary ?? v.change.type}</span>
        </span>
      )}
      {v.found_in_ms != null && (
        <span className="inline-flex items-center gap-1 rounded-md bg-muted px-1.5 py-0.5 text-muted-foreground" title="Diagnosis start → verdict">
          <Clock className="size-3" aria-hidden /> found in {ms(v.found_in_ms)}
        </span>
      )}
    </div>
  );
}

/** change −Nm → root onset −Ns → alert (Rootly's strip; tighter alignment is what `change_match` scores). */
export function TMinusStrip({ t }: { t: TMinus }) {
  const pts = [
    t.change && { label: t.change.label, at: `−${ago(t.change.offset)}`, cls: "bg-st-supported", text: "text-st-supported" },
    t.onset && { label: "root cause went bad", at: t.onset.offset >= 0 ? `−${ago(t.onset.offset)}` : ago(t.onset.offset), cls: "bg-st-confirmed", text: "text-st-confirmed" },
    { label: "alert", at: "0", cls: "bg-signal", text: "text-signal" },
  ].filter(Boolean) as { label: string; at: string; cls: string; text: string }[];
  if (pts.length < 2) return null;
  return (
    <div className="mt-3 rounded-lg bg-background/40 px-2.5 py-2" aria-label="Time before the alert">
      <div className="relative flex items-start justify-between">
        <span className="absolute top-[5px] right-2 left-2 h-px bg-border" aria-hidden />
        {pts.map((p, i) => (
          <span key={i} className={cn("relative flex min-w-0 flex-1 flex-col gap-0.5", i === 0 ? "items-start" : i === pts.length - 1 ? "items-end text-right" : "items-center text-center")}>
            <span className={cn("size-[11px] rounded-full ring-2 ring-card", p.cls)} aria-hidden />
            <span className={cn("font-mono text-[11px] font-semibold tabular-nums", p.text)}>{p.at}</span>
            <span className="max-w-[110px] truncate text-[10px] text-muted-foreground" title={p.label}>{p.label}</span>
          </span>
        ))}
      </div>
    </div>
  );
}

/** Every suspect that lost, with the engine's recorded reason; click to see its path (Cleric, incident.io). */
export function RuledOutList({ items, onPath }: { items: RuledOut[]; onPath: (p: string[], label: string) => void }) {
  if (!items.length) return null;
  return (
    <div className="mt-3 border-t border-border pt-3">
      <h3 className="mb-1.5 flex items-center gap-1.5 text-[11px] font-semibold tracking-wider text-muted-foreground uppercase">
        <CircleX className="size-3.5 text-st-refuted" aria-hidden /> Ruled out · {items.length}
      </h3>
      <ul className="space-y-1">
        {items.map((r) => (
          <li key={r.hyp.id}>
            <button onClick={() => onPath(r.path, `why not ${r.hyp.id}`)} className="w-full rounded-md px-1.5 py-1 text-left hover:bg-accent/50" title="Show its path on the graph">
              <span className="flex items-center gap-2 text-xs">
                <span className="w-8 shrink-0 font-mono text-muted-foreground">{r.hyp.id}</span>
                <OpLabel op={r.hyp.op} className="min-w-0 flex-1" />
                <span className={cn("shrink-0 text-[10px]", r.hyp.status === "refuted" ? "text-st-refuted" : "text-st-pruned")}>{r.hyp.status}</span>
              </span>
              <span className="mt-0.5 block pl-10 text-[11px] leading-snug text-muted-foreground">{r.reason}</span>
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}

const GAP_EFFECT: Record<string, string> = {
  traces: "call paths, per-operation latency and errors",
  metrics: "cpu and memory signals",
  logs: "log-pattern evidence",
  proxy: "the proxy's upstream timings",
};

/** Sources the window couldn't read, and what that hides (Cleric's "Access limitations"). */
export function CouldntSee({ gaps }: { gaps: string[] }) {
  if (!gaps.length) return null;
  return (
    <div className="mt-3 border-t border-border pt-3">
      <h3 className="mb-1.5 flex items-center gap-1.5 text-[11px] font-semibold tracking-wider text-ov-missed uppercase">
        <EyeOff className="size-3.5" aria-hidden /> Couldn&apos;t see
      </h3>
      <ul className="space-y-0.5 text-xs">
        {gaps.map((g) => (
          <li key={g}>
            <span className="font-mono">{g}</span>{" "}
            <span className="text-muted-foreground">: no {GAP_EFFECT[g] ?? "data from this source"}; suspects that needed it may end inconclusive</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function VerdictCard({
  v,
  onPath,
  weights,
  children,
}: {
  v: NonNullable<S["IncidentOut"]["verdict"]>;
  onPath: (p: string[]) => void;
  weights?: string | null;
  children?: React.ReactNode;
}) {
  const rc = v.root_cause;
  const parts = rc.score_parts as Record<string, number | string>;
  return (
    <section className="epi-in rounded-xl border border-st-confirmed/40 bg-carbon p-4" aria-labelledby="verdict-h">
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
          <Facts v={v} />
        </div>
        <ConfidenceRing value={v.confidence} parts={PARTS.filter(([k]) => typeof parts[k] === "number").length} weights={weights} />
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
      {children}
    </section>
  );
}

export function NoRootCauseCard({ n, children }: { n: NonNullable<S["IncidentOut"]["no_root_cause"]>; children?: React.ReactNode }) {
  return (
    <section className="epi-in rounded-xl border border-ov-missed/40 bg-carbon p-4" aria-labelledby="nrc-h">
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
      {children}
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
                        "mx-0.5 rounded bg-signal/12 px-1 py-px font-mono text-[11px] text-signal ring-signal/50 hover:bg-signal/25",
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
