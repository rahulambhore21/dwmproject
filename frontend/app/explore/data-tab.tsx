"use client";

import { Section, Tag } from "@/components/editorial";
import { Async, ErrorState } from "@/components/states";
import { Button } from "@/components/ui/button";
import { ALGORITHM_LABELS, dateShort, fixed, int } from "@/lib/format";
import { api } from "@/lib/api";
import type { EtlRuns, ModelList, ModelRunSummary } from "@/lib/types";
import { useAction, useApi } from "@/lib/use-api";
import { CsvImporter } from "./csv-importer";

const KEY_METRICS: Record<string, string[]> = {
  linear_regression: ["r2", "pearson_r"], multiple_linear_regression: ["r2", "r2_platform_adjusted", "cv_r2_mean"],
  mutual_information: ["features_above_noise", "features_ranked"], decision_tree: ["roc_auc", "accuracy", "baseline_accuracy"],
  gaussian_nb: ["roc_auc", "accuracy", "mean_predicted_probability"], kmeans: ["silhouette", "inertia"], agglomerative: ["silhouette", "n_segments"],
  apriori: ["rules_significant", "candidate_rules"],
};

export function DataTab() {
  const models = useApi<ModelList>("/models");
  const etl = useApi<EtlRuns>("/etl/runs");
  const retrain = useAction(async () => { await api.post("/models/retrain?force=true"); models.reload(); });
  return (
    <div className="space-y-2">
      <Section title="Model registry" kicker="Every run stores its metrics" className="mt-0" aside={models.data ? `${models.data.total_runs_stored} runs stored` : undefined}>
        <div className="mb-4 flex items-center gap-3"><Button size="sm" variant="outline" loading={retrain.pending} onClick={() => retrain.run()}>Retrain all (force)</Button><span className="text-xs text-mute">Training is deterministic (seed 42, chronological split): same data in, same metrics out.</span></div>
        {retrain.error && <ErrorState error={retrain.error} className="mb-4" />}
        <Async state={models}>
          {(d) => (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[46rem] text-sm">
                <thead><tr className="eyebrow border-b border-ink text-left"><th className="py-2 font-normal">Algorithm</th><th className="font-normal">Status</th><th className="font-normal">Target</th><th className="text-right font-normal">Train / test</th><th className="font-normal pl-6">Key metrics</th><th className="text-right font-normal">Trained</th></tr></thead>
                <tbody>
                  {d.runs.map((r) => <RunRow key={r.id} r={r} />)}
                </tbody>
              </table>
            </div>
          )}
        </Async>
      </Section>
      <Section title="Bring your own data" kicker="CSV → map → validate → warehouse → retrain">
        <CsvImporter onDone={() => { models.reload(); etl.reload(); }} />
        <Async state={etl}>
          {(d) => d.items.length === 0 ? null : (
            <div className="mt-8">
              <p className="eyebrow mb-2">Recent ETL runs</p>
              <ul className="divide-y divide-line border-y border-line text-sm">
                {d.items.map((r) => <li key={r.id} className="flex flex-wrap justify-between gap-2 py-2"><span>{r.source}</span><span className="num text-xs text-mute">{r.rows_loaded}/{r.rows_in} loaded · {r.report.rows_rejected} rejected · {r.report.duplicates_skipped} duplicates · {dateShort(r.started_at)}</span></li>)}
              </ul>
            </div>
          )}
        </Async>
      </Section>
    </div>
  );
}

function RunRow({ r }: { r: ModelRunSummary }) {
  const keys = KEY_METRICS[r.algorithm] ?? [];
  return (
    <tr className="border-b border-line align-top">
      <td className="py-3"><p className="font-medium">{ALGORITHM_LABELS[r.algorithm] ?? r.algorithm}</p><p className="num text-[11px] text-mute">#{r.id} · data {r.dataset_hash.slice(0, 8)}</p></td>
      <td><Tag tone={r.status === "ok" ? "neutral" : "alert"}>{r.status.replace("_", " ")}</Tag></td>
      <td className="text-xs text-ink-2">{r.target ?? r.task}</td>
      <td className="num text-right text-xs">{int(r.n_train)} / {int(r.n_test)}</td>
      <td className="num pl-6 text-xs">{r.status !== "ok" ? <span className="text-mute">{r.message}</span> : keys.filter((k) => r.metrics[k] != null).map((k) => <span key={k} className="mr-3 inline-block"><span className="text-mute">{k.replace(/_/g, " ")}</span> <strong>{typeof r.metrics[k] === "number" && Math.abs(r.metrics[k] as number) <= 1.0001 && !k.startsWith("n_") ? fixed(r.metrics[k] as number) : fixed(r.metrics[k] as number, 0)}</strong></span>)}</td>
      <td className="text-right text-xs text-mute">{dateShort(r.created_at)}</td>
    </tr>
  );
}
