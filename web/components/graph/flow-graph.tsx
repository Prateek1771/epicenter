"use client";

import {
  Background,
  BackgroundVariant,
  Controls,
  type Edge as FlowEdge,
  Handle,
  MarkerType,
  MiniMap,
  type Node as FlowNode,
  type NodeProps,
  Position,
  ReactFlow,
  ReactFlowProvider,
  useReactFlow,
} from "@xyflow/react";
import { Crown } from "@/components/icons";
import { memo, useEffect, useMemo, useRef, useState } from "react";

import { serviceColor, splitOp } from "@/lib/format";
import { layout, NODE_H, NODE_W, type XY } from "@/lib/layout";
import { cn } from "@/lib/utils";

/**
 * The read-only graph behind /map, blast radius and what-if (phase 12). Same node look and elk layout as the
 * incident canvas, without its investigation overlays.
 */
export interface GNode {
  id: string;
  service: string;
  kicker?: string; // the small line above the title; defaults to the service
  title: string; // the big line (operation name, or the service at service level)
  sub?: string; // small line under it (owner, ops, …)
  tone?: "source" | "root" | "anomaly" | null;
  badge?: string; // top-right chip: "fails", "1 hop", "p 0.92"
  intensity?: number; // 0..1: tints the card (what-if probability)
  meter?: number; // 0..1: the traffic bar along the bottom
  hidden?: boolean; // what-if playback: not reached yet
}

export interface GEdge {
  src: string;
  dst: string;
  rps?: number | null;
  err_rate?: number | null;
}

type Data = { n: GNode; selected: boolean; dim: boolean; rtl: boolean };

const TONE: Record<string, string> = {
  source: "border-st-refuted/70 bg-[color-mix(in_srgb,var(--card),var(--color-st-refuted)_14%)]",
  root: "border-st-confirmed/70 epi-glow",
  anomaly: "border-st-refuted/50 shadow-[0_0_0_3px_color-mix(in_oklch,var(--color-st-refuted),transparent_70%)]",
};

const GraphNode = memo(function GraphNode({ data }: NodeProps<FlowNode<Data>>) {
  const { n, selected, dim, rtl } = data;
  const tint = n.intensity != null ? `color-mix(in srgb, var(--card), var(--color-st-refuted) ${Math.round(n.intensity * 32)}%)` : undefined;
  return (
    <div
      className={cn(
        "epi-in relative flex h-16 w-[236px] items-stretch overflow-hidden rounded-lg border border-graphite bg-carbon text-left transition-[opacity,box-shadow,background-color] duration-500",
        n.tone && TONE[n.tone],
        selected && "shadow-[0_0_0_3px_var(--ring)]",
        dim && "opacity-25",
        n.hidden && "opacity-0",
      )}
      style={tint ? { background: tint } : undefined}
      title={n.id}
    >
      {/* callers → callees; right-to-left layouts (blast radius) enter on the right */}
      <Handle type="target" position={rtl ? Position.Right : Position.Left} className="!size-1.5 !border-0 !bg-muted-foreground/50" />
      <span className="w-1 shrink-0" style={{ background: serviceColor(n.service) }} aria-hidden />
      <span className="flex min-w-0 flex-1 flex-col justify-center gap-0.5 px-2.5">
        <span className="flex items-center gap-1.5">
          <span className="truncate font-mono text-[11px] text-muted-foreground">{n.kicker ?? n.service}</span>
          {n.tone === "root" && <Crown className="ml-auto size-3.5 shrink-0 text-st-confirmed" aria-label="root cause of an open incident" />}
          {n.badge && <span className={cn("shrink-0 rounded px-1 text-[10px] font-medium", n.tone === "source" ? "bg-st-refuted/20 text-st-refuted" : "bg-muted text-muted-foreground", n.tone !== "root" && "ml-auto")}>{n.badge}</span>}
        </span>
        <span className="truncate text-[13px] font-medium text-foreground">{n.title}</span>
        {n.sub && <span className="truncate text-[10px] text-muted-foreground">{n.sub}</span>}
      </span>
      {n.meter != null && (
        <span className="absolute inset-x-0 bottom-0 h-0.5 bg-muted" aria-hidden>
          <span className="block h-full bg-signal/70" style={{ width: `${Math.max(3, n.meter * 100)}%` }} />
        </span>
      )}
      <Handle type="source" position={rtl ? Position.Left : Position.Right} className="!size-1.5 !border-0 !bg-muted-foreground/50" />
    </div>
  );
});

const nodeTypes = { g: GraphNode };

interface Props {
  nodes: GNode[];
  edges: GEdge[];
  direction?: "RIGHT" | "LEFT";
  selected?: string | null;
  focus?: string | null; // centre on this node when it changes (search)
  onSelect?: (id: string | null) => void;
  label: string;
}

function edgeStyle(e: GEdge, maxRps: number, lit: boolean) {
  const err = e.err_rate ?? 0;
  const color = err > 0.05 ? "var(--color-st-refuted)" : err > 0 ? "var(--color-ov-missed)" : lit ? "var(--color-signal)" : "var(--color-smoke)";
  const w = maxRps > 0 && e.rps ? 1 + 3 * Math.sqrt(e.rps / maxRps) : 1.2;
  return { color, width: lit ? Math.max(w, 2.5) : w, animated: err > 0.05 || lit };
}

