"use client";

import { HBars } from "@/components/charts";
import { Section, Tag } from "@/components/editorial";
import { Async, InsufficientState } from "@/components/states";
import { fixed, p as fmtP, pct, signedPct } from "@/lib/format";
import type { AprioriRule, ModelRunFull } from "@/lib/types";
import { useApi } from "@/lib/use-api";

export function DriversTab() {
  return (
    <div className="space-y-2">
      <MutualInfo />
      <Regression />
      <Rules />
      <Tree />
    </div>
  );
}

function RunGate({ state, children }: { state: ReturnType<typeof useApi<ModelRunFull>>; children: (r: ModelRunFull) => React.ReactNode }) {
  return (
    <Async state={state}>
      {(r) => (r.status !== "ok" ? <InsufficientState title="Model unavailable">{r.message}</InsufficientState> : <>{children(r)}</>)}
    </Async>
  );
}

function MutualInfo() {
  const s = useApi<ModelRunFull>("/models/mutual_information");
  return (
    <Section title="Which attributes carry signal?" kicker="Mutual information" className="mt-0" aside="vs platform-adjusted engagement">
      <RunGate state={s}>
        {(r) => {
          const rows = r.results.ranking as { feature: string; label: string; mi_performance_index: number; noise_floor_performance_index: number; above_noise: boolean }[];
          return (
            <>
              <HBars format={(v) => v.toFixed(3)} items={rows.map((x) => ({ label: x.label, value: x.mi_performance_index, floor: x.noise_floor_performance_index, highlight: x.mi_performance_index > x.noise_floor_performance_index }))} />
              <p className="mt-4 text-xs text-mute">Red tick = noise floor: the 95th percentile of MI when the target is shuffled ({String(r.params.noise_shuffles)} times). Dark bars clear it; grey bars are indistinguishable from chance. MI shows dependence of any shape, not direction or cause. {String(r.metrics.features_above_noise)} of {String(r.metrics.features_ranked)} features clear the floor.</p>
            </>
          );
        }}
      </RunGate>
    </Section>
  );
}

