"use client";

import { ArrowRight, BookOpenCheck, FlaskConical, GitCommitHorizontal, GitFork, History, Target, TriangleAlert, Users, Zap } from "@/components/icons";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useMemo, useState } from "react";

import { DataView } from "@/components/graph/data-view";
import { FlowGraph, type GNode, opTitle } from "@/components/graph/flow-graph";
import { useGraphMode, ViewToggle } from "@/components/graph/view-toggle";
import { OpLabel } from "@/components/incident/verdict";
import { ServicePicker } from "@/components/service-picker";
import { StatusPill } from "@/components/status";
import { Skeleton } from "@/components/ui/skeleton";
import { api, call, type S } from "@/lib/api";
import { relTime } from "@/lib/format";
import { fromBlastRadius } from "@/lib/graph-data";
import { useEnv, useQuery, withEnv } from "@/lib/hooks";
import { cn } from "@/lib/utils";

const KINDS = ["down", "errors", "latency", "cpu", "mem", "saturation"] as const;
const plural = (n: number, w: string) => `${n} ${w}${n === 1 ? "" : "s"}`;

/** A bento tile: a titled card that spans a few grid columns. */
function Tile({ title, Icon, className, children, aside }: { title: string; Icon: typeof Users; className?: string; children: React.ReactNode; aside?: React.ReactNode }) {
  return (
    <section className={cn("flex min-w-0 flex-col rounded-xl border border-border bg-card/50 p-4", className)}>
      <h2 className="mb-3 flex items-center gap-1.5 text-[11px] font-semibold tracking-wider text-muted-foreground uppercase">
        <Icon className="size-3.5" aria-hidden /> {title}
        {aside && <span className="ml-auto normal-case tracking-normal">{aside}</span>}
      </h2>
      {children}
    </section>
  );
}

/** Inspect layout: the failing service's ops on the left, callers spreading right by hops (it fails upstream). */
function BlastGraph({ br, selected, onSelect }: { br: S["BlastRadius"]; selected: string | null; onSelect: (id: string | null) => void }) {
  const nodes = useMemo<GNode[]>(
    () => [
      ...(br.sources ?? []).map((op) => ({ id: op, service: br.service, title: opTitle(op), sub: "fails", tone: "source" as const, badge: "fails" })),
      ...br.affected.map((a) => ({ id: a.operation, service: a.service, title: opTitle(a.operation), sub: a.owner ?? "no owner", badge: `${a.hops} hop${a.hops > 1 ? "s" : ""}` })),
    ],
    [br],
  );
  return <FlowGraph nodes={nodes} edges={br.edges ?? []} direction="LEFT" selected={selected} onSelect={onSelect} label={`Operations that can be reached when ${br.service} fails`} />;
}

