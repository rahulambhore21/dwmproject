"use client";

import { ArrowLeft, ArrowRight } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { DivergingBars } from "@/components/charts";
import { PageHeader, PlatformDot, Section, Stat, Tag } from "@/components/editorial";
import { InterpretationPanel } from "@/components/interpretation";
import { NeighborList } from "@/components/post-bits";
import { Async, InsufficientState, LoadingBlock } from "@/components/states";
import { Button } from "@/components/ui/button";
import { compact, dateShort, int, p as fmtP, pct, signedPct } from "@/lib/format";
import type { Autopsy } from "@/lib/types";
import { useApi } from "@/lib/use-api";

export default function AutopsyPage() {
  const { id } = useParams<{ id: string }>();
  const valid = /^\d+$/.test(id ?? "");
  const state = useApi<Autopsy>(valid ? `/posts/${id}/autopsy` : null);
  if (!valid) return <InsufficientState title="That isn't a post id">Open a post from <Link className="underline" href="/memory">Content memory</Link>.</InsufficientState>;
  return (
    <>
      <Link href="/memory" className="mb-6 inline-flex items-center gap-1 text-sm text-mute hover:text-ink"><ArrowLeft className="size-4" />Content memory</Link>
      <Async state={state} skeleton={<LoadingBlock rows={8} label="Loading autopsy" />}>{(a) => <Body a={a} />}</Async>
    </>
  );
}

