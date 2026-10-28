"use client";

import { ArrowUpRight } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { CodeBlock } from "@/components/code-block";
import { PageHeader, Section } from "@/components/editorial";
import { Async, EmptyState, InsufficientState } from "@/components/states";
import { Badge } from "@/components/ui/badge";
import { dateShort, fixed, int, pct } from "@/lib/format";
import type { MethodEntry, MethodRun, Methods, OlapExample, StarTable } from "@/lib/types";
import { useApi } from "@/lib/use-api";
import { cn } from "@/lib/utils";

const WAREHOUSE_KEYS = ["etl", "warehouse"];
const OLAP_KEY = "olap";
const MODEL_GROUPS = ["All", "Predictive", "Descriptive", "Retrieval", "Experimentation"] as const;

export default function MethodsPage() {
  const state = useApi<Methods>("/methods");
  return (
    <>
      <PageHeader
        eyebrow="07 · Inspect"
        title="Under the hood."
        lede="Every algorithm in SIGNAL, how it works step by step, the metrics from its latest stored run, and the exact source that produced them. Nothing on this page is typed in by hand: code is read from the running modules and numbers from the model registry."
      />
      <Async state={state}>{(d) => <Body d={d} />}</Async>
    </>
  );
}

function Body({ d }: { d: Methods }) {
  const byKey = new Map(d.algorithms.map((a) => [a.key, a]));
  const warehouse = WAREHOUSE_KEYS.map((k) => byKey.get(k)).filter((a): a is MethodEntry => !!a);
  const olap = byKey.get(OLAP_KEY);
  const models = d.algorithms.filter((a) => ![...WAREHOUSE_KEYS, OLAP_KEY].includes(a.key));
  return (
    <>
      <nav aria-label="On this page" className="-mt-4 mb-2 flex flex-wrap gap-2 text-sm">
        {[["warehouse", "Warehouse & ETL"], ["olap", "OLAP queries"], ["algorithms", "Algorithms"]].map(([id, label]) => (
          <a key={id} href={`#${id}`} className="border border-line px-3 py-1 hover:border-ink">{label}</a>
        ))}
      </nav>

      <Section id="warehouse" title="Warehouse & ETL" kicker="Load → model" aside={d.has_data ? `${int(d.n_posts)} posts loaded` : undefined}>
        <StarSchema tables={d.star_schema.tables} grain={d.star_schema.grain} />
        <div className="mt-10 space-y-6">{warehouse.map((a) => <AlgorithmCard key={a.key} a={a} />)}</div>
      </Section>

      <Section id="olap" title="OLAP queries" kicker="Roll-up · drill-down · slice · dice · pivot">
        {olap && <AlgorithmCard a={olap} />}
        <OlapExplorer examples={d.olap.examples} note={d.olap.note} />
      </Section>

      <Section id="algorithms" title="Algorithms" kicker="Mining · prediction · experimentation">
        <ModelList models={models} />
      </Section>
    </>
  );
}

// ------------------------------------------------------------------ star schema
function StarSchema({ tables, grain }: { tables: StarTable[]; grain: string }) {
  const fact = tables.find((t) => t.role === "fact");
  const dims = tables.filter((t) => t.role === "dimension");
  return (
    <div>
      <p className="mb-4 text-sm text-ink-2"><span className="eyebrow mr-2">Grain</span>{grain}</p>
      <div className="grid gap-px border border-line bg-line lg:grid-cols-[1.4fr_2fr]">
        {fact && <TableCard t={fact} className="bg-card" />}
        <div className="grid gap-px bg-line sm:grid-cols-2">{dims.map((t) => <TableCard key={t.name} t={t} className="bg-paper" />)}</div>
      </div>
      <p className="mt-2 text-xs text-mute">Generated from the SQLAlchemy models. Arrows show foreign keys from the fact table into each dimension.</p>
    </div>
  );
}

