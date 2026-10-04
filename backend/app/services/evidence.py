"""Structured evidence + deterministic findings for the AI interpretation layer.

Each builder returns (evidence, statements). Evidence items carry the only numbers
an interpretation may cite. Statements are the deterministic reading, composed from
those same numbers, so they are always consistent with the evidence.
"""
from __future__ import annotations

from typing import Any

Evidence = dict[str, Any]
Statement = dict[str, Any]


class Collector:
    def __init__(self) -> None:
        self.evidence: list[Evidence] = []
        self.statements: list[Statement] = []

    def ev(self, label: str, text: str, numbers: list[float], n: int | None = None, kind: str = "metric") -> str:
        eid = f"E{len(self.evidence) + 1}"
        self.evidence.append({"id": eid, "label": label, "text": text, "numbers": [float(x) for x in numbers], "n": n, "kind": kind})
        return eid

    def say(self, text: str, ids: list[str], strength: str = "moderate") -> None:
        self.statements.append({"text": text, "evidence_ids": ids, "strength": strength})


def _pct(x: float, d: int = 1) -> str:
    return f"{x * 100:.{d}f}%"


def _strength(n: int, significant: bool | None) -> str:
    if significant is False or n < 15:
        return "weak"
    return "strong" if significant and n >= 40 else "moderate"


def overview_evidence(o: dict) -> tuple[list[Evidence], list[Statement]]:
    c = Collector()
    k = o["kpis"]
    for key, label in (("trend_90d", "90-day"), ("trend_30d", "30-day")):
        t = k[key]
        if t["delta_pct"] is None:
            continue
        eid = c.ev(f"{label} engagement trend",
                   f"Mean engagement rate {_pct(t['current'], 2)} over the last {t['window_days']} days (n={t['n_current']}) vs {_pct(t['previous'], 2)} in the "
                   f"{t['window_days']} days before (n={t['n_previous']}); change {t['delta_pct']:+.1f}%, Welch p={t['p_value']:.3f} on platform-adjusted performance.",
                   [t["current"] * 100, t["previous"] * 100, t["delta_pct"], t["p_value"], t["n_current"], t["n_previous"], t["window_days"]],
                   n=t["n_current"] + t["n_previous"], kind="trend")
        sig = t["p_value"] < 0.05
        direction = "higher" if t["delta_pct"] > 0 else "lower"
        if sig:
            c.say(f"Engagement over the last {t['window_days']} days is {abs(t['delta_pct']):.1f}% {direction} than the prior {t['window_days']} days "
                  f"({_pct(t['current'], 2)} vs {_pct(t['previous'], 2)}), a difference unlikely to be noise (p={t['p_value']:.3f}).", [eid], "moderate")
        else:
            c.say(f"Engagement over the last {t['window_days']} days is {abs(t['delta_pct']):.1f}% {direction} than the prior window, but with p={t['p_value']:.3f} "
                  f"this is within normal variation; treat it as no clear trend.", [eid], "weak")
        break
    for r in o["signals"]["working"][:3]:
        eid = c.ev("Pattern linked to top-quartile posts",
                   f"{' + '.join(r['antecedent_labels'])}: {r['n_hits']} of {r['n_posts']} posts reached their platform's top quartile "
                   f"({_pct(r['confidence'], 0)} vs {_pct(r['base_rate'], 0)} baseline), lift {r['lift']:.2f}, q={r['q_value']:.3f}.",
                   [r["n_hits"], r["n_posts"], r["confidence"] * 100, r["base_rate"] * 100, r["lift"], r["q_value"]], n=r["n_posts"], kind="rule")
        c.say(f"Posts with {' + '.join(r['antecedent_labels'])} reached the top quartile in {r['n_hits']} of {r['n_posts']} cases "
              f"({_pct(r['confidence'], 0)} against a {_pct(r['base_rate'], 0)} baseline). This is a historical association; it may reflect other differences between those posts.",
              [eid], _strength(r["n_posts"], r["significant"]))
    for r in o["signals"]["underperforming"][:2]:
        eid = c.ev("Pattern linked to bottom-quartile posts",
                   f"{' + '.join(r['antecedent_labels'])}: {r['n_hits']} of {r['n_posts']} posts landed in their platform's bottom quartile "
                   f"({_pct(r['confidence'], 0)} vs {_pct(r['base_rate'], 0)} baseline), lift {r['lift']:.2f}, q={r['q_value']:.3f}.",
                   [r["n_hits"], r["n_posts"], r["confidence"] * 100, r["base_rate"] * 100, r["lift"], r["q_value"]], n=r["n_posts"], kind="rule")
        c.say(f"{' + '.join(r['antecedent_labels'])} appears more often among weak posts ({r['n_hits']} of {r['n_posts']}, {_pct(r['confidence'], 0)} vs {_pct(r['base_rate'], 0)} baseline); "
              f"worth testing before treating it as a driver.", [eid], _strength(r["n_posts"], r["significant"]))
    for lr in o["learnings"][:2]:
        eid = c.ev("Recorded experiment learning", lr["statement"], [], kind="learning")
        c.say(f"From a completed experiment: {lr['statement']}", [eid], "strong" if lr["verdict"] in ("adopt", "keep_control") else "weak")
    mh = o["model_health"]
    c.ev("Model coverage", f"{mh['trained']} of {mh['total']} analytics models trained successfully.", [mh["trained"], mh["total"]], kind="model")
    return c.evidence, c.statements


