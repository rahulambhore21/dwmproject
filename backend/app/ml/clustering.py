"""K-Means (post archetypes) and Agglomerative (content-segment families).

Both are *descriptive*: they use post-publication performance to group history.
They are never used as inputs to the pre-publication prediction models.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.cluster import AgglomerativeClustering, KMeans
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import StandardScaler

from .common import SEED, ModelOutcome

EPS = 1e-5
PROFILE = {
    "log_er": "engagement rate", "log_save": "save rate", "log_share": "share rate",
    "log_comment": "comment rate", "log_impr": "impressions",
}
DOMINANT_NAME = {
    "log_er": "High resonance", "log_save": "Reference-worthy", "log_share": "Shareable",
    "log_comment": "Conversation starters", "log_impr": "Broad reach",
}


def _profile_frame(df: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame({
        "log_er": np.log(df["engagement_rate"] + EPS), "log_save": np.log(df["save_rate"] + EPS),
        "log_share": np.log(df["share_rate"] + EPS), "log_comment": np.log(df["comment_rate"] + EPS),
        "log_impr": np.log(df["impressions"]),
    })


def _name_clusters(centroids_z: np.ndarray, cols: list[str]) -> list[str]:
    names: list[str] = []
    for z in centroids_z:
        j = int(np.argmax(z))
        if z[j] < 0.35:
            name = "Quiet" if z.mean() < -0.25 else "Steady baseline"
        else:
            name = DOMINANT_NAME[cols[j]]
        names.append(name)
    seen: dict[str, int] = {}
    out = []
    for n in names:
        seen[n] = seen.get(n, 0) + 1
        out.append(n if seen[n] == 1 else f"{n} {'I' * seen[n]}")
    return out


def _overindex(sub: pd.DataFrame, full: pd.DataFrame, dims=("platform", "format", "hook", "topic")) -> list[dict]:
    out = []
    for d in dims:
        share_in = sub[d].value_counts(normalize=True)
        share_all = full[d].value_counts(normalize=True)
        for level, s in share_in.items():
            lift = s / share_all[level]
            if lift >= 1.3 and (sub[d] == level).sum() >= 8:
                out.append({"dimension": d, "level": level, "share_in_cluster": float(s),
                            "share_overall": float(share_all[level]), "over_index": float(lift)})
    return sorted(out, key=lambda r: -r["over_index"])[:4]


def kmeans_archetypes(df: pd.DataFrame) -> ModelOutcome:
    prof = _profile_frame(df)
    cols = list(prof.columns)
    Z = StandardScaler().fit_transform(prof)
    scores = {}
    for k in range(3, 7):
        labels = KMeans(n_clusters=k, n_init=10, random_state=SEED).fit_predict(Z)
        scores[k] = float(silhouette_score(Z, labels))
    best_k = max(scores, key=lambda k: (round(scores[k], 4), -k))
    km = KMeans(n_clusters=best_k, n_init=10, random_state=SEED).fit(Z)
    names = _name_clusters(km.cluster_centers_, cols)
    clusters = []
    for c in range(best_k):
        mask = km.labels_ == c
        sub = df[mask]
        clusters.append({
            "id": c, "name": names[c], "n": int(mask.sum()), "share": float(mask.mean()),
            "centroid_z": {col: float(km.cluster_centers_[c][i]) for i, col in enumerate(cols)},
            "mean_engagement_rate": float(sub["engagement_rate"].mean()),
            "mean_save_rate": float(sub["save_rate"].mean()), "mean_share_rate": float(sub["share_rate"].mean()),
            "mean_comment_rate": float(sub["comment_rate"].mean()), "median_impressions": float(sub["impressions"].median()),
            "over_indexed": _overindex(sub, df),
        })
    clusters.sort(key=lambda c: -c["mean_engagement_rate"])
    return ModelOutcome(
        "kmeans", "clustering", None, list(PROFILE), {"k_candidates": [3, 4, 5, 6], "selected_k": best_k, "seed": SEED},
        {"silhouette": scores[best_k], "silhouette_by_k": {str(k): v for k, v in scores.items()},
         "inertia": float(km.inertia_), "n_posts": len(df)},
        {"clusters": clusters, "labels": {int(p): int(lab) for p, lab in zip(df["post_id"], km.labels_, strict=True)},
         "profile_columns": cols, "note": "Archetypes group posts by how they performed (post-publication). Descriptive only."},
        len(df), 0,
    )


def agglomerative_segments(df: pd.DataFrame, min_posts: int = 6) -> ModelOutcome:
    prof = _profile_frame(df)
    cols = ["log_er", "log_save", "log_share", "log_comment"]
    rel = prof[cols] - prof[cols].groupby(df["platform"]).transform("mean")  # platform-relative performance
    rel[["platform", "format", "topic"]] = df[["platform", "format", "topic"]].to_numpy()
    seg = rel.groupby(["platform", "format", "topic"]).agg(**{c: (c, "mean") for c in cols}, n=("log_er", "size")).reset_index()
    seg = seg[seg["n"] >= min_posts].reset_index(drop=True)
    if len(seg) < 8:
        return ModelOutcome("agglomerative", "clustering", None, cols, {"min_posts": min_posts}, {}, {},
                            len(df), 0, status="insufficient_data",
                            message=f"Only {len(seg)} segments have >= {min_posts} posts; need at least 8.")
    Z = StandardScaler().fit_transform(seg[cols])
    scores = {}
    for k in range(2, 6):
        scores[k] = float(silhouette_score(Z, AgglomerativeClustering(n_clusters=k, linkage="ward").fit_predict(Z)))
    best_k = max(scores, key=lambda k: (round(scores[k], 4), -k))
    labels = AgglomerativeClustering(n_clusters=best_k, linkage="ward").fit_predict(Z)
    seg["cluster"] = labels
    centroids = np.vstack([Z[labels == c].mean(axis=0) for c in range(best_k)])
    names = _name_clusters(centroids, cols)
    families = []
    for c in range(best_k):
        sub = seg[seg["cluster"] == c].sort_values("log_er", ascending=False)
        families.append({
            "id": c, "name": names[c], "n_segments": int(len(sub)), "n_posts": int(sub["n"].sum()),
            "mean_relative_er_pct": float(np.expm1(sub["log_er"].mean()) * 100),
            "members": [{"platform": r.platform, "format": r.format, "topic": r.topic, "n": int(r.n),
                         "relative_er_pct": float(np.expm1(r.log_er) * 100)} for r in sub.itertuples()][:12],
        })
    families.sort(key=lambda f: -f["mean_relative_er_pct"])
    return ModelOutcome(
        "agglomerative", "clustering", None, cols,
        {"linkage": "ward", "selected_k": best_k, "min_posts_per_segment": min_posts},
        {"silhouette": scores[best_k], "silhouette_by_k": {str(k): v for k, v in scores.items()}, "n_segments": int(len(seg))},
        {"families": families, "note": "Segments = platform x format x topic with enough posts; performance is relative to each platform's average."},
        len(df), 0,
    )
