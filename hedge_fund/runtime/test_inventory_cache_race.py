"""Cooperating paper commits and root-bound caches share one inventory."""

from __future__ import annotations

import time
from pathlib import Path
from threading import current_thread, Event, Thread

import pytest
import yaml

from hedge_fund import paths
from hedge_fund.data.cached import CachedDataClient
from hedge_fund.fund import FundSpec
from hedge_fund.llm.cache import PromptCache
from hedge_fund.paper.deployed import deploy, load_deployed
from hedge_fund.paper.ledger import Ledger
from hedge_fund.pipeline.session import code_version, mandate_hash, SessionRecord
from hedge_fund.runtime.admission import AdmissionCoordinator, RootOwnerLease
from hedge_fund.runtime.handover import (
    enroll_fresh,
    enrollment_status,
    HandoverError,
    LedgerDrift,
    LedgerHeadPublicationError,
    require_enrollment,
    verify_ledger_head,
    verify_root_inventory,
)
from hedge_fund.runtime.root import RootConfigurationError, RootContext


def _spec(name: str) -> FundSpec:
    return FundSpec.model_validate(
        {
            "schema_version": 2,
            "name": name,
            "strategies": [
                {
                    "name": "solo",
                    "models": [{"name": "pead"}],
                    "blend": {"mode": "long_short"},
                }
            ],
            "risk": {"max_position_pct": 1, "max_gross_exposure": 1},
            "capital": 100_000,
            "rebalance": "daily",
        }
    )


@pytest.fixture
def enrolled_funds(tmp_path):
    root_path = tmp_path / "root"
    root_path.mkdir()
    with RootContext.open(root_path) as root:
        enroll_fresh(root)
        with RootOwnerLease.acquire(root) as owner:
            admission = AdmissionCoordinator(root, owner_lease=owner)
            for name in ("alpha", "beta"):
                with admission.deployment_lock(name):
                    deploy(name, _spec(name), ["AAPL"], root=root_path / "paper")
            with paths.bound_root(root):
                yield root, admission


class _OfflineData:
    def get_company_facts(self, _ticker):
        return None


def _write_cache(kind, root):
    if kind == "data":
        CachedDataClient(
            _OfflineData(),
            cache_dir=root.path / "cache" / "data",
        ).get_company_facts("AAPL")
    elif kind == "prompt":
        PromptCache(root.path / "cache" / "llm").put("synthetic", {"value": 1})
    elif kind == "root-status":
        assert enrollment_status(root, verify_inventory=True)["state"] == "enrolled"
    else:
        assert verify_ledger_head(root, "beta") is not None


def _record(spec: FundSpec) -> SessionRecord:
    record = SessionRecord(
        fund=spec.name,
        session="2024-06-07",
        universe=["AAPL"],
        nav=spec.capital,
        cash=spec.capital,
        positions={},
        marks={},
        benchmark=spec.benchmark,
        benchmark_close=100.0,
        rebalance=True,
        code_version=code_version(),
        mandate_hash=mandate_hash(spec),
    )
    record.hash = record.compute_hash()
    return record


def _after_record_write(monkeypatch, action):
    """Run ``action(path)`` after an enrolled ledger record effect writes its bytes."""
    from hedge_fund.runtime.handover import PaperInventoryTransition

    original = PaperInventoryTransition.write_text

    def write_then_act(self, relative, text):
        original(self, relative, text)
        action(Path(self._root.path, *self._base, relative))

    monkeypatch.setattr(PaperInventoryTransition, "write_text", write_then_act)


@pytest.mark.parametrize("kind", ["data", "prompt", "root-status", "head-check"])
def test_cache_waits_for_another_funds_append_and_head_publication(
    enrolled_funds,
    monkeypatch,
    kind,
):
    from hedge_fund.runtime import admission as admission_module

    root, admission = enrolled_funds
    spec = _spec("alpha")
    ledger = Ledger(root.path / "paper" / "alpha")
    record = _record(spec)
    written = Event()
    release = Event()
    cache_attempted = Event()
    cache_finished = Event()
    failures = []
    lock_held = []

    def pause_after_append(path):
        if path == ledger.path(record.session):
            lock_held.append(admission.lane_is_held("registry"))
            written.set()
            if not release.wait(timeout=10):
                raise TimeoutError("test did not release ledger publication")

    _after_record_write(monkeypatch, pause_after_append)

    def append_alpha():
        try:
            with admission.manual_session("alpha", timeout=5):
                ledger.append(record)
        except BaseException as exc:
            failures.append(exc)

    def cache_beta():
        try:
            with admission.manual_session("beta", timeout=5):
                cache_attempted.set()
                _write_cache(kind, root)
        except BaseException as exc:
            failures.append(exc)
        finally:
            cache_finished.set()

    writer = Thread(target=append_alpha, name="alpha-commit")
    cache = Thread(target=cache_beta, name="beta-cache")
    writer.start()
    try:
        assert written.wait(timeout=10)
        cache.start()
        assert cache_attempted.wait(timeout=10)
        key = admission_module._thread_lock_key(
            root,
            f"{admission_module.LOCK_DIRECTORY}/registry.lock",
        )
        deadline = time.monotonic() + 10
        queued_behind_writer = False
        while time.monotonic() < deadline and not cache_finished.is_set():
            with admission_module._LOCAL_LANES_GUARD:
                queued_behind_writer = len(admission_module._LOCAL_LANES.get(key, ())) >= 2
            if queued_behind_writer:
                break
            time.sleep(0.01)
    finally:
        release.set()
        writer.join(timeout=10)
        if cache.ident is not None:
            cache.join(timeout=10)

    assert not writer.is_alive() and not cache.is_alive()
    assert queued_behind_writer, failures
    assert lock_held == [True]
    assert failures == []
    assert cache_finished.is_set()
    verify_root_inventory(root)
    assert ledger.latest().hash == record.hash


def test_sibling_registry_contention_cannot_strand_a_paper_fill(enrolled_funds, monkeypatch):
    from datetime import datetime
    from importlib import import_module

    from hedge_fund.backtesting.test_fund import FakeAnalyst, FakeDataClient, SERIES
    from hedge_fund.brokers.paper import PaperBroker
    from hedge_fund.data.sessions import NEW_YORK
    from hedge_fund.fund import Fund
    from hedge_fund.runtime import handover

    root, admission = enrolled_funds
    directory = root.path / "paper" / "beta"
    paper_tick = import_module("hedge_fund.paper.tick")
    next_dates = iter(["2024-06-03", "2024-06-04"])
    monkeypatch.setattr(paper_tick, "next_session", lambda *_args, **_kwargs: next(next_dates))
    monkeypatch.setattr(handover, "MAX_LOCK_WAIT_SECONDS", 0.3)
    build_fund = lambda value: Fund(value, models={"solo": [FakeAnalyst("pead", {"AAPL": 1})]})
    client = FakeDataClient(SERIES)
    with admission.manual_session("beta"):
        first = paper_tick.tick(
            directory,
            client,
            now=lambda: datetime(2024, 6, 5, 12, tzinfo=NEW_YORK),
            build_fund=build_fund,
        )
    assert first.decision is not None

    filled = Event()
    attempted = Event()
    acquired = Event()
    release = Event()
    failures = []
    records = []
    place_order = PaperBroker.place_order

    def pause_after_fill(broker, order):
        fill = place_order(broker, order)
        filled.set()
        if not attempted.wait(timeout=10):
            raise TimeoutError("sibling did not attempt the registry")
        acquired.wait(timeout=0.25)
        return fill

    def tick_beta():
        try:
            with admission.manual_session("beta", timeout=5):
                records.append(
                    paper_tick.tick(
                        directory,
                        client,
                        now=lambda: datetime(2024, 6, 5, 12, tzinfo=NEW_YORK),
                        build_fund=build_fund,
                    )
                )
        except BaseException as exc:
            failures.append(exc)

    def hold_sibling_registry():
        try:
            if not filled.wait(timeout=10):
                raise TimeoutError("beta did not place a synthetic order")
            attempted.set()
            with admission.registry_lock(timeout=5):
                acquired.set()
                if not release.wait(timeout=10):
                    raise TimeoutError("test did not release sibling registry")
        except BaseException as exc:
            failures.append(exc)

    monkeypatch.setattr(PaperBroker, "place_order", pause_after_fill)
    sibling = Thread(target=hold_sibling_registry, name="sibling-registry")
    worker = Thread(target=tick_beta, name="beta-paper-tick")
    sibling.start()
    worker.start()
    try:
        worker.join(timeout=10)
        assert not worker.is_alive()
    finally:
        release.set()
        sibling.join(timeout=10)
        worker.join(timeout=10)
    assert not sibling.is_alive()
    latest = Ledger(directory).latest()
    book_positions = PaperBroker(directory / "broker.json").positions()
    assert failures == [], f"failures={failures!r}, fill={filled.is_set()}, sibling_registry={acquired.is_set()}, " f"book_positions={book_positions!r}, recorded_session={latest.session if latest else None}"
    assert len(records) == 1
    assert records[0].executed is not None
    assert latest.hash == records[0].hash
    verify_root_inventory(root)


