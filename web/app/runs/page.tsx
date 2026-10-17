"use client";

import { ArrowRight, CircleAlert, FlaskConical, Gauge, Loader2, PlayCircle, Radio, RotateCcw, ShieldCheck, Undo2 } from "@/components/icons";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { api, ApiError, call, type S } from "@/lib/api";
import { useQuery, withEnv } from "@/lib/hooks";
import { cn } from "@/lib/utils";

type Scenario = S["ScenarioOut"];
type Run = S["RunOut"];

const ENV_INFO: Record<string, { title: string; blurb: string; start: string }> = {
  synthetic: {
    title: "Demo 1 · Synthetic (small)",
    blurb: "Generated systems with a known answer, in the RCAEval file layout: replayed into the graph, then diagnosed. Start with the small cases.",
    start: "docker compose exec api python examples/synthetic/gen.py --size small --fault cpu",
  },
  "rcaeval-tt": {
    title: "Demo 2 · RCAEval Train-Ticket (medium)",
    blurb: "Real faults recorded by the RCAEval benchmark: replayed into the graph, then diagnosed. Same engine, measured.",
    start: "docker compose exec api python -m api.ingest.rcaeval --case <case> --env rcaeval-tt --download",
  },
  "flip-commerce": {
    title: "flip-commerce",
    blurb: "Your own system: nginx → flip-node → Mongo replica set + Redis. Real failures, shallow graph.",
    start: "python examples/flip-commerce/run.py up",
  },
  "astronomy-shop": {
    title: "Demo 3 · OpenTelemetry Demo (real-world)",
    blurb: "~20 services, flagd feature flags as faults. The multi-hop story.",
    start: "python examples/otel-demo/run.py up",
  },
};

// the demo order (SETUP §5): small → medium → real-world, then anything else
const ORDER = ["synthetic", "rcaeval-tt", "astronomy-shop"];
const rank = (env: string) => (ORDER.indexOf(env) + ORDER.length + 1) % (ORDER.length + 1);

const KIND: Record<Scenario["kind"], { label: string; Icon: typeof Radio; cls: string }> = {
  fault: { label: "fault", Icon: CircleAlert, cls: "text-st-refuted bg-st-refuted/10" },
  load: { label: "load", Icon: Gauge, cls: "text-ov-missed bg-ov-missed/10" },
  baseline: { label: "baseline", Icon: ShieldCheck, cls: "text-st-confirmed bg-st-confirmed/10" },
  replay: { label: "replay", Icon: RotateCcw, cls: "text-signal bg-signal/10" },
};

function useNow(ms = 1000) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), ms);
    return () => clearInterval(t);
  }, [ms]);
  return now;
}

function RunCard({ run, now, onUndo, busy }: { run: Run; now: number; onUndo: () => void; busy: boolean }) {
  const startedAt = new Date(run.started_at).getTime();
  const alertAt = new Date(run.alert_at).getTime();
  const total = Math.max(alertAt - startedAt, 1);
  const left = Math.max(0, Math.ceil((alertAt - now) / 1000));
  const pct = Math.min(1, Math.max(0, (now - startedAt) / total));
  const undone = run.status === "undone";
  const canUndo = !undone && (run.kind === "fault" || run.kind === "load");
  return (
    <div className="epi-in rounded-xl border border-signal/30 bg-signal/[0.05] p-4">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <span className="font-medium">{run.title}</span>
        <span className="font-mono text-xs text-muted-foreground">{run.env} · {run.run_id}</span>
        {undone && <span className="rounded bg-st-confirmed/12 px-1.5 py-0.5 text-[11px] text-st-confirmed">undone</span>}
        {run.status === "fault_failed" && <span className="rounded bg-st-refuted/12 px-1.5 py-0.5 text-[11px] text-st-refuted">fault failed</span>}
      </div>
      {run.status === "fault_failed" ? (
        <>
          <p className="mt-2 text-sm text-muted-foreground">
            The fault script failed, so no diagnosis runs. It may have acted before failing: undo to be safe.
          </p>
          {run.detail && (
            <pre className="mt-2 max-h-24 overflow-auto rounded bg-muted/60 p-2 font-mono text-[11px] whitespace-pre-wrap text-st-refuted">
              {run.detail.trim().split("\n").slice(-3).join("\n")}
            </pre>
          )}
        </>
      ) : left > 0 ? (
        <>
          <p className="mt-2 text-sm text-muted-foreground">
            {run.kind === "baseline" ? "Nothing injected." : run.kind === "load" ? "Extra load is on." : "Fault is in."} The alert
            fires in <span className="font-mono text-foreground tabular-nums">{left}s</span>
            {run.kind === "baseline" ? " on a healthy system: Epicenter should answer “no root cause”." : ", once the symptoms have spread; then Epicenter ingests the window and diagnoses."}
          </p>
          <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-muted" role="progressbar" aria-valuenow={Math.round(pct * 100)} aria-label="Until the alert">
            <div className="h-full bg-signal transition-[width] duration-1000" style={{ width: `${pct * 100}%` }} />
          </div>
        </>
      ) : run.matches == null ? (
        <p className="mt-2 text-sm text-muted-foreground">Alert fired. The diagnosis is running.</p>
      ) : (
        <p className="mt-2 flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
          Verdict <span className="font-mono text-foreground">{run.verdict}</span>
          <span className={`rounded px-1.5 py-0.5 text-[11px] ${run.matches ? "bg-st-confirmed/12 text-st-confirmed" : "bg-st-refuted/12 text-st-refuted"}`}>
            {run.matches ? "matches expected" : "differs from expected"}
          </span>
        </p>
      )}
      <div className="mt-3 flex flex-wrap gap-2">
        <Button asChild size="sm" variant={left > 0 || run.status === "fault_failed" ? "outline" : "default"}>
          <Link href={withEnv(`/incident/${encodeURIComponent(run.incident_id)}`, run.env)}>
            Open incident <ArrowRight className="size-3.5" />
          </Link>
        </Button>
        {canUndo && (
          <Button size="sm" variant="outline" onClick={onUndo} disabled={busy}>
            {busy ? <Loader2 className="size-3.5 animate-spin" /> : <Undo2 className="size-3.5" />} Undo fault
          </Button>
        )}
      </div>
    </div>
  );
}

