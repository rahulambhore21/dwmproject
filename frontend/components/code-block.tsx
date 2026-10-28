"use client";

import { Check, Copy } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

/** Monospace listing with a working copy button. Falls back to a hidden textarea where the Clipboard API is unavailable. */
export function CodeBlock({ code, label, className }: { code: string; label: string; className?: string }) {
  const [state, setState] = useState<"idle" | "copied" | "failed">("idle");
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  useEffect(() => () => clearTimeout(timer.current), []);

  async function copy() {
    let ok = false;
    try {
      await navigator.clipboard.writeText(code);
      ok = true;
    } catch {
      try {
        const ta = document.createElement("textarea");
        ta.value = code;
        ta.setAttribute("readonly", "");
        ta.style.position = "fixed";
        ta.style.opacity = "0";
        document.body.appendChild(ta);
        ta.select();
        ok = document.execCommand("copy");
        ta.remove();
      } catch {
        ok = false;
      }
    }
    setState(ok ? "copied" : "failed");
    clearTimeout(timer.current);
    timer.current = setTimeout(() => setState("idle"), 2000);
  }

  return (
    <div className={cn("relative border border-line bg-card", className)}>
      <Button type="button" size="sm" variant="quiet" className="absolute right-2 top-2 h-7" onClick={copy} aria-label={`Copy ${label}`}>
        {state === "copied" ? <Check className="size-3.5" /> : <Copy className="size-3.5" />}
        <span aria-live="polite">{state === "copied" ? "Copied" : state === "failed" ? "Copy failed" : "Copy"}</span>
      </Button>
      <pre tabIndex={0} aria-label={label} className="overflow-x-auto p-4 pr-24 font-mono text-[12px] leading-relaxed text-ink"><code>{code}</code></pre>
    </div>
  );
}
