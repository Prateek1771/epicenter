"use client";

import { ChevronDown, Gauge } from "@/components/icons";
import { Fragment, useMemo, useState } from "react";

import { ComingSoon } from "@/components/coming-soon";
import { Skeleton } from "@/components/ui/skeleton";
import { api, call, type S } from "@/lib/api";
import { pct } from "@/lib/format";
import { useQuery } from "@/lib/hooks";
import { cn } from "@/lib/utils";

type Case = S["EvalCase"];
const td = "px-3 py-2";
const PARTS = ["pagerank", "onset_earliness", "strength", "mechanism_fit", "footprint", "change_match", "refuted"];
const mean = (xs: number[]) => (xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : 0);

function Card({ title, note, className, children }: { title: string; note?: React.ReactNode; className?: string; children: React.ReactNode }) {
  return (
    <section className={cn("min-w-0 rounded-xl border border-border bg-card/40 p-4", className)}>
      <h2 className="text-[11px] font-semibold tracking-wider text-muted-foreground uppercase">{title}</h2>
      {note && <p className="mt-1 text-xs text-muted-foreground">{note}</p>}
      <div className="mt-3">{children}</div>
    </section>
  );
}

function Kpi({ k, v, sub }: { k: string; v: string; sub?: string }) {
  return (
    <div className="rounded-xl border border-border bg-card/40 p-4">
      <div className="text-[11px] text-muted-foreground">{k}</div>
      <div className="mt-1 font-[family-name:var(--font-display)] text-4xl text-paper italic tabular-nums">{v}</div>
      {sub && <div className="mt-0.5 text-[11px] text-muted-foreground">{sub}</div>}
    </div>
  );
}

/** AC@1 and AC@3 across every stored run: what each weights version bought. */
function History({ runs }: { runs: S["EvalRun"][] }) {
  const W = 600, H = 160, P = 28;
  const x = (i: number) => P + (i * (W - 2 * P)) / Math.max(1, runs.length - 1);
  const y = (v: number | null) => H - P - (v ?? 0) * (H - 2 * P);
  const line = (k: "ac1" | "ac3") => runs.map((r, i) => `${x(i)},${y(r[k])}`).join(" ");
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label="AC@1 and AC@3 per eval run">
      {[0, 0.5, 1].map((g) => (
        <g key={g}>
          <line x1={P} x2={W - P} y1={y(g)} y2={y(g)} stroke="var(--color-graphite)" strokeDasharray="2 4" />
          <text x={4} y={y(g) + 3} fontSize="9" fill="var(--color-ash)">{g * 100}%</text>
        </g>
      ))}
      <polyline points={line("ac3")} fill="none" stroke="var(--color-fog)" strokeWidth="1.5" strokeDasharray="4 3" />
      <polyline points={line("ac1")} fill="none" stroke="var(--color-gold)" strokeWidth="2" />
      {runs.map((r, i) => (
        <g key={r.run}>
          <circle cx={x(i)} cy={y(r.ac1)} r="3.5" fill="var(--color-gold)"><title>{`${r.run}: AC@1 ${pct(r.ac1, 1)}, AC@3 ${pct(r.ac3, 1)}`}</title></circle>
          <text x={x(i)} y={H - 8} fontSize="9" textAnchor="middle" fill="var(--color-ash)">{r.weights_version?.split(".").at(-1) ?? "?"}·{r.run.slice(0, 4)}</text>
        </g>
      ))}
    </svg>
  );
}

function Bar({ v, max = 1, className }: { v: number; max?: number; className?: string }) {
  return <span className="block h-2 overflow-hidden rounded-full bg-muted"><span className={cn("block h-full rounded-full", className ?? "bg-gold")} style={{ width: `${Math.max(0, Math.min(1, v / max)) * 100}%` }} /></span>;
}

