"use client";

import { useEffect, useMemo, useState } from "react";
import { Section } from "@/components/editorial";
import { EmptyState, ErrorState, LoadingBlock } from "@/components/states";
import { Field, Select } from "@/components/ui/select";
import { api } from "@/lib/api";
import { compact, int, pct } from "@/lib/format";
import type { OlapQueryInput, OlapResult, OlapSchema, Vocabulary } from "@/lib/types";
import { useAction, useApi } from "@/lib/use-api";
import { cn } from "@/lib/utils";

const NONE = "";
const FILTERS: { dim: string; label: string }[] = [
  { dim: "platform", label: "Platform" }, { dim: "format", label: "Format" }, { dim: "topic", label: "Topic" }, { dim: "hook", label: "Hook" }, { dim: "tone", label: "Tone" },
];
type RateKey = "median_engagement_rate" | "save_rate" | "share_rate" | "comment_rate";
const RATE_COLS: { key: RateKey; label: string }[] = [
  { key: "median_engagement_rate", label: "Median ER" }, { key: "save_rate", label: "Save rate" }, { key: "share_rate", label: "Share rate" }, { key: "comment_rate", label: "Comment rate" },
];

export function PivotTab() {
  const schema = useApi<OlapSchema>("/olap/schema");
  const vocab = useApi<Vocabulary>("/vocabulary");
  const [rows, setRows] = useState<string[]>(["platform", "format"]);
  const [column, setColumn] = useState(NONE);
  const [measure, setMeasure] = useState("engagement_rate");
  const [filters, setFilters] = useState<Record<string, string>>({});
  const [rollup, setRollup] = useState(true);
  const [result, setResult] = useState<OlapResult | null>(null);
  const query = useAction((q: OlapQueryInput) => api.post<OlapResult>("/olap/query", q));

  const input = useMemo<OlapQueryInput>(() => {
    const active = rows.filter(Boolean);
    const f: Record<string, string[]> = {};
    for (const [k, v] of Object.entries(filters)) if (v) f[k] = [v];
    return { rows: active, columns: column || null, measures: ["posts", "engagement_rate", "median_engagement_rate", "save_rate", "share_rate", "comment_rate"], filters: f, rollup: rollup && active.length > 1 && !column, sort_by: column ? measure : null, descending: true, limit: 200 };
  }, [rows, column, measure, filters, rollup]);
  useEffect(() => {
    if (input.rows.length === 0) return;
    let live = true;
    query.run(input).then((r) => live && r && setResult(r));
    return () => { live = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [input]);

  const dims = schema.data?.dimensions ?? [];
  const measures = schema.data?.measures.filter((m) => m.key !== "posts") ?? [];
  const options = (dim: string) => (dim === "platform" ? Object.keys(vocab.data?.platforms ?? {}) : dim === "topic" ? vocab.data?.topics ?? [] : dim === "hook" ? vocab.data?.hooks ?? [] : dim === "tone" ? vocab.data?.tones ?? [] : [...new Set(Object.values(vocab.data?.platforms ?? {}).flatMap((p) => p.formats.map((f) => f.name)))].sort());
  const setRow = (i: number, v: string) => setRows((r) => { const n = [...r]; n[i] = v; return n; });

  return (
    <Section title="OLAP pivot" kicker="Roll-up · drill-down · slice · dice · pivot" aside={result?.status === "ok" ? `${int(result.n_posts)} posts in scope` : undefined} className="mt-0">
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {[0, 1, 2].map((i) => (
          <Field key={i} label={i === 0 ? "Rows" : `Then by (drill-down ${i})`} htmlFor={`row-${i}`}>
            <Select id={`row-${i}`} value={rows[i] ?? NONE} onChange={(e) => setRow(i, e.target.value)}>
              {i > 0 && <option value={NONE}>—</option>}
              {dims.filter((d) => d.key === rows[i] || !rows.includes(d.key)).map((d) => <option key={d.key} value={d.key}>{d.label}</option>)}
            </Select>
          </Field>
        ))}
        <Field label="Pivot columns" htmlFor="col"><Select id="col" value={column} onChange={(e) => setColumn(e.target.value)}><option value={NONE}>None</option>{dims.filter((d) => !rows.includes(d.key)).map((d) => <option key={d.key} value={d.key}>{d.label}</option>)}</Select></Field>
        {column && <Field label="Cell measure" htmlFor="meas"><Select id="meas" value={measure} onChange={(e) => setMeasure(e.target.value)}>{measures.map((m) => <option key={m.key} value={m.key}>{m.label}</option>)}</Select></Field>}
      </div>
      <fieldset className="mt-4 grid gap-4 border-t border-line pt-4 sm:grid-cols-3 lg:grid-cols-6">
        <legend className="eyebrow mb-3 float-left w-full">Slice / dice</legend>
        {FILTERS.map((f) => (
          <Field key={f.dim} label={f.label} htmlFor={`flt-${f.dim}`}><Select id={`flt-${f.dim}`} value={filters[f.dim] ?? ""} onChange={(e) => setFilters({ ...filters, [f.dim]: e.target.value })}><option value="">All</option>{options(f.dim).map((o) => <option key={o}>{o}</option>)}</Select></Field>
        ))}
        <label className="flex items-end gap-2 pb-2 text-sm"><input type="checkbox" checked={rollup} onChange={(e) => setRollup(e.target.checked)} disabled={rows.filter(Boolean).length < 2 || !!column} />Subtotals (roll-up)</label>
      </fieldset>

      <div className="mt-8">
        {query.error && <ErrorState error={query.error} onRetry={() => query.run(input).then((r) => r && setResult(r))} />}
        {!result && !query.error && <LoadingBlock rows={6} label="Running query" />}
        {result?.status === "empty" && <EmptyState title="No data in this slice">{result.message}</EmptyState>}
        {result?.status === "ok" && (result.pivot ? <PivotTable result={result} /> : <FlatTable result={result} dims={input.rows} />)}
        <p className="mt-3 text-xs text-mute">Rates are per-post means (each post counts once) with 95% t-intervals. † marks cells with fewer than {result?.low_sample_threshold ?? 8} posts: read them as anecdotes.</p>
      </div>
    </Section>
  );
}

function FlatTable({ result, dims }: { result: OlapResult; dims: string[] }) {
  const max = Math.max(...result.rows.map((r) => r.engagement_rate), 1e-9);
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[44rem] text-sm">
        <thead><tr className="eyebrow border-b border-ink text-left">
          {dims.map((d) => <th key={d} className="py-2 font-normal capitalize">{d}</th>)}
          <th className="text-right font-normal">Posts</th><th className="w-48 pl-6 font-normal">Avg engagement (95% CI)</th>
          {RATE_COLS.map((c) => <th key={c.key} className="hidden text-right font-normal lg:table-cell">{c.label}</th>)}
        </tr></thead>
        <tbody>
          {result.rows.map((r, i) => {
            const sub = r.level < dims.length;
            return (
              <tr key={i} className={cn("border-b border-line", sub && "bg-paper-2 font-semibold")}>
                {dims.map((d, di) => <td key={d} className={cn("py-2", di >= r.level && sub && "text-mute")}>{r.keys[d] ?? (sub ? (di === r.level ? "subtotal" : "") : "")}</td>)}
                <td className="num text-right">{int(r.posts)}{r.low_sample && <span title="Low sample"> †</span>}</td>
                <td className="pl-6">
                  <div className="flex items-center gap-2"><div className="relative h-2 flex-1 bg-paper-2"><div className="absolute inset-y-0 left-0 bg-ink" style={{ width: `${(r.engagement_rate / max) * 100}%` }} />{r.er_ci_low !== null && r.er_ci_high !== null && <div className="absolute top-1/2 h-px -translate-y-1/2 bg-alert" style={{ left: `${(r.er_ci_low / max) * 100}%`, width: `${Math.min(100, ((r.er_ci_high - r.er_ci_low) / max) * 100)}%` }} />}</div><span className="num w-14 text-right">{pct(r.engagement_rate, 2)}</span></div>
                </td>
                {RATE_COLS.map((c) => <td key={c.key} className="num hidden text-right lg:table-cell">{pct(r[c.key], 2)}</td>)}
              </tr>
            );
          })}
        </tbody>
        {result.totals && <tfoot><tr className="border-t border-ink font-semibold"><td colSpan={dims.length} className="py-2">Total</td><td className="num text-right">{int(result.totals.posts)}</td><td className="num pl-6 text-right">{pct(result.totals.engagement_rate, 2)}</td>{RATE_COLS.map((c) => <td key={c.key} className="num hidden text-right lg:table-cell">{pct(result.totals![c.key], 2)}</td>)}</tr><tr className="hidden"><td>{compact(result.totals.impressions)}</td></tr></tfoot>}
      </table>
    </div>
  );
}

function PivotTable({ result }: { result: OlapResult }) {
  const pv = result.pivot!;
  const vals = pv.rows.flatMap((r) => r.cells.map((c) => c?.value).filter((v): v is number => v !== null && v !== undefined));
  const lo = Math.min(...vals), hi = Math.max(...vals);
  const isRate = pv.measure.endsWith("rate");
  const fmt = (v: number) => (isRate ? pct(v, 2) : compact(v));
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[32rem] border-collapse text-sm">
        <thead><tr className="eyebrow border-b border-ink text-left"><th className="py-2 font-normal capitalize">{pv.row_dimensions.join(" · ")}</th>{pv.column_labels.map((c) => <th key={String(c)} className="text-right font-normal">{c}</th>)}</tr></thead>
        <tbody>
          {pv.rows.map((r, i) => (
            <tr key={i} className="border-b border-line">
              <td className="py-2 pr-4">{Object.values(r.keys).join(" · ")}</td>
              {r.cells.map((c, j) => {
                const t = c && c.value !== null && hi > lo ? (c.value - lo) / (hi - lo) : 0;
                return (
                  <td key={j} className="num px-3 py-2 text-right" style={c && c.value !== null ? { background: `rgba(200,241,53,${(0.08 + t * 0.75).toFixed(2)})` } : undefined}>
                    {c && c.value !== null ? <><span>{fmt(c.value)}</span><span className="block text-[10px] text-mute">n={c.posts}{c.low_sample ? " †" : ""}</span></> : <span className="text-mute">—</span>}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
