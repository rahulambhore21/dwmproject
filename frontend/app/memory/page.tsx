"use client";

import { ChevronLeft, ChevronRight, Search } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { PageHeader, PlatformDot, Section } from "@/components/editorial";
import { IndexPill } from "@/components/post-bits";
import { Async, EmptyState, ErrorState, LoadingBlock } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Input, Select } from "@/components/ui/select";
import { dateShort, int, pct } from "@/lib/format";
import { qs } from "@/lib/api";
import type { ModelRunFull, PostList, Vocabulary } from "@/lib/types";
import { useApi } from "@/lib/use-api";

const PAGE_SIZE = 20;

export default function MemoryPage() {
  const vocab = useApi<Vocabulary>("/vocabulary");
  const [f, setF] = useState({ platform: "", format: "", topic: "", hook: "", tone: "", search: "", sort: "published_at", order: "desc", page: 1 });
  const [debounced, setDebounced] = useState(f.search);
  useEffect(() => {
    const t = setTimeout(() => setDebounced(f.search), 300);
    return () => clearTimeout(t);
  }, [f.search]);
  const set = (patch: Partial<typeof f>) => setF((s) => ({ ...s, page: 1, ...patch }));
  const sortKey = f.sort === "perf_index" ? "perf_index" : f.sort;
  const list = useApi<PostList>(`/posts${qs({ ...f, search: debounced, sort: sortKey, page_size: PAGE_SIZE })}`);
  const formats = f.platform && vocab.data ? vocab.data.platforms[f.platform]?.formats.map((x) => x.name) ?? [] : [...new Set(Object.values(vocab.data?.platforms ?? {}).flatMap((p) => p.formats.map((x) => x.name)))].sort();
  const pages = list.data ? Math.max(1, Math.ceil(list.data.total / PAGE_SIZE)) : 1;

  return (
    <>
      <PageHeader eyebrow="01 · Understand" title="Content memory." lede="Every post you've published, with how it did against its own platform's median. Open any post for its autopsy." />
      <Archetypes />
      <Section title="All posts" kicker="Filter · sort · open" className="mt-10" aside={list.data ? `${int(list.data.total)} match` : undefined}>
        <form role="search" aria-label="Filter posts" className="mb-5 grid gap-3 sm:grid-cols-3 lg:grid-cols-6" onSubmit={(e) => e.preventDefault()}>
          <FilterSelect label="Platform" value={f.platform} onChange={(v) => set({ platform: v, format: "" })} options={Object.keys(vocab.data?.platforms ?? {})} />
          <FilterSelect label="Format" value={f.format} onChange={(v) => set({ format: v })} options={formats} />
          <FilterSelect label="Topic" value={f.topic} onChange={(v) => set({ topic: v })} options={vocab.data?.topics ?? []} />
          <FilterSelect label="Hook" value={f.hook} onChange={(v) => set({ hook: v })} options={vocab.data?.hooks ?? []} />
          <FilterSelect label="Tone" value={f.tone} onChange={(v) => set({ tone: v })} options={vocab.data?.tones ?? []} />
          <div className="space-y-1.5">
            <label htmlFor="memory-search" className="eyebrow block">Search captions</label>
            <div className="relative"><Search className="pointer-events-none absolute left-2.5 top-3 size-4 text-mute" aria-hidden /><Input id="memory-search" className="pl-8" value={f.search} placeholder="e.g. A/B testing" maxLength={100} onChange={(e) => set({ search: e.target.value })} /></div>
          </div>
        </form>
        <div className="mb-3 flex flex-wrap items-center gap-3 text-sm">
          <label htmlFor="sort" className="eyebrow">Sort</label>
          <Select id="sort" className="h-8 w-auto text-xs" value={f.sort} onChange={(e) => set({ sort: e.target.value })}>
            <option value="published_at">Date</option><option value="perf_index">Performance vs platform</option><option value="engagement_rate">Engagement rate</option><option value="impressions">Impressions</option>
          </Select>
          <Button size="sm" variant="outline" onClick={() => set({ order: f.order === "desc" ? "asc" : "desc" })} aria-label={`Order: ${f.order === "desc" ? "descending" : "ascending"}`}>{f.order === "desc" ? "↓ Desc" : "↑ Asc"}</Button>
        </div>
        <Async state={list} skeleton={<LoadingBlock rows={8} label="Loading posts" />}>
          {(d) =>
            d.items.length === 0 ? (
              <EmptyState title="No posts match these filters" action={<Button variant="outline" size="sm" onClick={() => setF({ ...f, platform: "", format: "", topic: "", hook: "", tone: "", search: "", page: 1 })}>Clear filters</Button>}>
                {d.total === 0 && !f.platform && !f.search ? "The workspace has no posts yet. Import a CSV from Explore → Data." : "Try removing a filter."}
              </EmptyState>
            ) : (
              <>
                <div className="overflow-x-auto">
                  <table className="w-full min-w-[46rem] text-sm">
                    <thead><tr className="eyebrow border-b border-ink text-left"><th className="w-10 py-2 font-normal"><span className="sr-only">Platform</span></th><th className="font-normal">Post</th><th className="font-normal">Format · hook</th><th className="text-right font-normal">Reach</th><th className="text-right font-normal">Engagement</th><th className="text-right font-normal">vs median</th></tr></thead>
                    <tbody>
                      {d.items.map((p) => (
                        <tr key={p.post_id} className="border-b border-line hover:bg-paper-2/60">
                          <td className="py-3"><PlatformDot platform={p.platform} /></td>
                          <td className="max-w-md pr-4"><Link href={`/memory/${p.post_id}`} className="block truncate underline-offset-4 hover:underline">{p.caption_preview}</Link><span className="text-xs text-mute">{dateShort(p.published_at)} · {p.topic}</span></td>
                          <td className="text-xs text-ink-2">{p.format}<br /><span className="text-mute">{p.hook}</span></td>
                          <td className="num text-right">{int(p.impressions)}</td>
                          <td className="num text-right">{pct(p.engagement_rate, 2)}</td>
                          <td className="text-right"><IndexPill value={p.performance_index} /></td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <nav className="mt-4 flex items-center justify-between text-sm" aria-label="Pagination">
                  <span className="num text-mute">Page {d.page} of {pages}</span>
                  <div className="flex gap-2">
                    <Button size="sm" variant="outline" disabled={f.page <= 1} onClick={() => setF({ ...f, page: f.page - 1 })}><ChevronLeft className="size-4" />Prev</Button>
                    <Button size="sm" variant="outline" disabled={f.page >= pages} onClick={() => setF({ ...f, page: f.page + 1 })}>Next<ChevronRight className="size-4" /></Button>
                  </div>
                </nav>
              </>
            )
          }
        </Async>
      </Section>
    </>
  );
}

function FilterSelect({ label, value, onChange, options }: { label: string; value: string; onChange: (v: string) => void; options: string[] }) {
  const id = `f-${label.toLowerCase()}`;
  return (
    <div className="space-y-1.5">
      <label htmlFor={id} className="eyebrow block">{label}</label>
      <Select id={id} value={value} onChange={(e) => onChange(e.target.value)}><option value="">All</option>{options.map((o) => <option key={o} value={o}>{o}</option>)}</Select>
    </div>
  );
}

/** K-Means archetypes: descriptive groups of how posts actually performed. */
function Archetypes() {
  const km = useApi<ModelRunFull>("/models/kmeans");
  if (km.loading || km.warming) return <LoadingBlock rows={2} label="Loading archetypes" />;
  if (km.error) return km.error.status === 404 ? null : <ErrorState error={km.error} onRetry={km.reload} />;
  const run = km.data;
  if (!run || run.status !== "ok") return null;
  const clusters = run.results.clusters as { id: number; name: string; n: number; share: number; mean_engagement_rate: number; over_indexed: { dimension: string; level: string }[] }[];
  return (
    <div>
      <p className="eyebrow mb-3">Post archetypes · K-Means on how posts performed (silhouette {Number(run.metrics.silhouette).toFixed(2)})</p>
      <ul className="grid gap-px border border-line bg-line sm:grid-cols-2 lg:grid-cols-4">
        {clusters.map((c) => (
          <li key={c.id} className="bg-card p-4">
            <p className="font-medium">{c.name}</p>
            <p className="num mt-1 text-xs text-mute">{c.n} posts · {pct(c.share, 0)} · avg {pct(c.mean_engagement_rate, 1)}</p>
            <p className="mt-2 text-xs text-ink-2">{c.over_indexed.length ? `Over-represented: ${c.over_indexed.slice(0, 2).map((o) => o.level).join(", ")}` : "No dominant attribute"}</p>
          </li>
        ))}
      </ul>
    </div>
  );
}