def test_sibling_registry_contention_before_order_does_not_change_book(enrolled_funds, monkeypatch):
    from contextlib import contextmanager
    from datetime import datetime
    from importlib import import_module

    from hedge_fund.backtesting.test_fund import FakeAnalyst, FakeDataClient, SERIES
    from hedge_fund.brokers.paper import PaperBroker
    from hedge_fund.data.sessions import NEW_YORK
    from hedge_fund.fund import Fund
    from hedge_fund.runtime import handover
    from hedge_fund.runtime.admission import WriterConflict

    root, admission = enrolled_funds
    directory = root.path / "paper" / "beta"
    paper_tick = import_module("hedge_fund.paper.tick")
    dates = iter(["2024-06-03", "2024-06-04"])
    monkeypatch.setattr(paper_tick, "next_session", lambda *_args, **_kwargs: next(dates))
    monkeypatch.setattr(handover, "MAX_LOCK_WAIT_SECONDS", 0.3)
    build_fund = lambda value: Fund(value, models={"solo": [FakeAnalyst("pead", {"AAPL": 1})]})
    client = FakeDataClient(SERIES)
    with admission.manual_session("beta"):
        first = paper_tick.tick(
            directory,
            client,
            now=lambda: datetime(2024, 6, 5, 12, tzinfo=NEW_YORK),
            build_fund=build_fund,
        )
    assert first.decision is not None
    book_before = (directory / "broker.json").read_bytes()
    reserving = Event()
    acquired = Event()
    release = Event()
    failures = []
    reserve = handover.paper_effect_registry

    @contextmanager
    def wait_for_sibling(*args, **kwargs):
        reserving.set()
        if not acquired.wait(timeout=10):
            raise TimeoutError("sibling did not acquire the registry")
        with reserve(*args, **kwargs):
            yield

    def hold_sibling_registry():
        try:
            if not reserving.wait(timeout=10):
                raise TimeoutError("paper tick did not reserve publication")
            with admission.registry_lock(timeout=5):
                acquired.set()
                if not release.wait(timeout=10):
                    raise TimeoutError("test did not release sibling registry")
        except BaseException as exc:
            failures.append(exc)

    monkeypatch.setattr(handover, "paper_effect_registry", wait_for_sibling)
    monkeypatch.setattr(PaperBroker, "place_order", lambda *_args: pytest.fail("order reached a contended registry"))
    sibling = Thread(target=hold_sibling_registry, name="sibling-registry-before-order")
    sibling.start()
    try:
        with admission.manual_session("beta"):
            with pytest.raises(WriterConflict):
                paper_tick.tick(
                    directory,
                    client,
                    now=lambda: datetime(2024, 6, 5, 12, tzinfo=NEW_YORK),
                    build_fund=build_fund,
                    expected_head=first.hash,
                    request_id="registry-contention-before-order",
                )
    finally:
        release.set()
        sibling.join(timeout=10)
    assert not sibling.is_alive()
    assert failures == []
    assert (directory / "broker.json").read_bytes() == book_before
    ledger = Ledger(directory)
    assert ledger.latest().hash == first.hash
    # QA R1: pre-effect contention aborts without halting.
    aborts = [event for event in ledger.events() if event.get("kind") == "tick_aborted" and event.get("request_id") == "registry-contention-before-order"]
    assert len(aborts) == 1
    assert aborts[0]["no_effects"] is True
    assert ledger.halted() is None
    verify_root_inventory(root)


def test_intraday_snapshot_workers_can_verify_head_while_publication_is_reserved(enrolled_funds, monkeypatch):
    from hedge_fund.data.models import PriceSnapshot
    from hedge_fund.pipeline.clock import LiveClock
    from hedge_fund.runtime import handover

    root, admission = enrolled_funds
    directory = root.path / "paper" / "beta"
    monkeypatch.setattr(handover, "MAX_LOCK_WAIT_SECONDS", 0.3)

    class GuardedSnapshots:
        def get_snapshot(self, ticker):
            handover.verify_ledger_head(root, "beta")
            return PriceSnapshot(ticker=ticker, price=100, time="2024-06-04T15:00:00Z")

    clock = LiveClock(GuardedSnapshots(), 60, _spec("beta").window)
    with admission.manual_session("beta"):
        with handover.paper_effect_registry(directory, "beta"):
            observed = clock.observe(["AAPL", "MSFT"], "2024-06-04T11:00:00")
    assert set(observed) == {"AAPL", "MSFT"}


def test_reserved_intraday_observation_still_rejects_external_drift(enrolled_funds, monkeypatch):
    from hedge_fund.pipeline.clock import LiveClock
    from hedge_fund.runtime import handover

    root, admission = enrolled_funds
    directory = root.path / "paper" / "beta"
    monkeypatch.setattr(handover, "MAX_LOCK_WAIT_SECONDS", 0.3)

    class GuardedSnapshots:
        def get_snapshot(self, _ticker):
            handover.verify_root_inventory(root)
            pytest.fail("unexplained inventory drift was accepted")

    clock = LiveClock(GuardedSnapshots(), 60, _spec("beta").window)
    with admission.manual_session("beta"):
        with handover.paper_effect_registry(directory, "beta"):
            fund_file = root.path / "paper" / "alpha" / "fund.yaml"
            fund_file.write_bytes(fund_file.read_bytes() + b"\n")
            with pytest.raises(handover.LedgerDrift):
                clock.observe(["AAPL"], "2024-06-04T11:00:00")


def test_reserved_observation_finishes_before_publication_and_cannot_be_reused(enrolled_funds):
    from hedge_fund.runtime import handover

    root, admission = enrolled_funds
    directory = root.path / "paper" / "beta"
    entered = Event()
    release = Event()
    failures = []

    def observe():
        entered.set()
        if not release.wait(timeout=10):
            raise TimeoutError("test did not release inventory observation")
        handover.verify_ledger_head(root, "beta")

    def use_window(window):
        try:
            handover._run_with_paper_observation(window, observe)
        except BaseException as exc:
            failures.append(exc)

    def release_when_closing(window):
        with window._condition:
            while window._accepting:
                window._condition.wait(timeout=0.01)
        release.set()

    with admission.manual_session("beta"):
        with handover.paper_effect_registry(directory, "beta") as window:
            assert window is not None
            worker = Thread(target=use_window, args=(window,), name="reserved-observer")
            releaser = Thread(target=release_when_closing, args=(window,), name="observation-releaser")
            worker.start()
            try:
                assert entered.wait(timeout=10), failures
                releaser.start()
                window.close_observations()
            finally:
                release.set()
                worker.join(timeout=10)
                if releaser.ident is not None:
                    releaser.join(timeout=10)
            assert not worker.is_alive() and not releaser.is_alive()
            assert failures == []
            with pytest.raises(handover.InventoryObservationUnavailable, match="window has closed"):
                handover._run_with_paper_observation(window, lambda: None)


