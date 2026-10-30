import type { HTMLAttributes } from "react";

import { cn } from "@/lib/utils";

export function Alert({
  className,
  tone = "neutral",
  ...props
}: HTMLAttributes<HTMLDivElement> & { tone?: "neutral" | "danger" | "warning" }) {
  const tones = {
    neutral: "border-border bg-white/[0.03] text-muted-foreground",
    danger: "border-negative/30 bg-negative/10 text-rose-200",
    warning: "border-warning/30 bg-warning/10 text-amber-100",
  };
  return (
    <div
      role={tone === "danger" ? "alert" : "status"}
      className={cn("rounded-lg border px-4 py-3 text-sm leading-relaxed", tones[tone], className)}
      {...props}
    />
  );
}
