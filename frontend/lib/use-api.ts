"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, api } from "./api";

export interface ApiState<T> {
  data: T | null;
  error: ApiError | null;
  loading: boolean;
  /** true while the backend is still starting (auto-retrying) */
  warming: boolean;
  reload: () => void;
}

const MAX_WARMUP_RETRIES = 30;

interface Settled<T> {
  key: string;
  data: T | null;
  error: ApiError | null;
}

/**
 * GET hook with loading/error state. While the API boots (first-run seeding) it retries automatically.
 * Previous data is kept while a new request for the same hook is in flight (no flash on filter changes).
 */
export function useApi<T>(path: string | null): ApiState<T> {
  const [tick, setTick] = useState(0);
  const [settled, setSettled] = useState<Settled<T> | null>(null);
  const [warmingKey, setWarmingKey] = useState<string | null>(null);
  const [stale, setStale] = useState<T | null>(null);
  const key = path === null ? null : `${path}#${tick}`;

  useEffect(() => {
    if (path === null || key === null) return;
    const ctrl = new AbortController();
    let timer: ReturnType<typeof setTimeout> | undefined;
    let cancelled = false;
    let attempts = 0;
    const run = () => {
      api
        .get<T>(path, ctrl.signal)
        .then((d) => {
          if (cancelled) return;
          setStale(d);
          setWarmingKey(null);
          setSettled({ key, data: d, error: null });
        })
        .catch((e: unknown) => {
          if (cancelled || (e as Error).name === "AbortError") return;
          const err = e instanceof ApiError ? e : new ApiError(0, "network", "Unexpected error");
          if (err.isUnavailable && attempts < MAX_WARMUP_RETRIES) {
            attempts += 1;
            setWarmingKey(key);
            timer = setTimeout(run, Math.min(1000 + attempts * 250, 3000));
            return;
          }
          setWarmingKey(null);
          setSettled({ key, data: null, error: err });
        });
    };
    run();
    return () => {
      cancelled = true;
      ctrl.abort();
      if (timer) clearTimeout(timer);
    };
  }, [path, key]);

  const reload = useCallback(() => setTick((t) => t + 1), []);
  const current = settled !== null && settled.key === key;
  return {
    data: current ? settled.data : stale,
    error: current ? settled.error : null,
    loading: key !== null && !current,
    warming: warmingKey === key && key !== null,
    reload,
  };
}

/** Run an async action with pending/error state (for POSTs). */
export function useAction<A extends unknown[], R>(fn: (...args: A) => Promise<R>) {
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const fnRef = useRef(fn);
  useEffect(() => {
    fnRef.current = fn;
  });
  const run = useCallback(async (...args: A): Promise<R | undefined> => {
    setPending(true);
    setError(null);
    try {
      return await fnRef.current(...args);
    } catch (e) {
      setError(e instanceof ApiError ? e : new ApiError(0, "unknown", (e as Error).message));
      return undefined;
    } finally {
      setPending(false);
    }
  }, []);
  return { run, pending, error, clear: () => setError(null) };
}