def test_approval_event_observation_does_not_read_an_inflight_partial_append(enrolled_funds):
    import time

    from hedge_fund.runtime import admission as admission_module

    root, admission = enrolled_funds
    ledger = Ledger(root.path / "paper" / "alpha")
    partial = Event()
    release = Event()
    finished = Event()
    events = []
    failures = []
    audit_key = admission_module._thread_lock_key(
        root,
        f"{admission_module.LOCK_DIRECTORY}/{admission_module._lock_filename('audit:alpha')}",
    )

    def append_in_parts():
        try:
            with admission.audit_lane("alpha"):
                with ledger.events_path.open("a", encoding="utf-8") as handle:
                    handle.write('{"kind":"halt"')
                    handle.flush()
                    partial.set()
                    if not release.wait(timeout=10):
                        raise TimeoutError("test did not release audit writer")
                    handle.write(',"reason":"synthetic"}\n')
                    handle.flush()
        except BaseException as exc:
            failures.append(exc)

    def observe():
        try:
            events.extend(ledger.events())
        except BaseException as exc:
            failures.append(exc)
        finally:
            finished.set()

    writer = Thread(target=append_in_parts, name="partial-audit-writer")
    reader = Thread(target=observe, name="audit-reader")
    writer.start()
    try:
        assert partial.wait(timeout=10), failures
        reader.start()
        deadline = time.monotonic() + 5
        waiting = False
        while time.monotonic() < deadline:
            with admission_module._LOCAL_LANES_GUARD:
                waiting = len(admission_module._LOCAL_LANES.get(audit_key, ())) >= 2
            if waiting or finished.is_set():
                break
            time.sleep(0.005)
        assert waiting or finished.is_set(), failures
    finally:
        release.set()
        writer.join(timeout=10)
        if reader.ident is not None:
            reader.join(timeout=10)
    assert not writer.is_alive() and not reader.is_alive()
    assert failures == []
    assert events[-1] == {"kind": "halt", "reason": "synthetic"}


def test_audit_observer_rechecks_a_deployment_restored_after_it_was_absent(enrolled_funds, monkeypatch):
    from pathlib import Path

    from hedge_fund.runtime import admission as admission_module
    from hedge_fund.runtime.lifecycle import LifecycleArchiveStore

    root, admission = enrolled_funds
    directory = root.path / "paper" / "alpha"
    ledger = Ledger(directory)
    store = LifecycleArchiveStore(root, admission)
    preview = store.preview("deployment", "alpha")
    archive = store.archive("deployment", "alpha", expected_digest=preview["digest"], archive_id="c" * 32)
    checked_absent = Event()
    resume_reader = Event()
    partial = Event()
    release_writer = Event()
    finished = Event()
    failures = []
    events = []
    original_is_dir = Path.is_dir

    def pause_after_absent_check(candidate):
        result = original_is_dir(candidate)
        if candidate == directory and current_thread().name == "audit-restore-reader" and not checked_absent.is_set():
            assert not result
            checked_absent.set()
            if not resume_reader.wait(timeout=10):
                raise TimeoutError("test did not restore the deployment")
        return result

    def read_events():
        try:
            events.extend(ledger.events())
        except BaseException as exc:
            failures.append(exc)
        finally:
            finished.set()

    def append_in_parts():
        try:
            with admission.audit_lane("alpha"):
                with ledger.events_path.open("a", encoding="utf-8") as handle:
                    handle.write('{"kind":"halt"')
                    handle.flush()
                    partial.set()
                    if not release_writer.wait(timeout=10):
                        raise TimeoutError("test did not release audit writer")
                    handle.write(',"reason":"synthetic"}\n')
                    handle.flush()
        except BaseException as exc:
            failures.append(exc)

    monkeypatch.setattr(Path, "is_dir", pause_after_absent_check)
    reader = Thread(target=read_events, name="audit-restore-reader")
    writer = Thread(target=append_in_parts, name="audit-restore-writer")
    reader.start()
    try:
        assert checked_absent.wait(timeout=10), failures
        store.restore(archive["archive_id"], expected_digest=preview["digest"], operation_id="d" * 32)
        writer.start()
        assert partial.wait(timeout=10), failures
        resume_reader.set()
        audit_key = admission_module._thread_lock_key(root, f"{admission_module.LOCK_DIRECTORY}/{admission_module._lock_filename('audit:alpha')}")
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and not finished.is_set():
            with admission_module._LOCAL_LANES_GUARD:
                if len(admission_module._LOCAL_LANES.get(audit_key, ())) >= 2:
                    break
            time.sleep(0.005)
    finally:
        resume_reader.set()
        release_writer.set()
        reader.join(timeout=10)
        if writer.ident is not None:
            writer.join(timeout=10)

    assert not reader.is_alive() and not writer.is_alive()
    assert failures == []
    assert events[-1] == {"kind": "halt", "reason": "synthetic"}


@pytest.mark.parametrize("source", ["ownership", "read-body"])
def test_noncontention_inventory_failures_are_not_retryable(enrolled_funds, monkeypatch, source):
    from contextlib import contextmanager

    from hedge_fund.runtime import handover
    from hedge_fund.runtime.admission import OwnershipUnknown, WriterConflict

    root, _admission = enrolled_funds
    if source == "ownership":

        @contextmanager
        def lost_ownership(*_args, **_kwargs):
            raise OwnershipUnknown("synthetic process ownership loss")
            yield

        monkeypatch.setattr(AdmissionCoordinator, "registry_read_lock", lost_ownership)
    else:

        def failed_read(_root):
            raise WriterConflict("synthetic failure after registry admission")

        monkeypatch.setattr(handover, "build_head_inventory", failed_read)

    with pytest.raises((handover.HandoverError, OwnershipUnknown, WriterConflict)) as caught:
        verify_root_inventory(root)
    assert not isinstance(caught.value, handover.InventoryObservationUnavailable)
    if source == "ownership":
        assert isinstance(caught.value, (handover.HandoverError, OwnershipUnknown))
    else:
        assert isinstance(caught.value, WriterConflict)


@pytest.mark.parametrize("source", ["ownership", "read-body"])
def test_noncontention_audit_failures_are_not_retryable(enrolled_funds, monkeypatch, source):
    from contextlib import contextmanager

    from hedge_fund.paper.ledger import (
        AuditObservationUnavailable,
        EVENTS_FILE,
        LedgerError,
    )
    from hedge_fund.runtime import admission as admission_module
    from hedge_fund.runtime.root import RootContext

    root, admission = enrolled_funds
    ledger = Ledger(root.path / "paper" / "alpha")
    with admission.control_lane("alpha"):
        ledger.log_event("tick", session="synthetic")
    if source == "ownership":

        @contextmanager
        def lost_ownership(*_args, **_kwargs):
            raise admission_module.OwnershipUnknown("synthetic process ownership loss")
            yield

        monkeypatch.setattr(admission_module, "_existing_read_lock", lost_ownership)
    else:
        original_read = RootContext.read_bytes
        read_attempts = []

        def failed_read(candidate, relative, *args, **kwargs):
            if candidate.path == ledger.directory and relative == EVENTS_FILE:
                read_attempts.append(relative)
                raise admission_module.WriterConflict("synthetic failure after audit admission")
            return original_read(candidate, relative, *args, **kwargs)

        monkeypatch.setattr(RootContext, "read_bytes", failed_read)

    with pytest.raises((LedgerError, admission_module.AdmissionError)) as caught:
        ledger.events()
    assert not isinstance(caught.value, AuditObservationUnavailable)
    if source == "read-body":
        assert read_attempts == [EVENTS_FILE]


