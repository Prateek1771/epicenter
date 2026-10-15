"use client";

import { useEffect, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";

type Health = Record<string, string>;

export function HealthCard() {
  const [health, setHealth] = useState<Health | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch(`${API_URL}/health`)
      .then((r) => r.json())
      .then(setHealth)
      .catch((e: Error) => setError(e.message));
  }, []);

  return (
    <Card>
      <CardHeader>
        <CardTitle>System health</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-wrap gap-2">
        {error && <Badge variant="destructive">API unreachable: {error}</Badge>}
        {!error && !health && <span className="text-muted-foreground text-sm">Checking…</span>}
        {health &&
          Object.entries(health).map(([k, v]) => (
            <Badge key={k} variant={v === "ok" ? "default" : "destructive"}>
              {k}: {v}
            </Badge>
          ))}
      </CardContent>
    </Card>
  );
}
