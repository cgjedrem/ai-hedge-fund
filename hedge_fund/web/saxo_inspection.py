"""Transient, actor-scoped Saxo SIM inspection orchestration."""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass
from typing import Callable

from hedge_fund.brokers.saxo import (
    LeaseBackedDemoTokenManager,
    SaxoAuthError,
    SaxoClient,
    SaxoReconcileError,
)
from hedge_fund.runtime.external_credentials import (
    ExternalCredentialError,
    RuntimeCredentialHandle,
    RuntimeCredentialLeaseStore,
)

PROVIDER_ID = "saxo-demo-token"
DESTINATION = "saxo-sim-readonly"
PURPOSE = "saxo-sim-readonly"
_CHOICE_TTL_SECONDS = 300
_MAX_TRANSIENT_CHOICES = 1000


class SaxoInspectionError(RuntimeError):
    def __init__(self, reason: str, status_code: int, message: str):
        super().__init__(message)
        self.reason = reason
        self.status_code = status_code
        self.message = message


@dataclass(frozen=True)
class _Choice:
    actor: str
    generation: int
    account_key: str
    currency: str
    label: str
    expires_at: float


class SaxoInspectionCoordinator:
    """Run only explicitly consented, bounded reads without retaining results."""

    def __init__(
        self,
        store: RuntimeCredentialLeaseStore | None,
        *,
        enabled: bool,
        network_enabled: Callable[[], bool],
        authority_check: Callable[[], None],
        clock=None,
        transport_factory: Callable[[], object] | None = None,
    ):
        self.store = store
        self.enabled = bool(enabled and store is not None)
        self.network_enabled = network_enabled
        self.authority_check = authority_check
        self.clock = clock
        self.transport_factory = transport_factory
        self._lock = threading.RLock()
        self._choices: dict[str, _Choice] = {}
        self._busy_actor: str | None = None
        self._cancel: threading.Event | None = None

    def status(self, *, operator: bool) -> dict[str, object]:
        if not operator or not self.enabled or self.store is None:
            return {
                "enabled": self.enabled,
                "state": "unavailable" if self.enabled else "disabled",
                "generation": 0,
                "expires_at": None,
                "actions": {"discover": False, "inspect": False, "revoke": False},
            }
        try:
            status = self.store.capability_status(PROVIDER_ID, destination=DESTINATION, purpose=PURPOSE)
        except ExternalCredentialError:
            return {
                "enabled": False,
                "state": "unavailable",
                "generation": 0,
                "expires_at": None,
                "actions": {"discover": False, "inspect": False, "revoke": False},
            }
        state = status["state"]
        available = state == "available" and bool(self.network_enabled())
        return {
            "enabled": True,
            "state": state,
            "generation": status["generation"],
            "expires_at": status["expires_at"],
            "actions": {
                "discover": available,
                "inspect": available,
                "revoke": state not in {"unavailable", "requires-auth"} and status["generation"] > 0,
            },
        }

    def discover(self, actor: str, *, authorize_network: bool, expected_generation: int) -> dict[str, object]:
        self._require_request(actor, authorize_network)
        handle, cancel = self._begin(actor, expected_generation)
        try:
            manager, client = self._make_client(handle, cancel)
            client.check_connection()
            candidates = client.account_candidates()
            manager.verify_publish()
            self._assert_authority(cancel)
            token = self.store.capability_value_for_dispatch(handle, destination=DESTINATION, purpose=PURPOSE)
            try:
                choices = []
                with self._lock:
                    self._drop_actor_choices(actor)
                    self._purge_expired_choices()
                    if len(self._choices) + len(candidates) > _MAX_TRANSIENT_CHOICES:
                        raise SaxoInspectionError("inspection-limit", 429, "Too many temporary account choices are active.")
                    for index, candidate in enumerate(candidates, 1):
                        label = f"SIM account {index}"
                        choice_id = uuid.uuid4().hex
                        choice = _Choice(
                            actor=actor,
                            generation=handle.generation,
                            account_key=candidate.account_key,
                            currency=candidate.currency,
                            label=label,
                            expires_at=self._monotonic() + _CHOICE_TTL_SECONDS,
                        )
                        self._choices[choice_id] = choice
                        choices.append(
                            {
                                "selection_id": choice_id,
                                "label": label,
                                "currency": candidate.currency,
                            }
                        )
                self._reject_secret_reflection(choices, token)
            finally:
                token = None
            result = {
                "environment": "SIM",
                "read_only": True,
                "generation": handle.generation,
                "selection_required": True,
                "choices": choices,
            }
            return self._publish_result(handle, cancel, result)
        except SaxoInspectionError:
            self.clear_actor(actor)
            raise
        except SaxoAuthError as exc:
            self.clear_actor(actor)
            raise self._client_error(exc) from None
        except SaxoReconcileError as exc:
            self.clear_actor(actor)
            raise self._client_error(exc) from None
        except ExternalCredentialError:
            self.clear_actor(actor)
            raise SaxoInspectionError("requires-auth", 503, "Saxo SIM inspection credential is unavailable.") from None
        except Exception:
            self.clear_actor(actor)
            raise SaxoInspectionError("sim-request-failed", 503, "Saxo SIM inspection failed safely.") from None
        finally:
            self._end(actor, handle)

    def inspect(
        self,
        actor: str,
        *,
        authorize_network: bool,
        expected_generation: int,
        selection_id: str,
    ) -> dict[str, object]:
        self._require_request(actor, authorize_network)
        if not isinstance(selection_id, str) or not selection_id:
            raise SaxoInspectionError("stale-selection", 409, "Choose an account again before inspection.")
        handle, cancel = self._begin(actor, expected_generation)
        try:
            with self._lock:
                choice = self._choices.pop(selection_id, None)
            if choice is None or choice.actor != actor or choice.generation != handle.generation or choice.expires_at <= self._monotonic():
                raise SaxoInspectionError("stale-selection", 409, "Choose an account again before inspection.")
            manager, client = self._make_client(handle, cancel)
            client.check_connection()
            candidates = client.account_candidates()
            selected = [candidate for candidate in candidates if candidate.account_key == choice.account_key and candidate.currency == choice.currency]
            if len(selected) != 1:
                raise SaxoInspectionError("stale-selection", 409, "The selected SIM account changed; discover accounts again.")
            summary = client._inspect_account(selected[0])
            manager.verify_publish()
            self._assert_authority(cancel)
            token = self.store.capability_value_for_dispatch(handle, destination=DESTINATION, purpose=PURPOSE)
            try:
                result = {
                    "environment": "SIM",
                    "read_only": True,
                    "generation": handle.generation,
                    "account": {
                        "label": choice.label,
                        "currency": summary.currency,
                        "cash_balance": summary.cash_balance,
                        "positions": [{"uic": position.uic, "amount": position.amount} for position in summary.positions],
                    },
                    "fund_connected": False,
                    "trading_enabled": False,
                }
                self._reject_secret_reflection(result, token)
            finally:
                token = None
            self.clear_actor(actor)
            return self._publish_result(handle, cancel, result)
        except SaxoInspectionError:
            self.clear_actor(actor)
            raise
        except SaxoAuthError as exc:
            self.clear_actor(actor)
            raise self._client_error(exc) from None
        except SaxoReconcileError as exc:
            self.clear_actor(actor)
            raise self._client_error(exc) from None
        except ExternalCredentialError:
            self.clear_actor(actor)
            raise SaxoInspectionError("requires-auth", 503, "Saxo SIM inspection credential is unavailable.") from None
        except Exception:
            self.clear_actor(actor)
            raise SaxoInspectionError("sim-request-failed", 503, "Saxo SIM inspection failed safely.") from None
        finally:
            self._end(actor, handle)

    def cancel(self, actor: str) -> dict[str, bool]:
        with self._lock:
            if self._busy_actor != actor or self._cancel is None:
                return {"cancelled": False}
            self._cancel.set()
            return {"cancelled": True}

    def clear_actor(self, actor: str) -> None:
        with self._lock:
            self._drop_actor_choices(actor)

    def clear_all(self) -> None:
        with self._lock:
            self._choices.clear()
            if self._cancel is not None:
                self._cancel.set()

    def _require_request(self, actor: str, authorize_network: bool) -> None:
        if not isinstance(actor, str) or not actor:
            raise SaxoInspectionError("capability-denied", 403, "A server-owned operator session is required.")
        if authorize_network is not True:
            self.clear_actor(actor)
            raise SaxoInspectionError("consent-required", 400, "Explicit network consent is required for each SIM action.")
        if not self.enabled or self.store is None:
            self.clear_actor(actor)
            raise SaxoInspectionError("capability-disabled", 503, "Saxo SIM inspection is unavailable.")
        if not self.network_enabled():
            self.clear_actor(actor)
            raise SaxoInspectionError("network-disabled", 403, "Network capability is disabled for this server.")
        try:
            self._assert_authority(None)
        except SaxoInspectionError:
            self.clear_actor(actor)
            raise

    def _begin(self, actor: str, expected_generation: int) -> tuple[RuntimeCredentialHandle, threading.Event]:
        if type(expected_generation) is not int or expected_generation < 0:
            raise SaxoInspectionError("stale-generation", 409, "Credential status changed; reload before retrying.")
        with self._lock:
            if self._busy_actor is not None:
                raise SaxoInspectionError("inspection-busy", 409, "Another SIM inspection is already running.")
            try:
                status = self.store.capability_status(PROVIDER_ID, destination=DESTINATION, purpose=PURPOSE)
                if status["state"] != "available":
                    self._drop_actor_choices(actor)
                    raise SaxoInspectionError("requires-auth", 503, "Deliver a valid Saxo SIM inspection token before continuing.")
                if status["generation"] != expected_generation:
                    self._drop_actor_choices(actor)
                    raise SaxoInspectionError("stale-generation", 409, "Credential status changed; reload before retrying.")
                for key in [key for key, choice in self._choices.items() if choice.generation != status["generation"] or choice.expires_at <= self._monotonic()]:
                    self._choices.pop(key, None)
                handle = self.store.capture_capability(PROVIDER_ID, destination=DESTINATION, purpose=PURPOSE)
                if handle.generation != expected_generation:
                    self.store.release(handle)
                    self._drop_actor_choices(actor)
                    raise SaxoInspectionError("stale-generation", 409, "Credential status changed; reload before retrying.")
            except ExternalCredentialError:
                self._drop_actor_choices(actor)
                raise SaxoInspectionError("requires-auth", 503, "Deliver a valid Saxo SIM inspection token before continuing.") from None
            cancel = threading.Event()
            self._busy_actor = actor
            self._cancel = cancel
            return handle, cancel

    def _make_client(self, handle: RuntimeCredentialHandle, cancel: threading.Event):
        def revalidate() -> None:
            if cancel.is_set():
                raise SaxoAuthError("Saxo SIM inspection was canceled")
            self._assert_authority(cancel)

        manager_client_args = {
            "lease_store": self.store,
            "handle": handle,
            "authority_check": revalidate,
            "clock": self.clock,
        }
        transport = self.transport_factory() if self.transport_factory is not None else None
        manager = LeaseBackedDemoTokenManager(**manager_client_args)
        client = SaxoClient(
            tokens=manager,
            transport=transport,
            clock=self.clock,
            base_currency="USD",
        )
        return manager, client

    def _assert_authority(self, cancel: threading.Event | None) -> None:
        if cancel is not None and cancel.is_set():
            raise SaxoInspectionError("inspection-cancelled", 409, "Saxo SIM inspection was canceled.")
        if not self.network_enabled():
            raise SaxoInspectionError("network-disabled", 403, "Network capability is disabled for this server.")
        try:
            self.authority_check()
        except Exception:
            raise SaxoInspectionError("capability-denied", 403, "Root write authority is unavailable.") from None

    def _publish_result(self, handle: RuntimeCredentialHandle, cancel: threading.Event, result: dict[str, object]) -> dict[str, object]:
        # Match _begin's coordinator -> store order. All broker I/O, projection
        # and redaction precede these locks; the store never calls into authority.
        with self._lock:
            self._assert_authority(cancel)

            def commit() -> dict[str, object]:
                # This is the publication boundary, not an HTTP send/recall gate.
                # A cancel arriving after this commit must report no active action.
                self._cancel = None
                return result

            return self.store.commit_capability_publication(handle, commit, destination=DESTINATION, purpose=PURPOSE)

    def _end(self, actor: str, handle: RuntimeCredentialHandle) -> None:
        if self.store is not None:
            try:
                self.store.release(handle)
            except ExternalCredentialError:
                pass
        with self._lock:
            if self._busy_actor == actor:
                self._busy_actor = None
                self._cancel = None

    def _drop_actor_choices(self, actor: str) -> None:
        for key in [key for key, choice in self._choices.items() if choice.actor == actor]:
            self._choices.pop(key, None)

    def _purge_expired_choices(self) -> None:
        now = self._monotonic()
        for key in [key for key, choice in self._choices.items() if choice.expires_at <= now]:
            self._choices.pop(key, None)

    def _monotonic(self) -> float:
        if self.clock is not None and callable(getattr(self.clock, "monotonic", None)):
            return self.clock.monotonic()
        import time

        return time.monotonic()

    @staticmethod
    def _reject_secret_reflection(value: object, secret: str) -> None:
        if not secret:
            raise SaxoInspectionError("requires-auth", 503, "Saxo SIM inspection credential is unavailable.")

        def visit(item: object) -> bool:
            if isinstance(item, str):
                return secret in item
            if isinstance(item, dict):
                return any(visit(key) or visit(child) for key, child in item.items())
            if isinstance(item, (list, tuple)):
                return any(visit(child) for child in item)
            return False

        if visit(value):
            raise SaxoInspectionError("invalid-broker-response", 422, "Saxo SIM returned a response that could not be safely displayed.")

    @staticmethod
    def _client_error(error: SaxoAuthError | SaxoReconcileError) -> SaxoInspectionError:
        message = str(error)
        if message == "Saxo SIM inspection timed out":
            return SaxoInspectionError("inspection-timeout", 504, "The bounded Saxo SIM inspection timed out.")
        if message in {
            "Saxo SIM rejected the inspection credential",
            "Saxo SIM inspection credential is unavailable",
        }:
            return SaxoInspectionError("requires-auth", 503, "Saxo SIM rejected the credential; deliver a valid token and retry.")
        if "limit exceeded" in message or "exceeds a " in message or "exceeds the " in message:
            return SaxoInspectionError("inspection-limit", 429, "Saxo SIM inspection exceeded a fixed resource limit.")
        if isinstance(error, SaxoReconcileError):
            return SaxoInspectionError("invalid-broker-response", 422, "Saxo SIM returned an invalid inspection response.")
        return SaxoInspectionError("sim-request-failed", 503, "Saxo SIM request failed; verify the token and retry.")
