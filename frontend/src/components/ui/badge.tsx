import { cva, type VariantProps } from "class-variance-authority";
import type { HTMLAttributes } from "react";

import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.12em]",
  {
    variants: {
      variant: {
        default: "border-accent/30 bg-accent/10 text-cyan-200",
        muted: "border-border bg-white/[0.04] text-muted-foreground",
        positive: "border-positive/25 bg-positive/10 text-emerald-300",
        negative: "border-negative/25 bg-negative/10 text-rose-300",
        warning: "border-warning/25 bg-warning/10 text-amber-200",
      },
    },
    defaultVariants: { variant: "default" },
  },
);

export interface BadgeProps
  extends HTMLAttributes<HTMLSpanElement>,
    VariantProps<typeof badgeVariants> {}

export function Badge({ className, variant, ...props }: BadgeProps) {
  return <span className={cn(badgeVariants({ className, variant }))} {...props} />;
}
