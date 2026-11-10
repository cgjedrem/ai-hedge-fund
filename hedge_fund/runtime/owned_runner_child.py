"""Detached, finite local-paper runner child."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import threading
import time
from contextlib import ExitStack
from datetime import datetime, timezone
from typing import Callable

from hedge_fund import paths
from hedge_fund.data import CachedDataClient, make_data_client
from hedge_fund.data.sessions import NEW_YORK
from hedge_fund.fund import Fund, FundSpec
from hedge_fund.llm import make_llm, PromptCache
from hedge_fund.paper.deployed import load_deployed
from hedge_fund.paper.ledger import (
    AuditObservationUnavailable,
    Ledger,
    PaperReconciliationRequired,
    UnresolvedTickIntentRefusal,
)
from hedge_fund.paper.tick import next_session, tick
from hedge_fund.pipeline.session import code_version, mandate_hash
from hedge_fund.runtime.admission import (
    AdmissionCoordinator,
    AdmissionError,
    PaperPreflightBusy,
    PROTOCOL_VERSION,
    RootOwnerLease,
    WriterConflict,
)
from hedge_fund.runtime.capture import FrozenCapture
from hedge_fund.runtime.configuration import ConfigurationError
from hedge_fund.runtime.dispatch import ProviderDispatch
from hedge_fund.runtime.handover import (
    HandoverError,
    InventoryObservationUnavailable,
    require_enrollment,
    root_binding,
    verify_ledger_head,
    verify_root_inventory,
)
from hedge_fund.runtime.owned_runner import (
    OwnedRunnerError,
    read_runner_record,
    runner_key,
    validate_runner_control,
    validate_runner_state,
    write_runner_record,
)
from hedge_fund.runtime.ownership import current_process_identity
from hedge_fund.runtime.policy import (
    AuthorizationDenied,
    authorize_session,
    classify_provider,
    KEN_FRENCH_BREAKPOINTS_TARGET,
    OperationScope,
    ProviderClass,
    ProviderTarget,
    RunnerAuthorization,
)
from hedge_fund.runtime.root import RootContext, RootPathError


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="aihf-owned-paper-runner")
    parser.add_argument("--root", required=True)
    parser.add_argument("--fund", required=True)
    args = parser.parse_args(argv)
    if not os.path.isabs(args.root):
        return 2
    try:
        with RootContext.open(args.root) as root, paths.bound_root(root):
            run_owned_runner(root, args.fund)
    except Exception:
        return 1
    return 0


def run_owned_runner(
    root: RootContext,
    fund: str,
    *,
    data_client_factory: Callable[[FrozenCapture, RootContext, ProviderDispatch], object] | None = None,
    build_fund: Callable[[FundSpec, FrozenCapture, RootContext, ProviderDispatch], Fund] | None = None,
    now: Callable[[], datetime] | None = None,
    sleep: Callable[[float], None] | None = None,
    resolver=None,
) -> None:
    if not isinstance(root, RootContext):
        raise TypeError("an explicit root context is required")
    if not isinstance(fund, str) or not fund:
        raise TypeError("a runner fund is required")
    root.revalidate()
    launch = read_runner_record(root, fund, "launch")
    if launch is None:
        raise OwnedRunnerError("runner bootstrap record is missing")
    name = launch.get("fund")
    nonce = launch.get("nonce")
    nonce_hash = _sha256(nonce.encode("utf-8")) if isinstance(nonce, str) else None
    if name != fund or type(launch.get("schema")) is not int or launch.get("schema") != 1 or type(launch.get("protocol_version")) is not int or launch.get("protocol_version") != PROTOCOL_VERSION or launch.get("build_id") != code_version() or launch.get("root") != root_binding(root) or not isinstance(nonce, str) or len(nonce) < 32 or not isinstance(nonce_hash, str):
        raise OwnedRunnerError("runner bootstrap identity is invalid")
    expected_launch_fields = {
        "schema",
        "protocol_version",
        "build_id",
        "root",
        "fund",
        "nonce",
        "created_at",
        "capture",
        "authorization",
    }
    if set(launch) != expected_launch_fields:
        raise OwnedRunnerError("runner launch fields are invalid")
    state, authorization_raw = _wait_for_launch(root, fund, nonce_hash)

    capture_raw = launch.get("capture")
    if not isinstance(capture_raw, dict):
        raise OwnedRunnerError("runner capture is invalid")
    try:
        capture = FrozenCapture.from_private_bytes(
            root,
            json.dumps(
                capture_raw,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            ).encode("utf-8"),
        )
    except ConfigurationError:
        raise OwnedRunnerError("runner capture is invalid") from None
    if capture.subject_id != fund or capture.broker != "paper":
        raise OwnedRunnerError("runner capture does not match the deployment")
    deployed = load_deployed(root.path / "paper" / fund)
    if deployed.name != fund or deployed.broker != "paper":
        raise OwnedRunnerError("runner deployment is not local paper")
    if mandate_hash(deployed.spec) != capture.mandate_digest or tuple(deployed.universe) != capture.universe:
        raise OwnedRunnerError("runner deployment changed after review")
    _require_local_capture(capture)
    authorization = _runner_authorization(authorization_raw, capture)
    started_at = launch["created_at"]
    expires_at = _parse_datetime(authorization_raw["expires_at"])
    max_sessions = authorization_raw["max_sessions"]
    owner = RootOwnerLease.acquire(root, timeout=5.0)
    admission = AdmissionCoordinator(root, owner_lease=owner)
    clock = now or (lambda: datetime.now(timezone.utc))
    pause = sleep or time.sleep
    try:
        status = dict(state)
        try:
            while True:
                control = read_runner_record(root, fund, "control")
                if not validate_runner_control(root, fund, nonce_hash, control):
                    raise OwnedRunnerError("runner control state is unavailable")
                if control["stop_requested"]:
                    status.update({"status": "stopped", "reason": "stop-requested"})
                    _write_status(root, fund, nonce_hash, status)
                    return
                if _validated_now(clock()) >= expires_at:
                    status.update({"status": "completed", "reason": "expiry-reached"})
                    _write_status(root, fund, nonce_hash, status)
                    return
                try:
                    require_enrollment(root)
                    verify_root_inventory(root)
                    break
                except InventoryObservationUnavailable:
                    pause(0.25)
            _reject_legacy_pid(root, fund)
            with admission.runner_reservation(fund, timeout=5.0):
                process_record = current_process_identity()
                if process_record != state.get("process_identity"):
                    raise OwnedRunnerError("runner process incarnation changed")
                status.update(
                    {
                        "status": "running",
                        "pid": process_record["pid"],
                        "process_identity": process_record,
                        "started_at": started_at,
                        "reason": None,
                    }
                )
                _write_status(root, fund, nonce_hash, status)
                _runner_loop(
                    root,
                    fund,
                    deployed.spec,
                    capture,
                    authorization,
                    admission,
                    nonce_hash,
                    status,
                    expires_at=expires_at,
                    max_sessions=max_sessions,
                    data_client_factory=data_client_factory,
                    build_fund=build_fund,
                    now=clock,
                    sleep=pause,
                    resolver=resolver,
                )
        except Exception as exc:
            try:
                observed = read_runner_record(root, fund, "state")
                if observed is not None and observed.get("nonce_hash") == nonce_hash and observed.get("status") in {"starting", "running", "stopping"}:
                    observed["status"] = "failed"
                    observed["reason"] = f"runner-{type(exc).__name__}"
                    _write_status(root, fund, nonce_hash, observed)
            except Exception:
                pass
            raise
    finally:
        owner.close()


def _wait_for_launch(
    root: RootContext,
    fund: str,
    nonce_hash: str,
    *,
    timeout: float = 8.0,
) -> tuple[dict, dict]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        control = read_runner_record(root, fund, "control")
        if not validate_runner_control(root, fund, nonce_hash, control):
            raise OwnedRunnerError("runner launch control is invalid")
        if control["stop_requested"]:
            raise OwnedRunnerError("runner launch was stopped")
        if control["launch_ready"]:
            state = read_runner_record(root, fund, "state")
            if not validate_runner_state(root, fund, state):
                raise OwnedRunnerError("runner process state is invalid")
            current = current_process_identity()
            if state.get("status") != "starting" or state.get("pid") != os.getpid() or state.get("process_identity") != current or state.get("nonce_hash") != nonce_hash:
                raise OwnedRunnerError("runner launch process identity does not match")
            launch = read_runner_record(root, fund, "launch")
            if launch is None or not isinstance(launch.get("authorization"), dict):
                raise OwnedRunnerError("runner launch authorization is invalid")
            return state, launch["authorization"]
        time.sleep(0.025)
    raise OwnedRunnerError("runner launch authorization timed out")


def _runner_loop(
    root: RootContext,
    fund: str,
    spec: FundSpec,
    capture: FrozenCapture,
    authorization: RunnerAuthorization,
    admission: AdmissionCoordinator,
    nonce_hash: str,
    status: dict,
    *,
    expires_at: datetime,
    max_sessions: int,
    data_client_factory,
    build_fund,
    now: Callable[[], datetime],
    sleep: Callable[[float], None],
    resolver=None,
) -> None:
    stop_event = threading.Event()
    watcher_done = threading.Event()

    def watch_control() -> None:
        while not watcher_done.wait(0.1):
            try:
                control = read_runner_record(root, fund, "control")
            except Exception:
                status["reason"] = "control-state-unverified"
                stop_event.set()
                return
            if not validate_runner_control(root, fund, nonce_hash, control):
                status["reason"] = "control-state-unverified"
                stop_event.set()
                return
            if control["stop_requested"]:
                stop_event.set()
                return

    watcher = threading.Thread(target=watch_control, daemon=True)
    watcher.start()
    targets = (
        ProviderTarget(kind="data", provider=capture.data_provider),
        ProviderTarget(
            kind="llm",
            provider=capture.llm_provider,
            model=capture.model,
            endpoint=capture.endpoint,
        ),
        KEN_FRENCH_BREAKPOINTS_TARGET,
    )

    def dispatch_fence() -> None:
        moment = _validated_now(now())
        if moment >= expires_at:
            raise AuthorizationDenied("runner deadline expired")
        if stop_event.is_set() and authorization.sessions_started == 0:
            raise AuthorizationDenied("runner stop was requested")
        try:
            admission.require_root_owner()
        except AdmissionError as exc:
            raise AuthorizationDenied("runner write authority is unavailable") from exc
        root.revalidate()
        require_enrollment(root)
        verify_ledger_head(root, fund)
        control = read_runner_record(root, fund, "control")
        if not validate_runner_control(root, fund, nonce_hash, control):
            raise AuthorizationDenied("runner control state is unavailable")
        if control["stop_requested"]:
            stop_event.set()
            if authorization.sessions_started == 0:
                raise AuthorizationDenied("runner stop was requested")
        current_deployed = load_deployed(root.path / "paper" / fund)
        if current_deployed.broker != "paper" or mandate_hash(current_deployed.spec) != capture.mandate_digest or tuple(current_deployed.universe) != capture.universe:
            raise AuthorizationDenied("runner deployment changed")
        current = Ledger(root.path / "paper" / fund).replay(
            spec.capital,
            full=True,
        )
        if current.halted is not None:
            raise AuthorizationDenied("runner fund is halted")

    dispatch = ProviderDispatch(
        scope=OperationScope.SCHEDULED,
        root_id=capture.root_id,
        subject_id=fund,
        capture_digest=capture.digest,
        operation_id=authorization.operation_id,
        operation_digest=authorization.operation_digest,
        targets=targets,
        network_authorized=True,
        runner=authorization,
        approved_local_models={capture.model},
        clock=lambda: _validated_now(now()),
        boundary_check=dispatch_fence,
        resolver=resolver,
    )
    last_session = status.get("last_session")
    sessions_completed = status.get("sessions_completed", 0)
    try:
        while not stop_event.is_set():
            moment = _validated_now(now())
            if moment >= expires_at:
                status["status"] = "completed"
                status["reason"] = "expiry-reached"
                break
            if sessions_completed >= max_sessions:
                status["status"] = "completed"
                status["reason"] = "session-bound-reached"
                break
            try:
                require_enrollment(root)
                verify_ledger_head(root, fund)
            except InventoryObservationUnavailable:
                if stop_event.wait(0.25):
                    break
                continue
            ledger = Ledger(root.path / "paper" / fund)
            state = ledger.replay(spec.capital, full=True)
            if state.halted is not None:
                status["status"] = "failed"
                status["reason"] = "fund-halted"
                break
            try:
                with ExitStack() as preflight:
                    try:
                        preflight.enter_context(admission.control_lane(fund))
                    except WriterConflict:
                        if stop_event.wait(0.25):
                            break
                        continue
                    if ledger.halted() is not None:
                        status["status"] = "failed"
                        status["reason"] = "fund-halted"
                        break
                    try:
                        ledger.require_ready_for_work(state, approval_required=spec.approval_required)
                    except PaperReconciliationRequired:
                        ledger.halt("approval journal requires reconciliation")
                        raise
            except AuditObservationUnavailable:
                if stop_event.wait(0.25):
                    break
                continue
            if spec.is_intraday:
                due = next_session(
                    None,
                    spec,
                    state.last_session,
                    now=lambda: moment.astimezone(NEW_YORK),
                )
                if due is None:
                    if stop_event.wait(0.25):
                        break
                    continue
                with _client_context(
                    root,
                    capture,
                    data_client_factory,
                    dispatch,
                ) as client:
                    _execute_session(
                        root,
                        fund,
                        spec,
                        capture,
                        authorization,
                        admission,
                        ledger,
                        state,
                        due,
                        client,
                        nonce_hash,
                        status,
                        data_client_factory,
                        build_fund,
                        dispatch,
                        moment,
                        retry_clock=now,
                        stop_event=stop_event,
                        expires_at=expires_at,
                    )
            else:
                with _client_context(
                    root,
                    capture,
                    data_client_factory,
                    dispatch,
                ) as client:
                    due = next_session(
                        client,
                        spec,
                        state.last_session,
                        now=lambda: moment.astimezone(NEW_YORK),
                    )
                    if due is None:
                        if stop_event.wait(60.0):
                            break
                        continue
                    _execute_session(
                        root,
                        fund,
                        spec,
                        capture,
                        authorization,
                        admission,
                        ledger,
                        state,
                        due,
                        client,
                        nonce_hash,
                        status,
                        data_client_factory,
                        build_fund,
                        dispatch,
                        moment,
                        retry_clock=now,
                        stop_event=stop_event,
                        expires_at=expires_at,
                    )
            latest = Ledger(root.path / "paper" / fund).latest()
            last_session = latest.session if latest is not None else None
            sessions_completed += 1
            status["sessions_completed"] = sessions_completed
            status["last_session"] = last_session
            status["reason"] = None
            status["status"] = "running"
            _write_status(root, fund, nonce_hash, status)
            if stop_event.is_set():
                break
    except UnresolvedTickIntentRefusal as exc:
        status["status"] = "failed"
        status["reason"] = exc.reason
        status["refusal"] = exc.fields
        raise
    except AuthorizationDenied as exc:
        if stop_event.is_set():
            status["status"] = "stopped"
            status["reason"] = "stop-requested"
        elif _validated_now(now()) >= expires_at:
            status["status"] = "completed"
            status["reason"] = "expiry-reached"
        else:
            status["status"] = "failed"
            status["reason"] = f"runner-{type(exc).__name__}"
    except Exception as exc:
        status["status"] = "failed"
        status["reason"] = f"runner-{type(exc).__name__}"
    finally:
        watcher_done.set()
        watcher.join(timeout=1.0)
        if status["status"] == "running":
            status["status"] = "stopped" if stop_event.is_set() else "completed"
            if status.get("reason") is None:
                status["reason"] = "stop-requested" if stop_event.is_set() else "runner-finished"
        status["sessions_completed"] = sessions_completed
        status["last_session"] = last_session
        try:
            _write_status(root, fund, nonce_hash, status)
        except Exception as exc:
            raise OwnedRunnerError("runner terminal status could not be published") from exc


def _execute_session(
    root: RootContext,
    fund: str,
    spec: FundSpec,
    capture: FrozenCapture,
    authorization: RunnerAuthorization,
    admission: AdmissionCoordinator,
    ledger: Ledger,
    state,
    due: str,
    data_client,
    nonce_hash: str,
    status: dict,
    data_client_factory,
    build_fund,
    dispatch: ProviderDispatch,
    now: datetime,
    *,
    retry_clock: Callable[[], datetime],
    stop_event: threading.Event,
    expires_at: datetime,
) -> None:
    due_set = (due,)
    authorize_session(
        authorization,
        root_id=capture.root_id,
        deployment_id=fund,
        capture_digest=capture.digest,
        operation_id=authorization.operation_id,
        operation_digest=authorization.operation_digest,
        due_set=due_set,
        now=now,
    )
    with admission.execution_lease(fund, timeout=0):
        def require_retry_authority() -> None:
            if stop_event.is_set():
                raise AuthorizationDenied("runner stop was requested")
            if _validated_now(retry_clock()) >= expires_at:
                raise AuthorizationDenied("runner deadline expired")

        while True:
            require_retry_authority()
            try:
                require_enrollment(root)
                verify_ledger_head(root, fund)
                current = Ledger(root.path / "paper" / fund).replay(spec.capital, full=True)
            except InventoryObservationUnavailable:
                stop_event.wait(0.25)
                continue
            if current.prev_hash != state.prev_hash or current.last_session != state.last_session:
                raise HandoverError("ledger head changed before runner admission")
            break
        while True:
            require_retry_authority()
            try:
                record = tick(
                    root.path / "paper" / fund,
                    data_client,
                    session=due,
                    expected_head=current.prev_hash,
                    build_fund=((lambda selected: build_fund(selected, capture, root, dispatch)) if build_fund is not None else (lambda selected: _build_fund(selected, capture, root, dispatch))),
                    now=lambda: _validated_now(retry_clock()).astimezone(NEW_YORK),
                    operation_id=authorization.operation_id,
                    request_id=f"runner:{authorization.operation_id}:{due}",
                    capture_id=capture.capture_id,
                    capture_digest=capture.digest,
                )
                break
            except PaperPreflightBusy:
                stop_event.wait(0.25)
    status["sessions_completed"] = status.get("sessions_completed", 0) + 1
    status["last_session"] = record.session
    _write_status(root, fund, nonce_hash, status)


def _client_context(root, capture, factory, dispatch):
    if factory is not None:
        value = factory(capture, root, dispatch)
        if not hasattr(value, "__enter__") or not hasattr(value, "__exit__"):
            raise OwnedRunnerError("runner data client is invalid")
        return value

    class _ClientContext:
        def __enter__(self):
            paths.ensure_directory(root.path / "cache")
            self._raw_client = make_data_client(
                provider=capture.data_provider,
                dispatch=dispatch,
            )
            self._client = self._raw_client.__enter__()
            return CachedDataClient(
                self._client,
                cache_dir=root.resolve("cache"),
            )

        def __exit__(self, exc_type, exc, traceback):
            return self._raw_client.__exit__(exc_type, exc, traceback)

    return _ClientContext()


def _build_fund(
    spec: FundSpec,
    capture: FrozenCapture,
    root: RootContext,
    dispatch: ProviderDispatch,
) -> Fund:
    cache_id = runner_key(spec.name)
    cache_relative = f"cache/llm/{cache_id}"
    paths.ensure_directory(root.path.joinpath(*cache_relative.split("/")))
    cache = PromptCache(root.resolve(cache_relative))

    def llm_factory(_model_spec):
        return make_llm(
            model=capture.model,
            timeout=capture.timeout_seconds,
            max_tokens=int(capture.parameters.get("max_tokens", 4096)),
            temperature=capture.parameters.get("temperature"),
            top_p=capture.parameters.get("top_p"),
            context_size=int(capture.parameters.get("context_size", 8192)),
            api_key=None,
            endpoint=capture.endpoint,
            use_environment=False,
            dispatch=dispatch,
        )

    return Fund(
        spec,
        blind=True,
        cache=cache,
        llm_factory=llm_factory,
        breakpoints_dispatch=dispatch,
    )


def _require_local_capture(capture: FrozenCapture) -> None:
    approved_models = {capture.model}
    data_target = ProviderTarget(kind="data", provider=capture.data_provider)
    llm_target = ProviderTarget(
        kind="llm",
        provider=capture.llm_provider,
        model=capture.model,
        endpoint=capture.endpoint,
    )
    if classify_provider(data_target, approved_local_models=approved_models) is not ProviderClass.FREE_DATA:
        raise OwnedRunnerError("runner data provider is not free")
    if classify_provider(llm_target, approved_local_models=approved_models) is not ProviderClass.LOCAL:
        raise OwnedRunnerError("runner requires an approved local model endpoint")
    if classify_provider(KEN_FRENCH_BREAKPOINTS_TARGET) is not ProviderClass.FREE_DATA:
        raise OwnedRunnerError("runner breakpoint provider is not free")
    if capture.credential_versions or capture.credential_handles:
        raise OwnedRunnerError("runner cannot use credential handles")


def _runner_authorization(raw, capture) -> RunnerAuthorization:
    if not isinstance(raw, dict):
        raise OwnedRunnerError("runner authorization is invalid")
    expected = {
        "initial_due_set",
        "expires_at",
        "max_sessions",
        "max_calls",
        "max_resources",
        "operation_id",
        "operation_digest",
    }
    if set(raw) != expected:
        raise OwnedRunnerError("runner authorization fields are invalid")
    data_target = ProviderTarget(kind="data", provider=capture.data_provider)
    llm_target = ProviderTarget(
        kind="llm",
        provider=capture.llm_provider,
        model=capture.model,
        endpoint=capture.endpoint,
    )
    breakpoints_target = KEN_FRENCH_BREAKPOINTS_TARGET
    return RunnerAuthorization(
        root_id=capture.root_id,
        deployment_id=capture.subject_id,
        capture_digest=capture.digest,
        operation_id=raw["operation_id"],
        operation_digest=raw["operation_digest"],
        provider_ids=(
            data_target.identity,
            llm_target.identity,
            breakpoints_target.identity,
        ),
        expires_at=_parse_datetime(raw["expires_at"]),
        max_sessions=raw["max_sessions"],
        max_calls=raw["max_calls"],
        max_resources=raw["max_resources"],
        initial_due_set=tuple(raw["initial_due_set"]),
    )


def _write_status(root, fund, nonce_hash, status) -> None:
    current = read_runner_record(root, fund, "state")
    if current is None or current.get("nonce_hash") != nonce_hash:
        raise OwnedRunnerError("runner state ownership changed")
    status["updated_at"] = _datetime_text(datetime.now(timezone.utc))
    write_runner_record(root, fund, "state", status)


def _reject_legacy_pid(root: RootContext, fund: str) -> None:
    try:
        root.file_info(f"paper/{fund}/runner.pid")
    except FileNotFoundError:
        return
    except (OSError, RootPathError):
        raise OwnedRunnerError("legacy runner state is unavailable") from None
    raise OwnedRunnerError("legacy runner state blocks owned execution")


def _validated_now(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise OwnedRunnerError("runner clock must be timezone-aware")
    return value.astimezone(timezone.utc)


def _parse_datetime(value: object) -> datetime:
    if not isinstance(value, str):
        raise OwnedRunnerError("runner time is invalid")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        raise OwnedRunnerError("runner time is invalid") from None
    return _validated_now(parsed)


def _datetime_text(value: datetime) -> str:
    return _validated_now(value).isoformat(timespec="seconds")


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
