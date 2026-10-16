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
import { BellRing, Crown } from "lucide-react";
import { memo, useEffect, useMemo, useRef, useState } from "react";

import { serviceColor, splitOp, STATUS_LABEL } from "@/lib/format";
import { edgeKey, type Hyp, type Node, type View, winningPath } from "@/lib/incident-state";
import { layout, NODE_H, NODE_W, type XY } from "@/lib/layout";
import { cn } from "@/lib/utils";

export interface Overlay {
  hypothesis: string;
  matched: Set<string>;
  missed: Set<string>;
  unexplained: Set<string>;
  predicted: Set<string>;
}

export interface Spotlight {
  ops: Set<string>;
  edges: Set<string>;
  label: string;
}

type OpData = {
  node: Node;
  hyp: Hyp | undefined;
  symptom: boolean;
  root: boolean;
  second: boolean;
  dim: boolean;
  lit: boolean;
  overlay: "matched" | "missed" | "unexplained" | "predicted" | null;
  selected: boolean;
  later: boolean; // the onset slicer is before this operation went bad
};

const RING: Record<string, string> = {
  open: "ring-st-open/60",
  supported: "ring-st-supported",
  refuted: "ring-st-refuted",
  inconclusive: "ring-st-inconclusive",
  pruned: "ring-st-pruned/60",
  confirmed: "ring-st-confirmed ring-2",
};

const OVERLAY: Record<string, string> = {
  matched: "outline-2 outline-ov-matched",
  missed: "outline-2 outline-dashed outline-ov-missed",
  unexplained: "outline-2 outline-ov-unexplained",
  predicted: "outline-2 outline-dashed outline-ov-matched/70",
};

const OpNode = memo(function OpNode({ data }: NodeProps<FlowNode<OpData>>) {
  const { node, hyp, symptom, root, second, dim, lit, overlay, selected, later } = data;
  const [svc, name] = splitOp(node.id);
  const status = hyp?.status;
  return (
    <div
      className={cn(
        "epi-in relative flex h-16 w-[236px] items-stretch overflow-hidden rounded-lg border border-graphite bg-carbon text-left transition-[opacity,box-shadow] duration-300",
        hyp && "ring-1 ring-offset-0",
        status && RING[status],
        node.anomaly && "bg-[color-mix(in_srgb,var(--card),var(--color-st-refuted)_9%)]",
        root && "epi-glow",
        overlay && OVERLAY[overlay],
        overlay && "outline-offset-2",
        selected && "shadow-[0_0_0_3px_var(--ring)]",
        dim && "opacity-30",
        lit && "opacity-100 shadow-[0_0_0_2px_var(--color-signal)]",
        later && "opacity-15 grayscale",
      )}
      title={`${node.id}${hyp ? ` · ${STATUS_LABEL[hyp.status]}` : ""}${node.anomaly ? ` · ${node.anomaly.kind}` : ""}`}
    >
      <Handle type="target" position={Position.Left} className="!size-1.5 !border-0 !bg-muted-foreground/50" />
      <span className="w-1 shrink-0" style={{ background: serviceColor(node.service) }} aria-hidden />
      <span className="flex min-w-0 flex-1 flex-col justify-center gap-0.5 px-2.5">
        <span className="flex items-center gap-1.5">
          <span className="truncate font-mono text-[11px] text-muted-foreground">{svc}</span>
          {symptom && (
            <span className="ml-auto inline-flex items-center gap-0.5 rounded bg-signal/15 px-1 text-[10px] font-medium text-signal">
              <BellRing className="size-3" aria-hidden /> alert
            </span>
          )}
          {(root || second) && (
            <span className="ml-auto inline-flex items-center gap-0.5 rounded bg-st-confirmed/15 px-1 text-[10px] font-semibold text-st-confirmed">
              <Crown className="size-3" aria-hidden /> {root ? "root cause" : "2nd cause"}
            </span>
          )}
        </span>
        <span className="truncate text-[13px] font-medium text-foreground">{name || svc}</span>
        <span className="flex items-center gap-1.5 text-[10px]">
          {node.anomaly && (
            <span className="rounded bg-st-refuted/15 px-1 font-medium text-[color-mix(in_oklch,var(--color-st-refuted),white_30%)]">{node.anomaly.kind}</span>
          )}
          {hyp && (
            <span className="text-muted-foreground">
              {hyp.id} · {STATUS_LABEL[hyp.status]}
              {hyp.score != null && ` · ${hyp.score.toFixed(2)}`}
            </span>
          )}
        </span>
      </span>
      <Handle type="source" position={Position.Right} className="!size-1.5 !border-0 !bg-muted-foreground/50" />
    </div>
  );
});

const nodeTypes = { op: OpNode };

interface Props {
  view: View;
  overlay: Overlay | null;
  spotlight: Spotlight | null;
  selected: string | null;
  later?: Set<string>; // operations not yet anomalous at the slicer's time
  onSelect: (hypothesisId: string | null, op: string | null) => void;
}

