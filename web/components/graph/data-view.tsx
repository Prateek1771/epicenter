"use client";

import { ArrowDown, ArrowUp, Check, Copy, Download, Search } from "@/components/icons";
import { useMemo, useState } from "react";

import { Input } from "@/components/ui/input";
import { type Cell, filterRows, type GraphData, type Row, sortRows, type Table, toCsv } from "@/lib/graph-data";
import { cn } from "@/lib/utils";

type Tab = "nodes" | "edges" | "json";

function download(name: string, body: string, type: string) {
  const url = URL.createObjectURL(new Blob([body], { type }));
  const a = Object.assign(document.createElement("a"), { href: url, download: name });
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function fmt(c: Cell, numeric?: boolean): string {
  if (c === null || c === undefined) return "—";
  if (numeric && typeof c === "number") return Number.isInteger(c) ? String(c) : c.toFixed(Math.abs(c) < 10 ? 3 : 1);
  return String(c);
}

function Grid({ t, selected, onRow }: { t: Table; selected?: string | null; onRow?: (r: Row) => void }) {
  const [sort, setSort] = useState<{ key: string; dir: "asc" | "desc" } | null>(null);
  const rows = useMemo(() => (sort ? sortRows(t.rows, sort.key, sort.dir) : t.rows), [t.rows, sort]);
  if (!t.rows.length) return <p className="px-4 py-10 text-center text-sm text-muted-foreground">No rows match.</p>;
  return (
    <table className="w-full min-w-max text-left text-xs">
      <thead className="sticky top-0 z-10 bg-card/95 backdrop-blur">
        <tr className="border-b border-border">
          {t.columns.map((c) => {
            const on = sort?.key === c.key;
            return (
              <th key={c.key} scope="col" aria-sort={on ? (sort!.dir === "asc" ? "ascending" : "descending") : "none"} className={cn("px-3 py-2 font-medium text-muted-foreground", c.numeric && "text-right")}>
                <button
                  className="inline-flex items-center gap-1 hover:text-foreground"
                  onClick={() => setSort(on && sort!.dir === "desc" ? null : { key: c.key, dir: on ? "desc" : "asc" })}
                >
                  {c.label}
                  {on && (sort!.dir === "asc" ? <ArrowUp className="size-3" aria-hidden /> : <ArrowDown className="size-3" aria-hidden />)}
                </button>
              </th>
            );
          })}
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => (
          <tr
            key={r.id}
            onClick={onRow ? () => onRow(r) : undefined}
            className={cn("border-b border-border/50 hover:bg-accent/40", onRow && "cursor-pointer", selected === r.id && "bg-signal/10")}
          >
            {t.columns.map((c, i) => (
              <td key={c.key} className={cn("px-3 py-1.5 whitespace-nowrap", c.numeric ? "text-right font-mono tabular-nums" : i === 0 && "font-mono", r[c.key] === null && "text-muted-foreground/60")}>
                {fmt(r[c.key], c.numeric)}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

/**
 * The Data half of Graph | Data: Nodes / Edges tables (filter, sort, CSV) and the raw JSON (copy, download).
 * `onNode` lets a row jump back to the graph with that node selected.
 */
export function DataView({ data, name, onNode, selected, className }: { data: GraphData; name: string; onNode?: (id: string) => void; selected?: string | null; className?: string }) {
  const [tab, setTab] = useState<Tab>("nodes");
  const [q, setQ] = useState("");
  const [copied, setCopied] = useState(false);
  const json = useMemo(() => JSON.stringify(data.raw, null, 2), [data.raw]);
  const table = tab === "edges" ? data.edges : data.nodes;
  const shown = useMemo(() => ({ ...table, rows: filterRows(table.rows, q) }), [table, q]);
  const file = name.replace(/[^\w.-]+/g, "_");
  const tabs: [Tab, string][] = [
    ["nodes", `Nodes · ${data.nodes.rows.length}`],
    ["edges", `Edges · ${data.edges.rows.length}`],
    ["json", "JSON"],
  ];

  return (
    <div className={cn("flex min-h-0 flex-col overflow-hidden rounded-xl border border-border bg-card/60", className)}>
      <div className="flex flex-wrap items-center gap-2 border-b border-border px-3 py-2">
        <div role="tablist" aria-label="Graph data" className="inline-flex rounded-md bg-obsidian p-0.5 shadow-subtle">
          {tabs.map(([t, label]) => (
            <button key={t} role="tab" aria-selected={tab === t} onClick={() => setTab(t)} className="rounded px-2.5 py-1 text-xs text-muted-foreground aria-selected:bg-graphite aria-selected:text-paper">
              {label}
            </button>
          ))}
        </div>
        {tab !== "json" && (
          <label className="relative ml-1 min-w-[180px] flex-1 sm:max-w-xs">
            <Search className="pointer-events-none absolute top-1/2 left-2 size-3.5 -translate-y-1/2 text-muted-foreground" aria-hidden />
            <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="filter rows… (all words)" aria-label="Filter rows" className="h-7 pl-7 text-xs" />
          </label>
        )}
        <div className="ml-auto flex items-center gap-1">
          {tab === "json" ? (
            <button
              onClick={() => navigator.clipboard?.writeText(json).then(() => (setCopied(true), setTimeout(() => setCopied(false), 1200)))}
              className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs text-muted-foreground hover:bg-accent hover:text-foreground"
            >
              {copied ? <Check className="size-3.5 text-st-confirmed" aria-hidden /> : <Copy className="size-3.5" aria-hidden />} {copied ? "Copied" : "Copy"}
            </button>
          ) : (
            <button
              onClick={() => download(`${file}-${tab}.csv`, toCsv(shown), "text/csv;charset=utf-8")}
              className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs text-muted-foreground hover:bg-accent hover:text-foreground"
              title={q ? "Download the filtered rows" : "Download every row"}
            >
              <Download className="size-3.5" aria-hidden /> CSV{q && ` (${shown.rows.length})`}
            </button>
          )}
          <button
            onClick={() => download(`${file}.json`, json, "application/json")}
            className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs text-muted-foreground hover:bg-accent hover:text-foreground"
          >
            <Download className="size-3.5" aria-hidden /> JSON
          </button>
        </div>
      </div>
      <div className="min-h-0 flex-1 overflow-auto">
        {tab === "json" ? (
          <pre className="p-3 font-mono text-[11px] leading-relaxed text-muted-foreground">{json}</pre>
        ) : (
          <Grid t={shown} selected={selected} onRow={tab === "nodes" && onNode ? (r) => onNode(r.id) : undefined} />
        )}
      </div>
    </div>
  );
}
