import { ArrowDownRight, ArrowUpRight, Minus } from "lucide-react";
import type { ReactNode } from "react";
import { Badge } from "@/components/ui/badge";
import { p as fmtP, signedPct } from "@/lib/format";
import { cn } from "@/lib/utils";

export function PageHeader({ eyebrow, title, lede, actions }: { eyebrow: string; title: ReactNode; lede?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="mb-10 flex flex-col gap-6 border-b border-ink pb-8 md:flex-row md:items-end md:justify-between">
      <div className="max-w-3xl">
        <p className="eyebrow mb-3">{eyebrow}</p>
        <h1 className="display text-5xl sm:text-6xl">{title}</h1>
        {lede && <p className="mt-4 max-w-2xl text-base leading-relaxed text-ink-2">{lede}</p>}
      </div>
      {actions && <div className="flex shrink-0 flex-wrap gap-2">{actions}</div>}
    </div>
  );
}

export function Section({ title, kicker, aside, children, className, id }: { title: string; kicker?: string; aside?: ReactNode; children: ReactNode; className?: string; id?: string }) {
  return (
    <section id={id} aria-labelledby={id ? `${id}-h` : undefined} className={cn("mt-14", className)}>
      <div className="mb-5 flex items-end justify-between gap-4 border-b border-line pb-3">
        <div>
          {kicker && <p className="eyebrow mb-1">{kicker}</p>}
          <h2 id={id ? `${id}-h` : undefined} className="display text-3xl">{title}</h2>
        </div>
        {aside && <div className="text-sm text-mute">{aside}</div>}
      </div>
      {children}
    </section>
  );
}

export function Stat({ label, value, sub, className }: { label: string; value: ReactNode; sub?: ReactNode; className?: string }) {
  return (
    <div className={cn("border-t border-ink pt-3", className)}>
      <p className="eyebrow">{label}</p>
      <p className="num mt-2 text-4xl font-medium leading-none tracking-tight">{value}</p>
      {sub && <div className="mt-2 text-xs text-mute">{sub}</div>}
    </div>
  );
}

/** Delta with honest significance: only emphasised when p < 0.05. */
export function Delta({ pct, p, label }: { pct: number | null; p?: number | null; label?: string }) {
  if (pct === null) return <span className="text-mute">Not enough history to compare</span>;
  const sig = p !== null && p !== undefined && p < 0.05;
  const Icon = pct > 0.5 ? ArrowUpRight : pct < -0.5 ? ArrowDownRight : Minus;
  return (
    <span className="inline-flex flex-wrap items-center gap-1.5">
      <span className={cn("num inline-flex items-center gap-0.5", sig ? "font-semibold text-ink" : "text-mute")}>
        <Icon className="size-3.5" aria-hidden />
        {signedPct(pct)}
      </span>
      {label && <span className="text-mute">{label}</span>}
      <Badge tone={sig ? "lime" : "mute"}>{sig ? "significant" : "within noise"} · {fmtP(p ?? null)}</Badge>
    </span>
  );
}

export function Meter({ value, max = 1, marker, className, label }: { value: number; max?: number; marker?: number; className?: string; label?: string }) {
  const w = Math.max(0, Math.min(100, (value / max) * 100));
  return (
    <div className={cn("relative h-2 w-full bg-paper-2", className)} role="img" aria-label={label}>
      <div className="absolute inset-y-0 left-0 bg-ink" style={{ width: `${w}%` }} />
      {marker !== undefined && <div className="absolute -inset-y-1 w-px bg-alert" style={{ left: `${Math.min(100, (marker / max) * 100)}%` }} />}
    </div>
  );
}

export function Tag({ children, tone = "neutral" }: { children: ReactNode; tone?: "neutral" | "ink" | "lime" | "alert" | "mute" }) {
  return <Badge tone={tone}>{children}</Badge>;
}

export function StrengthBadge({ strength }: { strength: "weak" | "moderate" | "strong" }) {
  return (
    <Badge tone={strength === "strong" ? "ink" : strength === "moderate" ? "neutral" : "mute"} title="How strongly the underlying evidence supports this statement">
      {strength} evidence
    </Badge>
  );
}

export function PlatformDot({ platform }: { platform: string }) {
  const initials: Record<string, string> = { Instagram: "IG", LinkedIn: "LI", TikTok: "TT", X: "X" };
  return <span className="inline-grid h-5 min-w-6 place-items-center border border-ink px-1 font-mono text-[10px] font-semibold">{initials[platform] ?? platform.slice(0, 2).toUpperCase()}</span>;
}
