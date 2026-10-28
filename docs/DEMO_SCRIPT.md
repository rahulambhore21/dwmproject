# SIGNAL: Demo Script

A page-by-page walkthrough: **what to say**, **what to click**, and **why it is designed that way**.
Total time ≈ 10 minutes. Start at `http://localhost:3000` with the demo workspace loaded (720 posts).

> One-line pitch: *"Every post becomes data for the next decision."*
> The product loop: **Understand → Decide → Experiment → Learn.** The navigation numbers (01–07) follow it.

---

## 0. Opening (30 s)

**Say:** "Social teams publish constantly but rarely learn from it. SIGNAL turns post history into a warehouse,
mines it, lets you score a draft *before* publishing, and then closes the loop by testing the change properly."

**Design significance of the shell (applies to every page)**

| Choice | Why |
|---|---|
| Warm paper background, black type, one lime accent | An editorial "intelligence brief", not a BI template. Lime is used only for the thing that matters (primary action, a winner). If everything is highlighted nothing is. |
| Thin 1px borders, no shadows, square corners | Structure comes from rules and whitespace, like print. It keeps dense data calm. |
| Serif display headings + monospace numerals | Headlines read as editorial voice; tabular monospace numbers align in tables and look like measurements. |
| Numbered nav (`01 · Understand` … `07 · Inspect`) | The nav *is* the product loop, so a new user learns the workflow without a tutorial. |
| Every number carries its sample size, interval or caveat | The product never claims more certainty than the data gives. This is the trust principle behind the whole UI. |
| Every async view has loading, empty, error and "not enough data" states | A real product degrades gracefully; it never shows a blank or fake chart. |

---

## 1. Overview: *Understand* (1 min)  `/`

**Click path:** read the headline → KPI strip → click platform chips → "Try in Lab".

**Say:** "This is the state of the account in one screen: how many posts, average engagement, and how the last
30 days compare to the 30 before. The trend chart has a dashed line for the all-time average, and I can switch
platform because platforms have different baselines. Comparing Instagram to LinkedIn directly would be misleading."

- **Loop strip** (Understand / Decide / Experiment / Learn): makes the workflow obvious from the first screen.
- **Trend chart + dashed baseline:** a trend is only meaningful against a reference line.
- **"What the history says"** (Apriori rules): each card shows hit-rate vs baseline; **Try in Lab** turns an insight into an action. Insight is never a dead end.
- **Interpret this:** the AI layer only *reads* evidence the deterministic analytics produced (labelled E1, E2…). Click an `E#` chip to see the exact evidence behind a sentence. It cannot invent numbers, and it uses hedged language ("associated with", not "causes").

**Significance:** the first page proves two things: data is live, and language is honest.

---

## 2. Content Memory + Autopsy: *Understand* (1.5 min)  `/memory`, `/memory/[id]`

**Click path:** archetype cards → filter by Platform → Topic → type in search → change Sort / ↓ Desc → Next page → open a post.

**Say:** "Memory is every post, with how it did *against its own platform's median*. The ‘vs median’ pill is the
key column: +40% means 40% above what is normal for that platform. The archetypes at the top come from K-Means:
it groups posts by *how they performed*, so we see distinct ways a post can win, such as Shareable or Reference-worthy."

- **Filters** (platform → format are dependent; changing platform clears a stale format; any filter change returns to page 1) prevent impossible combinations.
- **Clear filters** in the empty state: dead ends always offer a way out.
- **Autopsy** (click a post): *Against the benchmark* (percentile and index), *What history associates with these choices* (model terms, not causes), *Did the model see it coming* (prediction vs actual, a check on the model itself), **Iterate in the Lab** (carries the post into the next step).

**Significance:** "performance vs platform median" removes the biggest confounder (platform), and the autopsy
frames every explanation as association, never causation.

---

## 3. Pre-Publish Lab: *Decide* (2 min)  `/lab`