function Body({ a }: { a: Autopsy }) {
  const { post, benchmark: b } = a;
  const m = post.metrics;
  const idx = b.performance_index;
  const mc = a.model_check;
  return (
    <>
      <PageHeader
        eyebrow={`02 · Content autopsy · ${post.external_id ?? `#${post.id}`}`}
        title={<>{idx >= 1.1 ? "It outperformed." : idx <= 0.9 ? "It underperformed." : "It performed about as expected."}</>}
        lede={<span className="num">{pct(m.engagement_rate, 2)} engagement, {idx.toFixed(2)}× the {post.platform} median ({pct(b.platform_median_engagement_rate, 2)}). {b.platform_percentile.toFixed(0)}th percentile of {b.platform_n} posts.</span>}
        actions={<Button asChild variant="accent"><Link href={`/lab?from=${post.id}`}>Iterate in the Lab <ArrowRight className="size-4" /></Link></Button>}
      />

      <div className="grid gap-10 lg:grid-cols-[1.2fr_1fr]">
        <div>
          <div className="mb-3 flex flex-wrap items-center gap-2"><PlatformDot platform={post.platform} /><Tag>{post.format}</Tag><Tag>{post.topic}</Tag><Tag>{post.hook}</Tag><Tag>{post.tone}</Tag><Tag tone="mute">{post.daypart}</Tag><span className="text-xs text-mute">{dateShort(post.published_at)}</span></div>
          <blockquote className="whitespace-pre-line border-l-2 border-ink bg-card p-5 text-[15px] leading-relaxed">{post.caption}</blockquote>
          <p className="num mt-2 text-xs text-mute">{post.caption_length} chars · {post.hashtag_count} hashtags · {post.emoji_count} emoji · {post.has_question ? "question" : "no question"} · {post.has_cta ? "CTA" : "no CTA"}</p>
        </div>
        <div className="grid grid-cols-2 gap-6 self-start">
          <Stat label="Impressions" value={compact(m.impressions)} sub={`${int(m.reach)} reached`} />
          <Stat label="Engagements" value={int(m.engagements)} sub={`${int(m.likes)} likes · ${int(m.comments)} comments`} />
          <Stat label="Shares" value={int(m.shares)} />
          <Stat label="Saves" value={int(m.saves)} />
        </div>
      </div>

      <Section title="Against the benchmark" kicker="Where it landed">
        <div className="grid gap-8 md:grid-cols-2">
          <Rank label={`All ${post.platform} posts`} pctile={b.platform_percentile} n={b.platform_n} median={b.platform_median_engagement_rate} own={m.engagement_rate} />
          <Rank label={`${post.platform} ${post.format} posts`} pctile={b.format_percentile} n={b.format_n} median={b.format_median_engagement_rate} own={m.engagement_rate} />
        </div>
        <div className="mt-8">
          <p className="eyebrow mb-3">How the response was shaped (vs platform median)</p>
          <DivergingBars items={a.engagement_mix.filter((x) => x.vs_median_pct !== null).map((x) => ({ label: x.label, value: x.vs_median_pct as number }))} max={Math.max(100, ...a.engagement_mix.map((x) => Math.abs(x.vs_median_pct ?? 0)))} />
        </div>
      </Section>

      <Section title="What history associates with these choices" kicker="Evidence, not verdicts" aside="Same-platform posts with vs without each attribute">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[40rem] text-sm">
            <thead><tr className="eyebrow border-b border-ink text-left"><th className="py-2 font-normal">Attribute</th><th className="font-normal">This post</th><th className="text-right font-normal">With (avg · n)</th><th className="text-right font-normal">Without (avg · n)</th><th className="text-right font-normal">Difference</th></tr></thead>
            <tbody>
              {a.attribute_evidence.map((e) => (
                <tr key={e.attribute} className="border-b border-line">
                  <td className="py-2.5">{e.attribute}</td><td>{e.value}</td>
                  {e.evidence ? (<>
                    <td className="num text-right">{pct(e.evidence.mean_with, 2)} · {e.evidence.n_with}</td>
                    <td className="num text-right">{pct(e.evidence.mean_without, 2)} · {e.evidence.n_without}</td>
                    <td className="num text-right"><span className={e.evidence.p_value < 0.05 ? "font-semibold" : "text-mute"}>{signedPct(e.evidence.lift_pct)}</span> <span className="text-xs text-mute">{fmtP(e.evidence.p_value)}</span></td>
                  </>) : <td colSpan={3} className="text-right text-xs text-mute">too few comparable posts (need ≥ 8 on each side)</td>}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="mt-3 text-xs text-mute">{a.caveat} Bold = p &lt; 0.05 (uncorrected, single comparison per row).</p>
      </Section>

      {mc && (
        <Section title="Did the model see it coming?" kicker="Pre-publication prediction vs actual" aside={<Tag tone={mc.split === "holdout" ? "lime" : "mute"}>{mc.split === "holdout" ? "out-of-sample" : "in training period"}</Tag>}>
          <div className="grid gap-8 md:grid-cols-[1fr_1.2fr]">
            <div className="space-y-4">
              <Stat label="Predicted before posting" value={pct(mc.predicted_engagement_rate, 2)} />
              <Stat label="Actual" value={pct(mc.actual_engagement_rate, 2)} sub={`${mc.ratio_actual_to_predicted.toFixed(2)}× the prediction`} />
              <p className="text-sm text-ink-2">{mc.note}</p>
            </div>
            <div><p className="eyebrow mb-3">Largest model contributions (within platform)</p><DivergingBars items={mc.contributions.map((c) => ({ label: c.label, value: c.effect_pct, detail: c.value }))} /></div>
          </div>
        </Section>
      )}

      {a.archetype && (
        <p className="mt-10 border-t border-line pt-4 text-sm">Archetype: <strong>{a.archetype.name}</strong> <span className="text-mute">· {a.archetype.n} posts ({pct(a.archetype.share, 0)}) share this performance profile (K-Means, descriptive).</span></p>
      )}

      <Section title="Similar past posts" kicker="Similarity search" aside={a.similar.summary ? `median ${pct(a.similar.summary.median_engagement_rate, 2)}` : undefined}>
        {a.similar.status === "ok" ? <NeighborList neighbors={a.similar.neighbors} /> : <InsufficientState>{a.similar.message}</InsufficientState>}
      </Section>

      <Section title="Read-out" kicker="AI interpretation">
        <InterpretationPanel request={{ scope: "autopsy", post_id: post.id }} title="What this post suggests" />
      </Section>
    </>
  );
}

function Rank({ label, pctile, n, median, own }: { label: string; pctile: number; n: number; median: number; own: number }) {
  return (
    <div>
      <p className="eyebrow">{label}</p>
      <p className="num mt-2 text-3xl">{pctile.toFixed(0)}<span className="text-lg text-mute">th percentile</span></p>
      <div className="relative mt-3 h-2 bg-paper-2" role="img" aria-label={`${pctile.toFixed(0)}th percentile of ${n} posts`}>
        <div className="absolute inset-y-0 left-0 bg-ink" style={{ width: `${pctile}%` }} />
        <div className="absolute -inset-y-1 left-1/2 w-px bg-mute" title="median" />
      </div>
      <p className="num mt-2 text-xs text-mute">n={n} · median {pct(median, 2)} · this post {pct(own, 2)}</p>
    </div>
  );
}
