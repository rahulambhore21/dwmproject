import { type VariantProps, cva } from "class-variance-authority";
import * as React from "react";
import { cn } from "@/lib/utils";

const badgeVariants = cva("inline-flex items-center gap-1 border px-1.5 py-0.5 font-mono text-[11px] leading-none tracking-wide", {
  variants: {
    tone: {
      neutral: "border-line bg-transparent text-ink-2",
      ink: "border-ink bg-ink text-paper",
      lime: "border-ink bg-lime text-lime-ink",
      alert: "border-alert text-alert",
      mute: "border-line text-mute",
    },
  },
  defaultVariants: { tone: "neutral" },
});

export function Badge({ className, tone, ...props }: React.HTMLAttributes<HTMLSpanElement> & VariantProps<typeof badgeVariants>) {
  return <span className={cn(badgeVariants({ tone }), className)} {...props} />;
}
