"use client";

import { ArrowRight, Check, Copy, Loader2, MessageSquareText, Sparkles, Wrench } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { api, ApiError, call, type S } from "@/lib/api";
import { useEnv } from "@/lib/hooks";
import { cn } from "@/lib/utils";

const EXAMPLES = [
  "Who should I page for payment?",
  "Which operation has the most callers?",
  "What was the root cause of the last resolved incident and how was it fixed?",
  "What breaks if redis goes down?",
];

type Turn = { q: string; a?: S["AskOut"]; err?: string };

function PathView({ path }: { path: string[] }) {
  if (!path.length) return null;
  return (
    <div className="mt-3 flex flex-wrap items-center gap-1.5" aria-label="Graph path behind the answer">
      {path.map((p, i) => {
        const rel = /^[A-Z][A-Z_]+$/.test(p);
        return (
          <span key={i} className="flex items-center gap-1.5">
            {rel ? (
              <span className="text-[10px] font-semibold tracking-wide text-muted-foreground">{p}</span>
            ) : (
              <span className="rounded-md border border-border bg-background px-2 py-0.5 font-mono text-xs">{p}</span>
            )}
            {i < path.length - 1 && <ArrowRight className="size-3 text-muted-foreground" aria-hidden />}
          </span>
        );
      })}
    </div>
  );
}

function CopyButton({ text }: { text: string }) {
  const [done, setDone] = useState(false);
  return (
    <button
      onClick={() => navigator.clipboard.writeText(text).then(() => { setDone(true); setTimeout(() => setDone(false), 1500); })}
      className="absolute top-2 right-2 rounded p-1 text-muted-foreground hover:bg-accent hover:text-foreground"
      aria-label="Copy Cypher"
    >
      {done ? <Check className="size-3.5" /> : <Copy className="size-3.5" />}
    </button>
  );
}

export default function AskPage() {
  const [env] = useEnv();
  const [q, setQ] = useState("");
  const [turns, setTurns] = useState<Turn[]>([]);
  const [busy, setBusy] = useState(false);

  const ask = async (question: string) => {
    if (!question.trim()) return;
    setBusy(true);
    setQ("");
    setTurns((t) => [...t, { q: question }]);
    try {
      const a = await call(api.POST("/api/v1/ask", { params: { query: { env: env ?? undefined } }, body: { question } }));
      setTurns((t) => t.map((x, i) => (i === t.length - 1 ? { ...x, a } : x)));
    } catch (e) {
      const msg = e instanceof ApiError ? (e.code === "UPSTREAM_ERROR" ? "The ask box needs the LLM, and it's unavailable right now." : e.message) : String(e);
      setTurns((t) => t.map((x, i) => (i === t.length - 1 ? { ...x, err: msg } : x)));
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="mx-auto flex w-full max-w-3xl flex-col px-4 py-8 lg:px-6">
      <h1 className="flex items-center gap-2 text-2xl font-medium tracking-[-0.012em]"><MessageSquareText className="size-6 text-fog" aria-hidden /> Ask the graph</h1>
      <p className="mt-1 mb-6 text-sm text-muted-foreground">
        GPT-4o answers with the typed graph tools first, and falls back to a read-only Cypher query. Every answer shows the path it rests on.
      </p>

      <div className="space-y-6">
        {turns.map((t, i) => (
          <div key={i} className="epi-in space-y-3">
            <p className="ml-auto w-fit max-w-[85%] rounded-2xl rounded-br-sm bg-signal/15 px-4 py-2 text-sm">{t.q}</p>
            {!t.a && !t.err && <p className="flex items-center gap-2 text-sm text-muted-foreground"><Loader2 className="size-4 animate-spin" /> walking the graph…</p>}
            {t.err && <p className="text-sm text-st-refuted">{t.err}</p>}
            {t.a && (
              <div className="rounded-2xl rounded-bl-sm border border-border bg-card/60 p-4">
                <p className="flex gap-2 text-sm leading-relaxed"><Sparkles className="mt-0.5 size-4 shrink-0 text-signal" aria-hidden /> {t.a.answer}</p>
                <PathView path={t.a.path} />
                {t.a.tools_used.length > 0 && (
                  <div className="mt-3 flex flex-wrap gap-1.5">
                    {t.a.tools_used.map((u, j) => (
                      <span key={j} className="inline-flex items-center gap-1 rounded-full bg-muted px-2 py-0.5 font-mono text-[11px] text-muted-foreground" title={JSON.stringify(u.args)}>
                        <Wrench className="size-3" aria-hidden /> {u.tool}
                      </span>
                    ))}
                  </div>
                )}
                {t.a.cypher && (
                  <div className="relative mt-3">
                    <p className="mb-1 text-[11px] text-muted-foreground">Read-only Cypher it ran (falkordb-mcp):</p>
                    <pre className="overflow-x-auto rounded-lg whitespace-pre-wrap break-words border border-border bg-background p-3 pr-9 font-mono text-xs leading-relaxed">{t.a.cypher}</pre>
                    <CopyButton text={t.a.cypher} />
                  </div>
                )}
              </div>
            )}
          </div>
        ))}
      </div>

      {turns.length === 0 && (
        <div className="grid gap-2 sm:grid-cols-2">
          {EXAMPLES.map((e) => (
            <button key={e} onClick={() => ask(e)} className="rounded-xl border border-border bg-card/40 p-3 text-left text-sm hover:border-signal/50 hover:bg-accent/40">
              {e}
            </button>
          ))}
        </div>
      )}

      <form
        className={cn("sticky bottom-4 mt-8 flex items-end gap-2 rounded-2xl border border-border bg-card/90 p-2 shadow-2xl backdrop-blur")}
        onSubmit={(e) => {
          e.preventDefault();
          ask(q);
        }}
      >
        <Textarea
          aria-label="Question"
          placeholder="Ask about services, owners, incidents, fixes…"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              ask(q);
            }
          }}
          className="min-h-10 resize-none border-0 bg-transparent shadow-none focus-visible:ring-0"
        />
        <Button type="submit" disabled={!q.trim() || busy} aria-label="Ask">
          {busy ? <Loader2 className="size-4 animate-spin" /> : <ArrowRight className="size-4" />}
        </Button>
      </form>
    </main>
  );
}
