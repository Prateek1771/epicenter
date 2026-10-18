"use client";

import { AlertTriangle, ArrowLeft, BellRing, Chats, ChevronLeft, History, Loader2, PanelRight, Play, RotateCcw, Search, MessageSquarePlus, WifiOff } from "@/components/icons";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";

import { DataView } from "@/components/graph/data-view";
import { IncidentCanvas, type Overlay, type Spotlight } from "@/components/graph/incident-canvas";
import { useGraphMode, ViewToggle } from "@/components/graph/view-toggle";
import { Chat } from "@/components/ask/chat";
import { ActionsPanel, DeliverMenu, ExportButtons, MemoryPanel, NotesBox, ResolveDialog } from "@/components/incident/act";
import { ExplainersCard } from "@/components/incident/explainers";
import { Lanes } from "@/components/incident/lanes";
import { QueryReceipts } from "@/components/incident/receipts";
import { IncidentFacts, OverlayLegend, SuspectList, Timeline, WhyNot } from "@/components/incident/side";
import { CouldntSee, ExplanationPanel, NoRootCauseCard, OpLabel, RuledOutList, TMinusStrip, VerdictCard } from "@/components/incident/verdict";
import { StatusPill } from "@/components/status";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { api, ApiError, call, type S } from "@/lib/api";
import { fromView } from "@/lib/graph-data";
import { apply, evidenceIndex, type Footprint, hydrate, merge, pathSets, type StreamEvent, type View } from "@/lib/incident-state";
import { notYet, ruledOut, tMinus } from "@/lib/investigation";
import { useEnv, useQuery, withEnv } from "@/lib/hooks";
import { useIncidentStream } from "@/lib/useIncidentStream";

