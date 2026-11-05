"""Advance a paper fund by exactly one session.

CLI provider dispatch requires invocation-local network enablement. Paid
authorization is one-shot; scheduled ticks use free data and local models.

It loads the fund, replays the ledger into its state, works out the next
session the fund owes, advances it, and appends the record. Calling it
twice is harmless: the second call finds nothing due. For a daily fund the
next session is the oldest unrecorded completed close: a missed day is
never skipped, and catching up after a week away takes a week of ticks,
each honest. For a minute fund it is the latest bar boundary that has
passed, at prints taken now: a bar is never back-filled, so a late tick
records the print it took and when it took it.

Any failure inside `advance` halts the fund. Cron retrying into a broken
book is the failure mode this exists to prevent; a human clears the halt.
"""

from __future__ import annotations

from contextlib import contextmanager, ExitStack
from datetime import date as _date
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable
from uuid import uuid4

from hedge_fund.brokers.account_binding import require_sim_account_ownership
from hedge_fund.brokers.factory import build_broker
from hedge_fund.brokers.models import Fill, Order
from hedge_fund.brokers.paper import PaperBroker
from hedge_fund.data.bars import (
    current_bar,
    is_intraday,
    is_last_bar,
    next_bar,
    previous_bar,
    session_date,
)
from hedge_fund.data.protocol import DataClient
from hedge_fund.data.sessions import (
    completed_through,
    NEW_YORK,
    previous_day,
    session_closes,
)
from hedge_fund.fund import Fund, FundSpec, TradingWindow
from hedge_fund.paper.deployed import BROKER_FILE, load_deployed
from hedge_fund.paper.ledger import (
    AuditObservationUnavailable,
    Ledger,
    LedgerError,
    PaperReconciliationRequired,
)
from hedge_fund.pipeline.clock import Clock, LiveClock, Marked
from hedge_fund.pipeline.session import (
    advance,
    FundHalted,
    FundState,
    is_rebalance_session,
    next_state,
    SessionRecord,
)

# A fresh fund starts at the most recent completed session; this is how far
# back to look for one (covers a long weekend plus a holiday cluster).
_FRESH_LOOKBACK_DAYS = 14


class NothingDue(RuntimeError):
    """Every session that can be run is already recorded."""


class RecordedClock:
    """A bar run again at the prices it saw. A print cannot be taken twice,
    so a redo of a bar serves the marks its record kept — the book's names,
    the benchmark, and whatever the executed decision was sized at. A name
    none of those cover has no honest price, and the redo says so."""

    def __init__(self, record: SessionRecord, interval_seconds: int, window: TradingWindow) -> None:
        self._record = record
        self._interval = interval_seconds
        self._window = window
        self._prices = {record.benchmark: record.benchmark_close, **record.marks}
        if record.executed is not None:
            self._prices = {**record.executed.marks, **self._prices}
        self._times = dict(record.snapshot_times or {})

    def is_complete(self, session: str) -> bool:
        return session <= self._record.session

    def previous(self, session: str) -> str:
        return previous_bar(session, self._interval, self._window)

    def session_date(self, session: str) -> str:
        return session_date(session)

    def marks(self, tickers: list[str], session: str) -> Marked:
        if session != self._record.session:
            raise ValueError(f"{session}: only {self._record.session} can be run again at recorded prices")
        missing = sorted(set(tickers) - set(self._prices))
        if missing:
            raise ValueError(f"{', '.join(missing)}: no recorded print at {session}; a bar can only be run " "again at the prices it saw")
        return Marked(
            prices={t: self._prices[t] for t in sorted(set(tickers))},
            times={t: self._times[t] for t in sorted(set(tickers)) if t in self._times} or None,
        )


