"use client";

import { FlaskConical } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useState } from "react";
import { DivergingBars, RangeBar } from "@/components/charts";
import { PageHeader, Section, Stat, Tag } from "@/components/editorial";
import { InterpretationPanel } from "@/components/interpretation";
import { NeighborList } from "@/components/post-bits";
import { Async, ErrorState, InsufficientState, LoadingBlock } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Dialog, DialogClose, DialogContent } from "@/components/ui/dialog";
import { Field, Select, Textarea } from "@/components/ui/select";
import { Input } from "@/components/ui/select";
import { api } from "@/lib/api";
import { fixed, pct, signedPct } from "@/lib/format";
import type { Autopsy, DraftInput, ExperimentDetail, PredictionResult, Vocabulary, WhatIf } from "@/lib/types";
import { useAction, useApi } from "@/lib/use-api";

const DAYPART_HOUR: Record<string, number> = { Morning: 8, Midday: 12, Afternoon: 16, Evening: 19 };
const STARTER = "5 things we learned about A/B testing basics. Change one variable at a time or you learn nothing. Save this for your next planning session. #learning";

function defaultSchedule(): string {
  const d = new Date();
  d.setDate(d.getDate() + 1);
  while (d.getDay() === 0 || d.getDay() === 6) d.setDate(d.getDate() + 1);
  d.setHours(9, 0, 0, 0);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

export default function LabPage() {
  return (
    <Suspense fallback={<LoadingBlock rows={6} label="Loading lab" />}>
      <Lab />
    </Suspense>
  );
}

function initialDraft(vocab: Vocabulary, prefill: string | null, source: Autopsy["post"] | null): DraftInput {
  const platforms = Object.keys(vocab.platforms);
  const platform = platforms.includes("LinkedIn") ? "LinkedIn" : platforms[0];
  const fmts = vocab.platforms[platform].formats;
  let d: DraftInput = {
    platform, format: fmts.find((f) => f.name === "Carousel")?.name ?? fmts[0].name,
    topic: vocab.topics.includes("Education") ? "Education" : vocab.topics[0],
    hook: vocab.hooks.includes("Numbered list") ? "Numbered list" : vocab.hooks[0],
    tone: vocab.tones.includes("Authoritative") ? "Authoritative" : vocab.tones[0], caption: STARTER, scheduled_at: defaultSchedule(),
  };
  if (source) d = { ...d, platform: source.platform, format: source.format, topic: source.topic, hook: source.hook, tone: source.tone, caption: source.caption };
  if (prefill) {
    for (const item of prefill.split("|")) {
      const [k, v] = item.split("=");
      if (!v) continue;
      if (k === "platform" && vocab.platforms[v]) d = { ...d, platform: v, format: vocab.platforms[v].formats[0].name };
      if (k === "format") d = { ...d, format: v };
      if (k === "topic") d = { ...d, topic: v };
      if (k === "hook") d = { ...d, hook: v };
      if (k === "tone") d = { ...d, tone: v };
      if (k === "daypart" && DAYPART_HOUR[v]) d = { ...d, scheduled_at: d.scheduled_at.replace(/T\d\d/, `T${String(DAYPART_HOUR[v]).padStart(2, "0")}`) };
    }
    if (!vocab.platforms[d.platform].formats.some((f) => f.name === d.format)) d = { ...d, format: vocab.platforms[d.platform].formats[0].name };
  }
  return d;
}

function Lab() {
  const vocab = useApi<Vocabulary>("/vocabulary");
  const sp = useSearchParams();
  const from = sp.get("from");
  const fromId = from && /^\d+$/.test(from) ? from : null;
  const source = useApi<Autopsy>(fromId ? `/posts/${fromId}/autopsy` : null);
  return (
    <>
      <PageHeader eyebrow="03 · Decide" title={<>Before it <em className="italic">ships</em>.</>} lede="Describe a draft. SIGNAL scores it using only what is known before publishing (never likes, reach or any post-publication metric), shows what drives the estimate, and turns any promising change into an experiment." />
      <Async state={vocab}>
        {(v) =>
          Object.keys(v.platforms).length === 0 ? (
            <InsufficientState title="No history to learn from">Import posts first. The Lab needs past performance to estimate a draft.</InsufficientState>
          ) : fromId && source.loading ? (
            <LoadingBlock rows={6} label="Loading source post" />
          ) : (
            <LabBody key={`${fromId}-${sp.get("prefill")}`} vocab={v} initial={initialDraft(v, sp.get("prefill"), source.data?.post ?? null)} />
          )
        }
      </Async>
    </>
  );
}

function LabBody({ vocab, initial }: { vocab: Vocabulary; initial: DraftInput }) {
  const platforms = Object.keys(vocab.platforms);
  const [draft, setDraft] = useState<DraftInput>(initial);
  const patch = (p: Partial<DraftInput>) => setDraft((d) => ({ ...d, ...p }));

  const formats = vocab.platforms[draft.platform]?.formats ?? [];
  const valid = draft.caption.trim().length > 0 && draft.scheduled_at.length >= 16;

  // Debounced prediction
  const [debounced, setDebounced] = useState(draft);
  useEffect(() => {
    const t = setTimeout(() => setDebounced(draft), 550);
    return () => clearTimeout(t);
  }, [draft]);
  const body = useMemo(() => ({ ...debounced, scheduled_at: debounced.scheduled_at.length === 16 ? `${debounced.scheduled_at}:00` : debounced.scheduled_at }), [debounced]);
  const [result, setResult] = useState<PredictionResult | null>(null);
  const predict = useAction((b: typeof body) => api.post<PredictionResult>("/lab/predict", b));
  useEffect(() => {
    if (!debounced.caption.trim() || debounced.scheduled_at.length < 16) return;
    let live = true;
    predict.run(body).then((r) => { if (live && r) setResult(r); });
    return () => { live = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [body]);

  const pr = result?.prediction;
  const chars = draft.caption.trim().length;

  return (
    <div className="grid gap-12 lg:grid-cols-[minmax(0,26rem)_minmax(0,1fr)]">
      <form className="space-y-5 self-start lg:sticky lg:top-24" onSubmit={(e) => e.preventDefault()} aria-label="Draft post">
        <div className="grid grid-cols-2 gap-4">
          <Field label="Platform" htmlFor="lab-platform"><Select id="lab-platform" value={draft.platform} onChange={(e) => patch({ platform: e.target.value, format: vocab.platforms[e.target.value].formats[0].name })}>{platforms.map((p) => <option key={p}>{p}</option>)}</Select></Field>
          <Field label="Format" htmlFor="lab-format"><Select id="lab-format" value={draft.format} onChange={(e) => patch({ format: e.target.value })}>{formats.map((f) => <option key={f.name} value={f.name}>{f.name} ({f.n})</option>)}</Select></Field>
          <Field label="Topic" htmlFor="lab-topic"><Select id="lab-topic" value={draft.topic} onChange={(e) => patch({ topic: e.target.value })}>{vocab.topics.map((t) => <option key={t}>{t}</option>)}</Select></Field>
          <Field label="Hook" htmlFor="lab-hook"><Select id="lab-hook" value={draft.hook} onChange={(e) => patch({ hook: e.target.value })}>{vocab.hooks.map((t) => <option key={t}>{t}</option>)}</Select></Field>
          <Field label="Tone" htmlFor="lab-tone"><Select id="lab-tone" value={draft.tone} onChange={(e) => patch({ tone: e.target.value })}>{vocab.tones.map((t) => <option key={t}>{t}</option>)}</Select></Field>
          <Field label="Scheduled for" htmlFor="lab-when"><Input id="lab-when" type="datetime-local" value={draft.scheduled_at} onChange={(e) => patch({ scheduled_at: e.target.value })} /></Field>
        </div>
        <Field label="Caption" htmlFor="lab-caption" hint={`${chars} characters. Hashtags, emoji, questions and calls to action are read from the text.`}>
          <Textarea id="lab-caption" rows={8} maxLength={5000} value={draft.caption} onChange={(e) => patch({ caption: e.target.value })} aria-invalid={!valid} />
        </Field>
        {!valid && <p role="alert" className="text-sm text-alert">Add a caption and a schedule to get an estimate.</p>}
        <p className="border-l-2 border-lime pl-3 text-xs text-mute">Leakage guard: the estimate uses platform, format, topic, hook, tone, time of day, weekend, caption length, hashtags, emoji, media count, question and CTA. Nothing measured after publishing.</p>
      </form>

      <div aria-live="polite" className="min-w-0">
        {predict.error && <ErrorState error={predict.error} onRetry={() => predict.run(body).then((r) => r && setResult(r))} className="mb-6" />}
        {!result && !predict.error && <LoadingBlock rows={6} label="Scoring draft" />}
        {result && result.status === "insufficient_data" && <InsufficientState title="Models aren't ready">{result.message}</InsufficientState>}
        {pr && result && (
          <div className={predict.pending ? "opacity-60 transition-opacity" : "transition-opacity"}>
            <div className="grid gap-8 sm:grid-cols-[1.2fr_1fr]">
              <div>
                <p className="eyebrow">Estimated engagement rate</p>
                <p className="display num mt-2 text-7xl" style={{ fontFamily: "var(--font-serif)" }}>{pct(pr.engagement_rate, 2)}</p>
                <p className="mt-1 text-sm text-mute"><span className={pr.vs_platform_median_pct >= 0 ? "font-semibold text-ink" : "text-alert"}>{signedPct(pr.vs_platform_median_pct, 0)}</span> vs {draft.platform} median</p>
                <div className="mt-5"><RangeBar value={pr.engagement_rate} low={pr.interval_80[0]} high={pr.interval_80[1]} marker={pr.platform_median_engagement_rate} markerLabel="median" /></div>
                <p className="mt-1 text-xs text-mute">Green band = 80% range, calibrated on the model&apos;s errors for later, unseen posts.</p>
              </div>
              <div className="space-y-5">
                <Stat label="Chance of a top-quartile post" value={pct(pr.probability_top_quartile.blend, 0)} sub={`baseline ${pct(pr.probability_top_quartile.base_rate, 0)} · tree ${pct(pr.probability_top_quartile.decision_tree, 0)} · naive Bayes ${pct(pr.probability_top_quartile.gaussian_nb, 0)}`} />
                {result.model && <Stat label="Model reliability" value={<>R² {fixed(result.model.holdout_r2)}</>} sub={`within-platform R² ${fixed(result.model.r2_platform_adjusted)} · ${result.model.n_train} train / ${result.model.n_test} later posts tested`} />}
              </div>
            </div>

            <Section title="What's driving the estimate" kicker="Within-platform contributions" className="mt-10">
              <DivergingBars items={pr.contributions.map((c) => ({ label: c.label, value: c.effect_pct, detail: c.value }))} />
              <p className="mt-3 text-xs text-mute">Each bar is the model&apos;s statistical association for this draft versus an average post on any platform, holding other inputs fixed. Associations are not causes.</p>
            </Section>

            <Section title="Changes worth testing" kicker="Model-estimated, history-supported" className="mt-10">
              {result.what_if && result.what_if.length > 0 ? (
                <ul className="divide-y divide-line border-y border-line">
                  {result.what_if.map((w) => (
                    <li key={w.change} className="flex flex-wrap items-center justify-between gap-3 py-3">
                      <div><p className="font-medium">{w.change}</p><p className="num text-xs text-mute">{w.label} · est. {signedPct(w.estimated_change_pct)} · {w.supporting_posts} past posts use this option</p></div>
                      {["hook", "format", "tone", "daypart"].includes(w.feature) ? <TestDialog draft={draft} whatIf={w} /> : <Tag tone="mute">edit caption to try</Tag>}
                    </li>
                  ))}
                </ul>
              ) : <InsufficientState title="No change clears the bar">No single swap is estimated to help by ≥ 3% with enough supporting history.</InsufficientState>}
            </Section>

            {result.similar && (
              <Section title="Most similar past posts" kicker="Similarity search" className="mt-10" aside={result.similar.summary ? `median ${pct(result.similar.summary.median_engagement_rate, 2)}` : undefined}>
                {result.similar.status === "ok" ? <NeighborList neighbors={result.similar.neighbors} /> : <InsufficientState>{result.similar.message}</InsufficientState>}
              </Section>
            )}

            <Section title="Caveats" kicker="Read before acting" className="mt-10">
              <ul className="list-disc space-y-1 pl-5 text-sm text-ink-2">{result.caveats?.map((c) => <li key={c}>{c}</li>)}</ul>
            </Section>

            <Section title="Read-out" kicker="AI interpretation" className="mt-10">
              <InterpretationPanel request={{ scope: "prediction", draft: body }} title="What the evidence supports" disabled={predict.pending} />
            </Section>
          </div>
        )}
      </div>
    </div>
  );
}

function TestDialog({ draft, whatIf }: { draft: DraftInput; whatIf: WhatIf }) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [randomized, setRandomized] = useState(false);
  const current = whatIf.change.split(" → ")[0];
  const create = useAction(async () => {
    const alt: DraftInput = { ...draft };
    if (whatIf.feature === "hook") alt.hook = whatIf.value;
    if (whatIf.feature === "format") alt.format = whatIf.value;
    if (whatIf.feature === "tone") alt.tone = whatIf.value;
    if (whatIf.feature === "daypart") alt.scheduled_at = draft.scheduled_at.replace(/T\d\d/, `T${String(DAYPART_HOUR[whatIf.value]).padStart(2, "0")}`);
    const norm = (d: DraftInput) => ({ ...d, scheduled_at: d.scheduled_at.length === 16 ? `${d.scheduled_at}:00` : d.scheduled_at });
    const [a, b] = await Promise.all([api.post<PredictionResult>("/lab/predict", norm(draft)), api.post<PredictionResult>("/lab/predict", norm(alt))]);
    const exp = await api.post<ExperimentDetail>("/experiments", {
      name: `${draft.platform}: ${current} vs ${whatIf.value}`,
      hypothesis: `${whatIf.value} will earn a higher engagement rate than ${current} on ${draft.platform}, other things equal.`,
      variable: whatIf.feature, platform: draft.platform, min_per_variant: 6, randomized, source: "prepublish_lab",
      variants: [{ label: "A", description: `${current} (control)`, is_control: true }, { label: "B", description: whatIf.value, is_control: false }],
      prediction_snapshot: { predicted_engagement_rate: { A: a.prediction?.engagement_rate, B: b.prediction?.engagement_rate }, model_run_id: a.model?.run_id },
    });
    router.push(`/experiments/${exp.id}`);
  });
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <Button size="sm" variant="outline" onClick={() => setOpen(true)}><FlaskConical className="size-3.5" />Test it</Button>
      <DialogContent title="Turn this into an experiment" description="Posts will be assigned to variant A (control) or B. Log each post's results as they come in; SIGNAL decides only when there is enough data.">
        <div className="space-y-4 text-sm">
          <p><strong>{whatIf.label}:</strong> {whatIf.change}</p>
          <p className="text-mute">The model&apos;s current predictions for both variants are stored with the experiment, so the result can be checked against them.</p>
          <label className="flex items-start gap-2"><input type="checkbox" className="mt-1" checked={randomized} onChange={(e) => setRandomized(e.target.checked)} /><span>I will randomise which posts get which variant. <span className="text-mute">(Only then can a difference be read as caused by the change.)</span></span></label>
          {create.error && <p role="alert" className="text-alert">{create.error.message}</p>}
          <div className="flex justify-end gap-2"><DialogClose asChild><Button variant="ghost">Cancel</Button></DialogClose><Button variant="accent" loading={create.pending} onClick={() => create.run()}>Create experiment</Button></div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
