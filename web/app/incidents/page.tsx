"use client";

import { ArrowRight, Radar } from "@/components/icons";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";

import { Meter, StatusPill } from "@/components/status";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { api, ApiError, call, type S } from "@/lib/api";
import { pct, relTime, splitOp } from "@/lib/format";
import { useEnv, useQuery, withEnv } from "@/lib/hooks";
import { cn } from "@/lib/utils";

const FILTERS = [
  { key: "", label: "All" },
  { key: "diagnosing", label: "Diagnosing" },
  { key: "diagnosed", label: "Diagnosed" },
  { key: "no_root_cause", label: "No root cause" },
  { key: "delivered", label: "Delivered" },
  { key: "resolved", label: "Resolved" },
] as const;

type Item = S["IncidentSummary"];

const SAMPLE = "synth-small_svc-0_cpu_1"; // examples/synthetic/gen.py, small, cpu, seed 1

/** The empty state's one click: replay the small synthetic CPU sample (generated on the API's first start). */
function SampleRun() {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const run = async () => {
    setBusy(true);
    setErr(null);
    try {
      // seed 1 is deterministic, so the CPU sample's id is known; list the scenarios only if it's missing
      let id = SAMPLE;
      const start = () => call(api.POST("/api/v1/runs", { body: { env: "synthetic", scenario: id } }));
      const r = await start().catch(async (e) => {
        if (!(e instanceof ApiError) || e.code !== "SCENARIO_NOT_FOUND") throw e;
        const sc = (await call(api.GET("/api/v1/runs/scenarios"))).items.filter((x) => x.env === "synthetic" && x.id.startsWith("synth-small_"));
        if (!sc.length) throw new Error("No samples found: check examples/samples/ is in your clone, then open Runs.");
        id = sc[0].id;
        return start();
      });
      router.push(withEnv(`/incident/${encodeURIComponent(r.incident_id)}`, "synthetic"));
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
      setBusy(false);
    }
  };
  return (
    <>
      <Button onClick={run} disabled={busy}>{busy ? "Starting…" : "Run a sample incident"} <ArrowRight className="size-4" /></Button>
      {err && <p className="text-xs text-st-refuted">{err}</p>}
    </>
  );
}

function Op({ op, className }: { op: string | null; className?: string }) {
  if (!op) return <span className="text-muted-foreground">—</span>;
  const [svc, name] = splitOp(op);
  return (
    <span className={cn("min-w-0 truncate font-mono text-[13px]", className)} title={op}>
      <span className="text-foreground">{svc}</span>
      <span className="text-muted-foreground">/{name}</span>
    </span>
  );
}

