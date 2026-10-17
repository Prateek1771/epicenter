"use client";

import { Crown, FlaskConical, GitFork, History, Loader2, Network, Search, TriangleAlert, Users } from "@/components/icons";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useMemo, useState } from "react";

import { DataView } from "@/components/graph/data-view";
import { FlowGraph, type GNode, opTitle } from "@/components/graph/flow-graph";
import { useGraphMode, ViewToggle } from "@/components/graph/view-toggle";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api, call, type S } from "@/lib/api";
import { fromTopology } from "@/lib/graph-data";
import { useEnv, useQuery, withEnv } from "@/lib/hooks";
import { cn } from "@/lib/utils";

type Level = "service" | "operation";

function Side({ n, t, env, onClose }: { n: S["TopologyNode"]; t: S["Topology"]; env: string | null; onClose: () => void }) {
  const inbound = t.edges.filter((e) => e.dst === n.id);
  const outbound = t.edges.filter((e) => e.src === n.id);
  const rps = inbound.reduce((s, e) => s + (e.rps ?? 0), 0);
  const incidents = [...new Set(n.anomalies.map((a) => a.incident))];
  return (
    <aside className="epi-in flex min-h-0 flex-col gap-4 overflow-y-auto border-l border-border p-4" aria-label="Selected node">
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
  const topo = useQuery(`map:${env}:${level}`, () =>
    call(api.GET("/api/v1/graph/topology", { params: { query: { env: env ?? undefined, level } } })),
  );
  const t = topo.data;

  const setLevel = (l: Level) => {
    const p = new URLSearchParams(params.toString());
    if (l === "operation") p.set("level", l);
    else p.delete("level");
    setSelected(null);
    router.replace(`/map${p.size ? `?${p}` : ""}`, { scroll: false });
  };

  const { nodes, edges } = useMemo(() => {
    if (!t) return { nodes: [] as GNode[], edges: [] };
    const inRps: Record<string, number> = {};
    for (const e of t.edges) inRps[e.dst] = (inRps[e.dst] ?? 0) + (e.rps ?? 0);
    const max = Math.max(0, ...Object.values(inRps));
    const nodes: GNode[] = t.nodes.map((n) => ({
      id: n.id,
      service: n.service,
      title: t.level === "operation" ? opTitle(n.id) : n.id,
      kicker: t.level === "service" ? (n.kind ?? "service") : undefined,
      sub: [n.owner, t.level === "service" && n.ops != null ? `${n.ops} op${n.ops === 1 ? "" : "s"}` : null, inRps[n.id] ? `${inRps[n.id].toFixed(2)} rps` : null].filter(Boolean).join(" · "),
      tone: n.root_cause_of.length ? "root" : n.anomalies.length ? "anomaly" : null,
      badge: n.anomalies.length ? `${n.anomalies.length} anomal${n.anomalies.length === 1 ? "y" : "ies"}` : n.kind === "datastore" ? "datastore" : undefined,
      meter: max ? (inRps[n.id] ?? 0) / max : undefined,
    }));
    return { nodes, edges: t.edges };
  }, [t]);
  const sel = t?.nodes.find((n) => n.id === selected) ?? null;
  const anomalous = t?.nodes.filter((n) => n.anomalies.length).length ?? 0;

  const find = (e: React.FormEvent) => {
    e.preventDefault();
    const hit = t?.nodes.find((n) => n.id === q) ?? t?.nodes.find((n) => n.id.toLowerCase().includes(q.toLowerCase()));
    if (hit) {
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
          <ViewToggle mode={mode} onChange={setMode} />
        </div>
      </div>
      <div className={cn("grid min-h-0 flex-1", sel && mode === "graph" ? "grid-cols-1 lg:grid-cols-[minmax(0,1fr)_300px]" : "grid-cols-1")}>
        <div className="relative min-h-[420px] bg-grid">
          {topo.error ? (
            <p className="grid h-full place-items-center text-sm text-st-refuted">{topo.error.message}</p>
          ) : !t ? (
            <div className="grid h-full place-items-center"><Loader2 className="size-6 animate-spin text-muted-foreground" aria-label="Loading map" /></div>
          ) : !t.nodes.length ? (
            <p className="grid h-full place-items-center text-sm text-muted-foreground">No topology yet: start an environment or replay an RCAEval case.</p>
          ) : mode === "data" ? (
            <div className="h-full p-4"><DataView data={fromTopology(t)} name={`map-${env ?? "env"}-${t.level}`} selected={selected} onNode={(id) => { setSelected(id); setFocus(id); setMode("graph"); }} className="h-full" /></div>
          ) : (
            <>
              <FlowGraph nodes={nodes} edges={edges} selected={selected} focus={focus} onSelect={setSelected} label="Service map: services and the calls between them" />
              <div className="pointer-events-none absolute top-3 left-3 rounded-lg border border-border bg-card/90 px-3 py-2 text-[11px] text-muted-foreground backdrop-blur">
                <p className="flex items-center gap-1.5"><span className="size-2.5 rounded-sm ring-2 ring-st-refuted/60" /> anomaly in an unresolved incident (24 h)</p>
                <p className="flex items-center gap-1.5"><Crown className="size-3 text-st-confirmed" /> root cause of one</p>
                <p className="flex items-center gap-1.5"><span className="h-0.5 w-4 bg-signal/70" /> inbound traffic · edge width = rps, colour = errors</p>
              </div>
            </>
          )}
        </div>
        {sel && t && mode === "graph" && <Side n={sel} t={t} env={env} onClose={() => setSelected(null)} />}
      </div>
    </main>
  );
}