def test_busy_audit_observation_is_explicit_and_does_not_halt(enrolled_funds, monkeypatch):
    from hedge_fund.paper.ledger import AuditObservationUnavailable
    from hedge_fund.runtime import admission as admission_module

    root, admission = enrolled_funds
    ledger = Ledger(root.path / "paper" / "alpha")
    held = Event()
    release = Event()
    failures = []
    monkeypatch.setattr(admission_module, "MAX_CONTROL_WAIT_SECONDS", 0.1)

    def hold_audit():
        try:
            with admission.audit_lane("alpha", timeout=0.1):
                held.set()
                if not release.wait(timeout=10):
                    raise TimeoutError("test did not release audit lane")
        except BaseException as exc:
            failures.append(exc)

    worker = Thread(target=hold_audit, name="busy-audit")
    worker.start()
    try:
        assert held.wait(timeout=10), failures
        with pytest.raises(AuditObservationUnavailable, match="temporarily unavailable"):
            ledger.events()
        assert ledger.halted() is None
    finally:
        release.set()
        worker.join(timeout=10)
    assert not worker.is_alive()
    assert failures == []


@pytest.mark.parametrize("kind", ["data", "prompt"])
def test_cache_still_rejects_unexplained_ledger_inventory_drift(enrolled_funds, kind):
    root, admission = enrolled_funds
    fund_file = root.path / "paper" / "alpha" / "fund.yaml"
    fund_file.write_bytes(fund_file.read_bytes() + b"\n")

    with admission.manual_session("beta", timeout=5):
        with pytest.raises(RootConfigurationError, match="root write admission"):
            _write_cache(kind, root)

    assert not (root.path / "cache").exists()


@pytest.mark.parametrize("kind", ["data", "prompt"])
@pytest.mark.parametrize("tamper", [False, True])
def test_cache_inspects_interrupted_sibling_archive_without_reconciling_it(
    enrolled_funds,
    monkeypatch,
    kind,
    tamper,
):
    from hedge_fund.runtime.lifecycle import LifecycleArchiveStore

    root, admission = enrolled_funds
    store = LifecycleArchiveStore(root, admission)
    preview = store.preview("deployment", "alpha")
    archive_id = "c" * 32
    finalize = store._finalize_archive

    def interrupt(*_args):
        raise RuntimeError("interrupted after move")

    monkeypatch.setattr(store, "_finalize_archive", interrupt)
    with pytest.raises(RuntimeError, match="interrupted after move"):
        store.archive("deployment", "alpha", expected_digest=preview["digest"], archive_id=archive_id)
    monkeypatch.setattr(store, "_finalize_archive", finalize)
    assert store.inspect(archive_id)["recovery_action"] == "finalize-archive"
    if tamper:
        archived = root.path / store.inspect(archive_id)["archive_path"] / "fund.yaml"
        archived.write_bytes(archived.read_bytes() + b"\n")

    with admission.manual_session("beta", timeout=5):
        if tamper:
            with pytest.raises(RootConfigurationError, match="root write admission"):
                _write_cache(kind, root)
        else:
            _write_cache(kind, root)
    assert store.inspect(archive_id)["state"] == "archive-prepared"
    assert enrollment_status(root, verify_inventory=True)["state"] == "drift"
    if not tamper:
        with pytest.raises(RootConfigurationError, match="root write admission"):
            paths.write_text(root.path / "research" / "unrelated.json", "{}")
        assert store.recover(archive_id, expected_digest=preview["digest"])["state"] == "archived"
        verify_root_inventory(root)


def test_tampered_prepared_sibling_is_not_accepted_before_head_publication(
    enrolled_funds,
    monkeypatch,
):
    from hedge_fund.runtime.lifecycle import LifecycleArchiveStore

    root, admission = enrolled_funds
    store = LifecycleArchiveStore(root, admission)
    preview = store.preview("deployment", "alpha")
    archive_id = "e" * 32
    finalize = store._finalize_archive
    monkeypatch.setattr(
        store,
        "_finalize_archive",
        lambda *_args: (_ for _ in ()).throw(RuntimeError("interrupted archive")),
    )
    with pytest.raises(RuntimeError, match="interrupted archive"):
        store.archive("deployment", "alpha", expected_digest=preview["digest"], archive_id=archive_id)
    monkeypatch.setattr(store, "_finalize_archive", finalize)
    inspected = store.inspect(archive_id)
    assert inspected["recovery_action"] == "finalize-archive"
    archived_fund = root.path / inspected["archive_path"] / "fund.yaml"
    ledger = Ledger(root.path / "paper" / "beta")
    record = _record(_spec("beta"))
    prior = require_enrollment(root)["heads"]["beta"]

    def damage_archive_after_append(path):
        if path == ledger.path(record.session):
            archived_fund.write_bytes(archived_fund.read_bytes() + b"\n")

    _after_record_write(monkeypatch, damage_archive_after_append)
    with admission.manual_session("beta"):
        with pytest.raises(LedgerHeadPublicationError):
            ledger.append(record)

    assert store.inspect(archive_id)["recovery_action"] == "manual-review"
    assert require_enrollment(root)["heads"]["beta"] == prior
    assert ledger.latest().hash == record.hash


def test_interrupted_archive_does_not_halt_an_independent_inflight_tick(
    enrolled_funds,
    monkeypatch,
):
    from datetime import datetime
    from importlib import import_module

    from hedge_fund.backtesting.test_fund import DailyOnly, FakeAnalyst, SERIES
    from hedge_fund.data.sessions import NEW_YORK
    from hedge_fund.fund import Fund
    from hedge_fund.runtime.lifecycle import LifecycleArchiveStore

    paper_tick = import_module("hedge_fund.paper.tick")
    root, admission = enrolled_funds
    store = LifecycleArchiveStore(root, admission)
    preview = store.preview("deployment", "alpha")
    archive_id = "d" * 32
    before_cache = Event()
    release = Event()
    failures = []
    results = []
    original_write = CachedDataClient._write

    def pause_inflight(client, *args, **kwargs):
        if current_thread().name == "beta-tick" and not before_cache.is_set():
            before_cache.set()
            if not release.wait(timeout=10):
                raise TimeoutError("test did not release beta cache")
        return original_write(client, *args, **kwargs)

    monkeypatch.setattr(CachedDataClient, "_write", pause_inflight)
    monkeypatch.setattr(paper_tick, "next_session", lambda *_args, **_kwargs: "2024-06-03")
    finalize = store._finalize_archive

    def interrupt(*_args):
        raise RuntimeError("interrupted after move")

    def run_beta():
        try:
            with admission.manual_session("beta", timeout=5):
                results.append(
                    paper_tick.tick(
                        root.path / "paper" / "beta",
                        CachedDataClient(
                            DailyOnly(SERIES),
                            cache_dir=root.path / "cache" / "data",
                        ),
                        now=lambda: datetime(2024, 6, 4, 12, tzinfo=NEW_YORK),
                        build_fund=lambda spec: Fund(
                            spec,
                            models={"solo": [FakeAnalyst("pead", {"AAPL": 1})]},
                        ),
                    )
                )
        except BaseException as exc:
            failures.append(exc)

    worker = Thread(target=run_beta, name="beta-tick")
    worker.start()
    try:
        assert before_cache.wait(timeout=10), failures
        monkeypatch.setattr(store, "_finalize_archive", interrupt)
        with pytest.raises(RuntimeError, match="interrupted after move"):
            store.archive("deployment", "alpha", expected_digest=preview["digest"], archive_id=archive_id)
        monkeypatch.setattr(store, "_finalize_archive", finalize)
        assert store.inspect(archive_id)["recovery_action"] == "finalize-archive"
    finally:
        release.set()
        worker.join(timeout=15)

    assert not worker.is_alive()
    assert failures == []
    assert len(results) == 1
    assert Ledger(root.path / "paper" / "beta").halted() is None
    assert store.recover(archive_id, expected_digest=preview["digest"])["state"] == "archived"
    verify_root_inventory(root)


