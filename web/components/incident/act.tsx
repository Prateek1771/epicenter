"use client";

import { BookOpenCheck, History, Loader2, MessageSquarePlus, Send, ShieldCheck } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { api, ApiError, call, type S } from "@/lib/api";
import { withEnv } from "@/lib/hooks";
import { cn } from "@/lib/utils";

import { OpLabel } from "./verdict";

const CHOSEN: Record<string, { label: string; cls: string }> = {
  history: { label: "fixed this before", cls: "bg-st-confirmed/12 text-st-confirmed" },
  runbook: { label: "runbook", cls: "bg-muted text-muted-foreground" },
  demoted: { label: "unrelated to the cause", cls: "bg-ov-missed/12 text-ov-missed" },
};

export function MemoryPanel({ similar, env }: { similar: S["IncidentOut"]["similar"]; env: string | null }) {
  if (!similar?.length) return <p className="text-xs text-muted-foreground">No similar resolved incidents yet. Resolve this one and it becomes memory.</p>;
  return (
    <ul className="space-y-2">
      {similar.map((s) => (
        <li key={s.incident} className="rounded-lg border border-border bg-background/40 p-2.5">
          <div className="flex items-center gap-2">
            <History className="size-3.5 text-signal" aria-hidden />
            <Link href={withEnv(`/incident/${encodeURIComponent(s.incident)}`, env)} className="truncate font-mono text-xs text-signal hover:underline">
              {s.incident}
            </Link>
            <span className="ml-auto font-mono text-[11px] text-muted-foreground" title="similarity (vector distance + graph overlap)">
              {s.score.toFixed(2)}
            </span>
          </div>
          {s.cause && <OpLabel op={s.cause} className="mt-1 text-xs" />}
          {s.fixes.length > 0 && (
            <p className="mt-1 text-xs text-muted-foreground">
              Fixed by: <span className="text-foreground">{s.fixes.join(", ")}</span>
            </p>
          )}
        </li>
      ))}
    </ul>
  );
}

function errMsg(e: unknown) {
  return e instanceof ApiError ? `${e.code}: ${e.message}` : String(e);
}

export function ActionsPanel({
  incident,
  env,
  actions,
  delivery,
  status,
  onChanged,
}: {
  incident: string;
  env: string | null;
  actions: S["IncidentOut"]["actions"];
  delivery: Record<string, { ok?: boolean; url?: string | null; message?: string | null }> | null | undefined;
  status: string;
  onChanged: () => void;
}) {
  const [sending, setSending] = useState<string | null>(null);
  const canDeliver = ["diagnosed", "delivered", "no_root_cause"].includes(status);
  const deliver = async (targets: ("slack" | "linear")[]) => {
    setSending(targets.join("+"));
    try {
      const res = await call(
        api.POST("/api/v1/incidents/{incident_id}/deliver", {
          params: { path: { incident_id: incident }, query: { env: env ?? undefined } },
          body: { targets },
        }),
      );
      for (const r of res.results) {
        if (r.ok) toast.success(`Sent to ${r.target}`, { description: r.url ?? undefined });
        else toast.error(`${r.target} failed`, { description: r.message ?? r.error ?? undefined });
      }
      onChanged();
    } catch (e) {
      toast.error("Delivery failed", { description: errMsg(e) });
    } finally {
      setSending(null);
    }
  };
  return (
    <div className="space-y-3">
      {actions.length === 0 ? (
        <p className="text-xs text-muted-foreground">No runbook step or past fix matches this root cause yet.</p>
      ) : (
        <ol className="space-y-1.5">
          {actions.map((a) => (
            <li key={a.id} className={cn("flex items-start gap-2 rounded-lg border border-border bg-background/40 p-2.5", a.status === "done" && "border-st-confirmed/40")}>
              <span className="grid size-5 shrink-0 place-items-center rounded-full bg-muted font-mono text-[11px]">{a.rank}</span>
              <span className="min-w-0 flex-1">
                <span className="block text-sm leading-snug">{a.name}</span>
                <span className="mt-1 flex flex-wrap items-center gap-1.5 text-[10px]">
                  <span className={cn("rounded px-1.5 py-0.5", CHOSEN[a.chosen_by]?.cls)}>{CHOSEN[a.chosen_by]?.label ?? a.chosen_by}</span>
                  {a.p != null && <span className="text-muted-foreground" title="Jev: does it address the cause?">relevance {a.p.toFixed(2)}</span>}
                  {a.status === "done" && <span className="text-st-confirmed">✓ fixed it</span>}
                </span>
                {a.precedent && a.precedent.length > 0 && (
                  <span className="mt-1 flex flex-wrap items-center gap-1 text-[10px] text-muted-foreground">
                    fixed
                    {a.precedent.map((i) => (
                      <Link key={i} href={withEnv(`/incident/${encodeURIComponent(i)}`, env)} className="font-mono text-signal hover:underline">
                        {i}
                      </Link>
                    ))}
                  </span>
                )}
              </span>
            </li>
          ))}
        </ol>
      )}
      <div className="flex flex-wrap gap-2">
        {(["slack", "linear"] as const).map((t) => {
          const d = delivery?.[t];
          return (
            <Button key={t} size="sm" variant={d?.ok ? "secondary" : "outline"} disabled={!canDeliver || !!sending} onClick={() => deliver([t])}>
              {sending?.includes(t) ? <Loader2 className="size-3.5 animate-spin" /> : <Send className="size-3.5" />}
              {d?.ok ? `Sent to ${t}` : d && !d.ok ? `Retry ${t}` : `Send to ${t}`}
            </Button>
          );
        })}
      </div>
      {delivery &&
        Object.entries(delivery).map(([t, d]) =>
          d.ok ? (
            d.url && (
              <a key={t} href={d.url} target="_blank" rel="noreferrer" className="block truncate text-xs text-signal hover:underline">
                {t}: {d.url}
              </a>
            )
          ) : (
            <p key={t} className="text-xs text-ov-missed">
              {t}: {d.message}
            </p>
          ),
        )}
    </div>
  );
}

