export const pct = (x: number | null | undefined, digits = 1): string =>
  x === null || x === undefined || Number.isNaN(x) ? "—" : `${(x * 100).toFixed(digits)}%`;

export const signedPct = (x: number | null | undefined, digits = 1): string =>
  x === null || x === undefined || Number.isNaN(x) ? "—" : `${x > 0 ? "+" : x < 0 ? "−" : ""}${Math.abs(x).toFixed(digits)}%`;

export const signedNum = (x: number | null | undefined, digits = 2): string =>
  x === null || x === undefined || Number.isNaN(x) ? "—" : `${x > 0 ? "+" : x < 0 ? "−" : ""}${Math.abs(x).toFixed(digits)}`;

export const compact = (x: number | null | undefined): string =>
  x === null || x === undefined ? "—" : new Intl.NumberFormat("en", { notation: "compact", maximumFractionDigits: 1 }).format(x);

export const int = (x: number | null | undefined): string =>
  x === null || x === undefined ? "—" : new Intl.NumberFormat("en").format(Math.round(x));

export const fixed = (x: number | null | undefined, digits = 2): string =>
  x === null || x === undefined || Number.isNaN(x) ? "—" : x.toFixed(digits);

export function dateShort(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleDateString("en", { month: "short", day: "numeric", year: "numeric" });
}

export function monthLabel(m: string): string {
  const [y, mo] = m.split("-");
  return new Date(Number(y), Number(mo) - 1, 1).toLocaleDateString("en", { month: "short", year: "2-digit" });
}

export function relativeTime(iso: string, now: Date = new Date()): string {
  const diff = (now.getTime() - new Date(iso).getTime()) / 1000;
  if (diff < 90) return "just now";
  if (diff < 3600) return `${Math.round(diff / 60)} min ago`;
  if (diff < 86400) return `${Math.round(diff / 3600)} h ago`;
  return `${Math.round(diff / 86400)} d ago`;
}

export function p(x: number | null | undefined): string {
  if (x === null || x === undefined) return "—";
  return x < 0.001 ? "p<0.001" : `p=${x.toFixed(3)}`;
}

export const ALGORITHM_LABELS: Record<string, string> = {
  linear_regression: "Linear regression",
  multiple_linear_regression: "Multiple linear regression",
  mutual_information: "Mutual information",
  decision_tree: "Decision tree",
  gaussian_nb: "Gaussian Naive Bayes",
  kmeans: "K-Means",
  agglomerative: "Agglomerative clustering",
  apriori: "Apriori",
};

export const VERDICT_LABELS: Record<string, string> = {
  adopt: "Adopt variant",
  keep_control: "Keep control",
  inconclusive: "Inconclusive",
  insufficient_data: "Collecting data",
};
