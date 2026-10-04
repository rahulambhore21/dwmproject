"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";

const NAV = [
  { href: "/", label: "Overview", step: "Understand" },
  { href: "/memory", label: "Memory", step: "Understand" },
  { href: "/lab", label: "Pre-Publish Lab", step: "Decide" },
  { href: "/experiments", label: "Experiments", step: "Experiment" },
  { href: "/learning", label: "Learning", step: "Learn" },
  { href: "/explore", label: "Explore", step: "Analyse" },
];

export function SiteHeader() {
  const pathname = usePathname();
  const active = (href: string) => (href === "/" ? pathname === "/" : pathname.startsWith(href));
  return (
    <header className="sticky top-0 z-30 border-b border-line bg-paper/95 backdrop-blur-sm">
      <div className="mx-auto flex max-w-[1240px] items-center gap-6 px-5 sm:px-8">
        <Link href="/" className="flex shrink-0 items-center gap-2 py-4" aria-label="SIGNAL home">
          <span className="grid size-5 place-items-center bg-lime" aria-hidden>
            <span className="size-1.5 bg-ink" />
          </span>
          <span className="font-mono text-sm font-semibold tracking-[0.18em]">SIGNAL</span>
        </Link>
        <nav aria-label="Primary" className="-mb-px flex flex-1 gap-5 overflow-x-auto">
          {NAV.map((n, i) => (
            <Link
              key={n.href}
              href={n.href}
              aria-current={active(n.href) ? "page" : undefined}
              className={cn(
                "group flex shrink-0 flex-col justify-center border-b-2 py-3 text-sm transition-colors",
                active(n.href) ? "border-ink text-ink" : "border-transparent text-mute hover:text-ink",
              )}
            >
              <span className="font-mono text-[10px] leading-none text-mute">{String(i + 1).padStart(2, "0")} · {n.step}</span>
              <span className="mt-1 leading-none">{n.label}</span>
            </Link>
          ))}
        </nav>
      </div>
    </header>
  );
}
