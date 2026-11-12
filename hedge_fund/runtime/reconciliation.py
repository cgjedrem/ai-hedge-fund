"""Head-bound provenance for local-paper recovery."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

_REQUEST_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_HEX_ID = re.compile(r"^[a-f0-9]{32}$")
_SHA256 = re.compile(r"^[a-f0-9]{64}$")
_DECISION = "confirm-paper-book-matches-ledger"
_RESIDUAL_UNCERTAINTY = "external-broker-state-not-applicable-local-paper-only"


class TickOperationIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    operation_id: str = Field(pattern=_HEX_ID.pattern)
    request_id: str = Field(pattern=_REQUEST_ID.pattern)
    capture_id: str = Field(pattern=_HEX_ID.pattern)
    capture_digest: str = Field(pattern=_SHA256.pattern)


class ReconciliationPreview(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    required: bool
    recoverable: bool
    reason: Literal[
        "no-ambiguous-tick-failure",
        "multiple-unreconciled-failures",
        "failure-identity-incomplete",
        "ledger-head-changed",
        "broker-not-local-paper",
        "broker-book-unavailable",
        "broker-book-invalid",
        "broker-book-changed",
        "broker-book-mismatch",
        "ready",
    ]
    failure_id: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    failed_request_id: str | None = Field(default=None, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
    operation_id: str | None = Field(default=None, pattern=r"^[a-f0-9]{32}$")
    expected_head: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    current_head: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    broker_book_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    fill_identity_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    capture_id: str | None = Field(default=None, pattern=r"^[a-f0-9]{32}$")
    capture_digest: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    book_matches_ledger: bool
    head_matches_failure: bool
    decision: Literal["confirm-paper-book-matches-ledger"] = _DECISION
    residual_uncertainty: Literal["external-broker-state-not-applicable-local-paper-only"] = _RESIDUAL_UNCERTAINTY
    preview_digest: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")

    @model_validator(mode="after")
    def _validate_digest(self) -> ReconciliationPreview:
        if (self.capture_id is None) != (self.capture_digest is None):
            raise ValueError("capture identity and digest must be paired")
        if self.required:
            if self.preview_digest != self.compute_preview_digest():
                raise ValueError("preview_digest does not match the preview contents")
        elif self.preview_digest is not None:
            raise ValueError("an unrequired reconciliation preview has no digest")
        return self

    @classmethod
    def create(cls, **fields) -> ReconciliationPreview:
        payload = {"schema_version": 1, **fields}
        if payload["required"]:
            candidate = cls.model_construct(**payload, preview_digest=None)
            payload["preview_digest"] = candidate.compute_preview_digest()
        else:
            payload["preview_digest"] = None
        return cls.model_validate(payload)

    def compute_preview_digest(self) -> str:
        return _receipt_digest(self.model_dump(mode="json", exclude={"preview_digest"}))


class ReconciliationConfirmation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    request_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
    failure_id: str = Field(pattern=r"^[a-f0-9]{64}$")
    preview_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    decision: Literal["confirm-paper-book-matches-ledger"] = _DECISION


@dataclass(frozen=True, slots=True)
class ReconciliationSnapshot:
    preview: ReconciliationPreview
    failure_event: dict | None


class ReconciliationReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    request_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
    failed_request_id: str | None = Field(default=None, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
    operation_id: str | None = Field(default=None, pattern=r"^[a-f0-9]{32}$")
    failure_id: str = Field(pattern=r"^[a-f0-9]{64}$")
    expected_head: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    current_head: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    broker_book_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    fill_identity_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    capture_id: str | None = Field(default=None, pattern=r"^[a-f0-9]{32}$")
    capture_digest: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    operator: Literal["cli", "tui", "web"]
    recorded_at: str
    decision: Literal["confirm-paper-book-matches-ledger"] = _DECISION
    residual_uncertainty: Literal["external-broker-state-not-applicable-local-paper-only"] = _RESIDUAL_UNCERTAINTY
    receipt_id: str = Field(pattern=r"^[a-f0-9]{64}$")

    @model_validator(mode="after")
    def _validate_identity(self) -> ReconciliationReceipt:
        if (self.capture_id is None) != (self.capture_digest is None):
            raise ValueError("capture identity and digest must be paired")
        try:
            recorded_at = datetime.fromisoformat(self.recorded_at.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("recorded_at must be an ISO timestamp") from exc
        if recorded_at.tzinfo is None or recorded_at.utcoffset() is None:
            raise ValueError("recorded_at must include a timezone")
        if self.receipt_id != self.compute_receipt_id():
            raise ValueError("receipt_id does not match the receipt contents")
        return self

    @classmethod
    def create(
        cls,
        *,
        failure_event: dict,
        request_id: str,
        current_head: str | None,
        broker_book_sha256: str,
        fill_identity_sha256: str,
        operator: Literal["cli", "tui", "web"],
        recorded_at: str,
    ) -> ReconciliationReceipt:
        if not isinstance(failure_event, dict) or failure_event.get("kind") != "tick_failed" or "expected_head" not in failure_event:
            raise ValueError("a complete tick-failure event is required")
        payload = {
            "schema_version": 1,
            "request_id": request_id,
            "failed_request_id": failure_event.get("request_id"),
            "operation_id": failure_event.get("operation_id"),
            "failure_id": failure_digest(failure_event),
            "expected_head": failure_event["expected_head"],
            "current_head": current_head,
            "broker_book_sha256": broker_book_sha256,
            "fill_identity_sha256": fill_identity_sha256,
            "capture_id": failure_event.get("capture_id"),
            "capture_digest": failure_event.get("capture_digest"),
            "operator": operator,
            "recorded_at": recorded_at,
            "decision": _DECISION,
            "residual_uncertainty": _RESIDUAL_UNCERTAINTY,
        }
        payload["receipt_id"] = _receipt_digest(payload)
        return cls.model_validate(payload)

    def compute_receipt_id(self) -> str:
        return _receipt_digest(self.model_dump(mode="json", exclude={"receipt_id"}))

    def matches_failure(self, failure_event: dict) -> bool:
        return self.failure_id == failure_digest(failure_event) and self.expected_head == failure_event.get("expected_head") and self.failed_request_id == failure_event.get("request_id") and self.operation_id == failure_event.get("operation_id") and self.capture_id == failure_event.get("capture_id") and self.capture_digest == failure_event.get("capture_digest")


class TickIntentReconciliationPreview(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    required: bool
    recoverable: bool
    reason: Literal[
        "no-unresolved-tick-intent",
        "multiple-unresolved-tick-intents",
        "intent-not-found",
        "ledger-head-changed",
        "broker-not-local-paper",
        "broker-book-unavailable",
        "broker-book-invalid",
        "broker-book-changed",
        "broker-book-mismatch",
        "approval-journal-incomplete",
        "ready",
    ]
    intent_request_id: str | None = Field(default=None, pattern=_REQUEST_ID.pattern)
    intent_session: str | None = Field(default=None, min_length=1, max_length=256)
    intent_digest: str | None = Field(default=None, pattern=_SHA256.pattern)
    metadata_complete: bool | None = None
    corrupt_event_digests: tuple[str, ...] = ()
    approval_journal_event_digests: tuple[str, ...] = ()
    expected_head: str | None = Field(default=None, pattern=_SHA256.pattern)
    current_head: str | None = Field(default=None, pattern=_SHA256.pattern)
    broker_book_sha256: str | None = Field(default=None, pattern=_SHA256.pattern)
    fill_identity_sha256: str = Field(pattern=_SHA256.pattern)
    book_matches_ledger: bool
    head_matches_intent: bool
    decision: Literal["confirm-paper-book-matches-ledger"] = _DECISION
    residual_uncertainty: Literal["external-broker-state-not-applicable-local-paper-only"] = _RESIDUAL_UNCERTAINTY
    preview_digest: str | None = Field(default=None, pattern=_SHA256.pattern)

    @model_validator(mode="after")
    def _validate_digest(self) -> TickIntentReconciliationPreview:
        if len(set(self.corrupt_event_digests)) != len(self.corrupt_event_digests):
            raise ValueError("corrupt event identities must be unique")
        if len(set(self.approval_journal_event_digests)) != len(self.approval_journal_event_digests) or any(_SHA256.fullmatch(digest) is None for digest in self.approval_journal_event_digests):
            raise ValueError("approval journal event identities are invalid")
        if self.required:
            if self.preview_digest != self.compute_preview_digest():
                raise ValueError("preview_digest does not match the preview contents")
            if (
                self.intent_digest is None
                and not self.corrupt_event_digests
                and not self.approval_journal_event_digests
                and self.reason
                not in {
                    "intent-not-found",
                    "multiple-unresolved-tick-intents",
                    "approval-journal-incomplete",
                }
            ):
                raise ValueError("required intent reconciliation has no target")
        elif self.preview_digest is not None or self.recoverable:
            raise ValueError("an unrequired intent reconciliation has no digest or recovery")
        return self

    @classmethod
    def create(cls, **fields) -> TickIntentReconciliationPreview:
        payload = {"schema_version": 1, **fields}
        if payload["required"]:
            candidate = cls.model_construct(**payload, preview_digest=None)
            payload["preview_digest"] = candidate.compute_preview_digest()
        else:
            payload["preview_digest"] = None
        return cls.model_validate(payload)

    def compute_preview_digest(self) -> str:
        return _receipt_digest(self.model_dump(mode="json", exclude={"preview_digest"}))


class TickIntentReconciliationConfirmation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    request_id: str = Field(pattern=_REQUEST_ID.pattern)
    intent_request_id: str | None = Field(default=None, pattern=_REQUEST_ID.pattern)
    intent_digest: str | None = Field(default=None, pattern=_SHA256.pattern)
    preview_digest: str = Field(pattern=_SHA256.pattern)
    decision: Literal["confirm-paper-book-matches-ledger"] = _DECISION

    @model_validator(mode="after")
    def _validate_target(self) -> TickIntentReconciliationConfirmation:
        if self.intent_digest is None and self.intent_request_id is not None:
            raise ValueError("intent request identity requires an intent digest")
        return self


class TickIntentReconciliationReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    request_id: str = Field(pattern=_REQUEST_ID.pattern)
    intent_request_id: str | None = Field(default=None, pattern=_REQUEST_ID.pattern)
    intent_digest: str | None = Field(default=None, pattern=_SHA256.pattern)
    preview_digest: str = Field(pattern=_SHA256.pattern)
    corrupt_event_digests: tuple[str, ...] = ()
    approval_journal_event_digests: tuple[str, ...] = ()
    expected_head: str | None = Field(default=None, pattern=_SHA256.pattern)
    current_head: str | None = Field(default=None, pattern=_SHA256.pattern)
    broker_book_sha256: str = Field(pattern=_SHA256.pattern)
    fill_identity_sha256: str = Field(pattern=_SHA256.pattern)
    operator: Literal["cli", "tui", "web"]
    recorded_at: str
    decision: Literal["confirm-paper-book-matches-ledger"] = _DECISION
    residual_uncertainty: Literal["external-broker-state-not-applicable-local-paper-only"] = _RESIDUAL_UNCERTAINTY
    receipt_id: str = Field(pattern=_SHA256.pattern)

    @model_validator(mode="after")
    def _validate_identity(self) -> TickIntentReconciliationReceipt:
        if self.intent_digest is None and self.intent_request_id is not None:
            raise ValueError("intent request identity requires an intent digest")
        if len(set(self.corrupt_event_digests)) != len(self.corrupt_event_digests):
            raise ValueError("corrupt event identities must be unique")
        if len(set(self.approval_journal_event_digests)) != len(self.approval_journal_event_digests) or any(_SHA256.fullmatch(digest) is None for digest in self.approval_journal_event_digests):
            raise ValueError("approval journal event identities are invalid")
        try:
            recorded_at = datetime.fromisoformat(self.recorded_at.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("recorded_at must be an ISO timestamp") from exc
        if recorded_at.tzinfo is None or recorded_at.utcoffset() is None:
            raise ValueError("recorded_at must include a timezone")
        if self.receipt_id != self.compute_receipt_id():
            raise ValueError("receipt_id does not match the receipt contents")
        return self

    @classmethod
    def create(
        cls,
        *,
        preview: TickIntentReconciliationPreview,
        request_id: str,
        operator: Literal["cli", "tui", "web"],
        recorded_at: str,
    ) -> TickIntentReconciliationReceipt:
        if not isinstance(preview, TickIntentReconciliationPreview) or not preview.required or not preview.recoverable:
            raise ValueError("a recoverable tick-intent preview is required")
        payload = {
            "schema_version": 1,
            "request_id": request_id,
            "intent_request_id": preview.intent_request_id,
            "intent_digest": preview.intent_digest,
            "preview_digest": preview.preview_digest,
            "corrupt_event_digests": preview.corrupt_event_digests,
            "approval_journal_event_digests": preview.approval_journal_event_digests,
            "expected_head": preview.expected_head,
            "current_head": preview.current_head,
            "broker_book_sha256": preview.broker_book_sha256,
            "fill_identity_sha256": preview.fill_identity_sha256,
            "operator": operator,
            "recorded_at": recorded_at,
            "decision": _DECISION,
            "residual_uncertainty": _RESIDUAL_UNCERTAINTY,
        }
        if not payload["approval_journal_event_digests"]:
            payload.pop("approval_journal_event_digests")
        payload["receipt_id"] = _receipt_digest(payload)
        return cls.model_validate(payload)

    def compute_receipt_id(self) -> str:
        payload = self.model_dump(mode="json", exclude={"receipt_id"})
        if not self.approval_journal_event_digests:
            payload.pop("approval_journal_event_digests", None)
        return _receipt_digest(payload)


@dataclass(frozen=True, slots=True)
class TickIntentReconciliationSnapshot:
    preview: TickIntentReconciliationPreview
    intent_event: dict | None


def failure_digest(event: dict) -> str:
    if not isinstance(event, dict) or event.get("kind") != "tick_failed":
        raise ValueError("failure identity requires a tick_failed event")
    return hashlib.sha256(_canonical_json(event)).hexdigest()


def unresolved_tick_failures(events: list[dict]) -> list[dict]:
    if not isinstance(events, list) or any(not isinstance(event, dict) for event in events):
        raise ValueError("paper events must be a list of objects")
    failures: dict[str, dict] = {}
    receipts: dict[str, ReconciliationReceipt] = {}
    resumed_receipts: set[str] = set()
    for event in events:
        if event.get("kind") == "tick_failed":
            failures[failure_digest(event)] = event
        elif event.get("kind") == "reconciliation":
            try:
                receipt = ReconciliationReceipt.model_validate(event.get("receipt"))
            except (TypeError, ValueError):
                continue
            failure = failures.get(receipt.failure_id)
            if failure is not None and receipt.matches_failure(failure):
                receipts[receipt.failure_id] = receipt
        elif event.get("kind") == "resume":
            receipt_id = event.get("reconciliation_id")
            if isinstance(receipt_id, str) and _SHA256.fullmatch(receipt_id):
                resumed_receipts.add(receipt_id)
    resolved = {failure_id for failure_id, receipt in receipts.items() if receipt.receipt_id in resumed_receipts}
    return [failure for identity, failure in failures.items() if identity not in resolved]


def build_reconciliation_snapshot(
    directory: str | Path,
    deployed,
    ledger,
    state,
    latest,
    *,
    failure_event: dict | None = None,
) -> ReconciliationSnapshot:
    events, unresolved_corrupt_event_digests = ledger.recovery_events_with_unresolved_corruption()
    failures = [failure_event] if failure_event is not None else unresolved_tick_failures(events)
    if not failures and unresolved_corrupt_event_digests:
        return ReconciliationSnapshot(
            preview=ReconciliationPreview.create(
                required=True,
                recoverable=False,
                reason="failure-identity-incomplete",
                fill_identity_sha256=_fill_identity_sha256(latest),
                book_matches_ledger=False,
                head_matches_failure=False,
            ),
            failure_event=None,
        )
    if not failures:
        return ReconciliationSnapshot(
            preview=ReconciliationPreview.create(
                required=False,
                recoverable=False,
                reason="no-ambiguous-tick-failure",
                fill_identity_sha256=_fill_identity_sha256(latest),
                book_matches_ledger=False,
                head_matches_failure=False,
            ),
            failure_event=None,
        )

    failure = failures[-1]
    latest_head = latest.hash if latest is not None else None
    expected_head = failure.get("expected_head")
    head_matches = "expected_head" in failure and (expected_head == latest_head or (latest is not None and latest.session == failure.get("session") and latest.prev_hash == expected_head))
    failure_identity_complete = "expected_head" in failure
    if any(failure.get(field) is not None for field in ("operation_id", "capture_id", "capture_digest")):
        try:
            TickOperationIdentity.model_validate(
                {
                    "operation_id": failure.get("operation_id"),
                    "request_id": failure.get("request_id"),
                    "capture_id": failure.get("capture_id"),
                    "capture_digest": failure.get("capture_digest"),
                }
            )
        except ValueError:
            failure_identity_complete = False

    book_digest = None
    book_matches = False
    reason = "ready"
    if len(failures) != 1:
        reason = "multiple-unreconciled-failures"
    elif not failure_identity_complete:
        reason = "failure-identity-incomplete"
    elif not head_matches or state.prev_hash != latest_head:
        reason = "ledger-head-changed"
    elif deployed.broker != "paper":
        reason = "broker-not-local-paper"
    else:
        from hedge_fund.brokers.paper import PaperBroker
        from hedge_fund.paths import read_bytes
        from hedge_fund.pipeline.session import BookMismatch, reconcile

        book_path = Path(directory) / "broker.json"
        try:
            before = read_bytes(book_path)
        except OSError:
            reason = "broker-book-unavailable"
        else:
            book_digest = hashlib.sha256(before).hexdigest()
            try:
                broker = PaperBroker(book_path, deployed.spec.costs)
                after = read_bytes(book_path)
            except (KeyError, OSError, TypeError, ValueError):
                reason = "broker-book-invalid"
            else:
                if before != after:
                    reason = "broker-book-changed"
                else:
                    try:
                        reconcile(state, broker, deployed.name)
                    except BookMismatch:
                        reason = "broker-book-mismatch"
                    else:
                        book_matches = True

    preview = ReconciliationPreview.create(
        required=True,
        recoverable=reason == "ready" and book_matches and head_matches,
        reason=reason,
        failure_id=failure_digest(failure),
        failed_request_id=failure.get("request_id"),
        operation_id=failure.get("operation_id"),
        expected_head=expected_head,
        current_head=latest_head,
        broker_book_sha256=book_digest,
        fill_identity_sha256=_fill_identity_sha256(latest),
        capture_id=failure.get("capture_id"),
        capture_digest=failure.get("capture_digest"),
        book_matches_ledger=book_matches,
        head_matches_failure=head_matches,
    )
    return ReconciliationSnapshot(preview=preview, failure_event=failure)


def build_tick_intent_reconciliation_snapshot(
    directory: str | Path,
    deployed,
    ledger,
    state,
    latest,
    *,
    intent_request_id: str | None = None,
    intent_digest: str | None = None,
) -> TickIntentReconciliationSnapshot:
    from hedge_fund.paper.ledger import LedgerError

    if intent_request_id is not None and (not isinstance(intent_request_id, str) or not _REQUEST_ID.fullmatch(intent_request_id)):
        raise ValueError("tick-intent request identity is invalid")
    if intent_digest is not None and (not isinstance(intent_digest, str) or not _SHA256.fullmatch(intent_digest)):
        raise ValueError("tick-intent digest is invalid")
    events, _corrupt_occurrences, event_offsets = ledger._recovery_events_with_offsets()
    unresolved = ledger.unresolved_tick_intents()
    intents = [item for item in unresolved if not item.is_corrupt and item.intent_digest is not None]
    corrupt_digests = tuple(sorted({digest for item in unresolved for digest in item.corrupt_event_digests}))
    try:
        approval_journal_events = ledger.unresolved_approval_consumption_events(allow_unresolved_corruption=True)
        approval_journal_unavailable = False
    except (LedgerError, OSError, UnicodeError, ValueError):
        approval_journal_events = ()
        approval_journal_unavailable = True
    selected = None
    reason = "ready"
    if intent_request_id is not None or intent_digest is not None:
        matches = [item for item in intents if (intent_request_id is None or item.request_id == intent_request_id) and (intent_digest is None or item.intent_digest == intent_digest)]
        if len(matches) == 1:
            selected = matches[0]
        elif matches:
            reason = "multiple-unresolved-tick-intents"
        else:
            reason = "intent-not-found"
    elif len(intents) == 1:
        selected = intents[0]
    elif len(intents) > 1:
        reason = "multiple-unresolved-tick-intents"

    if approval_journal_unavailable and reason == "ready":
        reason = "approval-journal-incomplete"
    elif approval_journal_events and selected is None and (intents or intent_request_id is not None or intent_digest is not None) and reason == "ready":
        reason = "approval-journal-incomplete"

    if selected is None and not corrupt_digests and not approval_journal_events and not approval_journal_unavailable and reason == "ready":
        return TickIntentReconciliationSnapshot(
            preview=TickIntentReconciliationPreview.create(
                required=False,
                recoverable=False,
                reason="no-unresolved-tick-intent",
                fill_identity_sha256=_fill_identity_sha256(latest),
                book_matches_ledger=False,
                head_matches_intent=False,
            ),
            intent_event=None,
        )

    intent_event = None
    intent_event_index = None
    expected_head = None
    if selected is not None:
        intent_event_index = next(
            (index for index, event in enumerate(events) if event.get("kind") == "tick_intent" and hashlib.sha256(_canonical_json(event)).hexdigest() == selected.intent_digest),
            None,
        )
        intent_event = events[intent_event_index] if intent_event_index is not None else None
        if intent_event is None:
            reason = "intent-not-found"
        elif "expected_head" in intent_event:
            observed_head = intent_event["expected_head"]
            if observed_head is None or isinstance(observed_head, str) and _SHA256.fullmatch(observed_head):
                expected_head = observed_head
    elif approval_journal_events and not intents and intent_request_id is None and intent_digest is None and reason == "ready":
        approval_heads = {journal_event.get("decision_hash") for _event_digest, journal_event, _event_offset in approval_journal_events}
        approval_head = next(iter(approval_heads), None)
        if len(approval_heads) != 1 or not isinstance(approval_head, str) or _SHA256.fullmatch(approval_head) is None:
            reason = "approval-journal-incomplete"
        else:
            expected_head = approval_head

    approval_journal_event_digests = ()
    if approval_journal_unavailable and reason == "ready":
        reason = "approval-journal-incomplete"
    elif approval_journal_events and selected is not None and intent_event_index is not None:
        offset_to_index = {offset: index for index, offset in enumerate(event_offsets)}
        unresolved_intent_events = []
        intent_digests = {item.intent_digest for item in intents}
        for index, event in enumerate(events):
            digest = hashlib.sha256(_canonical_json(event)).hexdigest() if event.get("kind") == "tick_intent" else None
            if digest in intent_digests:
                unresolved_intent_events.append((index, event, digest))
        resolved_journal_digests = []
        pending_as_of = state.pending.as_of if state.pending is not None else None
        for event_digest, journal_event, event_offset in approval_journal_events:
            journal_index = offset_to_index.get(event_offset)
            if journal_index is None or events[journal_index] != journal_event:
                reason = "approval-journal-incomplete"
                break
            if pending_as_of is None or journal_event.get("decision_as_of") != pending_as_of:
                reason = "approval-journal-incomplete"
                break
            matching_intents = [candidate for candidate in unresolved_intent_events if candidate[0] < journal_index and candidate[1].get("session") == journal_event.get("session") and candidate[1].get("expected_head") == journal_event.get("decision_hash")]
            if len(matching_intents) != 1 or matching_intents[0][2] != selected.intent_digest:
                reason = "approval-journal-incomplete"
                break
            resolved_journal_digests.append(event_digest)
        if reason == "ready" and len(resolved_journal_digests) == len(approval_journal_events):
            approval_journal_event_digests = tuple(sorted(resolved_journal_digests))
        else:
            approval_journal_event_digests = ()
    elif approval_journal_events and not intents and intent_request_id is None and intent_digest is None and reason == "ready":
        offset_to_index = {offset: index for index, offset in enumerate(event_offsets)}
        resolved_journal_digests = []
        for event_digest, journal_event, event_offset in approval_journal_events:
            journal_index = offset_to_index.get(event_offset)
            if journal_index is None or events[journal_index] != journal_event or (journal_event.get("kind") != "consume" and not (journal_event.get("kind") == "reject" and journal_event.get("consumed") is True)):
                reason = "approval-journal-incomplete"
                break
            resolved_journal_digests.append(event_digest)
        if reason == "ready" and len(resolved_journal_digests) == len(approval_journal_events):
            approval_journal_event_digests = tuple(sorted(resolved_journal_digests))
        else:
            approval_journal_event_digests = ()
    elif approval_journal_events and reason == "ready":
        reason = "approval-journal-incomplete"

    current_head = latest.hash if latest is not None else None
    ledger_head_matches = state.prev_hash == current_head
    if selected is None and approval_journal_events and not intents and intent_request_id is None and intent_digest is None and reason == "ready" and expected_head != current_head:
        reason = "ledger-head-changed"
    if reason == "ready" and not ledger_head_matches:
        reason = "ledger-head-changed"
    head_matches_intent = bool(expected_head == current_head and (intent_event is not None or approval_journal_event_digests))
    book_digest = None
    book_matches = False
    if reason == "ready" and deployed.broker != "paper":
        reason = "broker-not-local-paper"
    elif reason == "ready":
        from hedge_fund.brokers.paper import PaperBroker
        from hedge_fund.paths import read_bytes
        from hedge_fund.pipeline.session import BookMismatch, reconcile

        book_path = Path(directory) / "broker.json"
        try:
            before = read_bytes(book_path)
        except OSError:
            reason = "broker-book-unavailable"
        else:
            book_digest = hashlib.sha256(before).hexdigest()
            try:
                broker = PaperBroker(book_path, deployed.spec.costs)
                after = read_bytes(book_path)
            except (KeyError, OSError, TypeError, ValueError):
                reason = "broker-book-invalid"
            else:
                if before != after:
                    reason = "broker-book-changed"
                else:
                    try:
                        reconcile(state, broker, deployed.name)
                    except BookMismatch:
                        reason = "broker-book-mismatch"
                    else:
                        book_matches = True

    return TickIntentReconciliationSnapshot(
        preview=TickIntentReconciliationPreview.create(
            required=True,
            recoverable=reason == "ready" and book_matches and ledger_head_matches,
            reason=reason,
            intent_request_id=selected.request_id if selected is not None else intent_request_id,
            intent_session=selected.session if selected is not None else None,
            intent_digest=selected.intent_digest if selected is not None else intent_digest,
            metadata_complete=selected.metadata_complete if selected is not None else None,
            corrupt_event_digests=corrupt_digests,
            approval_journal_event_digests=approval_journal_event_digests,
            expected_head=expected_head,
            current_head=current_head,
            broker_book_sha256=book_digest,
            fill_identity_sha256=_fill_identity_sha256(latest),
            book_matches_ledger=book_matches,
            head_matches_intent=head_matches_intent,
        ),
        intent_event=intent_event,
    )


def tick_intent_reconciliation_targets(ledger) -> list[dict[str, object]]:
    return [
        {
            "intent_request_id": intent.request_id,
            "intent_session": intent.session,
            "intent_digest": intent.intent_digest,
            "recorded_at": intent.recorded_at,
            "metadata_complete": intent.metadata_complete,
        }
        for intent in ledger.unresolved_tick_intents()
        if not intent.is_corrupt and intent.intent_digest is not None
    ]


def verify_reconciliation_receipt(
    directory: str | Path,
    deployed,
    ledger,
    state,
    latest,
    receipt: ReconciliationReceipt,
) -> ReconciliationSnapshot:
    if not isinstance(receipt, ReconciliationReceipt):
        raise ValueError("verified reconciliation receipt is required")
    events = ledger.events()
    failure = next(
        (event for event in events if isinstance(event, dict) and event.get("kind") == "tick_failed" and failure_digest(event) == receipt.failure_id),
        None,
    )
    if failure is None or not receipt.matches_failure(failure):
        raise ValueError("reconciliation receipt does not match the failed operation")
    snapshot = build_reconciliation_snapshot(directory, deployed, ledger, state, latest, failure_event=failure)
    preview = snapshot.preview
    if not preview.recoverable or receipt.expected_head != preview.expected_head or receipt.current_head != preview.current_head or receipt.broker_book_sha256 != preview.broker_book_sha256 or receipt.fill_identity_sha256 != preview.fill_identity_sha256 or receipt.capture_id != preview.capture_id or receipt.capture_digest != preview.capture_digest:
        raise ValueError("reconciliation receipt no longer matches the paper state")
    return snapshot


def find_receipt_for_request(events: list[dict], request_id: str) -> ReconciliationReceipt | None:
    if not isinstance(events, list) or not isinstance(request_id, str) or not _REQUEST_ID.fullmatch(request_id):
        raise ValueError("reconciliation request identity is invalid")
    for event in reversed(events):
        if not isinstance(event, dict) or event.get("kind") != "reconciliation":
            continue
        try:
            receipt = ReconciliationReceipt.model_validate(event.get("receipt"))
        except (TypeError, ValueError):
            continue
        if receipt.request_id == request_id:
            return receipt
    return None


def _fill_identity_sha256(latest) -> str:
    executed = latest.executed if latest is not None else None
    return _receipt_digest(
        {
            "head_hash": latest.hash if latest is not None else None,
            "session": latest.session if latest is not None else None,
            "orders": [order.model_dump(mode="json") for order in executed.orders] if executed is not None else [],
            "fills": [fill.model_dump(mode="json") for fill in executed.fills] if executed is not None else [],
        }
    )


def _receipt_digest(value: dict) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


def _canonical_json(value: dict) -> bytes:
    if not isinstance(value, dict):
        raise ValueError("canonical identity must be an object")
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=True).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ValueError("canonical identity is invalid") from exc