def autopsy_evidence(a: dict) -> tuple[list[Evidence], list[Statement]]:
    c = Collector()
    p, b = a["post"], a["benchmark"]
    eid = c.ev("Performance vs benchmark",
               f"Engagement rate {_pct(p['metrics']['engagement_rate'], 2)} vs {_pct(b['platform_median_engagement_rate'], 2)} platform median "
               f"(index {b['performance_index']:.2f}); {b['platform_percentile']:.0f}th percentile of {b['platform_n']} {p['platform']} posts, "
               f"{b['format_percentile']:.0f}th of {b['format_n']} {p['platform']} {p['format']} posts.",
               [p["metrics"]["engagement_rate"] * 100, b["platform_median_engagement_rate"] * 100, b["performance_index"],
                b["platform_percentile"], b["platform_n"], b["format_percentile"], b["format_n"]], n=b["platform_n"], kind="benchmark")
    tier = "above" if b["performance_index"] > 1.1 else ("below" if b["performance_index"] < 0.9 else "close to")
    c.say(f"This post performed {tier} its platform median (index {b['performance_index']:.2f}; {b['platform_percentile']:.0f}th percentile among {b['platform_n']} {p['platform']} posts).", [eid], "strong")
    for ae in a["attribute_evidence"]:
        e = ae["evidence"]
        if not e:
            continue
        sig = e["p_value"] < 0.05
        eid = c.ev(f"{ae['attribute']}: {ae['value']}",
                   f"Same-platform posts with {ae['attribute'].lower()} = {ae['value']} averaged {_pct(e['mean_with'], 2)} (n={e['n_with']}) vs {_pct(e['mean_without'], 2)} "
                   f"without (n={e['n_without']}); difference {e['lift_pct']:+.1f}%, p={e['p_value']:.3f}.",
                   [e["mean_with"] * 100, e["n_with"], e["mean_without"] * 100, e["n_without"], e["lift_pct"], e["p_value"]], n=e["n_with"] + e["n_without"], kind="attribute")
        if sig:
            c.say(f"{ae['attribute']} '{ae['value']}' is associated with {abs(e['lift_pct']):.1f}% {'higher' if e['lift_pct'] > 0 else 'lower'} engagement across {e['n_with']} similar {p['platform']} posts "
                  f"(p={e['p_value']:.3f}). That is an association in history, not proof it drove this post's result.", [eid], _strength(e["n_with"], True))
    mc = a.get("model_check")
    if mc:
        eid = c.ev("Model check",
                   f"Model expected {_pct(mc['predicted_engagement_rate'], 2)}; actual {_pct(mc['actual_engagement_rate'], 2)} (ratio {mc['ratio_actual_to_predicted']:.2f}); post was in the model's {mc['split']} period.",
                   [mc["predicted_engagement_rate"] * 100, mc["actual_engagement_rate"] * 100, mc["ratio_actual_to_predicted"]], kind="model")
        rel = mc["ratio_actual_to_predicted"]
        verdict = "beat" if rel > 1.15 else ("fell short of" if rel < 0.87 else "roughly matched")
        c.say(f"Against what pre-publication attributes suggested ({_pct(mc['predicted_engagement_rate'], 2)}), the post {verdict} expectations ({_pct(mc['actual_engagement_rate'], 2)}). "
              f"{mc['note']}", [eid], "moderate" if mc["split"] == "holdout" else "weak")
    for m in a["engagement_mix"]:
        if m["vs_median_pct"] is not None and abs(m["vs_median_pct"]) >= 40 and m["label"] != "Impressions":
            eid = c.ev(f"{m['label']} vs platform median", f"{m['label']} {_pct(m['value'], 3)} vs median {_pct(m['platform_median'], 3)} ({m['vs_median_pct']:+.0f}%).",
                       [m["value"] * 100, m["platform_median"] * 100, m["vs_median_pct"]], kind="mix")
            c.say(f"{m['label']} was {abs(m['vs_median_pct']):.0f}% {'above' if m['vs_median_pct'] > 0 else 'below'} the platform median, which shapes the kind of response this post earned.", [eid], "moderate")
    return c.evidence, c.statements


