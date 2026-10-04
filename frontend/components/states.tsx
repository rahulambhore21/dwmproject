"use client";

import { AlertTriangle, DatabaseZap, Hourglass, Inbox } from "lucide-react";
import type { ReactNode } from "react";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import type { ApiError } from "@/lib/api";
import { cn } from "@/lib/utils";

function Frame({ icon, title, children, tone = "line", className, role }: { icon: ReactNode; title: string; children?: ReactNode; tone?: "line" | "alert"; className?: string; role?: string }) {
  return (
    <div role={role} className={cn("flex flex-col items-start gap-3 border bg-card p-6", tone === "alert" ? "border-alert" : "border-line", className)}>
      <div className={cn("grid size-8 place-items-center border", tone === "alert" ? "border-alert text-alert" : "border-line text-mute")}>{icon}</div>
      <div>
        <p className="font-medium">{title}</p>
        {children && <div className="mt-1 max-w-prose text-sm text-mute">{children}</div>}
      </div>
    </div>
  );
}

export function LoadingBlock({ rows = 3, className, label = "Loading" }: { rows?: number; className?: string; label?: string }) {
  return (
    <div role="status" aria-label={label} className={cn("space-y-3", className)}>
      {Array.from({ length: rows }).map((_, i) => (
        <Skeleton key={i} className={cn("h-5", i === 0 ? "w-2/5" : i % 2 ? "w-full" : "w-4/5")} />
      ))}
      <span className="sr-only">{label}…</span>
    </div>
  );
}

export function WarmingUp() {
  return (
    <Frame icon={<DatabaseZap className="size-4" />} title="Starting the analytics engine" role="status">
      On first launch SIGNAL seeds the demo workspace, builds the warehouse and trains the models. This takes about 20 seconds and only happens once.
    </Frame>
  );
}

export function ErrorState({ error, onRetry, className }: { error: ApiError | Error; onRetry?: () => void; className?: string }) {
  const unavailable = "isUnavailable" in error && (error as ApiError).isUnavailable;
  return (
    <Frame role="alert" tone="alert" icon={<AlertTriangle className="size-4" />} title={unavailable ? "The SIGNAL API isn't reachable" : "Something went wrong"} className={className}>
      <p>{unavailable ? "Start it with `npm run dev` (or check BACKEND_URL), then retry." : error.message}</p>
      {onRetry && (
        <Button variant="outline" size="sm" className="mt-3" onClick={onRetry}>
          Try again
        </Button>
      )}
    </Frame>
  );
}

export function EmptyState({ title, children, action, className }: { title: string; children?: ReactNode; action?: ReactNode; className?: string }) {
  return (
    <Frame icon={<Inbox className="size-4" />} title={title} className={className}>
      {children}
      {action && <div className="mt-3">{action}</div>}
    </Frame>
  );
}

export function InsufficientState({ title = "Not enough data yet", children, className }: { title?: string; children?: ReactNode; className?: string }) {
  return (
    <Frame icon={<Hourglass className="size-4" />} title={title} className={className}>
      {children}
    </Frame>
  );
}

/** Standard wrapper: handles warming/loading/error and renders children with data. */
export function Async<T>({ state, children, skeleton }: { state: { data: T | null; error: ApiError | null; loading: boolean; warming: boolean; reload: () => void }; children: (d: T) => ReactNode; skeleton?: ReactNode }) {
  if (state.warming) return <WarmingUp />;
  if (state.error) return <ErrorState error={state.error} onRetry={state.reload} />;
  if (state.loading && !state.data) return <>{skeleton ?? <LoadingBlock rows={4} />}</>;
  if (!state.data) return null;
  return <>{children(state.data)}</>;
}
