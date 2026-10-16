"use client";

import { AlertTriangle, ArrowLeft, BellRing, Loader2, Play, RotateCcw, WifiOff } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";

import { IncidentCanvas, type Overlay, type Spotlight } from "@/components/graph/incident-canvas";
import { ActionsPanel, MemoryPanel, NotesBox, ResolveDialog } from "@/components/incident/act";
import { IncidentFacts, OverlayLegend, SuspectList, Timeline, WhyNot } from "@/components/incident/side";
import { ExplanationPanel, NoRootCauseCard, OpLabel, VerdictCard } from "@/components/incident/verdict";
import { StatusPill } from "@/components/status";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { api, ApiError, call, type S } from "@/lib/api";
import { apply, evidenceIndex, type Footprint, hydrate, merge, pathSets, type StreamEvent, type View } from "@/lib/incident-state";
import { useEnv, useQuery, withEnv } from "@/lib/hooks";
import { useIncidentStream } from "@/lib/useIncidentStream";

// events after which the server-side detail (verdict, explanation, actions, memory) is worth refetching
const REFRESH_ON = new Set(["verdict", "no_root_cause", "explanation", "action", "memory.similar", "incident.status"]);
const QUIET_RESUME_MS = 30_000;

function Section({ title, children, aside }: { title: string; children: React.ReactNode; aside?: React.ReactNode }) {
  return (
    <section className="space-y-2.5">
      <h2 className="flex items-center text-[11px] font-semibold tracking-wider text-muted-foreground uppercase">
        {title}
        <span className="ml-auto normal-case">{aside}</span>
      </h2>
      {children}
    </section>
  );
}