**Click path:** change Platform, Hook, Tone, Format → edit caption → clear the caption (validation) → **Test it** → Cancel → **Test it** → Create experiment.

**Say:** "This is the decision step. I describe a draft *before* it is published and SIGNAL estimates its engagement
rate and the chance it lands in the platform's top quartile. Notice I only give it things I know before posting:
platform, format, topic, hook, tone, time, caption length, hashtags. It is *not allowed* to look at likes, comments,
reach or impressions. That would be target leakage: the model would look accurate and be useless."

- **Estimated rate + range:** a range, not a single number, because a point estimate hides uncertainty.
- **Similarity search** section (TF-IDF cosine similarity): concrete precedents are easier to trust than a score.
- **Changes worth testing** (what-if): the model proposes single-attribute changes with predicted effect. **Test it** opens a dialog that stores the model's prediction with the experiment so we can later check whether the model was right.
- **"I will randomise" checkbox:** only randomised assignment lets a difference be read as caused by the change; the product asks you to state it.
- **Validation:** an empty caption shows a clear message; nothing silently scores garbage.

**Significance:** the chain *prediction → experiment → verification* is what separates SIGNAL from a dashboard.

---

## 4. Experiments: *Experiment* (1.5 min)  `/experiments`, `/experiments/[id]`

**Click path:** **New experiment** (leave fields empty to show the "To create: add…" hint) → fill → Create → on a detail page, log a post → show the disabled **Conclude** and its reason.

**Say:** "An experiment is one control (A) and one variant (B): change one thing. I log each post's impressions and
engagements as results arrive. Until each variant has enough posts the verdict says *Collecting data*, and the
Conclude button tells me exactly why it's unavailable instead of just being greyed out."

- **Interval plot:** each dot is one post, and the bar is the mean with its interval. You see spread, not just an average.
- **The comparison:** Welch's t-test (Bonferroni-adjusted), Mann-Whitney as a distribution-free cross-check, a bootstrap 95% interval, Cohen's d, and the minimum detectable difference. Several lenses agreeing is the evidence.
- **Verdict** is one of *Adopt variant / Keep control / Inconclusive / Collecting data*; a winner is declared only when the interval excludes zero.
- **Causal note:** randomised → "can reasonably be attributed"; not randomised → "other differences may explain part of the gap".
- **Log form validation:** engagements can't exceed impressions; the Add button explains what's missing.

**Significance:** statistical honesty is a design feature. The UI withholds a verdict rather than guess.

---

## 5. Learning: *Learn* (30 s)  `/learning`

**Say:** "When an experiment is concluded, SIGNAL records a plain-English learning with its verdict and evidence.
It becomes institutional memory: a timeline of what the team has proven, and what was inconclusive."

- A vertical ruled timeline; lime marker only for *adopted* learnings. Inconclusive results are kept too, so the team doesn't repeat failed tests.

**Significance:** this closes the loop. Learnings feed the next round of Understand → Decide.

---

## 6. Explore: *Analyse* (2 min)  `/explore`

**Tab 1: OLAP pivot.** Pick Rows → add a drill-down level → set Pivot columns → change Cell measure → slice with the Platform/Format/Topic/Hook/Tone filters → toggle **Subtotals (roll-up)** → open **Show the SQL for this view**.

**Say:** "This is the data warehouse in use: roll-up, drill-down, slice, dice and pivot over a star schema.
Every cell shows its sample size, and a † marks cells under 8 posts; read those as anecdotes. Rates are per-post means,
so one viral post can't dominate a cell."

**Tab 2: Drivers.** "Which attributes carry signal?" Mutual information ranks attributes against a *noise floor* built by shuffling the target 20 times, and Apriori rules are corrected for multiple testing (Benjamini-Hochberg). Mining many rules guarantees some look good by chance; the correction is what makes survivors credible.

**Tab 3: Segments.** K-Means archetypes (per post) and Agglomerative families (per platform × format × topic): descriptive grouping of what worked.