// events after which the server-side detail (verdict, explanation, actions, memory) is worth refetching
const REFRESH_ON = new Set(["verdict", "no_root_cause", "explanation", "action", "memory.similar", "incident.status"]);
const QUIET_RESUME_MS = 30_000;
const PANEL_KEY = "epi:incident-panel"; // per viewer: the right panel open / closed (closed by default)
const TABS = [
  { id: "suspects", label: "Suspects", Icon: Search },
  { id: "timeline", label: "Timeline", Icon: History },
  { id: "notes", label: "Notes", Icon: MessageSquarePlus },
  { id: "chat", label: "Chat", Icon: Chats },
] as const;
type Tab = (typeof TABS)[number]["id"];

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
  const [mode, setMode] = useGraphMode();
  const [cutoff, setCutoff] = useState<number | null>(null); // onset slicer
  const [explainOp, setExplainOp] = useState<string | null>(null); // symptom → suspects
  const [fps, setFps] = useState<Record<string, S["FootprintOut"]>>({}); // every suspect's footprint, fetched lazily
  const [fpsLoading, setFpsLoading] = useState(false);
  const [lastEventAt, setLastEventAt] = useState(Date.now());
  const [panel, setPanel] = useState(false);
  const [tab, setTab] = useState<Tab>("suspects");
  useEffect(() => {
    try {
      setPanel(localStorage.getItem(PANEL_KEY) === "open");
    } catch {}
  }, []);
  const openPanel = (open: boolean, t?: Tab) => {
    setPanel(open);
    if (t) setTab(t);
    try {
      localStorage.setItem(PANEL_KEY, open ? "open" : "closed");
    } catch {}
  };
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
    // a replay just started from /runs or the sample button: its incident appears once ingest finishes, so wait
    let tries = 0;
    let timer: ReturnType<typeof setTimeout>;
    let live = true;
    const load = () =>
      loadGraph()
        .then((g) => {
          if (!live) return;
          setView(hydrate(g));
          if (tries) detail.reload();
        })
        .catch((e) => {
          if (!live) return;
          const err = e instanceof ApiError ? e : new ApiError("CLIENT", String(e), 0);
          if (err.code === "INCIDENT_NOT_FOUND" && tries++ < 75) timer = setTimeout(load, 2000); // ~150 s: a first RCAEval run downloads, then ingests
          else setLoadErr(err);
        });
    load();
    return () => {
      live = false;
      clearTimeout(timer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- `detail` changes every render; reload is only needed once
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

  // symptom → suspects: every suspect's footprint, fetched once per run when first needed
  useEffect(() => setFps({}), [view?.run]);
  useEffect(() => {
    if (!explainOp || !view) return;
    const missing = Object.keys(view.hyps).filter((h) => !fps[h]);
    if (!missing.length) return;
    let live = true;
    setFpsLoading(true);
    Promise.all(
      missing.map((hid) =>
        call(api.GET("/api/v1/incidents/{incident_id}/hypotheses/{hid}/footprint", { params: { path: { incident_id: incident, hid }, query: { env: env ?? undefined } } }))
          .then((f) => [hid, f] as const)
          .catch(() => null),
      ),
    ).then((rows) => {
      if (!live) return;
      setFps((cur) => ({ ...cur, ...Object.fromEntries(rows.filter((r) => r !== null)) }));
      setFpsLoading(false);
    });
    return () => {
      live = false;
    };
  }, [explainOp, view, fps, incident, env]);

  const ruled = useMemo(() => (view ? ruledOut(view) : []), [view]);
  const later = useMemo(() => (view ? notYet(view, cutoff) : undefined), [view, cutoff]);
  const strip = useMemo(() => {
    const c = detail.data?.verdict?.change;
    return view ? tMinus(view, c ? { ts: Math.round(Date.parse(c.ts) / 1000), summary: c.summary, type: c.type } : null) : null;
  }, [view, detail.data?.verdict?.change]);
  const data = useMemo(() => (view && mode === "data" ? fromView(view) : null), [view, mode]);

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
  const loaded = Boolean(view?.status ?? inc?.status); // until then, no pill and no Diagnose/Rerun: not "open" by default
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
        <Button asChild variant="outline" className="mt-6"><Link href={withEnv("/incidents", env)}><ArrowLeft className="size-4" /> All incidents</Link></Button>
      </main>
    );
  }

  const selHyp = selected && view ? view.hyps[selected] : null;
  const offCanvas = fp && view ? fp.missed.filter((o) => !view.nodes[o]) : [];

  return (
    <main className="flex flex-col lg:h-[calc(100vh-3.5rem)]">
      {/* header strip */}
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2 border-b border-border px-4 py-2.5 lg:px-6">
        <Link href={withEnv("/incidents", env)} className="text-muted-foreground hover:text-foreground" aria-label="All incidents">
          <ArrowLeft className="size-4" />
        </Link>
        <h1 className="min-w-0 truncate font-mono text-sm font-semibold not-italic">{incident}</h1>
        {loaded && <StatusPill status={status} />}
        {view?.symptom && (
          <span className="flex min-w-0 items-center gap-1.5 text-xs text-muted-foreground">
            <BellRing className="size-3.5 text-signal" aria-hidden /> alert on <OpLabel op={view.symptom} className="text-foreground" />
          </span>
        )}
        <div data-tour="act" className="flex w-full flex-wrap items-center gap-2 sm:ml-auto sm:w-auto">
          {stream === "reconnecting" && (
            <span className="flex items-center gap-1.5 rounded-full bg-ov-missed/12 px-2 py-0.5 text-xs text-ov-missed" role="status">
              <WifiOff className="size-3.5" aria-hidden /> reconnecting…
            </span>
          )}
          {stream === "live" && status === "diagnosing" && (
            <span className="flex items-center gap-1.5 text-xs text-signal" role="status">
              <span className="size-2 animate-pulse rounded-full bg-signal" aria-hidden /> live
            </span>
          )}
          {!loaded ? null : quiet ? (
            <Button size="sm" onClick={() => diagnose(false)}>
              <Play className="size-3.5" /> Resume diagnosis
            </Button>
          ) : (
            <Button size="sm" variant={status === "open" ? "default" : "outline"} disabled={status === "diagnosing"} onClick={() => diagnose(status !== "open")}>
              {status === "diagnosing" ? <Loader2 className="size-3.5 animate-spin" /> : <RotateCcw className="size-3.5" />}
              {status === "open" ? "Diagnose" : "Rerun"}
            </Button>
          )}
          {inc && <DeliverMenu incident={incident} env={env} delivery={inc.delivery as never} status={status} onChanged={() => detail.reload()} />}
          {inc && <ResolveDialog incident={incident} env={env} actions={inc.actions} status={status} onChanged={() => { detail.reload(); scheduleRefresh(); }} />}
        </div>
      </div>
      {inc?.gaps && inc.gaps.length > 0 && (
        <div className="border-b border-ov-missed/30 bg-ov-missed/10 px-6 py-1.5 text-xs text-ov-missed" role="status">
          {inc.gaps.join(", ")} unavailable for this window: see &ldquo;Couldn&apos;t see&rdquo; on the verdict.
        </div>
      )}

      <div className={`grid grid-cols-1 lg:min-h-0 lg:flex-1 ${panel ? "lg:grid-cols-[360px_minmax(0,1fr)_380px]" : "lg:grid-cols-[360px_minmax(0,1fr)_48px]"}`}>
        {/* left rail: verdict, explanation, memory, actions */}
        <aside className="space-y-6 border-border p-4 max-lg:order-2 max-lg:border-t lg:min-h-0 lg:overflow-y-auto lg:border-r" aria-label="Verdict and explanation">
          {!inc ? (
            <Skeleton className="h-64 w-full rounded-xl" />
          ) : inc.verdict ? (
            <VerdictCard v={inc.verdict} weights={inc.weights_version} onPath={(p) => spotlightPath(p, "winning path")}>
              {strip && <TMinusStrip t={strip} />}
              <RuledOutList items={ruled} onPath={spotlightPath} />
              <CouldntSee gaps={inc.gaps} />
            </VerdictCard>
          ) : inc.no_root_cause ? (
            <NoRootCauseCard n={inc.no_root_cause}>
              <RuledOutList items={ruled} onPath={spotlightPath} />
              <CouldntSee gaps={inc.gaps} />
            </NoRootCauseCard>
          ) : (
            <div className="rounded-xl border border-dashed border-border p-4 text-sm text-muted-foreground">
              {status === "diagnosing" ? "Investigating: suspects are being checked against the graph…" : "No verdict yet."}
              <CouldntSee gaps={inc.gaps} />
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
              <ActionsPanel env={env} actions={inc.actions} delivery={inc.delivery as never} />
            )}
          </Section>
        </aside>

        {/* canvas (Graph) or its tables (Data), with the timeline lanes underneath */}
        <div className="flex flex-col max-lg:order-1 lg:min-h-[420px]">
          <div data-tour="canvas" className="relative h-[60vh] min-h-[360px] bg-grid lg:h-auto lg:min-h-0 lg:flex-1">
            {!view ? (
              <div className="grid h-full place-items-center"><Loader2 className="size-6 animate-spin text-muted-foreground" aria-label="Loading graph" /></div>
            ) : !Object.keys(view.nodes).length ? (
              <div className="grid h-full place-items-center text-sm text-muted-foreground">Nothing on the canvas yet: start a diagnosis.</div>
            ) : mode === "data" && data ? (
              <div className="h-full p-3 pt-14">
                <DataView
                  data={data}
                  name={`${incident}-run${view.run ?? 0}`}
                  selected={selected ? view.hyps[selected]?.op : null}
                  onNode={(op) => {
                    const h = Object.values(view.hyps).find((x) => x.op === op);
                    setSpot(h ? null : { ...pathSets([op]), label: op });
                    setSelected(h?.id ?? null);
                    setMode("graph");
                  }}
                  className="h-full"
                />
              </div>
            ) : (
              <IncidentCanvas
                view={view}
                overlay={overlay}
                spotlight={spot}
                selected={selected}
                later={later}
                onSelect={(h, op) => {
                  setSpot(null);
                  setActiveCite(null);
                  setSelected(h);
                  // a broken operation that isn't a suspect: which suspects would explain it?
                  setExplainOp(!h && op && view.nodes[op]?.anomaly ? op : null);
                }}
              />
            )}
            <div className="pointer-events-none absolute inset-x-3 top-3 flex items-start gap-2">
              {mode === "graph" && selHyp && (
                <div className="pointer-events-auto w-full max-w-[330px]">
                  <OverlayLegend hyp={selHyp} fp={fp ? { ...(fp as unknown as Footprint), missedOffCanvas: offCanvas } : null} onClear={() => setSelected(null)} />
                </div>
              )}
              {mode === "graph" && !selHyp && explainOp && view && (
                <div className="pointer-events-auto w-full max-w-[330px]">
                  <ExplainersCard
                    view={view}
                    op={explainOp}
                    footprints={fps}
                    loading={fpsLoading}
                    onPick={(hid) => { setExplainOp(null); setSelected(hid); }}
                    onClose={() => setExplainOp(null)}
                  />
                </div>
              )}
              <div className="pointer-events-auto ml-auto flex items-center gap-2">
                {spot && mode === "graph" && (
                  <button
                    onClick={() => { setSpot(null); setActiveCite(null); }}
                    className="rounded-full bg-signal/15 px-3 py-1 text-xs text-signal ring-1 ring-signal/40 hover:bg-signal/25"
                  >
                    Showing {spot.label} · clear ✕
                  </button>
                )}
                {view && Object.keys(view.nodes).length > 0 && <ViewToggle mode={mode} onChange={setMode} />}
              </div>
            </div>
          </div>
          {view && mode === "graph" && (
            <Lanes
              view={view}
              cutoff={cutoff}
              onCutoff={setCutoff}
              active={spot && spot.ops.size === 1 ? [...spot.ops][0] : null}
              onLane={(op) => {
                setSelected(null);
                setActiveCite(null);
                setSpot({ ...pathSets([op]), label: op });
                setExplainOp(op); // every lane is a symptom: which suspects predicted it?
              }}
            />
          )}
        </div>

        {/* right rail: collapsed to icons by default (lg+); suspects, why-not, timeline, notes, chat, downloads */}
        {!panel && (
          <nav className="hidden flex-col items-center gap-1 border-l border-border py-3 lg:flex" aria-label="Incident panel">
            <button onClick={() => openPanel(true)} className="mb-2 rounded-md p-2 text-muted-foreground hover:bg-accent hover:text-foreground" aria-label="Open the panel" title="Open the panel">
              <ChevronLeft className="size-4" />
            </button>
            {TABS.map(({ id, label, Icon }) => (
              <button key={id} onClick={() => openPanel(true, id)} className="rounded-md p-2 text-muted-foreground hover:bg-accent hover:text-gold" aria-label={label} title={label}>
                <Icon className="size-4" />
              </button>
            ))}
          </nav>
        )}
        <aside className={`border-border p-4 max-lg:order-3 max-lg:border-t lg:min-h-0 lg:overflow-y-auto lg:border-l ${panel ? "" : "lg:hidden"}`} aria-label="Suspects, timeline, notes and chat">
          <div className="mb-3 flex items-center gap-2">
            <button onClick={() => openPanel(false)} className="hidden rounded-md p-1.5 text-muted-foreground hover:bg-accent hover:text-foreground lg:block" aria-label="Collapse the panel" title="Collapse">
              <PanelRight className="size-4" />
            </button>
            <ExportButtons incident={incident} env={env} className="flex-1" />
          </div>
          <Tabs value={tab} onValueChange={(v) => setTab(v as Tab)}>
            <TabsList className="sticky -top-4 z-10 w-full shadow-[0_-16px_0_var(--background)]">
              <TabsTrigger value="suspects">Suspects</TabsTrigger>
              <TabsTrigger value="timeline">Timeline{view?.timeline.length ? ` · ${view.timeline.length}` : ""}</TabsTrigger>
              <TabsTrigger value="notes">Notes</TabsTrigger>
              <TabsTrigger value="chat">Chat</TabsTrigger>
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
            <TabsContent value="timeline" className="mt-4 space-y-4">
              <QueryReceipts r={view?.receipts ?? null} />
              <Timeline items={view?.timeline ?? []} />
            </TabsContent>
            <TabsContent value="notes" className="mt-4">
              <NotesBox incident={incident} env={env} services={services} onChanged={() => detail.reload()} />
            </TabsContent>
            <TabsContent value="chat" className="mt-4 h-[70vh] shrink-0 lg:h-[calc(100vh-15rem)]">
              <Chat incident={incident} compact />
            </TabsContent>
          </Tabs>
        </aside>
      </div>
    </main>
  );
}
