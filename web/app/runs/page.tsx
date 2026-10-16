"use client";

import { PlayCircle } from "lucide-react";

import { ComingSoon } from "@/components/coming-soon";
import { Skeleton } from "@/components/ui/skeleton";
import { API_URL } from "@/lib/api";
import { useEnv, useQuery } from "@/lib/hooks";

type Scenario = { env: string; id: string; title: string };

export default function RunsPage() {
  const [env] = useEnv();
  // /runs isn't in the OpenAPI schema until phase 9, so this one call is untyped on purpose
  const s = useQuery<{ items: Scenario[] } | null>(`runs:${env}`, async () => {
    const r = await fetch(`${API_URL}/runs/scenarios`);
    return r.ok ? r.json() : null;
  });
  return (
    <main className="mx-auto w-full max-w-4xl px-4 py-8 lg:px-6">
      <h1 className="flex items-center gap-2 text-2xl font-semibold tracking-tight"><PlayCircle className="size-6 text-primary" aria-hidden /> Example runs</h1>
      <p className="mt-1 text-sm text-muted-foreground">
        Start a scripted fault on an example environment (OTel Demo, flip-commerce) or replay an RCAEval case, then watch the incident page.
      </p>
      {s.loading && <Skeleton className="mt-6 h-40 w-full rounded-xl" />}
      {!s.loading && !s.data && (
        <ComingSoon phase={9} what="Scenario runs need the live environments and their fault scripts." endpoint="GET /runs/scenarios" />
      )}
      {s.data && (
        <ul className="mt-6 grid gap-3 sm:grid-cols-2">
          {s.data.items.map((x) => (
            <li key={`${x.env}:${x.id}`} className="rounded-xl border border-border bg-card/40 p-4">
              <p className="font-medium">{x.title}</p>
              <p className="mt-1 font-mono text-xs text-muted-foreground">{x.env} · {x.id}</p>
            </li>
          ))}
        </ul>
      )}
    </main>
  );
}
