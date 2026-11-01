import { useEffect, useRef, useState } from "react";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { apiPost } from "@/lib/api";
import { useDesk } from "@/lib/hooks";

export type ArchiveKind = "template" | "deployment" | "research";
type LifecycleRequest =
  | { action: "archive"; kind: ArchiveKind; identity: string }
  | { action: "restore" | "recover"; archive_id: string };

interface LifecyclePreview {
  preview_id: string;
  preview_digest: string;
  confirmation_token: string;
  expected_head: string;
  expires_at: string;
  payload: Record<string, unknown>;
}

export function LifecycleActions({
  kind,
  identity,
  archiveId,
  recovery = false,
  onComplete,
}: {
  kind: ArchiveKind;
  identity: string;
  archiveId?: string;
  recovery?: boolean;
  onComplete: () => void;
}) {
  const { capabilities } = useDesk();
  const action = recovery ? "recover" : archiveId ? "restore" : "archive";
  const request: LifecycleRequest = archiveId ? { action: recovery ? "recover" : "restore", archive_id: archiveId } : { action: "archive", kind, identity };
  const [preview, setPreview] = useState<LifecyclePreview | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expired, setExpired] = useState(false);
  const requestVersion = useRef(0);
  const canWrite = capabilities?.writes === true
    && !capabilities.protected_names.some((name) => name.toLowerCase() === identity.toLowerCase());

  useEffect(() => {
    requestVersion.current += 1;
    setPreview(null);
    setError(null);
    setBusy(false);
    return () => { requestVersion.current += 1; };
  }, [kind, identity, archiveId, recovery]);

  useEffect(() => {
    if (!preview) return;
    const remaining = Date.parse(preview.expires_at) - Date.now();
    setExpired(remaining <= 0);
    const timer = window.setTimeout(() => setExpired(Date.parse(preview.expires_at) <= Date.now()), Math.min(2_147_483_647, Math.max(0, remaining)));
    return () => window.clearTimeout(timer);
  }, [preview]);

  async function review() {
    if (!canWrite || busy) return;
    const version = ++requestVersion.current;
    setBusy(true);
    setPreview(null);
    setError(null);
    try {
      const result = await apiPost<LifecyclePreview>("/api/lifecycle/preview", request);
      if (version !== requestVersion.current) return;
      const expiry = Date.parse(result.expires_at);
      if (!Number.isFinite(expiry) || expiry <= Date.now()) {
        throw new Error("Review expired; request a fresh review.");
      }
      setExpired(false);
      setPreview(result);
    } catch (cause) {
      if (version === requestVersion.current) setError(cause instanceof Error ? cause.message : "Lifecycle review failed.");
    } finally {
      if (version === requestVersion.current) setBusy(false);
    }
  }

  async function accept() {
    if (!preview || expired || Date.parse(preview.expires_at) <= Date.now() || busy || !canWrite) return;
    const version = ++requestVersion.current;
    setBusy(true);
    setError(null);
    try {
      const result = await apiPost<{ status: string }>("/api/lifecycle/accept", {
        ...request,
        preview_id: preview.preview_id,
        preview_digest: preview.preview_digest,
        confirmation_token: preview.confirmation_token,
        expected_head: preview.expected_head,
        request_id: crypto.randomUUID(),
      });
      if (version !== requestVersion.current) return;
      if (result.status !== "completed") {
        throw new Error("Lifecycle operation is not completed. Inspect archive recovery and operation status before taking further action.");
      }
      setPreview(null);
      onComplete();
    } catch (cause) {
      if (version !== requestVersion.current) return;
      setPreview(null);
      setError(cause instanceof Error ? cause.message : "Lifecycle outcome is uncertain. Inspect recovery before reviewing again.");
    } finally {
      if (version === requestVersion.current) setBusy(false);
    }
  }

  return (
    <div className="space-y-2">
      <Button variant="outline" disabled={!canWrite || busy} onClick={() => void review()}>
        {busy ? "Working..." : `Review ${action}`}
      </Button>
      {error ? <Alert tone="danger">{error}</Alert> : null}
      <Dialog open={preview !== null} onOpenChange={(open) => { if (!open && !busy) setPreview(null); }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Review {action}: {identity}</DialogTitle>
            <DialogDescription>
              Only this {kind} is affected. Archival retains its bytes and history; it does not remove sibling objects.
              Restoration is collision-checked and never starts a runner or replays work.
            </DialogDescription>
          </DialogHeader>
          {preview ? (
            <div className="min-w-0 space-y-3 text-xs">
              <p className="break-all">Reviewed identity / revision: <span className="mono">{preview.expected_head}</span></p>
              <p>Expires: {preview.expires_at}</p>
              <pre className="max-h-64 overflow-auto whitespace-pre-wrap break-all rounded-lg border border-border bg-black/10 p-3">{JSON.stringify(preview.payload, null, 2)}</pre>
              {expired ? <Alert tone="warning">Review expired. Close this dialog and request a fresh review.</Alert> : null}
            </div>
          ) : null}
          <DialogFooter>
            <Button variant="ghost" disabled={busy} onClick={() => setPreview(null)}>Cancel</Button>
            <Button variant={action === "archive" ? "danger" : "default"} disabled={!canWrite || busy || expired} onClick={() => void accept()}>
              {busy ? "Working..." : `Confirm ${action}`}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
