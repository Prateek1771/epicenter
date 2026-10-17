"use client";

import { BookOpenCheck, FlaskConical, History, Pause, Play, RotateCcw, Save, Scales, Timer } from "@/components/icons";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { DataView } from "@/components/graph/data-view";
import { FlowGraph, type GNode, opTitle } from "@/components/graph/flow-graph";
import { useGraphMode, ViewToggle } from "@/components/graph/view-toggle";
import { OpLabel } from "@/components/incident/verdict";
import { ServicePicker } from "@/components/service-picker";
import { Meter } from "@/components/status";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { api, ApiError, call, type S } from "@/lib/api";
import { relTime } from "@/lib/format";
import { fromSimulation } from "@/lib/graph-data";
import { useEnv, useQuery, withEnv } from "@/lib/hooks";
import { cn } from "@/lib/utils";

const KINDS = ["down", "errors", "latency", "cpu", "mem", "saturation"] as const;
type Kind = (typeof KINDS)[number];
const STEP_MS = 650;

function Panel({ title, Icon, aside, className, children }: { title: string; Icon: typeof Timer; aside?: React.ReactNode; className?: string; children: React.ReactNode }) {
  return (
    <section className={cn("min-w-0 rounded-xl border border-border bg-card/40 p-4", className)}>
      <h2 className="mb-3 flex items-center gap-1.5 text-[11px] font-semibold tracking-wider text-muted-foreground uppercase">
        <Icon className="size-3.5" aria-hidden /> {title}
        {aside && <span className="ml-auto normal-case tracking-normal">{aside}</span>}
      </h2>
      {children}
    </section>
  );
}

/** One node per op: its likeliest predicted kind, in the order the failure reaches it. */
function spreadOrder(res: S["SimulateOut"]) {
  const best = new Map<string, S["SimulatedOp"]>();
  for (const p of res.predicted) if (!best.has(p.op) || p.p > best.get(p.op)!.p) best.set(p.op, p);
  return [...best.values()].sort((a, b) => a.expected_delay_s - b.expected_delay_s || a.hops - b.hops || a.op.localeCompare(b.op));
}

/** The predicted spread as a graph; Play reveals operations in expected-delay order (nobody else animates this). */
function SpreadGraph({ res }: { res: S["SimulateOut"] }) {
  const order = useMemo(() => spreadOrder(res), [res]);
  const [step, setStep] = useState<number | null>(null);
  const [playing, setPlaying] = useState(false);
  const [selected, setSelected] = useState<string | null>(null);
  useEffect(() => {
    if (!playing) return;
    const t = setInterval(() => setStep((s) => {
      const next = (s ?? 0) + 1;
      if (next >= order.length) setPlaying(false);
      return Math.min(next, order.length);
    }), STEP_MS);
    return () => clearInterval(t);
  }, [playing, order.length]);
  const shown = step ?? order.length;
  const nodes: GNode[] = order.map((p, i) => ({
    id: p.op,
    service: p.service ?? p.op.split("/")[0],
    title: opTitle(p.op),
    sub: `${p.kind} · ≤ ${p.expected_delay_s}s · ${p.owner ?? "no owner"}`,
    tone: p.hops === 0 ? "source" : null,
    badge: p.hops === 0 ? res.kind : `p ${p.p.toFixed(2)}`,
    intensity: p.hops === 0 ? undefined : p.p,
    hidden: i >= shown,
  }));
  const clock = step === null ? null : order[Math.max(0, Math.min(step, order.length) - 1)]?.expected_delay_s ?? 0;
  return (
    <div className="relative h-[460px] overflow-hidden bg-grid lg:h-[540px]">
      <FlowGraph nodes={nodes} edges={res.edges ?? []} direction="LEFT" selected={selected} onSelect={setSelected} label={`Predicted spread if ${res.target} → ${res.kind}`} />
      <div className="absolute top-3 left-3 flex items-center gap-2 rounded-lg border border-border bg-card/90 px-2 py-1.5 text-xs backdrop-blur">
        <Button size="sm" className="h-7" onClick={() => { if (step === null || step >= order.length) setStep(0); setPlaying((x) => !x); }} aria-label={playing ? "Pause" : "Play the spread"}>
          {playing ? <Pause className="size-3.5" /> : <Play className="size-3.5" />} {playing ? "Pause" : "Play"}
        </Button>
        {step !== null && (
          <button onClick={() => { setPlaying(false); setStep(null); }} className="text-muted-foreground hover:text-foreground" aria-label="Show all"><RotateCcw className="size-3.5" /></button>
        )}
        <span className="font-mono text-muted-foreground tabular-nums">
          {clock === null ? `${order.length} ops · tint = probability` : `t ≤ ${clock}s · ${Math.min(shown, order.length)}/${order.length}`}
        </span>
      </div>
    </div>
  );
}