export default function RunsPage() {
  const router = useRouter();
  const now = useNow();
  const s = useQuery("runs:scenarios", () => call(api.GET("/api/v1/runs/scenarios")), 15_000);
  const [busy, setBusy] = useState<string | null>(null);
  const envs = useMemo(() => [...new Set((s.data?.items ?? []).map((x) => x.env))].sort(), [s.data]);
  // the shared record: Run nodes in each env's graph, so every viewer (and a reload) sees the same runs
  const recent = useQuery(envs.length ? `runs:recent:${envs.join(",")}` : null, async () => {
    const pages = await Promise.all(envs.map((env) => call(api.GET("/api/v1/runs", { params: { query: { env, limit: 3 } } }))));
    return pages.flatMap((p) => p.items).sort((a, b) => b.started_at.localeCompare(a.started_at));
  }, 5_000);
  const runs = useMemo(() => recent.data ?? [], [recent.data]);

  const groups = useMemo(() => {
    const m = new Map<string, Scenario[]>();
    for (const x of s.data?.items ?? []) m.set(x.env, [...(m.get(x.env) ?? []), x]);
    return [...m.entries()].sort(([a], [b]) => rank(a) - rank(b) || a.localeCompare(b));
  }, [s.data]);

  // a run's page opens by itself when its alert fires (unless the user already left for it)
  useEffect(() => {
    const due = runs.find((r) => r.status !== "undone" && Math.abs(new Date(r.alert_at).getTime() - now) < 500);
    if (due) toast.info("Alert fired", { description: `${due.title}: diagnosis started.`, action: { label: "Open", onClick: () => router.push(withEnv(`/incident/${encodeURIComponent(due.incident_id)}`, due.env)) } });
  }, [now, runs, router]);

  const start = async (x: Scenario) => {
    setBusy(`${x.env}:${x.id}`);
    try {
      const r = await call(api.POST("/api/v1/runs", { body: { env: x.env, scenario: x.id } }));
      recent.reload();
      toast.success(x.kind === "replay" ? "Replay started" : "Fault injected", {
        description: r.change_id ? `Change ${r.change_id} recorded before the fault.` : x.title,
      });
      if (x.kind === "replay") router.push(withEnv(`/incident/${encodeURIComponent(r.incident_id)}`, x.env));
    } catch (e) {
      toast.error("Couldn't start the run", { description: e instanceof ApiError ? `${e.code}: ${e.message}` : String(e) });
    } finally {
      setBusy(null);
    }
  };

  const undo = async (run: Run) => {
    setBusy(run.run_id);
    try {
      const r = await call(api.DELETE("/api/v1/runs/{run_id}", { params: { path: { run_id: run.run_id }, query: { env: run.env } } }));
      recent.reload();
      toast.success(r.status === "undone" ? "Fault undone" : "Nothing to undo", { description: `${run.title}: the environment is recovering.` });
    } catch (e) {
      toast.error("Undo failed", { description: e instanceof ApiError ? e.message : String(e) });
    } finally {
      setBusy(null);
    }
  };

  // what's still live, plus anything from the last 15 minutes
  const live = runs.filter((r) => (r.status === "started" && r.kind !== "replay") || new Date(r.started_at).getTime() > now - 15 * 60_000).slice(0, 4);

  return (
    <main className="mx-auto w-full max-w-[1200px] px-4 py-8 lg:px-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-medium tracking-[-0.012em]">
            <PlayCircle className="size-6 text-fog" aria-hidden /> Example runs
          </h1>
          <p className="mt-1 max-w-2xl text-sm text-muted-foreground">
            Break a real system on purpose and watch Epicenter find the cause. Each fault records its change first, fires
            the alert once symptoms spread, and can be undone.
          </p>
        </div>
        {s.data && (
          <span className={cn("inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs", s.data.runner ? "bg-st-confirmed/10 text-st-confirmed" : "bg-ov-missed/10 text-ov-missed")}>
            <span className={cn("size-1.5 rounded-full", s.data.runner ? "bg-st-confirmed" : "bg-ov-missed")} aria-hidden />
            {s.data.runner ? "Fault runner connected" : "Fault runner not reachable"}
          </span>
        )}
      </div>

      {live.length > 0 && (
        <section className="mt-6 space-y-3" aria-label="Recent runs">
          {live.map((r) => (
            <RunCard key={r.run_id} run={r} now={now} busy={busy === r.run_id} onUndo={() => undo(r)} />
          ))}
        </section>
      )}

      {s.loading && !s.data && <Skeleton className="mt-6 h-64 w-full rounded-xl" />}
      {s.error && <p className="mt-6 text-sm text-st-refuted">Couldn&apos;t load scenarios: {s.error.message}</p>}

      <div className="mt-6 space-y-6">
        {groups.map(([env, items]) => {
          const info = ENV_INFO[env];
          const up = items.some((i) => i.ready);
          const replay = items.every((i) => i.kind === "replay");
          return (
            <section key={env} className="overflow-hidden rounded-xl border border-border bg-card/40" aria-labelledby={`env-${env}`}>
              <header className="flex flex-wrap items-center gap-x-3 gap-y-1 border-b border-border px-4 py-3">
                {replay ? <RotateCcw className="size-4 text-signal" aria-hidden /> : <FlaskConical className="size-4 text-signal" aria-hidden />}
                <h2 id={`env-${env}`} className="font-semibold">{info?.title ?? env}</h2>
                <span className="font-mono text-xs text-muted-foreground">env:{env}</span>
                <span className={cn("ml-auto inline-flex items-center gap-1.5 text-xs", up ? "text-st-confirmed" : "text-muted-foreground")}>
                  <span className={cn("size-1.5 rounded-full", up ? "bg-st-confirmed" : "bg-muted-foreground")} aria-hidden />
                  {replay ? "recorded cases" : up ? "running" : "not running"}
                </span>
                {(info || replay) && (
                  <p className="w-full text-xs text-muted-foreground">
                    {info?.blurb ?? "Recorded cases on disk: replayed into the graph, then diagnosed."}
                    {!up && !replay && info && (
                      <> Start it with <code className="rounded bg-muted px-1 font-mono text-foreground">{info.start}</code>.</>
                    )}
                  </p>
                )}
              </header>
              <ul className="divide-y divide-border/60">
                {items.map((x) => {
                  const k = KIND[x.kind];
                  const key = `${x.env}:${x.id}`;
                  return (
                    <li key={key} className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-3 px-4 py-3 sm:grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)_auto]">
                      <div className="min-w-0">
                        <p className="flex items-center gap-2 text-sm font-medium">
                          <span className={cn("inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[11px] font-medium", k.cls)}>
                            <k.Icon className="size-3" aria-hidden /> {k.label}
                          </span>
                          <span className="truncate">{x.title}</span>
                        </p>
                        <p className="mt-0.5 truncate font-mono text-[11px] text-muted-foreground">{x.id}</p>
                      </div>
                      <p className="text-xs text-muted-foreground max-sm:hidden">
                        Expect <span className="font-mono text-foreground">{x.expected}</span>
                      </p>
                      <Button size="sm" variant={x.kind === "fault" ? "secondary" : "outline"} disabled={!x.ready || busy !== null} onClick={() => start(x)} aria-label={`Run ${x.title}`}>
                        {busy === key ? <Loader2 className="size-3.5 animate-spin" /> : <PlayCircle className="size-3.5" />} Run
                      </Button>
                    </li>
                  );
                })}
              </ul>
            </section>
          );
        })}
      </div>
    </main>
  );
}
