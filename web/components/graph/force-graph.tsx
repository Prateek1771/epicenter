"use client";

// Loaded with next/dynamic (ssr: false): force-graph touches `window` at import.
import { Maximize, Search } from "@/components/icons";
import { useEffect, useMemo, useRef, useState } from "react";
import ForceGraph2D, { type ForceGraphMethods, type LinkObject, type NodeObject } from "react-force-graph-2d";

import { Input } from "@/components/ui/input";
import type { S } from "@/lib/api";
import { cn } from "@/lib/utils";

// Canvas can't read CSS tokens cheaply per frame: the palette, as hex. Topology warm, incident artefacts cool.
const LABEL_COLOR: Record<string, string> = {
  Service: "#e6c77d",
  Operation: "#b8a26a",
  Team: "#d8c79c",
  Person: "#f6f3e4",
  Incident: "#e5484d",
  Hypothesis: "#f59e0b",
  Evidence: "#7c8a9a",
  Anomaly: "#ff7a6b",
  Change: "#3dd68c",
  Runbook: "#60a5fa",
  Action: "#a78bfa",
  Alert: "#f472b6",
  Explanation: "#94a3b8",
  Run: "#6b675c",
  Simulation: "#22d3ee",
};
const OTHER = "#9d998c";
const color = (label: string) => LABEL_COLOR[label] ?? OTHER;
const SIZE: Record<string, number> = { Service: 7, Incident: 6, Team: 5, Person: 4.5 };

type N = { id: string; label: string; name: string; props: Record<string, unknown> };
type L = { type: string; props: Record<string, unknown> };

function title(n: S["GraphNode"]): string {
  const p = n.props as Record<string, unknown>;
  const key = String(p.key ?? n.id.split(":").slice(1).join(":"));
  return n.label === "Operation" ? key.split("/").slice(1).join("/") || key : String(p.name ?? key);
}