function Graph({ nodes, edges, direction = "RIGHT", selected, focus, onSelect, label }: Props) {
  const [pos, setPos] = useState<Record<string, XY>>({});
  const flow = useReactFlow();
  const fitted = useRef(false);
  const shape = useMemo(() => `${direction}|${nodes.map((n) => n.id).sort().join("|")}#${edges.map((e) => `${e.src}>${e.dst}`).sort().join("|")}`, [nodes, edges, direction]);

  useEffect(() => {
    let live = true;
    fitted.current = false;
    layout({ nodes: nodes.map((n) => ({ id: n.id, group: n.service })), edges }, {}, direction).then((p) => live && setPos(p));
    return () => {
      live = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [shape]);

  useEffect(() => {
    if (fitted.current || !Object.keys(pos).length) return;
    fitted.current = true;
    requestAnimationFrame(() => flow.fitView({ padding: 0.2, minZoom: 0.2, maxZoom: 1, duration: 400 }));
  }, [pos, flow]);

  useEffect(() => {
    if (focus && pos[focus]) flow.setCenter(pos[focus].x + NODE_W / 2, pos[focus].y + NODE_H / 2, { zoom: 1, duration: 500 });
  }, [focus, pos, flow]);

  // selecting a node lights its direct calls and dims everything unrelated
  const near = useMemo(() => {
    if (!selected) return null;
    const s = new Set([selected]);
    for (const e of edges) if (e.src === selected || e.dst === selected) s.add(e.src).add(e.dst);
    return s;
  }, [selected, edges]);
  const maxRps = useMemo(() => Math.max(0, ...edges.map((e) => e.rps ?? 0)), [edges]);

  const fnodes: FlowNode<Data>[] = useMemo(
    () =>
      nodes
        .filter((n) => pos[n.id])
        .map((n) => ({ id: n.id, type: "g", position: pos[n.id], width: NODE_W, height: NODE_H, data: { n, selected: n.id === selected, dim: !!near && !near.has(n.id), rtl: direction === "LEFT" } })),
    [nodes, pos, selected, near, direction],
  );
  const hidden = useMemo(() => new Set(nodes.filter((n) => n.hidden).map((n) => n.id)), [nodes]);
  const fedges: FlowEdge[] = useMemo(
    () =>
      edges.map((e) => {
        const lit = !!near && (e.src === selected || e.dst === selected);
        const s = edgeStyle(e, maxRps, lit);
        const gone = hidden.has(e.src) || hidden.has(e.dst);
        return {
          id: `${e.src}>${e.dst}`,
          source: e.src,
          target: e.dst,
          type: "smoothstep",
          animated: s.animated && !gone,
          style: { stroke: s.color, strokeWidth: s.width, opacity: gone ? 0 : near && !lit ? 0.15 : 1, transition: "opacity 400ms" },
          markerEnd: { type: MarkerType.ArrowClosed, color: s.color, width: 14, height: 14 },
          label: e.err_rate != null && e.err_rate > 0.05 && !gone ? `${Math.round(e.err_rate * 100)}% err` : undefined,
          labelStyle: { fill: "var(--color-st-refuted)", fontSize: 10, fontFamily: "var(--font-geist-mono)" },
          labelBgStyle: { fill: "var(--card)" },
        };
      }),
    [edges, maxRps, near, selected, hidden],
  );

  return (
    <ReactFlow
      nodes={fnodes}
      edges={fedges}
      nodeTypes={nodeTypes}
      nodesConnectable={false}
      nodesDraggable
      minZoom={0.1}
      maxZoom={1.6}
      proOptions={{ hideAttribution: true }}
      onNodeClick={(_, n) => onSelect?.(n.id === selected ? null : n.id)}
      onPaneClick={() => onSelect?.(null)}
      aria-label={label}
    >
      <Background variant={BackgroundVariant.Dots} gap={22} size={1} color="rgb(255 255 255 / 5%)" />
      <Controls showInteractive={false} position="bottom-right" />
      <MiniMap
        pannable
        zoomable
        position="bottom-left"
        style={{ width: 160, height: 100 }}
        className="!rounded-lg !border !border-border"
        nodeColor={(x) => {
          const n = (x.data as Data).n;
          return n.tone === "source" || n.tone === "anomaly" ? "var(--color-st-refuted)" : n.tone === "root" ? "var(--color-st-confirmed)" : "var(--color-smoke)";
        }}
        maskColor="rgb(8 9 10 / 72%)"
      />
    </ReactFlow>
  );
}

export function FlowGraph(props: Props) {
  return (
    <ReactFlowProvider>
      <Graph {...props} />
    </ReactFlowProvider>
  );
}

/** `svc/GET /x` → title "GET /x"; a bare service name stays itself. */
export const opTitle = (id: string) => splitOp(id)[1] || id;
