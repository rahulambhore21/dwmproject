"use client";

import { ArrowLeft, CheckCircle2 } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import { IntervalPlot } from "@/components/charts";
import { PageHeader, Section, Stat, Tag } from "@/components/editorial";
import { InterpretationPanel } from "@/components/interpretation";
import { Async, ErrorState, InsufficientState, LoadingBlock } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Field, Input, Select } from "@/components/ui/select";
import { api } from "@/lib/api";
import { VERDICT_LABELS, dateShort, fixed, int, p as fmtP, pct, signedNum } from "@/lib/format";
import type { ExperimentDetail } from "@/lib/types";
import { useAction, useApi } from "@/lib/use-api";
import { cn } from "@/lib/utils";

export default function ExperimentPage() {
  const { id } = useParams<{ id: string }>();
  const valid = /^\d+$/.test(id ?? "");
  const state = useApi<ExperimentDetail>(valid ? `/experiments/${id}` : null);
  if (!valid) return <InsufficientState title="That isn't an experiment id"><Link className="underline" href="/experiments">Back to experiments</Link></InsufficientState>;
  return (
    <>
      <Link href="/experiments" className="mb-6 inline-flex items-center gap-1 text-sm text-mute hover:text-ink"><ArrowLeft className="size-4" />Experiments</Link>
      <Async state={state} skeleton={<LoadingBlock rows={8} label="Loading experiment" />}>{(e) => <Body e={e} reload={state.reload} />}</Async>
    </>
  );
}