@pytest.mark.parametrize("concurrent_vote", [False, True])
def test_redo_expires_old_verdict_and_allows_fresh_approval(
    enrolled_funds,
    monkeypatch,
    concurrent_vote,
):
    from datetime import datetime
    from importlib import import_module

    from hedge_fund.backtesting.test_fund import FakeAnalyst, FakeDataClient, SERIES
    from hedge_fund.data.sessions import NEW_YORK
    from hedge_fund.fund import Fund
    from hedge_fund.paper.ledger import LedgerError
    from hedge_fund.runtime.admission import paper_approval_transition

    paper_tick = import_module("hedge_fund.paper.tick")
    root, admission = enrolled_funds
    spec = _spec("gamma").model_copy(update={"approval_required": True})
    with admission.deployment_lock("gamma"):
        directory = deploy("gamma", spec, ["AAPL"], root=root.path / "paper")
    ledger = Ledger(directory)
    build_fund = lambda value: Fund(value, models={"solo": [FakeAnalyst("pead", {"AAPL": 1})]})
    monkeypatch.setattr(paper_tick, "next_session", lambda *_args, **_kwargs: "2024-06-03")
    with admission.manual_session("gamma"):
        original = paper_tick.tick(
            directory,
            FakeDataClient(SERIES),
            now=lambda: datetime(2024, 6, 4, 12, tzinfo=NEW_YORK),
            build_fund=build_fund,
        )
    assert original.decision is not None
    before_rewind = Event()
    release = Event()
    failures = []
    redone = []
    rewind = Ledger.rewind

    def pause_before_rewind(current):
        if current.directory == directory and current_thread().name == "redo":
            before_rewind.set()
            if not release.wait(timeout=10):
                raise TimeoutError("test did not release redo")
        return rewind(current)

    monkeypatch.setattr(Ledger, "rewind", pause_before_rewind)

    def run_redo():
        try:
            with admission.manual_session("gamma"):
                redone.append(paper_tick.redo(directory, FakeDataClient(SERIES), build_fund=build_fund))
        except BaseException as exc:
            failures.append(exc)

    worker = Thread(target=run_redo, name="redo")
    worker.start()
    try:
        assert before_rewind.wait(timeout=10), failures
        if concurrent_vote:
            with paper_approval_transition(admission, "gamma") as proof:
                with pytest.raises(LedgerError, match="expired"):
                    ledger.set_approval("approve", original.decision.as_of, original.hash, "web", admission=proof)
    finally:
        release.set()
        worker.join(timeout=15)

    assert not worker.is_alive()
    assert failures == []
    assert len(redone) == 1 and redone[0].hash != original.hash
    assert ledger.approval() is None
    assert ledger._latest_approval_event(original.decision.as_of, original.hash)["kind"] == "expire"
    with paper_approval_transition(admission, "gamma") as proof:
        with pytest.raises(LedgerError, match="expired"):
            ledger.set_approval("approve", original.decision.as_of, original.hash, "cli", admission=proof)
        ledger.set_approval("approve", redone[0].decision.as_of, redone[0].hash, "cli", admission=proof)

    monkeypatch.setattr(paper_tick, "next_session", lambda *_args, **_kwargs: "2024-06-04")
    with admission.manual_session("gamma"):
        next_record = paper_tick.tick(
            directory,
            FakeDataClient(SERIES),
            now=lambda: datetime(2024, 6, 5, 12, tzinfo=NEW_YORK),
            build_fund=build_fund,
        )
    assert next_record.executed is not None


def test_approval_waiting_for_sibling_publication_does_not_block_halt(
    enrolled_funds,
    monkeypatch,
):
    from datetime import datetime
    from importlib import import_module

    from hedge_fund.backtesting.test_fund import FakeAnalyst, FakeDataClient, SERIES
    from hedge_fund.data.sessions import NEW_YORK
    from hedge_fund.fund import Fund
    from hedge_fund.runtime import admission as admission_module
    from hedge_fund.web.schemas import ApprovalRequest
    from hedge_fund.web.services import DeskService, ServiceError

    root, admission = enrolled_funds
    spec = _spec("gamma").model_copy(update={"approval_required": True})
    with admission.deployment_lock("gamma"):
        directory = deploy("gamma", spec, ["AAPL"], root=root.path / "paper")
    paper_tick = import_module("hedge_fund.paper.tick")
    monkeypatch.setattr(paper_tick, "next_session", lambda *_args, **_kwargs: "2024-06-03")
    with admission.manual_session("gamma"):
        pending = paper_tick.tick(
            directory,
            FakeDataClient(SERIES),
            now=lambda: datetime(2024, 6, 4, 12, tzinfo=NEW_YORK),
            build_fund=lambda value: Fund(value, models={"solo": [FakeAnalyst("pead", {"AAPL": 1})]}),
        )
    service = DeskService(root.path, allow_writes=True, root_context=root)
    ledger = Ledger(root.path / "paper" / "alpha")
    record = _record(_spec("alpha"))
    written = Event()
    release = Event()
    failures = []
    vote_result = []

    def pause_publication(path):
        if path == ledger.path(record.session):
            written.set()
            if not release.wait(timeout=10):
                raise TimeoutError("test did not release publication")

    _after_record_write(monkeypatch, pause_publication)

    def publish():
        try:
            with admission.manual_session("alpha"):
                ledger.append(record)
        except BaseException as exc:
            failures.append(exc)

    def vote():
        try:
            service.approve(
                "gamma",
                ApprovalRequest(
                    request_id="approval-inventory-race-1",
                    verdict="approve",
                    decision_as_of=pending.decision.as_of,
                    source_record_hash=pending.hash,
                ),
            )
        except ServiceError as exc:
            vote_result.append(exc.status_code)
        except BaseException as exc:
            failures.append(exc)

    writer = Thread(target=publish, name="alpha-publication")
    voter = Thread(target=vote, name="beta-approval")
    writer.start()
    try:
        assert written.wait(timeout=10), failures
        voter.start()
        key = admission_module._thread_lock_key(root, f"{admission_module.LOCK_DIRECTORY}/registry.lock")
        deadline = time.monotonic() + 5
        queued = False
        while time.monotonic() < deadline and voter.is_alive():
            with admission_module._LOCAL_LANES_GUARD:
                queued = len(admission_module._LOCAL_LANES.get(key, ())) >= 2
            if queued:
                break
            time.sleep(0.01)
        assert queued, failures
        started = time.monotonic()
        result = service.halt_fund("gamma", "synthetic emergency", "halt-inventory-cache-race-001")
        halt_elapsed = time.monotonic() - started
        assert halt_elapsed < 2.0
        assert writer.is_alive() and not release.is_set()
        assert result["halted"] is True
        assert Ledger(directory).halted() == "synthetic emergency"
    finally:
        release.set()
        writer.join(timeout=15)
        if voter.ident is not None:
            voter.join(timeout=15)
        service.close()

    assert not writer.is_alive() and not voter.is_alive()
    assert failures == []
    assert vote_result == [423]


