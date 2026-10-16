"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import { ApiError } from "./api";

const ENV_KEY = "epicenter.env";

/** The environment in view: `?env=` first, then the last one picked, else the API's default (null). */
export function useEnv(): [string | null, (env: string) => void] {
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const fromUrl = params.get("env");
  const [stored, setStored] = useState<string | null>(null);
  useEffect(() => {
    try {
      setStored(localStorage.getItem(ENV_KEY));
    } catch {
      /* storage blocked: the URL still works */
    }
  }, []);
  const set = useCallback(
    (env: string) => {
      try {
        localStorage.setItem(ENV_KEY, env);
      } catch {
        /* ignore */
      }
      const q = new URLSearchParams(params.toString());
      q.set("env", env);
      router.replace(`${pathname}?${q}`);
    },
    [params, pathname, router],
  );
  return [fromUrl ?? stored, set];
}

/** Query string with the current env, for links that keep it. */
export function withEnv(href: string, env: string | null): string {
  if (!env) return href;
  return `${href}${href.includes("?") ? "&" : "?"}env=${encodeURIComponent(env)}`;
}

export interface Query<T> {
  data: T | undefined;
  error: ApiError | undefined;
  loading: boolean;
  reload: () => void;
}

/** Minimal fetch hook: refetches when `key` changes, optional polling, keeps old data while reloading. */
export function useQuery<T>(key: string | null, fn: () => Promise<T>, refreshMs?: number): Query<T> {
  const [data, setData] = useState<T>();
  const [error, setError] = useState<ApiError>();
  const [loading, setLoading] = useState(key !== null);
  const [tick, setTick] = useState(0);
  const fnRef = useRef(fn);
  fnRef.current = fn;

  useEffect(() => {
    if (key === null) return;
    let live = true;
    setLoading(true);
    fnRef
      .current()
      .then((d) => live && (setData(d), setError(undefined)))
      .catch((e) => live && setError(e instanceof ApiError ? e : new ApiError("CLIENT", String(e), 0)))
      .finally(() => live && setLoading(false));
    return () => {
      live = false;
    };
  }, [key, tick]);

  useEffect(() => {
    if (!refreshMs || key === null) return;
    const t = setInterval(() => setTick((x) => x + 1), refreshMs);
    return () => clearInterval(t);
  }, [refreshMs, key]);

  return { data, error, loading, reload: () => setTick((x) => x + 1) };
}
