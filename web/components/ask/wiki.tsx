"use client";

import { Crown, GitCommitHorizontal, History, Users, Wiki as WikiIcon } from "@/components/icons";

import { StatusPill } from "@/components/status";
import { api, call } from "@/lib/api";
import { relTime } from "@/lib/format";
import { useEnv, useQuery } from "@/lib/hooks";

function Block({ title, Icon, children }: { title: string; Icon: typeof Users; children: React.ReactNode }) {
  return (
    <section className="space-y-2">
      <h3 className="flex items-center gap-1.5 text-[11px] font-semibold tracking-wider text-muted-foreground uppercase"><Icon className="size-3.5" aria-hidden /> {title}</h3>
      {children}
    </section>
  );
}

function Ask({ q, onAsk, children }: { q: string; onAsk: (q: string) => void; children: React.ReactNode }) {
  return (
    <button onClick={() => onAsk(q)} title={`Ask: ${q}`} className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-xs hover:bg-accent">
      {children}
    </button>
  );
}

/** The incident in scope: its verdict, owner, change, actions and precedent, each a question away. */
function IncidentWiki({ incident, onAsk }: { incident: string; onAsk: (q: string) => void }) {
  const [env] = useEnv();
  const d = useQuery(`wiki:inc:${env}:${incident}`, () =>
    call(api.GET("/api/v1/incidents/{incident_id}", { params: { path: { incident_id: incident }, query: { env: env ?? undefined } } })),
  ).data;
  if (!d) return <p className="text-xs text-muted-foreground">Loading {incident}…</p>;
  const v = d.verdict;
  return (
    <div className="space-y-5">
      <div className="space-y-1.5">
        <p className="font-mono text-xs text-muted-foreground">{d.id}</p>
        <StatusPill status={d.status} />
        <p className="text-xs text-muted-foreground">alert on <span className="font-mono text-foreground">{d.symptom}</span></p>
      </div>
      {v && (
        <Block title="Root cause" Icon={Crown}>
          <Ask q={`Why is ${v.root_cause.target} the root cause and not its callers?`} onAsk={onAsk}>
            <span className="font-mono">{v.root_cause.target}</span><span className="ml-auto text-muted-foreground">{Math.round(v.confidence * 100)}%</span>
          </Ask>
          {v.owner && <Ask q={`Who on ${v.owner} should I page for ${d.id}?`} onAsk={onAsk}><Users className="size-3 text-muted-foreground" /> owner: {v.owner}</Ask>}
          {v.change && <Ask q={`What did the change "${v.change.summary}" do, and when?`} onAsk={onAsk}><GitCommitHorizontal className="size-3 text-muted-foreground" /> {v.change.summary}</Ask>}
        </Block>
      )}
      {d.actions.length > 0 && (
        <Block title="Proposed actions" Icon={History}>
          {d.actions.map((a) => <Ask key={a.id} q={`Is "${a.name}" safe to run now, and what does it fix?`} onAsk={onAsk}>{a.rank}. {a.name}</Ask>)}
        </Block>
      )}
      {d.similar.length > 0 && (
        <Block title="Seen before" Icon={History}>
          {d.similar.map((s) => <Ask key={s.incident} q={`How was ${s.incident} fixed, and does it apply here?`} onAsk={onAsk}><span className="font-mono">{s.incident}</span><span className="ml-auto text-muted-foreground">{s.score.toFixed(2)}</span></Ask>)}
        </Block>
      )}
    </div>
  );
}

/** The environment: services with owners and live anomalies, and the latest incidents. */
function EnvWiki({ onAsk }: { onAsk: (q: string) => void }) {
  const [env] = useEnv();
  const q = { env: env ?? undefined };
  const topo = useQuery(`wiki:topo:${env}`, () => call(api.GET("/api/v1/graph/topology", { params: { query: { ...q, level: "service" } } }))).data;
  const incs = useQuery(`wiki:incs:${env}`, () => call(api.GET("/api/v1/incidents", { params: { query: { ...q, limit: 6 } } }))).data;
  const services = [...(topo?.nodes ?? [])].sort((a, b) => b.anomalies.length - a.anomalies.length || a.id.localeCompare(b.id)).slice(0, 12);
  return (
    <div className="space-y-5">
      <Block title="Latest incidents" Icon={History}>
        {(incs?.items ?? []).map((i) => (
          <Ask key={i.id} q={`Summarise ${i.id}: root cause, owner, fix.`} onAsk={onAsk}>
            <span className="truncate font-mono">{i.id}</span><span className="ml-auto shrink-0 text-muted-foreground">{relTime(i.opened_at)}</span>
          </Ask>
        ))}
        {incs && !incs.items.length && <p className="px-2 text-xs text-muted-foreground">None yet.</p>}
      </Block>
      <Block title={`Services · ${topo?.nodes.length ?? 0}`} Icon={Users}>
        {services.map((s) => (
          <Ask key={s.id} q={`Who owns ${s.id}, and what depends on it?`} onAsk={onAsk}>
            <span className="truncate font-mono">{s.id}</span>
            {s.anomalies.length > 0 && <span className="rounded bg-st-refuted/15 px-1 text-[10px] text-st-refuted">{s.anomalies.length}</span>}
            <span className="ml-auto shrink-0 text-muted-foreground">{s.owner ?? "no owner"}</span>
          </Ask>
        ))}
      </Block>
    </div>
  );
}

/** The quick wiki beside the chat: what the graph knows about the scope, one click from a question. */
export function Wiki({ incident, onAsk }: { incident: string | null; onAsk: (q: string) => void }) {
  return (
    <div className="space-y-4 rounded-xl border border-border bg-card/40 p-4">
      <p className="flex items-center gap-1.5 text-sm font-medium text-paper"><WikiIcon className="size-4 text-gold" aria-hidden /> {incident ? "Incident wiki" : "Environment wiki"}</p>
      <p className="text-[11px] text-muted-foreground">Click anything to ask about it.</p>
      {incident ? <IncidentWiki incident={incident} onAsk={onAsk} /> : <EnvWiki onAsk={onAsk} />}
    </div>
  );
}
