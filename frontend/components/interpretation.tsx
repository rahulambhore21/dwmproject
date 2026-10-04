"use client";

import { ChevronDown, Sparkles } from "lucide-react";
import { useState } from "react";
import { StrengthBadge } from "@/components/editorial";
import { ErrorState } from "@/components/states";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import type { Interpretation } from "@/lib/types";
import { useAction } from "@/lib/use-api";

export type InterpretRequest =
  | { scope: "overview" }
  | { scope: "autopsy"; post_id: number }
  | { scope: "prediction"; draft: unknown }
  | { scope: "experiment"; experiment_id: number };

/**
 * AI interpretation layer. Every sentence cites evidence ids produced by the deterministic analytics;
 * nothing is shown that is not traceable to an evidence row.
 */
export function InterpretationPanel({ request, disabled, title = "Interpretation" }: { request: InterpretRequest; disabled?: boolean; title?: string }) {
  const [result, setResult] = useState<Interpretation | null>(null);
  const [open, setOpen] = useState<string | null>(null);
  const action = useAction((r: InterpretRequest) => api.post<Interpretation>("/ai/interpret", r));
  const evidenceById = new Map(result?.evidence.map((e) => [e.id, e]));

  const run = async () => {
    const r = await action.run(request);
    if (r) setResult(r);
  };

  return (
    <div className="border border-ink bg-card">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line px-5 py-3">
        <div className="flex items-center gap-2">
          <Sparkles className="size-4" aria-hidden />
          <h3 className="font-medium">{title}</h3>
          {result && (
            <Badge tone={result.source === "llm" ? "lime" : "neutral"} title={result.fallback_reason ?? undefined}>
              {result.source === "llm" ? `Claude · evidence-validated` : "Deterministic reading"}
            </Badge>
          )}
        </div>
        <Button size="sm" variant={result ? "outline" : "accent"} onClick={run} loading={action.pending} disabled={disabled}>
          {result ? "Regenerate" : "Interpret this"}
        </Button>
      </div>
      <div className="px-5 py-4">
        {!result && !action.error && !action.pending && (
          <p className="text-sm text-mute">
            Turns the structured evidence on this page into plain-language findings. Every statement cites the evidence behind it, and uses hedged language: patterns are associations, not causes.
          </p>
        )}
        {action.error && <ErrorState error={action.error} onRetry={run} />}
        {result && result.statements.length === 0 && <p className="text-sm text-mute">{result.caveats[0] ?? "Not enough evidence to interpret."}</p>}
        {result && result.statements.length > 0 && (
          <div className="space-y-4">
            <ol className="space-y-4">
              {result.statements.map((s, i) => (
                <li key={i} className="grid grid-cols-[1.5rem_1fr] gap-3">
                  <span className="num pt-0.5 text-xs text-mute">{String(i + 1).padStart(2, "0")}</span>
                  <div>
                    <p className="text-[15px] leading-relaxed">{s.text}</p>
                    <div className="mt-2 flex flex-wrap items-center gap-1.5">
                      <StrengthBadge strength={s.strength} />
                      {s.evidence_ids.map((id) => (
                        <button
                          key={id}
                          type="button"
                          onClick={() => setOpen(open === id ? null : id)}
                          aria-expanded={open === id}
                          className="inline-flex items-center gap-1 border border-line px-1.5 py-0.5 font-mono text-[11px] hover:border-ink"
                        >
                          {id}
                          <ChevronDown className={`size-3 transition-transform ${open === id ? "rotate-180" : ""}`} aria-hidden />
                        </button>
                      ))}
                    </div>
                    {s.evidence_ids.includes(open ?? "") && open && evidenceById.get(open) && (
                      <div className="mt-2 border-l-2 border-lime bg-paper px-3 py-2 text-xs leading-relaxed text-ink-2">
                        <p className="eyebrow mb-1">{evidenceById.get(open)!.label}</p>
                        {evidenceById.get(open)!.text}
                      </div>
                    )}
                  </div>
                </li>
              ))}
            </ol>
            <div className="border-t border-line pt-3 text-xs text-mute">
              {result.caveats.map((c, i) => <p key={i}>{c}</p>)}
              {result.fallback_reason && <p className="mt-1">Note: {result.fallback_reason}; showing the deterministic reading instead.</p>}
              <p className="mt-1">{result.disclaimer}</p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
