"use client";

import { useEffect, useRef } from "react";

import { activation, buildGraph, hops } from "@/lib/shockwave";

const CYCLE_MS = 7000;
const GOLD = "230, 199, 125";
const CREAM = "222, 219, 200";

/**
 * The hero's moving layer (in place of the reference's video): a call graph with a failure spreading from its
 * epicenter to every caller, hop by hop. Canvas, so it costs one draw per frame; a static frame under
 * prefers-reduced-motion.
 */
export function ShockwaveCanvas({ className }: { className?: string }) {
  const ref = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = ref.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    const g = buildGraph(7);
    const d = hops(g);
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    let w = 0;
    let h = 0;

    const resize = () => {
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      w = canvas.clientWidth;
      h = canvas.clientHeight;
      canvas.width = w * dpr;
      canvas.height = h * dpr;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    };
    // the graph sits in the right two thirds, behind the headline's empty side
    const px = (x: number) => w * (0.3 + x * 0.66);
    const py = (y: number) => h * (0.1 + y * 0.72);

    const draw = (t: number) => {
      const a = activation(g, d, t);
      ctx.clearRect(0, 0, w, h);
      const ep = g.nodes[g.epicenter];
      // shock rings
      for (let k = 0; k < 3; k++) {
        const p = (t * 1.15 - k * 0.12) % 1;
        if (p <= 0 || t > 0.85) continue;
        ctx.beginPath();
        ctx.arc(px(ep.x), py(ep.y), p * Math.max(w, h) * 0.75, 0, Math.PI * 2);
        ctx.strokeStyle = `rgba(${GOLD}, ${0.22 * (1 - p)})`;
        ctx.lineWidth = 1;
        ctx.stroke();
      }
      for (const [s, e] of g.edges) {
        const lit = Math.min(a[s], a[e]);
        ctx.beginPath();
        ctx.moveTo(px(g.nodes[s].x), py(g.nodes[s].y));
        ctx.lineTo(px(g.nodes[e].x), py(g.nodes[e].y));
        ctx.strokeStyle = lit > 0 ? `rgba(${GOLD}, ${0.12 + 0.45 * lit})` : `rgba(${CREAM}, 0.09)`;
        ctx.lineWidth = lit > 0 ? 1.2 : 0.8;
        ctx.stroke();
      }
      for (const n of g.nodes) {
        const l = a[n.id];
        const r = n.id === g.epicenter ? 5 : 3;
        if (l > 0) {
          ctx.beginPath();
          ctx.arc(px(n.x), py(n.y), r + 10 * l, 0, Math.PI * 2);
          ctx.fillStyle = `rgba(${GOLD}, ${0.08 * l})`;
          ctx.fill();
        }
        ctx.beginPath();
        ctx.arc(px(n.x), py(n.y), r, 0, Math.PI * 2);
        ctx.fillStyle = l > 0 ? `rgba(${GOLD}, ${0.35 + 0.65 * l})` : `rgba(${CREAM}, 0.28)`;
        ctx.fill();
      }
    };

    resize();
    const ro = new ResizeObserver(() => {
      resize();
      if (reduce) draw(0.6);
    });
    ro.observe(canvas);
    if (reduce) {
      draw(0.6);
      return () => ro.disconnect();
    }
    let raf = 0;
    const t0 = performance.now();
    const loop = (now: number) => {
      draw(((now - t0) % CYCLE_MS) / CYCLE_MS);
      raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);
    return () => {
      cancelAnimationFrame(raf);
      ro.disconnect();
    };
  }, []);

  return <canvas ref={ref} className={className} aria-hidden />;
}
