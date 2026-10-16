"use client";

import { FlaskConical, Save } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";

import { OpLabel } from "@/components/incident/verdict";
import { ServicePicker } from "@/components/service-picker";
import { Meter } from "@/components/status";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { api, ApiError, call, type S } from "@/lib/api";
import { useEnv, useQuery, withEnv } from "@/lib/hooks";

const KINDS = ["down", "errors", "latency", "cpu", "mem", "saturation"] as const;

export default function SimulatePage() {
  const [env] = useEnv();
  const params = useSearchParams();
  const router = useRouter();
  const [kind, setKind] = useState<(typeof KINDS)[number]>((params.get("kind") as never) ?? "down");
  const [save, setSave] = useState(false);
  const [busy, setBusy] = useState(false);
  const [res, setRes] = useState<S["SimulateOut"] | null>(null);
  const [err, setErr] = useState<string | null>(null);
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
    <main className="mx-auto w-full max-w-5xl px-4 py-8 lg:px-6">
      <h1 className="flex items-center gap-2 text-2xl font-semibold tracking-tight"><FlaskConical className="size-6 text-primary" aria-hidden /> What-if</h1>
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
              className="rounded-md border border-border px-2.5 py-1.5 text-xs aria-checked:border-primary aria-checked:bg-primary/15 aria-checked:text-primary"
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
          ) : (
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
          )}
        </section>
      )}
    </main>
  );
}
