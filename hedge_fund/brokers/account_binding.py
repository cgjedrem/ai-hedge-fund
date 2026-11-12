"""Fake-only SIM account/environment binding registry (Spec 005 T096 policy slice).

The registry is a private, per-user store outside every fund root. It records at
most one active binding per SIM account identity across all fund roots and
requires explicit release provenance before an account moves to another owner.

Account identities are never persisted or reported: the registry keeps only a
keyed HMAC digest whose key lives in the registry's verified private storage.

Global exclusive custody cannot be verified yet: other OS accounts use other
registries, a deleted or reinitialized registry forgets bindings, and arbitrary
same-account out-of-band writers are not excluded (T015/T021). The production
custody verifier therefore always reports ``ownership-unknown`` and binding or
transfer fails closed. The mutable AccountRegistry simulation is confined to
the checkout-owned synthetic test namespace. Custom custody/quiescence callbacks
cannot enable ordinary production initialization, reads, binding or release.
SIMAccountRegistry and the shared production ownership requirement always deny,
including inside the fake harness; synthetic receipts are never account authority.

Binding never constructs a broker, resolves a secret, contacts a network or
authorizes execution: ``execution_authorized`` is always ``False``.
Simulation receipts/views are explicitly ``policy_only`` and report global
custody as ``ownership-unknown``, even when the fake local policy admits a binding.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
from collections.abc import Callable, Iterator
from contextlib import contextmanager, ExitStack
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, NoReturn, Protocol, TypedDict

from hedge_fund.runtime.admission import (
    _acquire_os_lock,
    _release_os_lock,
    AdmissionError,
    MAX_LOCK_WAIT_SECONDS,
    OwnershipUnknown,
    root_registry_writer,
    WriterConflict,
)
from hedge_fund.runtime.handover import root_binding, write_authority
from hedge_fund.runtime.root import (
    ensure_unique_resource_name,
    PRIVATE_ROOT,
    RootContext,
    RootPathError,
)

SCHEMA = "sim-account-registry/v1"
SIM_ENVIRONMENT = "sim"
REGISTRY_DIRECTORY = f"{PRIVATE_ROOT}/sim-account-registry"
STATE_PATH = f"{REGISTRY_DIRECTORY}/registry.json"
KEY_PATH = f"{REGISTRY_DIRECTORY}/digest.key"
LOCK_PATH = f"{REGISTRY_DIRECTORY}/registry.lock"
_MAX_STATE_BYTES = 1024 * 1024
_MAX_BINDINGS = 1000
_MAX_PROVENANCE = 100
_KEY_BYTES = 32
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_ACCOUNT_KEY = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
_RUNNER_ACTIVE = frozenset({"starting", "running", "stopping"})
_RUNNER_TERMINAL = frozenset({"blocked", "completed", "stopped", "failed"})


class AccountBindingError(RuntimeError):
    """Base class for account binding denials. Messages never carry account identities."""

    reason = "account-binding-denied"


class AccountOwnershipUnknown(AccountBindingError):
    reason = "ownership-unknown"


class SIMOwnershipUnknown(AccountOwnershipUnknown, OwnershipUnknown):
    """No verifiable exclusive SIM account-control authority is available."""

    code = "ownership-unknown"
    authority_reason = "exclusive-account-control-unverifiable"

    def __init__(self) -> None:
        super().__init__("ownership-unknown: exclusive SIM account control cannot be verified; SIM mutation is unsupported")


class SIMOwnershipStatus(TypedDict):
    state: Literal["ownership-unknown"]
    reason: Literal["exclusive-account-control-unverifiable"]
    cross_root_inventory: Literal["unverifiable"]
    binding_supported: Literal[False]
    provisioning_supported: Literal[False]
    execution_authorized: Literal[False]


def require_sim_account_ownership() -> NoReturn:
    """Deny before reading credentials, account identities or registry paths."""
    raise SIMOwnershipUnknown()


class SIMAccountRegistry:
    """Permanently unavailable production authority, not the fake policy store.

    No identity, digest, key, binding or provenance is persisted. Inputs,
    including the root, are deliberately not retained as authority. The
    separate AccountRegistry simulation never grants production execution.
    """

    def __init__(self, root: RootContext) -> None:
        if not isinstance(root, RootContext):
            raise TypeError("an explicit RootContext is required")

    def bind(self, environment: str, account_identity: str, deployment: str) -> NoReturn:
        require_sim_account_ownership()

    def release(self, deployment: str, *, expected_binding_digest: str, request_id: str) -> NoReturn:
        """Quiescence alone cannot prove prior ownership or authorize release."""
        require_sim_account_ownership()

    def transfer(self, deployment: str, *, target_root: RootContext, target_deployment: str, expected_binding_digest: str, request_id: str) -> NoReturn:
        """Never fabricate released/transfer provenance from unverified claims."""
        require_sim_account_ownership()

    def inspect(self) -> SIMOwnershipStatus:
        """Return unavailable authority without probing or creating any files."""
        return {
            "state": "ownership-unknown",
            "reason": "exclusive-account-control-unverifiable",
            "cross_root_inventory": "unverifiable",
            "binding_supported": False,
            "provisioning_supported": False,
            "execution_authorized": False,
        }


class RealBrokerageDenied(AccountBindingError):
    reason = "real-brokerage-denied"


class AccountAlreadyBound(AccountBindingError):
    reason = "account-already-bound"


class DeploymentAlreadyBound(AccountBindingError):
    reason = "deployment-already-bound"


class ReleaseRequired(AccountBindingError):
    reason = "release-provenance-required"


class StaleRelease(AccountBindingError):
    reason = "stale-release-provenance"


class NotOwner(AccountBindingError):
    reason = "not-owner"


class RunnerNotQuiescent(AccountBindingError):
    reason = "runner-not-quiescent"


class RegistryBusy(AccountBindingError):
    reason = "registry-busy"


@dataclass(frozen=True)
class SimAccountIdentity:
    """A SIM account/environment identity. ``repr`` never reveals the account key."""

    environment: str
    account_key: str = field(repr=False)

    def __repr__(self) -> str:
        return "SimAccountIdentity(environment=<redacted>, account_key=<redacted>)"


@dataclass(frozen=True)
class CustodyAssessment:
    verified: bool
    reason: str


class CustodyVerifier(Protocol):
    def assess(self, registry: AccountRegistry, root: RootContext) -> CustodyAssessment:
        ...


class UnverifiableGlobalCustody:
    """Production verifier: global exclusive custody is not provable yet."""

    REASON = "global-custody-unverifiable"

    def assess(self, registry: AccountRegistry, root: RootContext) -> CustodyAssessment:
        return CustodyAssessment(False, self.REASON)


DEFAULT_CUSTODY = UnverifiableGlobalCustody()


@dataclass(frozen=True)
class RunnerQuiescence:
    quiescent: bool
    status: str


def _require_fake_registry_harness(*paths: str | os.PathLike[str]) -> None:
    """Confine policy simulation, never establish production account custody."""
    namespace = os.environ.get("HEDGE_FUND_TEST_ROOT", "")
    if os.environ.get("HEDGE_FUND_TEST_MODE") != "1" or not namespace or not Path(namespace).is_absolute():
        require_sim_account_ownership()
    try:
        from hedge_fund.test_support.network_guard import (
            _validate_test_child_path,
            _validate_test_root,
        )

        test_root = _validate_test_root(Path(namespace))
        for path in paths:
            _validate_test_child_path(test_root, Path(path))
    except (ImportError, OSError, RuntimeError, TypeError, ValueError):
        raise SIMOwnershipUnknown() from None


def default_registry_location(environ: dict[str, str] | None = None) -> Path:
    """Per-user registry directory, outside every fund root and the legacy home layout."""
    env = os.environ if environ is None else environ
    if os.name == "nt":
        base = env.get("LOCALAPPDATA", "")
    else:
        base = env.get("XDG_STATE_HOME", "") or (os.path.join(env.get("HOME", ""), ".local", "state") if env.get("HOME") else "")
    if not base or not os.path.isabs(base):
        raise AccountOwnershipUnknown("per-user registry location is unavailable")
    return Path(base) / "hedge-fund" / "sim-account-registry" / "v1"


def runner_quiescence(root: RootContext, deployment: str) -> RunnerQuiescence:
    """Read-only owned-runner observation; anything unverifiable is not quiescent."""
    from hedge_fund.runtime.owned_runner import (
        read_runner_record,
        validate_runner_state,
    )

    try:
        state = read_runner_record(root, deployment, "state")
    except Exception:
        return RunnerQuiescence(False, "unknown")
    if state is None:
        return RunnerQuiescence(True, "never-started")
    if not validate_runner_state(root, deployment, state):
        return RunnerQuiescence(False, "unknown")
    status = state["status"]
    if status in _RUNNER_TERMINAL:
        return RunnerQuiescence(True, status)
    if status in _RUNNER_ACTIVE:
        return RunnerQuiescence(False, status)
    return RunnerQuiescence(False, "unknown")


class AccountRegistry:
    """Atomic private fake-policy registry; no production custody or execution authority."""

    def __init__(self, context: RootContext) -> None:
        _require_fake_registry_harness(context.path)
        self._context = context

    @classmethod
    def initialize(cls, path: str | os.PathLike[str]) -> AccountRegistry:
        """Create a simulation in an existing, empty, absolute test-owned directory."""
        _require_fake_registry_harness(path)
        context = RootContext.open(path)
        try:
            if any(context.path.iterdir()):
                raise AccountOwnershipUnknown("registry initialization requires an empty directory")
            context.prepare_private_storage()
            context.mkdir(REGISTRY_DIRECTORY, parents=True, mode=0o700)
            context.write_bytes(KEY_PATH, secrets.token_bytes(_KEY_BYTES), mode=0o600)
            state = {"schema": SCHEMA, "registry_id": secrets.token_hex(16), "generation": 0, "bindings": {}}
            context.write_bytes(STATE_PATH, _canonical(state), mode=0o600)
            registry = cls(context)
            registry._load()
            return registry
        except BaseException:
            context.close()
            raise

    @classmethod
    def open(cls, path: str | os.PathLike[str]) -> AccountRegistry:
        """Open an initialized registry; missing, unprotected or corrupt state is ownership-unknown."""
        _require_fake_registry_harness(path)
        try:
            context = RootContext.open(path)
        except (OSError, RootPathError) as exc:
            raise AccountOwnershipUnknown(f"account registry is unavailable ({type(exc).__name__})") from None
        try:
            registry = cls(context)
            registry._load()
            return registry
        except BaseException:
            context.close()
            raise

    @property
    def path(self) -> Path:
        return self._context.path

    def close(self) -> None:
        self._context.close()

    def __enter__(self) -> AccountRegistry:
        return self

    def __exit__(self, *_exc_info) -> None:
        self.close()

    def inspect(self, account: SimAccountIdentity) -> dict[str, Any]:
        """Redacted readiness view. Provisioning never authorizes execution."""
        try:
            _require_fake_registry_harness(self.path)
            environment = _require_sim(account)
            state = self._load()
        except AccountBindingError as exc:
            return {"status": exc.reason, "environment": None, "deployment": None, "policy_only": True, "global_custody": "ownership-unknown", "execution_authorized": False}
        record = state["bindings"].get(self._digest(account, environment))
        if record is None:
            return {"status": "unbound", "environment": SIM_ENVIRONMENT, "deployment": None, "policy_only": True, "global_custody": "ownership-unknown", "execution_authorized": False}
        return {
            "status": record["status"],
            "environment": SIM_ENVIRONMENT,
            "deployment": record["deployment"] if record["status"] == "active" else None,
            "policy_only": True,
            "global_custody": "ownership-unknown",
            "execution_authorized": False,
        }

    def bind(
        self,
        root: RootContext,
        deployment: str,
        account: SimAccountIdentity,
        *,
        release_digest: str | None = None,
        custody: CustodyVerifier = DEFAULT_CUSTODY,
        lock_timeout: float = MAX_LOCK_WAIT_SECONDS,
    ) -> dict[str, Any]:
        """Bind a fake SIM account to one deployment; a released account needs its exact release digest."""
        _require_fake_registry_harness(self.path, root.path)
        environment = _require_sim(account)
        name = _deployment_name(deployment)
        if release_digest is not None and (not isinstance(release_digest, str) or not _SHA256.fullmatch(release_digest)):
            raise StaleRelease("release provenance digest is invalid")
        self._require_outside_root(root)
        with self._root_admission(root, name):
            assessment = custody.assess(self, root)
            if not isinstance(assessment, CustodyAssessment) or assessment.verified is not True:
                raise AccountOwnershipUnknown("global account custody is unverified (global-custody-unverifiable)")
            owner = self._owner_digest(root)
            with self._locked(lock_timeout) as state:
                digest = self._digest(account, environment)
                bindings = state["bindings"]
                for other_digest, other in bindings.items():
                    if other_digest != digest and other["status"] == "active" and other["owner"] == owner and other["deployment_key"] == _name_key(name):
                        raise DeploymentAlreadyBound("deployment already holds a different SIM account binding")
                record = bindings.get(digest)
                provenance: list[dict[str, Any]] = []
                if record is not None:
                    if record["status"] == "active":
                        if record["owner"] == owner and record["deployment_key"] == _name_key(name) and release_digest is None:
                            return self._receipt(state, record)
                        raise AccountAlreadyBound("SIM account is actively bound to another deployment or root")
                    if release_digest is None:
                        raise ReleaseRequired("released SIM account requires explicit release provenance")
                    if not hmac.compare_digest(record["release_digest"], release_digest):
                        raise StaleRelease("release provenance does not match the current registry state")
                    provenance = list(record["provenance"])
                    provenance.append({"from_owner": record["owner"], "from_deployment_key": record["deployment_key"], "release_digest": release_digest, "generation": state["generation"] + 1})
                    if len(provenance) > _MAX_PROVENANCE:
                        raise AccountOwnershipUnknown("account transfer provenance exceeds its bound")
                elif release_digest is not None:
                    raise StaleRelease("release provenance does not match the current registry state")
                if record is None and len(bindings) >= _MAX_BINDINGS:
                    raise AccountOwnershipUnknown("account registry capacity exceeded")
                state["generation"] += 1
                new = {
                    "environment": SIM_ENVIRONMENT,
                    "status": "active",
                    "owner": owner,
                    "deployment": name,
                    "deployment_key": _name_key(name),
                    "bound_generation": state["generation"],
                    "bound_at": _now(),
                    "release_digest": None,
                    "provenance": provenance,
                    "execution_authorized": False,
                }
                bindings[digest] = new
                return self._receipt(state, new)

    def release(
        self,
        root: RootContext,
        deployment: str,
        account: SimAccountIdentity,
        *,
        quiescence: Callable[[RootContext, str], RunnerQuiescence] = runner_quiescence,
        lock_timeout: float = MAX_LOCK_WAIT_SECONDS,
    ) -> dict[str, Any]:
        """Release an owned binding only while its deployment runner is stopped/quiescent."""
        _require_fake_registry_harness(self.path, root.path)
        environment = _require_sim(account)
        name = _deployment_name(deployment)
        self._require_outside_root(root)
        with self._root_admission(root, name, release=True):
            owner = self._owner_digest(root)
            with self._locked(lock_timeout) as state:
                record = state["bindings"].get(self._digest(account, environment))
                if record is None or record["status"] != "active" or record["owner"] != owner or record["deployment_key"] != _name_key(name):
                    raise NotOwner("release requires the active owning deployment")
                observed = quiescence(root, name)
                if not isinstance(observed, RunnerQuiescence) or observed.quiescent is not True:
                    raise RunnerNotQuiescent("release requires a stopped, quiescent deployment runner")
                state["generation"] += 1
                record["status"] = "released"
                record["released_generation"] = state["generation"]
                record["release_digest"] = hashlib.sha256(_canonical({"registry_id": state["registry_id"], "generation": state["generation"], "owner": record["owner"], "deployment_key": record["deployment_key"], "nonce": secrets.token_hex(16)})).hexdigest()
                return self._receipt(state, record)

    def _receipt(self, state: dict[str, Any], record: dict[str, Any]) -> dict[str, Any]:
        return {
            "status": record["status"],
            "environment": SIM_ENVIRONMENT,
            "deployment": record["deployment"],
            "generation": state["generation"],
            "release_digest": record["release_digest"],
            "transfers": len(record["provenance"]),
            "policy_only": True,
            "global_custody": "ownership-unknown",
            "execution_authorized": False,
        }

    def _require_outside_root(self, root: RootContext) -> None:
        if not isinstance(root, RootContext):
            raise TypeError("an explicit RootContext is required")
        registry = os.path.normcase(os.path.abspath(os.fspath(self.path)))
        fund = os.path.normcase(os.path.abspath(os.fspath(root.path)))
        try:
            shared = os.path.commonpath([registry, fund])
        except ValueError:
            # Different drive prefixes may alias one volume (subst, UNC admin shares); only a
            # distinct verified volume identity proves the registry is outside the fund root.
            if os.path.splitdrive(registry)[0] != os.path.splitdrive(fund)[0] and self._context.device_identity != root.device_identity:
                return
            raise AccountOwnershipUnknown("registry and root locations are not comparable") from None
        if shared in {registry, fund}:
            raise AccountOwnershipUnknown("root-local account bookkeeping cannot prove exclusivity")

    @contextmanager
    def _root_admission(self, root: RootContext, deployment: str, *, release: bool = False) -> Iterator[None]:
        """Hold root registry then deployment lanes; release also holds runner/execution lanes.

        Lane order matches ``AdmissionCoordinator.manual_session``/``multi_deployment``. Any
        held runner, execution or deployment lane during release means the deployment is not
        quiescent.
        """
        if write_authority(root)["authority"] != "protocol-native":
            raise AccountOwnershipUnknown("fund root write authority is not protocol-native")
        with ExitStack() as stack:
            try:
                coordinator = stack.enter_context(root_registry_writer(root, timeout=MAX_LOCK_WAIT_SECONDS))
            except WriterConflict:
                raise RegistryBusy("fund root registry lane is occupied") from None
            except AdmissionError as exc:
                raise AccountOwnershipUnknown(f"fund root ownership is unknown ({type(exc).__name__})") from None
            except Exception as exc:
                raise AccountOwnershipUnknown(f"fund root admission is unavailable ({type(exc).__name__})") from None
            try:
                stack.enter_context(coordinator.deployment_lock(deployment, timeout=0.0))
                if release:
                    stack.enter_context(coordinator.runner_reservation(deployment, timeout=0.0))
                    stack.enter_context(coordinator.execution_lease(deployment, timeout=0.0))
            except WriterConflict:
                if release:
                    raise RunnerNotQuiescent("release requires a stopped, quiescent deployment runner") from None
                raise RegistryBusy("deployment lane is occupied") from None
            except AdmissionError as exc:
                raise AccountOwnershipUnknown(f"deployment ownership is unknown ({type(exc).__name__})") from None
            yield

    def _owner_digest(self, root: RootContext) -> str:
        return self._keyed(b"owner", _canonical(root_binding(root)))

    def _digest(self, account: SimAccountIdentity, environment: str) -> str:
        key = account.account_key
        if not isinstance(key, str) or not _ACCOUNT_KEY.fullmatch(key):
            raise AccountBindingError("SIM account identity is invalid")
        return self._keyed(b"account", f"{environment}\0{key}".encode("utf-8"))

    def _keyed(self, purpose: bytes, value: bytes) -> str:
        return hmac.new(self._key(), purpose + b"\0" + value, hashlib.sha256).hexdigest()

    def _key(self) -> bytes:
        self._require_private()
        try:
            key = self._context.read_bytes(KEY_PATH)
        except (OSError, RootPathError) as exc:
            raise AccountOwnershipUnknown(f"account registry key is unavailable ({type(exc).__name__})") from None
        if len(key) != _KEY_BYTES:
            raise AccountOwnershipUnknown("account registry key is corrupt")
        return key

    def _require_private(self) -> None:
        if not self._context.verify_private_storage():
            raise AccountOwnershipUnknown("account registry private storage is unverified")

    def _load(self) -> dict[str, Any]:
        self._require_private()
        self._key()
        try:
            if self._context.file_info(STATE_PATH).size > _MAX_STATE_BYTES:
                raise AccountOwnershipUnknown("account registry state exceeds its bound")
            raw = self._context.read_bytes(STATE_PATH)
        except (OSError, RootPathError) as exc:
            raise AccountOwnershipUnknown(f"account registry state is unavailable ({type(exc).__name__})") from None
        try:
            state = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            raise AccountOwnershipUnknown("account registry state is corrupt") from None
        if not _valid_state(state) or raw != _canonical(state):
            raise AccountOwnershipUnknown("account registry state is corrupt")
        return state

    @contextmanager
    def _locked(self, timeout: float) -> Iterator[dict[str, Any]]:
        if type(timeout) not in {int, float} or not 0 <= timeout <= MAX_LOCK_WAIT_SECONDS:
            raise ValueError("lock timeout is out of bounds")
        self._require_private()
        try:
            handle = self._context.open_lock_file(LOCK_PATH, mode=0o600)
        except (OSError, RootPathError) as exc:
            raise AccountOwnershipUnknown(f"account registry lock is unavailable ({type(exc).__name__})") from None
        try:
            try:
                token = _acquire_os_lock(handle, float(timeout), exclusive=True)
            except WriterConflict:
                raise RegistryBusy("account registry is busy") from None
            try:
                state = self._load()
                before = state["generation"]
                yield state
                if state["generation"] != before:
                    if state["generation"] != before + 1 or not _valid_state(state):
                        raise AccountOwnershipUnknown("account registry update is invalid")
                    self._context.write_bytes(STATE_PATH, _canonical(state), mode=0o600)
            finally:
                _release_os_lock(handle, token)
        finally:
            handle.close()


def _require_sim(account: SimAccountIdentity) -> str:
    if not isinstance(account, SimAccountIdentity):
        raise TypeError("a SimAccountIdentity is required")
    if account.environment != SIM_ENVIRONMENT:
        raise RealBrokerageDenied("only fake SIM environments may be bound; real brokerage is denied")
    return SIM_ENVIRONMENT


def _deployment_name(deployment: str) -> str:
    try:
        return ensure_unique_resource_name(deployment, [])
    except (TypeError, RootPathError):
        raise AccountBindingError("deployment identity is invalid") from None


def _name_key(name: str) -> str:
    return hashlib.sha256(name.casefold().encode("utf-8")).hexdigest()


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _valid_state(state: object) -> bool:
    if not isinstance(state, dict) or set(state) != {"schema", "registry_id", "generation", "bindings"}:
        return False
    if state["schema"] != SCHEMA or not isinstance(state["registry_id"], str) or not re.fullmatch(r"[0-9a-f]{32}", state["registry_id"]):
        return False
    if type(state["generation"]) is not int or state["generation"] < 0:
        return False
    bindings = state["bindings"]
    if not isinstance(bindings, dict) or len(bindings) > _MAX_BINDINGS:
        return False
    active_owners: set[tuple[str, str]] = set()
    used_generations: set[int] = set()
    for key, record in bindings.items():
        if not isinstance(key, str) or not _SHA256.fullmatch(key) or not _valid_record(record, state["generation"]):
            return False
        if record["status"] == "active":
            owner = (record["owner"], record["deployment_key"])
            if owner in active_owners:
                return False
            active_owners.add(owner)
        generations = {record["bound_generation"]}
        generations.update(item["generation"] for item in record["provenance"])
        if record["status"] == "released":
            generations.add(record["released_generation"])
        if used_generations.intersection(generations):
            return False
        used_generations.update(generations)
    return True


def _valid_record(record: object, state_generation: int) -> bool:
    base = {"environment", "status", "owner", "deployment", "deployment_key", "bound_generation", "bound_at", "release_digest", "provenance", "execution_authorized"}
    if not isinstance(record, dict) or not base.issubset(record) or set(record) - base - {"released_generation"}:
        return False
    if record["environment"] != SIM_ENVIRONMENT or record["execution_authorized"] is not False:
        return False
    if record["status"] not in {"active", "released"} or not isinstance(record["owner"], str) or not _SHA256.fullmatch(record["owner"]):
        return False
    if not isinstance(record["deployment"], str) or record["deployment_key"] != _name_key(record["deployment"]):
        return False
    if type(record["bound_generation"]) is not int or not 1 <= record["bound_generation"] <= state_generation or not isinstance(record["bound_at"], str):
        return False
    if record["status"] == "active":
        if record["release_digest"] is not None or "released_generation" in record:
            return False
    elif not isinstance(record["release_digest"], str) or not _SHA256.fullmatch(record["release_digest"]) or type(record.get("released_generation")) is not int or not record["bound_generation"] < record["released_generation"] <= state_generation:
        return False
    provenance = record["provenance"]
    if not isinstance(provenance, list) or len(provenance) > _MAX_PROVENANCE:
        return False
    previous_generation = 0
    for item in provenance:
        if not isinstance(item, dict) or set(item) != {"from_owner", "from_deployment_key", "release_digest", "generation"}:
            return False
        if any(not isinstance(item[key], str) or not _SHA256.fullmatch(item[key]) for key in ("from_owner", "from_deployment_key", "release_digest")) or type(item["generation"]) is not int or not previous_generation < item["generation"] <= record["bound_generation"]:
            return False
        previous_generation = item["generation"]
    return not provenance or previous_generation == record["bound_generation"]


__all__ = [
    "AccountAlreadyBound",
    "AccountBindingError",
    "AccountOwnershipUnknown",
    "AccountRegistry",
    "CustodyAssessment",
    "CustodyVerifier",
    "DEFAULT_CUSTODY",
    "default_registry_location",
    "DeploymentAlreadyBound",
    "NotOwner",
    "RealBrokerageDenied",
    "RegistryBusy",
    "ReleaseRequired",
    "require_sim_account_ownership",
    "runner_quiescence",
    "RunnerNotQuiescent",
    "RunnerQuiescence",
    "SIM_ENVIRONMENT",
    "SIMAccountRegistry",
    "SIMOwnershipStatus",
    "SIMOwnershipUnknown",
    "SimAccountIdentity",
    "StaleRelease",
    "UnverifiableGlobalCustody",
]