function Regression() {
  const s = useApi<ModelRunFull>("/models/multiple_linear_regression");
  const simple = useApi<ModelRunFull>("/models/linear_regression");
  return (
    <Section title="What moves engagement, holding the rest fixed" kicker="Multiple linear regression on log engagement rate" aside="chronological 80/20 split">
      <RunGate state={s}>
        {(r) => {
          const m = r.metrics as Record<string, number>;
          const terms = (r.results.terms as { label: string; level: string | null; feature: string; multiplier: number; pct_effect: number; p_value: number; significant: boolean; unit: string }[]).filter((t) => t.feature !== "caption_length_sq");
          return (
            <>
              <div className="mb-6 flex flex-wrap gap-2 text-xs">
                <Tag>holdout R² {fixed(m.r2)}</Tag><Tag>baseline R² {fixed(m.baseline_r2)}</Tag><Tag tone="lime">within-platform R² {fixed(m.r2_platform_adjusted)}</Tag><Tag>CV R² {fixed(m.cv_r2_mean)} ± {fixed(m.cv_r2_std)}</Tag><Tag tone="mute">train {r.n_train} · test {r.n_test}</Tag>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full min-w-[34rem] text-sm">
                  <thead><tr className="eyebrow border-b border-ink text-left"><th className="py-2 font-normal">Term</th><th className="font-normal">Compared with</th><th className="text-right font-normal">Effect on ER</th><th className="text-right font-normal">p</th></tr></thead>
                  <tbody>
                    {terms.slice(0, 14).map((t) => (
                      <tr key={t.label + t.level} className="border-b border-line">
                        <td className="py-2">{t.label}{t.level ? `: ${t.level}` : ""}</td><td className="text-xs text-mute">{t.unit}</td>
                        <td className="num text-right"><span className={t.significant ? "font-semibold" : "text-mute"}>{signedPct(t.pct_effect)}</span></td>
                        <td className="num text-right text-xs text-mute">{fmtP(t.p_value)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <p className="mt-3 text-xs text-mute">{String(r.results.note)} Top 14 terms by size. Bold = p &lt; 0.05. Most R² comes from platform baselines; the within-platform figure is the honest measure of content signal.</p>
              {simple.data?.status === "ok" && (
                <p className="mt-4 border-l-2 border-line pl-3 text-sm text-ink-2">
                  Caption length alone (simple linear regression): {signedPct(Number(simple.data.results.pct_change_per_100_chars))} per +100 characters, Pearson r = {fixed(Number(simple.data.results.pearson_r))}, {fmtP(Number(simple.data.results.p_value))}, holdout R² {fixed(Number(simple.data.metrics.r2))}. {String(simple.data.results.interpretation_note)}
                </p>
              )}
            </>
          );
        }}
      </RunGate>
    </Section>
  );
}

function RuleList({ rules, tone }: { rules: AprioriRule[]; tone: "high" | "low" }) {
  if (rules.length === 0) return <InsufficientState title="No rules">Nothing met the support and lift thresholds.</InsufficientState>;
  return (
    <ul className="space-y-2">
      {rules.slice(0, 8).map((r, i) => (
        <li key={i} className="flex flex-wrap items-baseline justify-between gap-2 border border-line bg-card px-4 py-3 text-sm">
          <span className="font-medium">{r.antecedent_labels.join("  +  ")}</span>
          <span className="num text-xs text-mute">{r.n_hits}/{r.n_posts} · {pct(r.confidence, 0)} vs {pct(r.base_rate, 0)} · lift {fixed(r.lift)} · q={fixed(r.q_value, 3)} {r.significant ? <Tag tone={tone === "high" ? "lime" : "alert"}>significant</Tag> : <Tag tone="mute">not significant</Tag>}</span>
        </li>
      ))}
    </ul>
  );
}

function Rules() {
  const s = useApi<ModelRunFull>("/models/apriori");
  return (
    <Section title="Combinations that travel together" kicker="Apriori association rules" aside="Fisher exact · Benjamini–Hochberg">
      <RunGate state={s}>
        {(r) => {
          const rules = r.results.rules as AprioriRule[];
          return (
            <>
              <div className="grid gap-8 lg:grid-cols-2">
                <div><p className="eyebrow mb-2">→ top-quartile posts</p><RuleList rules={rules.filter((x) => x.outcome === "high_performer")} tone="high" /></div>
                <div><p className="eyebrow mb-2">→ bottom-quartile posts</p><RuleList rules={rules.filter((x) => x.outcome === "low_performer")} tone="low" /></div>
              </div>
              <p className="mt-4 text-xs text-mute">{String(r.metrics.candidate_rules)} candidate rules were tested, so a p-value alone would mislead: the q-value corrects for that. {String(r.results.note)}</p>
            </>
          );
        }}
      </RunGate>
    </Section>
  );
}

function Tree() {
  const s = useApi<ModelRunFull>("/models/decision_tree");
  return (
    <Section title="A readable rulebook" kicker="Decision tree (depth ≤ 4)" aside="top-quartile classifier">
      <RunGate state={s}>
        {(r) => {
          const rules = r.results.rules as { conditions: string[]; n_train: number; hit_rate_train: number; lift_train: number | null; n_test: number; hit_rate_test: number | null }[];
          const m = r.metrics as Record<string, number>;
          return (
            <>
              <div className="mb-5 flex flex-wrap gap-2 text-xs"><Tag>holdout AUC {fixed(m.roc_auc)}</Tag><Tag>accuracy {pct(m.accuracy, 0)} (majority baseline {pct(m.baseline_accuracy, 0)})</Tag><Tag tone="mute">base rate {pct(r.results.base_rate_train, 0)}</Tag></div>
              <ul className="space-y-3">
                {rules.slice(0, 6).map((x, i) => (
                  <li key={i} className="border border-line bg-card p-4">
                    <p className="text-sm">{x.conditions.join("  ›  ") || "All posts"}</p>
                    <p className="num mt-2 text-xs text-mute">train: <strong className="text-ink">{pct(x.hit_rate_train, 0)}</strong> top-quartile of {x.n_train} · holdout: {x.hit_rate_test !== null ? <strong className="text-ink">{pct(x.hit_rate_test, 0)}</strong> : "too few posts"} of {x.n_test}</p>
                  </li>
                ))}
              </ul>
              <p className="mt-3 text-xs text-mute">A leaf is trustworthy only if its holdout hit rate stays near its training hit rate. {String(r.results.note)}</p>
            </>
          );
        }}
      </RunGate>
    </Section>
  );
}
