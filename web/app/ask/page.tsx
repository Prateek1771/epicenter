"use client";

import { MessageSquareText } from "@/components/icons";
import { useRouter, useSearchParams } from "next/navigation";

import { Chat } from "@/components/ask/chat";
import { Wiki } from "@/components/ask/wiki";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { api, call } from "@/lib/api";
import { useEnv, useQuery } from "@/lib/hooks";

const ENV_WIDE = "__env__";

export default function AskPage() {
  const [env] = useEnv();
  const params = useSearchParams();
  const router = useRouter();
  const incident = params.get("incident");
  const incs = useQuery(`ask:incs:${env}`, () => call(api.GET("/api/v1/incidents", { params: { query: { env: env ?? undefined, limit: 50 } } })));

  const setScope = (v: string) => {
    const p = new URLSearchParams(params.toString());
    if (v === ENV_WIDE) p.delete("incident");
    else p.set("incident", v);
    router.replace(`/ask${p.size ? `?${p}` : ""}`, { scroll: false });
  };

  return (
    <main className="mx-auto flex w-full max-w-[1500px] flex-col px-4 pt-6 pb-4 lg:h-[calc(100dvh-3.5rem)] lg:px-6">
      <div className="mb-4 flex flex-wrap items-end gap-x-6 gap-y-3">
        <div>
          <h1 className="flex items-center gap-2 text-3xl"><MessageSquareText className="size-6 text-fog" aria-hidden /> Ask the graph</h1>
          <p className="mt-1 text-sm text-muted-foreground">A chat over the live graph: owners, dependencies, incidents, fixes. Attach logs or notes; every answer shows its path.</p>
        </div>
        <label className="ml-auto flex items-center gap-2 text-xs text-muted-foreground">
          Scope
          <span className="rounded-md border border-border px-2 py-1.5 font-mono text-foreground">{env ?? "default env"}</span>
          <Select value={incident ?? ENV_WIDE} onValueChange={setScope}>
            <SelectTrigger size="sm" className="h-8 w-[220px] font-mono text-xs" aria-label="Incident scope">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={ENV_WIDE} className="text-xs">Whole environment</SelectItem>
              {(incs.data?.items ?? []).map((i) => (
                <SelectItem key={i.id} value={i.id} className="font-mono text-xs">{i.id}</SelectItem>
              ))}
              {incident && !incs.data?.items.some((i) => i.id === incident) && <SelectItem value={incident} className="font-mono text-xs">{incident}</SelectItem>}
            </SelectContent>
          </Select>
        </label>
      </div>
      <Chat incident={incident} wiki={(ask) => <Wiki incident={incident} onAsk={ask} />} />
    </main>
  );
}