/** FalkorDB-browser-style view: every node of the env graph, coloured by label, force-directed. */
export default function ForceNetwork({ data, onSelect }: { data: S["Explore"]; onSelect?: (n: { id: string; label: string; key: string }) => void }) {
  const box = useRef<HTMLDivElement>(null);
  const fg = useRef<ForceGraphMethods<NodeObject<N>, LinkObject<N, L>>>(undefined);
  const [size, setSize] = useState({ w: 800, h: 600 });
  const [hidden, setHidden] = useState<Set<string>>(new Set(["Run", "Explanation"]));
  const [q, setQ] = useState("");
  const [hover, setHover] = useState<string | null>(null);
  const fitted = useRef(false);

  useEffect(() => {
    const el = box.current;
    if (!el) return;
    const ro = new ResizeObserver(([e]) => setSize({ w: e.contentRect.width, h: e.contentRect.height }));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const shownLabels = useMemo(() => [...new Set(data.nodes.map((n) => n.label))].sort((a, b) => (SIZE[b] ?? 0) - (SIZE[a] ?? 0) || a.localeCompare(b)), [data]);
  const graph = useMemo(() => {
    fitted.current = false;
    const nodes: N[] = data.nodes.filter((n) => !hidden.has(n.label)).map((n) => ({ id: n.id, label: n.label, name: title(n), props: n.props as Record<string, unknown> }));
    const ids = new Set(nodes.map((n) => n.id));
    const links = data.edges.filter((e) => ids.has(e.from) && ids.has(e.to)).map((e) => ({ source: e.from, target: e.to, type: e.type, props: e.props as Record<string, unknown> }));
    return { nodes, links };
  }, [data, hidden]);
  const degree = useMemo(() => {
    const d = new Map<string, number>();
    for (const e of data.edges) {
      d.set(e.from, (d.get(e.from) ?? 0) + 1);
      d.set(e.to, (d.get(e.to) ?? 0) + 1);
    }
    return d;
  }, [data]);
  const needle = q.trim().toLowerCase();
  const match = (n: N) => !needle || n.name.toLowerCase().includes(needle) || n.id.toLowerCase().includes(needle);
  const neighbours = useMemo(() => {
    if (!hover) return null;
    const s = new Set([hover]);
    for (const e of data.edges) {
      if (e.from === hover) s.add(e.to);
      if (e.to === hover) s.add(e.from);
    }
    return s;
  }, [hover, data]);
  const lit = (id: string, n?: N) => (neighbours ? neighbours.has(id) : n ? match(n) : true);

  const toggle = (l: string) => setHidden((h) => {
    const next = new Set(h);
    if (next.has(l)) next.delete(l);
    else next.add(l);
    return next;
  });

  return (
    <div ref={box} className="relative h-full min-h-[420px] w-full overflow-hidden bg-void">
      <ForceGraph2D<N, L>
        ref={fg}
        width={size.w}
        height={size.h}
        graphData={graph}
        backgroundColor="rgba(0,0,0,0)"
        cooldownTicks={120}
        onEngineStop={() => {
          if (!fitted.current) fg.current?.zoomToFit(400, 40);
          fitted.current = true;
        }}
        nodeRelSize={1}
        nodeVal={(n) => (SIZE[n.label] ?? 3.5) ** 2}
        nodeLabel={(n) => `<div style="font:12px ui-monospace,monospace;padding:6px 8px;background:#0a0a0a;border:1px solid #26241f;border-radius:6px;color:#dedbc8;max-width:320px"><b style="color:${color(n.label)}">${n.label}</b><br/>${escape(n.name)}${Object.entries(n.props).filter(([k]) => k !== "key" && k !== "name").map(([k, v]) => `<br/><span style="color:#9d998c">${k}</span> ${escape(String(v)).slice(0, 80)}`).join("")}</div>`}
        nodeCanvasObject={(n, ctx, scale) => {
          const r = SIZE[n.label] ?? 3.5;
          const on = lit(n.id as string, n);
          ctx.globalAlpha = on ? 1 : 0.12;
          ctx.beginPath();
          ctx.arc(n.x!, n.y!, r, 0, 2 * Math.PI);
          ctx.fillStyle = color(n.label);
          ctx.fill();
          if (needle && on && !neighbours) {
            ctx.lineWidth = 1.5 / scale;
            ctx.strokeStyle = "#f6f3e4";
            ctx.stroke();
          }
          // names: always for services and hubs, everything once zoomed in
          if (on && (scale > 2.2 || hover === n.id || (scale > 0.9 && (n.label === "Service" || (degree.get(n.id as string) ?? 0) > 6)))) {
            ctx.font = `${Math.max(10 / scale, 1.5)}px ui-monospace, monospace`;
            ctx.textAlign = "center";
            ctx.textBaseline = "top";
            ctx.fillStyle = "#dedbc8";
            ctx.fillText(n.name.length > 28 ? `${n.name.slice(0, 27)}…` : n.name, n.x!, n.y! + r + 1.5);
          }
          ctx.globalAlpha = 1;
        }}
        nodePointerAreaPaint={(n, c, ctx) => {
          ctx.fillStyle = c;
          ctx.beginPath();
          ctx.arc(n.x!, n.y!, (SIZE[n.label] ?? 3.5) + 2, 0, 2 * Math.PI);
          ctx.fill();
        }}
        linkColor={(l) => {
          const s = typeof l.source === "object" ? (l.source as N).id : String(l.source);
          const t = typeof l.target === "object" ? (l.target as N).id : String(l.target);
          const on = neighbours ? neighbours.has(s) && neighbours.has(t) && (s === hover || t === hover) : !needle;
          const err = Number(l.props.err_rate ?? 0) > 0.05;
          return on ? (err ? "rgba(229,72,77,0.8)" : l.type === "CALLS" ? "rgba(230,199,125,0.55)" : "rgba(157,153,140,0.35)") : "rgba(157,153,140,0.07)";
        }}
        linkWidth={(l) => (l.type === "CALLS" ? 1.2 : 0.6)}
        linkDirectionalArrowLength={3}
        linkDirectionalArrowRelPos={0.92}
        linkLabel={(l) => l.type}
        onNodeHover={(n) => setHover(n ? (n.id as string) : null)}
        onNodeClick={(n) => {
          fg.current?.centerAt(n.x, n.y, 500);
          fg.current?.zoom(4, 500);
          onSelect?.({ id: n.id as string, label: n.label, key: n.id.split(":").slice(1).join(":") });
        }}
      />

      {/* legend: per-label counts, click to hide or show */}
      <div className="absolute bottom-3 left-3 max-h-[35%] max-w-[calc(100%-1.5rem)] overflow-y-auto rounded-lg border border-border bg-card/90 p-2 backdrop-blur sm:top-3 sm:bottom-auto sm:max-h-none sm:max-w-[260px]">
        <div className="flex flex-wrap gap-1">
          {shownLabels.map((l) => (
            <button key={l} onClick={() => toggle(l)} aria-pressed={!hidden.has(l)}
              className={cn("inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] transition-opacity", hidden.has(l) ? "border-border opacity-40" : "border-transparent bg-background/60")}>
              <span className="size-2 rounded-full" style={{ background: color(l) }} /> {l}
              <span className="font-mono text-muted-foreground">{data.label_counts[l] ?? 0}</span>
            </button>
          ))}
        </div>
        <p className="mt-1.5 px-1 text-[10px] text-muted-foreground">
          {graph.nodes.length} nodes · {graph.links.length} relationships{data.truncated && " · first " + data.nodes.length + " shown"}
        </p>
      </div>

      <div className="absolute top-3 right-3 flex items-center gap-1.5">
        <div className="relative">
          <Search className="pointer-events-none absolute top-1/2 left-2 size-3.5 -translate-y-1/2 text-muted-foreground" aria-hidden />
          <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="highlight…" aria-label="Highlight nodes" className="h-8 w-36 bg-card/90 pl-7 font-mono text-xs sm:w-44" />
        </div>
        <button onClick={() => fg.current?.zoomToFit(400, 40)} className="grid size-8 place-items-center rounded-md border border-border bg-card/90 text-muted-foreground hover:text-foreground" aria-label="Zoom to fit" title="Zoom to fit">
          <Maximize className="size-3.5" />
        </button>
      </div>
    </div>
  );
}

function escape(s: string) {
  return s.replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]!);
}