export default function EvalPage() {
  const e = useQuery("eval", () => call(api.GET("/api/v1/eval")));
  const d = e.data;
  const [missesOnly, setMissesOnly] = useState(false);
  const [open, setOpen] = useState<string | null>(null);
  const cases = useMemo(() => d?.per_case ?? [], [d]);
  const rows = cases.filter((c) => !missesOnly || !c.hit1);

  const a = useMemo(() => {
    const hits = cases.filter((c) => c.hit1), misses = cases.filter((c) => !c.hit1);
    const parts = PARTS.map((p) => ({ p, hit: mean(hits.map((c) => c.parts[p] ?? 0)), miss: mean(misses.map((c) => c.parts[p] ?? 0)) }));
    const buckets = [0, 0.2, 0.4, 0.6, 0.8].map((lo) => {
      const inB = cases.filter((c) => c.confidence != null && c.confidence >= lo && (c.confidence < lo + 0.2 || (lo === 0.8 && c.confidence <= 1)));
      return { lo, n: inB.length, rate: inB.length ? inB.filter((c) => c.hit1).length / inB.length : null };
    });
    const blamed = new Map<string, Case[]>();
    for (const c of misses) {
      const k = c.top3[0] ?? "no root cause";
      blamed.set(k, [...(blamed.get(k) ?? []), c]);
    }
    const ms = cases.map((c) => c.diagnose_ms).filter((x): x is number => x != null);
    const edges = [0, 100, 150, 200, 300, 500, 1000, Infinity];
    const hist = edges.slice(0, -1).map((lo, i) => ({ lo, hi: edges[i + 1], n: ms.filter((m) => m >= lo && m < edges[i + 1]).length }));
    return { parts, buckets, blamed: [...blamed.entries()].sort((x, y) => y[1].length - x[1].length || x[0].localeCompare(y[0])), hist, ms };
  }, [cases]);

  const history = (d?.history ?? []).filter((r) => r.cases > 1);
  const synth = d?.synth as { run: string; seed?: number; by_size: Record<string, { ac1: number | null; ac3: number | null; cases: number }> } | null | undefined;

  return (
    <main className="mx-auto w-full max-w-[1300px] px-4 py-8 lg:px-6">
      <h1 className="flex items-center gap-2 text-3xl"><Gauge className="size-6 text-fog" aria-hidden /> Eval</h1>
      <p className="mt-1 text-sm text-muted-foreground">
        How often the verdict is right on the RCAEval benchmark, what each feature is worth, where it fails, and whether its confidence means anything. Weights are tuned on reps 1–2 only; rep 3 is held out.
      </p>
      {e.loading && <Skeleton className="mt-6 h-40 w-full rounded-xl" />}
      {!e.loading && !d && <ComingSoon phase={10} what="Run python -m api.eval --suite re2 --system tt to replay every RE2 case and score the verdicts." endpoint="GET /eval" />}
      {d && (
        <>
          <p className="mt-6 font-mono text-xs text-muted-foreground">RE2-{d.system.toUpperCase()} · {d.cases} cases · weights {d.weights_version} · rules {d.rules_version} · {d.run}</p>

          <div className="mt-3 grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-5">
            <Kpi k="AC@1 · all" v={pct(d.ac1, 1)} sub={`AC@3 ${pct(d.ac3, 1)}`} />
            <Kpi k="AC@1 · held-out" v={pct(d.split.test?.ac1 ?? null, 1)} sub={`${d.split.test?.cases ?? 0} cases never tuned on`} />
            <Kpi k="AC@1 · dev" v={pct(d.split.dev?.ac1 ?? null, 1)} sub={`${d.split.dev?.cases ?? 0} cases`} />
            <Kpi k="Alert → verdict p95" v={d.n1_ms?.p95 != null ? `${(d.n1_ms.p95 / 1000).toFixed(1)}s` : "—"} sub="replay excluded" />
            <Kpi k="Memory P@3" v={pct(d.memory.p_at_3, 1)} sub="similar past incidents" />
          </div>

          <div className="mt-4 grid gap-4 lg:grid-cols-3">
            <Card title="Run history" note="AC@1 (gold) and AC@3 (dashed) for every stored run, labelled by weights version." className="lg:col-span-2">
              {history.length > 1 ? <History runs={history} /> : <p className="text-xs text-muted-foreground">One run so far.</p>}
            </Card>
            <Card title="What each feature is worth" note="AC@1 change when one feature is switched off (points vs. the full scorer).">
              <ul className="space-y-2.5">
                {Object.entries(d.ablations).map(([k, v]) => {
                  const delta = ((v.ac1 ?? 0) - (d.ac1 ?? 0)) * 100;
                  return (
                    <li key={k} className="grid grid-cols-[96px_1fr_52px] items-center gap-2 text-xs">
                      <span className="truncate text-muted-foreground">{k.replace("no_", "− ")}</span>
                      <span className="relative h-3">
                        <span className="absolute inset-y-0 left-1/2 w-px bg-border" />
                        <span className={cn("absolute inset-y-0.5 rounded", delta < 0 ? "right-1/2 bg-st-refuted" : "left-1/2 bg-st-confirmed")} style={{ width: `${Math.min(50, Math.abs(delta) * 2)}%` }} />
                      </span>
                      <span className={cn("text-right font-mono tabular-nums", delta < 0 ? "text-st-refuted" : "text-st-confirmed")}>{delta > 0 ? "+" : ""}{delta.toFixed(1)}</span>
                    </li>
                  );
                })}
              </ul>
              {Object.entries(d.ablations).some(([, v]) => (v.ac1 ?? 0) > (d.ac1 ?? 0)) && (
                <p className="mt-3 text-[11px] text-ov-missed">A positive bar means the scorer does better without that feature on this suite: shown, not hidden.</p>
              )}
            </Card>
          </div>

          <div className="mt-4 grid gap-4 md:grid-cols-2 lg:grid-cols-3">
            <Card title="By fault kind" note="AC@1 per injected fault.">
              <ul className="space-y-2">
                {Object.entries(d.by_fault).map(([k, v]) => (
                  <li key={k} className="grid grid-cols-[56px_1fr_48px] items-center gap-2 text-xs">
                    <span className="font-mono">{k}</span><Bar v={Number(v.ac1 ?? 0)} className={Number(v.ac1 ?? 0) < 0.8 ? "bg-ov-missed" : "bg-gold"} /><span className="text-right font-mono tabular-nums">{pct(v.ac1 as number, 0)}</span>
                  </li>
                ))}
              </ul>
            </Card>
            <Card title="Is the confidence honest?" note="Verdict confidence bucket → how often it was right.">
              <ul className="space-y-2">
                {a.buckets.map((b) => (
                  <li key={b.lo} className="grid grid-cols-[64px_1fr_72px] items-center gap-2 text-xs">
                    <span className="font-mono text-muted-foreground">{b.lo.toFixed(1)}–{(b.lo + 0.2).toFixed(1)}</span>
                    <Bar v={b.rate ?? 0} className="bg-st-confirmed/80" />
                    <span className="text-right font-mono tabular-nums">{b.rate == null ? "—" : pct(b.rate, 0)} <span className="text-muted-foreground">n{b.n}</span></span>
                  </li>
                ))}
              </ul>
            </Card>
            <Card title="Synthetic scale test" note={synth ? `Generated systems, seed ${synth.seed ?? "?"}: does accuracy hold as the graph grows?` : undefined}>
              {synth ? (
                <ul className="space-y-2.5">
                  {["small", "medium", "huge"].filter((s) => synth.by_size[s]).map((s) => (
                    <li key={s} className="text-xs">
                      <p className="flex justify-between"><span>{s} <span className="text-muted-foreground">· {synth.by_size[s].cases} cases</span></span><span className="font-mono tabular-nums">{pct(synth.by_size[s].ac1, 0)} <span className="text-muted-foreground">@3 {pct(synth.by_size[s].ac3, 0)}</span></span></p>
                      <Bar v={synth.by_size[s].ac1 ?? 0} className="mt-1 bg-gold" />
                    </li>
                  ))}
                </ul>
              ) : <p className="text-xs text-muted-foreground">Run python -m api.eval --suite synth.</p>}
            </Card>
            <Card title="What decides a hit" note="Mean score parts of the verdict: hits (gold) vs misses (red).">
              <ul className="space-y-2">
                {a.parts.map(({ p, hit, miss }) => (
                  <li key={p} className="grid grid-cols-[104px_1fr] items-center gap-2 text-xs">
                    <span className="truncate text-muted-foreground">{p.replaceAll("_", " ")}</span>
                    <span className="space-y-0.5" title={`hits ${hit.toFixed(2)} · misses ${miss.toFixed(2)}`}><Bar v={hit} /><Bar v={miss} className="bg-st-refuted/80" /></span>
                  </li>
                ))}
              </ul>
            </Card>
            <Card title="Where misses go" note="The service we blamed when the verdict was wrong.">
              {a.blamed.length ? (
                <ul className="space-y-2">
                  {a.blamed.slice(0, 7).map(([svc, cs]) => (
                    <li key={svc} className="text-xs">
                      <p className="flex justify-between gap-2"><span className="truncate font-mono">{svc}</span><span className="shrink-0 font-mono text-st-refuted">{cs.length}</span></p>
                      <p className="truncate text-[11px] text-muted-foreground">instead of {[...new Set(cs.map((c) => `${c.service} (${c.fault})`))].join(", ")}</p>
                    </li>
                  ))}
                </ul>
              ) : <p className="text-xs text-st-confirmed">No misses.</p>}
            </Card>
            <Card title="Time to verdict" note={a.ms.length ? `Per case, diagnosis only. median ${Math.round([...a.ms].sort((x, y) => x - y)[Math.floor(a.ms.length / 2)])} ms.` : undefined}>
              <div className="flex h-28 items-end gap-1.5">
                {a.hist.map((h) => (
                  <div key={h.lo} className="flex flex-1 flex-col items-center gap-1">
                    <span className="font-mono text-[10px] text-muted-foreground">{h.n || ""}</span>
                    <span className="w-full rounded-t bg-gold/70" style={{ height: `${(h.n / Math.max(1, ...a.hist.map((x) => x.n))) * 80}px` }} />
                    <span className="font-mono text-[9px] text-muted-foreground">{h.hi === Infinity ? `${h.lo}+` : `<${h.hi}`}</span>
                  </div>
                ))}
              </div>
              <dl className="mt-3 grid grid-cols-2 gap-x-3 gap-y-1 border-t border-border pt-2 text-[11px]">
                {Object.entries(d.n2_p95_ms ?? {}).map(([q, ms]) => (
                  <div key={q} className="flex justify-between"><dt className="text-muted-foreground">{q} p95</dt><dd className="font-mono tabular-nums">{ms} ms</dd></div>
                ))}
              </dl>
            </Card>
          </div>

          {cases.length > 0 && (
            <section className="mt-8" aria-labelledby="per-case">
              <div className="flex flex-wrap items-center gap-3">
                <h2 id="per-case" className="text-base font-medium">Every case</h2>
                <span className="text-xs text-muted-foreground">{cases.filter((c) => !c.hit1).length} misses at @1, shown, not hidden · click a row for the detail</span>
                <div role="radiogroup" aria-label="Filter cases" className="ml-auto inline-flex rounded-lg border border-border p-0.5">
                  {([false, true] as const).map((m) => (
                    <button key={String(m)} role="radio" aria-checked={missesOnly === m} onClick={() => setMissesOnly(m)} className="rounded-md px-2.5 py-1 text-xs text-muted-foreground aria-checked:bg-accent aria-checked:text-foreground">
                      {m ? "Misses" : "All"}
                    </button>
                  ))}
                </div>
              </div>
              <div className="mt-3 overflow-x-auto rounded-xl border border-border">
                <table className="w-full min-w-[720px] text-sm">
                  <thead className="bg-card/60 text-left text-xs text-muted-foreground uppercase">
                    <tr><th className={td}>Case</th><th className={td}>Split</th><th className={td}>Label</th><th className={td}>Our top 3</th><th className={td}>Conf.</th><th className={td}>@1</th><th className={td}>@3</th><th className="w-8" /></tr>
                  </thead>
                  <tbody>
                    {rows.map((c) => (
                      <Fragment key={c.case}>
                        <tr className="cursor-pointer border-t border-border hover:bg-accent/40" onClick={() => setOpen(open === c.case ? null : c.case)} aria-expanded={open === c.case}>
                          <td className={`${td} font-mono text-xs`}>{c.case}</td>
                          <td className={`${td} text-xs text-muted-foreground`}>{c.split === "test" ? "held-out" : c.split ?? "—"}</td>
                          <td className={`${td} font-mono text-xs`}>{c.service} · {c.fault}</td>
                          <td className={`${td} font-mono text-xs`}>
                            {c.top3.length ? c.top3.map((s, i) => <span key={s} className={s === c.service ? "text-st-confirmed" : undefined}>{i ? ", " : ""}{s}</span>) : <span className="text-muted-foreground">no root cause</span>}
                          </td>
                          <td className={`${td} font-mono text-xs tabular-nums`}>{c.confidence != null ? c.confidence.toFixed(2) : "—"}</td>
                          <td className={td}><span className={c.hit1 ? "text-st-confirmed" : "text-st-refuted"}>{c.hit1 ? "hit" : "miss"}</span></td>
                          <td className={td}><span className={c.hit3 ? "text-st-confirmed" : "text-st-refuted"}>{c.hit3 ? "hit" : "miss"}</span></td>
                          <td className="pr-3"><ChevronDown className={cn("size-3.5 text-muted-foreground transition-transform", open === c.case && "rotate-180")} /></td>
                        </tr>
                        {open === c.case && (
                          <tr className="bg-card/30">
                            <td colSpan={8} className="px-3 py-3">
                              <div className="grid gap-4 text-xs md:grid-cols-3">
                                <div>
                                  <p className="mb-1 text-[11px] text-muted-foreground uppercase">With one feature off, top-1</p>
                                  {Object.entries(c.variants).map(([k, s]) => (
                                    <p key={k} className="flex justify-between gap-2"><span className="text-muted-foreground">{k.replace("no_", "− ")}</span><span className={cn("truncate font-mono", s === c.service ? "text-st-confirmed" : "text-st-refuted")}>{s ?? "none"}</span></p>
                                  ))}
                                </div>
                                <div>
                                  <p className="mb-1 text-[11px] text-muted-foreground uppercase">Verdict score parts</p>
                                  {Object.entries(c.parts).map(([k, v]) => (
                                    <p key={k} className="grid grid-cols-[110px_1fr_40px] items-center gap-2"><span className="text-muted-foreground">{k.replaceAll("_", " ")}</span><Bar v={v} className={k === "refuted" ? "bg-st-refuted" : "bg-gold"} /><span className="text-right font-mono">{v.toFixed(2)}</span></p>
                                  ))}
                                </div>
                                <div>
                                  <p className="mb-1 text-[11px] text-muted-foreground uppercase">Run</p>
                                  <p>confidence <span className="font-mono">{c.confidence?.toFixed(3) ?? "—"}</span></p>
                                  <p>diagnosis <span className="font-mono">{c.diagnose_ms != null ? `${c.diagnose_ms} ms` : "—"}</span></p>
                                  <p className="mt-2 text-muted-foreground">Replay it: <code className="font-mono text-foreground">python -m api.ingest.rcaeval --case {c.case}</code></p>
                                </div>
                              </div>
                            </td>
                          </tr>
                        )}
                      </Fragment>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          )}
        </>
      )}
    </main>
  );
}