/** Every fault kind for the same target, side by side: which failure mode hurts most, and how fast. */
function KindMatrix({ matrix, kind, onPick }: { matrix: Partial<Record<Kind, S["SimulateOut"]>>; kind: Kind; onPick: (k: Kind) => void }) {
  const maxOps = Math.max(1, ...KINDS.map((k) => matrix[k]?.counts.operations ?? 0));
  return (
    <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 xl:grid-cols-6" role="radiogroup" aria-label="Compare fault kinds">
      {KINDS.map((k) => {
        const r = matrix[k];
        const spread = r?.predicted.filter((p) => p.hops > 0) ?? [];
        const maxP = Math.max(0, ...spread.map((p) => p.p));
        const last = Math.max(0, ...spread.map((p) => p.expected_delay_s));
        return (
          <button key={k} role="radio" aria-checked={kind === k} onClick={() => onPick(k)}
            className="rounded-xl border border-border bg-card/40 p-3 text-left transition-colors hover:border-gold/40 aria-checked:border-gold/60 aria-checked:bg-gold/[0.06]">
            <p className="flex items-center justify-between text-xs"><span className="font-medium text-paper">{k}</span>{r && spread.length > 0 && <span className="font-mono text-muted-foreground">p {maxP.toFixed(2)}</span>}</p>
            {r ? (
              <>
                <p className="mt-2 font-mono text-2xl tabular-nums text-paper">{r.counts.operations}<span className="ml-1 text-xs text-muted-foreground">ops</span></p>
                <div className="mt-1.5 h-1 overflow-hidden rounded-full bg-muted"><div className="h-full bg-gradient-to-r from-gold/60 to-st-refuted" style={{ width: `${(r.counts.operations / maxOps) * 100}%` }} /></div>
                <p className="mt-1.5 text-[11px] text-muted-foreground">{r.counts.services} svc · {spread.length ? `≤ ${last}s` : "contained"}</p>
              </>
            ) : <p className="mt-2 h-14 animate-pulse rounded bg-muted/40" />}
          </button>
        );
      })}
    </div>
  );
}

/** When each service (and its team) is hit: first predicted onset per service, bar length = time, tint = probability. */
function SpreadTimeline({ res }: { res: S["SimulateOut"] }) {
  const rows = useMemo(() => {
    const m = new Map<string, { svc: string; t: number; p: number; ops: number; owner: string | null }>();
    for (const p of res.predicted) {
      const svc = p.service ?? p.op.split("/")[0];
      const r = m.get(svc) ?? { svc, t: Infinity, p: 0, ops: 0, owner: p.owner };
      m.set(svc, { ...r, t: Math.min(r.t, p.expected_delay_s), p: Math.max(r.p, p.p), ops: r.ops + 1 });
    }
    return [...m.values()].sort((a, b) => a.t - b.t || a.svc.localeCompare(b.svc));
  }, [res]);
  const tMax = Math.max(1, ...rows.map((r) => r.t));
  return (
    <ul className="space-y-1.5">
      {rows.map((r) => (
        <li key={r.svc} className="grid grid-cols-[minmax(0,120px)_1fr_48px] items-center gap-2 text-xs sm:grid-cols-[minmax(0,160px)_1fr_56px]">
          <span className="min-w-0" title={`${r.svc} · ${r.ops} ops`}>
            <span className="block truncate font-mono">{r.svc}</span>
            <span className="block truncate text-[10px] text-muted-foreground">{r.owner ?? "no owner"}</span>
          </span>
          <span className="relative h-3 rounded bg-muted/40">
            <span className="absolute inset-y-0 left-0 rounded bg-st-refuted" style={{ width: `max(4px, ${(r.t / tMax) * 100}%)`, opacity: 0.25 + 0.75 * r.p }} />
          </span>
          <span className="text-right font-mono tabular-nums text-muted-foreground">{r.t === 0 ? "t0" : `${r.t}s`}</span>
        </li>
      ))}
    </ul>
  );
}

