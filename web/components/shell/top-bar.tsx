"use client";

import { Activity, Crosshair, FlaskConical, GitFork, Gauge, MessageSquareText, Network, PlayCircle, Search } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { StatusPill } from "@/components/status";
import { Button } from "@/components/ui/button";
import {
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { api, call } from "@/lib/api";
import { useEnv, useQuery, withEnv } from "@/lib/hooks";
import { cn } from "@/lib/utils";

export const NAV = [
  { href: "/", label: "Incidents", Icon: Activity },
  { href: "/map", label: "Map", Icon: Network },
  { href: "/blast-radius", label: "Blast radius", Icon: GitFork },
  { href: "/simulate", label: "What-if", Icon: FlaskConical },
  { href: "/ask", label: "Ask", Icon: MessageSquareText },
  { href: "/runs", label: "Runs", Icon: PlayCircle },
  { href: "/eval", label: "Eval", Icon: Gauge },
];

function HealthDot() {
  const h = useQuery("health", () => call(api.GET("/api/v1/health")), 15_000);
  const ok = h.data?.status === "ok";
  const label = h.error ? "API unreachable" : !h.data ? "Checking…" : ok ? "All systems normal" : "Degraded";
  const deps = h.data
    ? (["falkordb", "falkordb_mcp", "openrouter", "jev", "openconnector"] as const).map((k) => [k, h.data![k]] as const)
    : [];
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <button className="flex items-center gap-2 rounded-md px-2 py-1 text-xs text-muted-foreground hover:bg-accent" aria-label={label}>
          <span className={cn("size-2 rounded-full", h.error ? "bg-st-refuted" : !h.data ? "bg-muted-foreground" : ok ? "bg-st-confirmed" : "bg-ov-missed")} />
          <span className="hidden lg:inline">{label}</span>
        </button>
      </TooltipTrigger>
      <TooltipContent side="bottom" className="font-mono text-xs">
        {h.error ? h.error.message : deps.map(([k, v]) => <div key={k}>{k}: {v}</div>)}
      </TooltipContent>
    </Tooltip>
  );
}

function EnvSwitcher() {
  const [env, setEnv] = useEnv();
  const envs = useQuery("envs", () => call(api.GET("/api/v1/envs")));
  const current = env ?? envs.data?.default ?? "";
  return (
    <Select value={current} onValueChange={setEnv}>
      <SelectTrigger size="sm" className="h-8 w-[170px] font-mono text-xs" aria-label="Environment">
        <SelectValue placeholder="environment" />
      </SelectTrigger>
      <SelectContent>
        {(envs.data?.items ?? (current ? [current] : [])).map((e) => (
          <SelectItem key={e} value={e} className="font-mono text-xs">
            {e}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}

function CommandPalette() {
  const [open, setOpen] = useState(false);
  const router = useRouter();
  const [env] = useEnv();
  useEffect(() => {
    const down = (e: KeyboardEvent) => {
      if (e.key === "k" && (e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        setOpen((o) => !o);
      }
    };
    document.addEventListener("keydown", down);
    return () => document.removeEventListener("keydown", down);
  }, []);
  const incidents = useQuery(open ? `palette:${env}` : null, () =>
    call(api.GET("/api/v1/incidents", { params: { query: { env: env ?? undefined, limit: 30 } } })),
  );
  const go = (href: string) => {
    setOpen(false);
    router.push(withEnv(href, env));
  };
  return (
    <>
      <Button variant="outline" size="sm" className="h-8 gap-2 text-fog" onClick={() => setOpen(true)}>
        <Search className="size-3.5" aria-hidden />
        <span className="sr-only md:not-sr-only">Jump to…</span>
        <kbd className="hidden rounded-sm bg-white/5 px-1 font-mono text-[10px] text-fog md:inline">⌘K</kbd>
      </Button>
      <CommandDialog open={open} onOpenChange={setOpen} title="Jump to" description="Incidents and pages">
        <CommandInput placeholder="Incident id, symptom, page…" />
        <CommandList>
          <CommandEmpty>Nothing matches.</CommandEmpty>
          <CommandGroup heading="Incidents">
            {(incidents.data?.items ?? []).map((i) => (
              <CommandItem key={i.id} value={`${i.id} ${i.symptom ?? ""} ${i.root_cause ?? ""}`} onSelect={() => go(`/incident/${encodeURIComponent(i.id)}`)}>
                <StatusPill status={i.status} />
                <span className="truncate font-mono text-xs">{i.id}</span>
                <span className="ml-auto truncate text-xs text-muted-foreground">{i.root_cause ?? i.symptom}</span>
              </CommandItem>
            ))}
          </CommandGroup>
          <CommandGroup heading="Pages">
            {NAV.map(({ href, label, Icon }) => (
              <CommandItem key={href} value={label} onSelect={() => go(href)}>
                <Icon className="size-4" aria-hidden /> {label}
              </CommandItem>
            ))}
          </CommandGroup>
        </CommandList>
      </CommandDialog>
    </>
  );
}

export function TopBar() {
  const pathname = usePathname();
  const [env] = useEnv();
  return (
    <header className="sticky top-0 z-40 border-b border-border bg-void/85 backdrop-blur-xl">
      <div className="flex h-14 items-center gap-4 px-4 lg:px-6">
        <Link href={withEnv("/", env)} className="flex items-center gap-2 text-base font-medium tracking-[-0.012em] text-paper" aria-label="Epicenter home">
          <span className="grid size-6 place-items-center rounded-md bg-paper text-void">
            <Crosshair className="size-3.5" aria-hidden />
          </span>
          <span className="hidden sm:inline">Epicenter</span>
        </Link>
        <nav className="flex items-center gap-0.5 overflow-x-auto" aria-label="Main">
          {NAV.map(({ href, label, Icon }) => {
            const active = href === "/" ? pathname === "/" || pathname.startsWith("/incident/") : pathname.startsWith(href);
            return (
              <Link
                key={href}
                href={withEnv(href, env)}
                aria-current={active ? "page" : undefined}
                aria-label={label} // the text label is hidden below md
                className={cn(
                  "relative flex h-14 items-center gap-1.5 px-2.5 text-[13px] text-fog transition-colors hover:text-mist",
                  active && "text-paper after:absolute after:inset-x-2.5 after:bottom-0 after:h-0.5 after:rounded-full after:bg-acid-lime",
                )}
              >
                <Icon className="size-4" aria-hidden />
                <span className="hidden md:inline">{label}</span>
              </Link>
            );
          })}
        </nav>
        <div className="ml-auto flex items-center gap-2">
          <HealthDot />
          <CommandPalette />
          <EnvSwitcher />
        </div>
      </div>
    </header>
  );
}
