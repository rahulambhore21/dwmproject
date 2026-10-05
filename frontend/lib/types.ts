// Typed contracts for the SIGNAL API (mirrors backend/app responses).

export type Platform = string;

export interface Health {
  status: "ok" | "empty" | "degraded";
  workspace: string | null;
  posts: number;
  llm_configured: boolean;
  error?: string;
}

export interface Trend {
  window_days: number;
  n_current: number;
  n_previous: number;
  current: number | null;
  previous: number | null;
  delta_pct: number | null;
  p_value: number | null;
}

export interface AprioriRule {
  outcome: "high_performer" | "low_performer";
  antecedents: string[];
  antecedent_labels: string[];
  n_posts: number;
  n_hits: number;
  support: number;
  confidence: number;
  base_rate: number;
  lift: number;
  p_value: number;
  q_value: number;
  significant: boolean;
}

export interface PostCard {
  post_id: number;
  platform: string;
  format: string;
  topic: string;
  hook: string;
  published_at: string;
  engagement_rate: number;
  performance_index: number;
  caption_preview: string;
}

export interface ExperimentSummary {
  id: number;
  name: string;
  hypothesis: string;
  variable: string;
  platform: string;
  metric: string;
  status: "running" | "completed";
  min_per_variant: number;
  randomized: boolean;
  source: string;
  created_at: string;
  completed_at: string | null;
  variants: { id: number; label: string; description: string; is_control: boolean; n: number }[];
  analysis: ExperimentAnalysis;
}

export interface Learning {
  id: number;
  statement: string;
  verdict: "adopt" | "keep_control" | "inconclusive" | string;
  created_at: string;
  experiment_id: number | null;
}

export interface Overview {
  status: "ok" | "empty";
  message: string | null;
  workspace: { id: number; name: string; is_demo: boolean };
  data?: { posts: number; first_post: string; last_post: string; last_etl: string | null };
  kpis?: {
    avg_engagement_rate: number;
    median_impressions: number;
    total_impressions: number;
    trend_30d: Trend;
    trend_90d: Trend;
  };
  trend?: {
    monthly: { month: string; posts: number; engagement_rate: number }[];
    by_platform: Record<string, number | string | null>[];
  };
  platforms?: { platform: string; posts: number; engagement_rate: number; median_impressions: number }[];
  top_posts?: PostCard[];
  bottom_posts?: PostCard[];
  signals?: { working: AprioriRule[]; underperforming: AprioriRule[] };
  suggested_tests?: { title: string; basis: string; antecedents: string[] }[];
  experiments?: { running: number; completed: number; recent: ExperimentSummary[] };
  learnings?: Learning[];
  model_health?: {
    trained: number;
    total: number;
    predictive_ready: boolean;
    runs: {
      algorithm: string;
      status: string;
      message: string | null;
      created_at: string;
      headline: { label: string; value: number } | null;
    }[];
  };
}

export interface PostListItem {
  post_id: number;
  platform: string;
  format: string;
  topic: string;
  hook: string;
  tone: string;
  published_at: string;
  caption_preview: string;
  impressions: number;
  engagements: number;
  engagement_rate: number;
  performance_index: number;
}

export interface PostList {
  total: number;
  page: number;
  page_size: number;
  items: PostListItem[];
}

export interface Vocabulary {
  platforms: Record<string, { formats: { name: string; n: number }[]; n: number; median_engagement_rate: number }>;
  topics: string[];
  hooks: string[];
  tones: string[];
}

export interface SegmentLift {
  n_with: number;
  n_without: number;
  mean_with: number;
  mean_without: number;
  lift_pct: number;
  p_value: number;
}

export interface Contribution {
  feature: string;
  label: string;
  value: string;
  log_effect: number;
  effect_pct: number;
}

export interface Neighbor {
  post_id: number;
  similarity: number;
  text_similarity: number;
  platform: string;
  format: string;
  topic: string;
  hook: string;
  tone: string;
  published_at: string;
  caption_preview: string;
  engagement_rate: number;
  vs_platform_median_pct: number;
  shared_attributes: string[];
}