export function ResolveDialog({
  incident,
  env,
  actions,
  status,
  onChanged,
}: {
  incident: string;
  env: string | null;
  actions: S["IncidentOut"]["actions"];
  status: string;
  onChanged: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [by, setBy] = useState("");
  const [action, setAction] = useState<string | null>(null);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const can = ["diagnosed", "delivered", "no_root_cause"].includes(status);
  const submit = async () => {
    setBusy(true);
    try {
      await call(
        api.POST("/api/v1/incidents/{incident_id}/resolve", {
          params: { path: { incident_id: incident }, query: { env: env ?? undefined } },
          body: { by, fixed_by_action: action, note: note || null },
        }),
      );
      toast.success("Resolved", { description: action ? "The fix is now memory for the next time." : undefined });
      setOpen(false);
      onChanged();
    } catch (e) {
      toast.error("Couldn't resolve", { description: errMsg(e) });
    } finally {
      setBusy(false);
    }
  };
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button size="sm" variant="outline" disabled={!can} title={can ? undefined : "Available once there is a verdict"}>
          <ShieldCheck className="size-3.5" /> Resolve
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Resolve incident</DialogTitle>
          <DialogDescription>Pick what fixed it: the next incident like this one will rank that fix first.</DialogDescription>
        </DialogHeader>
        <fieldset className="space-y-1.5">
          <legend className="mb-1 text-sm font-medium">What fixed it?</legend>
          {[...actions.map((a) => ({ id: a.id, name: a.name })), { id: "", name: "Something else / not listed" }].map((a) => (
            <label key={a.id || "none"} className="flex cursor-pointer items-center gap-2 rounded-md border border-border p-2 text-sm has-[:checked]:border-signal has-[:checked]:bg-signal/10">
              <input type="radio" name="fix" className="accent-[var(--color-signal)]" checked={(action ?? "") === a.id} onChange={() => setAction(a.id || null)} />
              {a.name}
            </label>
          ))}
        </fieldset>
        <div className="grid gap-1.5">
          <Label htmlFor="by">Resolved by</Label>
          <Input id="by" placeholder="your handle, e.g. priya" value={by} onChange={(e) => setBy(e.target.value)} />
        </div>
        <div className="grid gap-1.5">
          <Label htmlFor="note">Note</Label>
          <Textarea id="note" placeholder="flag off, errors gone" value={note} onChange={(e) => setNote(e.target.value)} />
        </div>
        <DialogFooter>
          <Button onClick={submit} disabled={!by.trim() || busy}>
            {busy && <Loader2 className="size-3.5 animate-spin" />} Resolve
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export function NotesBox({ incident, env, services, onChanged }: { incident: string; env: string | null; services: string[]; onChanged: () => void }) {
  const [text, setText] = useState("");
  const [by, setBy] = useState("");
  const [isChange, setIsChange] = useState(false);
  const [service, setService] = useState("");
  const [type, setType] = useState("deploy");
  const [busy, setBusy] = useState(false);
  const submit = async () => {
    setBusy(true);
    try {
      const res = await call(
        api.POST("/api/v1/incidents/{incident_id}/notes", {
          params: { path: { incident_id: incident }, query: { env: env ?? undefined } },
          body: { by, text, change: isChange ? { service, type, ts: new Date().toISOString() } : null },
        }),
      );
      toast.success(`Note ${res.decision_id} added`, { description: res.change_id ? `Change ${res.change_id}: the next diagnosis run sees it.` : undefined });
      setText("");
      onChanged();
    } catch (e) {
      toast.error("Couldn't add the note", { description: errMsg(e) });
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="space-y-2">
      <Textarea aria-label="Note" placeholder="What do you know? e.g. currency deployed at 14:02" value={text} onChange={(e) => setText(e.target.value)} className="min-h-16 text-sm" />
      <div className="flex items-center gap-2">
        <Input aria-label="Your handle" placeholder="handle" value={by} onChange={(e) => setBy(e.target.value)} className="h-8 w-28 text-sm" />
        <label className="flex items-center gap-1.5 text-xs text-muted-foreground">
          <Switch checked={isChange} onCheckedChange={setIsChange} aria-label="This was a change" /> a change
        </label>
        <Button size="sm" variant="secondary" className="ml-auto" disabled={!text.trim() || !by.trim() || busy || (isChange && !service)} onClick={submit}>
          <MessageSquarePlus className="size-3.5" /> Add
        </Button>
      </div>
      {isChange && (
        <div className="flex gap-2">
          <select aria-label="Service that changed" value={service} onChange={(e) => setService(e.target.value)} className="h-8 flex-1 rounded-md border border-input bg-transparent px-2 font-mono text-xs">
            <option value="">service…</option>
            {services.map((s) => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
          <select aria-label="Change type" value={type} onChange={(e) => setType(e.target.value)} className="h-8 rounded-md border border-input bg-transparent px-2 text-xs">
            {["deploy", "flag", "config", "infra", "manual"].map((t) => (
              <option key={t}>{t}</option>
            ))}
          </select>
        </div>
      )}
      <p className="flex items-center gap-1 text-[11px] text-muted-foreground">
        <BookOpenCheck className="size-3" aria-hidden /> Notes land in the graph as decisions; a change is seen by the next diagnosis run.
      </p>
    </div>
  );
}
