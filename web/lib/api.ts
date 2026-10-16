/**
 * Typed API client. Types come from the API's own OpenAPI schema (`npm run gen:api` → lib/api-types.ts), so the UI
 * can't drift from the backend: there are no hand-written copies of response shapes here.
 */
import createClient from "openapi-fetch";

import type { components, paths } from "./api-types";

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";
const ORIGIN = API_URL.replace(/\/api\/v1\/?$/, "");

export const api = createClient<paths>({ baseUrl: ORIGIN });

export type S = components["schemas"];

/** The API's error envelope (docs/API.md#errors), or a network failure (`code: "NETWORK"`). */
export class ApiError extends Error {
  constructor(
    public code: string,
    message: string,
    public status: number,
    public requestId?: string | null,
  ) {
    super(message);
  }
}

type Envelope = { error?: { code?: string; message?: string }; request_id?: string | null };

/** Unwrap an openapi-fetch result: the data, or an ApiError carrying the envelope's code and request id. */
export async function call<T>(p: Promise<{ data?: T; error?: unknown; response: Response }>): Promise<T> {
  let res;
  try {
    res = await p;
  } catch (e) {
    throw new ApiError("NETWORK", e instanceof Error ? e.message : "network error", 0);
  }
  if (res.data !== undefined && res.response.ok) return res.data;
  const env = (res.error ?? {}) as Envelope;
  throw new ApiError(
    env.error?.code ?? `HTTP_${res.response.status}`,
    env.error?.message ?? res.response.statusText,
    res.response.status,
    env.request_id,
  );
}

export function streamUrl(incident: string, env: string | null, after: number): string {
  const q = new URLSearchParams({ after: String(after) });
  if (env) q.set("env", env);
  return `${API_URL}/incidents/${encodeURIComponent(incident)}/stream?${q}`;
}