def prediction_evidence(r: dict) -> tuple[list[Evidence], list[Statement]]:
    c = Collector()
    pr, md = r["prediction"], r["model"]
    lo, hi = pr["interval_80"]
    eid = c.ev("Predicted engagement rate",
               f"Model estimate {_pct(pr['engagement_rate'], 2)} (80% range {_pct(lo, 2)} to {_pct(hi, 2)}) vs platform median {_pct(pr['platform_median_engagement_rate'], 2)} "
               f"({pr['vs_platform_median_pct']:+.0f}%).",
               [pr["engagement_rate"] * 100, lo * 100, hi * 100, pr["platform_median_engagement_rate"] * 100, pr["vs_platform_median_pct"]], kind="prediction")
    mid = ("above" if pr["vs_platform_median_pct"] > 8 else ("below" if pr["vs_platform_median_pct"] < -8 else "near"))
    c.say(f"The model estimates {_pct(pr['engagement_rate'], 2)} engagement, {mid} the platform median of {_pct(pr['platform_median_engagement_rate'], 2)}; "
          f"the plausible range is wide ({_pct(lo, 2)} to {_pct(hi, 2)}), so the draft could land well either side.", [eid], "moderate")
    adj = md.get("r2_platform_adjusted")
    mid_ = c.ev("Model reliability",
                f"Holdout R² {md['holdout_r2']:.2f} (baseline {md['baseline_r2']:.2f}); within-platform R² {adj:.2f}; trained on {md['n_train']} posts, tested on {md['n_test']} later posts."
                if adj is not None else f"Holdout R² {md['holdout_r2']:.2f}; trained on {md['n_train']} posts.",
                [md["holdout_r2"], md["baseline_r2"], adj or 0, md["n_train"], md["n_test"]], n=md["n_test"], kind="model")
    c.say(f"Most of the model's accuracy comes from platform differences; within a platform it explains about {((adj or 0) * 100):.0f}% of the variation on later posts, so treat predictions as directional.", [mid_], "weak")
    for ct in pr["contributions"][:3]:
        if abs(ct["effect_pct"]) < 2:
            continue
        cid = c.ev(f"Model contribution: {ct['label']}", f"{ct['label']} ({ct['value']}) shifts the estimate by {ct['effect_pct']:+.1f}% relative to an average post.", [ct["effect_pct"]], kind="contribution")
        c.say(f"{ct['label']} ({ct['value']}) is the model's {'tailwind' if ct['effect_pct'] > 0 else 'headwind'} here, worth {ct['effect_pct']:+.1f}% versus an average post. This is a statistical association.", [cid], "moderate")
    for w in r["what_if"][:2]:
        wid = c.ev(f"What-if: {w['change']}", f"Model estimates {w['estimated_change_pct']:+.1f}% for '{w['change']}' ({w['supporting_posts']} past posts use this option).",
                   [w["estimated_change_pct"], w["supporting_posts"]], n=w["supporting_posts"], kind="whatif")
        c.say(f"Changing {w['label'].lower()} ({w['change']}) is estimated at {w['estimated_change_pct']:+.1f}% based on {w['supporting_posts']} past posts. Worth an experiment rather than a guaranteed gain.", [wid], "weak")
    sim = (r.get("similar") or {}).get("summary")
    if sim:
        sid = c.ev("Similar past posts", f"Median engagement of the {sim['k']} most similar posts: {_pct(sim['median_engagement_rate'], 2)} (range {_pct(sim['min_engagement_rate'], 2)} to {_pct(sim['max_engagement_rate'], 2)}); "
                   f"median {sim['median_vs_platform_median_pct']:+.0f}% vs platform median.",
                   [sim["k"], sim["median_engagement_rate"] * 100, sim["min_engagement_rate"] * 100, sim["max_engagement_rate"] * 100, sim["median_vs_platform_median_pct"]], n=sim["k"], kind="similar")
        c.say(f"The {sim['k']} most similar past posts had a median engagement of {_pct(sim['median_engagement_rate'], 2)} (range {_pct(sim['min_engagement_rate'], 2)} to {_pct(sim['max_engagement_rate'], 2)}); a small sample, useful as a sanity check.", [sid], "weak")
    return c.evidence, c.statements