function TableCard({ t, className }: { t: StarTable; className?: string }) {
  return (
    <details open={t.role === "fact"} className={cn("group p-4", className)}>
      <summary className="flex cursor-pointer list-none items-center justify-between gap-2">
        <span className="font-mono text-sm font-semibold">{t.name}</span>
        <Badge tone={t.role === "fact" ? "lime" : "neutral"}>{t.role}</Badge>
      </summary>
      <ul className="mt-3 space-y-1 font-mono text-[11px]">
        {t.columns.map((c) => (
          <li key={c.name} className="flex items-baseline justify-between gap-3">
            <span className={cn(c.pk && "font-semibold")}>{c.name}{c.pk && " 🔑"}</span>
            <span className="text-mute">{c.references ? `→ ${c.references}` : c.type.toLowerCase()}</span>
          </li>
        ))}
      </ul>
    </details>
  );
}

// ------------------------------------------------------------------ OLAP
function OlapExplorer({ examples, note }: { examples: OlapExample[]; note: string }) {
  const [key, setKey] = useState(examples[0]?.key ?? "");
  const ex = examples.find((e) => e.key === key) ?? examples[0];
  if (!ex) return null;
  return (
    <div className="mt-10">
      <p className="eyebrow mb-3">Operations, run live on your data</p>
      <div className="grid gap-6 lg:grid-cols-[14rem_1fr]">
        <div role="tablist" aria-label="OLAP operations" aria-orientation="vertical" className="flex gap-2 overflow-x-auto lg:flex-col lg:gap-0 lg:border-l lg:border-line">
          {examples.map((e) => (
            <button
              key={e.key}
              role="tab"
              type="button"
              id={`olap-tab-${e.key}`}
              aria-selected={e.key === ex.key}
              aria-controls="olap-panel"
              onClick={() => setKey(e.key)}
              className={cn("shrink-0 whitespace-nowrap border px-3 py-2 text-left text-sm transition-colors lg:border-0 lg:border-l-2 lg:-ml-px", e.key === ex.key ? "border-ink font-medium text-ink lg:border-l-ink" : "border-line text-mute hover:text-ink lg:border-l-transparent")}
            >
              {e.name}
            </button>
          ))}
        </div>
        <div id="olap-panel" role="tabpanel" aria-labelledby={`olap-tab-${ex.key}`} className="min-w-0 space-y-5">
          <p className="text-sm text-ink-2">{ex.meaning}</p>
          <div>
            <p className="eyebrow mb-2">Equivalent SQL on the star schema</p>
            <CodeBlock code={ex.sql} label={`${ex.name} SQL`} />
          </div>
          <div>
            <p className="eyebrow mb-2">Request sent to the engine</p>
            <CodeBlock code={JSON.stringify(ex.query, null, 2)} label={`${ex.name} request`} />
          </div>
          <div>
            <p className="eyebrow mb-2">Result</p>
            <OlapPreview ex={ex} />
          </div>
        </div>
      </div>
      <p className="mt-6 max-w-3xl text-xs text-mute">{note}</p>
    </div>
  );
}