export default function IncidentPage() {
  const { id } = useParams<{ id: string }>();
  const incident = decodeURIComponent(id);
  const [env] = useEnv();
  const q = { env: env ?? undefined };

  const [view, setView] = useState<View | null>(null);
  const [loadErr, setLoadErr] = useState<ApiError | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [spot, setSpot] = useState<Spotlight | null>(null);
  const [activeCite, setActiveCite] = useState<string | null>(null);
  const [fp, setFp] = useState<S["FootprintOut"] | null>(null);
  const [lastEventAt, setLastEventAt] = useState(Date.now());
  const [now, setNow] = useState(Date.now());

  const detail = useQuery(`detail:${env}:${incident}`, () =>
    call(api.GET("/api/v1/incidents/{incident_id}", { params: { path: { incident_id: incident }, query: q } })),
  );

  const loadGraph = useCallback(
    () => call(api.GET("/api/v1/incidents/{incident_id}/graph", { params: { path: { incident_id: incident }, query: { env: env ?? undefined } } })),
    [incident, env],
  );
  useEffect(() => {
    setView(null);
    setLoadErr(null);
    loadGraph()
      .then((g) => setView(hydrate(g)))
      .catch((e) => setLoadErr(e instanceof ApiError ? e : new ApiError("CLIENT", String(e), 0)));
  }, [loadGraph]);

  // refetch the detail (and the graph's enrichment) shortly after a burst of meaningful events
  const refreshTimer = useRef<ReturnType<typeof setTimeout>>(undefined);
  const scheduleRefresh = useCallback(() => {
    clearTimeout(refreshTimer.current);
    refreshTimer.current = setTimeout(() => {
      detail.reload();
      loadGraph().then((g) => setView((v) => (v ? merge(v, g) : hydrate(g))));
    }, 600);
  }, [detail, loadGraph]);

  const onEvent = useCallback(
    (e: StreamEvent) => {
      setView((v) => (v ? apply(v, e) : v));
      setLastEventAt(Date.now());
      if (REFRESH_ON.has(e.event)) scheduleRefresh();
      if (e.event === "verdict") toast.success("Verdict", { description: String(e.data.root_cause ?? "") });
    },
    [scheduleRefresh],
  );
  const after = view ? view.lastSeq : null;
  const startAfter = useRef<number | null>(null);
  if (after !== null && startAfter.current === null) startAfter.current = after; // open once, from the snapshot
  const stream = useIncidentStream(incident, env, startAfter.current, onEvent);

  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 5000);
    return () => clearInterval(t);
  }, []);

  // Fault Simulator overlay for the selected suspect
  useEffect(() => {
    setFp(null);
    if (!selected) return;
    call(
      api.GET("/api/v1/incidents/{incident_id}/hypotheses/{hid}/footprint", {
        params: { path: { incident_id: incident, hid: selected }, query: { env: env ?? undefined } },
      }),
    )
      .then(setFp)
      .catch(() => setFp(null));
  }, [selected, incident, env, view?.run]);

  const overlay: Overlay | null = useMemo(() => {
    if (!selected || !view) return null;
    const live = view.footprints[selected] as Footprint | undefined;
    const src = fp ?? live;
    if (!src) return { hypothesis: selected, matched: new Set(), missed: new Set(), unexplained: new Set(), predicted: new Set() };
    return {
      hypothesis: selected,
      matched: new Set(src.matched),
      missed: new Set(src.missed),
      unexplained: new Set(src.unexplained),
      predicted: new Set(fp ? fp.predicted.map((p) => p.op) : []),
    };
  }, [selected, view, fp]);

  const evIdx = useMemo(() => (view ? evidenceIndex(view) : {}), [view]);
  const cite = (eid: string) => {
    const e = evIdx[eid];
    if (activeCite === eid || !e) {
      setActiveCite(null);
      setSpot(null);
      return;
    }
    setActiveCite(eid);
    setSelected(null);
    const p = pathSets(e.path.length ? e.path : [view!.hyps[e.hypothesis]?.op].filter(Boolean) as string[]);
    setSpot({ ...p, label: `${eid} · ${e.kind}` });
  };
  const spotlightPath = (ops: string[], label: string) => {
    setActiveCite(null);
    setSelected(null);
    setSpot({ ...pathSets(ops), label });
  };

  const inc = detail.data;
  const status = view?.status ?? inc?.status ?? "open";
  const quiet = status === "diagnosing" && now - lastEventAt > QUIET_RESUME_MS;
  const services = useMemo(() => [...new Set(Object.values(view?.nodes ?? {}).map((n) => n.service))], [view?.nodes]);

  const diagnose = async (force: boolean) => {
    try {
      await call(
        api.POST("/api/v1/incidents/{incident_id}/diagnose", {
          params: { path: { incident_id: incident }, query: { env: env ?? undefined, force } },
        }),
      );
      toast.message(force ? "New diagnosis run started" : "Diagnosis resumed", { description: "Watch the canvas." });
      setLastEventAt(Date.now());
      setSelected(null);
      setSpot(null);
    } catch (e) {
      toast.error("Couldn't start the diagnosis", { description: e instanceof ApiError ? e.message : String(e) });
    }
  };

  if (loadErr) {
    return (
      <main className="mx-auto max-w-xl px-4 py-24 text-center">
        <AlertTriangle className="mx-auto size-8 text-ov-missed" aria-hidden />
        <h1 className="mt-3 text-lg font-semibold">{loadErr.code === "INCIDENT_NOT_FOUND" ? "Incident not found" : loadErr.code === "GRAPH_UNAVAILABLE" ? "The graph is offline" : "Couldn't load the incident"}</h1>
        <p className="mt-1 font-mono text-sm text-muted-foreground">{loadErr.message}</p>
        <Button asChild variant="outline" className="mt-6"><Link href={withEnv("/", env)}><ArrowLeft className="size-4" /> All incidents</Link></Button>
      </main>
    );
  }

  const selHyp = selected && view ? view.hyps[selected] : null;
  const offCanvas = fp && view ? fp.missed.filter((o) => !view.nodes[o]) : [];

  return (
    <main className="flex h-[calc(100vh-3.5rem)] flex-col">
      {/* header strip */}
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2 border-b border-border px-4 py-2.5 lg:px-6">
        <Link href={withEnv("/", env)} className="text-muted-foreground hover:text-foreground" aria-label="All incidents">
          <ArrowLeft className="size-4" />
        </Link>
        <h1 className="font-mono text-sm font-semibold">{incident}</h1>
        <StatusPill status={status} />
        {view?.symptom && (
          <span className="flex min-w-0 items-center gap-1.5 text-xs text-muted-foreground">
            <BellRing className="size-3.5 text-primary" aria-hidden /> alert on <OpLabel op={view.symptom} className="text-foreground" />
          </span>
        )}
        <div className="ml-auto flex items-center gap-2">
          {stream === "reconnecting" && (
            <span className="flex items-center gap-1.5 rounded-full bg-ov-missed/12 px-2 py-0.5 text-xs text-ov-missed" role="status">
              <WifiOff className="size-3.5" aria-hidden /> reconnecting…
            </span>
          )}
          {stream === "live" && status === "diagnosing" && (
            <span className="flex items-center gap-1.5 text-xs text-primary" role="status">
              <span className="size-2 animate-pulse rounded-full bg-primary" aria-hidden /> live
            </span>
          )}
          {quiet ? (
            <Button size="sm" onClick={() => diagnose(false)}>
              <Play className="size-3.5" /> Resume diagnosis
            </Button>
          ) : (
            <Button size="sm" variant="outline" disabled={status === "diagnosing"} onClick={() => diagnose(status !== "open")}>
              {status === "diagnosing" ? <Loader2 className="size-3.5 animate-spin" /> : <RotateCcw className="size-3.5" />}
              {status === "open" ? "Diagnose" : "Rerun"}
            </Button>
          )}
          {inc && <ResolveDialog incident={incident} env={env} actions={inc.actions} status={status} onChanged={() => { detail.reload(); scheduleRefresh(); }} />}
        </div>
      </div>
      {inc?.gaps && inc.gaps.length > 0 && (
        <div className="border-b border-ov-missed/30 bg-ov-missed/10 px-6 py-1.5 text-xs text-ov-missed" role="status">
          {inc.gaps.join(", ")} unavailable for this window: suspects that needed them may end inconclusive.
        </div>
      )}

      <div className="grid min-h-0 flex-1 grid-cols-1 lg:grid-cols-[380px_minmax(0,1fr)_340px]">
        {/* left rail: verdict, explanation, memory, actions */}
        <aside className="min-h-0 space-y-6 overflow-y-auto border-r border-border p-4 max-lg:order-2" aria-label="Verdict and explanation">
          {!inc ? (
            <Skeleton className="h-64 w-full rounded-xl" />
          ) : inc.verdict ? (
            <VerdictCard v={inc.verdict} onPath={(p) => spotlightPath(p, "winning path")} />
          ) : inc.no_root_cause ? (
            <NoRootCauseCard n={inc.no_root_cause} />
          ) : (
            <div className="rounded-xl border border-dashed border-border p-4 text-sm text-muted-foreground">
              {status === "diagnosing" ? "Investigating: suspects are being checked against the graph…" : "No verdict yet."}
            </div>
          )}
          <Section title="Explanation">
            <ExplanationPanel explanation={inc?.explanation as never} onCite={cite} activeCite={activeCite} />
          </Section>
          <Section title="Seen before">
            <MemoryPanel similar={inc?.similar ?? []} env={env} />
          </Section>
          <Section title="Proposed actions">
            {inc && (
              <ActionsPanel
                incident={incident}
                env={env}
                actions={inc.actions}
                delivery={inc.delivery as never}
                status={status}
                onChanged={() => detail.reload()}
              />
            )}
          </Section>
        </aside>

        {/* canvas */}
        <div className="relative min-h-[420px] bg-grid max-lg:order-1">
          {view ? (
            Object.keys(view.nodes).length ? (
              <IncidentCanvas
                view={view}
                overlay={overlay}
                spotlight={spot}
                selected={selected}
                onSelect={(h) => {
                  setSpot(null);
                  setActiveCite(null);
                  setSelected(h);
                }}
              />
            ) : (
              <div className="grid h-full place-items-center text-sm text-muted-foreground">Nothing on the canvas yet: start a diagnosis.</div>
            )
          ) : (
            <div className="grid h-full place-items-center"><Loader2 className="size-6 animate-spin text-muted-foreground" aria-label="Loading graph" /></div>
          )}
          <div className="pointer-events-none absolute inset-x-3 top-3 flex items-start gap-2">
            {selHyp && (
              <div className="pointer-events-auto w-[330px]">
                <OverlayLegend hyp={selHyp} fp={fp ? { ...(fp as unknown as Footprint), missedOffCanvas: offCanvas } : null} onClear={() => setSelected(null)} />
              </div>
            )}
            {spot && (
              <button
                onClick={() => { setSpot(null); setActiveCite(null); }}
                className="pointer-events-auto ml-auto rounded-full bg-primary/15 px-3 py-1 text-xs text-primary ring-1 ring-primary/40 hover:bg-primary/25"
              >
                Showing {spot.label} · clear ✕
              </button>
            )}
          </div>
        </div>

        {/* right rail: suspects, why-not, timeline, notes */}
        <aside className="min-h-0 overflow-y-auto border-l border-border p-4 max-lg:order-3" aria-label="Suspects and timeline">
          <Tabs defaultValue="suspects">
            <TabsList className="sticky -top-4 z-10 w-full shadow-[0_-16px_0_var(--background)]">
              <TabsTrigger value="suspects">Suspects</TabsTrigger>
              <TabsTrigger value="timeline">Timeline{view?.timeline.length ? ` · ${view.timeline.length}` : ""}</TabsTrigger>
              <TabsTrigger value="notes">Notes</TabsTrigger>
            </TabsList>
            <TabsContent value="suspects" className="mt-4 space-y-6">
              <Section title="Why not…?">
                <WhyNot incident={incident} env={env} services={services} onPath={spotlightPath} />
              </Section>
              <Section title="Suspects" aside={<span className="text-muted-foreground">click to see what each would explain</span>}>
                <SuspectList hyps={Object.values(view?.hyps ?? {})} selected={selected} onSelect={(h) => { setSpot(null); setSelected(h === selected ? null : h); }} />
              </Section>
              {inc && (
                <Section title="Incident">
                  <IncidentFacts inc={inc} />
                </Section>
              )}
            </TabsContent>
            <TabsContent value="timeline" className="mt-4">
              <Timeline items={view?.timeline ?? []} />
            </TabsContent>
            <TabsContent value="notes" className="mt-4">
              <NotesBox incident={incident} env={env} services={services} onChanged={() => detail.reload()} />
            </TabsContent>
          </Tabs>
        </aside>
      </div>
    </main>
  );
}
