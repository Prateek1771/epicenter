"use client";

import { FlaskConical, Pause, Play, RotateCcw, Save } from "@/components/icons";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { DataView } from "@/components/graph/data-view";
import { FlowGraph, type GNode, opTitle } from "@/components/graph/flow-graph";
import { useGraphMode, ViewToggle } from "@/components/graph/view-toggle";
import { OpLabel } from "@/components/incident/verdict";
import { ServicePicker } from "@/components/service-picker";
import { Meter } from "@/components/status";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Button } from "@/components/ui/button";
import { api, ApiError, call, type S } from "@/lib/api";
import { fromSimulation } from "@/lib/graph-data";
import { useEnv, useQuery, withEnv } from "@/lib/hooks";

const KINDS = ["down", "errors", "latency", "cpu", "mem", "saturation"] as const;
const STEP_MS = 650;

/** The predicted spread as a graph; Play reveals operations in expected-delay order (nobody else animates this). */
function SpreadGraph({ res }: { res: S["SimulateOut"] }) {
  const order = useMemo(() => {
    const best = new Map<string, S["SimulatedOp"]>(); // one node per op: its likeliest predicted kind
    for (const p of res.predicted) if (!best.has(p.op) || p.p > best.get(p.op)!.p) best.set(p.op, p);
    return [...best.values()].sort((a, b) => a.expected_delay_s - b.expected_delay_s || a.hops - b.hops || a.op.localeCompare(b.op));
  }, [res]);
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
    <div className="relative h-[620px] overflow-hidden border-t border-border bg-grid">
      <FlowGraph nodes={nodes} edges={res.edges ?? []} direction="LEFT" selected={selected} onSelect={setSelected} label={`Predicted spread if ${res.target} → ${res.kind}`} />
      <div className="absolute top-3 left-3 flex items-center gap-2 rounded-lg border border-border bg-card/90 px-2 py-1.5 text-xs backdrop-blur">
        <Button size="sm" className="h-7" onClick={() => { if (step === null || step >= order.length) setStep(0); setPlaying((x) => !x); }} aria-label={playing ? "Pause" : "Play the spread"}>
          {playing ? <Pause className="size-3.5" /> : <Play className="size-3.5" />} {playing ? "Pause" : "Play"}
        </Button>
        {step !== null && (
          <button onClick={() => { setPlaying(false); setStep(null); }} className="text-muted-foreground hover:text-foreground" aria-label="Show all"><RotateCcw className="size-3.5" /></button>
        )}
        <span className="font-mono text-muted-foreground tabular-nums">
          {clock === null ? `${order.length} ops · card tint = probability` : `t ≤ ${clock}s · ${Math.min(shown, order.length)}/${order.length}`}
        </span>
      </div>
    </div>
  );
}