/** No service picked yet: where to look first. */
function Riskiest({ env, items }: { env: string | null; items: S["ServiceRisk"][] }) {
  const max = Math.max(1, ...items.map((r) => r.callers));
  return (
    <section className="mt-8">
      <h2 className="mb-3 flex items-center gap-1.5 text-[11px] font-semibold tracking-wider text-muted-foreground uppercase"><TriangleAlert className="size-3.5" /> Riskiest services: most incidents, most callers</h2>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {items.map((r) => (
          <Link key={r.name} href={withEnv(`/blast-radius?service=${encodeURIComponent(r.name)}`, env)} className="group rounded-xl border border-border bg-card/50 p-4 transition-colors hover:border-gold/50">
            <p className="flex items-center gap-2"><span className="truncate font-mono text-sm text-paper">{r.name}</span><ArrowRight className="ml-auto size-3.5 text-muted-foreground group-hover:text-gold" /></p>
            <p className="mt-1 text-xs text-muted-foreground">{r.kind ?? "service"} · {r.owner ?? "no owner"}</p>
            <div className="mt-3 h-1 overflow-hidden rounded-full bg-muted"><div className="h-full bg-gold/70" style={{ width: `${(r.callers / max) * 100}%` }} /></div>
            <p className="mt-2 flex justify-between text-[11px] text-muted-foreground"><span>{r.callers} calling service{r.callers === 1 ? "" : "s"}</span><span className={r.incidents ? "text-st-refuted" : ""}>{r.incidents} incident{r.incidents === 1 ? "" : "s"}</span></p>
          </Link>
        ))}
      </div>
    </section>
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
  const risk = useQuery(`risk:${env}`, () => call(api.GET("/api/v1/services/risk", { params: { query: { ...q, limit: 50 } } })));
  const br = useQuery(service ? `br:${env}:${service}` : null, () => call(api.GET("/api/v1/blast-radius/{service}", { params: { path: { service: service! }, query: q } })));
  const people = useQuery(service ? `ppl:${env}:${service}` : null, () => call(api.GET("/api/v1/services/{service}/people", { params: { path: { service: service! }, query: q } })));
  const books = useQuery(service ? `rb:${env}:${service}` : null, () => call(api.GET("/api/v1/services/{service}/runbooks", { params: { path: { service: service! }, query: q } })));
  const changes = useQuery(service ? `chg7:${env}:${service}` : null, () => call(api.GET("/api/v1/services/{service}/changes", { params: { path: { service: service! }, query: { ...q, hours: 168 } } })));
  const past = useQuery(service ? `past:${env}:${service}` : null, () => call(api.GET("/api/v1/incidents", { params: { query: { ...q, cause: service!, limit: 6 } } })));

  const d = br.data;
  const me = risk.data?.items.find((r) => r.name === service);
  const svcInfo = suggest.data?.items.find((s) => s.name === service);
  const byHop = useMemo(() => {
    const m = new Map<number, number>();
    for (const a of d?.affected ?? []) m.set(a.hops, (m.get(a.hops) ?? 0) + 1);
    return [...m.entries()].sort(([a], [b]) => a - b);
  }, [d]);
  const maxHop = Math.max(1, ...byHop.map(([, n]) => n));
  const owners = [...new Set((d?.affected ?? []).map((a) => a.owner).filter(Boolean))] as string[];
  // inbound traffic: the calls into this service's operations, by caller
  const inbound = useMemo(() => {
    const src = new Set(d?.sources ?? []);
    return (d?.edges ?? []).filter((e) => src.has(e.dst) && !src.has(e.src)).sort((a, b) => (b.rps ?? 0) - (a.rps ?? 0)).slice(0, 8);
  }, [d]);

  return (
    <main className={`mx-auto w-full ${d ? "max-w-[1500px]" : "max-w-[1200px]"} px-4 py-8 lg:px-6`}>
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="flex items-center gap-2 text-3xl"><GitFork className="size-6 text-fog" aria-hidden /> Blast radius</h1>
        {d && <ViewToggle mode={mode} onChange={setMode} className="ml-auto" />}
      </div>
      <p className="mt-1 mb-6 text-sm text-muted-foreground">Know a service before it fails: what it reaches, who to call, what broke here before, and what changed.</p>
      <ServicePicker
        key={service ?? ""}
        initial={service ?? ""}
        suggestions={(suggest.data?.items ?? []).map((s) => s.name)}
        busy={br.loading}
        label="Show impact"
        onPick={(s) => router.replace(withEnv(`/blast-radius?service=${encodeURIComponent(s)}`, env))}
      />

      {!service && risk.data && <Riskiest env={env} items={risk.data.items.slice(0, 8)} />}
      {br.error && <p className="mt-6 text-sm text-st-refuted">{br.error.code === "SERVICE_NOT_FOUND" ? `No service “${service}” in this environment.` : br.error.message}</p>}
      {br.loading && !d && <Skeleton className="mt-6 h-48 w-full rounded-xl" />}

      {d && (
        <div className="mt-6 grid grid-cols-1 gap-4 md:grid-cols-6 lg:grid-cols-12">
          {/* hero */}
          <section className="relative overflow-hidden rounded-xl border border-gold/25 bg-gradient-to-br from-gold/[0.07] to-transparent p-5 md:col-span-6 lg:col-span-5">
            <p className="font-mono text-xs text-muted-foreground">{me?.kind ?? svcInfo?.kind ?? "service"} · {plural(svcInfo?.operations ?? d.sources?.length ?? 0, "operation")}</p>
            <p className="mt-1 font-[family-name:var(--font-display)] text-4xl italic text-paper">{d.service}</p>
            <p className="mt-1 flex items-center gap-1.5 text-sm text-muted-foreground"><Users className="size-3.5" /> {me?.owner ?? "no owner recorded"}</p>
            <p className="mt-4 text-sm leading-relaxed">
              {d.affected.length ? (
                <>If <span className="font-mono text-paper">{d.service}</span> fails, it can reach <b className="text-gold">{d.counts.services} services</b> and <b className="text-gold">{d.counts.operations} operations</b> within {byHop.at(-1)?.[0] ?? 0} hop{(byHop.at(-1)?.[0] ?? 0) === 1 ? "" : "s"}{owners.length ? <>, paging <b className="text-gold">{owners.length} team{owners.length === 1 ? "" : "s"}</b></> : null}.</>
              ) : (
                <>Nothing with traffic calls into <span className="font-mono">{d.service}</span>: a failure stays contained.</>
              )}
            </p>
          </section>

          {/* impact by hop */}
          <Tile title="Impact by hop" Icon={Target} className="md:col-span-3 lg:col-span-4">
            {byHop.length ? (
              <ul className="space-y-2">
                {byHop.map(([h, n]) => (
                  <li key={h} className="grid grid-cols-[52px_1fr_32px] items-center gap-2 text-xs">
                    <span className="text-muted-foreground">{h} hop{h > 1 ? "s" : ""}</span>
                    <span className="h-2 overflow-hidden rounded-full bg-muted"><span className="block h-full rounded-full bg-gradient-to-r from-st-refuted to-gold" style={{ width: `${(n / maxHop) * 100}%` }} /></span>
                    <span className="text-right font-mono tabular-nums">{n}</span>
                  </li>
                ))}
              </ul>
            ) : <p className="text-xs text-muted-foreground">No callers.</p>}
          </Tile>

          {/* numbers */}
          <div className="grid grid-cols-2 gap-3 md:col-span-3 lg:col-span-3">
            {[
              ["Services reached", d.counts.services],
              ["Operations", d.counts.operations],
              ["Incidents rooted here", d.past_incidents.length],
              ["Changes · 7 d", changes.data?.items.length ?? "…"],
            ].map(([k, v]) => (
              <div key={k} className="rounded-xl border border-border bg-card/50 p-3">
                <div className="text-[11px] text-muted-foreground">{k}</div>
                <div className="mt-1 font-mono text-2xl tabular-nums text-paper">{v}</div>
              </div>
            ))}
          </div>

          {/* the graph, or its tables */}
          <section className="relative h-[440px] overflow-hidden rounded-xl border border-border bg-grid md:col-span-6 lg:col-span-8 lg:row-span-2 lg:h-auto lg:min-h-[480px]">
            {mode === "data" ? (
              <div className="h-full overflow-auto p-3"><DataView data={fromBlastRadius(d)} name={`blast-radius-${service}`} selected={selected} onNode={(id) => { setSelected(id); setMode("graph"); }} className="h-full" /></div>
            ) : d.affected.length ? (
              <BlastGraph br={d} selected={selected} onSelect={setSelected} />
            ) : (
              <p className="grid h-full place-items-center text-sm text-muted-foreground">No callers to draw.</p>
            )}
          </section>

          {/* people */}
          <Tile title="People to page" Icon={Users} className="md:col-span-3 lg:col-span-4" aside={<span className="text-muted-foreground">who_knows</span>}>
            {people.data?.items.length ? (
              <ul className="space-y-2">
                {people.data.items.slice(0, 6).map((p) => (
                  <li key={p.handle} className="flex items-center gap-2 text-sm">
                    <span className="grid size-7 shrink-0 place-items-center rounded-full bg-gold/15 font-mono text-[11px] text-gold">{p.handle.slice(0, 2).toUpperCase()}</span>
                    <span className="min-w-0"><span className="block truncate">{p.name ?? p.handle}</span><span className="block truncate font-mono text-[11px] text-muted-foreground">@{p.handle} · {p.via.join(", ").toLowerCase().replaceAll("_", " ")}</span></span>
                    <span className="ml-auto font-mono text-[11px] text-muted-foreground" title="score: one point per reason">{p.score}</span>
                  </li>
                ))}
              </ul>
            ) : <p className="text-xs text-muted-foreground">{people.loading ? "Loading…" : "No owner, fixer or author recorded."}</p>}
            {owners.length > 0 && <p className="mt-3 border-t border-border pt-2 text-[11px] text-muted-foreground">Teams it pages: {owners.join(", ")}</p>}
          </Tile>

          {/* try it */}
          <Tile title="Try it" Icon={FlaskConical} className="md:col-span-3 lg:col-span-4">
            <p className="mb-2 text-xs text-muted-foreground">Run the Fault Simulator on {d.service}, per fault kind:</p>
            <div className="grid grid-cols-3 gap-1.5">
              {KINDS.map((k) => (
                <Link key={k} href={withEnv(`/simulate?service=${encodeURIComponent(d.service)}&kind=${k}`, env)} className="rounded-md border border-border px-2 py-1.5 text-center text-xs hover:border-gold/50 hover:text-gold">{k}</Link>
              ))}
            </div>
          </Tile>

          {/* past incidents */}
          <Tile title="Incidents rooted here" Icon={History} className="md:col-span-6 lg:col-span-5"
            aside={d.past_incidents.length > 0 && <Link className="text-signal hover:underline" href={withEnv(`/incidents?cause=${encodeURIComponent(service!)}`, env)}>all →</Link>}>
            {past.data?.items.length ? (
              <ul className="divide-y divide-border/60">
                {past.data.items.map((i) => (
                  <li key={i.id} className="py-2">
                    <Link href={withEnv(`/incident/${encodeURIComponent(i.id)}`, env)} className="flex items-center gap-2 text-xs hover:text-gold">
                      <StatusPill status={i.status} /><span className="truncate font-mono">{i.id}</span><span className="ml-auto shrink-0 text-muted-foreground">{relTime(i.opened_at)}</span>
                    </Link>
                    {i.root_cause && <OpLabel op={i.root_cause} className="mt-1 text-[11px]" />}
                  </li>
                ))}
              </ul>
            ) : <p className="text-xs text-muted-foreground">{past.loading ? "Loading…" : "None: no incident has been rooted at this service yet."}</p>}
          </Tile>

          {/* changes */}
          <Tile title="Changes · 7 days" Icon={GitCommitHorizontal} className="md:col-span-3 lg:col-span-4">
            {changes.data?.items.length ? (
              <ol className="relative space-y-3 border-l border-border pl-3">
                {changes.data.items.slice(0, 6).map((c) => (
                  <li key={c.id} className="relative text-xs">
                    <span className="absolute top-1 -left-[17px] size-2 rounded-full bg-st-supported" aria-hidden />
                    <p className="flex gap-2"><span className="rounded bg-st-supported/12 px-1.5 text-[10px] text-st-supported">{c.type}</span><span className="ml-auto text-muted-foreground">{relTime(new Date(c.ts * 1000).toISOString())}</span></p>
                    <p className="mt-0.5 font-mono">{c.summary}</p>
                  </li>
                ))}
              </ol>
            ) : <p className="text-xs text-muted-foreground">{changes.loading ? "Loading…" : "No deploys, config or flag changes recorded."}</p>}
          </Tile>

          {/* runbooks */}
          <Tile title="Runbooks" Icon={BookOpenCheck} className="md:col-span-3 lg:col-span-3">
            {books.data?.items.length ? (
              <ul className="space-y-3">
                {books.data.items.map((b) => (
                  <li key={b.id} className="text-xs">
                    <p className="font-mono text-paper">{b.id}{b.kind && <span className="text-muted-foreground"> · {b.kind}</span>}</p>
                    <ol className="mt-1 list-decimal space-y-0.5 pl-4 text-muted-foreground">
                      {b.steps.map((s, i) => <li key={i}>{s}{b.success[String(i)] ? <span className="text-st-confirmed"> · fixed {b.success[String(i)]}×</span> : null}</li>)}
                    </ol>
                  </li>
                ))}
              </ul>
            ) : <p className="text-xs text-muted-foreground">{books.loading ? "Loading…" : "No runbook for this service (seed/runbooks.yaml)."}</p>}
          </Tile>

          {/* traffic */}
          <Tile title="Who calls it" Icon={Zap} className="md:col-span-6 lg:col-span-12" aside={<span className="text-muted-foreground">last 24 h · rps · errors · p95</span>}>
            {inbound.length ? (
              <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
                {inbound.map((e) => (
                  <div key={`${e.src}>${e.dst}`} className="rounded-lg border border-border bg-background/40 p-2.5 text-xs">
                    <OpLabel op={e.src} />
                    <p className="mt-0.5 flex items-center gap-1 text-muted-foreground"><ArrowRight className="size-3" /> <span className="truncate font-mono">{opTitle(e.dst)}</span></p>
                    <p className="mt-1.5 flex gap-3 font-mono tabular-nums">
                      <span>{(e.rps ?? 0).toFixed(2)} rps</span>
                      <span className={(e.err_rate ?? 0) > 0.05 ? "text-st-refuted" : "text-muted-foreground"}>{((e.err_rate ?? 0) * 100).toFixed(1)}% err</span>
                      <span className="text-muted-foreground">{e.p95_ms != null ? `${Math.round(e.p95_ms)} ms` : "—"}</span>
                    </p>
                  </div>
                ))}
              </div>
            ) : <p className="text-xs text-muted-foreground">No direct callers with traffic.</p>}
          </Tile>
        </div>
      )}
    </main>
  );
}
