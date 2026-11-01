"""Root-private state and exact-process controls for finite paper runners."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import sysconfig
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from secrets import token_urlsafe
from typing import Any

from hedge_fund.pipeline.session import code_version
from hedge_fund.runtime.admission import (
    AdmissionCoordinator,
    AdmissionError,
    PROTOCOL_VERSION,
)
from hedge_fund.runtime.capture import FrozenCapture
from hedge_fund.runtime.configuration import build_child_environment
from hedge_fund.runtime.handover import (
    require_enrollment,
    root_binding,
    verify_root_inventory,
)
from hedge_fund.runtime.ownership import (
    identity_matches,
    process_identity,
    ProcessIdentityError,
)
from hedge_fund.runtime.root import (
    ensure_unique_resource_name,
    PRIVATE_ROOT,
    RootContext,
    RootPathError,
)

RUNNER_ROOT = f"{PRIVATE_ROOT}/runners"
_MAX_RECORD_BYTES = 2 * 1024 * 1024
_MAX_SESSIONS = 100
_MAX_OPERATION_SECONDS = 24 * 60 * 60
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SESSION_KEY = re.compile(r"^\d{4}-\d{2}-\d{2}(?:T\d{2}:\d{2}:\d{2})?$")
_ACTIVE_STATES = frozenset({"starting", "running", "stopping"})
_TERMINAL_STATES = frozenset({"completed", "stopped", "failed"})


class OwnedRunnerError(RuntimeError):
    """Owned runner start, status or stop failed."""


class RunnerOwnershipUnknown(OwnedRunnerError):
    """Exact child process ownership is not verified."""


@dataclass(slots=True)
class _ProcessRef:
    process: subprocess.Popen
    identity: dict[str, Any]
    nonce_hash: str


class OwnedRunnerManager:
    """Launch detached children and control only exact in-process Popen handles."""

    def __init__(
        self,
        root: RootContext,
        admission: AdmissionCoordinator,
    ) -> None:
        if not isinstance(root, RootContext) or not isinstance(admission, AdmissionCoordinator):
            raise TypeError("explicit root and admission are required")
        if admission.root is not root:
            raise TypeError("runner admission root does not match")
        root.revalidate()
        self._root = root
        self._admission = admission
        self._processes: dict[str, _ProcessRef] = {}
        self._guard = threading.RLock()

    def start(
        self,
        fund: str,
        capture: FrozenCapture,
        *,
        expected_head: str | None,
        initial_due_set: tuple[str, ...],
        max_sessions: int,
        expires_at: datetime,
        max_calls: int,
        max_resources: int,
    ) -> dict[str, object]:
        name, _key = _fund_key(fund)
        try:
            with self._admission.deployment_lock(name, timeout=0):
                return self._start_locked(
                    fund,
                    capture,
                    expected_head=expected_head,
                    initial_due_set=initial_due_set,
                    max_sessions=max_sessions,
                    expires_at=expires_at,
                    max_calls=max_calls,
                    max_resources=max_resources,
                )
        except AdmissionError:
            raise OwnedRunnerError("runner deployment admission is unavailable") from None

    def _start_locked(
        self,
        fund: str,
        capture: FrozenCapture,
        *,
        expected_head: str | None,
        initial_due_set: tuple[str, ...],
        max_sessions: int,
        expires_at: datetime,
        max_calls: int,
        max_resources: int,
    ) -> dict[str, object]:
        name, key = _fund_key(fund)
        if not isinstance(capture, FrozenCapture) or capture.subject_id != name:
            raise OwnedRunnerError("runner capture does not match the deployment")
        if capture.broker != "paper":
            raise OwnedRunnerError("runner requires a local-paper capture")
        if type(max_sessions) is not int or not 1 <= max_sessions <= _MAX_SESSIONS:
            raise OwnedRunnerError("runner session bound is invalid")
        if type(max_calls) is not int or not 1 <= max_calls <= 10000:
            raise OwnedRunnerError("runner call bound is invalid")
        if type(max_resources) is not int or not 1 <= max_resources <= 1_000_000:
            raise OwnedRunnerError("runner resource bound is invalid")
        if expected_head is not None and (not isinstance(expected_head, str) or not _SHA256.fullmatch(expected_head)):
            raise OwnedRunnerError("runner ledger head is invalid")
        if not isinstance(initial_due_set, tuple) or len(initial_due_set) > 1:
            raise OwnedRunnerError("runner initial due-set is invalid")
        if any(not isinstance(value, str) or not value.strip() for value in initial_due_set):
            raise OwnedRunnerError("runner initial due-set is invalid")
        if not isinstance(expires_at, datetime) or expires_at.tzinfo is None or expires_at.utcoffset() is None:
            raise OwnedRunnerError("runner expiry is invalid")
        now = datetime.now(timezone.utc)
        remaining = (expires_at.astimezone(timezone.utc) - now).total_seconds()
        if remaining <= 0 or remaining > _MAX_OPERATION_SECONDS:
            raise OwnedRunnerError("runner expiry is outside the supported bound")

        self._root.revalidate()
        if not self._root.verify_private_storage():
            raise OwnedRunnerError("private runner storage is unverified")
        try:
            record = require_enrollment(self._root)
            verify_root_inventory(self._root, record=record)
        except Exception:
            raise OwnedRunnerError("offline root enrollment or inventory is unavailable") from None
        head_entry = record["heads"].get(name)
        if not isinstance(head_entry, dict) or head_entry.get("head_hash") != expected_head:
            raise OwnedRunnerError("runner ledger head changed after review")
        self._reject_legacy_pid(name)
        directory = f"{RUNNER_ROOT}/{key}"
        launch_path = f"{directory}/launch.json"
        state_path = f"{directory}/state.json"
        control_path = f"{directory}/control.json"
        self._root.mkdir(directory, parents=True, mode=0o700)
        prior = _read_record(self._root, state_path, missing_ok=True)
        if prior is not None and prior.get("status") not in _TERMINAL_STATES:
            raise OwnedRunnerError("runner state is active or unknown; offline recovery is required")
        try:
            with self._admission.runner_reservation(name, timeout=0):
                pass
        except AdmissionError:
            raise OwnedRunnerError("another runner or manual session owns this deployment") from None

        nonce = token_urlsafe(32)
        nonce_hash = _sha256(nonce.encode("utf-8"))
        launch = {
            "schema": 1,
            "protocol_version": PROTOCOL_VERSION,
            "build_id": code_version(),
            "root": root_binding(self._root),
            "fund": name,
            "nonce": nonce,
            "created_at": _datetime_text(now),
            "capture": json.loads(capture.private_bytes().decode("utf-8")),
            "authorization": {
                "initial_due_set": list(initial_due_set),
                "expires_at": _datetime_text(expires_at),
                "max_sessions": max_sessions,
                "max_calls": max_calls,
                "max_resources": max_resources,
            },
        }
        state = {
            "schema": 1,
            "protocol_version": PROTOCOL_VERSION,
            "build_id": code_version(),
            "root": root_binding(self._root),
            "fund": name,
            "nonce_hash": nonce_hash,
            "status": "starting",
            "created_at": launch["created_at"],
            "expires_at": launch["authorization"]["expires_at"],
            "max_sessions": max_sessions,
            "sessions_completed": 0,
            "last_session": None,
            "reason": None,
            "pid": None,
            "process_identity": None,
        }
        control = {
            "schema": 1,
            "protocol_version": PROTOCOL_VERSION,
            "build_id": code_version(),
            "root": root_binding(self._root),
            "fund": name,
            "nonce_hash": nonce_hash,
            "launch_ready": False,
            "stop_requested": False,
            "requested_at": None,
        }
        _write_record(self._root, launch_path, launch)
        _write_record(self._root, state_path, state)
        _write_record(self._root, control_path, control)

        env = build_child_environment(
            self._root,
            child_id=f"runner-{key[:24]}",
            settings=_capture_settings(capture),
        )
        command = _runner_command(self._root, name)
        options: dict[str, object] = {
            "stdin": subprocess.DEVNULL,
            "stdout": subprocess.DEVNULL,
            "stderr": subprocess.DEVNULL,
            "cwd": os.fspath(Path(__file__).resolve().parents[2]),
            "env": env,
        }
        if os.name == "nt":
            options["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200) | getattr(subprocess, "DETACHED_PROCESS", 0x00000008)
        else:
            options["start_new_session"] = True
        process = None
        try:
            process = subprocess.Popen(command, **options)
            identity = process_identity(process.pid)
            state["pid"] = process.pid
            state["process_identity"] = identity
            _write_record(self._root, state_path, state)
            control["launch_ready"] = True
            _write_record(self._root, control_path, control)
        except (OSError, OwnedRunnerError, ProcessIdentityError) as exc:
            state["status"] = "failed"
            state["reason"] = f"launch-{type(exc).__name__}"
            try:
                _write_record(self._root, state_path, state)
                control["launch_ready"] = True
                control["stop_requested"] = True
                control["requested_at"] = _datetime_text(datetime.now(timezone.utc))
                _write_record(self._root, control_path, control)
            except Exception:
                pass
            raise OwnedRunnerError("owned runner could not be launched") from None

        with self._guard:
            self._processes[key] = _ProcessRef(process, identity, nonce_hash)
        deadline = time.monotonic() + 8.0
        while time.monotonic() < deadline:
            observed = _read_record(self._root, state_path, missing_ok=True)
            if observed is not None and observed.get("nonce_hash") == nonce_hash:
                if not self._valid_state(observed, name):
                    raise RunnerOwnershipUnknown("runner state identity is invalid")
                status = observed.get("status")
                if status == "running":
                    if not self._matches_process(key, observed):
                        raise RunnerOwnershipUnknown("runner process incarnation does not match")
                    return self._public_state(observed, stopping=False)
                if status in _TERMINAL_STATES:
                    if status in {"stopped", "completed"} and (observed.get("pid") == process.pid and observed.get("process_identity") == identity):
                        return self._public_state(observed, stopping=False)
                    raise OwnedRunnerError("owned runner did not reach running state")
            if process.poll() is not None:
                self._mark_start_failed(
                    state_path,
                    nonce_hash,
                    "runner-exited-before-ready",
                )
                raise OwnedRunnerError("owned runner exited before readiness")
            time.sleep(0.025)
        self._request_stop_record(name, key, nonce_hash)
        self._mark_start_failed(state_path, nonce_hash, "runner-readiness-timeout")
        raise OwnedRunnerError("owned runner readiness timed out")

    def status(self, fund: str) -> dict[str, object]:
        name, key = _fund_key(fund)
        state_path = f"{RUNNER_ROOT}/{key}/state.json"
        try:
            state = _read_record(self._root, state_path, missing_ok=True)
        except OwnedRunnerError:
            return _unknown_state("runner ownership record is unavailable")
        if state is None:
            if self._legacy_pid_present(name):
                return _unknown_state("legacy runner presence is unverified")
            return _public_state("stopped", reason="No owned runner is active.")
        if not self._valid_state(state, name):
            return _unknown_state("runner ownership record is invalid")
        status = state.get("status")
        if status in _TERMINAL_STATES:
            return self._public_state(state, stopping=False)
        if status not in _ACTIVE_STATES:
            return _unknown_state("runner ownership state is unknown")
        if not self._matches_process(key, state):
            return _unknown_state("runner owner is not verified in this server process")
        try:
            control = _read_record(
                self._root,
                f"{RUNNER_ROOT}/{key}/control.json",
                missing_ok=True,
            )
        except OwnedRunnerError:
            return _unknown_state("runner control record is unavailable")
        if not validate_runner_control(self._root, name, state["nonce_hash"], control):
            return _unknown_state("runner control record is invalid")
        stopping = bool(control["stop_requested"] is True)
        return self._public_state(state, stopping=stopping)

    def request_stop(self, fund: str) -> dict[str, object]:
        name, key = _fund_key(fund)
        state_path = f"{RUNNER_ROOT}/{key}/state.json"
        state = _read_record(self._root, state_path, missing_ok=True)
        if state is None or not self._valid_state(state, name) or state.get("status") not in _ACTIVE_STATES:
            raise RunnerOwnershipUnknown("owned runner is not available for stop")
        if not self._matches_process(key, state):
            raise RunnerOwnershipUnknown("runner process incarnation is not verified")
        if self._legacy_pid_present(name):
            raise RunnerOwnershipUnknown("legacy runner presence blocks stop")
        control_path = f"{RUNNER_ROOT}/{key}/control.json"
        control = _read_record(self._root, control_path, missing_ok=True)
        if not validate_runner_control(self._root, name, state["nonce_hash"], control):
            raise RunnerOwnershipUnknown("runner control identity is invalid")
        if not control["stop_requested"]:
            control["stop_requested"] = True
            control["requested_at"] = _datetime_text(datetime.now(timezone.utc))
            _write_record(self._root, control_path, control)
        return self._public_state(state, stopping=True)

    def _matches_process(self, key: str, state: dict[str, Any]) -> bool:
        with self._guard:
            process_ref = self._processes.get(key)
        if process_ref is None or process_ref.process.poll() is not None:
            return False
        if state.get("pid") != process_ref.process.pid:
            return False
        if state.get("nonce_hash") != process_ref.nonce_hash:
            return False
        if state.get("process_identity") != process_ref.identity:
            return False
        return identity_matches(process_ref.process.pid, process_ref.identity)

    def _valid_state(self, state: dict[str, Any], fund: str) -> bool:
        try:
            return validate_runner_state(self._root, fund, state)
        except (OSError, RootPathError, ValueError):
            return False

    def _mark_start_failed(
        self,
        state_path: str,
        nonce_hash: str,
        reason: str,
    ) -> None:
        try:
            state = _read_record(self._root, state_path, missing_ok=True)
            if state is not None and state.get("nonce_hash") == nonce_hash and state.get("status") == "starting":
                state["status"] = "failed"
                state["reason"] = reason
                _write_record(self._root, state_path, state)
        except Exception:
            pass

    def _public_state(
        self,
        state: dict[str, Any],
        *,
        stopping: bool,
    ) -> dict[str, object]:
        status = "stopping" if stopping else state.get("status", "unknown")
        return {
            "status": status,
            "available": status in {"running", "stopping"},
            "reason": state.get("reason"),
            "started_at": state.get("created_at"),
            "expires_at": state.get("expires_at"),
            "sessions_completed": state.get("sessions_completed", 0),
            "max_sessions": state.get("max_sessions"),
            "last_session": state.get("last_session"),
        }

    def _request_stop_record(self, fund: str, key: str, nonce_hash: str) -> None:
        path = f"{RUNNER_ROOT}/{key}/control.json"
        control = _read_record(self._root, path, missing_ok=True)
        if not validate_runner_control(self._root, fund, nonce_hash, control):
            return
        control["stop_requested"] = True
        control["requested_at"] = _datetime_text(datetime.now(timezone.utc))
        control["launch_ready"] = True
        _write_record(self._root, path, control)

    def _legacy_pid_present(self, fund: str) -> bool:
        path = f"paper/{fund}/runner.pid"
        try:
            self._root.file_info(path)
        except FileNotFoundError:
            return False
        except (OSError, RootPathError):
            return True
        return True

    def _reject_legacy_pid(self, fund: str) -> None:
        if self._legacy_pid_present(fund):
            raise RunnerOwnershipUnknown("legacy runner presence blocks start")


def runner_paths(fund: str) -> tuple[str, str, str]:
    _name, key = _fund_key(fund)
    directory = f"{RUNNER_ROOT}/{key}"
    return (
        f"{directory}/launch.json",
        f"{directory}/state.json",
        f"{directory}/control.json",
    )


def read_runner_record(
    root: RootContext,
    fund: str,
    kind: str,
) -> dict[str, Any] | None:
    if kind not in {"launch", "state", "control"}:
        raise ValueError("runner record kind is invalid")
    launch_path, state_path, control_path = runner_paths(fund)
    path = {"launch": launch_path, "state": state_path, "control": control_path}[kind]
    return _read_record(root, path, missing_ok=True)


def write_runner_record(root: RootContext, fund: str, kind: str, value: dict[str, Any]) -> None:
    if kind not in {"launch", "state", "control"}:
        raise ValueError("runner record kind is invalid")
    launch_path, state_path, control_path = runner_paths(fund)
    path = {"launch": launch_path, "state": state_path, "control": control_path}[kind]
    _write_record(root, path, value)


def runner_key(fund: str) -> str:
    return _fund_key(fund)[1]


def validate_runner_state(
    root: RootContext,
    fund: str,
    state: object,
) -> bool:
    if not isinstance(state, dict):
        return False
    required = {
        "schema",
        "protocol_version",
        "build_id",
        "root",
        "fund",
        "nonce_hash",
        "status",
        "created_at",
        "expires_at",
        "max_sessions",
        "sessions_completed",
        "last_session",
        "reason",
        "pid",
        "process_identity",
    }
    optional = {"started_at", "updated_at"}
    if not required.issubset(state) or set(state) - required - optional:
        return False
    try:
        name, _key = _fund_key(fund)
        if (
            type(state["schema"]) is not int
            or state["schema"] != 1
            or type(state["protocol_version"]) is not int
            or state["protocol_version"] != PROTOCOL_VERSION
            or state["build_id"] != code_version()
            or state["root"] != root_binding(root)
            or state["fund"] != name
            or not isinstance(state["nonce_hash"], str)
            or not _SHA256.fullmatch(state["nonce_hash"])
            or state["status"] not in _ACTIVE_STATES.union(_TERMINAL_STATES)
        ):
            return False
        _parse_datetime(state["created_at"])
        expires_at = _parse_datetime(state["expires_at"])
        if expires_at <= _parse_datetime(state["created_at"]):
            return False
        if type(state["max_sessions"]) is not int or not 1 <= state["max_sessions"] <= _MAX_SESSIONS or type(state["sessions_completed"]) is not int or not 0 <= state["sessions_completed"] <= state["max_sessions"]:
            return False
        last_session = state["last_session"]
        if last_session is not None and (not isinstance(last_session, str) or not _SESSION_KEY.fullmatch(last_session)):
            return False
        reason = state["reason"]
        if reason is not None and (not isinstance(reason, str) or not 1 <= len(reason) <= 128 or any(not (char.isascii() and (char.isalnum() or char in "._-")) for char in reason)):
            return False
        pid = state["pid"]
        identity = state["process_identity"]
        if pid is None:
            if identity is not None or state["status"] in {"running", "stopping", "stopped", "completed"}:
                return False
        elif type(pid) is not int or pid <= 0 or not isinstance(identity, dict) or set(identity) != {"pid", "creation_time", "image", "host", "namespace"} or type(identity.get("pid")) is not int or identity.get("pid") != pid or any(not isinstance(identity.get(key), str) or not identity[key] for key in ("creation_time", "image", "host", "namespace")):
            return False
        for field in ("started_at", "updated_at"):
            if field in state:
                _parse_datetime(state[field])
        return True
    except (OSError, OwnedRunnerError, RootPathError, TypeError, ValueError):
        return False


def validate_runner_control(
    root: RootContext,
    fund: str,
    nonce_hash: str,
    control: object,
) -> bool:
    if not isinstance(control, dict):
        return False
    try:
        name, _key = _fund_key(fund)
        if (
            set(control)
            != {
                "schema",
                "protocol_version",
                "build_id",
                "root",
                "fund",
                "nonce_hash",
                "launch_ready",
                "stop_requested",
                "requested_at",
            }
            or type(control["schema"]) is not int
            or control["schema"] != 1
            or type(control["protocol_version"]) is not int
            or control["protocol_version"] != PROTOCOL_VERSION
            or control["build_id"] != code_version()
            or control["root"] != root_binding(root)
            or control["fund"] != name
            or control["nonce_hash"] != nonce_hash
            or type(control["launch_ready"]) is not bool
            or type(control["stop_requested"]) is not bool
        ):
            return False
        requested_at = control["requested_at"]
        if requested_at is not None:
            _parse_datetime(requested_at)
        return control["stop_requested"] == (requested_at is not None)
    except (OSError, OwnedRunnerError, RootPathError, TypeError, ValueError):
        return False


def _fund_key(fund: str) -> tuple[str, str]:
    try:
        name = ensure_unique_resource_name(fund, [])
    except (TypeError, RootPathError):
        raise OwnedRunnerError("runner fund identity is invalid") from None
    return name, _sha256(name.casefold().encode("utf-8"))


def _capture_settings(capture: FrozenCapture):
    from hedge_fund.runtime.configuration import RuntimeSettings

    return RuntimeSettings(
        data_provider=capture.data_provider,
        llm_provider=capture.llm_provider,
        model=capture.model,
        endpoint=capture.endpoint,
        timeout_seconds=capture.timeout_seconds,
        parameters=capture.parameters,
        version=capture.settings_version,
        provenance=capture.provenance,
    )


def _read_record(
    root: RootContext,
    path: str,
    *,
    missing_ok: bool,
) -> dict[str, Any] | None:
    try:
        info = root.file_info(path)
    except FileNotFoundError:
        if missing_ok:
            return None
        raise OwnedRunnerError("runner record is missing") from None
    except (OSError, RootPathError):
        raise OwnedRunnerError("runner record is unavailable") from None
    if info.size <= 0 or info.size > _MAX_RECORD_BYTES:
        raise OwnedRunnerError("runner record size is invalid")
    try:
        value = json.loads(
            root.read_bytes(path).decode("utf-8"),
            object_pairs_hook=_unique_mapping,
        )
    except (UnicodeDecodeError, ValueError, OSError, RootPathError):
        raise OwnedRunnerError("runner record is malformed") from None
    if not isinstance(value, dict):
        raise OwnedRunnerError("runner record is malformed")
    return value


def _write_record(root: RootContext, path: str, value: dict[str, Any]) -> None:
    if not isinstance(value, dict):
        raise TypeError("runner record must be a mapping")
    payload = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    if len(payload) > _MAX_RECORD_BYTES:
        raise OwnedRunnerError("runner record exceeds its bound")
    try:
        root.write_bytes(path, payload, mode=0o600)
    except (OSError, RootPathError):
        raise OwnedRunnerError("runner record could not be written") from None


def _public_state(status: str, *, reason: str) -> dict[str, object]:
    return {
        "status": status,
        "available": False,
        "reason": reason,
        "started_at": None,
        "expires_at": None,
        "sessions_completed": 0,
        "max_sessions": None,
        "last_session": None,
    }


def _unknown_state(reason: str) -> dict[str, object]:
    return _public_state("unknown", reason=reason)


def _parse_datetime(value: object) -> datetime:
    if not isinstance(value, str):
        raise OwnedRunnerError("runner time is invalid")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        raise OwnedRunnerError("runner time is invalid") from None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise OwnedRunnerError("runner time is invalid")
    return parsed.astimezone(timezone.utc)


def _runner_command(root: RootContext, fund: str) -> list[str]:
    arguments = [
        "--root",
        os.fspath(root.path),
        "--fund",
        fund,
    ]
    module = "hedge_fund.runtime.owned_runner_child"
    if os.name != "nt":
        return [sys.executable, "-m", module, *arguments]

    base_executable = getattr(sys, "_base_executable", None)
    if not isinstance(base_executable, str) or not os.path.isabs(base_executable) or not os.path.isfile(base_executable):
        raise OwnedRunnerError("direct runner interpreter is unavailable")
    base_executable = os.path.abspath(base_executable)
    if os.path.normcase(base_executable) == os.path.normcase(os.path.abspath(sys.executable)):
        return [base_executable, "-m", module, *arguments]

    try:
        paths = sysconfig.get_paths()
    except (OSError, TypeError, ValueError):
        raise OwnedRunnerError("runner package paths are unavailable") from None
    site_directories = []
    for key in ("purelib", "platlib"):
        directory = paths.get(key)
        if not isinstance(directory, str) or not os.path.isabs(directory) or not os.path.isdir(directory):
            raise OwnedRunnerError("runner package paths are invalid")
        if os.path.normcase(os.path.abspath(directory)) not in {os.path.normcase(os.path.abspath(value)) for value in site_directories}:
            site_directories.append(directory)
    bootstrap = "import importlib.util,runpy,site,sys\n" f"_site_count={len(site_directories)}\n" "_args=sys.argv[1:]\n" "for _path in _args[:_site_count]:\n" " site.addsitedir(_path)\n" "sys.argv=['aihf-owned-paper-runner',*_args[_site_count:]]\n" "if importlib.util.find_spec('sitecustomize') is not None:\n" " import sitecustomize\n" f"runpy.run_module({module!r},run_name='__main__')\n"
    return [
        base_executable,
        "-S",
        "-c",
        bootstrap,
        *site_directories,
        *arguments,
    ]


def _unique_mapping(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("runner record contains duplicate fields")
        result[key] = value
    return result


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _datetime_text(value: datetime) -> str:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise OwnedRunnerError("runner time must be timezone-aware")
    return value.astimezone(timezone.utc).isoformat(timespec="seconds")
