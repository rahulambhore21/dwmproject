# SIGNAL architecture

## Principle: analytics are code, UI is a view

```
Next.js (React, typed client)  ──/api proxy──▶  FastAPI routers (validation only)
                                                     │
                       ┌─────────────────────────────┼───────────────────────────────┐
                       ▼                             ▼                               ▼
                  services/*                    ml/* , olap/*                   etl/*, warehouse/*
          prediction · experiments ·       trainers, leakage guard,        validate → stage → star schema
          autopsy · overview · AI          OLAP engine (pure functions)
                       └──────────────▶  SQLAlchemy  ◀──────────────────────────────┘
                                         SQLite (default) / PostgreSQL (Neon, Railway)
```

Routers contain no analytics. Services and engines take a DataFrame or a Session and return plain dicts, so they are testable without HTTP. The frontend never computes a statistic; it formats what the API returns.

## Data flow

1. **Ingest** (`etl/pipeline.py`). Records → `RawPostIn` (Pydantic) → rejected rows counted with reasons → duplicates by `(platform, external_id)` skipped → staged in `posts` → `EtlRun` report stored.
2. **Warehouse** (`warehouse/build.py`). Caption features (length, hashtags, emoji, question, CTA) are extracted by one function shared with the Lab (`etl/text.py`), so a draft is featurised exactly like history. Dimensions are upserted; `fact_post` is rebuilt for the workspace.
3. **Frame** (`warehouse/frames.py`). One join of the star schema → analysis DataFrame. `dataset_hash` fingerprints ids and outcomes.
4. **Train** (`ml/pipeline.py`). Eight trainers run; each writes a `ModelRun` (metrics, params, features, results, hash). If the latest run has the same hash, nothing retrains. Joblib artifacts back prediction.
5. **Serve.** Prediction, autopsy, similarity, overview and experiments read the stored runs and the frame.

## Schema

| Group | Tables |
|---|---|
| Staging | `workspaces`, `posts`, `etl_runs` |
| Warehouse | `fact_post`, `dim_date`, `dim_platform`, `dim_format`, `dim_topic`, `dim_hook`, `dim_tone`, `dim_daypart` |
| Intelligence | `model_runs`, `post_labels` (K-Means archetype per post) |
| Experimentation | `experiments`, `experiment_variants`, `experiment_observations`, `learnings` |

`fact_post` splits columns into **pre-publication attributes** (caption length, hashtags, emoji, CTA, question, media count, hour, dimension keys) and **post-publication measures** (impressions, reach, likes, comments, shares, saves, rates).

## Leakage control (`ml/common.py`)

- `PRE_PUBLICATION_FEATURES` is the only feature list a predictive model may use.
- `POST_PUBLICATION` enumerates blocked fields; `assert_no_leakage` raises `LeakageError` for any of them or any unapproved name. Trainers call it before fitting.
- Splits are chronological 80/20 (no shuffling). The "top quartile" label threshold per platform is computed on the training window only.
- Clustering and association mining *do* use post-publication performance, because they describe history. They are labelled descriptive and never feed prediction.

## Statistical choices

| Concern | Choice |
|---|---|
| Platform baselines dominate engagement rate | Targets are platform-relative where content effects matter (MI, classifiers, clustering, rules); regression reports raw **and** within-platform R² |
| Tiny MI values over-read | 20 label shuffles give a 95th-percentile noise floor per feature |
| Rule mining finds spurious rules | Fisher exact p → Benjamini–Hochberg q across all candidates; minimum antecedent size and lift |
| Tree/NB probabilities | Tree uses each leaf's observed (unweighted) training hit rate; GNB is sigmoid-calibrated |
| Prediction intervals | 80% range from the standard deviation of *out-of-sample* residuals on log engagement |
| Few posts per variant | Gate: no verdict below `min_per_variant`; otherwise Welch + Mann-Whitney + bootstrap CI (seeded), Bonferroni across variants, minimum detectable difference reported |
| Causal language | Experiment copy depends on `randomized`; everything else is "associated with" |

## AI interpretation (`services/evidence.py`, `services/ai.py`)

Builders turn deterministic outputs into **evidence items** (`id`, label, text, numbers, n) and a deterministic set of statements composed from those same numbers. If `ANTHROPIC_API_KEY` is set, Claude receives only the evidence and must return JSON statements citing evidence ids. A validator rejects the response if an id is unknown or missing, a number does not appear in the evidence (as value, ×100 or ÷100), or causal/promissory language appears; on rejection (or any API failure) the deterministic reading is returned with `fallback_reason`. The deterministic statements must pass the same validator (tested).

## API (all under `/api`)

| Area | Endpoints |
|---|---|
| Core | `GET /health`, `GET /overview`, `GET /vocabulary` |
| Memory | `GET /posts` (filters, sort, pagination), `GET /posts/{id}/autopsy` |
| Lab | `POST /lab/predict`, `POST /similarity/search` |
| OLAP | `GET /olap/schema`, `POST /olap/query` |
| Models | `GET /models`, `GET /models/{algorithm}`, `POST /models/retrain` |
| Experiments | `GET/POST /experiments`, `GET /experiments/{id}`, `POST /experiments/{id}/observations`, `POST /experiments/{id}/complete`, `GET /learnings` |
| AI | `POST /ai/interpret` (`overview` · `autopsy` · `prediction` · `experiment`) |
| Data | `POST /ingest/csv`, `GET /etl/runs` |

Errors use one envelope: `{"error": {"code", "message", "details?"}}`. Validation failures are 422; unknown resources 404; closed experiments 409; insufficient data 422/409 with an explanatory message.

## Frontend

- App Router; pages are client components over a typed `useApi` hook (loading, error, insufficient and warm-up states; automatic retry while the API seeds).
- Design tokens live in `app/globals.css` (warm paper, ink, one lime accent, serif display + mono numerals). Charts are monochrome with a single highlight; negatives use a restrained alert red, never a rainbow.
- Accessibility: skip link, labelled controls, `aria-live` results, text alternatives for charts, reduced-motion support, keyboard-operable dialogs (Radix).
- `lib/types.ts` mirrors the API contracts; tests cover the client, the hook and shared components; Playwright covers the full flows.

## Testing

| Suite | Count | Covers |
|---|---|---|
| pytest | 50 | ETL rejection/dedupe, star schema integrity, seed determinism, leakage guard, chronological split, model runs stored with metrics, baselines, BH correction, OLAP vs pandas, prediction bounds/determinism, experiments (power, bootstrap reproducibility, lifecycle, validation), AI validator, API contracts, CSV ingest |
| Vitest | 22 | formatters, API client errors, warm-up retry, state components, significance display, interpretation panel |
| Playwright | 11 | every screen against a real, freshly seeded stack, incl. error state, empty state, phone-width overflow, skip link |

## Decisions and trade-offs

- **SQLite by default, Postgres by URL.** Zero-config clone-and-run was a hard requirement; the schema is portable.
- **No Drizzle.** One schema owner (SQLAlchemy) avoids drift because the frontend never queries the database.
- **Models train at the first boot, not per request.** Predictions are cheap and reproducible; runs are auditable in the registry.
- **Deployed model = the 80% training split.** Holdout labels in the autopsy stay truthful ("the model had not seen this post"). A refit on all data would improve accuracy slightly at the cost of that guarantee.
- **Rewrites baked at build time.** Next.js reads `BACKEND_URL` at build; set it before building on Vercel/Docker.