def next_session(
    data_client: DataClient,
    spec: FundSpec,
    last_session: str | None,
    *,
    now: Callable[[], datetime] | None = None,
) -> str | None:
    """The next session the fund owes, or None when nothing is due yet.

    Daily cadences: the first benchmark session after *last_session*, or,
    for a fund that has never ticked, the most recent completed one. Minute
    cadence: the latest bar boundary at or before now, if it is newer than
    *last_session*; no network, the bar's prints are taken when it runs.
    """
    moment = now() if now is not None else None  # None: the engine's own clock
    if spec.is_intraday:
        bar = current_bar(moment or datetime.now(NEW_YORK), spec.interval_seconds, spec.window)
        if bar is None or (last_session is not None and bar <= last_session):
            return None
        return bar
    end = completed_through(moment)
    if last_session is None:
        start = (_date.fromisoformat(end) - timedelta(days=_FRESH_LOOKBACK_DAYS)).isoformat()
        closes = session_closes(data_client, spec.benchmark, start, end)
        return max(closes) if closes else None
    start = (_date.fromisoformat(session_date(last_session)) + timedelta(days=1)).isoformat()
    closes = session_closes(data_client, spec.benchmark, start, end)
    return min(closes) if closes else None


def following_session(spec: FundSpec, after: str | None, now: datetime) -> str:
    """When the session after the current one arrives, as a short phrase
    for a human: the next bar boundary, or the next weekday's close."""
    if spec.is_intraday:
        upcoming = next_bar(now, spec.interval_seconds, spec.window)
        same_day = upcoming.date() == now.astimezone(NEW_YORK).date()
        return upcoming.strftime("%H:%M:%S ET" if same_day else "%a %H:%M:%S ET")
    day = _date.fromisoformat(session_date(after)) if after else now.astimezone(NEW_YORK).date()
    day += timedelta(days=1)
    while day.weekday() >= 5:
        day += timedelta(days=1)
    return f"{day.isoformat()} close"


def previous_session(session: str, spec: FundSpec) -> str:
    """The session before *session* on the fund's own grid: the bar before
    a bar, the calendar day before a date (what `execute_decision` uses as
    the refresh cutoff)."""
    if is_intraday(session):
        return previous_bar(session, spec.interval_seconds, spec.window)
    return previous_day(session)


def assessment_dates(state: FundState, session: str, spec: FundSpec) -> list[str]:
    """The sessions the analysts are asked about when *session* is run from
    *state*: the session before it, to refresh a pending decision made
    earlier than that (`execute_decision` sizes from the refreshed views),
    and *session* itself when it opens a rebalance period (`advance` then
    makes a new decision)."""
    dates: list[str] = []
    before = previous_session(session, spec)
    if state.pending is not None and before != state.pending.as_of:
        dates.append(before)
    if is_rebalance_session(session, state.last_session, spec.rebalance):
        dates.append(session)
    return dates


