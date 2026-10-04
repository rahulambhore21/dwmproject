"use client";

import Link from "next/link";
import { PageHeader, Tag } from "@/components/editorial";
import { Async, EmptyState } from "@/components/states";
import { Button } from "@/components/ui/button";
import { VERDICT_LABELS, dateShort } from "@/lib/format";
import type { Learning } from "@/lib/types";
import { useApi } from "@/lib/use-api";

export default function LearningPage() {
  const state = useApi<{ items: Learning[] }>("/learnings");
  return (
    <>
      <PageHeader eyebrow="05 · Learn" title="What you now know." lede="Each concluded experiment writes one learning, built only from its measured result, with sample sizes and uncertainty attached. Inconclusive results are kept too: knowing what didn't show an effect is a finding." />
      <Async state={state}>
        {(d) =>
          d.items.length === 0 ? (
            <EmptyState title="Nothing learned yet" action={<Button asChild variant="accent"><Link href="/experiments">Go to experiments</Link></Button>}>Conclude an experiment and its learning appears here.</EmptyState>
          ) : (
            <ol className="relative space-y-0 border-l border-ink pl-8">
              {d.items.map((l) => (
                <li key={l.id} className="relative pb-10">
                  <span className={`absolute -left-[2.45rem] top-1.5 size-3 border border-ink ${l.verdict === "adopt" ? "bg-lime" : "bg-paper"}`} aria-hidden />
                  <div className="mb-2 flex flex-wrap items-center gap-2"><Tag tone={l.verdict === "adopt" ? "lime" : "neutral"}>{VERDICT_LABELS[l.verdict] ?? l.verdict}</Tag><span className="text-xs text-mute">{dateShort(l.created_at)}</span></div>
                  <p className="max-w-3xl text-lg leading-relaxed">{l.statement}</p>
                  {l.experiment_id && <Link href={`/experiments/${l.experiment_id}`} className="mt-2 inline-block text-sm underline underline-offset-4">See the experiment</Link>}
                </li>
              ))}
            </ol>
          )
        }
      </Async>
    </>
  );
}
