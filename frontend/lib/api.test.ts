import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, api, qs } from "./api";

const json = (status: number, body: unknown) => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

afterEach(() => vi.restoreAllMocks());

describe("api client", () => {
  it("returns parsed JSON on success", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(json(200, { ok: true }));
    await expect(api.get<{ ok: boolean }>("/health")).resolves.toEqual({ ok: true });
  });

  it("maps the backend error envelope onto ApiError", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(json(422, { error: { code: "invalid_draft", message: "Unknown platform 'X'" } }));
    const err = await api.post<never>("/lab/predict", {}).catch((e: ApiError) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err).toMatchObject({ status: 422, code: "invalid_draft", message: "Unknown platform 'X'" });
    expect(err.isUnavailable).toBe(false);
  });

  it("treats proxy failures and network errors as 'unavailable' so the UI can retry while the API boots", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(new Response("Internal Server Error", { status: 500 }));
    const proxy = await api.get<never>("/overview").catch((e: ApiError) => e);
    expect(proxy.isUnavailable).toBe(true);

    vi.spyOn(globalThis, "fetch").mockRejectedValueOnce(new TypeError("fetch failed"));
    const net = await api.get<never>("/overview").catch((e: ApiError) => e);
    expect(net).toMatchObject({ status: 0, code: "network" });
    expect(net.isUnavailable).toBe(true);
  });

  it("sends JSON bodies with the right header, and FormData without one", async () => {
    const spy = vi.spyOn(globalThis, "fetch").mockImplementation(() => Promise.resolve(json(200, {})));
    await api.post("/x", { a: 1 });
    expect(spy.mock.calls[0][1]).toMatchObject({ method: "POST", body: '{"a":1}', headers: { "Content-Type": "application/json" } });
    const fd = new FormData();
    await api.post("/y", fd);
    expect(spy.mock.calls[1][1]?.headers).toBeUndefined();
  });

  it("builds query strings, skipping empty values", () => {
    expect(qs({ a: 1, b: "", c: undefined, d: "x y" })).toBe("?a=1&d=x+y");
    expect(qs({})).toBe("");
  });
});
