"use client";

import { Loader2 } from "@/components/icons";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

/** Service name input with suggestions from the graph (any services list the page already has). */
export function ServicePicker({
  initial = "",
  suggestions,
  busy,
  label,
  onPick,
  children,
}: {
  initial?: string;
  suggestions: string[];
  busy?: boolean;
  label: string;
  onPick: (service: string) => void;
  children?: React.ReactNode;
}) {
  const [v, setV] = useState(initial);
  return (
    <form
      className="flex flex-wrap items-center gap-2"
      onSubmit={(e) => {
        e.preventDefault();
        if (v.trim()) onPick(v.trim());
      }}
    >
      <Input
        list="service-suggestions"
        aria-label="Service"
        placeholder="service, e.g. redis"
        value={v}
        onChange={(e) => setV(e.target.value)}
        className="h-9 w-64 font-mono"
      />
      <datalist id="service-suggestions">
        {[...new Set(suggestions)].sort().map((s) => (
          <option key={s} value={s} />
        ))}
      </datalist>
      {children}
      <Button type="submit" disabled={!v.trim() || busy}>
        {busy && <Loader2 className="size-4 animate-spin" />} {label}
      </Button>
    </form>
  );
}