/** "Did it happen before?": the prediction against each past incident rooted at the target. */
function Precedents({ env, target, kind }: { env: string | null; target: string; kind: Kind }) {
  const body = target.includes("/") ? { operation: target, kind, save: false } : { service: target, kind, save: false };
  const q = useQuery(`cmp:${env}:${target}:${kind}`, () => call(api.POST("/api/v1/simulate/compare", { params: { query: { env: env ?? undefined } }, body })));
  if (q.loading && !q.data) return <p className="text-xs text-muted-foreground">Matching against past incidents…</p>;
  if (!q.data?.items.length) return <p className="text-xs text-muted-foreground">No incident has been rooted at {target.split("/")[0]} yet, so there is nothing to compare with.</p>;
  return (
    <ul className="space-y-3">
      {q.data.items.map((r) => (
        <li key={r.incident} className="text-xs">
          <p className="flex items-center gap-2">
            <Link href={withEnv(`/incident/${encodeURIComponent(r.incident)}`, env)} className="truncate font-mono hover:text-gold">{r.incident}</Link>
            <span className="ml-auto shrink-0 font-mono tabular-nums text-paper">{Math.round(r.footprint * 100)}%</span>
          </p>
          <Meter value={r.coverage} label="coverage" className={cn("mt-1", r.coverage >= 0.8 ? "bg-st-confirmed" : r.coverage >= 0.5 ? "bg-gold" : "bg-st-refuted")} />
          <p className="mt-1 text-muted-foreground">
            {r.explains}{r.unexplained.length > 0 && <> · not explained: <span className="font-mono">{r.unexplained.map(opTitle).join(", ")}</span></>}
          </p>
        </li>
      ))}
    </ul>
  );
}

/** The propagation rules behind this prediction: why each hop is there. */
function RulesUsed({ kind, predicted, svcKind }: { kind: Kind; predicted: S["SimulatedOp"][]; svcKind: string | null }) {
  const rules = useQuery("rules", () => call(api.GET("/api/v1/rules"))).data?.items ?? [];
  const kinds = new Set(predicted.map((p) => p.kind));
  const used = rules.filter((r) => r.cause_kinds.includes(kind) && kinds.has(r.symptom_kind) && (!r.service_kind || r.service_kind === svcKind));
  if (!used.length) return <p className="text-xs text-muted-foreground">No rule fires for {kind}.</p>;
  return (
    <ul className="divide-y divide-border/60 text-xs">
      {used.map((r) => (
        <li key={r.id} className="grid grid-cols-[1fr_auto] gap-x-3 py-1.5">
          <span className="truncate font-mono">{r.id}</span>
          <span className="font-mono tabular-nums text-muted-foreground">p {r.p.toFixed(2)} · ≤ {r.delay_s_max}s</span>
          <span className="col-span-2 text-muted-foreground">
            {kind} → {r.symptom_kind}, {r.direction === "self" ? "on itself" : "on its callers"}
            {r.service_kind && <> · if it is a {r.service_kind}</>}{r.caller_kind && <> · callers that are {r.caller_kind}</>}
          </span>
        </li>
      ))}
    </ul>
  );
}

function Saved({ env, onOpen }: { env: string | null; onOpen: (target: string, kind: Kind) => void }) {
  const sims = useQuery(`sims:${env}`, () => call(api.GET("/api/v1/simulations", { params: { query: { env: env ?? undefined, limit: 12 } } })));
  if (!sims.data?.items.length) return <p className="text-xs text-muted-foreground">Nothing saved. Turn on “save” to keep a prediction: a later incident is compared with it.</p>;
  return (
    <ul className="space-y-1">
      {sims.data.items.map((s) => (
        <li key={s.id}>
          <button onClick={() => onOpen(s.target, s.kind as Kind)} className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-xs hover:bg-accent">
            <span className="truncate font-mono">{s.target}</span>
            <span className="rounded bg-st-refuted/12 px-1.5 text-[10px] text-st-refuted">{s.kind}</span>
            <span className="ml-auto shrink-0 text-muted-foreground">{s.operations} ops · {relTime(new Date(s.ts * 1000).toISOString())}</span>
          </button>
        </li>
      ))}
    </ul>
  );
}

