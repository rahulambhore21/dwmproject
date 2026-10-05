import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { CsvPreview } from "@/lib/types";
import { CsvImporter } from "./csv-importer";

const REQUIRED = ["platform", "format", "published_at", "impressions", "reach", "likes", "comments", "shares", "saves"];
const OPTIONAL = ["external_id", "topic", "hook_type", "tone", "caption", "media_count"];

const preview = (over: Partial<CsvPreview> = {}): CsvPreview => ({
  filename: "export.csv",
  row_count: 42,
  headers: ["Channel", "Views", "Date"],
  mapping: Object.fromEntries([...REQUIRED, ...OPTIONAL].map((f) => [f, null])),
  sample: [{ Channel: "Instagram", Views: "1,000", Date: "2026-03-04" }],
  fields: [...REQUIRED.map((name) => ({ name, required: true })), ...OPTIONAL.map((name) => ({ name, required: false }))],
  missing_required: REQUIRED,
  ...over,
});

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const pick = (file = new File(["a,b\n1,2"], "export.csv", { type: "text/csv" })) =>
  userEvent.upload(screen.getByLabelText("CSV file"), file);

afterEach(() => vi.restoreAllMocks());

describe("CsvImporter", () => {
  it("shows the detected mapping and blocks import until required fields are mapped", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(json(preview()));
    render(<CsvImporter onDone={() => {}} />);
    await pick();
    expect(await screen.findByText(/42 rows/)).toBeInTheDocument();
    expect(screen.getByText(/Still needed: platform/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Import and retrain/ })).toBeDisabled();
  });

  it("rejects one column feeding several fields", async () => {
    const mapping = { ...preview().mapping, ...Object.fromEntries(REQUIRED.map((f) => [f, "Channel"])) };
    vi.spyOn(globalThis, "fetch").mockResolvedValue(json(preview({ mapping, missing_required: [] })));
    render(<CsvImporter onDone={() => {}} />);
    await pick();
    await screen.findByText(/42 rows/);
    expect(screen.getByText(/A column can only feed one field/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Import and retrain/ })).toBeDisabled();
  });

  it("sends mapping + mode, then reports defaults and rejections", async () => {
    const headers = REQUIRED.map((f) => `col_${f}`);
    const mapping = { ...preview().mapping, ...Object.fromEntries(REQUIRED.map((f) => [f, `col_${f}`])) };
    const spy = vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(json(preview({ headers, mapping, missing_required: [] })));
    const onDone = vi.fn();
    render(<CsvImporter onDone={onDone} />);
    await pick();
    await waitFor(() => expect(screen.getByRole("button", { name: /Import and retrain/ })).toBeEnabled());

    spy.mockResolvedValueOnce(json({
      report: {
        rows_in: 42, rows_valid: 40, rows_loaded: 40, rows_rejected: 2, duplicates_skipped: 0, rejection_reasons: {},
        rejection_examples: [{ row: 7, reason: "impressions: Input should be greater than or equal to 1" }],
        warehouse: { fact_rows: 40, dimensions: {} }, mode: "replace", defaulted_fields: ["topic", "tone"],
      },
    }));
    await userEvent.click(screen.getByLabelText(/Replace everything/));
    await userEvent.click(screen.getByRole("button", { name: /Replace data and retrain/ }));

    expect(await screen.findByText(/40 of 42 rows loaded/)).toBeInTheDocument();
    expect(screen.getByText(/previous data replaced/)).toBeInTheDocument();
    expect(screen.getByText(/topic, tone/)).toBeInTheDocument();
    expect(screen.getByText(/row 7: impressions/)).toBeInTheDocument();
    expect(onDone).toHaveBeenCalledTimes(1);

    const body = spy.mock.calls.at(-1)![1]!.body as FormData;
    expect(body.get("mode")).toBe("replace");
    expect(JSON.parse(body.get("mapping") as string).platform).toBe("col_platform");
  });

  it("surfaces an API error for a bad file", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(json({ error: { code: "bad_encoding", message: "CSV must be UTF-8 encoded." } }, 422));
    render(<CsvImporter onDone={() => {}} />);
    await pick();
    expect(await screen.findByText("CSV must be UTF-8 encoded.")).toBeInTheDocument();
  });
});