def tick(
    directory: str | Path,
    data_client: DataClient,
    *,
    session: str | None = None,
    build_fund: Callable[[FundSpec], Fund] | None = None,
    now: Callable[[], datetime] | None = None,
    expected_head: str | None = None,
    operation_id: str | None = None,
    request_id: str | None = None,
    capture_id: str | None = None,
    capture_digest: str | None = None,
    on_progress: Callable[[int], None] | None = None,
) -> SessionRecord:
    """Advance the paper fund in *directory* by one session and record it.

    *session* is a backfill override: it must be the next unrecorded
    session. Passing a session that is already recorded returns its record
    unchanged (idempotent). Raises NothingDue when no session can be run
    yet (no completed close after the last one; no bar boundary passed; the
    benchmark has not printed today), FundHalted when the kill switch is
    set. *now* is the clock; tests inject it.
    """
    if on_progress is not None and not callable(on_progress):
        raise ValueError("paper tick progress callback must be callable")
    directory = Path(directory)
    operation_context = None
    if request_id is not None:
        from hedge_fund.paper.ledger import Ledger

        operation_values = (operation_id, capture_id, capture_digest)
        if any(value is not None for value in operation_values):
            from hedge_fund.runtime.reconciliation import TickOperationIdentity

            try:
                operation_context = TickOperationIdentity(
                    operation_id=operation_id,
                    request_id=request_id,
                    capture_id=capture_id,
                    capture_digest=capture_digest,
                ).model_dump(mode="json")
            except ValueError:
                raise ValueError("paper tick operation identity is invalid") from None
        else:
            operation_context = {"request_id": request_id}
        ledger = Ledger(directory)
        try:
            request_digest = ledger.tick_request_digest(
                request_id,
                expected_head=expected_head,
                session=session,
                operation_id=operation_id,
                capture_id=capture_id,
                capture_digest=capture_digest,
            )
        except ValueError:
            raise ValueError("paper tick operation identity is invalid") from None
        operation_context.update(
            {
                "request_action": "tick",
                "request_digest": request_digest,
                "expected_head": expected_head,
            }
        )
    elif any(value is not None for value in (operation_id, capture_id, capture_digest)):
        raise ValueError("paper tick operation identity is invalid")
    from hedge_fund.runtime.admission import (
        paper_execution_transition,
        PaperPreflightBusy,
    )

    with paper_execution_transition(directory, directory.name):
        if operation_context is not None:
            from hedge_fund.paper.ledger import Ledger, PaperTickNoWork

            ledger = Ledger(directory)
            try:
                replayed = ledger.tick_request_result(
                    request_id,
                    expected_head=expected_head,
                    session=session,
                    operation_id=operation_id,
                    capture_id=capture_id,
                    capture_digest=capture_digest,
                )
            except AuditObservationUnavailable as exc:
                raise PaperPreflightBusy("Paper preflight audit observation is occupied.") from exc
            except PaperTickNoWork as exc:
                raise NothingDue(str(exc)) from exc
            if replayed is not None:
                return replayed
            latest = ledger.latest()
            current_head = latest.hash if latest is not None else None
            if current_head != expected_head:
                raise LedgerError("paper ledger head changed before the tick request")
            if session is not None and session in ledger.sessions():
                record = ledger.read(session)
                ledger.log_event(
                    "tick",
                    request_id=request_id,
                    request_action="tick",
                    request_digest=operation_context["request_digest"],
                    expected_head=expected_head,
                    result={"session": record.session, "hash": record.hash},
                    durable=True,
                )
                return record
        try:
            return _tick(
                directory,
                data_client,
                session=session,
                build_fund=build_fund,
                now=now,
                operation_context=operation_context,
                on_progress=on_progress,
            )
        except NothingDue as exc:
            if operation_context is not None:
                ledger.log_event(
                    "tick_no_work",
                    request_id=request_id,
                    request_action="tick",
                    request_digest=operation_context["request_digest"],
                    expected_head=expected_head,
                    result={"outcome": "nothing-due", "message": str(exc)},
                    durable=True,
                )
            raise


@contextmanager
def _preflight_control(directory: Path, name: str):
    from hedge_fund.runtime.admission import (
        paper_control_transition,
        PaperControlBusy,
        PaperPreflightBusy,
    )

    with ExitStack() as stack:
        try:
            stack.enter_context(paper_control_transition(directory, name))
        except PaperControlBusy as exc:
            raise PaperPreflightBusy("Paper preflight control admission is occupied.") from exc
        try:
            yield
        except AuditObservationUnavailable as exc:
            raise PaperPreflightBusy("Paper preflight audit observation is occupied.") from exc