export default function SimulatePage() {
  const [env] = useEnv();
  const params = useSearchParams();
  const router = useRouter();
  const [kind, setKind] = useState<Kind>(KINDS.includes(params.get("kind") as Kind) ? (params.get("kind") as Kind) : "down");
  const [save, setSave] = useState(false);
  const [busy, setBusy] = useState(false);
  const [target, setTarget] = useState<string | null>(null);
  const [matrix, setMatrix] = useState<Partial<Record<Kind, S["SimulateOut"]>>>({});
  const [err, setErr] = useState<string | null>(null);
  const [mode, setMode] = useGraphMode();
  const [savedKey, setSavedKey] = useState(0);
  const svcs = useQuery(`svc:${env}`, () => call(api.GET("/api/v1/services", { params: { query: { env: env ?? undefined } } })));
  const res = matrix[kind] ?? null;

  const pickKind = (k: Kind) => {
    setKind(k);
    if (target) router.replace(withEnv(`/simulate?service=${encodeURIComponent(target)}&kind=${k}`, env), { scroll: false });
  };

  // one target, every kind at once (the selected one saved if asked): the matrix is the comparison
  const run = async (t: string, k: Kind = kind) => {
    setBusy(true);
    setErr(null);
    setKind(k);
    setTarget(t);
    setMatrix({});
    router.replace(withEnv(`/simulate?service=${encodeURIComponent(t)}&kind=${k}`, env), { scroll: false });
    const one = async (x: Kind) => {
      const body = t.includes("/") ? { operation: t, kind: x, save: save && x === k } : { service: t, kind: x, save: save && x === k };
      const out = await call(api.POST("/api/v1/simulate", { params: { query: { env: env ?? undefined } }, body }));
      setMatrix((m) => ({ ...m, [x]: out }));
      if (out.simulation_id) {
        toast.success("Simulation saved", { description: `${out.simulation_id}: a later incident can be compared with it.` });
        setSavedKey((n) => n + 1);
      }
    };
    try {
      await one(k); // the chosen kind first, so the main view is never waiting on the others
      await Promise.all(KINDS.filter((x) => x !== k).map(one));
    } catch (e) {
      setErr(e instanceof ApiError ? (e.code === "SERVICE_NOT_FOUND" ? `No service or operation “${t}”.` : e.message) : String(e));
    } finally {
      setBusy(false);
    }
  };

  const service = params.get("service");
  useEffect(() => {
    if (service && !target) void run(service);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- run once for a deep link
  }, [service]);

  return (
    <main className="mx-auto w-full max-w-[1500px] px-4 py-8 lg:px-6">
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="flex items-center gap-2 text-3xl"><FlaskConical className="size-6 text-fog" aria-hidden /> What-if lab</h1>
        {res && <ViewToggle mode={mode} onChange={setMode} className="ml-auto" />}
      </div>
      <p className="mt-1 mb-6 text-sm text-muted-foreground">
        Run the Fault Simulator with no incident: break a service six ways, watch the spread in time, and check it against what really happened before.
      </p>
      <ServicePicker key={service ?? ""} initial={service ?? ""} suggestions={(svcs.data?.items ?? []).map((s) => s.name)} busy={busy} label="Run experiment" onPick={(t) => run(t)}>
        <div className="flex flex-wrap gap-1" role="radiogroup" aria-label="Failure kind">
          {KINDS.map((k) => (
            <button key={k} type="button" role="radio" aria-checked={kind === k} onClick={() => pickKind(k)}
              className="rounded-md border border-border px-2.5 py-1.5 text-xs text-fog hover:text-mist aria-checked:border-gold/50 aria-checked:bg-gold/10 aria-checked:text-gold">
              {k}
            </button>
          ))}
        </div>
        <Label className="flex items-center gap-1.5 text-xs text-muted-foreground">
          <Switch checked={save} onCheckedChange={setSave} /> <Save className="size-3.5" aria-hidden /> save
        </Label>
      </ServicePicker>
      {err && <p className="mt-6 text-sm text-st-refuted">{err}</p>}

      {!target && (
        <div className="mt-8 grid gap-4 lg:grid-cols-2">
          <Panel title="Saved experiments" Icon={History}><Saved key={savedKey} env={env} onOpen={(t, k) => run(t, k)} /></Panel>
          <Panel title="How it predicts" Icon={BookOpenCheck}>
            <p className="text-xs leading-relaxed text-muted-foreground">
              Each hop comes from a versioned propagation rule (seed/propagation_rules.yaml): a fault kind on a service causes a symptom on itself or its callers, with a probability and a maximum delay. Probabilities multiply along call paths and weak branches are cut. The same simulator checks every suspect during a diagnosis.
            </p>
          </Panel>
        </div>
      )}

      {target && (
        <div className="mt-6 space-y-4">
          <KindMatrix matrix={matrix} kind={kind} onPick={pickKind} />

          {res && (
            <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_380px]">
              <section className="min-w-0 overflow-hidden rounded-xl border border-border bg-card/40">
                <header className="flex flex-wrap items-center gap-x-4 gap-y-1 border-b border-border px-4 py-3 text-sm">
                  <span>If <span className="font-mono text-paper">{res.target}</span> → <span className="text-st-refuted">{res.kind}</span>:</span>
                  <span className="text-muted-foreground">{res.counts.operations} operations in {res.counts.services} services · rules {res.rules_version}</span>
                </header>
                {res.predicted.length === 0 ? (
                  <p className="px-4 py-16 text-center text-sm text-muted-foreground">Nothing with traffic depends on it: the failure stays contained.</p>
                ) : mode === "graph" ? (
                  <SpreadGraph key={`${res.target}:${res.kind}`} res={res} />
                ) : (
                  <>
                    <div className="p-3"><DataView data={fromSimulation(res)} name={`what-if-${res.target}-${res.kind}`} className="max-h-[420px]" /></div>
                    <ol className="divide-y divide-border/60 border-t border-border">
                      {res.predicted.map((p, i) => (
                        <li key={`${p.op}:${p.kind}`} className="grid grid-cols-[28px_1fr_80px] items-center gap-3 px-4 py-2 text-sm md:grid-cols-[28px_minmax(0,1fr)_80px_140px_90px_120px]">
                          <span className="font-mono text-xs text-muted-foreground">{i + 1}</span>
                          <OpLabel op={p.op} />
                          <span className="rounded bg-st-refuted/12 px-1.5 py-0.5 text-center text-xs text-st-refuted">{p.kind}</span>
                          <span className="hidden items-center gap-2 md:flex">
                            <Meter value={p.p} label="probability" className={p.p > 0.7 ? "bg-st-refuted" : p.p > 0.4 ? "bg-ov-missed" : "bg-muted-foreground"} />
                            <span className="w-9 font-mono text-xs tabular-nums">{p.p.toFixed(2)}</span>
                          </span>
                          <span className="hidden text-xs text-muted-foreground md:block">≤ {p.expected_delay_s}s · {p.hops} hop{p.hops === 1 ? "" : "s"}</span>
                          <span className="hidden truncate text-xs text-muted-foreground md:block">{p.owner ?? "no owner"}</span>
                        </li>
                      ))}
                    </ol>
                  </>
                )}
              </section>
              <div className="space-y-4">
                <Panel title="Spread timeline" Icon={Timer} aside={<span className="text-muted-foreground">when each team is hit</span>}>
                  {res.predicted.length ? <SpreadTimeline res={res} /> : <p className="text-xs text-muted-foreground">Contained.</p>}
                </Panel>
                <Panel title="Did it happen before?" Icon={Scales}><Precedents env={env} target={res.target} kind={kind} /></Panel>
              </div>
            </div>
          )}

          {res && (
            <div className="grid gap-4 lg:grid-cols-2">
              <Panel title="Rules behind it" Icon={BookOpenCheck} aside={<span className="font-mono text-muted-foreground">{res.rules_version}</span>}><RulesUsed kind={kind} predicted={res.predicted} svcKind={svcs.data?.items.find((s) => s.name === res.target.split("/")[0])?.kind ?? null} /></Panel>
              <Panel title="Saved experiments" Icon={History}><Saved key={savedKey} env={env} onOpen={(t, k) => run(t, k)} /></Panel>
            </div>
          )}
        </div>
      )}
    </main>
  );
}