**Tab 4: Models & data.** The model registry: every run's parameters, metrics and train/test sizes are stored. **Retrain all (force)** re-runs everything deterministically (seed 42, chronological split: same data in, same metrics out). Below is **Bring your own data**: choose a CSV, confirm the column mapping, preview, then Append or Replace. Rejected rows are reported with a reason; nothing is silently imputed.

**Significance:** the controls are real filters wired to the warehouse, not decoration, and every algorithm result is stored and reproducible.

---

## 7. Methods: *Inspect* (1.5 min)  `/methods`  ← new

**Click path:** jump chips (Warehouse & ETL / OLAP queries / Algorithms) → read the star schema → click through **Roll-up, Drill-down, Slice, Dice, Pivot, Roll-up with subtotals** → **Copy** the SQL → filter algorithms **Predictive / Descriptive / …** → open **View source** on Decision tree.

**Say:** "For the DWM examiner: this page shows how every algorithm is implemented. The star schema is read from the
database models. Each OLAP operation shows the SQL a warehouse engine would run, the request we send our engine, and the
*live result* on your data. For each algorithm: the steps, why it was chosen, its guardrails, the metrics from its
latest stored run, and the actual source code."

- **Nothing is hand-copied.** Source listings come from the running modules; metrics come from the model registry; OLAP examples are executed live. If the code changes, the page changes, so documentation can't drift.
- **SQL honesty:** the engine runs the same grouping in pandas over the joined fact frame; the SQL is generated from the *same query object*, and a test runs it on the database and checks it matches the engine's numbers.
- Every algorithm card links to where it's used in the product, so theory connects to experience.

**Algorithm cheat-sheet (DWM syllabus mapping)**

| Topic | Where in SIGNAL | One-line answer |
|---|---|---|
| ETL | Methods → ETL | Pydantic validation, counted rejections, no imputation |
| Dimensional warehouse | Methods → Star schema | `fact_post` + 7 dimensions, one row per post |
| OLAP | Explore → pivot; Methods | Roll-up, drill-down, slice, dice, pivot, subtotals |
| Linear regression | Drivers | Caption length → log engagement, vs a mean baseline |
| Multiple linear regression | Lab / Drivers | All pre-publication features; coefficients with p-values |
| Mutual information | Drivers | Non-linear dependence, with a shuffled-target noise floor |
| Decision tree | Lab | Depth-4 readable rules, confirmed on held-out posts |
| Gaussian Naive Bayes | Lab | Calibrated probability of a top-quartile post |
| K-Means | Memory / Segments | Post archetypes; k chosen by silhouette |
| Agglomerative | Segments | Ward linkage over content segments |
| Apriori | Overview / Drivers | Frequent itemsets → rules, Fisher + BH correction |
| Similarity search | Lab | TF-IDF cosine blended with attribute overlap |
| Experiment comparison | Experiments | Welch, Mann-Whitney, bootstrap CI, Cohen's d |

---

## 8. Closing (30 s)

**Say:** "Three things make this a product and not a demo. It's *honest*: every number has its sample size, models can't
see post-publication data, and AI only interprets evidence. It's *closed-loop*: insight leads to a prediction, a
prediction to an experiment, and the result to a stored learning. And it's *inspectable*: the Methods page shows the
SQL, the code and the metrics behind every claim."

---

## Likely questions

- **Why not just correlate likes with features?** Likes are known only after publishing, so using them leaks the answer. The code raises an error if a post-publication field is used as a feature.
- **Is the data real?** Realistic *synthetic* demo data, deterministic from a seed. Use **Explore → Models & data → Bring your own data** for a real export.
- **Does the AI make things up?** It receives structured evidence only, must cite evidence ids, and falls back to a deterministic reading when no LLM key is configured.
- **Why is a button disabled?** The page says why: not enough posts per variant, a missing field, or an invalid value.
- **Why are model R² values modest?** Pre-publication features explain only part of performance. The page reports the baseline next to each metric so you can see the lift honestly.
