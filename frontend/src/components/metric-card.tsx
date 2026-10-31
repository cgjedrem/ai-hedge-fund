import type { LucideIcon } from "lucide-react";

import { Card, CardContent } from "@/components/ui/card";

export function MetricCard({
  label,
  value,
  note,
  icon: Icon,
  tone = "neutral",
}: {
  label: string;
  value: string;
  note?: string;
  icon?: LucideIcon;
  tone?: "neutral" | "positive" | "negative" | "warning";
}) {
  const tones = {
    neutral: "text-foreground",
    positive: "text-emerald-300",
    negative: "text-rose-300",
    warning: "text-amber-200",
  };
  return (
    <Card>
      <CardContent className="p-5">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <p className="mono text-[10px] uppercase tracking-[0.16em] text-muted-foreground">{label}</p>
            <p className={`mono mt-3 truncate text-xl font-medium tracking-tight ${tones[tone]}`}>{value}</p>
            {note ? <p className="mt-1.5 text-[11px] leading-relaxed text-muted-foreground">{note}</p> : null}
          </div>
          {Icon ? (
            <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-border bg-white/[0.03] text-muted-foreground">
              <Icon className="h-4 w-4" />
            </div>
          ) : null}
        </div>
      </CardContent>
    </Card>
  );
}
