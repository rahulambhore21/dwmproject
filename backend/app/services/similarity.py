"""Similarity search: TF-IDF caption cosine blended with structured-attribute overlap."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from sqlalchemy.orm import Session

from ..warehouse.frames import dataset_hash

TEXT_WEIGHT = 0.7
ATTRS = ["platform", "format", "topic", "hook", "tone"]
MIN_POSTS = 15


@dataclass
class _Index:
    digest: str
    vectorizer: TfidfVectorizer
    matrix: object
    frame: pd.DataFrame  # fact frame + caption, row-aligned with matrix


_CACHE: dict[int, _Index] = {}


def _index(session: Session, workspace_id: int, frame: pd.DataFrame) -> _Index | None:
    if len(frame) < MIN_POSTS:
        return None
    digest = dataset_hash(frame)
    cached = _CACHE.get(workspace_id)
    if cached and cached.digest == digest:
        return cached
    fr = frame.reset_index(drop=True)
    vec = TfidfVectorizer(stop_words="english", ngram_range=(1, 2), min_df=2, sublinear_tf=True, strip_accents="unicode")
    mat = vec.fit_transform(fr["caption"].fillna(""))
    _CACHE[workspace_id] = _Index(digest, vec, mat, fr)
    return _CACHE[workspace_id]


def find_similar(session: Session, workspace_id: int, frame: pd.DataFrame, *, caption: str, attrs: dict[str, str],
                 k: int = 5, exclude_post_id: int | None = None) -> dict:
    idx = _index(session, workspace_id, frame)
    if idx is None:
        return {"status": "insufficient_data", "message": f"Need at least {MIN_POSTS} posts for similarity search.",
                "neighbors": [], "summary": None}
    fr = idx.frame
    q_vec = idx.vectorizer.transform([caption or ""])
    text_sim = cosine_similarity(q_vec, idx.matrix).ravel()
    attr_sim = np.mean([(fr[a] == attrs[a]).to_numpy(dtype=float) for a in ATTRS if a in attrs], axis=0) if attrs else 0
    score = TEXT_WEIGHT * text_sim + (1 - TEXT_WEIGHT) * attr_sim
    if exclude_post_id is not None:
        score = np.where(fr["post_id"].to_numpy() == exclude_post_id, -1, score)
    order = np.argsort(-score, kind="stable")[:k]
    plat_median = fr.groupby("platform")["engagement_rate"].median()
    neighbors = []
    for i in order:
        r = fr.iloc[int(i)]
        pm = float(plat_median[r["platform"]])
        neighbors.append({
            "post_id": int(r["post_id"]), "similarity": float(score[i]), "text_similarity": float(text_sim[i]),
            "platform": r["platform"], "format": r["format"], "topic": r["topic"], "hook": r["hook"], "tone": r["tone"],
            "published_at": r["published_at"].isoformat(), "caption_preview": (r["caption"] or "")[:140],
            "engagement_rate": float(r["engagement_rate"]), "vs_platform_median_pct": float((r["engagement_rate"] / pm - 1) * 100),
            "shared_attributes": [a for a in ATTRS if attrs.get(a) == r[a]],
        })
    ers = [n["engagement_rate"] for n in neighbors]
    rel = [n["vs_platform_median_pct"] for n in neighbors]
    summary = None
    if neighbors:
        summary = {
            "k": len(neighbors), "median_engagement_rate": float(np.median(ers)), "min_engagement_rate": float(min(ers)),
            "max_engagement_rate": float(max(ers)), "median_vs_platform_median_pct": float(np.median(rel)),
        }
    return {"status": "ok", "message": None, "neighbors": neighbors, "summary": summary}
