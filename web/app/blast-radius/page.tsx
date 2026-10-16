"use client";

import { FlaskConical, GitFork, History, Users } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useMemo, useState } from "react";

import { DataView } from "@/components/graph/data-view";
import { FlowGraph, type GNode, opTitle } from "@/components/graph/flow-graph";
import { useGraphMode, ViewToggle } from "@/components/graph/view-toggle";
import { OpLabel } from "@/components/incident/verdict";
import { ServicePicker } from "@/components/service-picker";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { api, call, type S } from "@/lib/api";
import { fromBlastRadius } from "@/lib/graph-data";
import { useEnv, useQuery, withEnv } from "@/lib/hooks";

/** Inspect layout: the failing service's ops on the left, callers spreading right by hops (it fails upstream). */
function BlastGraph({ br, selected, onSelect }: { br: S["BlastRadius"]; selected: string | null; onSelect: (id: string | null) => void }) {
  const nodes = useMemo<GNode[]>(
    () => [
      ...(br.sources ?? []).map((op) => ({ id: op, service: br.service, title: opTitle(op), sub: "fails", tone: "source" as const, badge: "fails" })),
      ...br.affected.map((a) => ({ id: a.operation, service: a.service, title: opTitle(a.operation), sub: a.owner ?? "no owner", badge: `${a.hops} hop${a.hops > 1 ? "s" : ""}` })),
    ],
    [br],
  );
  return (
    <div className="relative h-[620px] overflow-hidden rounded-xl border border-border bg-grid">
      <FlowGraph nodes={nodes} edges={br.edges ?? []} direction="LEFT" selected={selected} onSelect={onSelect} label={`Operations that can be reached when ${br.service} fails`} />
    </div>
  );
}

export default function BlastRadiusPage() {
  const [env] = useEnv();
  const params = useSearchParams();
  const router = useRouter();
  const service = params.get("service");
  const [mode, setMode] = useGraphMode();
  const [selected, setSelected] = useState<string | null>(null);
  const q = { env: env ?? undefined };
  const suggest = useQuery(`svc:${env}`, () => call(api.GET("/api/v1/services", { params: { query: q } })));
  const br = useQuery(service ? `br:${env}:${service}` : null, () =>
    call(api.GET("/api/v1/blast-radius/{service}", { params: { path: { service: service! }, query: q } })),
  );
  const byHops = new Map<number, typeof br.data extends undefined ? never : NonNullable<typeof br.data>["affected"]>();
  for (const a of br.data?.affected ?? []) byHops.set(a.hops, [...(byHops.get(a.hops) ?? []), a]);
  const owners = [...new Set((br.data?.affected ?? []).map((a) => a.owner).filter(Boolean))] as string[];

  return (
    <main className={`mx-auto w-full ${br.data && mode === "graph" ? "max-w-[1600px]" : "max-w-[1200px]"} px-4 py-8 lg:px-6`}>
      <h1 className="flex items-center gap-2 text-2xl font-medium tracking-[-0.012em]">
        <GitFork className="size-6 text-fog" aria-hidden /> Blast radius
        {br.data && <ViewToggle mode={mode} onChange={setMode} className="ml-auto" />}
      </h1>
      <p className="mt-1 mb-6 text-sm text-muted-foreground">If this service fails, which operations can it reach through the call graph, and who owns them?</p>
      <ServicePicker
        key={service ?? ""}
        initial={service ?? ""}
        suggestions={(suggest.data?.items ?? []).map((s) => s.name)}
        busy={br.loading}
        label="Show impact"
        onPick={(s) => router.replace(withEnv(`/blast-radius?service=${encodeURIComponent(s)}`, env))}
      />

      {br.error && <p className="mt-6 text-sm text-st-refuted">{br.error.code === "SERVICE_NOT_FOUND" ? `No service “${service}” in this environment.` : br.error.message}</p>}
      {br.loading && !br.data && <Skeleton className="mt-6 h-48 w-full rounded-xl" />}
      {br.data && (
        <div className="mt-6 grid gap-6 lg:grid-cols-[1fr_280px]">
          <div className="space-y-4">
            <div className="grid grid-cols-3 gap-3">
              {[
                ["Services", br.data.counts.services],
                ["Operations", br.data.counts.operations],
                ["Past incidents", br.data.past_incidents.length],
              ].map(([k, v]) => (
                <div key={k} className="rounded-xl border border-border bg-card/60 p-4">
                  <div className="text-xs text-muted-foreground">{k}</div>
                  <div className="mt-1 font-mono text-2xl font-semibold tabular-nums">{v}</div>
                </div>
              ))}
            </div>
            {br.data.affected.length === 0 && <p className="text-sm text-muted-foreground">Nothing calls into {service}: a failure stays contained.</p>}
            {mode === "graph" && br.data.affected.length > 0 && <BlastGraph br={br.data} selected={selected} onSelect={setSelected} />}
            {mode === "data" && <DataView data={fromBlastRadius(br.data)} name={`blast-radius-${service}`} selected={selected} onNode={(id) => { setSelected(id); setMode("graph"); }} className="max-h-[480px]" />}
            {mode === "data" && [...byHops.entries()].sort(([a], [b]) => a - b).map(([hops, ops]) => (
              <section key={hops} className="rounded-xl border border-border bg-card/40">
                <h2 className="border-b border-border px-4 py-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
                  {hops} hop{hops > 1 ? "s" : ""} away · {ops.length}
                </h2>
                <ul className="divide-y divide-border/60">
                  {ops.map((a) => (
                    <li key={a.operation} className="flex items-center gap-3 px-4 py-2 text-sm">
                      <OpLabel op={a.operation} className="min-w-0 flex-1" />
                      <span className="text-xs text-muted-foreground">{a.owner ?? "no owner"}</span>
                    </li>
                  ))}
                </ul>
              </section>
            ))}
          </div>
          <aside className="space-y-4">
            <div className="rounded-xl border border-border bg-card/40 p-4">
              <h2 className="flex items-center gap-1.5 text-xs font-semibold tracking-wide text-muted-foreground uppercase"><Users className="size-3.5" aria-hidden /> Owners to pull in</h2>
              <ul className="mt-2 space-y-1 text-sm">{owners.length ? owners.map((o) => <li key={o}>{o}</li>) : <li className="text-muted-foreground">none recorded</li>}</ul>
            </div>
            <div className="rounded-xl border border-border bg-card/40 p-4">
              <h2 className="flex items-center gap-1.5 text-xs font-semibold tracking-wide text-muted-foreground uppercase"><History className="size-3.5" aria-hidden /> Past incidents rooted here</h2>
              <ul className="mt-2 space-y-1">
                {br.data.past_incidents.length ? br.data.past_incidents.map((i) => (
                  <li key={i}><Link className="font-mono text-xs text-signal hover:underline" href={withEnv(`/incident/${encodeURIComponent(i)}`, env)}>{i}</Link></li>
                )) : <li className="text-sm text-muted-foreground">none</li>}
              </ul>
              {br.data.past_incidents.length > 0 && (
                <Link className="mt-2 block text-xs text-signal hover:underline" href={withEnv(`/?cause=${encodeURIComponent(service!)}`, env)}>All incidents caused by {service} →</Link>
              )}
            </div>
            <Button asChild variant="outline" className="w-full">
              <Link href={withEnv(`/simulate?service=${encodeURIComponent(service!)}`, env)}><FlaskConical className="size-4" /> Simulate a failure</Link>
            </Button>
          </aside>
        </div>
      )}
    </main>
  );
}
