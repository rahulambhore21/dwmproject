"use client";

import { Plus } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { PageHeader, Tag } from "@/components/editorial";
import { Async, EmptyState } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Dialog, DialogClose, DialogContent } from "@/components/ui/dialog";
import { Field, Input, Select, Textarea } from "@/components/ui/select";
import { api } from "@/lib/api";
import { VERDICT_LABELS, dateShort } from "@/lib/format";
import type { ExperimentDetail, ExperimentInput, ExperimentSummary, Vocabulary } from "@/lib/types";
import { useAction, useApi } from "@/lib/use-api";

export default function ExperimentsPage() {
  const list = useApi<{ items: ExperimentSummary[] }>("/experiments");
  return (
    <>
      <PageHeader
        eyebrow="04 · Experiment"
        title="One change at a time."
        lede="A single post is an anecdote. An experiment compares variants on the same platform, waits for enough posts, and reports what it can and cannot tell you, including the smallest difference it was able to detect."
        actions={<NewExperiment />}
      />
      <Async state={list}>
        {(d) =>
          d.items.length === 0 ? (
            <EmptyState title="No experiments yet" action={<Button asChild variant="accent"><Link href="/lab">Find a change in the Lab</Link></Button>}>
              Start from a Pre-Publish Lab suggestion (the model&apos;s prediction is stored alongside) or create one by hand.
            </EmptyState>
          ) : (
            <ul className="grid gap-px border border-line bg-line md:grid-cols-2">
              {d.items.map((e) => <ExperimentCard key={e.id} e={e} />)}
            </ul>
          )
        }
      </Async>
    </>
  );
}

function ExperimentCard({ e }: { e: ExperimentSummary }) {
  const a = e.analysis;
  return (
    <li className="bg-paper">
      <Link href={`/experiments/${e.id}`} className="block h-full p-6 hover:bg-paper-2/70">
        <div className="mb-3 flex flex-wrap items-center gap-2">
          <Tag tone={e.status === "running" ? "lime" : "ink"}>{e.status}</Tag>
          <Tag>{e.platform}</Tag><Tag tone="mute">{e.variable}</Tag>
          {e.randomized && <Tag tone="mute">randomised</Tag>}
        </div>
        <h2 className="display text-2xl leading-tight">{e.name}</h2>
        <p className="mt-2 line-clamp-2 text-sm text-mute">{e.hypothesis}</p>
        <div className="mt-5 space-y-2">
          {e.variants.map((v) => (
            <div key={v.id} className="grid grid-cols-[1.5rem_1fr_3.5rem] items-center gap-3 text-xs">
              <span className="num font-semibold">{v.label}</span>
              <div className="h-1.5 bg-paper-2" role="img" aria-label={`Variant ${v.label}: ${v.n} of ${e.min_per_variant} posts`}><div className="h-full bg-ink" style={{ width: `${Math.min(100, (v.n / e.min_per_variant) * 100)}%` }} /></div>
              <span className="num text-right text-mute">{v.n}/{e.min_per_variant}</span>
            </div>
          ))}
        </div>
        <p className="mt-4 text-sm"><strong>{VERDICT_LABELS[a.verdict]}</strong>{e.status === "completed" && e.completed_at ? <span className="text-mute"> · {dateShort(e.completed_at)}</span> : <span className="text-mute"> · {a.message ?? "Ready to conclude"}</span>}</p>
      </Link>
    </li>
  );
}

function NewExperiment() {
  const router = useRouter();
  const vocab = useApi<Vocabulary>("/vocabulary");
  const [open, setOpen] = useState(false);
  const [f, setF] = useState({ name: "", hypothesis: "", variable: "hook", platform: "", a: "", b: "", min: 6, randomized: false });
  const platforms = Object.keys(vocab.data?.platforms ?? {});
  const create = useAction(async () => {
    const input: ExperimentInput = {
      name: f.name.trim(), hypothesis: f.hypothesis.trim(), variable: f.variable, platform: f.platform || platforms[0],
      min_per_variant: f.min, randomized: f.randomized, source: "manual",
      variants: [{ label: "A", description: f.a.trim(), is_control: true }, { label: "B", description: f.b.trim(), is_control: false }],
    };
    const exp = await api.post<ExperimentDetail>("/experiments", input);
    router.push(`/experiments/${exp.id}`);
  });
  const ready = f.name.trim().length >= 3 && f.hypothesis.trim().length >= 5 && f.a.trim() && f.b.trim();
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <Button variant="accent" onClick={() => setOpen(true)}><Plus className="size-4" />New experiment</Button>
      <DialogContent title="New experiment" description="Define a control (A) and one variant (B). Change a single thing between them.">
        <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); if (ready) create.run(); }}>
          <Field label="Name" htmlFor="x-name"><Input id="x-name" required minLength={3} maxLength={160} value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} placeholder="Question vs statement openers" /></Field>
          <Field label="Hypothesis" htmlFor="x-hyp"><Textarea id="x-hyp" className="min-h-20" required minLength={5} maxLength={1000} value={f.hypothesis} onChange={(e) => setF({ ...f, hypothesis: e.target.value })} placeholder="Question openers will earn a higher engagement rate than statements." /></Field>
          <div className="grid grid-cols-2 gap-4">
            <Field label="Platform" htmlFor="x-plat"><Select id="x-plat" value={f.platform || platforms[0] || ""} onChange={(e) => setF({ ...f, platform: e.target.value })}>{platforms.map((p) => <option key={p}>{p}</option>)}</Select></Field>
            <Field label="What changes" htmlFor="x-var"><Select id="x-var" value={f.variable} onChange={(e) => setF({ ...f, variable: e.target.value })}>{["hook", "format", "tone", "topic", "daypart", "caption_length", "has_question", "has_cta", "hashtags", "other"].map((v) => <option key={v}>{v}</option>)}</Select></Field>
            <Field label="A · control" htmlFor="x-a"><Input id="x-a" required maxLength={240} value={f.a} onChange={(e) => setF({ ...f, a: e.target.value })} placeholder="Statement opener" /></Field>
            <Field label="B · variant" htmlFor="x-b"><Input id="x-b" required maxLength={240} value={f.b} onChange={(e) => setF({ ...f, b: e.target.value })} placeholder="Question opener" /></Field>
            <Field label="Min posts per variant" htmlFor="x-min" hint="No verdict until every variant reaches this."><Input id="x-min" type="number" min={3} max={100} value={f.min} onChange={(e) => setF({ ...f, min: Math.max(3, Math.min(100, Number(e.target.value) || 6)) })} /></Field>
          </div>
          <label className="flex items-start gap-2 text-sm"><input type="checkbox" className="mt-1" checked={f.randomized} onChange={(e) => setF({ ...f, randomized: e.target.checked })} /><span>Posts will be assigned to variants at random.</span></label>
          {create.error && <div role="alert" className="text-sm text-alert">{create.error.message}{create.error.details?.map((d) => <p key={d.field}>{d.field}: {d.message}</p>)}</div>}
          <div className="flex justify-end gap-2"><DialogClose asChild><Button type="button" variant="ghost">Cancel</Button></DialogClose><Button type="submit" variant="accent" disabled={!ready} loading={create.pending}>Create</Button></div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