function Canvas({ view, overlay, spotlight, selected, later, onSelect }: Props) {
  const [pos, setPos] = useState<Record<string, XY>>({});
  const posRef = useRef(pos);
  posRef.current = pos;
  const flow = useReactFlow();
  const fitted = useRef(false);

  // re-layout only when the node / edge set changes; placed nodes keep their spot (lib/layout.ts)
  const shape = useMemo(
    () => `${Object.keys(view.nodes).sort().join("|")}#${Object.keys(view.edges).sort().join("|")}`,
    [view.nodes, view.edges],
  );
  useEffect(() => {
    let live = true;
    const nodes = Object.values(view.nodes).map((n) => ({ id: n.id, group: n.service }));
    const edges = Object.values(view.edges);
    layout({ nodes, edges }, posRef.current).then((p) => live && setPos(p));
    return () => {
      live = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [shape]);

  const win = useMemo(() => winningPath(view), [view]);

  // open on what matters: the winning path and the alert (or everything, while there is no verdict yet)
  useEffect(() => {
    if (fitted.current || !Object.keys(pos).length) return;
    fitted.current = true;
    const focus = [...win.ops, ...(view.symptom ? [view.symptom] : [])].filter((id) => pos[id]);
    requestAnimationFrame(() =>
      flow.fitView({
        nodes: focus.length > 1 ? focus.map((id) => ({ id })) : undefined,
        padding: 0.35,
        minZoom: 0.35,
        maxZoom: 1,
        duration: 500,
      }),
    );
  }, [pos, flow, win, view.symptom]);
  const hypByOp = useMemo(() => {
    // the newest hypothesis per op (round 2 can re-test an op)
    const m: Record<string, Hyp> = {};
    for (const h of Object.values(view.hyps)) if (!m[h.op] || h.round >= m[h.op].round) m[h.op] = h;
    return m;
  }, [view.hyps]);

  const nodes: FlowNode<OpData>[] = useMemo(
    () =>
      Object.values(view.nodes)
        .filter((n) => pos[n.id])
        .map((n) => {
          const ov = overlay
            ? overlay.matched.has(n.id)
              ? "matched"
              : overlay.missed.has(n.id)
                ? "missed"
                : overlay.unexplained.has(n.id)
                  ? "unexplained"
                  : overlay.predicted.has(n.id)
                    ? "predicted"
                    : null
            : null;
          const lit = spotlight ? spotlight.ops.has(n.id) : false;
          const dim = spotlight ? !lit : overlay ? ov === null && hypByOp[n.id]?.id !== overlay.hypothesis : false;
          const hyp = hypByOp[n.id];
          return {
            id: n.id,
            type: "op",
            width: NODE_W, // fixed-size nodes; the minimap only draws nodes with known dimensions
            height: NODE_H,
            position: pos[n.id],
            data: {
              node: n,
              hyp,
              symptom: n.id === view.symptom,
              root: n.id === view.rootCause,
              second: n.id === view.secondCause,
              dim,
              lit,
              overlay: ov,
              selected: !!hyp && hyp.id === selected,
              later: !!later?.has(n.id),
            },
          };
        }),
    [view.nodes, view.symptom, view.rootCause, view.secondCause, pos, overlay, spotlight, hypByOp, selected, later],
  );

  const edges: FlowEdge[] = useMemo(
    () =>
      Object.values(view.edges).map((e) => {
        const k = edgeKey(e.src, e.dst);
        const onWin = win.edges.has(k) && !spotlight;
        const lit = spotlight?.edges.has(k) ?? false;
        const color = lit ? "var(--color-signal)" : onWin ? "var(--color-st-confirmed)" : "var(--color-smoke)";
        return {
          id: k,
          source: e.src,
          target: e.dst,
          type: "smoothstep",
          animated: onWin || lit,
          className: onWin ? "epi-glow" : undefined,
          style: { stroke: color, strokeWidth: onWin || lit ? 2.5 : 1.2, opacity: spotlight && !lit ? 0.25 : 1 },
          markerEnd: { type: MarkerType.ArrowClosed, color, width: 16, height: 16 },
          label: e.err_rate != null && e.err_rate > 0.05 ? `${Math.round(e.err_rate * 100)}% err` : undefined,
          labelStyle: { fill: "var(--color-st-refuted)", fontSize: 10, fontFamily: "var(--font-geist-mono)" },
          labelBgStyle: { fill: "var(--card)" },
        };
      }),
    [view.edges, win, spotlight],
  );

  return (
    <ReactFlow
      nodes={nodes}
      edges={edges}
      nodeTypes={nodeTypes}
      nodesConnectable={false}
      nodesDraggable
      minZoom={0.15}
      maxZoom={1.6}
      proOptions={{ hideAttribution: true }}
      onNodeClick={(_, n) => onSelect((n.data as OpData).hyp?.id ?? null, n.id)}
      onPaneClick={() => onSelect(null, null)}
      aria-label="Incident graph: operations, calls and suspects"
    >
      <Background variant={BackgroundVariant.Dots} gap={22} size={1} color="rgb(255 255 255 / 5%)" />
      <Controls showInteractive={false} position="bottom-right" />
      <MiniMap
        pannable
        zoomable
        position="bottom-left"
        style={{ width: 168, height: 104 }}
        className="!rounded-lg !border !border-border"
        nodeColor={(n) => {
          const d = n.data as OpData;
          if (d.root) return "var(--color-st-confirmed)";
          if (d.hyp?.status === "refuted") return "var(--color-st-refuted)";
          return d.node.anomaly ? "rgb(235 87 87 / 55%)" : "var(--color-smoke)";
        }}
        maskColor="rgb(8 9 10 / 72%)"
      />
    </ReactFlow>
  );
}

export function IncidentCanvas(props: Props) {
  return (
    <ReactFlowProvider>
      <Canvas {...props} />
    </ReactFlowProvider>
  );
}
