"use client";

import { ForceGraph, Network, Table2 } from "@/components/icons";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback } from "react";

import { cn } from "@/lib/utils";

export type GraphMode = "graph" | "network" | "data";

/** Graph | (Network) | Data, kept in the URL (`?view=data`) so a shared link opens on the same view. */
export function useGraphMode(): [GraphMode, (m: GraphMode) => void] {
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const v = params.get("view");
  const mode: GraphMode = v === "data" || v === "network" ? v : "graph";
  const set = useCallback(
    (m: GraphMode) => {
      const q = new URLSearchParams(params.toString());
      if (m !== "graph") q.set("view", m);
      else q.delete("view");
      router.replace(q.size ? `${pathname}?${q}` : pathname, { scroll: false });
    },
    [params, pathname, router],
  );
  return [mode, set];
}

/** `network` adds the force-directed view of everything in the env (the /map page only). */
export function ViewToggle({ mode, onChange, className, network }: { mode: GraphMode; onChange: (m: GraphMode) => void; className?: string; network?: boolean }) {
  const opts = [
    { m: "graph" as const, label: network ? "Layers" : "Graph", Icon: Network },
    ...(network ? [{ m: "network" as const, label: "Network", Icon: ForceGraph }] : []),
    { m: "data" as const, label: "Data", Icon: Table2 },
  ];
  return (
    <div role="radiogroup" aria-label="Show the graph or its data" className={cn("inline-flex rounded-md bg-obsidian/90 p-0.5 shadow-subtle backdrop-blur", className)}>
      {opts.map(({ m, label, Icon }) => (
        <button
          key={m}
          role="radio"
          aria-checked={mode === m}
          onClick={() => onChange(m)}
          className="inline-flex items-center gap-1.5 rounded-md px-2.5 py-1 text-xs text-muted-foreground transition-colors hover:text-mist aria-checked:bg-graphite aria-checked:text-paper"
        >
          <Icon className="size-3.5" aria-hidden /> {label}
        </button>
      ))}
    </div>
  );
}