export default function SimulatePage() {
  const [env] = useEnv();
  const params = useSearchParams();
  const router = useRouter();
  const [kind, setKind] = useState<(typeof KINDS)[number]>((params.get("kind") as never) ?? "down");
  const [save, setSave] = useState(false);
  const [busy, setBusy] = useState(false);
  const [res, setRes] = useState<S["SimulateOut"] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [mode, setMode] = useGraphMode();
  const svcs = useQuery(`svc:${env}`, () => call(api.GET("/api/v1/services", { params: { query: { env: env ?? undefined } } })));

  const run = async (target: string) => {
    setBusy(true);
    setErr(null);
    router.replace(withEnv(`/simulate?service=${encodeURIComponent(target)}&kind=${kind}`, env));
    try {
      const body = target.includes("/") ? { operation: target, kind, save } : { service: target, kind, save };
      const out = await call(api.POST("/api/v1/simulate", { params: { query: { env: env ?? undefined } }, body }));
      setRes(out);
      if (out.simulation_id) toast.success("Simulation saved", { description: `${out.simulation_id}: a later incident can be compared with it.` });
    } catch (e) {
      setErr(e instanceof ApiError ? (e.code === "SERVICE_NOT_FOUND" ? `No service or operation “${target}”.` : e.message) : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className={`mx-auto w-full ${res && mode === "graph" ? "max-w-[1600px]" : "max-w-[1200px]"} px-4 py-8 lg:px-6`}>
      <h1 className="flex items-center gap-2 text-2xl font-medium tracking-[-0.012em]">
        <FlaskConical className="size-6 text-fog" aria-hidden /> What-if
        {res && <ViewToggle mode={mode} onChange={setMode} className="ml-auto" />}
      </h1>
      <p className="mt-1 mb-6 text-sm text-muted-foreground">
        The Fault Simulator, no incident needed: if this fails like that, what breaks, how likely, and how soon?
      </p>
      <ServicePicker initial={params.get("service") ?? ""} suggestions={(svcs.data?.items ?? []).map((s) => s.name)} busy={busy} label="Simulate" onPick={run}>
        <div className="flex gap-1" role="radiogroup" aria-label="Failure kind">
          {KINDS.map((k) => (
            <button
              key={k}
              type="button"
              role="radio"
              aria-checked={kind === k}
              onClick={() => setKind(k)}
              className="rounded-md border border-border px-2.5 py-1.5 text-xs text-fog hover:text-mist aria-checked:border-smoke aria-checked:bg-graphite aria-checked:text-paper"
            >
              {k}
            </button>
          ))}
        </div>
        <Label className="flex items-center gap-1.5 text-xs text-muted-foreground">
          <Switch checked={save} onCheckedChange={setSave} /> <Save className="size-3.5" aria-hidden /> save
        </Label>
      </ServicePicker>
      {err && <p className="mt-6 text-sm text-st-refuted">{err}</p>}
      {res && (
        <section className="mt-6 overflow-hidden rounded-xl border border-border bg-card/40">
          <header className="flex flex-wrap items-center gap-x-4 gap-y-1 border-b border-border px-4 py-3 text-sm">
            <span>
              If <span className="font-mono text-foreground">{res.target}</span> → <span className="text-st-refuted">{res.kind}</span>:
            </span>
            <span className="text-muted-foreground">
              {res.counts.operations} operations in {res.counts.services} services · rules {res.rules_version}
            </span>
          </header>
          {res.predicted.length === 0 ? (
            <p className="px-4 py-8 text-center text-sm text-muted-foreground">Nothing with traffic depends on it: the failure stays contained.</p>
          ) : mode === "graph" ? (
            <SpreadGraph key={`${res.target}:${res.kind}`} res={res} />
          ) : (
            <>
            <div className="border-t border-border p-3"><DataView data={fromSimulation(res)} name={`what-if-${res.target}-${res.kind}`} className="max-h-[420px]" /></div>
            <ol className="divide-y divide-border/60">
              {res.predicted.map((p, i) => (
                <li key={`${p.op}:${p.kind}`} className="grid grid-cols-[28px_minmax(0,1fr)_80px_140px_90px_120px] items-center gap-3 px-4 py-2 text-sm max-md:grid-cols-[28px_1fr_80px]">
                  <span className="font-mono text-xs text-muted-foreground">{i + 1}</span>
                  <OpLabel op={p.op} />
                  <span className="rounded bg-st-refuted/12 px-1.5 py-0.5 text-center text-xs text-st-refuted">{p.kind}</span>
                  <span className="flex items-center gap-2 max-md:hidden">
                    <Meter value={p.p} label="probability" className={p.p > 0.7 ? "bg-st-refuted" : p.p > 0.4 ? "bg-ov-missed" : "bg-muted-foreground"} />
                    <span className="w-9 font-mono text-xs tabular-nums">{p.p.toFixed(2)}</span>
                  </span>
                  <span className="text-xs text-muted-foreground max-md:hidden">≤ {p.expected_delay_s}s · {p.hops} hop{p.hops === 1 ? "" : "s"}</span>
                  <span className="truncate text-xs text-muted-foreground max-md:hidden">{p.owner ?? "no owner"}</span>
                </li>
              ))}
            </ol>
            </>
          )}
        </section>
      )}
    </main>
  );
}
