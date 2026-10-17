"use client";

import { Crown, FlaskConical, GitCommitHorizontal, GitFork, History, Loader2, Network, Search, TriangleAlert, Users } from "@/components/icons";
import dynamic from "next/dynamic";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useMemo, useState } from "react";

import { DataView } from "@/components/graph/data-view";
import { FlowGraph, type GNode, opTitle } from "@/components/graph/flow-graph";
import { useGraphMode, ViewToggle } from "@/components/graph/view-toggle";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api, call, type S } from "@/lib/api";
import { relTime } from "@/lib/format";
import { fromTopology } from "@/lib/graph-data";
import { useEnv, useQuery, withEnv } from "@/lib/hooks";
import { cn } from "@/lib/utils";

type Level = "service" | "operation";
// canvas + d3-force: client only, and only fetched when the Network view is opened
const ForceNetwork = dynamic(() => import("@/components/graph/force-graph"), { ssr: false });

function Side({ n, t, env, onClose }: { n: S["TopologyNode"]; t: S["Topology"]; env: string | null; onClose: () => void }) {
  const inbound = t.edges.filter((e) => e.dst === n.id);
  const outbound = t.edges.filter((e) => e.src === n.id);
  const rps = inbound.reduce((s, e) => s + (e.rps ?? 0), 0);
  const incidents = [...new Set(n.anomalies.map((a) => a.incident))];
  const changes = useQuery(`map:changes:${env}:${n.service}`, () =>
    call(api.GET("/api/v1/services/{service}/changes", { params: { path: { service: n.service }, query: { env: env ?? undefined, hours: 24 } } })),
  );
  return (
    <aside className="epi-in z-20 flex min-h-0 flex-col gap-4 overflow-y-auto border-border bg-background p-4 max-lg:absolute max-lg:inset-x-0 max-lg:bottom-0 max-lg:max-h-[55%] max-lg:rounded-t-2xl max-lg:border-t max-lg:shadow-[0_-12px_40px_rgba(0,0,0,0.6)] lg:border-l" aria-label="Selected node">
      <div className="flex items-start gap-2">
        <div className="min-w-0">
          <p className="font-mono text-xs text-muted-foreground">{t.level === "operation" ? n.service : "service"}</p>
          <h2 className="truncate font-mono text-base font-semibold" title={n.id}>{t.level === "operation" ? opTitle(n.id) : n.id}</h2>
        </div>
        <button onClick={onClose} className="ml-auto text-muted-foreground hover:text-foreground" aria-label="Close">✕</button>
      </div>
      <dl className="grid grid-cols-2 gap-x-3 gap-y-1.5 text-xs">
        <dt className="text-muted-foreground">Kind</dt><dd>{n.kind ?? "—"}</dd>
        <dt className="text-muted-foreground">Owner</dt><dd className="flex items-center gap-1"><Users className="size-3" aria-hidden /> {n.owner ?? "none recorded"}</dd>
        {n.ops != null && (<><dt className="text-muted-foreground">Operations</dt><dd className="font-mono">{n.ops}</dd></>)}
        <dt className="text-muted-foreground">Inbound</dt><dd className="font-mono">{rps.toFixed(2)} rps · {inbound.length} caller{inbound.length === 1 ? "" : "s"}</dd>
        <dt className="text-muted-foreground">Calls out to</dt><dd className="font-mono">{outbound.length}</dd>
      </dl>
      <section>
        <h3 className="mb-1.5 flex items-center gap-1.5 text-[11px] font-semibold tracking-wider text-muted-foreground uppercase"><TriangleAlert className="size-3.5" aria-hidden /> Anomalies now</h3>
        {n.anomalies.length ? (
          <ul className="space-y-1 text-xs">
            {n.anomalies.map((a, i) => (
              <li key={i} className="flex items-center gap-2">
                <span className="rounded bg-st-refuted/15 px-1.5 py-0.5 text-st-refuted">{String(a.kind)}</span>
                <Link href={withEnv(`/incident/${encodeURIComponent(String(a.incident))}`, env)} className="truncate font-mono text-signal hover:underline">{String(a.incident)}</Link>
                <span className="ml-auto font-mono text-muted-foreground">{Number(a.score).toFixed(2)}</span>
              </li>
            ))}
          </ul>
        ) : <p className="text-xs text-muted-foreground">None in unresolved incidents.</p>}
      </section>
      <section>
        <h3 className="mb-1.5 flex items-center gap-1.5 text-[11px] font-semibold tracking-wider text-muted-foreground uppercase"><GitCommitHorizontal className="size-3.5" aria-hidden /> Recent changes · 24 h</h3>
        {changes.data?.items.length ? (
          <ul className="space-y-1.5 text-xs">
            {changes.data.items.map((c) => (
              <li key={c.id}>
                <p className="flex items-center gap-2"><span className="rounded bg-signal/10 px-1.5 py-0.5 text-signal">{c.type}</span><span className="ml-auto text-muted-foreground">{relTime(new Date(c.ts * 1000).toISOString())}</span></p>
                <p className="mt-0.5 font-mono">{c.summary}{c.authors.length ? <span className="text-muted-foreground"> · {c.authors.join(", ")}</span> : null}</p>
              </li>
            ))}
          </ul>
        ) : <p className="text-xs text-muted-foreground">{changes.loading ? "Loading…" : changes.error ? "Couldn't load changes." : "None in the last 24 h."}</p>}
      </section>
      {n.root_cause_of.length > 0 && (
        <section>
          <h3 className="mb-1.5 flex items-center gap-1.5 text-[11px] font-semibold tracking-wider text-st-confirmed uppercase"><Crown className="size-3.5" aria-hidden /> Root cause of</h3>
          <ul className="space-y-1">{n.root_cause_of.map((i) => <li key={i}><Link className="font-mono text-xs text-signal hover:underline" href={withEnv(`/incident/${encodeURIComponent(i)}`, env)}>{i}</Link></li>)}</ul>
        </section>
      )}
      <div className="mt-auto grid gap-2">
        <Button asChild variant="outline" size="sm"><Link href={withEnv(`/blast-radius?service=${encodeURIComponent(n.service)}`, env)}><GitFork className="size-3.5" /> Blast radius</Link></Button>
        <Button asChild variant="outline" size="sm"><Link href={withEnv(`/simulate?service=${encodeURIComponent(n.id)}`, env)}><FlaskConical className="size-3.5" /> What-if</Link></Button>
        <Button asChild variant="ghost" size="sm"><Link href={withEnv(`/incidents?cause=${encodeURIComponent(n.service)}`, env)}><History className="size-3.5" /> Past incidents{incidents.length ? ` · ${incidents.length} open` : ""}</Link></Button>
      </div>
    </aside>
  );
}

