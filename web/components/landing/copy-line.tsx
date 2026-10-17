"use client";

import { useState } from "react";

import { Check, Copy } from "@/components/icons";

/** One setup command in the reference's form style: a bottom-border-only field, with a copy button. */
export function CopyLine({ label, cmd }: { label: string; cmd: string }) {
  const [done, setDone] = useState(false);
  return (
    <div>
      <p className="text-[11px] tracking-[0.18em] text-cream/50 uppercase">{label}</p>
      <div className="flex items-center gap-3 border-b border-white/20 py-3">
        <code className="min-w-0 flex-1 overflow-x-auto font-mono text-sm whitespace-nowrap text-cream">{cmd}</code>
        <button
          onClick={() => navigator.clipboard?.writeText(cmd).then(() => (setDone(true), setTimeout(() => setDone(false), 1200)))}
          className="shrink-0 text-cream/50 transition-colors hover:text-gold"
          aria-label={`Copy: ${cmd}`}
        >
          {done ? <Check className="size-4 text-gold" /> : <Copy className="size-4" />}
        </button>
      </div>
    </div>
  );
}