function Body({ e, reload }: { e: ExperimentDetail; reload: () => void }) {
  const a = e.analysis;
  const running = e.status === "running";
  const ready = a.verdict !== "insufficient_data";
  const complete = useAction(async () => { await api.post(`/experiments/${e.id}/complete`); reload(); });
  const pointsBy = (label: string) => e.observations.filter((o) => o.variant_label === label).map((o) => o.engagement_rate);
  const cmp = a.comparisons.find((c) => c.testable);
  const verdictTone = a.verdict === "adopt" ? "lime" : a.verdict === "insufficient_data" ? "mute" : "neutral";

  return (
    <>
      <PageHeader
        eyebrow={`04 · Experiment #${e.id}`}
        title={e.name}
        lede={<><span className="block">{e.hypothesis}</span><span className="mt-3 flex flex-wrap items-center gap-2"><Tag tone={running ? "lime" : "ink"}>{e.status}</Tag><Tag>{e.platform}</Tag><Tag tone="mute">varies: {e.variable}</Tag><Tag tone={e.randomized ? "neutral" : "alert"}>{e.randomized ? "randomised" : "not randomised"}</Tag>{e.source === "prepublish_lab" && <Tag tone="mute">from Lab</Tag>}</span></>}
        actions={running ? <Button variant="accent" disabled={!ready} loading={complete.pending} onClick={() => complete.run()} title={ready ? undefined : "Every variant needs enough posts first"}><CheckCircle2 className="size-4" />Conclude & record learning</Button> : undefined}
      />
      {complete.error && <ErrorState error={complete.error} className="mb-6" />}

      <div className="grid gap-8 sm:grid-cols-3">
        <div className="sm:col-span-2">
          <p className="eyebrow mb-3">Variant means · each dot is one post</p>
          {e.observations.length === 0 ? <InsufficientState title="No posts logged yet">Log each post&apos;s impressions and engagements below as results arrive.</InsufficientState> : (
            <IntervalPlot rows={a.variant_summaries.filter((v) => v.mean_engagement_rate !== null).map((v) => ({ label: `${v.label}${v.is_control ? " · control" : ""}`, mean: v.mean_engagement_rate as number, n: v.n, points: pointsBy(v.label), emphasis: !v.is_control }))} min={0} />
          )}
          <ul className="mt-4 space-y-1 text-sm text-ink-2">{e.variants.map((v) => <li key={v.id}><span className="num font-semibold">{v.label}</span> {v.description} <span className="text-mute">· {v.n}/{e.min_per_variant} posts</span></li>)}</ul>
        </div>
        <div className="space-y-6">
          <Stat label="Verdict" value={<span className="text-2xl">{VERDICT_LABELS[a.verdict]}</span>} sub={<Tag tone={verdictTone}>{a.winner ? `winner: ${a.winner}` : a.verdict === "insufficient_data" ? "keep posting" : "no winner"}</Tag>} />
          {a.message && <p className="text-sm text-mute">{a.message}</p>}
        </div>
      </div>

      {cmp && (
        <Section title="The comparison" kicker={`${cmp.variant} vs ${cmp.control} on engagement rate`}>
          <div className="grid gap-8 md:grid-cols-[1.3fr_1fr]">
            <div>
              <DiffPlot lo={cmp.ci95_diff_pp![0]} hi={cmp.ci95_diff_pp![1]} diff={cmp.diff_pp!} />
              <p className="mt-2 text-xs text-mute">Difference in engagement rate (percentage points), with a 95% bootstrap interval. If the interval spans zero, the data are compatible with no effect.</p>
            </div>
            <dl className="num grid grid-cols-2 gap-x-6 gap-y-3 text-sm">
              <Row k="Difference" v={`${signedNum(cmp.diff_pp)} pp`} /><Row k="Relative lift" v={cmp.relative_lift_pct != null ? `${signedNum(cmp.relative_lift_pct, 1)}%` : "—"} />
              <Row k="Welch p (adjusted)" v={fmtP(cmp.welch_p_adjusted)} /><Row k="Mann–Whitney p" v={fmtP(cmp.mann_whitney_p)} />
              <Row k="Effect size (d)" v={fixed(cmp.cohens_d)} /><Row k="Smallest detectable" v={`${fixed(cmp.min_detectable_diff_pp)} pp`} />
              <Row k="Posts" v={`${cmp.n_variant} vs ${cmp.n_control}`} /><Row k="Means" v={`${pct(cmp.mean_variant, 2)} vs ${pct(cmp.mean_control, 2)}`} />
            </dl>
          </div>
          <p className="mt-5 border-l-2 border-ink pl-3 text-sm">{a.causal_note}</p>
          {!cmp.significant && a.verdict !== "insufficient_data" && <p className="mt-3 text-sm text-mute">Not significant: with this many posts, differences smaller than about {fixed(cmp.min_detectable_diff_pp)} pp can&apos;t be told apart from noise. More posts would narrow that.</p>}
        </Section>
      )}

      {a.prediction_check && (
        <Section title="Did the model call it?" kicker="Prediction made before the test">
          <div className="overflow-x-auto"><table className="w-full max-w-lg text-sm"><thead><tr className="eyebrow border-b border-ink text-left"><th className="py-2 font-normal">Variant</th><th className="text-right font-normal">Predicted</th><th className="text-right font-normal">Observed</th></tr></thead><tbody>{a.prediction_check.rows.map((r) => <tr key={r.label} className="border-b border-line"><td className="py-2">{r.label}</td><td className="num text-right">{pct(r.predicted, 2)}</td><td className="num text-right">{pct(r.observed, 2)}</td></tr>)}</tbody></table></div>
          <p className="mt-3 text-sm">The model favoured <strong>{a.prediction_check.predicted_best}</strong>; the data favour <strong>{a.prediction_check.observed_best}</strong>: {a.prediction_check.direction_matched ? "same direction" : "opposite direction"}. <span className="text-mute">{a.prediction_check.note}</span></p>
        </Section>
      )}

      {running && <LogForm e={e} onSaved={reload} />}

      <Section title="Logged posts" kicker={`${e.observations.length} observations`}>
        {e.observations.length === 0 ? <p className="text-sm text-mute">None yet.</p> : (
          <div className="overflow-x-auto"><table className="w-full min-w-[30rem] text-sm"><thead><tr className="eyebrow border-b border-ink text-left"><th className="py-2 font-normal">Variant</th><th className="font-normal">Published</th><th className="text-right font-normal">Impressions</th><th className="text-right font-normal">Engagements</th><th className="text-right font-normal">Rate</th></tr></thead>
            <tbody>{e.observations.map((o) => <tr key={o.id} className="border-b border-line"><td className="num py-2 font-semibold">{o.variant_label}</td><td>{dateShort(o.published_at)}</td><td className="num text-right">{int(o.impressions)}</td><td className="num text-right">{int(o.engagements)}</td><td className="num text-right">{pct(o.engagement_rate, 2)}</td></tr>)}</tbody></table></div>
        )}
      </Section>

      <Section title="Read-out" kicker="AI interpretation"><InterpretationPanel request={{ scope: "experiment", experiment_id: e.id }} title="What this experiment supports" /></Section>
    </>
  );
}

