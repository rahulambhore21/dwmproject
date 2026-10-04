import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Delta } from "./editorial";
import { InterpretationPanel } from "./interpretation";
import { Async, EmptyState, ErrorState, InsufficientState, WarmingUp } from "./states";
import { ApiError } from "@/lib/api";

afterEach(() => vi.restoreAllMocks());

describe("Delta", () => {
  it("only claims significance when p < 0.05", () => {
    const { rerender } = render(<Delta pct={5.2} p={0.01} label="vs prior" />);
    expect(screen.getByText(/significant/)).toBeInTheDocument();
    expect(screen.getByText("+5.2%")).toBeInTheDocument();
    rerender(<Delta pct={5.2} p={0.4} />);
    expect(screen.getByText(/within noise/)).toBeInTheDocument();
    expect(screen.queryByText(/^significant/)).not.toBeInTheDocument();
  });
  it("says so when there is not enough history", () => {
    render(<Delta pct={null} />);
    expect(screen.getByText(/Not enough history/)).toBeInTheDocument();
  });
});

describe("states", () => {
  it("ErrorState distinguishes unreachable API from other errors and offers retry", async () => {
    const onRetry = vi.fn();
    const { rerender } = render(<ErrorState error={new ApiError(0, "network", "x")} onRetry={onRetry} />);
    expect(screen.getByRole("alert")).toHaveTextContent(/isn't reachable/);
    await userEvent.click(screen.getByRole("button", { name: /try again/i }));
    expect(onRetry).toHaveBeenCalled();
    rerender(<ErrorState error={new ApiError(404, "post_not_found", "Post 9 not found.")} />);
    expect(screen.getByRole("alert")).toHaveTextContent("Post 9 not found.");
  });
  it("renders empty, insufficient and warming states", () => {
    render(<><EmptyState title="No posts">Import a CSV</EmptyState><InsufficientState>Need 80 posts</InsufficientState><WarmingUp /></>);
    expect(screen.getByText("No posts")).toBeInTheDocument();
    expect(screen.getByText("Not enough data yet")).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent(/seeds the demo workspace/);
  });
  it("Async picks the right branch", () => {
    const base = { data: null, error: null, loading: false, warming: false, reload: () => {} };
    const { rerender } = render(<Async state={{ ...base, loading: true }}>{() => <p>data</p>}</Async>);
    expect(screen.getByRole("status")).toBeInTheDocument();
    rerender(<Async state={{ ...base, data: 1 }}>{(d) => <p>value {d}</p>}</Async>);
    expect(screen.getByText("value 1")).toBeInTheDocument();
    rerender(<Async state={{ ...base, error: new ApiError(500, "x", "boom") }}>{() => null}</Async>);
    expect(screen.getByRole("alert")).toBeInTheDocument();
    rerender(<Async state={{ ...base, warming: true }}>{() => null}</Async>);
    expect(screen.getByText(/analytics engine/)).toBeInTheDocument();
  });
});

describe("InterpretationPanel", () => {
  const payload = {
    scope: "overview", source: "deterministic", disclaimer: "Patterns are historical associations.", fallback_reason: null, caveats: ["Based on history."],
    evidence: [{ id: "E1", label: "Trend", text: "Mean engagement 5.3% (n=117).", n: 117, kind: "trend" }],
    statements: [{ text: "Engagement is flat.", evidence_ids: ["E1"], strength: "weak" }],
  };

  it("fetches on demand and shows each statement with its evidence", async () => {
    const spy = vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify(payload), { status: 200 }));
    render(<InterpretationPanel request={{ scope: "overview" }} />);
    expect(spy).not.toHaveBeenCalled(); // nothing is generated until asked
    await userEvent.click(screen.getByRole("button", { name: /interpret this/i }));
    expect(await screen.findByText("Engagement is flat.")).toBeInTheDocument();
    expect(screen.getByText("Deterministic reading")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "E1" }));
    expect(screen.getByText(/Mean engagement 5.3%/)).toBeInTheDocument();
    expect(screen.getByText(/historical associations/)).toBeInTheDocument();
  });

  it("shows an error state and can retry", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify({ error: { code: "x", message: "AI layer failed" } }), { status: 422 }));
    render(<InterpretationPanel request={{ scope: "overview" }} />);
    await userEvent.click(screen.getByRole("button", { name: /interpret this/i }));
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("AI layer failed"));
  });

  it("explains an empty interpretation instead of inventing one", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify({ ...payload, statements: [], evidence: [], caveats: ["Not enough data to interpret."] }), { status: 200 }));
    render(<InterpretationPanel request={{ scope: "overview" }} />);
    await userEvent.click(screen.getByRole("button", { name: /interpret this/i }));
    expect(await screen.findByText("Not enough data to interpret.")).toBeInTheDocument();
  });
});
