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

import json
import os
import re
from collections.abc import Callable
from datetime import datetime, timezone
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
        if (
            set(value) != {"version", "state", "approval_id"}
            or type(value["version"]) is not int
            or value["version"] != 1
            or not isinstance(value["state"], str)
            or value["state"] not in {"pending", "committed", "aborted"}
            or not isinstance(value["approval_id"], str)
            or _APPROVAL_ID.fullmatch(value["approval_id"]) is None
        ):
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
        if (
            set(value) != {"version", "state", "redo_id", "source_session", "source_hash", "result_hash"}
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
            or (
                value["state"] == "pending"
                and value["result_hash"] is not None
            )
            or (
                value["state"] == "completed"
                and (
                    not isinstance(value["result_hash"], str)
                    or _HASH.fullmatch(value["result_hash"]) is None
                )
            )
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

    def begin_redo(self, source: SessionRecord) -> str:
        self._require_write_lanes(_EXECUTION_LANES)
        self._require_completed_redo()
        redo_id = uuid4().hex
        value = {
            "version": 1,
            "state": "pending",
            "redo_id": redo_id,
            "source_session": source.session,
            "source_hash": source.hash,
            "result_hash": None,
        }
        write_atomic(self.redo_state_path, json.dumps(value, indent=2), mode=0o600, durable=True)
        return redo_id

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
        if event is not None and (
            event.get("kind") in {"consume", "tick"} or event.get("consumed") is True
        ):
            raise PaperReconciliationRequired("approval consumption is incomplete; reconciliation is required")

    def observe_approval_for_display(
        self, state: FundState, *, approval_required: bool
    ) -> dict[str, str] | None:
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
        self._require_write_lanes(_DEPLOYMENT_LANES)
        from hedge_fund.runtime.admission import paper_halt_transition

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
            keep.mkdir(exist_ok=True)
            safe = latest.session.replace(":", "")
            name = f"{safe}.{latest.hash[:12]}"
            target = keep / f"{name}.json"
            if target.exists():
                target = keep / f"{name}.{uuid4().hex}.json"
            self.path(latest.session).rename(target)
            checkpoint = self.checkpoint_path(session_date(latest.session))
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
        if not control["halted"]:
            return None
        reason = control.get("reason")
        if reason is not None and not isinstance(reason, str):
            raise LedgerError(f"{self.control_path}: kill switch reason is invalid")
        return reason or "halted"

    def halt(self, reason: str) -> None:
        self._require_write_lanes(_HALT_LANES)
        from hedge_fund.runtime.admission import AdmissionError, paper_halt_transition

        with paper_halt_transition(self.directory, self.directory.name):
            self._write_control(True, reason)
            try:
                self.log_event("halt", reason=reason)
            except (AdmissionError, LedgerError, OSError, ValueError) as exc:
                raise HaltAuditUnavailable(
                    "Halt was applied but its audit record is unavailable; reconciliation is required"
                ) from exc

    def resume(self) -> None:
        self._require_write_lanes(_CONTROL_LANES)
        raise LedgerError("Resume requires a verified reconciliation receipt.")

    def _write_control(self, halted: bool, reason: str | None) -> None:
        self._require_write_lanes(_HALT_LANES if halted is True else _CONTROL_LANES)
        write_atomic(
            self.control_path,
            json.dumps(
                {
                    "halted": halted,
                    "reason": reason,
                    "since": _now(),
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
        if "approval_id" in value and (
            not isinstance(value["approval_id"], str)
            or _APPROVAL_ID.fullmatch(value["approval_id"]) is None
        ):
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
        if (
            event["kind"] != mailbox["verdict"]
            or event.get("by") != mailbox["by"]
            or event.get("approval_id") != mailbox.get("approval_id")
        ):
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
        approval_tick = kind == "tick" and any(
            field in event
            for field in ("decision_as_of", "decision_hash", "approval_verdict", "approval_by", "approval_id")
        )
        if kind not in {"approve", "reject", "expire", "consume"} and not approval_tick:
            return True
        decision_as_of = event.get("decision_as_of")
        decision_hash = event.get("decision_hash")
        if not isinstance(decision_as_of, str) or not decision_as_of.strip():
            return False
        if not isinstance(decision_hash, str) or _HASH.fullmatch(decision_hash) is None:
            return False
        approval_id = event.get("approval_id")
        if "approval_id" in event and (
            not isinstance(approval_id, str) or _APPROVAL_ID.fullmatch(approval_id) is None
        ):
            return False
        if kind in {"approve", "reject"}:
            by = event.get("by")
            valid = isinstance(by, str) and by in {"cli", "tui", "web"} and (
                "consumed" not in event or isinstance(event["consumed"], bool)
            )
            if event.get("consumed") is True:
                return valid and isinstance(event.get("session"), str) and bool(event["session"])
            return valid
        if kind == "consume" or approval_tick:
            verdict = event.get("approval_verdict")
            by = event.get("approval_by")
            return (
                isinstance(verdict, str)
                and verdict in {"approve", "reject"}
                and isinstance(by, str)
                and by in {"cli", "tui", "web"}
                and isinstance(event.get("session"), str)
                and bool(event["session"])
            )
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
        return (
            kind == "reject"
            and event["consumed"] is True
            and isinstance(event.get("session"), str)
            and bool(event["session"])
            and set(event) == common | {"by", "consumed", "session"}
        )

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
            if event["kind"] in {"approve", "reject", "expire", "consume"} or (
                event["kind"] == "tick" and "decision_hash" in event
            ):
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
            if (
                source.hash != source.compute_hash()
                or record.hash != record.compute_hash()
                or record.prev_hash != source.hash
                or source.decision is None
                or source.decision.as_of != event["decision_as_of"]
                or record.executed is not None
            ):
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
        if strict and any(
            self._legacy_approval_event(event) and event.get("decision_as_of") == decision_as_of
            for event in events
        ):
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
        from hedge_fund.runtime.admission import PaperApprovalAdmission

        enrolled = self._require_write_lanes((("control",),))
        if enrolled and (
            not isinstance(admission, PaperApprovalAdmission)
            or not admission.matches(self.directory, self.directory.name)
        ):
            raise LedgerError("verified paper verdict admission is required")
        if not enrolled:
            from hedge_fund.runtime.admission import paper_control_transition

            with paper_control_transition(self.directory, self.directory.name):
                return self._publish_approval(verdict, decision_as_of, decision_hash, by, enrolled=False)
        return self._publish_approval(verdict, decision_as_of, decision_hash, by, enrolled=True)

    def _publish_approval(
        self,
        verdict: str,
        decision_as_of: str,
        decision_hash: str,
        by: str,
        *,
        enrolled: bool,
    ) -> dict[str, str]:
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
            if (
                latest is None
                or latest.hash != decision_hash
                or latest.decision is None
                or latest.decision.as_of != decision_as_of
            ):
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
            raise
        return value

    def clear_approval(self, expected: dict[str, str] | None = None) -> bool:
        """Clear the expected verdict while the enrolled control lane is held."""
        enrolled = self._require_write_lanes((("control",),))
        if not enrolled:
            from hedge_fund.runtime.admission import paper_control_transition

            with paper_control_transition(self.directory, self.directory.name):
                return self._clear_approval(expected)
        return self._clear_approval(expected)

    def _clear_approval(self, expected: dict[str, str] | None) -> bool:
        if expected is not None and self.approval() != expected:
            return False
        try:
            self.approval_path.unlink()
        except FileNotFoundError:
            return False
        except OSError as exc:
            fields = {}
            if expected is not None:
                fields = {
                    "decision_as_of": expected["decision_as_of"],
                    "decision_hash": expected["decision_hash"],
                }
            self.log_event("approval_clear_failed", error=type(exc).__name__, **fields)
            return False
        return True

    # ---- events -----------------------------------------------------------

    def log_event(self, kind: str, *, durable: bool = False, **fields) -> None:
        halt_event = kind == "halt"
        self._require_write_lanes(_HALT_LANES if halt_event else _CONTROL_LANES)
        from hedge_fund.runtime.admission import paper_audit_transition

        with paper_audit_transition(self.directory, self.directory.name, halt_event=halt_event):
            line = json.dumps({"time": _now(), "kind": kind, **fields}, default=str)
            with self.events_path.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")
                if durable:
                    handle.flush()
                    os.fsync(handle.fileno())

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