def _tick(
    directory: Path,
    data_client: DataClient,
    *,
    session: str | None,
    build_fund: Callable[[FundSpec], Fund] | None,
    now: Callable[[], datetime] | None,
    operation_context: dict | None,
    on_progress: Callable[[int], None] | None,
) -> SessionRecord:
    deployed = load_deployed(directory)
    if deployed.broker == "saxo":
        require_sim_account_ownership()
    spec = deployed.spec
    ledger = Ledger(directory)
    if session is not None and session in ledger.sessions():
        try:
            with _preflight_control(directory, deployed.name):
                ledger._require_completed_redo()
                ledger._require_completed_approval_publication()
                ledger._require_completed_approval_consumptions()
                return ledger.read(session)
        except PaperReconciliationRequired:
            ledger.halt("approval journal requires reconciliation")
            raise
    ledger._require_completed_redo()
    state = ledger.replay(spec.capital)
    if state.halted is not None:
        raise FundHalted(f"{deployed.name} is halted: {state.halted}")

    try:
        with _preflight_control(directory, deployed.name):
            ledger.require_ready_for_work(state, approval_required=spec.approval_required)
    except PaperReconciliationRequired:
        ledger.halt("approval journal requires reconciliation")
        raise

    due = next_session(data_client, spec, state.last_session, now=now)
    now = now or (lambda: datetime.now(NEW_YORK))
    if due is None:
        after = f"after {state.last_session}" if state.last_session else "yet"
        what = "bar" if spec.is_intraday else f"completed {spec.benchmark} session"
        raise NothingDue(f"{deployed.name}: no {what} {after}; next {following_session(spec, state.last_session, now())}")
    if session is not None and session != due:
        raise ValueError(f"{deployed.name}: session {session} is not the next unrecorded session ({due})")
    clock = None
    if spec.is_intraday:
        # The benchmark's print says whether the market is trading today; a
        # bar on a holiday is nothing due, not a failure. A held name's own
        # missing print is a failure of the bar and halts inside `_run`.
        clock = LiveClock(data_client, spec.interval_seconds, spec.window, now=now)
        benchmark = clock.observe([spec.benchmark], due)[spec.benchmark]
        if print_day(benchmark.time) < session_date(due):
            raise NothingDue(f"{deployed.name}: {spec.benchmark} has not printed today (market closed); " f"next {following_session(spec, state.last_session, now())}")
    if operation_context is not None:
        ledger.log_event(
            "tick_intent",
            request_id=operation_context["request_id"],
            request_action=operation_context["request_action"],
            request_digest=operation_context["request_digest"],
            expected_head=state.prev_hash,
            requested_session=session,
            session=due,
            **{key: operation_context[key] for key in ("operation_id", "capture_id", "capture_digest") if key in operation_context},
            durable=True,
        )
    if on_progress is not None:
        on_progress(35)
    return _run(
        directory,
        deployed,
        ledger,
        state,
        due,
        data_client,
        build_fund,
        clock=clock,
        operation_context=operation_context,
        on_progress=on_progress,
    )


def print_day(time: str) -> str:
    """The New York date a print's timestamp falls on."""
    return datetime.fromisoformat(time.replace("Z", "+00:00")).astimezone(NEW_YORK).date().isoformat()


def redo(
    directory: str | Path,
    data_client: DataClient,
    *,
    build_fund: Callable[[FundSpec], Fund] | None = None,
    on_rewind: Callable[[SessionRecord], None] | None = None,
    request_id: str | None = None,
    expected_head: str | None = None,
) -> SessionRecord:
    """Run the latest recorded session again and replace its record.

    For when the fund already ran today and you want it to look again:
    the analysts are asked afresh, the book is sized afresh, all at the same
    close. The old record leaves the chain for ledger/superseded/ (a redo is
    an event, not an erasure), the broker's book is put back to where it
    stood going into that session, and the session is advanced as if for
    the first time. Raises NothingDue when nothing has been recorded yet,
    FundHalted when the kill switch is set.
    """
    directory = Path(directory)
    from hedge_fund.runtime.admission import paper_execution_transition

    with paper_execution_transition(directory, directory.name):
        return _redo(
            directory,
            data_client,
            build_fund=build_fund,
            on_rewind=on_rewind,
            request_id=request_id,
            expected_head=expected_head,
        )