export interface SimilarResult {
  status: "ok" | "insufficient_data";
  message: string | null;
  neighbors: Neighbor[];
  summary: {
    k: number;
    median_engagement_rate: number;
    min_engagement_rate: number;
    max_engagement_rate: number;
    median_vs_platform_median_pct: number;
  } | null;
}

export interface Autopsy {
  post: {
    id: number;
    external_id: string | null;
    platform: string;
    format: string;
    topic: string;
    hook: string;
    tone: string;
    daypart: string;
    published_at: string;
    caption: string;
    caption_length: number;
    hashtag_count: number;
    emoji_count: number;
    has_cta: boolean;
    has_question: boolean;
    media_count: number;
    metrics: {
      impressions: number;
      reach: number;
      likes: number;
      comments: number;
      shares: number;
      saves: number;
      engagements: number;
      engagement_rate: number;
    };
  };
  benchmark: {
    platform_median_engagement_rate: number;
    platform_n: number;
    platform_percentile: number;
    format_median_engagement_rate: number;
    format_n: number;
    format_percentile: number;
    performance_index: number;
  };
  engagement_mix: { label: string; value: number; platform_median: number; vs_median_pct: number | null }[];
  attribute_evidence: { attribute: string; value: string; evidence: SegmentLift | null }[];
  model_check: {
    predicted_engagement_rate: number;
    actual_engagement_rate: number;
    ratio_actual_to_predicted: number;
    split: "holdout" | "training";
    note: string;
    contributions: Contribution[];
  } | null;
  archetype: { id: number; name: string; share: number; n: number; mean_engagement_rate: number } | null;
  similar: SimilarResult;
  caveat: string;
}

export interface DraftInput {
  platform: string;
  format: string;
  topic: string;
  hook: string;
  tone: string;
  caption: string;
  scheduled_at: string;
}

export interface WhatIf {
  feature: string;
  label: string;
  change: string;
  value: string;
  estimated_change_pct: number;
  supporting_posts: number;
}

export interface PredictionResult {
  status: "ok" | "insufficient_data" | "invalid";
  message: string | null;
  prediction: {
    engagement_rate: number;
    interval_80: [number, number];
    platform_median_engagement_rate: number;
    vs_platform_median_pct: number;
    probability_top_quartile: {
      decision_tree: number | null;
      gaussian_nb: number | null;
      blend: number | null;
      base_rate: number;
    };
    contributions: Contribution[];
    features: Record<string, number>;
  } | null;
  model?: {
    run_id: number;
    algorithm: string;
    trained_at: string;
    n_train: number;
    n_test: number;
    holdout_r2: number;
    r2_platform_adjusted: number | null;
    baseline_r2: number;
  };
  caveats?: string[];
  similar?: SimilarResult | null;
  what_if?: WhatIf[];
}

// ---- OLAP
export interface OlapSchema {
  dimensions: { key: string; label: string }[];
  hierarchies: { name: string; levels: string[] }[];
  measures: { key: string; label: string; is_rate: boolean }[];
}

export interface OlapRow {
  keys: Record<string, string | number | null>;
  level: number;
  posts: number;
  impressions: number;
  engagements: number;
  engagement_rate: number;
  median_engagement_rate: number;
  save_rate: number;
  share_rate: number;
  comment_rate: number;
  avg_impressions: number;
  er_ci_low: number | null;
  er_ci_high: number | null;
  low_sample: boolean;
}

export interface OlapResult {
  status: "ok" | "empty";
  message: string | null;
  rows: OlapRow[];
  totals: Omit<OlapRow, "keys" | "level"> | null;
  pivot: {
    measure: string;
    row_dimensions: string[];
    column_dimension: string;
    column_labels: (string | number)[];
    rows: { keys: Record<string, string | number | null>; cells: ({ value: number | null; posts: number; low_sample: boolean } | null)[] }[];
  } | null;
  n_posts: number;
  low_sample_threshold: number;
  dimensions?: string[];
  measures?: string[];
}