export default function MapPage() {
  const [env] = useEnv();
  const params = useSearchParams();
  const router = useRouter();
  const [mode, setMode] = useGraphMode();
  const level: Level = params.get("level") === "operation" ? "operation" : "service";
  const [selected, setSelected] = useState<string | null>(null);
  const [focus, setFocus] = useState<string | null>(null);
  const [q, setQ] = useState("");
  // double-click: only the nodes within `hops` of `center` (1 → 3 on repeat), the map's "expand neighbours"
  const [hood, setHood] = useState<{ center: string; hops: number } | null>(null);
  const topo = useQuery(`map:${env}:${level}`, () =>
    call(api.GET("/api/v1/graph/topology", { params: { query: { env: env ?? undefined, level } } })),
  );
  const t = topo.data;
  const net = useQuery(mode === "network" ? `explore:${env}` : null, () =>
    call(api.GET("/api/v1/graph/explore", { params: { query: { env: env ?? undefined, limit: 1500 } } })),
  );

  const setLevel = (l: Level) => {
    const p = new URLSearchParams(params.toString());
    if (l === "operation") p.set("level", l);
    else p.delete("level");
    setSelected(null);
    setHood(null);
    router.replace(`/map${p.size ? `?${p}` : ""}`, { scroll: false });
  };

  const near = useMemo(() => {
    if (!t || !hood) return null;
    const seen = new Set([hood.center]);
    let ring = [hood.center];
    for (let h = 0; h < hood.hops; h++) {
      ring = t.edges.flatMap((e) => (ring.includes(e.src) ? [e.dst] : ring.includes(e.dst) ? [e.src] : [])).filter((x) => !seen.has(x));
      ring.forEach((x) => seen.add(x));
    }
    return seen;
  }, [t, hood]);
  const expand = (id: string) => {
    setHood((h) => (h?.center === id ? { center: id, hops: Math.min(3, h.hops + 1) } : { center: id, hops: 1 }));
    setSelected(id);
    setFocus(id);
  };

  const { nodes, edges } = useMemo(() => {
    if (!t) return { nodes: [] as GNode[], edges: [] };
    const inRps: Record<string, number> = {};
    for (const e of t.edges) inRps[e.dst] = (inRps[e.dst] ?? 0) + (e.rps ?? 0);
    const max = Math.max(0, ...Object.values(inRps));
    const nodes: GNode[] = t.nodes.filter((n) => !near || near.has(n.id)).map((n) => ({
      id: n.id,
      service: n.service,
      title: t.level === "operation" ? opTitle(n.id) : n.id,
      kicker: t.level === "service" ? (n.kind ?? "service") : undefined,
      sub: [n.owner, t.level === "service" && n.ops != null ? `${n.ops} op${n.ops === 1 ? "" : "s"}` : null, inRps[n.id] ? `${inRps[n.id].toFixed(2)} rps` : null].filter(Boolean).join(" · "),
      tone: n.root_cause_of.length ? "root" : n.anomalies.length ? "anomaly" : null,
      badge: n.anomalies.length ? `${n.anomalies.length} anomal${n.anomalies.length === 1 ? "y" : "ies"}` : n.kind === "datastore" ? "datastore" : undefined,
      meter: max ? (inRps[n.id] ?? 0) / max : undefined,
    }));
    return { nodes, edges: near ? t.edges.filter((e) => near.has(e.src) && near.has(e.dst)) : t.edges };
  }, [t, near]);
  const sel = t?.nodes.find((n) => n.id === selected) ?? null;
  const anomalous = t?.nodes.filter((n) => n.anomalies.length).length ?? 0;

  const find = (e: React.FormEvent) => {
    e.preventDefault();
    const hit = t?.nodes.find((n) => n.id === q) ?? t?.nodes.find((n) => n.id.toLowerCase().includes(q.toLowerCase()));
    if (hit) {
      setHood(null);
      setSelected(hit.id);
      setFocus(hit.id);
      if (mode === "data") setMode("graph");
    }
  };

  return (
    <main className="flex h-[calc(100vh-3.5rem)] flex-col">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2 border-b border-border px-4 py-2.5 lg:px-6">
        <h1 className="flex items-center gap-2 text-base font-semibold"><Network className="size-5 text-fog" aria-hidden /> Service map</h1>
        {t && (
          <span className="text-xs text-muted-foreground">
            {env ?? "default env"} · {t.nodes.length} {t.level === "service" ? "services" : "operations"} · {t.edges.length} calls
            {anomalous > 0 && <span className="text-st-refuted"> · {anomalous} anomalous</span>}
            {t.truncated && <span className="text-ov-missed"> · truncated</span>}
          </span>
        )}
        <div className="ml-auto flex flex-wrap items-center gap-2">
          <div role="radiogroup" aria-label="Zoom level" className="inline-flex rounded-lg border border-border p-0.5">
            {(["service", "operation"] as const).map((l) => (
              <button key={l} role="radio" aria-checked={level === l} onClick={() => setLevel(l)} className="rounded-md px-2.5 py-1 text-xs text-muted-foreground aria-checked:bg-accent aria-checked:text-foreground">
                {l === "service" ? "Services" : "Operations"}
              </button>
            ))}
          </div>
          <form onSubmit={find} className="relative">
            <Search className="pointer-events-none absolute top-1/2 left-2 size-3.5 -translate-y-1/2 text-muted-foreground" aria-hidden />
            <Input list="map-nodes" value={q} onChange={(e) => setQ(e.target.value)} placeholder="find…" aria-label="Find a node" className="h-8 w-48 pl-7 font-mono text-xs" />
            <datalist id="map-nodes">{t?.nodes.map((n) => <option key={n.id} value={n.id} />)}</datalist>
          </form>
          <ViewToggle mode={mode} onChange={setMode} network />
        </div>
      </div>
      <div className={cn("relative grid min-h-0 flex-1", sel && mode !== "data" ? "grid-cols-1 lg:grid-cols-[minmax(0,1fr)_300px]" : "grid-cols-1")}>
        <div className="relative min-h-[420px] bg-grid">
          {topo.error ? (
            <p className="grid h-full place-items-center text-sm text-st-refuted">{topo.error.message}</p>
          ) : !t ? (
            <div className="grid h-full place-items-center"><Loader2 className="size-6 animate-spin text-muted-foreground" aria-label="Loading map" /></div>
          ) : !t.nodes.length ? (
            <p className="grid h-full place-items-center text-sm text-muted-foreground">No topology yet: start an environment or replay an RCAEval case.</p>
          ) : mode === "network" ? (
            net.data ? (
              <ForceNetwork data={net.data} onSelect={(n) => { if (level === "service" ? n.label === "Service" : n.label === "Operation") setSelected(n.key); }} />
            ) : net.error ? (
              <p className="grid h-full place-items-center text-sm text-st-refuted">{net.error.message}</p>
            ) : (
              <div className="grid h-full place-items-center"><Loader2 className="size-6 animate-spin text-muted-foreground" aria-label="Loading the network" /></div>
            )
          ) : mode === "data" ? (
            <div className="h-full p-4"><DataView data={fromTopology(t)} name={`map-${env ?? "env"}-${t.level}`} selected={selected} onNode={(id) => { setSelected(id); setFocus(id); setMode("graph"); }} className="h-full" /></div>
          ) : (
            <>
              <FlowGraph key={hood ? `${hood.center}:${hood.hops}` : "all"} nodes={nodes} edges={edges} selected={selected} focus={focus} onSelect={setSelected} onExpand={expand} label="Service map: services and the calls between them" />
              {hood ? (
                <div className="absolute bottom-3 left-1/2 flex -translate-x-1/2 items-center gap-2 rounded-lg border border-signal/40 bg-card/90 px-3 py-1.5 text-xs backdrop-blur">
                  <span>Around <span className="font-mono">{t.level === "operation" ? opTitle(hood.center) : hood.center}</span> · {hood.hops} hop{hood.hops === 1 ? "" : "s"} · {nodes.length} nodes</span>
                  {hood.hops < 3 && <button onClick={() => expand(hood.center)} className="text-signal hover:underline">+1 hop</button>}
                  <button onClick={() => setHood(null)} className="text-muted-foreground hover:text-foreground">Show all</button>
                </div>
              ) : (
                <p className="pointer-events-none absolute bottom-3 left-1/2 -translate-x-1/2 rounded-lg border border-border bg-card/90 px-3 py-1.5 text-[11px] text-muted-foreground backdrop-blur">Double-click a node to show its neighbours</p>
              )}
              <div className="pointer-events-none absolute top-3 left-3 rounded-lg border border-border bg-card/90 px-3 py-2 text-[11px] text-muted-foreground backdrop-blur">
                <p className="flex items-center gap-1.5"><span className="size-2.5 rounded-sm ring-2 ring-st-refuted/60" /> anomaly in an unresolved incident (24 h)</p>
                <p className="flex items-center gap-1.5"><Crown className="size-3 text-st-confirmed" /> root cause of one</p>
                <p className="flex items-center gap-1.5"><span className="h-0.5 w-4 bg-signal/70" /> inbound traffic · edge width = rps, colour = errors</p>
              </div>
            </>
          )}
        </div>
        {sel && t && mode !== "data" && <Side n={sel} t={t} env={env} onClose={() => setSelected(null)} />}
      </div>
    </main>
  );
}
