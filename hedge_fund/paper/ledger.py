"""The ledger — a paper fund's append-only book of record.

One JSON file per session under ledger/, each SessionRecord carrying the
hash of the one before it. The fund's state (positions, cash, the pending
decision, the last session) is never stored on its own: it is rebuilt by
folding `next_state` over the chain, so there is nothing to drift. A gap,
a reordered file, or an edited record breaks the chain and `replay` refuses.

Layout, by cadence:

    ledger/2026-10-05.json                a daily fund's session
    ledger/2026-10-05/100500.json         a minute fund's 10:05:00 bar
    ledger/2026-10-05/checkpoint.json     the state after that day's last bar

A minute fund writes hundreds of records a day, so each day gets a
directory and, once it closes, a checkpoint: `replay` starts from the
newest checkpoint it can trust (its last session is still on the chain
with the hash it remembers) and folds forward from there. `replay(full=True)`
ignores checkpoints and verifies every link, as `aihf paper status --verify`
does. A checkpoint is a cache of the chain, never a substitute for it.

control.json is the kill switch. It is read into FundState.halted by
`replay`, and `advance` checks it first — so no client of the engine (CLI,
TUI, cron) can trade a halted fund by forgetting to look.

Corrupt `control.json` raises; a broken halt must fail loud. Corrupt
`pending-approval.json` means no verdict; a broken vote must never become yay.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from math import isfinite
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import uuid4

from hedge_fund.data.bars import is_intraday, session_date
from hedge_fund.paths import read_text, write_atomic
from hedge_fund.pipeline.session import FundState, next_state, SessionRecord

if TYPE_CHECKING:
    from hedge_fund.runtime.admission import PaperApprovalAdmission

LEDGER_SUBDIR = "ledger"
SUPERSEDED_SUBDIR = "superseded"  # records taken off the chain by a redo, kept
CHECKPOINT_FILE = "checkpoint.json"
CONTROL_FILE = "control.json"
APPROVAL_FILE = "pending-approval.json"
APPROVAL_PUBLICATION_FILE = "approval-publication.json"
REDO_STATE_FILE = "redo-state.json"
EVENTS_FILE = "events.jsonl"

_DAY = re.compile(r"\d{4}-\d{2}-\d{2}")
_BAR_FILE = re.compile(r"(\d{2})(\d{2})(\d{2})")
_HASH = re.compile(r"[0-9a-f]{64}")
_APPROVAL_ID = re.compile(r"[0-9a-f]{32}")
_REQUEST_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}")
_DEPLOYMENT_LANES = (("deployment",),)
_EXECUTION_LANES = (("runner", "execution"),)
_CONTROL_LANES = (("control",), ("runner", "execution"))
_HALT_LANES = (("halt",),) + _CONTROL_LANES


class LedgerError(RuntimeError):
    """The ledger is inconsistent, or an append would make it so."""


class ApprovalStale(LedgerError):
    """The reviewed decision is no longer the pending ledger head."""


class ApprovalHalted(LedgerError):
    """A halted fund cannot accept a verdict."""


class ApprovalExpired(LedgerError):
    """The reviewed decision was already expired or consumed."""


class PaperReconciliationRequired(LedgerError):
    """A previous paper-control transition has an uncertain outcome."""


class PaperRequestConflict(LedgerError):
    """A request ID was reused for another or already-failed control action."""


class PaperTickNoWork(LedgerError):
    """A tick request completed without a due session."""


class HaltAuditUnavailable(LedgerError):
    """The kill switch was written but its audit record was not."""


class AuditObservationUnavailable(LedgerError):
    """A stable paper audit observation could not be obtained."""


class Ledger:
    def __init__(self, directory: str | Path) -> None:
        self.directory = Path(directory)
        self.records_dir = self.directory / LEDGER_SUBDIR
        self.control_path = self.directory / CONTROL_FILE
        self.approval_path = self.directory / APPROVAL_FILE
        self.approval_publication_path = self.directory / APPROVAL_PUBLICATION_FILE
        self.redo_state_path = self.directory / REDO_STATE_FILE
        self.events_path = self.directory / EVENTS_FILE

    def _require_write_lanes(
        self,
        lane_sets: tuple[tuple[str, ...], ...],
        *,
        verify_inventory: bool = False,
    ) -> bool:
        from hedge_fund.runtime.admission import (
            AdmissionError,
            require_paper_write_lanes,
        )

        try:
            return require_paper_write_lanes(
                self.directory,
                self.directory.name,
                lane_sets=lane_sets,
                verify_inventory=verify_inventory,
            )
        except AdmissionError as exc:
            raise LedgerError(f"{self.directory}: paper write admission denied: {exc}") from exc

    def _transition_effect(self, effect: Callable[[], object]) -> None:
        """Run one enrolled root effect, failing closed as a ledger error."""
        from hedge_fund.runtime.handover import HandoverError
        from hedge_fund.runtime.root import RootPathError

        try:
            effect()
        except (HandoverError, RootPathError) as exc:
            raise LedgerError(f"{self.directory}: paper write effect denied: {exc}") from exc

    def _read_transition_state(self, path: Path, label: str) -> dict | None:
        try:
            value = json.loads(read_text(path))
        except FileNotFoundError:
            return None
        except (OSError, UnicodeError, ValueError) as exc:
            raise PaperReconciliationRequired(f"{label} state is unavailable; reconciliation is required") from exc
        if not isinstance(value, dict):
            raise PaperReconciliationRequired(f"{label} state is invalid; reconciliation is required")
        return value

    def _approval_publication_state(self) -> dict | None:
        value = self._read_transition_state(self.approval_publication_path, "approval publication")
        if value is None:
            return None
        if set(value) != {"version", "state", "approval_id"} or type(value["version"]) is not int or value["version"] != 1 or not isinstance(value["state"], str) or value["state"] not in {"pending", "committed", "aborted"} or not isinstance(value["approval_id"], str) or _APPROVAL_ID.fullmatch(value["approval_id"]) is None:
            raise PaperReconciliationRequired("approval publication state is invalid; reconciliation is required")
        return value

    def _require_completed_approval_publication(self) -> dict | None:
        value = self._approval_publication_state()
        if value is not None and value["state"] == "pending":
            raise PaperReconciliationRequired("approval publication is incomplete; reconciliation is required")
        if value is not None and value["state"] == "committed":
            mailbox = self.approval()
            if mailbox is not None and value["approval_id"] != mailbox.get("approval_id"):
                raise PaperReconciliationRequired("approval publication and mailbox disagree; reconciliation is required")
        return value

    def _write_approval_publication(self, approval_id: str, state: str) -> None:
        self._require_write_lanes((("control",),))
        write_atomic(
            self.approval_publication_path,
            json.dumps({"version": 1, "state": state, "approval_id": approval_id}, indent=2),
            mode=0o600,
            durable=True,
        )

    def _redo_state(self) -> dict | None:
        value = self._read_transition_state(self.redo_state_path, "redo")
        if value is None:
            return None
        fields = {"version", "state", "redo_id", "source_session", "source_hash", "result_hash"}
        request_fields = {"request_id", "request_digest"}
        if (
            frozenset(value) not in {frozenset(fields), frozenset(fields | request_fields)}
            or type(value["version"]) is not int
            or value["version"] != 1
            or not isinstance(value["state"], str)
            or value["state"] not in {"pending", "completed"}
            or not isinstance(value["redo_id"], str)
            or _APPROVAL_ID.fullmatch(value["redo_id"]) is None
            or not isinstance(value["source_session"], str)
            or not value["source_session"]
            or not isinstance(value["source_hash"], str)
            or _HASH.fullmatch(value["source_hash"]) is None
            or (value["state"] == "pending" and value["result_hash"] is not None)
            or (value["state"] == "completed" and (not isinstance(value["result_hash"], str) or _HASH.fullmatch(value["result_hash"]) is None))
            or ("request_id" in value and (not isinstance(value["request_id"], str) or _REQUEST_ID.fullmatch(value["request_id"]) is None or not isinstance(value["request_digest"], str) or _HASH.fullmatch(value["request_digest"]) is None))
        ):
            raise PaperReconciliationRequired("redo state is invalid; reconciliation is required")
        return value

    def _require_completed_redo(self, *, active_redo_id: str | None = None) -> None:
        value = self._redo_state()
        if active_redo_id is not None:
            if value is None or value["state"] != "pending" or value["redo_id"] != active_redo_id:
                raise PaperReconciliationRequired("active redo state changed; reconciliation is required")
        elif value is not None and value["state"] == "pending":
            raise PaperReconciliationRequired("interrupted redo requires reconciliation")

    def begin_redo(
        self,
        source: SessionRecord,
        *,
        request_id: str | None = None,
        request_digest: str | None = None,
    ) -> str:
        self._require_write_lanes(_EXECUTION_LANES)
        self._require_completed_redo()
        if request_id is not None:
            _validate_request_id(request_id)
            if not isinstance(request_digest, str) or _HASH.fullmatch(request_digest) is None:
                raise ValueError("redo request digest is invalid")
        elif request_digest is not None:
            raise ValueError("redo request identity is invalid")
        redo_id = uuid4().hex
        value = {
            "version": 1,
            "state": "pending",
            "redo_id": redo_id,
            "source_session": source.session,
            "source_hash": source.hash,
            "result_hash": None,
        }
        if request_id is not None:
            value.update({"request_id": request_id, "request_digest": request_digest})
        write_atomic(self.redo_state_path, json.dumps(value, indent=2), mode=0o600, durable=True)
        return redo_id

    def redo_request_digest(self, request_id: str, expected_head: str) -> str:
        _validate_request_id(request_id)
        if not isinstance(expected_head, str) or _HASH.fullmatch(expected_head) is None:
            raise ValueError("redo expected head is invalid")
        return _control_request_digest("redo", self.directory.name, {"expected_head": expected_head})

    def redo_request_result(self, request_id: str, expected_head: str) -> SessionRecord | None:
        """Return committed redo; pending rewind requests never repeat."""
        digest = self.redo_request_digest(request_id, expected_head)
        matches = [event for event in self.events() if isinstance(event, dict) and event.get("request_id") == request_id]
        if matches and any(event.get("request_action") != "redo" or event.get("request_digest") != digest for event in matches):
            raise PaperRequestConflict("request identity conflicts with durable paper history")
        completed = [event for event in matches if event.get("kind") == "redo_completed"]
        if completed:
            if len(completed) != 1:
                raise PaperReconciliationRequired("redo request result is duplicated; reconciliation is required")
            result = completed[0].get("result")
            if not isinstance(result, dict) or set(result) != {"session", "hash"}:
                raise PaperReconciliationRequired("redo request result is invalid; reconciliation is required")
            session = result.get("session")
            result_hash = result.get("hash")
            if not isinstance(session, str) or not session or not isinstance(result_hash, str) or _HASH.fullmatch(result_hash) is None:
                raise PaperReconciliationRequired("redo request result is invalid; reconciliation is required")
            try:
                record = self.read(session)
            except (LedgerError, OSError, ValueError) as exc:
                raise PaperReconciliationRequired("redo request record is unavailable; reconciliation is required") from exc
            if record.hash != result_hash:
                raise PaperReconciliationRequired("redo request record changed; reconciliation is required")
            return record
        if matches and any(event.get("kind") in {"redo_intent", "redo"} for event in matches):
            raise PaperReconciliationRequired("redo request outcome is uncertain; reconciliation is required")
        state = self._redo_state()
        if state is None or state.get("request_id") != request_id:
            if matches:
                raise PaperRequestConflict("request identity conflicts with durable paper history")
            return None
        if state["request_digest"] != digest:
            raise PaperRequestConflict("request identity conflicts with durable paper history")
        if state["state"] != "completed":
            raise PaperReconciliationRequired("redo request outcome is uncertain; reconciliation is required")
        try:
            record = self.read(state["source_session"])
        except (LedgerError, OSError, ValueError) as exc:
            raise PaperReconciliationRequired("redo request record is unavailable; reconciliation is required") from exc
        if record.hash != state["result_hash"]:
            raise PaperReconciliationRequired("redo request record changed; reconciliation is required")
        return record

    def finish_redo(self, redo_id: str, record: SessionRecord) -> None:
        self._require_write_lanes(_EXECUTION_LANES)
        self._require_completed_redo(active_redo_id=redo_id)
        value = self._redo_state()
        latest = self.latest()
        if value is None or latest is None or latest.hash != record.hash or value["source_session"] != record.session:
            raise PaperReconciliationRequired("redo result changed; reconciliation is required")
        value.update({"state": "completed", "result_hash": record.hash})
        write_atomic(self.redo_state_path, json.dumps(value, indent=2), mode=0o600, durable=True)

    def require_ready_for_work(self, state: FundState, *, approval_required: bool) -> None:
        self._require_completed_redo()
        self._require_completed_approval_publication()
        self._require_completed_approval_consumptions()
        if not approval_required or state.pending is None:
            return
        if not isinstance(state.prev_hash, str):
            raise PaperReconciliationRequired("pending decision has no source hash")
        event = self._latest_approval_event(state.pending.as_of, state.prev_hash, strict=True)
        if event is not None and (event.get("kind") in {"consume", "tick"} or event.get("consumed") is True):
            raise PaperReconciliationRequired("approval consumption is incomplete; reconciliation is required")

    def observe_approval_for_display(self, state: FundState, *, approval_required: bool) -> dict[str, str] | None:
        """Observe a stable approval state without granting execution authority."""
        self.require_ready_for_work(state, approval_required=approval_required)
        approval = None
        if state.pending is not None:
            if not isinstance(state.prev_hash, str):
                raise PaperReconciliationRequired("pending decision has no source hash")
            approval, _ = self.resolve_approval(state.pending.as_of, state.prev_hash)
        self.require_ready_for_work(state, approval_required=approval_required)
        if state.pending is not None:
            observed, _ = self.resolve_approval(state.pending.as_of, state.prev_hash)
            if observed != approval:
                raise PaperReconciliationRequired("approval changed during observation")
        self.require_ready_for_work(state, approval_required=approval_required)
        latest = self.latest()
        if (latest.hash if latest is not None else None) != state.prev_hash:
            raise PaperReconciliationRequired("ledger head changed during observation")
        return approval

    # ---- records ----------------------------------------------------------

    def init(self) -> None:
        """Create an empty ledger with the kill switch off."""
        enrolled = self._require_write_lanes(_DEPLOYMENT_LANES)
        from hedge_fund.runtime.admission import paper_halt_transition
        from hedge_fund.runtime.root import RootPathError

        if enrolled:
            try:
                with self._enrolled_root(_DEPLOYMENT_LANES, self.records_dir) as (root, relative):
                    root.mkdir(relative, parents=False)
            except RootPathError as exc:
                raise LedgerError(f"{self.directory}: ledger directory is unsafe: {exc}") from exc
        else:
            self.records_dir.mkdir(parents=True, exist_ok=True)
        with paper_halt_transition(self.directory, self.directory.name):
            if not self.control_path.exists():
                write_atomic(self.control_path, json.dumps({"halted": False}, indent=2))

    def sessions(self) -> list[str]:
        """Every recorded session, daily and bar alike, in chain order."""
        if not self.records_dir.exists():
            return []
        found: list[str] = []
        for entry in self.records_dir.iterdir():
            if entry.is_file() and entry.suffix == ".json" and _DAY.fullmatch(entry.stem):
                found.append(entry.stem)
            elif entry.is_dir() and _DAY.fullmatch(entry.name):
                for bar in entry.glob("*.json"):
                    match = _BAR_FILE.fullmatch(bar.stem)
                    if match:
                        found.append(f"{entry.name}T{':'.join(match.groups())}")
        return sorted(found)

    def days(self) -> list[str]:
        """The New York dates with at least one record, in order."""
        return sorted({session_date(s) for s in self.sessions()})

    def path(self, session: str) -> Path:
        if is_intraday(session):
            return self.records_dir / session_date(session) / f"{session[11:].replace(':', '')}.json"
        return self.records_dir / f"{session}.json"

    def read(self, session: str) -> SessionRecord:
        try:
            return SessionRecord.model_validate_json(self.path(session).read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise LedgerError(f"{self.path(session)}: cannot read session record: {exc}") from exc

    def records(self, *, since: str | None = None) -> list[SessionRecord]:
        """Every record in order; with *since*, only sessions at or after it."""
        return [self.read(s) for s in self.sessions() if since is None or s >= since]

    def latest(self) -> SessionRecord | None:
        sessions = self.sessions()
        return self.read(sessions[-1]) if sessions else None

    def append(self, record: SessionRecord) -> Path:
        """Append *record*, refusing a duplicate session, an out-of-order
        session, a broken hash chain, or a record whose hash is not its own."""
        self._require_write_lanes(_EXECUTION_LANES)
        from hedge_fund.runtime.handover import paper_inventory_transition

        with paper_inventory_transition(self.directory, self.directory.name, lane_sets=_EXECUTION_LANES) as transition:
            path = self.path(record.session)
            if path.exists():
                raise LedgerError(f"{record.fund}: session {record.session} is already recorded")
            latest = self.latest()
            if latest is not None and record.session <= latest.session:
                raise LedgerError(f"{record.fund}: session {record.session} is not after the last " f"recorded session {latest.session}")
            expected_prev = latest.hash if latest is not None else None
            if record.prev_hash != expected_prev:
                raise LedgerError(f"{record.fund}: session {record.session} does not chain to the " f"last recorded session ({latest.session if latest else 'none'})")
            if record.hash != record.compute_hash():
                raise LedgerError(f"{record.fund}: session {record.session} hash does not match its contents")
            if transition is not None:
                previous = transition.previous_entry
                if previous is None or previous["head_hash"] != expected_prev:
                    raise LedgerError(f"{self.directory.name}: enrolled ledger head changed")
                transition.expect_entry(
                    {
                        **previous,
                        "last_session": record.session,
                        "head_hash": record.hash,
                        "session_count": previous["session_count"] + 1,
                    }
                )
                relative = path.relative_to(self.directory)
                self._transition_effect(lambda: transition.mkdir(relative.parent))
                self._transition_effect(lambda: transition.write_text(relative, record.model_dump_json(indent=2)))
                return path
            path.parent.mkdir(parents=True, exist_ok=True)
            write_atomic(path, record.model_dump_json(indent=2))
            return path

    def rewind(self) -> SessionRecord:
        """Take the latest record off the chain so its session can be run
        again. The record is not destroyed: it moves to ledger/superseded/,
        named with its hash, where it no longer counts but can still be read.
        A checkpoint that remembered it is dropped. The broker's book is the
        caller's to restore."""
        self._require_write_lanes(_EXECUTION_LANES)
        from hedge_fund.runtime.handover import paper_inventory_transition

        with paper_inventory_transition(self.directory, self.directory.name, lane_sets=_EXECUTION_LANES) as transition:
            sessions = self.sessions()
            latest = self.read(sessions[-1]) if sessions else None
            if latest is None:
                raise LedgerError(f"{self.directory.name}: nothing recorded to rewind")
            if transition is not None:
                previous = transition.previous_entry
                if previous is None or previous["head_hash"] != latest.hash or previous["last_session"] != latest.session or previous["session_count"] != len(sessions):
                    raise LedgerError(f"{self.directory.name}: enrolled ledger head changed")
                transition.expect_entry(
                    {
                        **previous,
                        "last_session": sessions[-2] if len(sessions) > 1 else None,
                        "head_hash": latest.prev_hash,
                        "session_count": previous["session_count"] - 1,
                    }
                )
            keep = self.records_dir / SUPERSEDED_SUBDIR
            safe = latest.session.replace(":", "")
            name = f"{safe}.{latest.hash[:12]}"
            if transition is not None:
                keep_relative = keep.relative_to(self.directory)
                self._transition_effect(lambda: transition.mkdir(keep_relative, parents=False))
            else:
                keep.mkdir(exist_ok=True)
            target = keep / f"{name}.json"
            if target.exists():
                target = keep / f"{name}.{uuid4().hex}.json"
            checkpoint = self.checkpoint_path(session_date(latest.session))
            if transition is not None:
                source = self.path(latest.session).relative_to(self.directory)
                destination = target.relative_to(self.directory)
                self._transition_effect(lambda: transition.rename_file(source, destination))
                checkpoint_relative = checkpoint.relative_to(self.directory)
                self._transition_effect(lambda: transition.unlink_file(checkpoint_relative, missing_ok=True))
                return latest
            self.path(latest.session).rename(target)
            if checkpoint.exists():
                checkpoint.unlink()
            return latest

    def replay(
        self,
        capital: float,
        *,
        before: str | None = None,
        full: bool = False,
        on_verified: Callable[[SessionRecord], None] | None = None,
    ) -> FundState:
        """Fold the chain into the fund's current state, verifying every link
        it walks. With *before*, stop short of that session: the state the
        fund was in going into it. Starts from the newest trusted checkpoint
        before the stop unless *full*, which walks from the first record.
        Calls on_verified after each record passes chain checks."""
        state = FundState.initial(capital)
        sessions = self.sessions()
        if not full:
            checkpoint = self._trusted_checkpoint(sessions, before)
            if checkpoint is not None:
                state = checkpoint
                sessions = [s for s in sessions if s > checkpoint.last_session]
        for session in sessions:
            if before is not None and session >= before:
                break
            record = self.read(session)
            if record.session != session:
                raise LedgerError(f"{self.path(session)}: file is named {session} but records {record.session}")
            if record.prev_hash != state.prev_hash:
                raise LedgerError(f"{record.fund}: chain broken at session {session}")
            if record.hash != record.compute_hash():
                raise LedgerError(f"{record.fund}: session {session} has been altered since it was written")
            state = next_state(state, record)
            if on_verified is not None:
                on_verified(record)
        return state.model_copy(update={"halted": self.halted()})

    # ---- checkpoints ------------------------------------------------------

    def checkpoint_path(self, day: str) -> Path:
        return self.records_dir / day / CHECKPOINT_FILE

    def checkpoint(self, state: FundState) -> Path:
        """Remember *state* as the state after its last session's day. Only a
        state whose last session is the newest recorded one can be kept:
        a checkpoint is a shortcut to the chain's head, not a fork."""
        self._require_write_lanes(_EXECUTION_LANES)
        if state.last_session is None or not is_intraday(state.last_session):
            raise LedgerError(f"{self.directory.name}: only a minute fund's day is checkpointed")
        latest = self.latest()
        if latest is None or latest.session != state.last_session or latest.hash != state.prev_hash:
            raise LedgerError(f"{self.directory.name}: checkpoint for {state.last_session} does not match the chain's head")
        path = self.checkpoint_path(session_date(state.last_session))
        write_atomic(path, state.model_dump_json(exclude={"halted"}, indent=2))
        self.log_event("checkpoint", session=state.last_session)
        return path

    def _trusted_checkpoint(self, sessions: list[str], before: str | None) -> FundState | None:
        """The newest checkpoint whose last session is still on the chain with
        the hash it remembers, and which lies before *before*. Anything else
        is ignored, not an error: the chain is the truth, this is a cache."""
        if not self.records_dir.exists():
            return None
        recorded = set(sessions)
        days = sorted((p.parent.name for p in self.records_dir.glob(f"*/{CHECKPOINT_FILE}")), reverse=True)
        for day in days:
            if before is not None and day >= before[:10]:
                continue
            try:
                state = FundState.model_validate_json(self.checkpoint_path(day).read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if state.last_session not in recorded or (before is not None and state.last_session >= before):
                continue
            try:
                head = self.read(state.last_session)
            except LedgerError:
                continue
            if head.hash == state.prev_hash and head.hash == head.compute_hash():
                return state
        return None

    # ---- the kill switch --------------------------------------------------

    def halted(self) -> str | None:
        """The halt reason, or None when the fund may trade."""
        if not self.control_path.exists():
            return None
        try:
            control = json.loads(self.control_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise LedgerError(f"{self.control_path}: cannot read the kill switch: {exc}") from exc
        if not isinstance(control, dict) or not isinstance(control.get("halted"), bool):
            raise LedgerError(f"{self.control_path}: kill switch has no boolean halt state")
        request_fields = {"request_id", "request_action", "request_digest"}
        present = request_fields.intersection(control)
        if present and (present != request_fields or not isinstance(control["request_id"], str) or _REQUEST_ID.fullmatch(control["request_id"]) is None or control["request_action"] != "halt" or not isinstance(control["request_digest"], str) or _HASH.fullmatch(control["request_digest"]) is None or control["halted"] is not True):
            raise LedgerError(f"{self.control_path}: kill switch request identity is invalid")
        if not control["halted"]:
            return None
        reason = control.get("reason")
        if reason is not None and not isinstance(reason, str):
            raise LedgerError(f"{self.control_path}: kill switch reason is invalid")
        return reason or "halted"

    def halt(self, reason: str, *, request_id: str | None = None) -> None:
        if not isinstance(reason, str) or not reason.strip() or len(reason) > 240 or any(ord(char) < 32 or ord(char) == 127 for char in reason):
            raise ValueError("halt reason is invalid")
        request_digest = None
        request_fields = {}
        if request_id is not None:
            _validate_request_id(request_id)
            request_digest = _control_request_digest("halt", self.directory.name, {"reason": reason})
            request_fields = {
                "request_id": request_id,
                "request_action": "halt",
                "request_digest": request_digest,
            }
        self._require_write_lanes(_HALT_LANES)
        from hedge_fund.runtime.admission import AdmissionError, paper_halt_transition

        with paper_halt_transition(self.directory, self.directory.name):
            if request_id is not None:
                try:
                    previous = self.control_request_result(request_id, "halt", {"reason": reason})
                except PaperRequestConflict:
                    raise
                except LedgerError:
                    previous = None
                if previous is not None:
                    return
                current = self._halt_request_identity()
                if current is not None and current["request_id"] == request_id and current["request_digest"] != request_digest:
                    raise PaperRequestConflict("request identity conflicts with the active Halt state")
                try:
                    prior_events = self.events()
                except (LedgerError, OSError, UnicodeError, ValueError):
                    prior_events = []
                if not any(event.get("kind") == "halt_intent" and event.get("request_id") == request_id for event in prior_events):
                    try:
                        self.log_event(
                            "halt_intent",
                            reason=reason,
                            **request_fields,
                            durable=True,
                        )
                    except (AdmissionError, LedgerError, OSError, ValueError) as exc:
                        self._write_control(True, reason, request_id=request_id, request_digest=request_digest)
                        raise HaltAuditUnavailable("Halt was applied but its intent record is unavailable; reconciliation is required") from exc
                if current is not None and current["request_id"] == request_id:
                    if self.halted() != reason:
                        raise PaperReconciliationRequired("Halt state and request identity disagree; reconciliation is required")
                else:
                    self._write_control(True, reason, request_id=request_id, request_digest=request_digest)
            else:
                self._write_control(True, reason)
            try:
                self.log_event(
                    "halt",
                    reason=reason,
                    **request_fields,
                    **({"result": {"name": self.directory.name, "halted": True}} if request_id is not None else {}),
                    durable=request_id is not None,
                )
            except (AdmissionError, LedgerError, OSError, ValueError) as exc:
                raise HaltAuditUnavailable("Halt was applied but its audit record is unavailable; reconciliation is required") from exc
        return

    def _halt_request_identity(self) -> dict[str, str] | None:
        try:
            control = json.loads(self.control_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            return None
        if not isinstance(control, dict):
            return None
        fields = {"request_id", "request_action", "request_digest"}
        if not fields.issubset(control) or control.get("request_action") != "halt":
            return None
        request_id = control.get("request_id")
        request_digest = control.get("request_digest")
        if control.get("halted") is not True or not isinstance(request_id, str) or _REQUEST_ID.fullmatch(request_id) is None or not isinstance(request_digest, str) or _HASH.fullmatch(request_digest) is None:
            return None
        return {"request_id": request_id, "request_digest": request_digest}

    def control_request_result(self, request_id: str, action: str, payload: dict[str, object]) -> dict[str, object] | None:
        """Return a terminal control result; incomplete requests never repeat."""
        _validate_request_id(request_id)
        if action not in {"halt", "resume"}:
            raise ValueError("control action is invalid")
        if not isinstance(payload, dict):
            raise ValueError("control request payload is invalid")
        digest = _control_request_digest(action, self.directory.name, payload)
        try:
            events = self.events()
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            if action != "halt":
                raise PaperReconciliationRequired("control request history is unavailable; reconciliation is required") from exc
            identity = self._halt_request_identity()
            if identity is not None and identity["request_id"] == request_id:
                if identity["request_digest"] != digest:
                    raise PaperRequestConflict("request identity conflicts with durable control history") from exc
                return {"name": self.directory.name, "halted": True}
            return None
        matches = [event for event in events if isinstance(event, dict) and event.get("request_id") == request_id]
        if not matches:
            return None
        if any(event.get("request_action") != action or event.get("request_digest") != digest for event in matches):
            raise PaperRequestConflict("request identity conflicts with durable control history")
        completed_kind = "halt" if action == "halt" else "resume_completed"
        completed = [event for event in matches if event.get("kind") == completed_kind]
        if completed:
            results = [event.get("result") for event in completed]
            if any(not isinstance(result, dict) for result in results) or any(result != results[0] for result in results[1:]):
                raise PaperReconciliationRequired("control request result is invalid; reconciliation is required")
            result = results[0]
            if action == "halt":
                valid = result == {"name": self.directory.name, "halted": True}
            else:
                valid = set(result) == {"name", "halted", "reconciliation_id"} and result.get("name") == self.directory.name and result.get("halted") is False and (result.get("reconciliation_id") is None or isinstance(result.get("reconciliation_id"), str))
            if not valid:
                raise PaperReconciliationRequired("control request result is invalid; reconciliation is required")
            return result
        if action == "resume":
            receipts = [event for event in matches if event.get("kind") == "reconciliation"]
            resumes = [event for event in matches if event.get("kind") == "resume"]
            if len(receipts) > 1 or len(resumes) > 1:
                raise PaperReconciliationRequired("Resume request history is ambiguous; reconciliation is required")
            receipt = None
            if receipts:
                from hedge_fund.runtime.reconciliation import ReconciliationReceipt

                try:
                    receipt = ReconciliationReceipt.model_validate(receipts[0].get("receipt"))
                except (TypeError, ValueError):
                    raise PaperReconciliationRequired("Resume receipt is invalid; reconciliation is required") from None
                if receipt.request_id != request_id or receipt.failure_id != payload.get("failure_id") or receipt.operator != payload.get("operator") or receipt.decision != payload.get("decision"):
                    raise PaperReconciliationRequired("Resume receipt conflicts with its request; reconciliation is required")
            expected_receipt_id = receipt.receipt_id if receipt is not None else None
            if resumes:
                resume_event = resumes[0]
                head_hash = resume_event.get("head_hash")
                if (payload.get("failure_id") is not None and receipt is None) or resume_event.get("by") != payload.get("operator") or resume_event.get("reconciliation_id") != expected_receipt_id or (head_hash is not None and (not isinstance(head_hash, str) or _HASH.fullmatch(head_hash) is None)):
                    raise PaperReconciliationRequired("Resume event conflicts with its request; reconciliation is required")
            effect_intents = [event for event in matches if event.get("kind") == "resume_effect_intent"]
            if len(effect_intents) > 1:
                raise PaperReconciliationRequired("Resume request has multiple control-write intents; reconciliation is required")
            if effect_intents:
                effect = effect_intents[0]
                head_hash = effect.get("head_hash")
                if not resumes or effect.get("by") != payload.get("operator") or effect.get("reconciliation_id") != expected_receipt_id or effect.get("head_hash") != resumes[0].get("head_hash") or (head_hash is not None and (not isinstance(head_hash, str) or _HASH.fullmatch(head_hash) is None)):
                    raise PaperReconciliationRequired("Resume control-write intent conflicts with its request; reconciliation is required")
                raise PaperReconciliationRequired("Resume control write outcome is uncertain; reconciliation is required")
            if receipts or resumes:
                return None
        expected_intents = {"halt"} if action == "halt" else {"resume", "reconciliation", "resume_effect_intent"}
        if action == "halt" and any(event.get("kind") == "halt_intent" for event in matches):
            return None
        if any(event.get("kind") in expected_intents for event in matches):
            raise PaperReconciliationRequired("control request outcome is uncertain; inspect paper state")
        raise PaperRequestConflict("request identity conflicts with durable control history")

    def tick_request_digest(
        self,
        request_id: str,
        *,
        expected_head: str | None,
        session: str | None,
        operation_id: str | None = None,
        capture_id: str | None = None,
        capture_digest: str | None = None,
    ) -> str:
        _validate_tick_request_values(
            request_id,
            expected_head,
            session,
            operation_id,
            capture_id,
            capture_digest,
        )
        return _control_request_digest(
            "tick",
            self.directory.name,
            _tick_request_payload(expected_head, session, operation_id, capture_id, capture_digest),
        )

    def tick_request_result(
        self,
        request_id: str,
        *,
        expected_head: str | None,
        session: str | None,
        operation_id: str | None = None,
        capture_id: str | None = None,
        capture_digest: str | None = None,
    ) -> SessionRecord | None:
        """Return committed tick; uncertain or no-work requests never repeat."""
        digest = self.tick_request_digest(
            request_id,
            expected_head=expected_head,
            session=session,
            operation_id=operation_id,
            capture_id=capture_id,
            capture_digest=capture_digest,
        )
        try:
            events = self.events()
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise PaperReconciliationRequired("approval history is unavailable") from exc
        matches = [event for event in events if isinstance(event, dict) and event.get("request_id") == request_id]
        if not matches:
            return None
        if any(event.get("request_action") != "tick" or event.get("request_digest") != digest for event in matches):
            raise PaperRequestConflict("request identity conflicts with durable paper history")
        if any(event.get("kind") == "tick_failed" for event in matches):
            raise PaperReconciliationRequired("tick request outcome is uncertain; reconciliation is required")
        no_work = [event for event in matches if event.get("kind") == "tick_no_work"]
        if no_work:
            if len(no_work) != 1:
                raise PaperReconciliationRequired("tick no-work result is invalid; reconciliation is required")
            result = no_work[0].get("result")
            if not isinstance(result, dict) or set(result) != {"outcome", "message"} or result.get("outcome") != "nothing-due" or not isinstance(result.get("message"), str) or not result["message"]:
                raise PaperReconciliationRequired("tick no-work result is invalid; reconciliation is required")
            raise PaperTickNoWork(result["message"])
        completed = [event for event in matches if event.get("kind") == "tick"]
        if completed:
            if len(completed) != 1:
                raise PaperReconciliationRequired("tick request result is duplicated; reconciliation is required")
            result = completed[0].get("result")
            if not isinstance(result, dict) or set(result) != {"session", "hash"}:
                raise PaperReconciliationRequired("tick request result is invalid; reconciliation is required")
            result_session = result.get("session")
            result_hash = result.get("hash")
            if not isinstance(result_session, str) or not result_session or not isinstance(result_hash, str) or _HASH.fullmatch(result_hash) is None:
                raise PaperReconciliationRequired("tick request result is invalid; reconciliation is required")
            try:
                record = self.read(result_session)
            except (LedgerError, OSError, ValueError) as exc:
                raise PaperReconciliationRequired("tick request record is unavailable; reconciliation is required") from exc
            if record.hash != result_hash:
                raise PaperReconciliationRequired("tick request record changed; reconciliation is required")
            return record
        if any(event.get("kind") == "tick_intent" for event in matches):
            raise PaperReconciliationRequired("tick request outcome is uncertain; reconciliation is required")
        raise PaperRequestConflict("request identity conflicts with durable paper history")

    def resume_request_result(
        self,
        request_id: str,
        *,
        failure_id: str | None = None,
        preview_digest: str | None = None,
        decision: str | None = None,
        operator: str = "web",
    ) -> dict[str, object] | None:
        _validate_request_id(request_id)
        if not isinstance(operator, str) or operator not in {"cli", "tui", "web"}:
            raise ValueError("Resume operator identity is invalid.")
        values = (failure_id, preview_digest, decision)
        if any(value is not None for value in values) and any(value is None for value in values):
            raise ValueError("Resume confirmation fields must be supplied together.")
        if failure_id is not None and (not isinstance(failure_id, str) or _HASH.fullmatch(failure_id) is None):
            raise ValueError("Resume failure identity is invalid.")
        if preview_digest is not None and (not isinstance(preview_digest, str) or _HASH.fullmatch(preview_digest) is None):
            raise ValueError("Resume preview digest is invalid.")
        if decision is not None and decision != "confirm-paper-book-matches-ledger":
            raise ValueError("Resume decision is invalid.")
        return self.control_request_result(
            request_id,
            "resume",
            {
                "operator": operator,
                "failure_id": failure_id,
                "preview_digest": preview_digest,
                "decision": decision,
            },
        )

    def resume(
        self,
        capital: float | None = None,
        *,
        approval_required: bool = False,
        reconciliation: dict | None = None,
        request_id: str | None = None,
        operator: str = "web",
    ) -> str | None:
        if capital is None or isinstance(capital, bool) or not isinstance(capital, (int, float)) or not isfinite(capital) or capital <= 0:
            raise LedgerError("Resume requires valid mandate capital for full ledger replay.")
        if type(approval_required) is not bool:
            raise LedgerError("Resume approval policy is invalid.")
        if not isinstance(operator, str) or operator not in {"cli", "tui", "web"}:
            raise LedgerError("Resume operator identity is invalid.")
        from hedge_fund.runtime.reconciliation import (
            build_reconciliation_snapshot,
            failure_digest,
            find_receipt_for_request,
            ReconciliationConfirmation,
            ReconciliationReceipt,
            unresolved_tick_failures,
            verify_reconciliation_receipt,
        )

        try:
            confirmation = ReconciliationConfirmation.model_validate(reconciliation) if reconciliation is not None else None
        except ValueError:
            raise LedgerError("Resume confirmation is invalid.") from None
        if request_id is not None:
            _validate_request_id(request_id)
        if confirmation is not None:
            if request_id is None:
                request_id = confirmation.request_id
            elif request_id != confirmation.request_id:
                raise LedgerError("Resume request identity does not match its reconciliation confirmation.")
        request_digest = None
        request_fields = {}
        if request_id is not None:
            request_digest = _control_request_digest(
                "resume",
                self.directory.name,
                {
                    "operator": operator,
                    "failure_id": confirmation.failure_id if confirmation is not None else None,
                    "preview_digest": confirmation.preview_digest if confirmation is not None else None,
                    "decision": confirmation.decision if confirmation is not None else None,
                },
            )
            request_fields = {
                "request_id": request_id,
                "request_action": "resume",
                "request_digest": request_digest,
            }
        self._require_write_lanes(_CONTROL_LANES)
        from hedge_fund.paper.deployed import load_deployed
        from hedge_fund.runtime.admission import paper_control_transition

        with paper_control_transition(self.directory, self.directory.name):
            if request_id is not None:
                previous = self.resume_request_result(
                    request_id,
                    failure_id=confirmation.failure_id if confirmation is not None else None,
                    preview_digest=confirmation.preview_digest if confirmation is not None else None,
                    decision=confirmation.decision if confirmation is not None else None,
                    operator=operator,
                )
                if previous is not None:
                    return previous["reconciliation_id"]
            halted = self.halted()
            state = self.replay(capital, full=True)
            self.require_ready_for_work(state, approval_required=approval_required)
            latest = self.latest()
            events = self.events()
            pending_halt = self._halt_request_identity()
            if pending_halt is not None and not any(event.get("kind") == "halt" and event.get("request_id") == pending_halt["request_id"] and event.get("request_digest") == pending_halt["request_digest"] for event in events):
                raise PaperReconciliationRequired("Halt request audit is incomplete; reconciliation is required.")
            if any(event.get("kind") == "resume_effect_intent" and not _resume_effect_has_completion(events, index) for index, event in enumerate(events)):
                raise PaperReconciliationRequired("Resume control write outcome is uncertain; reconciliation is required.")
            receipt = None
            if halted is None:
                if confirmation is None:
                    raise LedgerError("Paper fund is not halted.")
                receipt = find_receipt_for_request(events, confirmation.request_id)
                if receipt is None or receipt.failure_id != confirmation.failure_id:
                    raise LedgerError("Resume request has no matching reconciliation receipt.")
                failure = next((event for event in events if event.get("kind") == "tick_failed" and failure_digest(event) == receipt.failure_id), None)
                if failure is None:
                    raise LedgerError("Resume receipt does not match a failed paper operation.")
                snapshot = build_reconciliation_snapshot(self.directory, load_deployed(self.directory), self, state, latest, failure_event=failure)
                if confirmation.preview_digest != snapshot.preview.preview_digest:
                    raise LedgerError("Resume confirmation is stale; review the current paper state.")
                try:
                    verify_reconciliation_receipt(self.directory, load_deployed(self.directory), self, state, latest, receipt)
                except ValueError:
                    raise LedgerError("Reconciliation receipt no longer matches the paper state.") from None
                if not any(event.get("kind") == "resume" and event.get("request_id") == confirmation.request_id and event.get("reconciliation_id") == receipt.receipt_id for event in events):
                    raise LedgerError("Completed Resume audit is unavailable.")
                return receipt.receipt_id

            failures = unresolved_tick_failures(events)
            if failures:
                if len(failures) != 1 or confirmation is None:
                    raise LedgerError("Resume requires a verified reconciliation receipt for the failed tick.")
                deployed = load_deployed(self.directory)
                snapshot = build_reconciliation_snapshot(self.directory, deployed, self, state, latest, failure_event=failures[0])
                if not snapshot.preview.recoverable or confirmation.failure_id != snapshot.preview.failure_id or confirmation.preview_digest != snapshot.preview.preview_digest:
                    raise LedgerError("Resume confirmation is stale or paper state is not reconcilable.")
                receipt = find_receipt_for_request(events, confirmation.request_id)
                if receipt is None:
                    receipt = ReconciliationReceipt.create(
                        failure_event=snapshot.failure_event,
                        request_id=confirmation.request_id,
                        current_head=snapshot.preview.current_head,
                        broker_book_sha256=snapshot.preview.broker_book_sha256,
                        fill_identity_sha256=snapshot.preview.fill_identity_sha256,
                        operator=operator,
                        recorded_at=_now(),
                    )
                    self.log_event(
                        "reconciliation",
                        time=receipt.recorded_at,
                        receipt=receipt.model_dump(mode="json"),
                        **request_fields,
                        durable=True,
                    )
                    receipt = find_receipt_for_request(self.events(), confirmation.request_id)
                    if receipt is None:
                        raise LedgerError("Reconciliation receipt could not be verified after writing.")
                if receipt.failure_id != confirmation.failure_id:
                    raise LedgerError("Resume request conflicts with its existing reconciliation receipt.")
                if confirmation.preview_digest != snapshot.preview.preview_digest:
                    raise LedgerError("Resume confirmation is stale; review the current paper state.")
                try:
                    verify_reconciliation_receipt(self.directory, deployed, self, state, latest, receipt)
                except ValueError:
                    raise LedgerError("Reconciliation receipt no longer matches the paper state.") from None
            elif confirmation is not None:
                receipt = find_receipt_for_request(events, confirmation.request_id)
                if receipt is None or receipt.failure_id != confirmation.failure_id:
                    raise LedgerError("Resume request has no matching reconciliation receipt.")
                failure = next((event for event in events if event.get("kind") == "tick_failed" and failure_digest(event) == receipt.failure_id), None)
                if failure is None:
                    raise LedgerError("Resume receipt does not match a failed paper operation.")
                deployed = load_deployed(self.directory)
                snapshot = build_reconciliation_snapshot(self.directory, deployed, self, state, latest, failure_event=failure)
                if confirmation.preview_digest != snapshot.preview.preview_digest:
                    raise LedgerError("Resume confirmation is stale; review the current paper state.")
                try:
                    verify_reconciliation_receipt(self.directory, deployed, self, state, latest, receipt)
                except ValueError:
                    raise LedgerError("Reconciliation receipt no longer matches the paper state.") from None
            elif any(event.get("kind") == "resume" and isinstance(event.get("reconciliation_id"), str) and not any(later.get("kind") == "halt" for later in events[index + 1 :]) for index, event in enumerate(events)):
                raise LedgerError("Resume requires the matching reconciliation request.")

            resume_fields = {
                "head_hash": latest.hash if latest is not None else None,
                "by": operator,
            }
            if request_id is not None:
                resume_fields.update(request_fields)
            if confirmation is not None and receipt is not None:
                resume_fields.update(
                    {
                        "reconciliation_id": receipt.receipt_id,
                    }
                )
            if not any(event.get("kind") == "resume" and event.get("request_id") == resume_fields.get("request_id") and event.get("reconciliation_id") == resume_fields.get("reconciliation_id") for event in events):
                self.log_event("resume", durable=True, **resume_fields)
            self.log_event("resume_effect_intent", durable=True, **resume_fields)
            self._write_control(False, None)
            result = {
                "name": self.directory.name,
                "halted": False,
                "reconciliation_id": receipt.receipt_id if receipt is not None else None,
            }
            self.log_event(
                "resume_completed",
                **resume_fields,
                result=result,
                durable=True,
            )
            return receipt.receipt_id if receipt is not None else None

    def _write_control(self, halted: bool, reason: str | None, *, request_id: str | None = None, request_digest: str | None = None) -> None:
        self._require_write_lanes(_HALT_LANES if halted is True else _CONTROL_LANES)
        if request_id is not None:
            _validate_request_id(request_id)
            if not isinstance(request_digest, str) or _HASH.fullmatch(request_digest) is None:
                raise ValueError("halt request digest is invalid")
        write_atomic(
            self.control_path,
            json.dumps(
                {
                    **{
                        "halted": halted,
                        "reason": reason,
                        "since": _now(),
                    },
                    **(
                        {
                            "request_id": request_id,
                            "request_action": "halt",
                            "request_digest": request_digest,
                        }
                        if request_id is not None
                        else {}
                    ),
                },
                indent=2,
            ),
        )

    # ---- approval mailbox ------------------------------------------------

    def approval(self) -> dict[str, str] | None:
        """Return a valid verdict; unreadable or malformed mailbox means none."""
        try:
            value = json.loads(self.approval_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            return None
        fields = {"verdict", "decision_as_of", "decision_hash", "decided_at", "by"}
        if not isinstance(value, dict) or set(value) not in (fields, fields | {"approval_id"}):
            return None
        verdict = value["verdict"]
        decision_as_of = value["decision_as_of"]
        decision_hash = value["decision_hash"]
        decided_at = value["decided_at"]
        by = value["by"]
        if not isinstance(verdict, str) or verdict not in {"approve", "reject"}:
            return None
        if not isinstance(decision_as_of, str) or not decision_as_of.strip():
            return None
        if not isinstance(decision_hash, str) or _HASH.fullmatch(decision_hash) is None:
            return None
        if not isinstance(decided_at, str) or not isinstance(by, str) or by not in {"cli", "tui", "web"}:
            return None
        if "approval_id" in value and (not isinstance(value["approval_id"], str) or _APPROVAL_ID.fullmatch(value["approval_id"]) is None):
            return None
        try:
            stamp = datetime.fromisoformat(decided_at.replace("Z", "+00:00"))
        except ValueError:
            return None
        if stamp.tzinfo is None:
            return None
        return value

    def resolve_approval(
        self,
        decision_as_of: str,
        decision_hash: str,
        *,
        replay_session: str | None = None,
    ) -> tuple[dict[str, str] | None, dict[str, str] | None]:
        self._require_completed_approval_publication()
        event = self._latest_approval_event(decision_as_of, decision_hash, strict=True)
        mailbox = self.approval()
        if replay_session is not None:
            if not isinstance(replay_session, str) or not replay_session:
                raise ValueError("replay session must be a non-empty string")
            return self._consumed_approval(event, decision_as_of, decision_hash, replay_session), mailbox
        if mailbox is None:
            return None, None
        if mailbox["decision_as_of"] != decision_as_of or mailbox["decision_hash"] != decision_hash:
            return None, mailbox
        if event is None or event.get("kind") not in {"approve", "reject"} or event.get("consumed") is True:
            return None, mailbox
        if event["kind"] != mailbox["verdict"] or event.get("by") != mailbox["by"] or event.get("approval_id") != mailbox.get("approval_id"):
            return None, mailbox
        return mailbox, mailbox

    def _consumed_approval(
        self,
        event: dict | None,
        decision_as_of: str,
        decision_hash: str,
        replay_session: str,
    ) -> dict[str, str] | None:
        if event is None or event.get("kind") != "tick" or event.get("session") != replay_session:
            return None
        verdict = event.get("approval_verdict")
        by = event.get("approval_by")
        decided_at = event.get("time")
        if verdict not in {"approve", "reject"} or by not in {"cli", "tui", "web"} or not isinstance(decided_at, str):
            return None
        value = {
            "verdict": verdict,
            "decision_as_of": decision_as_of,
            "decision_hash": decision_hash,
            "decided_at": decided_at,
            "by": by,
        }
        if "approval_id" in event:
            value["approval_id"] = event["approval_id"]
        return value

    @staticmethod
    def _valid_approval_event(event: dict) -> bool:
        kind = event["kind"]
        approval_tick = kind == "tick" and any(field in event for field in ("decision_as_of", "decision_hash", "approval_verdict", "approval_by", "approval_id"))
        if kind not in {"approve", "reject", "expire", "consume"} and not approval_tick:
            return True
        decision_as_of = event.get("decision_as_of")
        decision_hash = event.get("decision_hash")
        if not isinstance(decision_as_of, str) or not decision_as_of.strip():
            return False
        if not isinstance(decision_hash, str) or _HASH.fullmatch(decision_hash) is None:
            return False
        approval_id = event.get("approval_id")
        if "approval_id" in event and (not isinstance(approval_id, str) or _APPROVAL_ID.fullmatch(approval_id) is None):
            return False
        if kind in {"approve", "reject"}:
            by = event.get("by")
            valid = isinstance(by, str) and by in {"cli", "tui", "web"} and ("consumed" not in event or isinstance(event["consumed"], bool))
            if event.get("consumed") is True:
                return valid and isinstance(event.get("session"), str) and bool(event["session"])
            return valid
        if kind == "consume" or approval_tick:
            verdict = event.get("approval_verdict")
            by = event.get("approval_by")
            return isinstance(verdict, str) and verdict in {"approve", "reject"} and isinstance(by, str) and by in {"cli", "tui", "web"} and isinstance(event.get("session"), str) and bool(event["session"])
        return True

    @staticmethod
    def _legacy_approval_event(event: dict) -> bool:
        kind = event.get("kind")
        if kind not in {"approve", "reject", "expire"} or "decision_hash" in event:
            return False
        if not isinstance(event.get("decision_as_of"), str) or not event["decision_as_of"].strip():
            return False
        common = {"time", "kind", "decision_as_of"}
        if kind == "expire":
            return set(event) == common | {"reason"} and isinstance(event.get("reason"), str)
        by = event.get("by")
        if not isinstance(by, str) or by not in {"cli", "tui"}:
            return False
        if "consumed" not in event:
            return set(event) == common | {"by"}
        return kind == "reject" and event["consumed"] is True and isinstance(event.get("session"), str) and bool(event["session"]) and set(event) == common | {"by", "consumed", "session"}

    def _validated_approval_events(self) -> list[dict]:
        try:
            events = self.events()
        except (OSError, UnicodeError, ValueError) as exc:
            raise PaperReconciliationRequired("approval history is unavailable") from exc
        identity_bound = False
        for event in events:
            if not isinstance(event, dict) or not isinstance(event.get("kind"), str) or not isinstance(event.get("time"), str):
                raise PaperReconciliationRequired("approval history is unavailable")
            if self._legacy_approval_event(event):
                if identity_bound:
                    raise PaperReconciliationRequired("approval history is unavailable")
                continue
            if not self._valid_approval_event(event):
                raise PaperReconciliationRequired("approval history is unavailable")
            if event["kind"] in {"approve", "reject", "expire", "consume"} or (event["kind"] == "tick" and "decision_hash" in event):
                identity_bound = True
        return events

    def _require_completed_approval_consumptions(self) -> None:
        pending: dict[tuple[str, str, str, str, str], dict[str | None, list[int]]] = {}
        legacy: dict[tuple[str, str, str, str, str], int] = {}
        unbound_rejections: dict[str, int] = {}
        for event in self._validated_approval_events():
            kind = event["kind"]
            if self._legacy_approval_event(event):
                if kind == "reject" and event.get("consumed") is True:
                    self._require_legacy_rejection_record(event)
                    session = event["session"]
                    unbound_rejections[session] = unbound_rejections.get(session, 0) + 1
                continue
            if kind == "consume":
                key = (
                    event["decision_as_of"],
                    event["decision_hash"],
                    event["session"],
                    event["approval_verdict"],
                    event["approval_by"],
                )
                approval_id = event.get("approval_id")
                counts = pending.setdefault(key, {}).setdefault(approval_id, [0, 0])
                counts[0] += 1
            elif kind == "reject" and event.get("consumed") is True:
                key = (
                    event["decision_as_of"],
                    event["decision_hash"],
                    event["session"],
                    "reject",
                    event["by"],
                )
                matched = False
                for approval_id, counts in pending.get(key, {}).items():
                    if counts[0] and ("approval_id" not in event or event["approval_id"] == approval_id):
                        counts[0] -= 1
                        counts[1] += 1
                        matched = True
                        break
                if not matched:
                    legacy[key] = legacy.get(key, 0) + 1
            elif kind == "tick" and event.get("approval_verdict") in {"approve", "reject"}:
                key = (
                    event["decision_as_of"],
                    event["decision_hash"],
                    event["session"],
                    event["approval_verdict"],
                    event["approval_by"],
                )
                approval_id = event.get("approval_id")
                attempts = pending.get(key, {})
                counts = attempts.get(approval_id)
                if counts is not None:
                    counts[1 if counts[1] else 0] -= 1
                    if not any(counts):
                        del attempts[approval_id]
                    if not attempts:
                        del pending[key]
                elif legacy.get(key, 0):
                    legacy[key] -= 1
                    if legacy[key] == 0:
                        del legacy[key]
            elif kind == "tick" and isinstance(event.get("session"), str):
                session = event["session"]
                if unbound_rejections.get(session, 0):
                    unbound_rejections[session] -= 1
                    if unbound_rejections[session] == 0:
                        del unbound_rejections[session]
        if pending or legacy or unbound_rejections:
            raise PaperReconciliationRequired("approval consumption is incomplete; reconciliation is required")

    def _require_legacy_rejection_record(self, event: dict) -> None:
        try:
            sessions = self.sessions()
            index = sessions.index(event["session"])
            if index == 0:
                raise ValueError("legacy rejection has no source record")
            source = self.read(sessions[index - 1])
            record = self.read(event["session"])
            if source.hash != source.compute_hash() or record.hash != record.compute_hash() or record.prev_hash != source.hash or source.decision is None or source.decision.as_of != event["decision_as_of"] or record.executed is not None:
                raise ValueError("legacy rejection does not match the recorded decision")
        except (LedgerError, OSError, ValueError) as exc:
            raise PaperReconciliationRequired("legacy approval history requires reconciliation") from exc

    def _latest_approval_event(
        self,
        decision_as_of: str,
        decision_hash: str,
        *,
        strict: bool = False,
    ) -> dict | None:
        if strict:
            events = self._validated_approval_events()
        else:
            try:
                events = self.events()
            except (OSError, UnicodeError, ValueError):
                return None
        if strict and any(self._legacy_approval_event(event) and event.get("decision_as_of") == decision_as_of for event in events):
            raise PaperReconciliationRequired("legacy approval identity requires reconciliation")
        for event in reversed(events):
            if not isinstance(event, dict):
                continue
            if event.get("decision_as_of") != decision_as_of or event.get("decision_hash") != decision_hash:
                continue
            kind = event.get("kind")
            if kind in {"approve", "reject", "expire", "consume"}:
                return event
            if kind == "tick" and event.get("approval_verdict") in {"approve", "reject"}:
                return event
        return None

    def set_approval(
        self,
        verdict: str,
        decision_as_of: str,
        decision_hash: str,
        by: str,
        *,
        request_id: str | None = None,
        admission: PaperApprovalAdmission | None = None,
    ) -> dict[str, str]:
        if not isinstance(verdict, str) or verdict not in {"approve", "reject"}:
            raise ValueError("verdict must be 'approve' or 'reject'")
        if not isinstance(decision_as_of, str) or not decision_as_of.strip():
            raise ValueError("decision_as_of must be a non-empty string")
        if not isinstance(decision_hash, str) or _HASH.fullmatch(decision_hash) is None:
            raise ValueError("decision_hash must be a lowercase SHA-256 hash")
        if not isinstance(by, str) or by not in {"cli", "tui", "web"}:
            raise ValueError("by must be 'cli', 'tui' or 'web'")
        if request_id is not None:
            _validate_request_id(request_id)
        from hedge_fund.runtime.admission import PaperApprovalAdmission

        enrolled = self._require_write_lanes((("control",),))
        if enrolled and (not isinstance(admission, PaperApprovalAdmission) or not admission.matches(self.directory, self.directory.name)):
            raise LedgerError("verified paper verdict admission is required")
        if not enrolled:
            from hedge_fund.runtime.admission import paper_control_transition

            with paper_control_transition(self.directory, self.directory.name):
                return self._publish_approval(verdict, decision_as_of, decision_hash, by, request_id=request_id, enrolled=False)
        return self._publish_approval(verdict, decision_as_of, decision_hash, by, request_id=request_id, enrolled=True)

    def approval_request_result(
        self,
        request_id: str,
        verdict: str,
        decision_as_of: str,
        decision_hash: str,
        by: str,
    ) -> dict[str, str] | None:
        """Return committed verdict for a request; uncertain requests never replay."""
        _validate_request_id(request_id)
        if not isinstance(verdict, str) or verdict not in {"approve", "reject"}:
            raise ValueError("verdict must be 'approve' or 'reject'")
        if not isinstance(decision_as_of, str) or not decision_as_of.strip():
            raise ValueError("decision_as_of must be a non-empty string")
        if not isinstance(decision_hash, str) or _HASH.fullmatch(decision_hash) is None:
            raise ValueError("decision_hash must be a lowercase SHA-256 hash")
        if not isinstance(by, str) or by not in {"cli", "tui", "web"}:
            raise ValueError("by must be 'cli', 'tui' or 'web'")
        payload = {
            "verdict": verdict,
            "decision_as_of": decision_as_of,
            "decision_hash": decision_hash,
            "by": by,
        }
        digest = _control_request_digest("approval", self.directory.name, payload)
        return self._approval_request_result(request_id, digest)

    def approval_command_result(
        self,
        request_id: str,
        verdict: str,
        by: str,
        expected_head: str | None,
    ) -> dict[str, str] | None:
        """Return CLI verdict replay without requiring the pending head again."""
        _validate_request_id(request_id)
        if not isinstance(verdict, str) or verdict not in {"approve", "reject"} or not isinstance(by, str) or by not in {"cli", "tui", "web"}:
            raise ValueError("verdict request identity is invalid")
        matches = [event for event in self.events() if isinstance(event, dict) and event.get("request_id") == request_id]
        if not matches:
            return None
        if not isinstance(expected_head, str) or _HASH.fullmatch(expected_head) is None:
            raise PaperRequestConflict("request identity conflicts with durable control history")
        if any(event.get("request_action") != "approval" for event in matches):
            raise PaperRequestConflict("request identity conflicts with durable control history")
        digests = [event.get("request_digest") for event in matches]
        if not isinstance(digests[0], str) or _HASH.fullmatch(digests[0]) is None or any(digest != digests[0] for digest in digests[1:]):
            raise PaperReconciliationRequired("verdict request identity is invalid; reconciliation is required")
        result = self._approval_request_result(request_id, digests[0])
        if result is not None:
            if result["verdict"] != verdict or result["by"] != by or result["decision_hash"] != expected_head:
                raise PaperRequestConflict("request identity conflicts with durable control history")
            return result
        if any(event.get("kind") == "approval_abort" for event in matches):
            raise PaperRequestConflict("verdict request already completed without a saved approval")
        raise PaperReconciliationRequired("verdict request outcome is uncertain; inspect paper state")

    def _approval_request_result(self, request_id: str, request_digest: str) -> dict[str, str] | None:
        matches = [event for event in self.events() if isinstance(event, dict) and event.get("request_id") == request_id]
        if not matches:
            return None
        if any(event.get("request_action") != "approval" or event.get("request_digest") != request_digest for event in matches):
            raise PaperRequestConflict("request identity conflicts with durable control history")
        committed = [event for event in matches if event.get("kind") == "approval_commit"]
        if committed:
            event = committed[-1]
            result = {
                "verdict": event.get("verdict"),
                "decision_as_of": event.get("decision_as_of"),
                "decision_hash": event.get("decision_hash"),
                "decided_at": event.get("decided_at"),
                "by": event.get("by"),
                "approval_id": event.get("approval_id"),
            }
            if result["verdict"] not in {"approve", "reject"} or not isinstance(result["decision_as_of"], str) or not isinstance(result["decision_hash"], str) or _HASH.fullmatch(result["decision_hash"]) is None or not isinstance(result["decided_at"], str) or result["by"] not in {"cli", "tui", "web"} or not isinstance(result["approval_id"], str) or _APPROVAL_ID.fullmatch(result["approval_id"]) is None:
                raise PaperReconciliationRequired("verdict request result is invalid; reconciliation is required")
            return result
        if any(event.get("kind") == "approval_abort" for event in matches):
            raise PaperRequestConflict("verdict request already completed without a saved approval")
        if any(event.get("kind") in {"approve", "reject"} for event in matches):
            raise PaperReconciliationRequired("verdict request outcome is uncertain; inspect paper state")
        raise PaperRequestConflict("request identity conflicts with durable control history")

    def _publish_approval(
        self,
        verdict: str,
        decision_as_of: str,
        decision_hash: str,
        by: str,
        *,
        request_id: str | None,
        enrolled: bool,
    ) -> dict[str, str]:
        request_digest = None
        request_fields = {}
        if request_id is not None:
            request_digest = _control_request_digest(
                "approval",
                self.directory.name,
                {
                    "verdict": verdict,
                    "decision_as_of": decision_as_of,
                    "decision_hash": decision_hash,
                    "by": by,
                },
            )
            previous = self._approval_request_result(request_id, request_digest)
            if previous is not None:
                return previous
            request_fields = {
                "request_id": request_id,
                "request_action": "approval",
                "request_digest": request_digest,
            }
        self._require_completed_approval_publication()
        latest_event = self._latest_approval_event(decision_as_of, decision_hash, strict=True)
        if latest_event is not None:
            if latest_event.get("kind") == "expire":
                raise ApprovalExpired("decision has expired")
            if latest_event.get("kind") in {"consume", "tick"} or latest_event.get("consumed") is True:
                raise ApprovalExpired("decision has already been consumed")
        self._require_completed_approval_consumptions()
        self._require_completed_redo()
        if self.halted() is not None:
            raise ApprovalHalted("fund is halted")
        if enrolled:
            latest = self.latest()
            if latest is None or latest.hash != decision_hash or latest.decision is None or latest.decision.as_of != decision_as_of:
                raise ApprovalStale("pending decision changed")
        value = {
            "verdict": verdict,
            "decision_as_of": decision_as_of,
            "decision_hash": decision_hash,
            "decided_at": _now(),
            "by": by,
            "approval_id": uuid4().hex,
        }
        self._write_approval_publication(value["approval_id"], "pending")
        publication_attempted = False
        try:
            self.log_event(
                verdict,
                decision_as_of=decision_as_of,
                decision_hash=decision_hash,
                by=by,
                approval_id=value["approval_id"],
                **request_fields,
            )
            write_atomic(self.approval_path, json.dumps({**value, "pending": True}, indent=2))
            if self.halted() is not None:
                self.log_event(
                    "expire",
                    decision_as_of=decision_as_of,
                    decision_hash=decision_hash,
                    reason="fund halted while verdict was saved",
                    durable=True,
                )
                self.clear_approval()
                raise ApprovalHalted("fund is halted")
            publication_attempted = True
            from hedge_fund.runtime.admission import paper_halt_transition

            with paper_halt_transition(self.directory, self.directory.name):
                if self.halted() is not None:
                    raise ApprovalHalted("fund is halted")
                write_atomic(self.approval_path, json.dumps(value, indent=2))
                self._write_approval_publication(value["approval_id"], "committed")
                if request_id is not None:
                    self.log_event(
                        "approval_commit",
                        **request_fields,
                        verdict=verdict,
                        decision_as_of=decision_as_of,
                        decision_hash=decision_hash,
                        by=by,
                        approval_id=value["approval_id"],
                        decided_at=value["decided_at"],
                        durable=True,
                    )
        except Exception:
            if publication_attempted:
                try:
                    self.log_event(
                        "expire",
                        decision_as_of=decision_as_of,
                        decision_hash=decision_hash,
                        reason="verdict publication failed",
                        durable=True,
                    )
                except Exception as exc:
                    try:
                        self.halt("verdict publication outcome requires reconciliation")
                    except Exception as halt_exc:
                        raise LedgerError("verdict publication and halt outcomes are uncertain; offline reconciliation is required") from halt_exc
                    raise LedgerError("verdict publication outcome is uncertain; fund halted for reconciliation") from exc
                self.clear_approval()
            try:
                self._write_approval_publication(value["approval_id"], "aborted")
            except (OSError, ValueError, LedgerError) as exc:
                raise PaperReconciliationRequired("approval publication cleanup failed; reconciliation is required") from exc
            if request_id is not None:
                try:
                    self.log_event(
                        "approval_abort",
                        **request_fields,
                        verdict=verdict,
                        decision_as_of=decision_as_of,
                        decision_hash=decision_hash,
                        by=by,
                        approval_id=value["approval_id"],
                        durable=True,
                    )
                except Exception as exc:
                    raise PaperReconciliationRequired("verdict request outcome is unavailable; reconciliation is required") from exc
            raise
        return value

    def clear_approval(self, expected: dict[str, str] | None = None) -> bool:
        """Clear the expected verdict while the enrolled control lane is held."""
        enrolled = self._require_write_lanes((("control",),))
        if not enrolled:
            from hedge_fund.runtime.admission import paper_control_transition

            with paper_control_transition(self.directory, self.directory.name):
                return self._clear_approval(expected)
        return self._clear_approval(expected, enrolled=True)

    def _unlink_enrolled(self, path: Path) -> None:
        """Recheck the control lane, then unlink without following reparse points."""
        with self._enrolled_root((("control",),), path) as (root, relative):
            root.unlink_file(relative)

    @contextmanager
    def _enrolled_root(self, lane_sets: tuple[tuple[str, ...], ...], path: Path) -> Iterator[tuple[object, str]]:
        """Recheck lanes and authority, then expose one root-relative no-follow target."""
        from hedge_fund.runtime.root import RootContext

        if not self._require_write_lanes(lane_sets):
            raise LedgerError(f"{self.directory.name}: enrolled admission changed")
        directory = Path(os.path.abspath(self.directory))
        relative = path.relative_to(self.directory).as_posix()
        with RootContext.open(directory.parent.parent) as root:
            yield root, f"{directory.parent.name}/{directory.name}/{relative}"

    def _clear_approval(self, expected: dict[str, str] | None, *, enrolled: bool = False) -> bool:
        from hedge_fund.runtime.root import RootPathError

        if expected is not None and self.approval() != expected:
            return False
        try:
            if enrolled:
                self._unlink_enrolled(self.approval_path)
            else:
                self.approval_path.unlink()
        except FileNotFoundError:
            return False
        except (OSError, RootPathError) as exc:
            fields = {}
            if expected is not None:
                fields = {
                    "decision_as_of": expected["decision_as_of"],
                    "decision_hash": expected["decision_hash"],
                }
            try:
                self.log_event("approval_clear_failed", error=type(exc).__name__, **fields)
            except RootPathError:
                if enrolled:
                    return False
                raise
            return False
        return True

    # ---- events -----------------------------------------------------------

    def log_event(self, kind: str, *, durable: bool = False, **fields) -> None:
        halt_event = kind in {"halt_intent", "halt"}
        self._require_write_lanes(_HALT_LANES if halt_event else _CONTROL_LANES)
        from hedge_fund.runtime.admission import paper_audit_transition
        from hedge_fund.runtime.root import RootContext

        with paper_audit_transition(self.directory, self.directory.name, halt_event=halt_event):
            line = json.dumps({"time": _now(), "kind": kind, **fields}, default=str)
            self._require_write_lanes(_HALT_LANES if halt_event else _CONTROL_LANES)
            with RootContext.open(self.directory) as root:
                root.append_bytes(EVENTS_FILE, (line + "\n").encode("utf-8"), durable=durable)

    def events(self) -> list[dict]:
        from hedge_fund.runtime.admission import (
            AdmissionError,
            paper_audit_snapshot,
            PaperAuditObservationBusy,
        )

        def read() -> list[dict]:
            try:
                text = self.events_path.read_text(encoding="utf-8")
            except FileNotFoundError:
                return []
            return [json.loads(line) for line in text.splitlines() if line.strip()]

        try:
            return paper_audit_snapshot(self.directory, self.directory.name, read)
        except PaperAuditObservationBusy as exc:
            raise AuditObservationUnavailable("paper audit observation is temporarily unavailable") from exc
        except AdmissionError as exc:
            raise LedgerError("paper audit observation failed") from exc


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _tick_request_payload(
    expected_head: str | None,
    session: str | None,
    operation_id: str | None,
    capture_id: str | None,
    capture_digest: str | None,
) -> dict[str, object]:
    return {
        "expected_head": expected_head,
        "session": session,
        "operation_id": operation_id,
        "capture_id": capture_id,
        "capture_digest": capture_digest,
    }


def _validate_tick_request_values(
    request_id: object,
    expected_head: object,
    session: object,
    operation_id: object,
    capture_id: object,
    capture_digest: object,
) -> None:
    _validate_request_id(request_id)
    if expected_head is not None and (not isinstance(expected_head, str) or _HASH.fullmatch(expected_head) is None):
        raise ValueError("expected_head must be a lowercase SHA-256 hash or None")
    if session is not None and (not isinstance(session, str) or not session or len(session) > 64):
        raise ValueError("tick session identity is invalid")
    operation_values = (operation_id, capture_id, capture_digest)
    if any(value is not None for value in operation_values):
        if not isinstance(operation_id, str) or _APPROVAL_ID.fullmatch(operation_id) is None or not isinstance(capture_id, str) or _APPROVAL_ID.fullmatch(capture_id) is None or not isinstance(capture_digest, str) or _HASH.fullmatch(capture_digest) is None:
            raise ValueError("tick operation identity is invalid")


def _control_request_digest(action: str, subject: str, payload: dict[str, object]) -> str:
    record = {"action": action, "subject": subject, "payload": payload}
    encoded = json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _resume_effect_has_completion(events: list[dict], index: int) -> bool:
    intent = events[index]
    identity_keys = ("request_id", "request_digest", "head_hash", "by", "reconciliation_id")
    return any(event.get("kind") == "resume_completed" and all(event.get(key) == intent.get(key) for key in identity_keys) for event in events[index + 1 :])


def _validate_request_id(value: object) -> str:
    if not isinstance(value, str) or _REQUEST_ID.fullmatch(value) is None:
        raise ValueError("request_id must be a bounded opaque identifier")
    return value
