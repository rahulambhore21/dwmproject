"""Linear and multiple linear regression on log engagement rate (pre-publication features only)."""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats
from sklearn.linear_model import LinearRegression
from sklearn.model_selection import TimeSeriesSplit
from sklearn.pipeline import Pipeline

from .common import (
    CATEGORICAL,
    FEATURE_LABELS,
    NUMERIC,
    PRE_PUBLICATION_FEATURES,
    SEED,
    ModelOutcome,
    assert_no_leakage,
    chrono_split,
    preprocessor,
    regression_metrics,
    term_group,
)


def simple_linear_regression(df: pd.DataFrame) -> ModelOutcome:
    """Caption length (characters) -> log engagement rate, scipy OLS with test-set validation."""
    assert_no_leakage(["caption_length"])
    train, test = chrono_split(df)
    fit = stats.linregress(train["caption_length"], train["log_er"])
    pred = fit.intercept + fit.slope * test["caption_length"]
    m = regression_metrics(test["log_er"], pred)
    baseline = regression_metrics(test["log_er"], np.full(len(test), train["log_er"].mean()))
    t = stats.t.ppf(0.975, len(train) - 2)
    per100 = fit.slope * 100
    results = {
        "predictor": "caption_length",
        "slope_per_char": float(fit.slope),
        "intercept": float(fit.intercept),
        "pearson_r": float(fit.rvalue),
        "p_value": float(fit.pvalue),
        "slope_ci_95": [float(fit.slope - t * fit.stderr), float(fit.slope + t * fit.stderr)],
        "pct_change_per_100_chars": float(np.expm1(per100) * 100),
        "train_r2": float(fit.rvalue**2),
        "interpretation_note": (
            "A single straight line cannot capture an optimum-length curve and ignores platform mix; "
            "treat this as a descriptive baseline, not a recommendation."
        ),
        "scatter": [
            {"x": int(x), "y": float(np.exp(y))}
            for x, y in zip(df["caption_length"].iloc[:: max(len(df) // 250, 1)],
                            df["log_er"].iloc[:: max(len(df) // 250, 1)], strict=True)
        ],
    }
    return ModelOutcome(
        "linear_regression", "regression", "log_engagement_rate", ["caption_length"], {"solver": "scipy.linregress"},
        {**m, "baseline_r2": baseline["r2"], "pearson_r": float(fit.rvalue), "p_value": float(fit.pvalue)},
        results, len(train), len(test),
    )


def _ols_inference(X: np.ndarray, y: np.ndarray, coef: np.ndarray, intercept: float) -> tuple[np.ndarray, np.ndarray]:
    n, p = X.shape
    Xd = np.column_stack([np.ones(n), X])
    beta = np.concatenate([[intercept], coef])
    resid = y - Xd @ beta
    dof = max(n - Xd.shape[1], 1)
    sigma2 = float(resid @ resid) / dof
    cov = sigma2 * np.linalg.pinv(Xd.T @ Xd)
    se = np.sqrt(np.clip(np.diag(cov), 0, None))[1:]
    with np.errstate(divide="ignore", invalid="ignore"):
        tvals = np.where(se > 0, coef / se, 0.0)
    pvals = 2 * (1 - stats.t.cdf(np.abs(tvals), dof))
    return se, pvals


def multiple_linear_regression(df: pd.DataFrame) -> ModelOutcome:
    assert_no_leakage(PRE_PUBLICATION_FEATURES)
    train, test = chrono_split(df)
    pipe = Pipeline([("prep", preprocessor(scale=True, drop_first=True)), ("lr", LinearRegression())])
    X_tr, y_tr = train[PRE_PUBLICATION_FEATURES], train["log_er"].to_numpy()
    pipe.fit(X_tr, y_tr)
    pred_te = pipe.predict(test[PRE_PUBLICATION_FEATURES])
    pred_tr = pipe.predict(X_tr)
    m = regression_metrics(test["log_er"], pred_te)
    base = regression_metrics(test["log_er"], np.full(len(test), y_tr.mean()))

    plat_mean = train.groupby("platform")["log_er"].mean()
    y_adj = test["log_er"] - test["platform"].map(plat_mean)
    p_adj = pred_te - test["platform"].map(plat_mean)
    r2_adjusted = regression_metrics(y_adj, p_adj)["r2"]

    cv_scores = []
    for tr_idx, va_idx in TimeSeriesSplit(n_splits=5).split(df):
        p = Pipeline([("prep", preprocessor(scale=True, drop_first=True)), ("lr", LinearRegression())])
        p.fit(df.iloc[tr_idx][PRE_PUBLICATION_FEATURES], df.iloc[tr_idx]["log_er"])
        va = df.iloc[va_idx]
        cv_scores.append(regression_metrics(va["log_er"], p.predict(va[PRE_PUBLICATION_FEATURES]))["r2"])

    prep = pipe.named_steps["prep"]
    lr = pipe.named_steps["lr"]
    names = list(prep.get_feature_names_out())
    Xt = prep.transform(X_tr)
    se, pvals = _ols_inference(Xt, y_tr, lr.coef_, float(lr.intercept_))
    scaler = prep.named_transformers_["num"]
    scale_by_name = dict(zip(NUMERIC, scaler.scale_, strict=True))
    ref_levels = {
        c: [cat for cat in prep.named_transformers_["cat"].categories_[i]][0] for i, c in enumerate(CATEGORICAL)
    }
    terms = []
    for i, name in enumerate(names):
        group, level = term_group(name)
        terms.append({
            "term": name, "feature": group, "label": FEATURE_LABELS.get(group, group), "level": level or None,
            "coef_log": float(lr.coef_[i]), "multiplier": float(np.exp(lr.coef_[i])),
            "pct_effect": float(np.expm1(lr.coef_[i]) * 100), "std_error": float(se[i]),
            "p_value": float(pvals[i]), "significant": bool(pvals[i] < 0.05),
            "unit": "per 1 SD" if group in NUMERIC else f"vs {ref_levels.get(group)}",
            "sd": float(scale_by_name[group]) if group in NUMERIC else None,
        })
    resid_sd_test = float(np.std(test["log_er"].to_numpy() - pred_te, ddof=1))
    results = {
        "intercept_log": float(lr.intercept_),
        "terms": sorted(terms, key=lambda t: -abs(t["coef_log"])),
        "reference_levels": ref_levels,
        "residual_sd_train": float(np.std(y_tr - pred_tr, ddof=1)),
        "residual_sd_test": resid_sd_test,
        "train_column_means": {n: float(v) for n, v in zip(names, Xt.mean(axis=0), strict=True)},
        "cv_r2_folds": [float(s) for s in cv_scores],
        "note": "Coefficients describe associations in historical data after adjusting for the other features; they are not causal effects.",
    }
    metrics = {
        **m, "baseline_r2": base["r2"], "r2_platform_adjusted": r2_adjusted, "train_r2": regression_metrics(y_tr, pred_tr)["r2"],
        "cv_r2_mean": float(np.mean(cv_scores)), "cv_r2_std": float(np.std(cv_scores)),
        "interval_sd_log": resid_sd_test,
    }
    return ModelOutcome(
        "multiple_linear_regression", "regression", "log_engagement_rate", list(PRE_PUBLICATION_FEATURES),
        {"estimator": "LinearRegression", "split": "chronological 80/20", "seed": SEED}, metrics, results,
        len(train), len(test), artifact={"pipeline": pipe, "feature_names": names, "results": results},
    )
