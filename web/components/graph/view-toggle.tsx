"use client";

import { Network, Table2 } from "@/components/icons";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback } from "react";

import { cn } from "@/lib/utils";

export type GraphMode = "graph" | "data";

/** Graph | Data, kept in the URL (`?view=data`) so a shared link opens on the same view. */
export function useGraphMode(): [GraphMode, (m: GraphMode) => void] {
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const mode: GraphMode = params.get("view") === "data" ? "data" : "graph";
  const set = useCallback(
    (m: GraphMode) => {
      const q = new URLSearchParams(params.toString());
      if (m === "data") q.set("view", "data");
      else q.delete("view");
      router.replace(q.size ? `${pathname}?${q}` : pathname, { scroll: false });
    },
    [params, pathname, router],
  );
  return [mode, set];
}

export function ViewToggle({ mode, onChange, className }: { mode: GraphMode; onChange: (m: GraphMode) => void; className?: string }) {
  const opts = [
    { m: "graph" as const, label: "Graph", Icon: Network },
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