function Row({ k, v }: { k: string; v: string }) {
  return <div><dt className="eyebrow">{k}</dt><dd className="mt-0.5">{v}</dd></div>;
}

function DiffPlot({ lo, hi, diff }: { lo: number; hi: number; diff: number }) {
  const span = Math.max(Math.abs(lo), Math.abs(hi), Math.abs(diff)) * 1.25 || 1;
  const x = (v: number) => `${50 + (v / span) * 50}%`;
  const spans = lo <= 0 && hi >= 0;
  return (
    <div>
      <div className="relative h-12" role="img" aria-label={`Difference ${diff.toFixed(2)} percentage points, 95% interval ${lo.toFixed(2)} to ${hi.toFixed(2)}`}>
        <div className="absolute inset-x-0 top-1/2 h-px bg-line" />
        <div className="absolute inset-y-0 left-1/2 w-px bg-ink" />
        <div className={cn("absolute top-1/2 h-2 -translate-y-1/2", spans ? "bg-mute/50" : "bg-lime outline outline-1 outline-ink")} style={{ left: x(lo), width: `calc(${x(hi)} - ${x(lo)})` }} />
        <div className="absolute top-1/2 size-3.5 -translate-x-1/2 -translate-y-1/2 border-2 border-ink bg-paper" style={{ left: x(diff) }} />
      </div>
      <div className="num flex justify-between text-[11px] text-mute"><span>{(-span).toFixed(1)} pp</span><span>0</span><span>+{span.toFixed(1)} pp</span></div>
    </div>
  );
}

function LogForm({ e, onSaved }: { e: ExperimentDetail; onSaved: () => void }) {
  const today = new Date().toISOString().slice(0, 10);
  const [f, setF] = useState({ variant_id: e.variants[0].id, date: today, impressions: "", engagements: "", saves: "" });
  const save = useAction(async () => {
    await api.post(`/experiments/${e.id}/observations`, {
      variant_id: f.variant_id, published_at: `${f.date}T12:00:00`, impressions: Number(f.impressions), engagements: Number(f.engagements), saves: Number(f.saves || 0),
    });
    setF({ ...f, impressions: "", engagements: "", saves: "" });
    onSaved();
  });
  const imp = Number(f.impressions), eng = Number(f.engagements);
  const clientError = f.impressions && f.engagements && eng > imp ? "Engagements can't exceed impressions." : null;
  const ok = imp >= 1 && f.engagements !== "" && eng >= 0 && !clientError;
  return (
    <Section title="Log a post" kicker="Record results as they arrive">
      <form className="grid gap-4 sm:grid-cols-5" onSubmit={(ev) => { ev.preventDefault(); if (ok) save.run(); }}>
        <Field label="Variant" htmlFor="o-var"><Select id="o-var" value={f.variant_id} onChange={(ev) => setF({ ...f, variant_id: Number(ev.target.value) })}>{e.variants.map((v) => <option key={v.id} value={v.id}>{v.label} · {v.description}</option>)}</Select></Field>
        <Field label="Published" htmlFor="o-date"><Input id="o-date" type="date" max={today} value={f.date} onChange={(ev) => setF({ ...f, date: ev.target.value })} /></Field>
        <Field label="Impressions" htmlFor="o-imp"><Input id="o-imp" type="number" min={1} inputMode="numeric" value={f.impressions} onChange={(ev) => setF({ ...f, impressions: ev.target.value })} /></Field>
        <Field label="Engagements" htmlFor="o-eng"><Input id="o-eng" type="number" min={0} inputMode="numeric" value={f.engagements} onChange={(ev) => setF({ ...f, engagements: ev.target.value })} /></Field>
        <div className="flex items-end"><Button type="submit" variant="primary" className="w-full" disabled={!ok} loading={save.pending}>Add</Button></div>
      </form>
      {(clientError || save.error) && <p role="alert" className="mt-3 text-sm text-alert">{clientError ?? save.error?.message}</p>}
      <p className="mt-3 text-xs text-mute">Engagements = likes + comments + shares + saves.</p>
    </Section>
  );
}
