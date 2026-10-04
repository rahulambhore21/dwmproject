"use client";

import { CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { monthLabel, pct } from "@/lib/format";
import { cn } from "@/lib/utils";

const INK = "#111111";
const MUTE = "#9b9585";

export interface TrendPoint {
  month: string;
  [series: string]: number | string | null;
}

/** Monthly engagement trend. One bold ink line; optional quieter comparison series. */
export function TrendChart({ data, primary, secondary = [], height = 280, baseline }: { data: TrendPoint[]; primary: string; secondary?: string[]; height?: number; baseline?: number }) {
  if (data.length === 0) return null;
  return (
    <div role="img" aria-label={`Line chart of ${primary} by month`} style={{ height }} className="w-full">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 8, right: 12, bottom: 0, left: -8 }}>
          <CartesianGrid vertical={false} strokeDasharray="2 4" />
          <XAxis dataKey="month" tickFormatter={monthLabel} tickLine={false} axisLine={{ stroke: INK }} minTickGap={24} />
          <YAxis tickFormatter={(v: number) => pct(v, 0)} tickLine={false} axisLine={false} width={44} domain={[0, "auto"]} />
          <Tooltip
            cursor={{ stroke: INK, strokeWidth: 1 }}
            content={({ active, payload, label }) =>
              active && payload?.length ? (
                <div className="border border-ink bg-paper px-3 py-2 text-xs shadow-none">
                  <p className="eyebrow mb-1">{monthLabel(String(label))}</p>
                  {payload.map((p) => (
                    <p key={String(p.dataKey)} className="num flex justify-between gap-4">
                      <span className="text-mute">{String(p.dataKey)}</span>
                      <span>{pct(p.value as number, 2)}</span>
                    </p>
                  ))}
                </div>
              ) : null
            }
          />
          {baseline !== undefined && <ReferenceLine y={baseline} stroke={MUTE} strokeDasharray="3 3" />}
          {secondary.map((s) => (
            <Line key={s} type="monotone" dataKey={s} stroke={MUTE} strokeWidth={1.25} dot={false} connectNulls />
          ))}
          <Line type="monotone" dataKey={primary} stroke={INK} strokeWidth={2.25} dot={{ r: 2.5, fill: INK, stroke: INK }} activeDot={{ r: 5, fill: "#c8f135", stroke: INK, strokeWidth: 1.5 }} connectNulls />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

/** Ranked horizontal bars (labels left, value right), optional noise-floor tick. */
export function HBars({ items, format = (v: number) => v.toFixed(3), className }: { items: { label: string; value: number; floor?: number; note?: string; highlight?: boolean }[]; format?: (v: number) => string; className?: string }) {
  const max = Math.max(...items.map((i) => Math.max(i.value, i.floor ?? 0)), 1e-9);
  return (
    <ul className={cn("space-y-2.5", className)}>
      {items.map((i) => (
        <li key={i.label} className="grid grid-cols-[minmax(7rem,11rem)_1fr_auto] items-center gap-3 text-sm">
          <span className="truncate" title={i.label}>{i.label}</span>
          <div className="relative h-3 bg-paper-2" role="img" aria-label={`${i.label}: ${format(i.value)}${i.floor !== undefined ? `, noise floor ${format(i.floor)}` : ""}`}>
            <div className={cn("absolute inset-y-0 left-0", i.highlight ? "bg-ink" : "bg-mute/60")} style={{ width: `${(i.value / max) * 100}%` }} />
            {i.floor !== undefined && <div className="absolute -inset-y-1 w-px bg-alert" style={{ left: `${(i.floor / max) * 100}%` }} title="Noise floor (95th percentile of shuffled data)" />}
          </div>
          <span className="num w-16 text-right text-xs">{format(i.value)}</span>
        </li>
      ))}
    </ul>
  );
}

/** Diverging bars around zero: positive = ink, negative = alert. Values are percent effects. */
export function DivergingBars({ items, max }: { items: { label: string; value: number; detail?: string }[]; max?: number }) {
  const m = max ?? Math.max(...items.map((i) => Math.abs(i.value)), 1);
  return (
    <ul className="space-y-2.5">
      {items.map((i) => (
        <li key={i.label} className="grid grid-cols-[minmax(6rem,10rem)_1fr_auto] items-center gap-3 text-sm">
          <span className="truncate" title={i.detail ? `${i.label}: ${i.detail}` : i.label}>
            {i.label}
            {i.detail && <span className="block truncate text-xs text-mute">{i.detail}</span>}
          </span>
          <div className="relative h-3" role="img" aria-label={`${i.label}: ${i.value.toFixed(1)} percent`}>
            <div className="absolute inset-y-0 left-1/2 w-px bg-ink" />
            <div
              className={cn("absolute inset-y-0", i.value >= 0 ? "bg-ink" : "bg-alert")}
              style={i.value >= 0 ? { left: "50%", width: `${(i.value / m) * 50}%` } : { right: "50%", width: `${(-i.value / m) * 50}%` }}
            />
          </div>
          <span className="num w-16 text-right text-xs">{i.value > 0 ? "+" : i.value < 0 ? "−" : ""}{Math.abs(i.value).toFixed(1)}%</span>
        </li>
      ))}
    </ul>
  );
}

/** Mean with interval on a shared axis (SVG). Used to compare variants honestly, with n visible. */
export function IntervalPlot({ rows, format = (v: number) => pct(v, 2), min, max }: { rows: { label: string; mean: number; low?: number; high?: number; n: number; points?: number[]; emphasis?: boolean }[]; format?: (v: number) => string; min?: number; max?: number }) {
  const all = rows.flatMap((r) => [r.mean, r.low ?? r.mean, r.high ?? r.mean, ...(r.points ?? [])]);
  const lo = min ?? Math.max(0, Math.min(...all) * 0.85);
  const hi = max ?? Math.max(...all) * 1.08;
  const x = (v: number) => ((v - lo) / (hi - lo || 1)) * 100;
  return (
    <div className="space-y-4">
      {rows.map((r) => (
        <div key={r.label} className="grid grid-cols-[5.5rem_1fr_6rem] items-center gap-3 text-sm">
          <div>
            <p className="font-medium">{r.label}</p>
            <p className="num text-xs text-mute">n={r.n}</p>
          </div>
          <div className="relative h-8" role="img" aria-label={`${r.label}: mean ${format(r.mean)}, n=${r.n}`}>
            <div className="absolute inset-x-0 top-1/2 h-px bg-line" />
            {(r.points ?? []).map((v, i) => (
              <span key={i} className="absolute top-1/2 size-1.5 -translate-x-1/2 -translate-y-1/2 rounded-full bg-mute/70" style={{ left: `${x(v)}%` }} />
            ))}
            {r.low !== undefined && r.high !== undefined && (
              <div className="absolute top-1/2 h-1 -translate-y-1/2 bg-ink/25" style={{ left: `${x(r.low)}%`, width: `${x(r.high) - x(r.low)}%` }} />
            )}
            <span className={cn("absolute top-1/2 size-3.5 -translate-x-1/2 -translate-y-1/2 border-2 border-ink", r.emphasis ? "bg-lime" : "bg-paper")} style={{ left: `${x(r.mean)}%` }} />
          </div>
          <p className="num text-right">{format(r.mean)}</p>
        </div>
      ))}
    </div>
  );
}

/** Predicted value with 80% range against the platform median (SVG-free, accessible). */
export function RangeBar({ value, low, high, marker, max, markerLabel }: { value: number; low: number; high: number; marker: number; max?: number; markerLabel: string }) {
  const m = max ?? Math.max(high, marker) * 1.15;
  const x = (v: number) => `${(v / m) * 100}%`;
  return (
    <div className="space-y-2">
      <div className="relative h-10" role="img" aria-label={`Predicted ${pct(value, 2)}, 80% range ${pct(low, 2)} to ${pct(high, 2)}, ${markerLabel} ${pct(marker, 2)}`}>
        <div className="absolute inset-x-0 top-1/2 h-px bg-line" />
        <div className="absolute top-1/2 h-3 -translate-y-1/2 bg-lime/70" style={{ left: x(low), width: `calc(${x(high)} - ${x(low)})` }} />
        <div className="absolute top-1/2 h-6 w-0.5 -translate-y-1/2 bg-ink" style={{ left: x(value) }} />
        <div className="absolute top-0 h-10 w-px bg-alert" style={{ left: x(marker) }} />
      </div>
      <div className="num flex justify-between text-[11px] text-mute">
        <span>{pct(low, 1)} low</span>
        <span className="text-alert">▏{markerLabel} {pct(marker, 1)}</span>
        <span>high {pct(high, 1)}</span>
      </div>
    </div>
  );
}
