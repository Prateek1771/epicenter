"use client";

import { createElement, useEffect, useRef } from "react";

/**
 * Scroll-triggered text reveal: words rise out of a blur with a per-word stagger (`--i`). The motion is CSS
 * (globals.css `[data-reveal]`); this only flips `data-reveal` to "in" once the element enters the viewport.
 * Reduced motion and no-JS both render the text plainly.
 */
export function Reveal({ as = "div", className, children }: { as?: keyof React.JSX.IntrinsicElements; className?: string; children: React.ReactNode }) {
  const ref = useRef<HTMLElement>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const io = new IntersectionObserver(([e]) => {
      if (e.isIntersecting) {
        el.dataset.reveal = "in";
        io.disconnect();
      }
    }, { rootMargin: "0px 0px -10% 0px" });
    io.observe(el);
    return () => io.disconnect();
  }, []);
  return createElement(as, { ref, className, "data-reveal": "out" }, children);
}

/** Splits text into staggered words; `from` continues the count after earlier words in the same Reveal. */
export function W({ children, from = 0 }: { children: string; from?: number }) {
  return children.split(" ").map((w, i, all) => (
    <span key={i} className="rv-w" style={{ "--i": from + i } as React.CSSProperties}>
      {w}
      {i < all.length - 1 ? " " : ""}
    </span>
  ));
}
