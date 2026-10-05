"use client";

import { Download, FileUp } from "lucide-react";
import { useId, useRef, useState } from "react";
import { ErrorState } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Input, Select } from "@/components/ui/select";
import { api } from "@/lib/api";
import { pct } from "@/lib/format";
import type { CsvPreview, EtlReport } from "@/lib/types";
import { useAction } from "@/lib/use-api";

type Mapping = Record<string, string | null>;
type Mode = "append" | "replace";

const FIELD_HELP: Record<string, string> = {
  platform: "e.g. Instagram, LinkedIn",
  format: "e.g. Reel, Carousel, Text",
  published_at: "date or date-time",
  impressions: "must be ≥ 1",
  reach: "≤ impressions",
  external_id: "generated from content if absent",
  topic: "defaults to Unspecified",
  hook_type: "defaults to Unspecified",
  tone: "defaults to Unspecified",
  caption: "used for text features and similarity",
  media_count: "defaults to 1",
};

export function CsvImporter({ onDone }: { onDone: () => void }) {
  const inputId = useId();
  const ref = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<CsvPreview | null>(null);
  const [mapping, setMapping] = useState<Mapping>({});
  const [mode, setMode] = useState<Mode>("append");
  const [dayFirst, setDayFirst] = useState(false);
  const [name, setName] = useState("");
  const [report, setReport] = useState<EtlReport | null>(null);

  const reset = () => { setFile(null); setPreview(null); setMapping({}); setMode("append"); setDayFirst(false); setName(""); };

  const inspect = useAction(async (f: File) => {
    const fd = new FormData();
    fd.append("file", f);
    const p = await api.post<CsvPreview>("/ingest/csv/preview", fd);
    setFile(f);
    setPreview(p);
    setMapping(p.mapping);
    setReport(null);
  });

  const commit = useAction(async () => {
    if (!file) return;
    const fd = new FormData();
    fd.append("file", file);
    fd.append("mapping", JSON.stringify(mapping));
    fd.append("mode", mode);
    fd.append("day_first", String(dayFirst));
    if (mode === "replace" && name.trim()) fd.append("workspace_name", name.trim());
    const r = await api.post<{ report: EtlReport }>("/ingest/csv", fd);
    setReport(r.report);
    reset();
    onDone();
  });

  const required = preview?.fields.filter((f) => f.required) ?? [];
  const optional = preview?.fields.filter((f) => !f.required) ?? [];
  const missing = required.filter((f) => !mapping[f.name]).map((f) => f.name);
  const used = Object.values(mapping).filter(Boolean) as string[];
  const dupes = used.filter((c, i) => used.indexOf(c) !== i);
  const canImport = !!preview && missing.length === 0 && dupes.length === 0;

  return (
    <div>
      <p className="max-w-2xl text-sm text-ink-2">
        Upload a UTF-8 CSV (≤ 5 MB, comma, semicolon or tab separated). SIGNAL detects your columns, you confirm the mapping, then every row is validated and anything rejected is reported with a reason. Nothing is imputed: engagement measures must come from your file.
      </p>
      <input ref={ref} type="file" accept=".csv,text/csv" className="sr-only" id={inputId} aria-label="CSV file"
        onChange={(e) => { const f = e.target.files?.[0]; if (f) inspect.run(f); e.target.value = ""; }} />
      <div className="mt-4 flex flex-wrap items-center gap-3">
        <Button variant="outline" loading={inspect.pending} onClick={() => ref.current?.click()}><FileUp className="size-4" />{preview ? "Choose a different file" : "Choose CSV"}</Button>
        <Button variant="ghost" asChild><a href="/api/ingest/template.csv" download><Download className="size-4" />Download template</a></Button>
      </div>
      {inspect.error && <div className="mt-4"><ErrorState error={inspect.error} /></div>}

      {preview && (
        <div className="mt-6 space-y-6 border border-line bg-card p-5">
          <div>
            <p className="font-medium">{preview.filename ?? "Uploaded file"}</p>
            <p className="num mt-1 text-xs text-mute">{preview.row_count} rows · {preview.headers.length} columns detected</p>
          </div>

          <fieldset>
            <legend className="eyebrow mb-3">Map your columns</legend>
            <div className="grid gap-x-6 gap-y-3 sm:grid-cols-2">
              {[...required, ...optional].map((f) => (
                <div key={f.name} className="space-y-1">
                  <label htmlFor={`map-${f.name}`} className="flex items-baseline justify-between text-xs">
                    <span className="num font-medium">{f.name}{f.required && <span className="text-alert" aria-label="required"> *</span>}</span>
                    <span className="text-mute">{FIELD_HELP[f.name] ?? (f.required ? "required" : "")}</span>
                  </label>
                  <Select id={`map-${f.name}`} value={mapping[f.name] ?? ""} onChange={(e) => setMapping((m) => ({ ...m, [f.name]: e.target.value || null }))}>
                    <option value="">{f.required ? "Select a column…" : "— not in my file —"}</option>
                    {preview.headers.map((h) => <option key={h} value={h}>{h}</option>)}
                  </Select>
                </div>
              ))}
            </div>
            {missing.length > 0 && <p role="alert" className="mt-3 text-xs text-alert">Still needed: {missing.join(", ")}.</p>}
            {dupes.length > 0 && <p role="alert" className="mt-3 text-xs text-alert">A column can only feed one field: {[...new Set(dupes)].join(", ")}.</p>}
          </fieldset>

          <div>
            <p className="eyebrow mb-2">First rows of your file</p>
            <div className="overflow-x-auto border border-line">
              <table className="w-full min-w-[32rem] text-xs">
                <thead><tr className="border-b border-ink text-left">{preview.headers.map((h) => <th key={h} className="whitespace-nowrap px-2 py-1.5 font-normal text-mute">{h}</th>)}</tr></thead>
                <tbody>{preview.sample.map((r, i) => <tr key={i} className="border-b border-line last:border-0">{preview.headers.map((h) => <td key={h} className="max-w-[14rem] truncate px-2 py-1.5">{r[h]}</td>)}</tr>)}</tbody>
              </table>
            </div>
          </div>

          <fieldset className="space-y-3">
            <legend className="eyebrow mb-1">What should happen to existing data?</legend>
            <label className="flex items-start gap-2 text-sm"><input type="radio" name="mode" className="mt-1" checked={mode === "append"} onChange={() => setMode("append")} /><span><strong>Add to current data.</strong> <span className="text-mute">Rows already present (same platform + id) are skipped. Mixing with the demo data blends two unrelated brands.</span></span></label>
            <label className="flex items-start gap-2 text-sm"><input type="radio" name="mode" className="mt-1" checked={mode === "replace"} onChange={() => setMode("replace")} /><span><strong>Replace everything with this file.</strong> <span className="text-mute">Deletes current posts, warehouse facts, experiments and learnings. Model-run history is kept. If no row in the file is valid, nothing is deleted.</span></span></label>
            {mode === "replace" && (
              <div className="max-w-sm space-y-1 pl-6">
                <label htmlFor="ws-name" className="eyebrow block">Workspace name (optional)</label>
                <Input id="ws-name" value={name} maxLength={120} placeholder="e.g. Acme Social" onChange={(e) => setName(e.target.value)} />
              </div>
            )}
            <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={dayFirst} onChange={(e) => setDayFirst(e.target.checked)} />Dates are day-first (31/12/2026, not 12/31/2026)</label>
          </fieldset>

          {commit.error && <ErrorState error={commit.error} />}
          <div className="flex flex-wrap gap-3">
            <Button variant={mode === "replace" ? "accent" : "primary"} disabled={!canImport} loading={commit.pending} onClick={() => commit.run()}>
              {mode === "replace" ? "Replace data and retrain" : "Import and retrain"}
            </Button>
            <Button variant="ghost" onClick={reset} disabled={commit.pending}>Cancel</Button>
          </div>
        </div>
      )}

      {report && (
        <div className="mt-6 border border-ink bg-card p-5 text-sm" role="status">
          <p className="font-medium">{report.rows_loaded} of {report.rows_in} rows loaded{report.mode === "replace" ? " · previous data replaced" : ""}</p>
          <p className="num mt-1 text-xs text-mute">{report.rows_rejected} rejected · {report.duplicates_skipped} duplicates skipped · warehouse now {report.warehouse.fact_rows} facts ({pct(report.rows_loaded / Math.max(report.rows_in, 1), 0)} accepted)</p>
          {report.defaulted_fields && report.defaulted_fields.length > 0 && <p className="mt-2 text-xs text-ink-2">Not in your file, so filled with neutral defaults: {report.defaulted_fields.join(", ")}. Analyses by those attributes will show a single group.</p>}
          {report.rejection_examples.length > 0 && <ul className="mt-3 list-disc space-y-0.5 pl-5 text-xs text-ink-2">{report.rejection_examples.slice(0, 8).map((x) => <li key={x.row}>row {x.row}: {x.reason}</li>)}</ul>}
        </div>
      )}
    </div>
  );
}