export interface OlapQueryInput {
  rows: string[];
  columns?: string | null;
  measures: string[];
  filters: Record<string, (string | number)[]>;
  rollup?: boolean;
  sort_by?: string | null;
  descending?: boolean;
  limit?: number;
  min_posts?: number;
}

// ---- Models
export interface ModelRunSummary {
  id: number;
  algorithm: string;
  task: string;
  target: string | null;
  status: "ok" | "insufficient_data" | "failed";
  message: string | null;
  metrics: Record<string, number | null | Record<string, number>>;
  params: Record<string, unknown>;
  features: string[];
  n_train: number;
  n_test: number;
  dataset_hash: string;
  created_at: string;
}

export interface ModelRunFull extends ModelRunSummary {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  results: Record<string, any>;
}

export interface ModelList {
  algorithms: string[];
  runs: ModelRunSummary[];
  total_runs_stored: number;
}

// ---- Experiments
export interface Comparison {
  control: string;
  variant: string;
  n_control: number;
  n_variant: number;
  testable: boolean;
  mean_control?: number;
  mean_variant?: number;
  diff_pp?: number;
  relative_lift_pct?: number | null;
  ci95_diff_pp?: [number, number];
  welch_p?: number;
  welch_p_adjusted?: number;
  mann_whitney_p?: number | null;
  cohens_d?: number | null;
  min_detectable_diff_pp?: number;
  significant?: boolean;
}

export interface ExperimentAnalysis {
  verdict: "adopt" | "keep_control" | "inconclusive" | "insufficient_data";
  winner: string | null;
  message: string | null;
  counts: Record<string, number>;
  min_per_variant: number;
  comparisons: Comparison[];
  randomized: boolean;
  causal_note: string;
  variant_summaries: { label: string; description: string; is_control: boolean; n: number; mean_engagement_rate: number | null; impressions: number }[];
  prediction_check?: {
    rows: { label: string; predicted: number; observed: number }[];
    predicted_best: string;
    observed_best: string;
    direction_matched: boolean;
    note: string;
  } | null;
}

export interface ExperimentDetail extends ExperimentSummary {
  prediction_snapshot: { predicted_engagement_rate?: Record<string, number> } | null;
  observations: {
    id: number;
    variant_id: number;
    variant_label: string;
    published_at: string;
    impressions: number;
    engagements: number;
    saves: number;
    engagement_rate: number;
  }[];
}

export interface ExperimentInput {
  name: string;
  hypothesis: string;
  variable: string;
  platform: string;
  variants: { label: string; description: string; is_control: boolean }[];
  min_per_variant: number;
  randomized: boolean;
  source?: string;
  prediction_snapshot?: Record<string, unknown> | null;
}

// ---- AI
export interface Interpretation {
  scope: string;
  source: "deterministic" | "llm";
  model?: string;
  statements: { text: string; evidence_ids: string[]; strength: "weak" | "moderate" | "strong" }[];
  caveats: string[];
  evidence: { id: string; label: string; text: string; n: number | null; kind: string }[];
  disclaimer: string;
  fallback_reason: string | null;
}

export interface EtlReport {
  rows_in: number;
  rows_valid: number;
  rows_loaded: number;
  rows_rejected: number;
  duplicates_skipped: number;
  rejection_reasons: Record<string, number>;
  rejection_examples: { row: number; reason: string }[];
  warehouse: { fact_rows: number; dimensions: Record<string, number> };
  mode?: "append" | "replace";
  defaulted_fields?: string[];
}

export interface CsvPreview {
  filename: string | null;
  row_count: number;
  headers: string[];
  mapping: Record<string, string | null>;
  sample: Record<string, string>[];
  fields: { name: string; required: boolean }[];
  missing_required: string[];
}

export interface EtlRuns {
  items: { id: number; source: string; started_at: string; rows_in: number; rows_loaded: number; report: EtlReport }[];
  required_columns: string[];
  optional_columns: string[];
}
