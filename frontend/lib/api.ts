// Minimal typed fetch client. All calls go through the Next.js /api proxy.

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public details?: { field: string; message: string }[],
  ) {
    super(message);
    this.name = "ApiError";
  }
  /** True when the backend is unreachable or still booting (proxy 5xx / network failure). */
  get isUnavailable() {
    return this.status === 0 || this.status === 502 || this.status === 503 || this.status === 504 || this.status === 500 && this.code === "proxy";
  }
}

async function parseError(res: Response): Promise<ApiError> {
  let body: unknown = null;
  try {
    body = await res.json();
  } catch {
    /* non-JSON error body (e.g. proxy failure) */
  }
  const err = (body as { error?: { code?: string; message?: string; details?: { field: string; message: string }[] } } | null)?.error;
  if (err) return new ApiError(res.status, err.code ?? "error", err.message ?? res.statusText, err.details);
  return new ApiError(res.status, res.status >= 500 ? "proxy" : "http_error", res.statusText || "Request failed");
}

async function request<T>(method: string, path: string, body?: unknown, signal?: AbortSignal): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`/api${path}`, {
      method,
      signal,
      cache: "no-store",
      headers: body instanceof FormData || body === undefined ? undefined : { "Content-Type": "application/json" },
      body: body === undefined ? undefined : body instanceof FormData ? body : JSON.stringify(body),
    });
  } catch (e) {
    if ((e as Error).name === "AbortError") throw e;
    throw new ApiError(0, "network", "Cannot reach the SIGNAL API.");
  }
  if (!res.ok) throw await parseError(res);
  return (await res.json()) as T;
}

export const api = {
  get: <T>(path: string, signal?: AbortSignal) => request<T>("GET", path, undefined, signal),
  post: <T>(path: string, body?: unknown, signal?: AbortSignal) => request<T>("POST", path, body, signal),
};

export function qs(params: Record<string, string | number | undefined | null>): string {
  const sp = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== null && v !== "") sp.set(k, String(v));
  const s = sp.toString();
  return s ? `?${s}` : "";
}