def _redo(
    directory: Path,
    data_client: DataClient,
    *,
    build_fund: Callable[[FundSpec], Fund] | None,
    on_rewind: Callable[[SessionRecord], None] | None,
    request_id: str | None,
    expected_head: str | None,
) -> SessionRecord:
    deployed = load_deployed(directory)
    if deployed.broker != "paper":
        raise ValueError(f"redo is only supported for paper broker funds, not {deployed.broker}")
    ledger = Ledger(directory)
    request_digest = None
    if request_id is not None:
        if expected_head is None:
            raise ValueError("redo expected head is required")
        replayed = ledger.redo_request_result(request_id, expected_head)
        if replayed is not None:
            return replayed
        latest = ledger.latest()
        current_head = latest.hash if latest is not None else None
        if current_head != expected_head:
            raise LedgerError("paper ledger head changed before the redo request")
        request_digest = ledger.redo_request_digest(request_id, expected_head)
    elif expected_head is not None:
        raise ValueError("redo request identity is invalid")
    ledger._require_completed_redo()
    state = ledger.replay(deployed.spec.capital)  # verifies the whole chain first
    if state.halted is not None:
        raise FundHalted(f"{deployed.name} is halted: {state.halted}")
    if state.last_session is None:
        raise NothingDue(f"{deployed.name}: no session recorded yet, nothing to run again")

    before = ledger.replay(deployed.spec.capital, before=state.last_session)
    superseded = ledger.latest()
    if superseded is None or superseded.session != state.last_session or superseded.hash != state.prev_hash:
        raise LedgerError("paper ledger changed before redo")
    from hedge_fund.runtime.admission import AdmissionError, paper_control_transition

    with paper_control_transition(directory, deployed.name):
        try:
            if ledger.halted() is not None:
                raise FundHalted(f"{deployed.name} is halted")
            if deployed.spec.approval_required:
                _verified_redo_approval(ledger, before, superseded)
            ledger.require_ready_for_work(state, approval_required=deployed.spec.approval_required)
            redo_id = ledger.begin_redo(
                superseded,
                request_id=request_id,
                request_digest=request_digest,
            )
            if request_id is not None:
                ledger.log_event(
                    "redo_intent",
                    request_id=request_id,
                    request_action="redo",
                    request_digest=request_digest,
                    expected_head=expected_head,
                    source_session=superseded.session,
                    source_hash=superseded.hash,
                    durable=True,
                )
            if deployed.spec.approval_required:
                if superseded.decision is not None:
                    ledger.log_event(
                        "expire",
                        decision_as_of=superseded.decision.as_of,
                        decision_hash=superseded.hash,
                        reason="decision redone",
                        durable=True,
                    )
                mailbox = ledger.approval()
                if mailbox is not None and (mailbox["decision_as_of"] == superseded.session or mailbox["decision_hash"] == superseded.hash):
                    ledger.clear_approval(expected=mailbox)
        except AuditObservationUnavailable:
            raise
        except (AdmissionError, LedgerError, OSError):
            ledger.halt("redo approval expiry unavailable")
            raise
    from hedge_fund.runtime.policy import AuthorizationDenied

    try:
        superseded = ledger.rewind()
        if on_rewind is not None:
            try:
                on_rewind(superseded)
            except AuthorizationDenied:
                ledger.halt("redo authorization denied after rewind")
                raise
        PaperBroker.restore(directory / BROKER_FILE, before.cash, before.positions, deployed.spec.costs)
        request_fields = (
            {
                "request_id": request_id,
                "request_action": "redo",
                "request_digest": request_digest,
                "expected_head": expected_head,
            }
            if request_id is not None
            else {}
        )
        ledger.log_event("redo", session=superseded.session, superseded=superseded.hash, **request_fields)
        clock = None
        if deployed.spec.is_intraday:  # a bar's prints are gone; run it at the ones it kept
            clock = RecordedClock(superseded, deployed.spec.interval_seconds, deployed.spec.window)
        redo_nonce = uuid4().hex if deployed.spec.approval_required and superseded.decision is not None else None
        record = _run(
            directory,
            deployed,
            ledger,
            before,
            superseded.session,
            data_client,
            build_fund,
            clock=clock,
            redo_nonce=redo_nonce,
            replay_record=superseded,
            active_redo_id=redo_id,
        )
        ledger.finish_redo(redo_id, record)
        if request_id is not None:
            ledger.log_event(
                "redo_completed",
                request_id=request_id,
                request_action="redo",
                request_digest=request_digest,
                result={"session": record.session, "hash": record.hash},
                durable=True,
            )
        return record
    except Exception as exc:
        try:
            if ledger.halted() is None:
                ledger.halt("redo failed after rewind")
        except Exception as halt_exc:
            raise PaperReconciliationRequired(f"redo failed after rewind ({type(exc).__name__}) and the emergency halt is unavailable ({type(halt_exc).__name__}); offline reconciliation is required") from exc
        raise


