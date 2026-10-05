# SIGNAL

**Every post becomes data for the next decision.**

SIGNAL is a content intelligence & experimentation engine. It reads a workspace's post history through a dimensional warehouse and eight stored models, scores drafts *before* they ship, runs proper A/B experiments, and keeps what the evidence supports.

```
UNDERSTAND  →  DECIDE  →  EXPERIMENT  →  LEARN
Overview · Memory · Autopsy   Pre-Publish Lab   Experiments   Learning        (+ Explore)
```

The demo workspace is a fictional brand ("Northwind Studio") with 720 synthetic posts over ~18 months across Instagram, LinkedIn, TikTok and X. The data comes from a seeded simulator with hidden effects plus noise. The analytics never see those effects: they have to rediscover them, so every number on screen is computed, none is hard-coded.

## Run it

Requires **Node ≥ 20** and **Python ≥ 3.10**.

```bash
npm install     # installs the frontend and creates backend/.venv (first run: a few minutes)
npm run dev     # API on :8000, web on :3000
```

Open <http://localhost:3000>. The first boot seeds the demo workspace, builds the warehouse and trains the models (~15 s); the UI waits for it automatically. API docs: <http://localhost:8000/docs>.

| Command | What it does |
|---|---|
| `npm run dev` | FastAPI (reload) + Next.js dev server |
| `npm run seed` | Drop and rebuild the demo workspace |
| `npm run test` | Backend (pytest) + frontend (Vitest) |
| `npm run test:e2e` | Playwright against the real stack and a throwaway database |
| `npm run lint` · `npm run typecheck` | ruff + eslint · mypy + tsc |
| `npm run build` · `npm start` | Production build · run it |
| `npm run verify` | Everything above, in order, plus a from-scratch seed |

### Docker

```bash
docker compose up --build      # Postgres + API + web on http://localhost:3000
```

### Deploy

| Piece | Target | Notes |
|---|---|---|
| Database | **Neon** (or Railway Postgres) | `DATABASE_URL=postgresql://…` (`postgres://` is normalised to the psycopg3 driver) |
| API | **Railway** | Root dir `backend/`, uses `Dockerfile` + `railway.json`; health check `/api/health`. Set `DATABASE_URL`, `CORS_ORIGINS`, optionally `OPENAI_API_KEY` |
| Web | **Vercel** | Root dir `frontend/`. Set `BACKEND_URL` to the API's public URL **before building**: Next.js bakes rewrites at build time |

The browser only talks to the web origin; `/api/*` is proxied to FastAPI, so there is no CORS surface in production. Details in [`.env.example`](.env.example).

## What's inside

| Layer | Implementation |
|---|---|
| **ETL** | Row-level Pydantic validation (non-negative counts, reach ≤ impressions, engagements ≤ impressions, no future dates), dedupe, per-run report of every rejection. CSV import endpoint + UI |
| **Warehouse** | Star schema: `fact_post` + `dim_date/platform/format/topic/hook/tone/daypart`, rebuilt idempotently from staging |
| **OLAP** | Roll-up (subtotals), drill-down, slice, dice, pivot. Whitelisted dimensions/measures, per-cell *n* and 95% intervals, low-sample flags |
| **Regression** | Simple (scipy) and multiple linear regression on log engagement rate; OLS standard errors and p-values; chronological holdout + time-series CV; **within-platform R²** reported next to raw R² |
| **Mutual information** | Against platform-adjusted performance, with a label-shuffle **noise floor** |
| **Classifiers** | Decision tree (readable rules, train vs holdout hit-rate) and Gaussian Naive Bayes (sigmoid-calibrated) for "top quartile of its platform" |
| **Clustering** | K-Means post archetypes; Agglomerative (Ward) families of platform × format × topic segments; k chosen by silhouette |
| **Apriori** | mlxtend itemsets → rules; Fisher exact test + Benjamini–Hochberg correction; reported separately for top and bottom quartile |
| **Similarity** | TF-IDF caption cosine blended with attribute overlap |
| **Prediction** | Pre-publication features only, 80% range from out-of-sample residuals, per-feature contributions, history-supported "what-if" swaps |
| **Experiments** | Welch t, Mann-Whitney, bootstrap CI on the difference, Cohen's d, Bonferroni across variants, minimum detectable effect, minimum-n gate, randomised/not-randomised wording, prediction-vs-outcome check, auto-written learning |
| **AI layer** | Interprets structured evidence only. Optional OpenAI model (set `OPENAI_API_KEY`); output is validated (cited evidence ids, no invented numbers, no causal language) or replaced by the deterministic reading |

Every training run is stored in `model_runs` (algorithm, features, params, metrics, results, data hash, timestamp). Re-training on unchanged data is a no-op; forced re-training reproduces the same metrics.

## Honesty rules the code enforces

- **No leakage.** `likes, comments, shares, saves, reach, impressions` and every derived rate are blocked from predictive features by `assert_no_leakage`, and tests cover it. Splits are chronological; the top-quartile threshold comes from the training period only.
- **Correlation ≠ causation.** Patterns are labelled associations. Only an experiment flagged *randomised* is described as supporting a causal reading.
- **Metrics are real, including bad ones.** If a model barely beats baseline, the UI says so (baseline R², majority-class accuracy, noise floors).
- **Insufficient data is a state, not an error.** Below 80 posts, models are stored as `insufficient_data` and the UI explains why; experiments refuse a verdict until every variant has enough posts.

## Layout

```
backend/   FastAPI · SQLAlchemy · pandas/scikit-learn/mlxtend   (app/{etl,warehouse,olap,ml,services,routers,seed})
frontend/  Next.js 16 · Tailwind 4 · Recharts · Framer Motion   (app/, components/, lib/, e2e/)
scripts/   cross-platform dev / setup / verify orchestration
docs/ARCHITECTURE.md
```

Architecture, data model, API list and decisions: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Known limits

- SQLite is the zero-config default; Postgres is supported through `DATABASE_URL` (schema is portable SQLAlchemy). Drizzle is not used: the frontend never touches the database, so a second schema owner would only add drift.
- Single workspace per deployment (no auth). The data model carries `workspace_id` throughout, so multi-tenancy is an additive change.
- Demo data is synthetic. Real data will show weaker, messier signal, which is what the uncertainty reporting is for.
