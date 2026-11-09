import { LifecycleActions, type ArchiveKind } from "@/components/lifecycle-actions";
import { ErrorState } from "@/components/page";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useResource } from "@/lib/hooks";

interface ArchiveRecord {
  archive_id: string;
  kind: ArchiveKind;
  identity: string;
  state: "archive-unprepared" | "archive-prepared" | "archived" | "restore-prepared" | "restored" | "abandoned";
  updated_at: string;
  recovery_required?: boolean;
  recovery_action?: string;
  recovery_error?: string;
}

export function ArchivePanel({ kind, onChange }: { kind: ArchiveKind; onChange: () => void }) {
  const resource = useResource<{ items: ArchiveRecord[] }>("/api/lifecycle/archives");
  const items = resource.data?.items.filter((item) => item.kind === kind && item.state !== "restored" && item.state !== "abandoned") ?? [];
  return (
    <Card className="mt-5">
      <CardHeader>
        <CardTitle>Archives and recovery</CardTitle>
        <p className="text-xs text-muted-foreground">Exact-scope retained history. Restore never starts a runner. Interrupted transitions require deliberate recovery.</p>
      </CardHeader>
      <CardContent>
        {resource.error ? <ErrorState message={resource.error} error={resource.apiError} onRetry={resource.refresh} /> : null}
        {resource.loading ? <p className="text-xs text-muted-foreground">Loading archive records...</p> : null}
        {!resource.loading && !resource.error && items.length === 0 ? <p className="text-xs text-muted-foreground">No archived {kind} objects.</p> : null}
        <div className="space-y-4">
          {items.map((item) => (
            <div key={item.archive_id} className="flex flex-wrap items-center justify-between gap-3 border-t border-border pt-4">
              <div className="min-w-0">
                <p className="break-all text-sm font-medium">{item.identity}</p>
                <p className="mono mt-1 break-all text-[10px] text-muted-foreground">{item.archive_id} / {item.updated_at}</p>
                <Badge variant={item.recovery_required || item.state !== "archived" ? "warning" : "muted"}>{item.recovery_action === "manual-review" ? "manual review required" : item.state}</Badge>
                {item.recovery_error ? <p role="alert" className="mt-2 text-xs text-warning">{item.recovery_error}</p> : null}
              </div>
              {item.recovery_action !== "manual-review" ? <LifecycleActions kind={kind} identity={item.identity} archiveId={item.archive_id} recovery={item.recovery_required || item.state !== "archived"} onComplete={() => { resource.refresh(); onChange(); }} /> : null}
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}