def test_direct_approval_requires_live_inventory_proof_and_control_lane(enrolled_funds, monkeypatch):
    from datetime import datetime
    from importlib import import_module

    from hedge_fund.backtesting.test_fund import FakeAnalyst, FakeDataClient, SERIES
    from hedge_fund.data.sessions import NEW_YORK
    from hedge_fund.fund import Fund
    from hedge_fund.paper.ledger import LedgerError
    from hedge_fund.runtime.admission import (
        paper_approval_transition,
        PaperApprovalAdmission,
        WriterConflict,
    )

    root, admission = enrolled_funds
    spec = _spec("gamma").model_copy(update={"approval_required": True})
    with admission.deployment_lock("gamma"):
        directory = deploy("gamma", spec, ["AAPL"], root=root.path / "paper")
    paper_tick = import_module("hedge_fund.paper.tick")
    monkeypatch.setattr(paper_tick, "next_session", lambda *_args, **_kwargs: "2024-06-03")
    with admission.manual_session("gamma"):
        pending = paper_tick.tick(
            directory,
            FakeDataClient(SERIES),
            now=lambda: datetime(2024, 6, 4, 12, tzinfo=NEW_YORK),
            build_fund=lambda value: Fund(value, models={"solo": [FakeAnalyst("pead", {"AAPL": 1})]}),
        )
    ledger = Ledger(directory)

    with admission.control_lane("gamma"):
        with pytest.raises(LedgerError, match="verified paper verdict admission"):
            ledger.set_approval("approve", pending.decision.as_of, pending.hash, "cli")
        with pytest.raises(WriterConflict, match="must precede"):
            with paper_approval_transition(admission, "gamma"):
                pytest.fail("entered verdict admission while holding control")
    with pytest.raises(TypeError, match="verified admission"):
        PaperApprovalAdmission(admission, "gamma", _seal=object())

    with paper_approval_transition(admission, "gamma") as proof:
        assert proof.matches(directory, "gamma")
        assert not proof.matches(root.path / "paper" / "beta", "beta")
        ledger.set_approval("approve", pending.decision.as_of, pending.hash, "cli", admission=proof)

    with admission.control_lane("gamma"):
        with pytest.raises(LedgerError, match="verified paper verdict admission"):
            ledger.set_approval("reject", pending.decision.as_of, pending.hash, "cli", admission=proof)
    assert ledger.approval()["verdict"] == "approve"


@pytest.mark.parametrize("initial", ["approve", "reject", None])
def test_verdict_cannot_change_after_tick_starts_consuming_it(enrolled_funds, monkeypatch, initial):
    from datetime import datetime
    from importlib import import_module

    from hedge_fund.backtesting.test_fund import FakeAnalyst, FakeDataClient, SERIES
    from hedge_fund.data.sessions import NEW_YORK
    from hedge_fund.fund import Fund
    from hedge_fund.paper.ledger import ApprovalExpired
    from hedge_fund.runtime.admission import paper_approval_transition

    paper_tick = import_module("hedge_fund.paper.tick")
    root, admission = enrolled_funds
    spec = _spec("gamma").model_copy(update={"approval_required": True})
    with admission.deployment_lock("gamma"):
        directory = deploy("gamma", spec, ["AAPL"], root=root.path / "paper")
    build_fund = lambda value: Fund(value, models={"solo": [FakeAnalyst("pead", {"AAPL": 1})]})
    monkeypatch.setattr(paper_tick, "next_session", lambda *_args, **_kwargs: "2024-06-03")
    with admission.manual_session("gamma"):
        first = paper_tick.tick(
            directory,
            FakeDataClient(SERIES),
            now=lambda: datetime(2024, 6, 4, 12, tzinfo=NEW_YORK),
            build_fund=build_fund,
        )
    ledger = Ledger(directory)
    if initial is not None:
        with paper_approval_transition(admission, "gamma") as proof:
            ledger.set_approval(initial, first.decision.as_of, first.hash, "cli", admission=proof)

    started = Event()
    release = Event()
    failures = []
    records = []
    advance = paper_tick.advance

    def pause_before_effects(*args, **kwargs):
        started.set()
        if not release.wait(timeout=10):
            raise TimeoutError("test did not release tick")
        return advance(*args, **kwargs)

    monkeypatch.setattr(paper_tick, "advance", pause_before_effects)
    monkeypatch.setattr(paper_tick, "next_session", lambda *_args, **_kwargs: "2024-06-04")

    def run_tick():
        try:
            with admission.manual_session("gamma"):
                records.append(
                    paper_tick.tick(
                        directory,
                        FakeDataClient(SERIES),
                        now=lambda: datetime(2024, 6, 5, 12, tzinfo=NEW_YORK),
                        build_fund=build_fund,
                    )
                )
        except BaseException as exc:
            failures.append(exc)

    worker = Thread(target=run_tick, name="consuming-tick")
    worker.start()
    try:
        assert started.wait(timeout=10), failures
        with paper_approval_transition(admission, "gamma") as proof:
            with pytest.raises(ApprovalExpired):
                ledger.set_approval("reject", first.decision.as_of, first.hash, "web", admission=proof)
    finally:
        release.set()
        worker.join(timeout=15)

    assert not worker.is_alive()
    assert failures == []
    assert len(records) == 1
    assert (records[0].executed is not None) is (initial == "approve")


def test_redo_control_timeout_cannot_accept_a_verdict_after_halt(enrolled_funds, monkeypatch):
    from datetime import datetime
    from importlib import import_module

    from hedge_fund.backtesting.test_fund import FakeAnalyst, FakeDataClient, SERIES
    from hedge_fund.data.sessions import NEW_YORK
    from hedge_fund.fund import Fund
    from hedge_fund.paper import ledger as ledger_module
    from hedge_fund.paper.ledger import ApprovalHalted
    from hedge_fund.runtime.admission import paper_approval_transition, WriterConflict

    paper_tick = import_module("hedge_fund.paper.tick")
    root, admission = enrolled_funds
    spec = _spec("gamma").model_copy(update={"approval_required": True})
    with admission.deployment_lock("gamma"):
        directory = deploy("gamma", spec, ["AAPL"], root=root.path / "paper")
    build_fund = lambda value: Fund(value, models={"solo": [FakeAnalyst("pead", {"AAPL": 1})]})
    monkeypatch.setattr(paper_tick, "next_session", lambda *_args, **_kwargs: "2024-06-03")
    with admission.manual_session("gamma"):
        first = paper_tick.tick(
            directory,
            FakeDataClient(SERIES),
            now=lambda: datetime(2024, 6, 4, 12, tzinfo=NEW_YORK),
            build_fund=build_fund,
        )
    ledger = Ledger(directory)
    redo_ready = Event()
    release_redo = Event()
    vote_ready = Event()
    release_vote = Event()
    failures = []
    results = []
    replay = Ledger.replay
    write_atomic = ledger_module.write_atomic

    def pause_after_replay(current, *args, **kwargs):
        state = replay(current, *args, **kwargs)
        if current.directory == directory and current_thread().name == "contended-redo" and kwargs.get("before"):
            redo_ready.set()
            if not release_redo.wait(timeout=10):
                raise TimeoutError("test did not release redo")
        return state

    def pause_before_vote(path, text, **kwargs):
        if path == ledger.approval_path and current_thread().name == "contended-vote":
            vote_ready.set()
            if not release_vote.wait(timeout=10):
                raise TimeoutError("test did not release vote")
        return write_atomic(path, text, **kwargs)

    monkeypatch.setattr(Ledger, "replay", pause_after_replay)
    monkeypatch.setattr(ledger_module, "write_atomic", pause_before_vote)

    def run_redo():
        try:
            with admission.manual_session("gamma"):
                with pytest.raises(WriterConflict):
                    paper_tick.redo(
                        directory,
                        FakeDataClient(SERIES),
                        build_fund=lambda _spec: pytest.fail("redo reached provider work"),
                    )
        except BaseException as exc:
            failures.append(exc)

    def run_vote():
        try:
            with paper_approval_transition(admission, "gamma") as proof:
                ledger.set_approval("approve", first.decision.as_of, first.hash, "web", admission=proof)
            results.append("accepted")
        except ApprovalHalted:
            results.append("halted-denial")
        except BaseException as exc:
            failures.append(exc)

    redo_worker = Thread(target=run_redo, name="contended-redo")
    vote_worker = Thread(target=run_vote, name="contended-vote")
    redo_worker.start()
    try:
        assert redo_ready.wait(timeout=10), failures
        vote_worker.start()
        assert vote_ready.wait(timeout=10), failures
        release_redo.set()
        redo_worker.join(timeout=10)
        assert not redo_worker.is_alive(), failures
    finally:
        release_redo.set()
        release_vote.set()
        redo_worker.join(timeout=10)
        if vote_worker.ident is not None:
            vote_worker.join(timeout=10)

    assert not vote_worker.is_alive()
    assert failures == []
    assert not (ledger.halted() is not None and results == ["accepted"])
    assert ledger.latest().hash == first.hash
    verify_root_inventory(root)


