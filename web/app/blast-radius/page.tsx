"use client";

import { FlaskConical, GitFork, History, Users } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";

import { OpLabel } from "@/components/incident/verdict";
import { ServicePicker } from "@/components/service-picker";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { api, call } from "@/lib/api";
import { useEnv, useQuery, withEnv } from "@/lib/hooks";

export default function BlastRadiusPage() {
  const [env] = useEnv();
  const params = useSearchParams();
  const router = useRouter();
  const service = params.get("service");
  const q = { env: env ?? undefined };
  const suggest = useQuery(`svc:${env}`, () => call(api.GET("/api/v1/services", { params: { query: q } })));
  const br = useQuery(service ? `br:${env}:${service}` : null, () =>
    call(api.GET("/api/v1/blast-radius/{service}", { params: { path: { service: service! }, query: q } })),
  );
  const byHops = new Map<number, typeof br.data extends undefined ? never : NonNullable<typeof br.data>["affected"]>();
  for (const a of br.data?.affected ?? []) byHops.set(a.hops, [...(byHops.get(a.hops) ?? []), a]);
  const owners = [...new Set((br.data?.affected ?? []).map((a) => a.owner).filter(Boolean))] as string[];

  return (
    <main className="mx-auto w-full max-w-5xl px-4 py-8 lg:px-6">
      <h1 className="flex items-center gap-2 text-2xl font-semibold tracking-tight"><GitFork className="size-6 text-primary" aria-hidden /> Blast radius</h1>
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
            {[...byHops.entries()].sort(([a], [b]) => a - b).map(([hops, ops]) => (
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
                  <li key={i}><Link className="font-mono text-xs text-primary hover:underline" href={withEnv(`/incident/${encodeURIComponent(i)}`, env)}>{i}</Link></li>
                )) : <li className="text-sm text-muted-foreground">none</li>}
              </ul>
              {br.data.past_incidents.length > 0 && (
                <Link className="mt-2 block text-xs text-primary hover:underline" href={withEnv(`/?cause=${encodeURIComponent(service!)}`, env)}>All incidents caused by {service} →</Link>
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