def _verified_redo_approval(
    ledger: Ledger,
    state: FundState,
    record: SessionRecord,
) -> dict[str, str] | None:
    if record.prev_hash != state.prev_hash:
        raise LedgerError("redo approval does not match the previous ledger head")
    if state.pending is None:
        if record.executed is not None:
            raise LedgerError("redo execution has no pending decision")
        return None
    if not isinstance(state.prev_hash, str):
        raise LedgerError("redo pending decision has no source hash")
    approval, _ = ledger.resolve_approval(
        state.pending.as_of,
        state.prev_hash,
        replay_session=record.session,
    )
    if record.executed is not None:
        if approval is None or approval["verdict"] != "approve" or record.executed.as_of != state.pending.as_of or record.executed.execution_as_of not in {None, record.session}:
            raise LedgerError("redo consumed approval is unavailable")
    elif approval is not None and approval["verdict"] == "approve":
        raise LedgerError("redo approval does not match the recorded execution")
    elif approval is None:
        event = ledger._latest_approval_event(state.pending.as_of, state.prev_hash, strict=True)
        if event is not None and (event.get("kind") in {"consume", "tick"} or event.get("consumed") is True):
            raise LedgerError("redo consumed approval is unavailable")
    return approval


def _run(
    directory: Path,
    deployed,
    ledger: Ledger,
    state,
    session: str,
    data_client: DataClient,
    build_fund: Callable[[FundSpec], Fund] | None,
    *,
    clock: Clock | None = None,
    fund: Fund | None = None,
    broker=None,
    redo_nonce: str | None = None,
    replay_record: SessionRecord | None = None,
    active_redo_id: str | None = None,
    operation_context: dict | None = None,
    on_progress: Callable[[int], None] | None = None,
) -> SessionRecord:
    """Advance one session from *state* and record it, halting on failure.
    *fund* lets a long-running caller keep one Fund (and its analysts'
    caches) across sessions instead of staffing a new one each time. A
    minute fund's closing bar also checkpoints the day, so tomorrow's
    replay starts from tonight."""
    from hedge_fund.runtime.admission import (
        paper_audit_transition,
        paper_control_transition,
        PaperPreflightBusy,
        WriterConflict,
    )

    with paper_control_transition(directory, deployed.name):
        ledger._require_completed_redo(active_redo_id=active_redo_id)
        ledger._require_completed_approval_publication()
    run_state = state
    clear_verdict = None
    consumed_verdict = None
    audit = None
    if deployed.spec.approval_required and state.pending is not None:
        if not isinstance(state.prev_hash, str):
            raise LedgerError("pending decision has no source hash")
        journal_attempted = False
        try:
            with paper_control_transition(directory, deployed.name):
                halted = ledger.halted()
                if halted is not None:
                    raise FundHalted(f"{deployed.name} is halted: {halted}")
                if replay_record is None:
                    approval, clear_verdict = ledger.resolve_approval(state.pending.as_of, state.prev_hash)
                    if approval is None:
                        event = ledger._latest_approval_event(state.pending.as_of, state.prev_hash, strict=True)
                        if event is not None and (event.get("kind") in {"consume", "tick"} or event.get("consumed") is True):
                            journal_attempted = True
                            raise LedgerError("approval consumption is incomplete; reconciliation is required")
                else:
                    approval = _verified_redo_approval(ledger, state, replay_record)
                    clear_verdict = ledger.approval()
                if approval is not None and replay_record is None:
                    fields = {
                        "decision_as_of": approval["decision_as_of"],
                        "decision_hash": approval["decision_hash"],
                        "approval_verdict": approval["verdict"],
                        "approval_by": approval["by"],
                        "session": session,
                    }
                    if "approval_id" in approval:
                        fields["approval_id"] = approval["approval_id"]
                    with paper_audit_transition(directory, deployed.name):
                        journal_attempted = True
                        ledger.log_event("consume", durable=True, **fields)
                if approval is None:
                    with paper_audit_transition(directory, deployed.name):
                        journal_attempted = True
                        ledger.log_event(
                            "expire",
                            decision_as_of=state.pending.as_of,
                            decision_hash=state.prev_hash,
                            reason="stale verdict" if clear_verdict is not None else "no verdict",
                            durable=True,
                        )
        except (AuditObservationUnavailable, WriterConflict) as exc:
            if journal_attempted:
                ledger.halt("approval journal requires reconciliation")
                raise
            raise PaperPreflightBusy("Paper preflight audit admission is occupied.") from exc
        except Exception:
            if journal_attempted:
                ledger.halt("approval journal requires reconciliation")
            raise
        if approval is not None:
            consumed_verdict = approval
            if approval["verdict"] == "reject":
                run_state = state.model_copy(update={"pending": None})
                audit = (
                    "reject",
                    {
                        "decision_as_of": state.pending.as_of,
                        "decision_hash": state.prev_hash,
                        "by": approval["by"],
                        "consumed": True,
                        "session": session,
                    },
                )
        else:
            run_state = state.model_copy(update={"pending": None})

    def record_fill(order: Order, fill: Fill) -> None:
        ledger.log_event("broker_fill", session=session, order=order.model_dump(mode="json"), fill=fill.model_dump(mode="json"))

    def check_effect_admission() -> None:
        from hedge_fund.runtime.admission import paper_control_transition

        with paper_control_transition(directory, deployed.name):
            halted = ledger.halted()
            if halted is not None:
                raise FundHalted(f"{deployed.name} is halted: {halted}")
            ledger._require_completed_redo(active_redo_id=active_redo_id)
            ledger._require_completed_approval_publication()

    try:
        with ExitStack() as publication:
            registry_reserved = False
            registry_observation = None

            def reserve_publication() -> None:
                nonlocal registry_reserved, registry_observation
                if not registry_reserved and deployed.broker == "paper":
                    from hedge_fund.runtime.handover import paper_effect_registry

                    registry_observation = publication.enter_context(paper_effect_registry(directory, deployed.name))
                    registry_reserved = True

            broker = broker or build_broker(deployed, directory=directory)
            fund = fund or (build_fund or Fund)(deployed.spec)
            halted = ledger.halted()
            if halted is not None:
                raise FundHalted(f"{deployed.name} is halted: {halted}")
            record = advance(
                fund,
                run_state,
                session,
                broker,
                data_client,
                deployed.universe,
                clock,
                on_fill=record_fill if deployed.broker == "saxo" else None,
                before_effect=check_effect_admission,
                before_order=reserve_publication,
                on_progress=on_progress,
            )
            if registry_observation is not None:
                registry_observation.close_observations()
            if redo_nonce is not None:
                record.redo_nonce = redo_nonce
                record.hash = record.compute_hash()
            ledger.append(record)
            if audit is not None:
                kind, fields = audit
                ledger.log_event(kind, **fields)
            tick_fields = {
                "session": session,
                "nav": record.nav,
                "executed": record.executed is not None,
                "decided": record.decision is not None,
            }
            if consumed_verdict is not None:
                tick_fields.update(
                    {
                        "decision_as_of": consumed_verdict["decision_as_of"],
                        "decision_hash": consumed_verdict["decision_hash"],
                        "approval_verdict": consumed_verdict["verdict"],
                        "approval_by": consumed_verdict["by"],
                    }
                )
                if "approval_id" in consumed_verdict:
                    tick_fields["approval_id"] = consumed_verdict["approval_id"]
            if operation_context is not None:
                tick_fields.update(operation_context)
                tick_fields["result"] = {"session": record.session, "hash": record.hash}
            ledger.log_event("tick", durable=operation_context is not None, **tick_fields)
            if clear_verdict is not None:
                with paper_control_transition(directory, deployed.name):
                    ledger.clear_approval(expected=clear_verdict)
            if is_intraday(session) and is_last_bar(session, deployed.spec.window):
                ledger.checkpoint(next_state(state, record))
            return record
    except FundHalted:
        raise
    except Exception as exc:
        reason = f"tick {session} failed: {type(exc).__name__}: {exc}"
        failure_fields = {"expected_head": state.prev_hash}
        if operation_context is not None:
            failure_fields.update(operation_context)
        try:
            ledger.log_event(
                "tick_failed",
                session=session,
                error=f"{type(exc).__name__}: {exc}",
                durable=operation_context is not None,
                **failure_fields,
            )
        finally:
            ledger.halt(reason)
        raise