def test_failed_final_halt_check_does_not_commit_a_verdict(enrolled_funds, monkeypatch):
    from datetime import datetime
    from importlib import import_module

    from hedge_fund.backtesting.test_fund import FakeAnalyst, FakeDataClient, SERIES
    from hedge_fund.data.sessions import NEW_YORK
    from hedge_fund.fund import Fund
    from hedge_fund.paper.ledger import LedgerError
    from hedge_fund.runtime.admission import paper_approval_transition

    paper_tick = import_module("hedge_fund.paper.tick")
    root, admission = enrolled_funds
    spec = _spec("gamma").model_copy(update={"approval_required": True})
    with admission.deployment_lock("gamma"):
        directory = deploy("gamma", spec, ["AAPL"], root=root.path / "paper")
    monkeypatch.setattr(paper_tick, "next_session", lambda *_args, **_kwargs: "2024-06-03")
    with admission.manual_session("gamma"):
        pending = paper_tick.tick(
            directory,
            FakeDataClient(SERIES),
            now=lambda: datetime(2024, 6, 4, 12, tzinfo=NEW_YORK),
            build_fund=lambda value: Fund(value, models={"solo": [FakeAnalyst("pead", {"AAPL": 1})]}),
        )
    ledger = Ledger(directory)
    read_halt = ledger.halted
    reads = []

    def fail_final_read():
        reads.append(None)
        if len(reads) == 2:
            raise LedgerError("synthetic unreadable halt")
        return read_halt()

    with paper_approval_transition(admission, "gamma") as proof:
        monkeypatch.setattr(ledger, "halted", fail_final_read)
        with pytest.raises(LedgerError, match="synthetic unreadable halt"):
            ledger.set_approval("approve", pending.decision.as_of, pending.hash, "cli", admission=proof)

    monkeypatch.setattr(ledger, "halted", read_halt)
    resolved, _ = ledger.resolve_approval(pending.decision.as_of, pending.hash)
    assert resolved is None


