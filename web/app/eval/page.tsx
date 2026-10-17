"use client";

import { Gauge } from "@/components/icons";

import { ComingSoon } from "@/components/coming-soon";
import { Skeleton } from "@/components/ui/skeleton";
import { API_URL } from "@/lib/api";
import { pct } from "@/lib/format";
import { useQuery } from "@/lib/hooks";

type Eval = { suite: string; system: string; cases: number; ac1: number; ac3: number; ablations: Record<string, { ac1: number }> };

export default function EvalPage() {
  // /eval isn't in the OpenAPI schema until phase 10, so this one call is untyped on purpose
  const e = useQuery<Eval | null>("eval", async () => {
    const r = await fetch(`${API_URL}/eval`);
    return r.ok ? r.json() : null;
  });
  return (
    <main className="mx-auto w-full max-w-[1200px] px-4 py-8 lg:px-6">
      <h1 className="flex items-center gap-2 text-2xl font-medium tracking-[-0.012em]"><Gauge className="size-6 text-fog" aria-hidden /> Eval</h1>
      <p className="mt-1 text-sm text-muted-foreground">Root-cause accuracy on the RCAEval benchmark (AC@1, AC@3), with ablations.</p>
      {e.loading && <Skeleton className="mt-6 h-40 w-full rounded-xl" />}
      {!e.loading && !e.data && <ComingSoon phase={10} what="The eval runner replays every RE2 case and scores the verdicts." endpoint="GET /eval" />}
      {e.data && (
        <table className="mt-6 w-full overflow-hidden rounded-xl border border-border text-sm">
          <thead className="bg-card/60 text-left text-xs text-muted-foreground uppercase">
            <tr><th className="px-4 py-2">Variant</th><th className="px-4 py-2">AC@1</th><th className="px-4 py-2">AC@3</th></tr>
          </thead>
          <tbody>
            <tr className="border-t border-border"><td className="px-4 py-2">full ({e.data.cases} cases)</td><td className="px-4 py-2 font-mono">{pct(e.data.ac1)}</td><td className="px-4 py-2 font-mono">{pct(e.data.ac3)}</td></tr>
            {Object.entries(e.data.ablations).map(([k, v]) => (
              <tr key={k} className="border-t border-border"><td className="px-4 py-2 text-muted-foreground">{k.replaceAll("_", " ")}</td><td className="px-4 py-2 font-mono">{pct(v.ac1)}</td><td className="px-4 py-2" /></tr>
            ))}
          </tbody>
        </table>
      )}
    </main>
  );
}
