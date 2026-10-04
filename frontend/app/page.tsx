"use client";

import { ArrowRight } from "lucide-react";
import Link from "next/link";
import { useMemo, useState } from "react";
import { TrendChart } from "@/components/charts";
import { Delta, PageHeader, Section, Stat, Tag } from "@/components/editorial";
import { InterpretationPanel } from "@/components/interpretation";
import { PostCardList } from "@/components/post-bits";
import { Async, EmptyState, InsufficientState } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { ALGORITHM_LABELS, VERDICT_LABELS, compact, dateShort, fixed, int, pct } from "@/lib/format";
import type { AprioriRule, Overview } from "@/lib/types";
import { useApi } from "@/lib/use-api";
import { cn } from "@/lib/utils";

export default function OverviewPage() {
  const state = useApi<Overview>("/overview");
  return (
    <Async state={state} skeleton={<OverviewSkeleton />}>
      {(o) => (o.status === "empty" ? <EmptyOverview message={o.message} /> : <OverviewBody o={o} />)}
    </Async>
  );
}

function OverviewSkeleton() {
  return (
    <div className="space-y-10">
      <Skeleton className="h-40 w-full" />
      <div className="grid gap-6 sm:grid-cols-4">{[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-24" />)}</div>
      <Skeleton className="h-72 w-full" />
    </div>
  );
}

function EmptyOverview({ message }: { message: string | null }) {
  return (
    <>
      <PageHeader eyebrow="Overview" title="Nothing to read yet." />
      <EmptyState title="No posts in this workspace" action={<Button asChild variant="accent"><Link href="/explore?tab=data">Import a CSV</Link></Button>}>
        {message} Import your post history, or run <code className="font-mono">npm run seed</code> to load the demo workspace.
      </EmptyState>
    </>
  );
}

const LOOP = [
  { step: "Understand", href: "/memory", blurb: "Read your history" },
  { step: "Decide", href: "/lab", blurb: "Score a draft before it ships" },
  { step: "Experiment", href: "/experiments", blurb: "Test one change at a time" },
  { step: "Learn", href: "/learning", blurb: "Keep what the evidence supports" },
];

function OverviewBody({ o }: { o: Overview }) {
  const k = o.kpis!;
  const trend = k.trend_90d.delta_pct !== null ? k.trend_90d : k.trend_30d;
  const [platform, setPlatform] = useState<string>("All");
  const platforms = o.platforms ?? [];
  const chartData = useMemo(() => {
    if (platform === "All") return o.trend!.monthly.map((m) => ({ month: m.month, "All platforms": m.engagement_rate }));
    return o.trend!.by_platform.map((r) => ({ month: String(r.month), [platform]: (r[platform] as number | null) ?? null, "All platforms": o.trend!.monthly.find((m) => m.month === r.month)?.engagement_rate ?? null }));
  }, [o, platform]);
  const loopCounts = [`${int(o.data!.posts)} posts`, o.model_health!.predictive_ready ? "model ready" : "model pending", `${o.experiments!.running} running`, `${o.experiments!.completed} recorded`];

  return (
    <>
      <PageHeader
        eyebrow={`${o.workspace.name}${o.workspace.is_demo ? " · demo workspace" : ""}`}
        title={<>What your content is <em className="italic">telling</em> you.</>}
        lede={`${int(o.data!.posts)} posts from ${dateShort(o.data!.first_post)} to ${dateShort(o.data!.last_post)}, read through a dimensional warehouse and eight stored models. Every number below traces back to that history.`}
        actions={<><Button asChild variant="accent"><Link href="/lab">Score a draft <ArrowRight className="size-4" /></Link></Button><Button asChild variant="outline"><Link href="/explore">Explore the data</Link></Button></>}
      />

      <ol className="grid gap-px border border-line bg-line sm:grid-cols-4" aria-label="The SIGNAL loop">
        {LOOP.map((l, i) => (
          <li key={l.step} className="bg-paper">
            <Link href={l.href} className="group block p-4 hover:bg-paper-2">
              <p className="eyebrow">{String(i + 1).padStart(2, "0")} · {l.step}</p>
              <p className="mt-2 text-sm">{l.blurb}</p>
              <p className="num mt-3 flex items-center justify-between text-xs text-mute">{loopCounts[i]}<ArrowRight className="size-3.5 transition-transform group-hover:translate-x-0.5" aria-hidden /></p>
            </Link>
          </li>
        ))}
      </ol>

      <div className="mt-12 grid gap-8 sm:grid-cols-2 lg:grid-cols-4">
        <Stat label="Avg engagement rate" value={pct(k.avg_engagement_rate, 2)} sub={<Delta pct={trend.delta_pct} p={trend.p_value} label={`last ${trend.window_days}d vs prior`} />} />
        <Stat label="Posts analysed" value={int(o.data!.posts)} sub={`across ${platforms.length} platforms`} />
        <Stat label="Median impressions" value={compact(k.median_impressions)} sub={`${compact(k.total_impressions)} total`} />
        <Stat label="Experiments" value={`${o.experiments!.completed} / ${o.experiments!.completed + o.experiments!.running}`} sub="completed / total" />
      </div>

      <Section title="Engagement over time" kicker="Understand" aside={`${trend.n_current} posts in the latest window`}>
        <div className="mb-4 flex flex-wrap gap-2" role="group" aria-label="Platform filter">
          {["All", ...platforms.map((p) => p.platform)].map((p) => (
            <button key={p} type="button" onClick={() => setPlatform(p)} aria-pressed={platform === p}
              className={cn("border px-3 py-1 text-xs transition-colors", platform === p ? "border-ink bg-ink text-paper" : "border-line hover:border-ink")}>{p}</button>
          ))}
        </div>
        <TrendChart data={chartData} primary={platform === "All" ? "All platforms" : platform} secondary={platform === "All" ? [] : ["All platforms"]} baseline={k.avg_engagement_rate} />
        <p className="mt-2 text-xs text-mute">Mean engagement rate per post, by publication month. Dashed line is the all-time average. Platforms have different baselines, so compare within a platform.</p>
      </Section>

      <Section title="What the history says" kicker="Understand → Decide" aside="Apriori rules, Benjamini–Hochberg corrected">
        <div className="grid gap-8 lg:grid-cols-2 [&>*]:min-w-0">
          <RuleColumn title="Linked to top-quartile posts" rules={o.signals!.working} tone="lime" empty="No attribute combination clears the significance bar yet." />
          <RuleColumn title="Linked to bottom-quartile posts" rules={o.signals!.underperforming} tone="alert" empty="No reliably weak pattern detected." />
        </div>
        {o.suggested_tests!.length > 0 && (
          <div className="mt-8">
            <p className="eyebrow mb-3">Worth testing next</p>
            <ul className="divide-y divide-line border-y border-line">
              {o.suggested_tests!.map((s) => (
                <li key={s.title} className="flex flex-wrap items-center justify-between gap-3 py-3">
                  <div className="min-w-0 max-w-2xl"><p className="font-medium">{s.title}</p><p className="text-sm text-mute">{s.basis}</p></div>
                  <Button asChild size="sm" variant="outline"><Link href={`/lab?prefill=${encodeURIComponent(s.antecedents.join("|"))}`}>Try in Lab <ArrowRight className="size-3.5" /></Link></Button>
                </li>
              ))}
            </ul>
          </div>
        )}
      </Section>

      <Section title="Recent standouts" kicker="Last 120 days · relative to platform median" aside={<Link href="/memory" className="underline underline-offset-4">All posts</Link>}>
        <div className="grid gap-10 lg:grid-cols-2 [&>*]:min-w-0">
          <div><p className="eyebrow mb-2">Best</p><PostCardList posts={o.top_posts!} empty="No recent posts." /></div>
          <div><p className="eyebrow mb-2">Weakest</p><PostCardList posts={o.bottom_posts!} empty="No recent posts." /></div>
        </div>
      </Section>

      <Section title="Experiments & learnings" kicker="Experiment → Learn" aside={<Link href="/experiments" className="underline underline-offset-4">Manage</Link>}>
        <div className="grid gap-10 lg:grid-cols-2 [&>*]:min-w-0">
          <div>
            <p className="eyebrow mb-2">Recent experiments</p>
            {o.experiments!.recent.length === 0 ? <EmptyState title="No experiments yet">Create one from the Pre-Publish Lab.</EmptyState> : (
              <ul className="divide-y divide-line border-y border-line">
                {o.experiments!.recent.map((e) => (
                  <li key={e.id}><Link href={`/experiments/${e.id}`} className="flex items-center justify-between gap-3 py-3 hover:bg-paper-2/60">
                    <div className="min-w-0"><p className="truncate text-sm font-medium">{e.name}</p><p className="text-xs text-mute">{e.platform} · {Object.entries(e.analysis.counts).map(([l, n]) => `${l}:${n}`).join(" · ")}</p></div>
                    <Tag tone={e.analysis.verdict === "adopt" ? "lime" : e.analysis.verdict === "insufficient_data" ? "mute" : "neutral"}>{e.status === "completed" ? VERDICT_LABELS[e.analysis.verdict] : "Running"}</Tag>
                  </Link></li>
                ))}
              </ul>
            )}
          </div>
          <div>
            <p className="eyebrow mb-2">Latest learnings</p>
            {o.learnings!.length === 0 ? <InsufficientState title="Nothing learned yet">Complete an experiment to record what the evidence supports.</InsufficientState> : (
              <ul className="space-y-4">
                {o.learnings!.map((l) => (<li key={l.id} className="border-l-2 border-ink pl-4"><p className="text-sm leading-relaxed">{l.statement}</p><p className="mt-1 text-xs text-mute">{VERDICT_LABELS[l.verdict] ?? l.verdict} · {dateShort(l.created_at)}</p></li>))}
              </ul>
            )}
          </div>
        </div>
      </Section>

      <Section title="Read-out" kicker="AI interpretation">
        <InterpretationPanel request={{ scope: "overview" }} title="What the evidence supports" />
      </Section>

      <Section title="Model health" kicker="Stored runs" aside={<Link href="/explore?tab=models" className="underline underline-offset-4">Registry</Link>}>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[32rem] text-sm">
            <thead><tr className="eyebrow border-b border-ink text-left"><th className="py-2 font-normal">Model</th><th className="font-normal">Status</th><th className="text-right font-normal">Headline metric</th></tr></thead>
            <tbody>
              {o.model_health!.runs.map((r) => (
                <tr key={r.algorithm} className="border-b border-line">
                  <td className="py-2.5">{ALGORITHM_LABELS[r.algorithm] ?? r.algorithm}</td>
                  <td><Tag tone={r.status === "ok" ? "neutral" : "alert"}>{r.status === "ok" ? "trained" : r.status.replace("_", " ")}</Tag></td>
                  <td className="num text-right">{r.headline ? <>{r.headline.label} <strong>{fixed(r.headline.value, r.headline.value > 20 ? 0 : 2)}</strong></> : r.message ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Section>
    </>
  );
}

function RuleColumn({ title, rules, tone, empty }: { title: string; rules: AprioriRule[]; tone: "lime" | "alert"; empty: string }) {
  return (
    <div>
      <p className="eyebrow mb-3 flex items-center gap-2"><span className={cn("size-2", tone === "lime" ? "bg-lime outline outline-1 outline-ink" : "bg-alert")} aria-hidden />{title}</p>
      {rules.length === 0 ? <InsufficientState title="Nothing to report">{empty}</InsufficientState> : (
        <ul className="space-y-3">
          {rules.map((r, i) => (
            <li key={i} className="border border-line bg-card p-4">
              <p className="font-medium leading-snug">{r.antecedent_labels.join("  +  ")}</p>
              <p className="num mt-2 text-sm"><strong>{pct(r.confidence, 0)}</strong> <span className="text-mute">hit rate vs {pct(r.base_rate, 0)} baseline</span></p>
              <p className="num mt-1 text-xs text-mute">{r.n_hits} of {r.n_posts} posts · lift {fixed(r.lift)} · q={fixed(r.q_value, 3)}</p>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
