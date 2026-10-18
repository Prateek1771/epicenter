"use client";

import { usePathname } from "next/navigation";
import { useCallback, useEffect, useLayoutEffect, useState } from "react";

import { Button } from "@/components/ui/button";

// First-visit walkthrough: a spotlight over one control at a time and a pointer card next to it. Steps whose target
// isn't on screen (the nav at phone width, incident-only parts elsewhere) are skipped. The top bar's Tour button
// restarts it via the `epi:tour` window event.
type Step = { sel: string; title: string; body: string; when?: (path: string) => boolean };

const onIncident = (p: string) => p.startsWith("/incident/");
const nav = (href: string) => `nav[aria-label="Main"] a[href^="${href}"]`;

const STEPS: Step[] = [
  { sel: nav("/incidents"), title: "Incidents", body: "Every outage Epicenter diagnosed, newest first. Open one to see where it started." },
  { sel: nav("/map"), title: "Map", body: "The live graph of the system: services, operations and the calls between them, as layers, network or data." },
  { sel: nav("/blast-radius"), title: "Blast radius", body: "Pick a component and see everything downstream that breaks if it fails." },
  { sel: nav("/simulate"), title: "What-if", body: "The Fault Simulator: if this failed, what would we see? Six fault kinds, side by side." },
  { sel: nav("/ask"), title: "Ask", body: "Ask the graph a question in plain English. Answers are read-only and show the path they came from." },
  { sel: nav("/runs"), title: "Runs", body: "Start a sample or an RCAEval benchmark incident yourself and watch it get diagnosed live." },
  { sel: nav("/eval"), title: "Eval", body: "How often the verdict is right on RCAEval (87.8% top-1), what each feature is worth, and where it misses." },
  { sel: '[data-tour="env"]', title: "Environment", body: "One graph per environment. Switch here; every page follows." },
  { sel: '[data-tour="jump"]', title: "Jump to  ⌘K", body: "Any incident or page, from the keyboard." },
  { sel: 'aside[aria-label="Verdict and explanation"]', title: "The verdict", body: "The root cause, its confidence, the score breakdown, and why every other suspect was ruled out.", when: onIncident },
  { sel: '[data-tour="canvas"]', title: "The causal path", body: "From the alert back to where it started. Click a node to see what that suspect would explain.", when: onIncident },
  { sel: 'section[aria-label="Anomaly onsets over time"]', title: "Timeline lanes", body: "When each part went bad. Play spread replays the outage moving through the system.", when: onIncident },
  { sel: '[data-tour="act"]', title: "Act on it", body: "Rerun the diagnosis, deliver the verdict to Slack or Linear, or Resolve: the fix becomes memory for next time.", when: onIncident },
];

const KEY = "epi-tour";
const PAD = 6;
const GUTTER = 16;
const CARD_W = 320;

function visible(sel: string): Element | null {
  const el = document.querySelector(sel);
  const r = el?.getBoundingClientRect();
  return r && r.width > 0 && r.height > 0 ? el! : null;
}

export function Tour() {
  const pathname = usePathname();
  const [steps, setSteps] = useState<Step[]>([]);
  const [i, setI] = useState(-1);
  const [rect, setRect] = useState<DOMRect | null>(null);

  const start = useCallback(() => {
    const s = STEPS.filter((x) => (!x.when || x.when(pathname)) && visible(x.sel));
    if (s.length) {
      setSteps(s);
      setI(0);
    }
  }, [pathname]);

  const stop = useCallback(() => {
    setI(-1);
    try {
      localStorage.setItem(KEY, "done");
    } catch {}
  }, []);

  // first visit to an app page: start once the page has rendered its controls
  useEffect(() => {
    if (pathname === "/") return;
    let seen = "done";
    try {
      seen = localStorage.getItem(KEY) ?? "";
    } catch {}
    if (seen) return;
    const t = setTimeout(start, 1200);
    return () => clearTimeout(t);
  }, [pathname, start]);

  useEffect(() => {
    window.addEventListener("epi:tour", start);
    return () => window.removeEventListener("epi:tour", start);
  }, [start]);

  const step = i >= 0 ? steps[i] : null;

  useLayoutEffect(() => {
    if (!step) return;
    const el = document.querySelector(step.sel);
    if (!el) return;
    el.scrollIntoView({ block: "nearest" });
    const place = () => setRect(el.getBoundingClientRect());
    place();
    window.addEventListener("resize", place);
    window.addEventListener("scroll", place, true);
    return () => {
      window.removeEventListener("resize", place);
      window.removeEventListener("scroll", place, true);
    };
  }, [step]);

  useEffect(() => {
    if (!step) return;
    const key = (e: KeyboardEvent) => {
      if (e.key === "Escape") stop();
      else if (e.key === "ArrowRight") setI((n) => (n + 1 < steps.length ? n + 1 : (stop(), -1)));
      else if (e.key === "ArrowLeft") setI((n) => Math.max(0, n - 1));
    };
    document.addEventListener("keydown", key);
    return () => document.removeEventListener("keydown", key);
  }, [step, steps.length, stop]);

  if (!step || !rect) return null;

  const vw = window.innerWidth;
  const vh = window.innerHeight;
  const w = Math.min(CARD_W, vw - 2 * GUTTER);
  const left = Math.min(Math.max(GUTTER, rect.left + rect.width / 2 - w / 2), vw - w - GUTTER);
  // below the target when there's room, else above it; a target taller than the screen gets the card inside it
  const below = rect.bottom + PAD + 12;
  const above = rect.top - PAD - 12;
  const pos = below + 180 < vh ? { top: below } : above > 180 ? { bottom: vh - above } : { top: Math.max(GUTTER, vh - 200) };
  const last = i === steps.length - 1;

  return (
    <div className="fixed inset-0 z-[60]" role="dialog" aria-modal="true" aria-label="Product tour">
      <div className="absolute inset-0" onClick={stop} />
      <div
        className="pointer-events-none absolute rounded-lg ring-2 ring-gold transition-all duration-300 ease-out"
        style={{
          top: rect.top - PAD,
          left: rect.left - PAD,
          width: rect.width + 2 * PAD,
          height: rect.height + 2 * PAD,
          boxShadow: "0 0 0 9999px rgb(0 0 0 / 0.62)",
        }}
      />
      <div
        className="epi-in absolute rounded-xl border border-border bg-card p-4 shadow-2xl transition-all duration-300 ease-out"
        style={{ left, width: w, ...pos }}
      >
        <div className="font-mono text-[11px] text-muted-foreground">
          {i + 1} / {steps.length}
        </div>
        <div className="mt-1 text-sm font-medium text-paper">{step.title}</div>
        <p className="mt-1 text-[13px] leading-relaxed text-fog">{step.body}</p>
        <div className="mt-3 flex items-center gap-2">
          <Button variant="ghost" size="sm" className="text-muted-foreground" onClick={stop}>
            Skip
          </Button>
          <div className="ml-auto flex gap-2">
            {i > 0 && (
              <Button variant="outline" size="sm" onClick={() => setI(i - 1)}>
                Back
              </Button>
            )}
            <Button size="sm" onClick={() => (last ? stop() : setI(i + 1))} autoFocus>
              {last ? "Done" : "Next"}
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