function OlapPreview({ ex }: { ex: OlapExample }) {
  const p = ex.preview;
  if (!p) return <EmptyState title="No result">There is no data in scope for this operation yet.</EmptyState>;
  if (p.kind === "pivot") {
    const isRate = p.measure.endsWith("rate");
    return (
      <div className="overflow-x-auto">
        <table className="w-full min-w-[28rem] text-sm">
          <thead><tr className="eyebrow border-b border-ink text-left"><th className="py-2 font-normal capitalize">{p.row_dimensions.join(" · ")}</th>{p.column_labels.map((c) => <th key={String(c)} className="text-right font-normal">{c}</th>)}</tr></thead>
          <tbody>{p.rows.map((r, i) => <tr key={i} className="border-b border-line"><td className="py-2">{Object.values(r.keys).join(" · ")}</td>{r.cells.map((v, j) => <td key={j} className="num text-right">{v === null ? "—" : isRate ? pct(v, 2) : int(v)}</td>)}</tr>)}</tbody>
        </table>
        <p className="mt-2 text-xs text-mute">Cell value: {p.measure.replace(/_/g, " ")}.</p>
      </div>
    );
  }
  const fmt = (m: string, v: unknown) => (typeof v !== "number" ? "—" : m.endsWith("rate") ? pct(v, 2) : int(v));
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[28rem] text-sm">
        <thead><tr className="eyebrow border-b border-ink text-left">{p.dimensions.map((d) => <th key={d} className="py-2 font-normal capitalize">{d}</th>)}{p.measures.map((m) => <th key={m} className="text-right font-normal">{m.replace(/_/g, " ")}</th>)}</tr></thead>
        <tbody>
          {p.rows.map((r, i) => {
            const sub = r.level < p.dimensions.length;
            return (
              <tr key={i} className={cn("border-b border-line", sub && "bg-paper-2 font-semibold")}>
                {p.dimensions.map((d, di) => <td key={d} className="py-2">{r.keys[d] ?? (sub && di === r.level ? "subtotal" : "")}</td>)}
                {p.measures.map((m) => <td key={m} className="num text-right">{fmt(m, r[m])}</td>)}
              </tr>
            );
          })}
        </tbody>
      </table>
      <p className="mt-2 text-xs text-mute">{int(p.n_posts)} posts in scope; first {p.rows.length} rows shown.</p>
    </div>
  );
}

// ------------------------------------------------------------------ algorithms
function ModelList({ models }: { models: MethodEntry[] }) {
  const [group, setGroup] = useState<(typeof MODEL_GROUPS)[number]>("All");
  const shown = models.filter((m) => group === "All" || m.group === group);
  return (
    <>
      <div role="group" aria-label="Filter algorithms by family" className="mb-6 flex flex-wrap gap-2">
        {MODEL_GROUPS.map((g) => {
          const n = g === "All" ? models.length : models.filter((m) => m.group === g).length;
          return (
            <button key={g} type="button" aria-pressed={group === g} disabled={n === 0} onClick={() => setGroup(g)}
              className={cn("border px-3 py-1 text-xs transition-colors disabled:opacity-40", group === g ? "border-ink bg-ink text-paper" : "border-line hover:border-ink")}>
              {g} <span className="num opacity-70">{n}</span>
            </button>
          );
        })}
      </div>
      {shown.length === 0 ? <EmptyState title="No algorithms in this family" /> : <div className="space-y-6">{shown.map((a) => <AlgorithmCard key={a.key} a={a} />)}</div>}
    </>
  );
}

