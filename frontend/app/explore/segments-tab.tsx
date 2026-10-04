"use client";

import { Section, Tag } from "@/components/editorial";
import { Async, InsufficientState } from "@/components/states";
import { fixed, pct, signedPct } from "@/lib/format";
import type { ModelRunFull } from "@/lib/types";
import { useApi } from "@/lib/use-api";

export function SegmentsTab() {
  const km = useApi<ModelRunFull>("/models/kmeans");
  const ag = useApi<ModelRunFull>("/models/agglomerative");
  return (
    <div className="space-y-2">
      <Section title="Post archetypes" kicker="K-Means on post-publication performance" className="mt-0" aside="descriptive, never a predictor">
        <Async state={km}>
          {(r) => {
            if (r.status !== "ok") return <InsufficientState>{r.message}</InsufficientState>;
            const cl = r.results.clusters as { id: number; name: string; n: number; share: number; mean_engagement_rate: number; mean_save_rate: number; mean_share_rate: number; mean_comment_rate: number; median_impressions: number; over_indexed: { dimension: string; level: string; share_in_cluster: number; share_overall: number; over_index: number }[] }[];
            return (
              <>
                <div className="mb-5 flex gap-2 text-xs"><Tag>k = {String(r.params.selected_k)}</Tag><Tag>silhouette {fixed(Number(r.metrics.silhouette))}</Tag></div>
                <ul className="grid gap-px border border-line bg-line md:grid-cols-2">
                  {cl.map((c) => (
                    <li key={c.id} className="bg-paper p-5">
                      <div className="flex items-baseline justify-between"><h3 className="display text-2xl">{c.name}</h3><span className="num text-xs text-mute">{c.n} posts · {pct(c.share, 0)}</span></div>
                      <dl className="num mt-3 grid grid-cols-4 gap-2 text-xs">
                        <div><dt className="eyebrow">ER</dt><dd>{pct(c.mean_engagement_rate, 1)}</dd></div><div><dt className="eyebrow">Saves</dt><dd>{pct(c.mean_save_rate, 2)}</dd></div><div><dt className="eyebrow">Shares</dt><dd>{pct(c.mean_share_rate, 2)}</dd></div><div><dt className="eyebrow">Comments</dt><dd>{pct(c.mean_comment_rate, 2)}</dd></div>
                      </dl>
                      <p className="mt-3 text-xs text-ink-2">{c.over_indexed.length ? c.over_indexed.map((o) => `${o.level} ${o.over_index.toFixed(1)}×`).join(" · ") : "No attribute is notably over-represented."}</p>
                    </li>
                  ))}
                </ul>
                <p className="mt-3 text-xs text-mute">{String(r.results.note)} Cluster names are assigned by a fixed rule from the strongest standardized dimension of each centroid.</p>
              </>
            );
          }}
        </Async>
      </Section>
      <Section title="Segment families" kicker="Agglomerative clustering (Ward)" aside="platform × format × topic, relative to each platform">
        <Async state={ag}>
          {(r) => {
            if (r.status !== "ok") return <InsufficientState>{r.message}</InsufficientState>;
            const fam = r.results.families as { id: number; name: string; n_segments: number; n_posts: number; mean_relative_er_pct: number; members: { platform: string; format: string; topic: string; n: number; relative_er_pct: number }[] }[];
            return (
              <>
                <div className="mb-5 flex gap-2 text-xs"><Tag>k = {String(r.params.selected_k)}</Tag><Tag>silhouette {fixed(Number(r.metrics.silhouette))}</Tag><Tag tone="mute">{String(r.metrics.n_segments)} segments (≥ {String(r.params.min_posts_per_segment)} posts)</Tag></div>
                <div className="grid gap-8 lg:grid-cols-2">
                  {fam.map((f) => (
                    <div key={f.id}>
                      <div className="mb-2 flex items-baseline justify-between border-b border-ink pb-1"><h3 className="font-medium">{f.name}</h3><span className="num text-xs text-mute">{f.n_segments} segments · {signedPct(f.mean_relative_er_pct, 0)} vs platform avg</span></div>
                      <ul className="divide-y divide-line text-sm">
                        {f.members.slice(0, 6).map((m) => <li key={`${m.platform}${m.format}${m.topic}`} className="flex justify-between gap-3 py-1.5"><span>{m.platform} · {m.format} · {m.topic}</span><span className="num text-xs text-mute">{signedPct(m.relative_er_pct, 0)} · n={m.n}</span></li>)}
                      </ul>
                    </div>
                  ))}
                </div>
                <p className="mt-4 text-xs text-mute">{String(r.results.note)}</p>
              </>
            );
          }}
        </Async>
      </Section>
    </div>
  );
}
