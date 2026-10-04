import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "./api";
import { useApi } from "./use-api";

const ok = (body: unknown) => new Response(JSON.stringify(body), { status: 200 });

beforeEach(() => vi.useFakeTimers({ shouldAdvanceTime: true }));
afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

describe("useApi", () => {
  it("goes loading → data", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(ok({ n: 1 }));
    const { result } = renderHook(() => useApi<{ n: number }>("/x"));
    expect(result.current.loading).toBe(true);
    await waitFor(() => expect(result.current.data).toEqual({ n: 1 }));
    expect(result.current.loading).toBe(false);
    expect(result.current.error).toBeNull();
  });

  it("retries while the backend is warming up, then succeeds", async () => {
    const spy = vi
      .spyOn(globalThis, "fetch")
      .mockRejectedValueOnce(new TypeError("down"))
      .mockResolvedValueOnce(new Response("bad gateway", { status: 502 }))
      .mockResolvedValue(ok({ ready: true }));
    const { result } = renderHook(() => useApi<{ ready: boolean }>("/overview"));
    await waitFor(() => expect(result.current.warming).toBe(true));
    await act(async () => { await vi.advanceTimersByTimeAsync(5000); });
    await waitFor(() => expect(result.current.data).toEqual({ ready: true }));
    expect(result.current.warming).toBe(false);
    expect(spy).toHaveBeenCalledTimes(3);
  });

  it("surfaces real API errors immediately without retrying", async () => {
    const spy = vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify({ error: { code: "post_not_found", message: "nope" } }), { status: 404 }));
    const { result } = renderHook(() => useApi("/posts/1/autopsy"));
    await waitFor(() => expect(result.current.error).toBeInstanceOf(ApiError));
    expect(result.current.error?.code).toBe("post_not_found");
    expect(spy).toHaveBeenCalledTimes(1);
  });

  it("does nothing for a null path and reload re-fetches", async () => {
    const spy = vi.spyOn(globalThis, "fetch").mockResolvedValue(ok({}));
    const idle = renderHook(() => useApi(null));
    expect(idle.result.current.loading).toBe(false);
    expect(spy).not.toHaveBeenCalled();
    const live = renderHook(() => useApi("/z"));
    await waitFor(() => expect(live.result.current.data).toEqual({}));
    act(() => live.result.current.reload());
    await waitFor(() => expect(spy).toHaveBeenCalledTimes(2));
  });
});