export default function IncidentsPage() {
  const [env] = useEnv();
  const params = useSearchParams();
  const router = useRouter();
  const status = params.get("status") ?? "";
  const cause = params.get("cause");
  const [extra, setExtra] = useState<Item[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);

  const first = useQuery(
    `incidents:${env}:${status}:${cause}`,
    () =>
      call(
        api.GET("/api/v1/incidents", {
          params: { query: { env: env ?? undefined, status: (status || undefined) as never, cause: cause ?? undefined, limit: 25 } },
        }),
      ),
    10_000,
  );
  useEffect(() => {
    setExtra([]);
    setCursor(null);
  }, [env, status, cause]);
  const next = cursor ?? first.data?.next_cursor ?? null;
  const more = async () => {
    if (!next) return;
    const page = await call(
      api.GET("/api/v1/incidents", {
        params: { query: { env: env ?? undefined, status: (status || undefined) as never, cause: cause ?? undefined, limit: 25, cursor: next } },
      }),
    );
    setExtra((x) => [...x, ...page.items]);
    setCursor(page.next_cursor ?? "");
  };
  const items = [...(first.data?.items ?? []), ...extra];
  const setFilter = (key: string) => {
    const q = new URLSearchParams(params.toString());
    if (key) q.set("status", key);
    else q.delete("status");
    router.replace(`/incidents?${q}`);
  };

  return (
    <main className="mx-auto w-full max-w-[1200px] px-4 py-8 lg:px-6">
      <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-medium tracking-[-0.012em]">Incidents</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Every alert becomes a live investigation: suspects, evidence, a verdict you can check.
            {cause && (
              <>
                {" "}Filtered to root cause in <span className="font-mono text-foreground">{cause}</span>.{" "}
                <Link className="text-signal underline-offset-4 hover:underline" href={withEnv("/incidents", env)}>
                  Clear
                </Link>
              </>
            )}
          </p>
        </div>
        <div className="flex flex-wrap gap-1" role="group" aria-label="Filter by status">
          {FILTERS.map((f) => (
            <Button
              key={f.key}
              size="sm"
              variant={status === f.key ? "secondary" : "ghost"}
              className="h-8"
              aria-pressed={status === f.key}
              onClick={() => setFilter(f.key)}
            >
              {f.label}
            </Button>
          ))}
        </div>
      </div>

      <div className="overflow-hidden rounded-xl border border-border bg-card/60">
        <div className="grid grid-cols-[minmax(0,1.7fr)_120px_minmax(0,1fr)_minmax(0,1.5fr)_120px_80px] gap-4 border-b border-border px-4 py-2.5 text-xs font-medium tracking-wide text-muted-foreground uppercase max-md:hidden">
          <span>Incident</span>
          <span>Status</span>
          <span>Alerting operation</span>
          <span>Root cause</span>
          <span>Confidence</span>
          <span className="text-right">Opened</span>
        </div>
        {first.loading && !first.data &&
          Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="border-b border-border/60 px-4 py-4 last:border-0">
              <Skeleton className="h-5 w-full" />
            </div>
          ))}
        {first.error && (
          <div className="px-4 py-10 text-center text-sm text-muted-foreground">
            {first.error.code === "GRAPH_UNAVAILABLE" ? "The graph is offline. " : "Couldn't load incidents: "}
            <span className="font-mono">{first.error.message}</span>
          </div>
        )}
        {first.data && items.length === 0 && (
          <div className="flex flex-col items-center gap-3 px-4 py-16 text-center">
            <Radar className="size-8 text-muted-foreground" aria-hidden />
            <p className="font-medium">No incidents here yet</p>
            <p className="max-w-md text-sm text-muted-foreground">
              Run a sample: a generated 5-service system with one injected fault and a known answer, replayed into the graph
              and diagnosed in a few seconds. No setup needed.
            </p>
            <SampleRun />
            <p className="max-w-md text-xs text-muted-foreground">
              Or pick any demo in <Link href={withEnv("/runs", env)} className="text-signal hover:underline">Runs</Link>, or fire
              an alert with <span className="font-mono text-foreground">POST /api/v1/alerts</span>.
            </p>
          </div>
        )}
        <ul>
          {items.map((i) => (
            <li key={i.id} className="border-b border-border/60 last:border-0">
              <Link
                href={withEnv(`/incident/${encodeURIComponent(i.id)}`, env)}
                className="group grid grid-cols-[minmax(0,1.7fr)_120px_minmax(0,1fr)_minmax(0,1.5fr)_120px_80px] items-center gap-4 px-4 py-3 transition-colors hover:bg-accent/40 max-md:grid-cols-1 max-md:gap-1.5"
              >
                <span className="truncate font-mono text-[13px] text-foreground" title={i.id}>{i.id}</span>
                <span><StatusPill status={i.status} /></span>
                <Op op={i.symptom} />
                <Op op={i.root_cause} className={i.root_cause ? "text-st-confirmed" : ""} />
                <span className="flex items-center gap-2">
                  {i.confidence != null ? (
                    <>
                      <Meter value={i.confidence} label="confidence" className="bg-st-confirmed" />
                      <span className="w-10 text-right font-mono text-xs tabular-nums">{pct(i.confidence)}</span>
                    </>
                  ) : (
                    <span className="text-muted-foreground">—</span>
                  )}
                </span>
                <span className="flex items-center justify-end gap-1 text-right text-xs text-muted-foreground">
                  {relTime(i.opened_at)}
                  <ArrowRight className="size-3.5 opacity-0 transition-opacity group-hover:opacity-100" aria-hidden />
                </span>
              </Link>
            </li>
          ))}
        </ul>
      </div>
      {next && (
        <div className="mt-4 flex justify-center">
          <Button variant="outline" size="sm" onClick={more}>
            Load more
          </Button>
        </div>
      )}
    </main>
  );
}
