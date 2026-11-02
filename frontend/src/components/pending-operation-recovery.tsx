import { useEffect, useRef, useState } from "react";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { ApiError } from "@/lib/api";
import { useOperation } from "@/lib/hooks";
import { matchesOperationIdentity } from "@/lib/operation-identity";
import {
  recoverPendingOperation,
  type PendingOperation,
  type SavedOperationIdentity,
  type SavedOperationObservation,
} from "@/lib/pending-operations";
import type { Operation } from "@/lib/types";

const MAX_SAVED_OBSERVATIONS = 16;

interface Props {
  items: PendingOperation[];
  saved: SavedOperationIdentity[];
  error: string | null;
  onRefresh: () => void;
  onForget: (item: PendingOperation) => boolean;
  onRecovered: (item: PendingOperation, operation: Operation) => boolean;
  onMonitor: (item: SavedOperationIdentity) => void;
  onForgetSaved: (item: SavedOperationIdentity) => boolean;
  onObserve: (item: SavedOperationIdentity, status: SavedOperationObservation) => void;
}

export function PendingOperationRecovery({ items, saved, error, onRefresh, onForget, onRecovered, onMonitor, onForgetSaved, onObserve }: Props) {
  return (
    <>
      {error ? (
        <Alert tone="danger" className="mb-5">
          <p>{error}</p>
          <p>New reviewed operations are disabled until request identities can be inspected.</p>
          <Button className="mt-2" size="sm" variant="outline" onClick={onRefresh}>Retry browser storage</Button>
        </Alert>
      ) : null}
      {items.map((item) => (
        <PendingOperationNotice key={item.requestId} item={item} onForget={onForget} onRecovered={onRecovered} />
      ))}
      {saved.length ? (
        <Alert tone="neutral" className="mb-5">
          <p className="font-semibold">Saved operation monitors</p>
          <p>Active or unknown saved operations block new reviewed operations. Removing a monitor does not cancel it or prove that its effects stopped.</p>
          {saved.map((item, index) => (
            <SavedOperationMonitor
              key={item.requestId}
              item={item}
              enabled={index < MAX_SAVED_OBSERVATIONS}
              onObserve={onObserve}
              onMonitor={onMonitor}
              onForgetSaved={onForgetSaved}
            />
          ))}
        </Alert>
      ) : null}
    </>
  );
}

function SavedOperationMonitor({
  item,
  enabled,
  onObserve,
  onMonitor,
  onForgetSaved,
}: {
  item: SavedOperationIdentity;
  enabled: boolean;
  onObserve: Props["onObserve"];
  onMonitor: Props["onMonitor"];
  onForgetSaved: Props["onForgetSaved"];
}) {
  const resource = useOperation(enabled ? item.operationId : null, item.subjectId);
  const operation = resource.data && matchesOperationIdentity(resource.data, item) ? resource.data : null;
  const status: SavedOperationObservation = !enabled || resource.loading || resource.apiError || !operation
    ? "unknown"
    : ["accepted", "running", "cancel-requested"].includes(operation.status) ? "active" : "terminal";
  useEffect(() => {
    onObserve(item, status);
    return () => onObserve(item, "unknown");
  }, [item.requestId, item.operationId, item.action, item.subjectId, status, onObserve]);
  const label = !enabled
    ? "Observation limit reached; remove earlier monitors to check this one."
    : status === "unknown" ? "Status unverified." : `Status: ${operation?.status}.`;
  return (
    <div className="mt-2 flex flex-wrap items-center gap-2">
      <span className="mono text-xs">{item.action} · {item.subjectId} · {item.operationId} · {label}</span>
      <Button size="sm" variant="outline" aria-label={`Monitor saved operation ${item.operationId}`} onClick={() => onMonitor(item)}>
        Monitor
      </Button>
      <Button size="sm" variant="outline" aria-label={`Remove saved operation ${item.operationId}`} onClick={() => onForgetSaved(item)}>
        Remove
      </Button>
      {enabled && status === "unknown" ? (
        <Button size="sm" variant="outline" aria-label={`Retry saved operation ${item.operationId}`} onClick={resource.refresh}>
          Retry status
        </Button>
      ) : null}
    </div>
  );
}

function PendingOperationNotice({
  item,
  onForget,
  onRecovered,
}: {
  item: PendingOperation;
  onForget: Props["onForget"];
  onRecovered: Props["onRecovered"];
}) {
  const [attempt, setAttempt] = useState(0);
  const [checking, setChecking] = useState(true);
  const [message, setMessage] = useState("Checking durable status.");
  const recovered = useRef(onRecovered);
  recovered.current = onRecovered;

  useEffect(() => {
    const controller = new AbortController();
    let active = true;
    setChecking(true);
    setMessage("Checking durable status.");
    void recoverPendingOperation(item, { timeoutMs: 10_000, signal: controller.signal })
      .then((operation) => {
        if (active && !recovered.current(item, operation)) {
          setMessage("The operation was found, but recovery could not be finalized. The request identity remains saved.");
        }
      })
      .catch((cause: unknown) => {
        if (!active) return;
        if (cause instanceof ApiError && cause.status === 404) {
          setMessage("No operation was found for this request; its outcome is still unknown.");
        } else {
          setMessage(cause instanceof Error ? cause.message : "Operation status is unavailable; the outcome is unknown.");
        }
      })
      .finally(() => { if (active) setChecking(false); });
    return () => {
      active = false;
      controller.abort();
    };
  }, [attempt, item.requestId, item.action, item.subjectId]);

  return (
    <Alert tone="warning" className="mb-5">
      <p className="font-semibold">Unresolved reviewed operation</p>
      <p className="mono text-xs">{item.action} · {item.subjectId} · {item.requestId}</p>
      <p>{message}</p>
      <p>Forgetting this request does not prove that no effects occurred. Inspect durable state before submitting again.</p>
      <div className="mt-2 flex flex-wrap gap-2">
        <Button size="sm" variant="outline" disabled={checking} onClick={() => setAttempt((value) => value + 1)}>
          Check status
        </Button>
        <Button size="sm" variant="outline" onClick={() => onForget(item)}>
          Forget pending request
        </Button>
      </div>
    </Alert>
  );
}