def experiment_evidence(e: dict) -> tuple[list[Evidence], list[Statement]]:
    c = Collector()
    a = e["analysis"]
    cts = a["counts"]
    cid = c.ev("Sample sizes", f"Posts per variant: {', '.join(f'{k}={v}' for k, v in cts.items())}; minimum required {a['min_per_variant']}.", [*cts.values(), a["min_per_variant"]], kind="sample")
    if a["verdict"] == "insufficient_data":
        c.say(f"{a['message']} No conclusion should be drawn yet.", [cid], "weak")
        return c.evidence, c.statements
    for cmp_ in a["comparisons"]:
        if not cmp_.get("testable"):
            continue
        ci = cmp_["ci95_diff_pp"]
        eid = c.ev(f"{cmp_['variant']} vs {cmp_['control']}",
                   f"Mean engagement {_pct(cmp_['mean_variant'], 2)} vs {_pct(cmp_['mean_control'], 2)}; difference {cmp_['diff_pp']:+.2f} pp (95% bootstrap interval {ci[0]:+.2f} to {ci[1]:+.2f}); "
                   f"Welch p adjusted={cmp_['welch_p_adjusted']:.3f}; smallest reliably detectable difference ≈{cmp_['min_detectable_diff_pp']:.2f} pp; n={cmp_['n_variant']} vs {cmp_['n_control']}.",
                   [cmp_["mean_variant"] * 100, cmp_["mean_control"] * 100, cmp_["diff_pp"], ci[0], ci[1], cmp_["welch_p_adjusted"], cmp_["min_detectable_diff_pp"], cmp_["n_variant"], cmp_["n_control"]],
                   n=cmp_["n_variant"] + cmp_["n_control"], kind="comparison")
        if cmp_["significant"]:
            c.say(f"Variant {cmp_['variant']} {'beat' if cmp_['diff_pp'] > 0 else 'trailed'} {cmp_['control']} by {abs(cmp_['diff_pp']):.2f} pp ({_pct(cmp_['mean_variant'], 2)} vs {_pct(cmp_['mean_control'], 2)}); "
                  f"the interval ({ci[0]:+.2f} to {ci[1]:+.2f} pp) excludes zero.", [eid], "strong" if e["randomized"] else "moderate")
        else:
            c.say(f"No reliable difference between {cmp_['variant']} and {cmp_['control']} ({cmp_['diff_pp']:+.2f} pp; interval {ci[0]:+.2f} to {ci[1]:+.2f}). "
                  f"With this sample only differences above about {cmp_['min_detectable_diff_pp']:.2f} pp are reliably detectable, so a smaller effect cannot be excluded.", [eid], "weak")
    rid = c.ev("Design", a["causal_note"], [], kind="design")
    c.say(a["causal_note"], [rid], "moderate")
    pc = a.get("prediction_check")
    if pc:
        pid = c.ev("Prediction check", f"Model predicted best variant {pc['predicted_best']}; observed best {pc['observed_best']}.", [], kind="model")
        c.say(f"Before the test the model favoured variant {pc['predicted_best']}; the observed leader was {pc['observed_best']} "
              f"({'consistent' if pc['direction_matched'] else 'not consistent'} with the model). One experiment is a single data point about model quality.", [pid], "weak")
    return c.evidence, c.statements