function AlgorithmCard({ a }: { a: MethodEntry }) {
  return (
    <article id={a.key} aria-labelledby={`${a.key}-title`} className="scroll-mt-24 border border-line bg-card">
      <header className="flex flex-wrap items-start justify-between gap-3 border-b border-line p-5">
        <div className="max-w-2xl">
          <div className="mb-2 flex flex-wrap items-center gap-2"><Badge tone="neutral">{a.group}</Badge>{a.run && <RunBadge run={a.run} />}</div>
          <h3 id={`${a.key}-title`} className="display text-2xl">{a.name}</h3>
          <p className="mt-2 text-sm leading-relaxed text-ink-2">{a.summary}</p>
        </div>
        {a.used_in.length > 0 && (
          <ul className="flex flex-wrap gap-2 text-xs" aria-label={`Where ${a.name} is used`}>
            {a.used_in.map((u) => <li key={u.href}><Link href={u.href} className="inline-flex items-center gap-1 border border-line px-2 py-1 hover:border-ink">{u.label}<ArrowUpRight className="size-3" aria-hidden /></Link></li>)}
          </ul>
        )}
      </header>

      <div className="grid gap-8 p-5 lg:grid-cols-[1.3fr_1fr]">
        <div>
          <p className="eyebrow mb-2">How it works</p>
          <ol className="space-y-2 text-sm">
            {a.steps.map((s, i) => <li key={i} className="flex gap-3"><span className="num mt-0.5 w-5 shrink-0 text-mute">{i + 1}</span><span className="leading-relaxed">{s}</span></li>)}
          </ol>
          <p className="eyebrow mb-1 mt-6">Why this method</p>
          <p className="text-sm leading-relaxed text-ink-2">{a.why}</p>
        </div>
        <div className="space-y-6">
          {(a.target || a.features) && (
            <dl className="space-y-3 text-sm">
              {a.target && <div><dt className="eyebrow">Target</dt><dd className="mt-1">{a.target}</dd></div>}
              {a.features && <div><dt className="eyebrow">Inputs</dt><dd className="mt-1 break-words font-mono text-[11px] leading-relaxed text-ink-2">{a.features}</dd></div>}
            </dl>
          )}
          <div>
            <p className="eyebrow mb-2">Guardrails</p>
            <ul className="list-disc space-y-1 pl-4 text-sm text-ink-2">{a.guardrails.map((g, i) => <li key={i}>{g}</li>)}</ul>
          </div>
        </div>
      </div>

      {a.run && <RunMetrics run={a.run} />}

      <details className="border-t border-line">
        <summary className="cursor-pointer select-none px-5 py-3 text-sm font-medium hover:bg-paper-2">
          View source <span className="font-normal text-mute">· {a.source.map((s) => s.function).join(", ")}</span>
        </summary>
        <div className="space-y-5 px-5 pb-5">
          {a.source.map((s) => (
            <div key={s.function}>
              <p className="mb-1 font-mono text-[11px] text-mute">{s.file}:{s.line}</p>
              <CodeBlock code={s.code} label={`Source of ${s.function}`} />
            </div>
          ))}
        </div>
      </details>
    </article>
  );
}

function RunBadge({ run }: { run: MethodRun }) {
  if (run.status === "ok") return <Badge tone="lime">trained · {dateShort(run.trained_at)}</Badge>;
  return <Badge tone="alert">{run.status.replace(/_/g, " ")}</Badge>;
}

function metricValue(v: MethodRun["metrics"][string]): string {
  if (v === null || v === undefined) return "—";
  if (typeof v === "number") return Number.isInteger(v) ? int(v) : fixed(v, 3);
  if (typeof v === "string") return v;
  return Object.entries(v).map(([k, x]) => `${k}: ${fixed(x, 2)}`).join(" · ");
}

function RunMetrics({ run }: { run: MethodRun }) {
  if (run.status !== "ok") {
    return <div className="border-t border-line p-5"><InsufficientState title="No metrics stored for this run">{run.message ?? "The model has not produced a usable result on the current data."}</InsufficientState></div>;
  }
  const rows = Object.entries(run.metrics);
  return (
    <div className="border-t border-line p-5">
      <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
        <p className="eyebrow">Latest stored run</p>
        <p className="num text-xs text-mute">
          {run.n_test ? `${int(run.n_train)} train / ${int(run.n_test)} test (chronological)` : `${int(run.n_train)} posts`} · data {run.dataset_hash}
        </p>
      </div>
      <dl className="grid gap-x-8 gap-y-3 sm:grid-cols-2 lg:grid-cols-4">
        {rows.map(([k, v]) => (
          <div key={k} className="border-t border-line pt-2">
            <dt className="text-[11px] text-mute">{k.replace(/_/g, " ")}</dt>
            <dd className="num mt-0.5 break-words text-base">{metricValue(v)}</dd>
          </div>
        ))}
      </dl>
      {Object.keys(run.params).length > 0 && (
        <p className="mt-4 break-words font-mono text-[11px] text-mute">params: {JSON.stringify(run.params)}</p>
      )}
    </div>
  );
}