def test_cli_halt_succeeds_while_sibling_head_publication_is_inflight(enrolled_funds, monkeypatch):
    import subprocess

    from hedge_fund.test_support.network_guard import (
        child_test_environment,
        guarded_test_python_command,
    )

    root, admission = enrolled_funds
    ledger = Ledger(root.path / "paper" / "alpha")
    record = _record(_spec("alpha"))
    written = Event()
    release = Event()
    failures = []

    def pause_publication(path):
        if path == ledger.path(record.session):
            written.set()
            if not release.wait(timeout=15):
                raise TimeoutError("test did not release publication")

    _after_record_write(monkeypatch, pause_publication)

    def publish():
        try:
            with admission.manual_session("alpha"):
                ledger.append(record)
        except BaseException as exc:
            failures.append(exc)

    writer = Thread(target=publish, name="alpha-publication")
    writer.start()
    try:
        assert written.wait(timeout=10), failures
        result = subprocess.run(
            guarded_test_python_command(
                "-m",
                "hedge_fund.run",
                "--root",
                str(root.path),
                "paper",
                "halt",
                "beta",
                "--reason",
                "synthetic emergency",
                "--request-id",
                "t027-sibling-halt-001",
            ),
            env=child_test_environment(),
            capture_output=True,
            check=False,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0, result.stderr
        assert Ledger(root.path / "paper" / "beta").halted() == "synthetic emergency"
    finally:
        release.set()
        writer.join(timeout=15)

    assert not writer.is_alive()
    assert failures == []


def test_redo_control_contention_is_retryable_before_mutation(
    enrolled_funds,
    monkeypatch,
):
    from datetime import datetime
    from importlib import import_module

    from hedge_fund.backtesting.test_fund import FakeAnalyst, FakeDataClient, SERIES
    from hedge_fund.data.sessions import NEW_YORK
    from hedge_fund.fund import Fund
    from hedge_fund.runtime.admission import WriterConflict

    paper_tick = import_module("hedge_fund.paper.tick")
    root, admission = enrolled_funds
    spec = _spec("gamma").model_copy(update={"approval_required": True})
    with admission.deployment_lock("gamma"):
        directory = deploy("gamma", spec, ["AAPL"], root=root.path / "paper")
    build_fund = lambda value: Fund(value, models={"solo": [FakeAnalyst("pead", {"AAPL": 1})]})
    monkeypatch.setattr(paper_tick, "next_session", lambda *_args, **_kwargs: "2024-06-03")
    with admission.manual_session("gamma"):
        original = paper_tick.tick(
            directory,
            FakeDataClient(SERIES),
            now=lambda: datetime(2024, 6, 4, 12, tzinfo=NEW_YORK),
            build_fund=build_fund,
        )
    locked = Event()
    release = Event()
    failures = []

    def hold_control():
        try:
            with admission.control_lane("gamma"):
                locked.set()
                if not release.wait(timeout=10):
                    raise TimeoutError("test did not release control lane")
        except BaseException as exc:
            failures.append(exc)

    holder = Thread(target=hold_control, name="held-control")
    holder.start()
    try:
        assert locked.wait(timeout=10), failures
        with admission.manual_session("gamma"):
            with pytest.raises(WriterConflict):
                paper_tick.redo(
                    directory,
                    FakeDataClient(SERIES),
                    build_fund=lambda _spec: pytest.fail("redo reached model work"),
                )
    finally:
        release.set()
        holder.join(timeout=10)

    assert not holder.is_alive()
    assert failures == []
    assert Ledger(directory).halted() is None
    assert Ledger(directory).sessions() == [original.session]
    assert Ledger(directory).latest().hash == original.hash
    assert not (directory / "ledger" / "superseded").exists()
    verify_root_inventory(root)


@pytest.mark.parametrize("mutation", ["append", "rewind", "deploy"])
def test_failed_head_publication_leaves_paper_and_cache_writes_blocked(
    enrolled_funds,
    monkeypatch,
    mutation,
):
    from hedge_fund.runtime import handover

    root, admission = enrolled_funds
    ledger = Ledger(root.path / "paper" / "alpha")
    record = _record(_spec("alpha"))
    if mutation == "rewind":
        with admission.manual_session("alpha"):
            ledger.append(record)

    def fail_publication(*_args, **_kwargs):
        raise handover.HandoverError("injected publication failure")

    monkeypatch.setattr(handover, "_publish_expected_ledger_head", fail_publication)
    with pytest.raises(LedgerHeadPublicationError, match="offline reconciliation"):
        if mutation == "deploy":
            with admission.deployment_lock("gamma"):
                deploy("gamma", _spec("gamma"), ["AAPL"], root=root.path / "paper")
        else:
            with admission.manual_session("alpha"):
                if mutation == "append":
                    ledger.append(record)
                else:
                    ledger.rewind()

    with pytest.raises(LedgerDrift):
        verify_root_inventory(root)
    with admission.manual_session("beta"):
        with pytest.raises(RootConfigurationError, match="root write admission"):
            _write_cache("prompt", root)


def test_existing_drift_is_not_published_by_a_later_append(enrolled_funds):
    root, admission = enrolled_funds
    fund_file = root.path / "paper" / "alpha" / "fund.yaml"
    fund_file.write_bytes(fund_file.read_bytes() + b"\n")
    ledger = Ledger(root.path / "paper" / "alpha")
    record = _record(_spec("alpha"))

    with admission.manual_session("alpha"):
        with pytest.raises(LedgerDrift):
            ledger.append(record)

    assert not ledger.path(record.session).exists()
    with pytest.raises(LedgerDrift):
        verify_root_inventory(root)


def test_external_target_drift_during_append_is_not_published(
    enrolled_funds,
    monkeypatch,
):

    root, admission = enrolled_funds
    ledger = Ledger(root.path / "paper" / "alpha")
    record = _record(_spec("alpha"))
    fund_file = root.path / "paper" / "alpha" / "fund.yaml"
    original_digest = require_enrollment(root)["heads"]["alpha"]["deployment_digest"]

    def append_then_tamper(path):
        if path == ledger.path(record.session):
            fund_file.write_bytes(fund_file.read_bytes() + b"\n")

    _after_record_write(monkeypatch, append_then_tamper)
    with admission.manual_session("alpha"):
        with pytest.raises(LedgerHeadPublicationError, match="offline reconciliation"):
            ledger.append(record)

    assert require_enrollment(root)["heads"]["alpha"]["deployment_digest"] == original_digest
    with pytest.raises(LedgerDrift):
        verify_root_inventory(root)


def test_cache_waits_for_another_process_to_publish_its_ledger_head(
    enrolled_funds,
    owned_test_process,
    tmp_path,
    monkeypatch,
):
    from hedge_fund.runtime import admission as admission_module

    root, admission = enrolled_funds
    record = _record(_spec("alpha"))
    written = tmp_path / "child-written"
    release = tmp_path / "release-child"
    failure = tmp_path / "child-failure"
    script = f"""
import time
from pathlib import Path
from hedge_fund import paths
from hedge_fund.paper.ledger import Ledger
from hedge_fund.pipeline.session import SessionRecord
from hedge_fund.runtime.admission import AdmissionCoordinator, RootOwnerLease
from hedge_fund.runtime.handover import PaperInventoryTransition
from hedge_fund.runtime.root import RootContext

root_path = Path({str(root.path)!r})
written = Path({str(written)!r})
release = Path({str(release)!r})
failure = Path({str(failure)!r})
record = SessionRecord.model_validate_json({record.model_dump_json()!r})
ledger = Ledger(root_path / "paper" / "alpha")
original_write = PaperInventoryTransition.write_text

def pause_after_write(self, relative, text):
    original_write(self, relative, text)
    if Path(self._root.path, *self._base, relative) == ledger.path(record.session):
        written.write_text("written", encoding="utf-8")
        deadline = time.monotonic() + 15
        while not release.exists():
            if time.monotonic() >= deadline:
                raise TimeoutError("parent did not release publication")
            time.sleep(0.01)

PaperInventoryTransition.write_text = pause_after_write
try:
    with RootContext.open(root_path) as root:
        with RootOwnerLease.acquire(root) as owner:
            admission = AdmissionCoordinator(root, owner_lease=owner)
            with paths.bound_root(root):
                with admission.manual_session("alpha", timeout=5):
                    ledger.append(record)
except BaseException as exc:
    failure.write_text(type(exc).__name__ + ": " + str(exc), encoding="utf-8")
    raise
"""
    writer = owned_test_process(script)
    cache_attempted = Event()
    cache_finished = Event()
    registry_contended = Event()
    failures = []
    try_acquire = admission_module._try_acquire_os_lock

    def observe_os_contention(handle, *, exclusive=True):
        result = try_acquire(handle, exclusive=exclusive)
        if current_thread().name == "beta-process-cache" and not result[0]:
            registry_contended.set()
        return result

    monkeypatch.setattr(admission_module, "_try_acquire_os_lock", observe_os_contention)

    def write_beta_cache():
        try:
            with admission.manual_session("beta", timeout=5):
                cache_attempted.set()
                _write_cache("prompt", root)
        except BaseException as exc:
            failures.append(exc)
        finally:
            cache_finished.set()

    cache = Thread(target=write_beta_cache, name="beta-process-cache")
    deadline = time.monotonic() + 15
    try:
        while not written.exists() and writer.poll() is None and time.monotonic() < deadline:
            time.sleep(0.01)
        assert written.exists(), failure.read_text(encoding="utf-8") if failure.exists() else "child did not append"
        cache.start()
        assert cache_attempted.wait(timeout=10)
        waited_for_publication = registry_contended.wait(timeout=10)
    finally:
        release.write_text("release", encoding="utf-8")
        if cache.ident is not None:
            cache.join(timeout=10)
    assert writer.wait(timeout=15) == 0, failure.read_text(encoding="utf-8") if failure.exists() else "child failed"
    assert not cache.is_alive()
    assert waited_for_publication
    assert failures == []
    assert cache_finished.is_set()
    verify_root_inventory(root)
    assert Ledger(root.path / "paper" / "alpha").latest().hash == record.hash


def test_external_drift_during_deploy_is_not_published(enrolled_funds, monkeypatch):
    root, admission = enrolled_funds
    original_init = Ledger.init

    def init_then_tamper(ledger):
        original_init(ledger)
        fund_file = ledger.directory / "fund.yaml"
        fund_file.write_bytes(fund_file.read_bytes() + b"\n")

    monkeypatch.setattr(Ledger, "init", init_then_tamper)
    with admission.deployment_lock("gamma"):
        with pytest.raises(LedgerHeadPublicationError, match="offline reconciliation"):
            deploy("gamma", _spec("gamma"), ["AAPL"], root=root.path / "paper")

    assert "gamma" not in require_enrollment(root)["heads"]
    with pytest.raises(LedgerDrift):
        verify_root_inventory(root)


@pytest.mark.parametrize("display_name", [None, "B\u00f8rs \U0001f4c8"])
def test_deployment_preserves_native_text_serialization(enrolled_funds, tmp_path, display_name):
    root, admission = enrolled_funds
    spec = _spec("gamma")
    spec.strategies[0].display_name = display_name
    with admission.deployment_lock("gamma"):
        directory = deploy("gamma", spec, ["AAPL"], root=root.path / "paper")
    deployed = load_deployed(directory)
    expected = tmp_path / "expected-fund.yaml"
    expected.write_text(yaml.safe_dump(deployed.model_dump(), sort_keys=False))

    assert (directory / "fund.yaml").read_bytes() == expected.read_bytes()


@pytest.mark.parametrize("initial_read_fails", [False, True])
def test_observer_retries_if_first_registry_lock_is_created_during_its_read(
    tmp_path,
    monkeypatch,
    initial_read_fails,
):
    from hedge_fund.runtime import handover
    from hedge_fund.runtime.admission import LOCK_DIRECTORY

    root_path = tmp_path / "fresh"
    root_path.mkdir()
    with RootContext.open(root_path) as root:
        enroll_fresh(root)
        verify_root_inventory(root)
        with pytest.raises(FileNotFoundError):
            root.file_info(f"{LOCK_DIRECTORY}/registry.lock")
        observed = Event()
        release = Event()
        calls = []
        failures = []
        original_inventory = handover.build_head_inventory

        def delayed_inventory(context):
            if current_thread().name == "initial-inventory-observer":
                calls.append("read")
                if len(calls) == 1:
                    snapshot = original_inventory(context)
                    observed.set()
                    assert release.wait(timeout=10)
                    if initial_read_fails:
                        raise HandoverError("synthetic incomplete concurrent inventory")
                    return snapshot
            return original_inventory(context)

        def observe():
            try:
                verify_root_inventory(root)
            except BaseException as exc:
                failures.append(exc)

        monkeypatch.setattr(handover, "build_head_inventory", delayed_inventory)
        observer = Thread(target=observe, name="initial-inventory-observer")
        observer.start()
        try:
            assert observed.wait(timeout=10)
            with RootOwnerLease.acquire(root) as owner:
                admission = AdmissionCoordinator(root, owner_lease=owner)
                with paths.bound_root(root):
                    with admission.deployment_lock("alpha"):
                        deploy("alpha", _spec("alpha"), ["AAPL"], root=root.path / "paper")
        finally:
            release.set()
            observer.join(timeout=10)
        assert not observer.is_alive()
        assert failures == []
        assert len(calls) == 2
        verify_root_inventory(root)
