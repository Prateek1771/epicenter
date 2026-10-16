"use client";

import { useEffect, useRef, useState } from "react";

import { streamUrl } from "./api";
import { type StreamEvent } from "./incident-state";

export type StreamState = "connecting" | "live" | "reconnecting" | "closed";

const EVENTS = [
  "incident.status",
  "hypothesis.created",
  "evidence.added",
  "footprint",
  "hypothesis.status",
  "verdict",
  "no_root_cause",
  "memory.similar",
  "explanation",
  "action",
  "error",
];

/**
 * Live incident events (LLD §9). Opens the stream right after the snapshot (`after` = its `last_seq`).
 * The browser's own EventSource retry resends `Last-Event-ID`; if the connection is closed for good (API restarted,
 * 503), this hook reopens it with `?after=<last seq seen>` and backoff. Either way the reducer drops anything it
 * already applied, so a replay never duplicates nodes.
 */
export function useIncidentStream(
  incident: string | null,
  env: string | null,
  after: number | null,
  onEvent: (e: StreamEvent) => void,
): StreamState {
  const [state, setState] = useState<StreamState>("connecting");
  const last = useRef(after ?? 0);
  const handler = useRef(onEvent);
  handler.current = onEvent;

  useEffect(() => {
    if (!incident || after === null) return;
    last.current = Math.max(last.current, after);
    let es: EventSource | null = null;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let attempt = 0;
    let stopped = false;

    const open = () => {
      es = new EventSource(streamUrl(incident, env, last.current));
      es.onopen = () => {
        attempt = 0;
        setState("live");
      };
      const receive = (ev: MessageEvent) => {
        const seq = Number(ev.lastEventId);
        if (!Number.isFinite(seq) || seq <= last.current) return;
        last.current = seq;
        handler.current({ seq, event: ev.type, data: JSON.parse(ev.data) });
      };
      for (const name of EVENTS) es.addEventListener(name, receive as EventListener);
      es.onerror = () => {
        if (stopped || !es) return;
        if (es.readyState === EventSource.CLOSED) {
          // the browser gave up: reopen ourselves from the last seq we applied
          setState("reconnecting");
          es.close();
          timer = setTimeout(open, Math.min(10_000, 500 * 2 ** attempt++));
        } else {
          setState("reconnecting"); // the browser is retrying with Last-Event-ID
        }
      };
    };
    open();
    return () => {
      stopped = true;
      clearTimeout(timer);
      es?.close();
      setState("closed");
    };
  }, [incident, env, after]);

  return state;
}
