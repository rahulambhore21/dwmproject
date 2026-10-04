import * as React from "react";
import { cn } from "@/lib/utils";

/** Styled native select: fully accessible, keyboard- and mobile-friendly. */
export const Select = React.forwardRef<HTMLSelectElement, React.SelectHTMLAttributes<HTMLSelectElement>>(({ className, children, ...props }, ref) => (
  <select
    ref={ref}
    className={cn(
      "h-10 w-full border border-line bg-card px-2.5 text-sm text-ink hover:border-ink disabled:opacity-50",
      className,
    )}
    {...props}
  >
    {children}
  </select>
));
Select.displayName = "Select";

export const Input = React.forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(({ className, ...props }, ref) => (
  <input ref={ref} className={cn("h-10 w-full border border-line bg-card px-3 text-sm text-ink placeholder:text-mute hover:border-ink disabled:opacity-50", className)} {...props} />
));
Input.displayName = "Input";

export const Textarea = React.forwardRef<HTMLTextAreaElement, React.TextareaHTMLAttributes<HTMLTextAreaElement>>(({ className, ...props }, ref) => (
  <textarea ref={ref} className={cn("min-h-28 w-full border border-line bg-card px-3 py-2 text-sm leading-relaxed text-ink placeholder:text-mute hover:border-ink", className)} {...props} />
));
Textarea.displayName = "Textarea";

export function Field({ label, hint, children, htmlFor, className }: { label: string; hint?: string; children: React.ReactNode; htmlFor?: string; className?: string }) {
  return (
    <div className={cn("space-y-1.5", className)}>
      <label htmlFor={htmlFor} className="eyebrow block">{label}</label>
      {children}
      {hint && <p className="text-xs text-mute">{hint}</p>}
    </div>
  );
}
