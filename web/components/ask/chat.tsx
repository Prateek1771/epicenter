"use client";

import { ArrowRight, Check, Chats, Copy, FileText, Loader2, Paperclip, Plus, Search, Sparkles, Trash, Wrench, X } from "@/components/icons";
import { useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";

import { Markdown } from "@/components/ask/markdown";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { api, ApiError, call, type S } from "@/lib/api";
import { relTime } from "@/lib/format";
import { useEnv, useQuery } from "@/lib/hooks";
import { cn } from "@/lib/utils";

type Msg = Pick<S["MessageOut"], "id" | "role" | "text"> & Partial<Pick<S["MessageOut"], "path" | "tools_used" | "cypher" | "attachments" | "ts">> & { err?: string; pending?: boolean };
type File_ = { name: string; text: string };

const TEXT_TYPES = ".md,.markdown,.txt,.log,.json,.yaml,.yml,.csv,.toml,.ini,.cfg,.xml,.sql,.py,.ts,.js,.go,.java";
const MAX_TOTAL = 200_000; // characters, as the API allows

export function PathView({ path }: { path: string[] }) {
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

function CopyButton({ text, label }: { text: string; label: string }) {
  const [done, setDone] = useState(false);
  return (
    <button
      onClick={() => navigator.clipboard.writeText(text).then(() => { setDone(true); setTimeout(() => setDone(false), 1500); })}
      className="rounded p-1 text-muted-foreground hover:bg-accent hover:text-foreground"
      aria-label={label}
    >
      {done ? <Check className="size-3.5" /> : <Copy className="size-3.5" />}
    </button>
  );
}

function Answer({ m }: { m: Msg }) {
  return (
    <div className="group rounded-2xl rounded-bl-sm border border-border bg-card/60 p-4">
      <div className="flex gap-2">
        <Sparkles className="mt-0.5 size-4 shrink-0 text-gold" aria-hidden />
        <div className="min-w-0 flex-1"><Markdown text={m.text} /></div>
        <span className="opacity-0 transition-opacity group-hover:opacity-100 focus-within:opacity-100"><CopyButton text={m.text} label="Copy answer" /></span>
      </div>
      <PathView path={m.path ?? []} />
      {(m.tools_used?.length ?? 0) > 0 && (
        <div className="mt-3 flex flex-wrap gap-1.5">
          {m.tools_used!.map((u, j) => (
            <span key={j} className="inline-flex items-center gap-1 rounded-full bg-muted px-2 py-0.5 font-mono text-[11px] text-muted-foreground" title={JSON.stringify(u.args)}>
              <Wrench className="size-3" aria-hidden /> {u.tool}
            </span>
          ))}
        </div>
      )}
      {m.cypher && (
        <details className="mt-3">
          <summary className="cursor-pointer text-[11px] text-muted-foreground">Read-only Cypher it ran (falkordb-mcp)</summary>
          <div className="relative mt-1">
            <pre className="overflow-x-auto rounded-lg border border-border bg-background p-3 pr-9 font-mono text-xs leading-relaxed break-words whitespace-pre-wrap">{m.cypher}</pre>
            <span className="absolute top-1.5 right-1.5"><CopyButton text={m.cypher} label="Copy Cypher" /></span>
          </div>
        </details>
      )}
    </div>
  );
}

function History({
  items, active, onOpen, onNew, onDelete, q, setQ, loading,
}: {
  items: S["ConversationOut"][]; active: string | null; onOpen: (id: string) => void; onNew: () => void;
  onDelete: (id: string) => void; q: string; setQ: (v: string) => void; loading: boolean;
}) {
  const day = 86_400_000;
  const groups: [string, S["ConversationOut"][]][] = [
    ["Today", items.filter((c) => Date.now() - Date.parse(c.updated) < day)],
    ["Earlier", items.filter((c) => Date.now() - Date.parse(c.updated) >= day)],
  ];
  return (
    <div className="flex min-h-0 flex-col gap-3">
      <Button onClick={onNew} variant="outline" size="sm" className="justify-start"><Plus className="size-3.5" /> New chat</Button>
      <label className="relative">
        <Search className="pointer-events-none absolute top-1/2 left-2 size-3.5 -translate-y-1/2 text-muted-foreground" aria-hidden />
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search chats" aria-label="Search chats"
          className="h-8 w-full rounded-md border border-input bg-transparent pr-2 pl-7 text-xs outline-none focus-visible:border-ring" />
      </label>
      <nav className="min-h-0 flex-1 space-y-4 overflow-y-auto" aria-label="Chat history">
        {loading && !items.length && <p className="text-xs text-muted-foreground">Loading…</p>}
        {!loading && !items.length && <p className="text-xs text-muted-foreground">No chats yet. They&apos;re shared: everyone on this environment sees them.</p>}
        {groups.map(([label, list]) => list.length > 0 && (
          <div key={label}>
            <p className="mb-1 px-2 text-[10px] font-semibold tracking-wider text-muted-foreground uppercase">{label}</p>
            <ul className="space-y-0.5">
              {list.map((c) => (
                <li key={c.id} className="group flex items-center">
                  <button onClick={() => onOpen(c.id)} aria-current={active === c.id ? "true" : undefined}
                    className={cn("min-w-0 flex-1 truncate rounded-md px-2 py-1.5 text-left text-xs text-fog hover:bg-accent hover:text-mist", active === c.id && "bg-accent text-paper")}>
                    {c.title || "New chat"}
                    {c.incident && <span className="ml-1 font-mono text-[10px] text-muted-foreground">· {c.incident}</span>}
                  </button>
                  <button onClick={() => onDelete(c.id)} aria-label={`Delete ${c.title}`} className="rounded p-1 text-muted-foreground opacity-0 group-hover:opacity-100 hover:text-st-refuted focus:opacity-100">
                    <Trash className="size-3.5" />
                  </button>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </nav>
    </div>
  );
}

/**
 * Ask as a chat (USER_FLOW Flow 4): shared history in the graph, attachments read in the browser, scoped to the env and
 * optionally one incident. `compact` is the incident page's panel (history as a menu, no rails); `wiki` renders the
 * right rail and gets a function that puts a question in the box.
 */
export function Chat({ incident = null, compact = false, wiki }: { incident?: string | null; compact?: boolean; wiki?: (ask: (q: string) => void) => React.ReactNode }) {
  const [env] = useEnv();
  const query = { env: env ?? undefined };
  const [conv, setConv] = useState<string | null>(null);
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [text, setText] = useState("");
  const [files, setFiles] = useState<File_[]>([]);
  const [busy, setBusy] = useState(false);
  const [search, setSearch] = useState("");
  const [showHistory, setShowHistory] = useState(false);
  const [drag, setDrag] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);
  const box = useRef<HTMLTextAreaElement>(null);
  const end = useRef<HTMLDivElement>(null);

  const list = useQuery(`conv:${env}:${incident ?? ""}:${search}`, () =>
    call(api.GET("/api/v1/conversations", { params: { query: { ...query, incident: incident ?? undefined, q: search || undefined, limit: 50 } } })),
  );
  useEffect(() => { setConv(null); setMsgs([]); }, [env, incident]);
  useEffect(() => { end.current?.scrollIntoView({ block: "end", behavior: "smooth" }); }, [msgs]);

  const open = async (id: string) => {
    setShowHistory(false);
    try {
      const d = await call(api.GET("/api/v1/conversations/{conversation_id}", { params: { path: { conversation_id: id }, query } }));
      setConv(id);
      setMsgs(d.message_list);
    } catch (e) {
      toast.error("Couldn't open the chat", { description: e instanceof ApiError ? e.message : String(e) });
    }
  };
  const fresh = () => { setConv(null); setMsgs([]); setShowHistory(false); box.current?.focus(); };
  const remove = async (id: string) => {
    await call(api.DELETE("/api/v1/conversations/{conversation_id}", { params: { path: { conversation_id: id }, query } })).catch(() => undefined);
    if (id === conv) fresh();
    list.reload();
  };

  const addFiles = async (picked: FileList | File[]) => {
    const read = await Promise.all([...picked].map(async (f) => ({ name: f.name, text: await f.text() })));
    setFiles((cur) => {
      const next = [...cur, ...read].slice(0, 5);
      const total = next.reduce((s, f) => s + f.text.length, 0);
      if (total > MAX_TOTAL) {
        toast.error("Attachments too large", { description: "200 KB of text in total at most." });
        return cur;
      }
      return next;
    });
  };

  const send = async (question: string) => {
    if (!question.trim() || busy) return;
    setBusy(true);
    setText("");
    const attached = files;
    setFiles([]);
    setMsgs((m) => [...m, { id: `local-${Date.now()}`, role: "user", text: question, attachments: attached.map((f) => f.name) }, { id: "pending", role: "assistant", text: "", pending: true }]);
    try {
      let id = conv;
      if (!id) {
        const c = await call(api.POST("/api/v1/conversations", { params: { query }, body: { incident_id: incident } }));
        id = c.id;
        setConv(id);
      }
      const a = await call(api.POST("/api/v1/ask", { params: { query }, body: { question, incident_id: incident, conversation_id: id, attachments: attached } }));
      setMsgs((m) => m.map((x) => (x.id === "pending" ? { id: a.message_id ?? `a-${Date.now()}`, role: "assistant", text: a.answer, path: a.path, tools_used: a.tools_used, cypher: a.cypher } : x)));
    } catch (e) {
      const msg = e instanceof ApiError ? (e.code === "UPSTREAM_ERROR" ? "The LLM is unavailable right now. Your question is saved in this chat; ask again later." : e.message) : String(e);
      setMsgs((m) => m.map((x) => (x.id === "pending" ? { ...x, pending: false, err: msg } : x)));
    } finally {
      setBusy(false);
      list.reload();
    }
  };

  const suggestions = useMemo(
    () => (incident
      ? ["Summarise this incident in three lines", "Who should I page, and why?", "What would have prevented this?", "Has this happened before? How was it fixed?"]
      : ["Who should I page for payment?", "Which operation has the most callers?", "What breaks if redis goes down?", "What was the last incident and how was it fixed?"]),
    [incident],
  );

  const thread = (
    <div className={cn("min-h-0 flex-1 space-y-5 overflow-y-auto", compact ? "px-1" : "px-1 sm:px-2")} aria-live="polite">
      {msgs.length === 0 && (
        <div className="py-6">
          {!compact && <p className="mb-3 text-sm text-muted-foreground">Answers walk the graph with typed tools first, then read-only Cypher. Every answer shows the path it rests on.</p>}
          <div className={cn("grid gap-2", !compact && "sm:grid-cols-2")}>
            {suggestions.map((s) => (
              <button key={s} onClick={() => send(s)} className="rounded-xl border border-border bg-card/40 p-3 text-left text-sm hover:border-gold/50 hover:bg-accent/40">{s}</button>
            ))}
          </div>
        </div>
      )}
      {msgs.map((m) => (
        <div key={m.id} className="epi-in">
          {m.role === "user" ? (
            <div className="ml-auto w-fit max-w-[90%] space-y-1.5">
              <p className="rounded-2xl rounded-br-sm bg-gold/12 px-4 py-2 text-sm whitespace-pre-wrap text-paper">{m.text}</p>
              {(m.attachments?.length ?? 0) > 0 && (
                <p className="flex flex-wrap justify-end gap-1">{m.attachments!.map((a) => <span key={a} className="inline-flex items-center gap-1 rounded-full bg-muted px-2 py-0.5 text-[11px] text-muted-foreground"><FileText className="size-3" /> {a}</span>)}</p>
              )}
            </div>
          ) : m.pending ? (
            <p className="flex items-center gap-2 text-sm text-muted-foreground"><Loader2 className="size-4 animate-spin" /> walking the graph…</p>
          ) : m.err ? (
            <p className="rounded-xl border border-st-refuted/30 bg-st-refuted/10 px-3 py-2 text-sm text-st-refuted">{m.err}</p>
          ) : (
            <Answer m={m} />
          )}
        </div>
      ))}
      <div ref={end} />
    </div>
  );

  const composer = (
    <form
      className={cn("rounded-2xl border bg-card/90 p-2 backdrop-blur transition-colors", drag ? "border-gold" : "border-border")}
      onSubmit={(e) => { e.preventDefault(); send(text); }}
      onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
      onDragLeave={() => setDrag(false)}
      onDrop={(e) => { e.preventDefault(); setDrag(false); if (e.dataTransfer.files.length) addFiles(e.dataTransfer.files); }}
    >
      {files.length > 0 && (
        <div className="flex flex-wrap gap-1.5 px-1 pb-2">
          {files.map((f, i) => (
            <span key={i} className="inline-flex items-center gap-1 rounded-full border border-border bg-background px-2 py-0.5 text-[11px]">
              <FileText className="size-3 text-muted-foreground" /> {f.name} <span className="text-muted-foreground">{(f.text.length / 1000).toFixed(1)} kB</span>
              <button type="button" onClick={() => setFiles((cur) => cur.filter((_, j) => j !== i))} aria-label={`Remove ${f.name}`} className="text-muted-foreground hover:text-foreground"><X className="size-3" /></button>
            </span>
          ))}
        </div>
      )}
      <div className="flex items-end gap-1.5">
        <input ref={fileInput} type="file" multiple accept={TEXT_TYPES} className="hidden" onChange={(e) => { if (e.target.files) addFiles(e.target.files); e.target.value = ""; }} />
        <Button type="button" variant="ghost" size="sm" className="size-9 shrink-0 p-0" onClick={() => fileInput.current?.click()} aria-label="Attach files"><Paperclip className="size-4" /></Button>
        <Textarea
          ref={box}
          aria-label="Question"
          placeholder={incident ? `Ask about ${incident}…` : "Ask about services, owners, incidents, fixes… (drop files here)"}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(text); } }}
          className="max-h-40 min-h-9 resize-none border-0 bg-transparent px-1 py-2 shadow-none focus-visible:ring-0"
        />
        <Button type="submit" disabled={!text.trim() || busy} aria-label="Send" className="size-9 shrink-0 p-0">
          {busy ? <Loader2 className="size-4 animate-spin" /> : <ArrowRight className="size-4" />}
        </Button>
      </div>
    </form>
  );

  const history = (
    <History items={list.data?.items ?? []} active={conv} onOpen={open} onNew={fresh} onDelete={remove} q={search} setQ={setSearch} loading={list.loading} />
  );

  if (compact) {
    return (
      <div className="flex h-full min-h-0 flex-col gap-3">
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={() => setShowHistory((s) => !s)} aria-expanded={showHistory}><Chats className="size-3.5" /> Chats · {list.data?.items.length ?? 0}</Button>
          <Button variant="ghost" size="sm" onClick={fresh}><Plus className="size-3.5" /> New</Button>
        </div>
        {showHistory && <div className="max-h-64 rounded-lg border border-border p-2">{history}</div>}
        {thread}
        {composer}
      </div>
    );
  }

  return (
    <div className="grid min-h-0 flex-1 gap-4 lg:grid-cols-[240px_minmax(0,1fr)_300px]">
      <aside className="hidden min-h-0 lg:flex lg:flex-col" aria-label="Chats">{history}</aside>
      <section className="flex min-h-0 flex-col gap-3 max-lg:h-[64dvh]" aria-label="Conversation">
        <div className="flex items-center gap-2 lg:hidden">
          <Button variant="outline" size="sm" onClick={() => setShowHistory((s) => !s)} aria-expanded={showHistory}><Chats className="size-3.5" /> Chats</Button>
          <Button variant="ghost" size="sm" onClick={fresh}><Plus className="size-3.5" /> New chat</Button>
          {conv && <span className="ml-auto truncate text-xs text-muted-foreground">{list.data?.items.find((c) => c.id === conv)?.title}</span>}
        </div>
        {showHistory && <div className="max-h-72 rounded-lg border border-border p-2 lg:hidden">{history}</div>}
        {thread}
        {composer}
        {msgs.length > 0 && conv && (
          <p className="text-center text-[11px] text-muted-foreground">Saved to the shared history · updated {relTime(list.data?.items.find((c) => c.id === conv)?.updated)}</p>
        )}
      </section>
      {wiki && <aside className="min-h-0 overflow-y-auto max-lg:border-t max-lg:border-border max-lg:pt-4" aria-label="Wiki">{wiki((q) => { setText(q); box.current?.focus(); })}</aside>}
    </div>
  );
}
