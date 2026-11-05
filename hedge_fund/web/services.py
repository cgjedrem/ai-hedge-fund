"""Thin adapters over validated fund, ledger, research and key services."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import threading
import unicodedata
from contextlib import contextmanager, ExitStack
from datetime import date, datetime, timedelta
from decimal import Decimal
from ipaddress import ip_address
from pathlib import Path
from typing import Callable, Iterator
from urllib.parse import urlsplit
from uuid import uuid4

import yaml

from hedge_fund.backtesting.fund import backtest_fund, FundBacktestResult
from hedge_fund.backtesting.research import save_result
from hedge_fund.data import (
    CachedDataClient,
    data_provider,
    make_data_client,
    PriceSnapshot,
)
from hedge_fund.data.registry import DATA_PROVIDER_ENV_VARS
from hedge_fund.data.sessions import NEW_YORK
from hedge_fund.fund import (
    Fund,
    FundSpec,
    load_spec,
    load_strategy,
    model_call_bounds,
    normalize_universe,
    save_spec,
    StrategySpec,
)
from hedge_fund.fund.storage import StorageAdmissionError
from hedge_fund.llm import (
    DEFAULT_MODEL,
    env_var_for,
    make_llm,
    PromptCache,
    PROVIDER_ENV_VARS,
)
from hedge_fund.llm.client import validate_llm_transport
from hedge_fund.llm.registry import is_supported, KEYLESS_PROVIDERS, load_api_models
from hedge_fund.paper.deployed import (
    deploy,
    DeployedFund,
    list_deployed,
    load_deployed,
    validate_fund_name,
)
from hedge_fund.paper.ledger import (
    ApprovalExpired,
    ApprovalHalted,
    ApprovalStale,
    HaltAuditUnavailable,
    Ledger,
    LedgerError,
    PaperReconciliationRequired,
    PaperRequestConflict,
)
from hedge_fund.paper.tick import following_session, next_session, tick
from hedge_fund.pipeline.session import (
    code_version,
    FundState,
    mandate_hash,
    SessionRecord,
)
from hedge_fund.runtime.admission import (
    AdmissionCoordinator,
    AdmissionError,
    OwnershipUnknown,
    paper_approval_transition,
    RootOwnerLease,
    WriterConflict,
)
from hedge_fund.runtime.capture import freeze_capture, FrozenCapture
from hedge_fund.runtime.configuration import (
    ConfigurationError,
    describe_configuration,
    environment_settings,
    load_settings,
    resolve_settings,
    RuntimeSettings,
    save_settings,
    SettingsConflict,
)
from hedge_fund.runtime.costs import (
    cost_model_description,
    cost_model_identity,
    COST_MODEL_VERSION,
    has_verified_cost_model,
    minimum_attempt_cost,
)
from hedge_fund.runtime.credentials import (
    CredentialStore,
    CredentialStoreError,
    CredentialVersionConflict,
)
from hedge_fund.runtime.dispatch import make_one_shot_dispatch, ProviderDispatch
from hedge_fund.runtime.handover import (
    enrollment_status,
    HandoverError,
    has_write_authority,
    LedgerHeadPublicationError,
    LedgerInventoryCorrupt,
    require_enrollment,
    SINGLE_WRITER_RESPONSIBILITY_WARNING,
    TRUSTED_SINGLE_WRITER_AUTHORITY,
    verify_root_inventory,
    write_authority,
)
from hedge_fund.runtime.lifecycle import (
    ArchiveConflict,
    ArchiveError,
    ArchiveNotFound,
    LifecycleArchiveStore,
)
from hedge_fund.runtime.operations import (
    ConfirmationExpired,
    ConfirmationRejected,
    OperationBusy,
    OperationCapacityExceeded,
    OperationConflict,
    OperationError,
    OperationRecord,
    OperationStartUncertain,
    OperationStatus,
    OperationStore,
    StalePreview,
)
from hedge_fund.runtime.owned_runner import (
    OwnedRunnerError,
    OwnedRunnerManager,
    runner_key,
    RUNNER_ROOT,
)
from hedge_fund.runtime.policy import (
    AuthorizationDenied,
    BudgetDenied,
    classify_provider,
    KEN_FRENCH_BREAKPOINTS_TARGET,
    ProviderClass,
    ProviderTarget,
)
from hedge_fund.runtime.reconciliation import build_reconciliation_snapshot
from hedge_fund.runtime.root import RootContext, RootPathError
from hedge_fund.scorecard import score
from hedge_fund.web.jobs import JobCancelled, JobConflict, OperationJobRegistry
from hedge_fund.web.schemas import (
    ApprovalRequest,
    BacktestRequest,
    CredentialRequest,
    DeployRequest,
    error_code_for,
    LifecycleAcceptRequest,
    LifecyclePreviewRequest,
    ModelRequest,
    OperationAcceptRequest,
    OperationCancelRequest,
    OperationPreviewRequest,
    PaperResumeRequest,
    PaperTickAcceptRequest,
    PaperTickPreviewRequest,
    RETRY_POLICIES,
    RunnerPreviewRequest,
    RunnerStartAcceptRequest,
    RuntimeSettingsRequest,
    valid_retry_after,
    ValuationRefreshRequest,
)
from hedge_fund.web.valuation import estimate_valuation, MAX_VALUATION_POSITIONS

PROTECTED_NAMES = ("watchtower", "watchtower-weekly", "umbrella")
# Worker pools: per-process slots (OperationJobRegistry.max_active) and the same durable
# root-wide bound on unfinished operations of the pool's actions (OperationStore.accept_request).
_BACKTEST_POOL_ACTIONS = frozenset({"backtest"})
_PAPER_POOL_ACTIONS = frozenset({"paper-tick", "paper-runner-start"})
_BACKTEST_POOL_CAPACITY = 1
_PAPER_POOL_CAPACITY = 2
# Advisory only: the bound holds until a running operation finishes, which has no fixed duration.
OPERATION_CAPACITY_RETRY_AFTER_SECONDS = 30
_REPORT_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,180}\.json$")
_SESSION_CURSOR = re.compile(r"\d{4}-\d{2}-\d{2}(?:T\d{2}:\d{2}:\d{2})?$")
_SECRET_FIELD = re.compile(r"(?:api.?key|secret|token|password|credential|authorization)", re.IGNORECASE)


class ServiceError(RuntimeError):
    def __init__(
        self,
        status_code: int,
        detail: str,
        *,
        code: str | None = None,
        subject_id: str | None = None,
        request_id: str | None = None,
        current_head: str | None = None,
        retry_policy: str | None = None,
        retry_after_seconds: int | None = None,
    ) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail
        self.code = error_code_for(status_code, code)
        self.subject_id = subject_id
        self.request_id = request_id
        self.current_head = current_head
        if retry_policy is not None and retry_policy not in RETRY_POLICIES:
            raise ValueError(f"unknown retry policy: {retry_policy}")
        self.retry_policy = retry_policy
        if retry_after_seconds is not None and not valid_retry_after(status_code, self.code, retry_after_seconds):
            raise ValueError("retry-after is only a bounded hint on 429/503 responses")
        self.retry_after_seconds = retry_after_seconds

    def attach(self, *, subject_id: str | None = None, request_id: str | None = None) -> "ServiceError":
        """Add request identity known to the caller without overwriting a site's own identity."""
        if self.subject_id is None:
            self.subject_id = subject_id
        if self.request_id is None:
            self.request_id = request_id
        return self


def _capacity_denied(subject_id: str, request_id: str) -> ServiceError:
    # Raised only before durable acceptance: the preview stays issued and nothing was started.
    return ServiceError(
        429,
        "Operation capacity is full; this request was not accepted and nothing was started. Wait for the running operation to finish, then submit again.",
        code="capacity-denied",
        retry_policy="retry-later",
        retry_after_seconds=OPERATION_CAPACITY_RETRY_AFTER_SECONDS,
        subject_id=subject_id,
        request_id=request_id,
    )


class _DispatchGuardedInjectedDataClient:
    """Reserve fake provider calls beneath operation authority."""

    _METHODS = frozenset(
        {
            "get_company_facts",
            "get_earnings",
            "get_earnings_history",
            "get_financial_metrics",
            "get_insider_trades",
            "get_market_cap",
            "get_news",
            "get_prices",
            "get_snapshot",
        }
    )

    def __init__(
        self,
        client: object,
        dispatch: ProviderDispatch,
        target: ProviderTarget,
        url: str,
    ) -> None:
        if not isinstance(dispatch, ProviderDispatch) or not isinstance(target, ProviderTarget):
            raise AuthorizationDenied("provider operation authorization is required")
        dispatch.validate_target(target)
        self._client = client
        self._dispatch = dispatch
        self._target = target
        self._url = url

    def __getattr__(self, name: str):
        value = getattr(self._client, name)
        if name not in self._METHODS or not callable(value):
            return value

        def guarded_call(*args, **kwargs):
            self._dispatch.authorize_transport(
                self._target,
                url=self._url,
                method="GET",
            )
            return value(*args, **kwargs)

        return guarded_call


class DeskService:
    def __init__(
        self,
        root: str | Path,
        *,
        allow_writes: bool = False,
        network_enabled: bool = False,
        demo: bool = False,
        data_client_factory: Callable[[], object] | None = None,
        fund_factory: Callable[[FundSpec], Fund] | None = None,
        root_context: RootContext | None = None,
        container_observer: bool = False,
    ) -> None:
        if type(allow_writes) is not bool or type(network_enabled) is not bool:
            raise TypeError("write and network capabilities must be booleans")
        if type(demo) is not bool or type(container_observer) is not bool:
            raise TypeError("service mode flags must be booleans")
        if container_observer:
            raise ValueError("container observer projection is unavailable")
        if root_context is None:
            root_context = RootContext.open(root)
            self._owns_root_context = True
        else:
            if not isinstance(root_context, RootContext):
                raise RootPathError("an opened root context is required")
            if Path(root) != root_context.path:
                raise RootPathError("root path does not match root context")
            root_context.revalidate()
            self._owns_root_context = False
        self.root_context = root_context
        self.root = root_context.path
        self.container_observer = False
        status = enrollment_status(root_context, verify_inventory=True)
        self.enrollment_state = status["state"]
        self._owner_lease: RootOwnerLease | None = None
        self._operation_service_lease = None
        self._admission = AdmissionCoordinator(root_context)
        self.allow_writes = False
        self.emergency_halt_available = False
        self.write_unavailable_reason: str | None = status["reason"]
        authority = write_authority(root_context) if status["state"] in {"enrolled", "drift"} else None
        self.write_authority = authority["authority"] if authority is not None else "unavailable"
        if authority is not None and not has_write_authority(authority):
            self.write_unavailable_reason = authority["reason"] if status["state"] == "enrolled" else status["reason"]
        elif not allow_writes and status["state"] == "enrolled":
            self.write_unavailable_reason = "write-capability-disabled"
        if allow_writes and status["state"] in {"enrolled", "drift"} and has_write_authority(authority):
            owner = None
            try:
                owner = RootOwnerLease.acquire(root_context)
                admission = AdmissionCoordinator(root_context, owner_lease=owner)
                self._owner_lease = owner
                self._admission = admission
                self.allow_writes = status["state"] == "enrolled"
                self.emergency_halt_available = status["state"] == "drift"
            except (AdmissionError, OSError, RootPathError, ValueError, RuntimeError):
                if owner is not None:
                    owner.close()
                self.write_unavailable_reason = "private-storage-unverified" if not root_context.verify_private_storage() else "root-owner-unavailable"
        self.network_enabled = bool(network_enabled and self.allow_writes and not container_observer)
        self.demo = bool(demo)
        self._data_client_factory = data_client_factory
        self._fund_factory = fund_factory if fund_factory is not None else self._default_fund_factory
        self._custom_fund_factory = fund_factory is not None
        self._locks: dict[str, threading.RLock] = {}
        self._locks_guard = threading.Lock()
        self._settings_lock = threading.RLock()
        self._valuation_lock = threading.Lock()
        self._valuation_generations: dict[str, int] = {}
        self._valuation_estimates: dict[str, dict[str, object]] = {}
        self._settings_error: str | None = None
        self._runtime_settings = RuntimeSettings()
        self._environment_settings: dict[str, object] = {}
        self._credential_store: CredentialStore | None = None
        self._operation_store: OperationStore | None = None
        self._operation_jobs: OperationJobRegistry | None = None
        self._paper_operation_jobs: OperationJobRegistry | None = None
        self._captures: dict[str, FrozenCapture] = {}
        self._preview_captures: dict[str, str] = {}
        self._preview_expiries: dict[str, datetime] = {}
        self._lifecycle_previews: dict[str, dict[str, object]] = {}
        try:
            self._environment_settings = environment_settings()
            self._runtime_settings = resolve_settings(
                root_context,
                admission=self._admission,
                environment=self._environment_settings,
            )
        except ConfigurationError:
            self._settings_error = "private-settings-unavailable"
        self._startup_settings_version = self._runtime_settings.version
        if root_context.verify_private_storage():
            try:
                self._credential_store = CredentialStore(root_context, self._admission)
            except CredentialStoreError:
                self._settings_error = "private-settings-unavailable"
            try:
                self._operation_store = OperationStore(
                    root_context,
                    admission=self._admission,
                )
                if self.allow_writes:
                    operation_jobs = OperationJobRegistry(
                        self._operation_store,
                        max_active=_BACKTEST_POOL_CAPACITY,
                    )
                    paper_operation_jobs = OperationJobRegistry(
                        self._operation_store,
                        max_active=_PAPER_POOL_CAPACITY,
                    )
                    service_lease = self._admission.operation_service_lease(timeout=0)
                    try:
                        operation_jobs.recover_unfinished()
                        service_lease.__enter__()
                    except Exception:
                        operation_jobs.close()
                        paper_operation_jobs.close()
                        raise
                    self._operation_service_lease = service_lease
                    self._operation_jobs = operation_jobs
                    self._paper_operation_jobs = paper_operation_jobs
            except (AdmissionError, JobConflict, OperationError, OSError, ValueError) as exc:
                if self.allow_writes:
                    self.allow_writes = False
                    self.network_enabled = False
                    self.write_unavailable_reason = "operation-service-active" if isinstance(exc, WriterConflict) else "operation-recovery-unavailable"
                    if isinstance(exc, WriterConflict):
                        self._admission = AdmissionCoordinator(root_context, owner_lease=self._owner_lease)
                    else:
                        if self._owner_lease is not None:
                            self._owner_lease.close()
                            self._owner_lease = None
                        self._admission = AdmissionCoordinator(root_context)
                        self._operation_store = None
        self._runner_manager = OwnedRunnerManager(root_context, self._admission)

    def close(self) -> None:
        try:
            if self._paper_operation_jobs is not None:
                self._paper_operation_jobs.close()
        finally:
            try:
                if self._operation_jobs is not None:
                    self._operation_jobs.close()
            finally:
                try:
                    if self._operation_service_lease is not None:
                        self._operation_service_lease.__exit__(None, None, None)
                        self._operation_service_lease = None
                finally:
                    try:
                        if self._owner_lease is not None:
                            self._owner_lease.close()
                            self._owner_lease = None
                    finally:
                        if self._owns_root_context:
                            self.root_context.close()

    def capabilities(self, mutation_token: str | None) -> dict:
        if self.allow_writes or self.emergency_halt_available:
            self._refresh_write_authority()
        return {
            "mode": "demo" if self.demo else "live",
            "read_only": not self.allow_writes,
            "writes": self.allow_writes,
            "network": self.network_enabled,
            "local_operator_only": True,
            "csrf_authenticates_users": False,
            "container_observer": self.container_observer,
            "enrollment_state": self.enrollment_state,
            "write_authority": self.write_authority,
            "write_unavailable_reason": self.write_unavailable_reason,
            "operator_trust_warning": SINGLE_WRITER_RESPONSIBILITY_WARNING if self.write_authority == TRUSTED_SINGLE_WRITER_AUTHORITY else None,
            "protected_names": list(PROTECTED_NAMES),
            "mutation_token": mutation_token if self.allow_writes or self.emergency_halt_available else None,
            "deferred_actions": {
                "runner": ("Finite local-paper runner start and stop require an explicit reviewed operation." if self.allow_writes else "Runner controls are unavailable because root writes are disabled."),
                "manual_run": ("One-session local-paper ticks require a reviewed head and due-set confirmation." if self.allow_writes and self.network_enabled else "Manual ticks are unavailable because writes or network capability are disabled."),
                **({} if self.allow_writes and self._operation_store is not None else {"delete": "Scoped archival is unavailable because root writes or durable operation storage are disabled."}),
                "redo": "Ledger redo is not available from the web UI.",
                "live_value": ("Explicit free-Yahoo refresh is available; quote print freshness remains unverified." if self.network_enabled else "Valuation refresh is disabled because network capability is off."),
            },
        }

    def catalog(self) -> dict:
        models = [{"label": label, "id": model_id, "provider": provider} for label, model_id, provider in load_api_models() if is_supported(provider)]
        strategies = []
        from hedge_fund.signals import (
            ALPHA_MODEL_REGISTRY,
            get_investment_approach,
            LLMAgent,
        )

        for strategy in self._strategy_library().values():
            kind = "discretionary" if all(issubclass(ALPHA_MODEL_REGISTRY[model.name], LLMAgent) for model in strategy.models) else "systematic"
            strategies.append(
                {
                    "name": strategy.name,
                    "title": strategy.title,
                    "models": [model.model_dump(mode="json") for model in strategy.models],
                    "kind": kind,
                    "mode": strategy.blend.mode,
                    "blend": strategy.blend.model_dump(mode="json"),
                }
            )
        analysts = [{"name": name, "approach": get_investment_approach(name)} for name in sorted(ALPHA_MODEL_REGISTRY)]
        return {"models": models, "strategies": strategies, "analysts": analysts, "default_model": DEFAULT_MODEL}

    def home(self) -> dict:
        mandates = self.list_mandates()
        papers = self.list_paper()
        reports = self.list_research()
        paper_items = papers["items"]
        return {
            "mode": "demo" if self.demo else "live",
            "mandate_count": len(mandates["items"]),
            "paper_count": len(paper_items),
            "research_count": reports["total"],
            "recorded_nav_total": sum(item["nav"] for item in paper_items if isinstance(item.get("nav"), (int, float))),
            "paper_funds": paper_items[:6],
            "errors": mandates["errors"] + papers["errors"] + reports["errors"],
        }

    def list_mandates(self) -> dict:
        directory = self._safe_child("mandates")
        if not directory.exists():
            return {"items": [], "errors": []}
        if not directory.is_dir():
            raise ServiceError(409, "Mandate storage is not a directory.")
        items = []
        errors = []
        for path in sorted(directory.iterdir(), key=lambda entry: entry.name.casefold()):
            if path.suffix.lower() not in {".yaml", ".yml"}:
                continue
            try:
                safe_path = self._safe_child("mandates", path.name)
                spec = load_spec(safe_path)
                _reject_secret_fields(spec.model_dump(mode="python"))
                items.append(self._mandate_summary(spec))
            except ServiceError as exc:
                errors.append({"name": path.stem, "error": exc.detail})
            except (OSError, ValueError, StorageAdmissionError) as exc:
                errors.append({"name": path.stem, "error": f"Invalid mandate ({type(exc).__name__})."})
        return {"items": items, "errors": errors}

    def get_mandate(self, name: str) -> dict:
        normalized = self._validated_name(name)
        spec = self._load_mandate_by_name(normalized)
        _reject_secret_fields(spec.model_dump(mode="python"))
        return self._mandate_summary(spec, include_spec=True)

    def create_mandate(self, payload: dict) -> dict:
        self._require_writes()
        spec = self._validated_mandate(payload)
        name = self._validated_name(spec.name)
        self._guard_protected(name)
        with self._mandate_writer():
            with self._fund_lock(name):
                directory = self._ensure_dir("mandates")
                self._assert_mandate_name_available(name, directory)
                try:
                    save_spec(spec, directory, admission=self._admission)
                except FileExistsError:
                    raise ServiceError(409, "A mandate with this name already exists.") from None
                except (OSError, ValueError, StorageAdmissionError) as exc:
                    raise ServiceError(400, f"Mandate could not be saved ({type(exc).__name__}).") from None
        return self._mandate_summary(spec, include_spec=True)

    def update_mandate(self, name: str, payload: dict, *, expected_hash: str) -> dict:
        self._require_writes()
        normalized = self._validated_name(name)
        self._guard_protected(normalized)
        if not isinstance(expected_hash, str) or re.fullmatch(r"[0-9a-f]{64}", expected_hash) is None:
            raise ServiceError(400, "Mandate revision is invalid.")
        spec = self._validated_mandate(payload)
        target = self._validated_name(spec.name)
        self._guard_protected(target)
        with self._mandate_writer():
            with self._fund_lock(normalized):
                current, path = self._load_mandate_entry(normalized)
                if mandate_hash(current) != expected_hash:
                    raise ServiceError(409, "Mandate changed; reload before editing.", code="stale-preview", subject_id=normalized, current_head=mandate_hash(current))
                relative = path.relative_to(self.root).as_posix()
                if _windows_name_key(target) != _windows_name_key(normalized):
                    directory = self._safe_child("mandates")
                    self._assert_mandate_name_available(
                        target,
                        directory,
                        exclude_path=path,
                    )
                    target_relative = f"mandates/{target}.yaml"
                    if relative.casefold() != target_relative.casefold():
                        self._recheck_mandate_authority()
                        try:
                            self.root_context.rename_file(relative, target_relative)
                        except FileExistsError:
                            raise ServiceError(
                                409,
                                "A mandate with this name already exists.",
                            ) from None
                        except (OSError, RootPathError, ValueError):
                            raise ServiceError(
                                409,
                                "Mandate could not be renamed safely.",
                            ) from None
                    relative = target_relative
                serialized = yaml.safe_dump(spec.model_dump(), sort_keys=False).encode("utf-8")
                self._recheck_mandate_authority(renamed=relative != path.relative_to(self.root).as_posix())
                try:
                    self.root_context.write_bytes(relative, serialized)
                except (OSError, RootPathError, ValueError):
                    raise ServiceError(409, "Mandate could not be updated safely.") from None
        return self._mandate_summary(spec, include_spec=True)

    def clone_mandate(self, name: str, payload: dict, *, expected_hash: str) -> dict:
        self._require_writes()
        source = self._validated_name(name)
        self._guard_protected(source)
        if not isinstance(expected_hash, str) or re.fullmatch(r"[0-9a-f]{64}", expected_hash) is None:
            raise ServiceError(400, "Mandate revision is invalid.")
        spec = self._validated_mandate(payload)
        target = self._validated_name(spec.name)
        self._guard_protected(target)
        if _windows_name_key(target) == _windows_name_key(source):
            raise ServiceError(400, "A clone must use a distinct mandate name.")
        with self._mandate_writer():
            with self._fund_lock(source):
                current, _source_path = self._load_mandate_entry(source)
                if mandate_hash(current) != expected_hash:
                    raise ServiceError(409, "Mandate changed; reload before cloning.", code="stale-preview", subject_id=source, current_head=mandate_hash(current))
                directory = self._ensure_dir("mandates")
                self._assert_mandate_name_available(target, directory)
                try:
                    save_spec(spec, directory, admission=self._admission)
                except FileExistsError:
                    raise ServiceError(409, "A mandate with this name already exists.") from None
                except StorageAdmissionError:
                    raise ServiceError(409, "Mandate could not be saved safely.") from None
                except (OSError, ValueError) as exc:
                    raise ServiceError(400, f"Mandate could not be saved ({type(exc).__name__}).") from None
        return self._mandate_summary(spec, include_spec=True)

    def deploy_mandate(self, name: str, request: DeployRequest) -> dict:
        self._require_writes()
        normalized = self._validated_name(name)
        self._guard_protected(normalized)
        try:
            universe = normalize_universe(request.universe)
        except ValueError:
            raise ServiceError(400, "Deployment universe is invalid.") from None
        with self._fund_lock(normalized):
            with self._paper_deployment_lane(normalized):
                self._verify_root_inventory()
                spec = self._load_mandate_by_name(normalized)
                _reject_secret_fields(spec.model_dump(mode="python"))
                if spec.broker != "paper":
                    raise ServiceError(403, "Web deployment is restricted to local-paper mandates.", code="broker-not-web-supported")
                paper_root = self._ensure_dir("paper")
                self._assert_unique(paper_root, normalized)
                try:
                    directory = deploy(normalized, spec, universe, root=paper_root)
                except FileExistsError:
                    raise ServiceError(409, "A paper fund with this name already exists.") from None
                except LedgerHeadPublicationError:
                    raise ServiceError(423, "Deployment was written; root head inventory requires offline review.", code="reconciliation-required") from None
                except HandoverError:
                    raise ServiceError(423, "Offline paper ledger inventory changed; writes are denied.", code="reconciliation-required") from None
                except ValueError as exc:
                    raise ServiceError(400, f"Deployment validation failed ({type(exc).__name__}).") from None
                except OSError as exc:
                    raise ServiceError(409, f"Deployment could not be written ({type(exc).__name__}).") from None
        return {"name": normalized, "universe": universe, "path": directory.name, "status": "deployed"}

    def list_paper(self) -> dict:
        root = self._safe_child("paper")
        if not root.exists():
            return {"items": [], "errors": []}
        if not root.is_dir():
            raise ServiceError(409, "Paper storage is not a directory.")
        items = []
        errors = []
        try:
            directories = list_deployed(root)
        except OSError as exc:
            raise ServiceError(409, f"Paper storage could not be read ({type(exc).__name__}).") from None
        for directory in directories:
            name = directory.name
            try:
                safe_dir = self._safe_child("paper", name)
                deployed = load_deployed(safe_dir)
                snapshot = self._paper_snapshot(deployed, safe_dir)
                items.append(
                    {
                        "name": deployed.name,
                        "universe": deployed.universe,
                        "cadence": deployed.spec.cadence_label,
                        "broker": deployed.broker,
                        "nav": snapshot.get("nav"),
                        "cash": snapshot.get("cash"),
                        "last_session": snapshot.get("last_session"),
                        "ledger_ok": snapshot["ledger"]["ok"],
                        "halted": snapshot.get("halted"),
                        "halt_state": snapshot["halt_state"],
                        "runner": self._runner_state(deployed.name),
                    }
                )
                if not snapshot["ledger"]["ok"]:
                    errors.append({"name": name, "error": snapshot["ledger"]["error"]})
            except ServiceError as exc:
                errors.append({"name": name, "error": exc.detail})
            except (OSError, ValueError) as exc:
                errors.append({"name": name, "error": f"Invalid paper fund ({type(exc).__name__})."})
        return {"items": items, "errors": errors}

    def paper_detail(self, name: str) -> dict:
        normalized = self._validated_name(name)
        directory = self._safe_child("paper", normalized)
        if not directory.is_dir():
            raise ServiceError(404, "Paper fund not found.")
        try:
            deployed = load_deployed(directory)
        except ValueError as exc:
            raise ServiceError(422, f"Paper fund is invalid ({type(exc).__name__}).", code="readiness-denied") from None
        return self._paper_snapshot(deployed, directory, include_records=True)

    def paper_reconciliation(self, name: str) -> dict:
        normalized = self._validated_name(name)
        directory, deployed, ledger, state, latest = self._paper_state(
            normalized,
            local_paper_only=True,
        )
        self._safe_child("paper", normalized, "broker.json")
        try:
            snapshot = build_reconciliation_snapshot(directory, deployed, ledger, state, latest)
            halted = ledger.halted()
        except (LedgerError, OSError, ValueError):
            raise ServiceError(423, "Paper state is invalid (LedgerError).", code="replay-corrupt") from None
        preview = snapshot.preview
        return {
            "name": normalized,
            "halted": halted,
            "resume_allowed": halted is not None and (not preview.required or preview.recoverable),
            "preview": preview.model_dump(mode="json"),
        }

    def paper_sessions(
        self,
        name: str,
        *,
        limit: int = 50,
        cursor: str | None = None,
        search: str | None = None,
    ) -> dict:
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ServiceError(400, "Session page limit must be between 1 and 100.")
        if cursor is not None:
            if not isinstance(cursor, str) or not _SESSION_CURSOR.fullmatch(cursor):
                raise ServiceError(400, "Session cursor is invalid.")
            try:
                if "T" in cursor:
                    datetime.strptime(cursor, "%Y-%m-%dT%H:%M:%S")
                else:
                    date.fromisoformat(cursor)
            except ValueError:
                raise ServiceError(400, "Session cursor is invalid.") from None
        if search is not None and (not isinstance(search, str) or len(search) > 128 or any(ord(character) < 32 or ord(character) == 127 for character in search)):
            raise ServiceError(400, "Session search is invalid.")

        normalized = self._validated_name(name)
        directory = self._safe_child("paper", normalized)
        if not directory.is_dir():
            raise ServiceError(404, "Paper fund not found.")
        try:
            deployed = load_deployed(directory)
        except ValueError as exc:
            raise ServiceError(422, f"Paper fund is invalid ({type(exc).__name__}).", code="readiness-denied") from None

        records: list[SessionRecord] = []
        try:
            Ledger(directory).replay(
                deployed.spec.capital,
                full=True,
                on_verified=records.append,
            )
        except (LedgerError, OSError, ValueError) as exc:
            error = f"Ledger verification failed ({type(exc).__name__})."
            return {
                "items": [],
                "errors": [{"id": "ledger", "error": error}],
                "next_cursor": None,
                "limit": limit,
                "total": 0,
                "search": search or "",
                "ledger": {"ok": False, "error": error},
            }

        query = search.casefold() if search else ""
        entries = [record for record in sorted(records, key=lambda record: record.session, reverse=True) if not query or query in record.session.casefold() or query in record.hash.casefold()]
        total = len(entries)
        if cursor is not None:
            entries = [record for record in entries if record.session < cursor]
        page = entries[:limit]
        return {
            "items": [self._session_summary(record) for record in reversed(page)],
            "errors": [],
            "next_cursor": page[-1].session if len(entries) > limit else None,
            "limit": limit,
            "total": total,
            "search": search or "",
            "ledger": {"ok": True, "error": None},
        }

    def create_manual_tick_preview(
        self,
        name: str,
        request: PaperTickPreviewRequest,
        *,
        operator_session: str | None,
    ) -> dict:
        if not isinstance(request, PaperTickPreviewRequest):
            raise ServiceError(400, "Paper tick preview is invalid.")

        def payload(head, due, _spec, _calls, _universe_size):
            if not due:
                return {"kind": "manual-no-work", "expected_head": head}
            return {
                "kind": "manual-tick",
                "session": due[0],
                "expected_head": head,
            }

        preview = self._create_local_paper_preview(
            name,
            expected_head=request.expected_head,
            action="paper-tick",
            operator_session=operator_session,
            require_due=False,
            payload_builder=payload,
        )
        preview["outcome"] = "nothing-due" if not preview["due_set"] else "ready"
        return preview

    def create_runner_preview(
        self,
        name: str,
        request: RunnerPreviewRequest,
        *,
        operator_session: str | None,
    ) -> dict:
        if not isinstance(request, RunnerPreviewRequest):
            raise ServiceError(400, "Runner preview is invalid.")

        def payload(head, due, spec, model_calls, universe_size):
            max_calls, max_resources = _runner_limits(
                spec,
                universe_size=universe_size,
                max_sessions=request.max_sessions,
                max_runtime_minutes=request.max_runtime_minutes,
            )
            return {
                "kind": "runner-start",
                "expected_head": head,
                "initial_due_set": list(due),
                "max_sessions": request.max_sessions,
                "max_runtime_minutes": request.max_runtime_minutes,
                "max_calls": max_calls,
                "max_resources": max_resources,
                "maximum_model_calls_per_session": model_calls,
            }

        return self._create_local_paper_preview(
            name,
            expected_head=request.expected_head,
            action="paper-runner-start",
            operator_session=operator_session,
            require_due=False,
            payload_builder=payload,
        )

    def runner_status(self, name: str) -> dict:
        normalized = self._validated_name(name)
        return self._runner_state(normalized)

    def stop_runner(self, name: str) -> dict:
        self._require_writes()
        normalized = self._validated_name(name)
        self._guard_protected(normalized)
        with self._fund_lock(normalized):
            with self._paper_control_lane(normalized):
                self._paper_control_state(normalized)
                try:
                    return self._runner_manager.request_stop(normalized)
                except OwnedRunnerError:
                    raise ServiceError(409, "Owned runner identity is unavailable; no process was signalled.", code="ownership-unknown") from None

    def _create_local_paper_preview(
        self,
        name: str,
        *,
        expected_head: str | None,
        action: str,
        operator_session: str | None,
        require_due: bool,
        payload_builder: Callable[
            [str | None, tuple[str, ...], FundSpec, int, int],
            dict[str, object],
        ],
    ) -> dict:
        self._require_writes()
        if not operator_session:
            raise ServiceError(403, "A server-owned operator session is required.")
        if not self.network_enabled:
            raise ServiceError(403, "Network capability is disabled for this server.")
        if self._operation_store is None:
            raise ServiceError(409, "Durable operation storage is unavailable.")
        normalized = self._validated_name(name)
        self._guard_protected(normalized)
        with self._fund_lock(normalized):
            with self._paper_manual_lane(normalized):
                self._verify_root_inventory()
                directory, deployed, ledger, state, latest = self._paper_state(
                    normalized,
                    local_paper_only=True,
                )
                if deployed.broker != "paper":
                    raise ServiceError(403, "Paper operations require a local-paper deployment.", code="broker-not-web-supported")
                current_head = latest.hash if latest is not None else None
                if expected_head != current_head:
                    raise ServiceError(409, "Paper ledger changed; reload before previewing.", code="stale-preview", subject_id=normalized, current_head=current_head)
                if state.halted is not None:
                    raise ServiceError(423, "Halted funds cannot accept a paper operation.", code="halted", subject_id=normalized, current_head=current_head)
                self._require_paper_work_ready(deployed, ledger, state)
                with self._settings_lock:
                    self._ensure_settings_available()
                    settings = self._runtime_settings
                    self._require_local_paper_policy(settings)
                    model_calls = _estimate_paper_model_calls(
                        deployed.spec,
                        len(deployed.universe),
                    )
                    if model_calls > 1000:
                        raise ServiceError(422, "Estimated local model calls exceed the 1000-call bound.", code="readiness-denied")
                    now = _utcnow()
                    try:
                        capture = freeze_capture(
                            root=self.root_context,
                            subject_id=normalized,
                            mandate_digest=mandate_hash(deployed.spec),
                            universe=tuple(deployed.universe),
                            broker=deployed.broker,
                            settings=settings,
                            credential_versions={},
                            code_version=code_version(),
                            mandate_snapshot=deployed.spec.model_dump(mode="json"),
                        )
                        preview_dispatch = self._authorize_manual_capture(
                            capture,
                            now=now,
                            model_calls=model_calls,
                        )
                        due = self._next_paper_session(
                            deployed,
                            state.last_session,
                            provider=capture.data_provider,
                            now=now,
                            dispatch=preview_dispatch,
                        )
                        due_set = (due,) if due is not None else ()
                        if require_due and not due_set:
                            raise ServiceError(409, "No paper session is currently due.")
                        payload = payload_builder(
                            current_head,
                            due_set,
                            deployed.spec,
                            model_calls,
                            len(deployed.universe),
                        )
                        preview = self._operation_store.create_preview(
                            action=action,
                            subject_id=normalized,
                            expected_head=current_head,
                            due_set=due_set,
                            capture=capture,
                            operator_session=operator_session,
                            payload=payload,
                            now=now,
                            expires_at=now + timedelta(minutes=10),
                        )
                    except ServiceError:
                        raise
                    except (AdmissionError, HandoverError, OperationError, OSError, ValueError):
                        raise ServiceError(409, "Paper operation preview could not be verified or persisted.") from None
                    self._cache_preview_capture(
                        preview.preview_id,
                        capture,
                        preview.expires_at,
                    )
                    return {
                        **preview.public_view(),
                        "confirmation_token": preview.confirmation_token,
                        "reviewed_head": current_head,
                        "due_set": list(due_set),
                        "capture": capture.public_view(
                            current_settings_version=settings.version,
                        ),
                        "estimate": {
                            "maximum_model_calls_per_session": model_calls,
                            "maximum_calls": payload.get("max_calls", 3),
                            "maximum_resources": payload.get(
                                "max_resources",
                                max(1, model_calls),
                            ),
                            "maximum_cost_usd": 0.0,
                            "market_data_provider": capture.data_provider,
                        },
                        "warnings": ["Only free market data and the captured local Ollama model are authorized."],
                    }

    def accept_manual_tick(
        self,
        name: str,
        request: PaperTickAcceptRequest,
        *,
        operator_session: str | None,
    ) -> dict:
        if not isinstance(request, PaperTickAcceptRequest):
            raise ServiceError(400, "Paper tick acceptance is invalid.")
        if len(request.due_set) > 1:
            raise ServiceError(400, "Manual tick accepts at most one reviewed session.")
        payload = {"kind": "manual-no-work", "expected_head": request.expected_head}
        if request.due_set:
            payload = {
                "kind": "manual-tick",
                "session": request.due_set[0],
                "expected_head": request.expected_head,
            }
        return self._accept_local_paper_operation(
            name,
            request,
            action="paper-tick",
            operator_session=operator_session,
            payload=payload,
        )

    def accept_runner_start(
        self,
        name: str,
        request: RunnerStartAcceptRequest,
        *,
        operator_session: str | None,
    ) -> dict:
        if not isinstance(request, RunnerStartAcceptRequest):
            raise ServiceError(400, "Runner acceptance is invalid.")
        normalized = self._validated_name(name)
        _directory, deployed, _ledger, _state, _latest = self._paper_state(
            normalized,
            local_paper_only=True,
        )
        if deployed.broker != "paper":
            raise ServiceError(403, "Runner requires a local-paper deployment.", code="broker-not-web-supported")
        model_calls = _estimate_paper_model_calls(
            deployed.spec,
            len(deployed.universe),
        )
        max_calls, max_resources = _runner_limits(
            deployed.spec,
            universe_size=len(deployed.universe),
            max_sessions=request.max_sessions,
            max_runtime_minutes=request.max_runtime_minutes,
        )
        payload = {
            "kind": "runner-start",
            "expected_head": request.expected_head,
            "initial_due_set": list(request.due_set),
            "max_sessions": request.max_sessions,
            "max_runtime_minutes": request.max_runtime_minutes,
            "max_calls": max_calls,
            "max_resources": max_resources,
            "maximum_model_calls_per_session": model_calls,
        }
        return self._accept_local_paper_operation(
            normalized,
            request,
            action="paper-runner-start",
            operator_session=operator_session,
            payload=payload,
        )

    def _accept_local_paper_operation(
        self,
        name: str,
        request: PaperTickAcceptRequest | RunnerStartAcceptRequest,
        *,
        action: str,
        operator_session: str | None,
        payload: dict[str, object],
    ) -> dict:
        self._require_writes()
        if not operator_session:
            raise ServiceError(403, "A server-owned operator session is required.")
        if not self.network_enabled:
            raise ServiceError(403, "Network capability is disabled for this server.")
        store = self._operation_store
        worker = self._paper_operation_jobs
        if store is None or worker is None:
            raise ServiceError(409, "Paper operation worker is unavailable.")
        normalized = self._validated_name(name)
        self._guard_protected(normalized)
        capture_id = self._preview_captures.get(request.preview_id)
        capture = self._captures.get(capture_id or "")
        if capture is None or capture.subject_id != normalized:
            raise ServiceError(409, "Paper preview is no longer available; review again.", code="stale-preview")
        if request.due_set != payload.get("initial_due_set", request.due_set):
            raise ServiceError(409, "Reviewed session set changed; review again.", code="stale-preview")
        if payload.get("expected_head") != request.expected_head:
            raise ServiceError(409, "Reviewed ledger head changed; review again.", code="stale-preview")

        def current_state() -> tuple[str | None, tuple[str, ...]]:
            return self._resolve_paper_schedule(normalized, capture)

        def start_worker(operation: OperationRecord) -> None:
            selected_capture = self._captures.get(operation.capture_id)
            if selected_capture is None or selected_capture.digest != operation.capture_digest:
                raise OperationError("captured paper inputs are unavailable")

            def work(progress, cancelled, _apply_if_current):
                if action == "paper-tick":
                    return self._execute_manual_tick(
                        operation,
                        selected_capture,
                        progress,
                        cancelled,
                    )
                return self._execute_runner_start(
                    operation,
                    selected_capture,
                    progress,
                    cancelled,
                )

            worker.submit(operation, work, reservation=reservation)

        reservation = self._reserve_operation_slot(worker, subject_id=normalized, request_id=request.request_id)
        try:
            with self._settings_lock:
                self._ensure_settings_available()
                if self._runtime_settings.version != capture.settings_version or self._runtime_settings.model != capture.model or self._runtime_settings.data_provider != capture.data_provider or self._runtime_settings.llm_provider != capture.llm_provider:
                    raise ServiceError(409, "Runtime settings changed; review the paper operation again.", code="stale-preview")
                self._require_local_paper_policy(self._runtime_settings)
                try:
                    operation = store.accept_request(
                        request_id=request.request_id,
                        action=action,
                        subject_id=normalized,
                        preview_id=request.preview_id,
                        preview_digest=request.preview_digest,
                        confirmation_token=request.confirmation_token,
                        operator_session=operator_session,
                        expected_head=request.expected_head,
                        due_set=tuple(request.due_set),
                        payload=payload,
                        now=_utcnow(),
                        start_worker=start_worker,
                        current_state_resolver=current_state,
                        capacity=(_PAPER_POOL_ACTIONS, _PAPER_POOL_CAPACITY if reservation is not None else 0),
                    )
                except ConfirmationExpired:
                    raise ServiceError(410, "Confirmation expired; review the paper operation again.") from None
                except (ConfirmationRejected, StalePreview):
                    raise ServiceError(409, "Reviewed paper operation is stale or no longer valid.", code="stale-preview") from None
                except OperationCapacityExceeded:
                    raise _capacity_denied(normalized, request.request_id) from None
                except OperationStartUncertain:
                    raise ServiceError(409, "Paper operation start is uncertain; inspect its durable status.", code="ownership-unknown") from None
                except OperationConflict:
                    raise ServiceError(409, "Paper operation request conflicts with durable state.", code="request-conflict") from None
                except (AdmissionError, JobConflict):
                    raise ServiceError(409, "Paper operation conflicts with current runner or execution state.", code="writer-conflict") from None
                except OperationBusy:
                    raise ServiceError(409, "Operation storage is busy; this request was not processed now. Retry later; if this request was submitted before, inspect its operation status first.", code="writer-conflict", retry_policy="retry-later") from None
                except OperationError:
                    raise ServiceError(409, "Paper operation could not be accepted.") from None
        finally:
            worker.release(reservation)
        return self._operation_view(operation)

    def _reserve_operation_slot(
        self,
        worker: OperationJobRegistry,
        *,
        subject_id: str,
        request_id: str,
    ):
        """Reserve a local worker slot before acceptance.

        ``None`` means this process is at capacity: acceptance then runs with a
        zero durable bound so a replay of an admitted request still answers with
        its record while any new acceptance is denied with 429 before effects.
        """
        try:
            reservation = worker.try_reserve()
        except JobConflict:
            raise ServiceError(409, "The operation worker is shutting down; nothing was accepted.", code="writer-conflict", retry_policy="retry-later", subject_id=subject_id, request_id=request_id) from None
        if reservation is not None:
            worker.reclaim_stranded()
        return reservation

    def _execute_manual_tick(
        self,
        operation: OperationRecord,
        capture: FrozenCapture,
        progress: Callable[[int], None],
        cancelled: Callable[[], bool],
    ) -> dict[str, object]:
        payload = dict(operation.payload)
        kind = payload.get("kind")
        expected = {"kind", "expected_head"} if kind == "manual-no-work" else {"kind", "session", "expected_head"}
        if set(payload) != expected or kind not in {"manual-tick", "manual-no-work"}:
            raise OperationError("stored paper tick request is invalid")
        if capture.code_version != code_version() or capture.broker != "paper":
            raise OperationError("captured paper tick is incompatible")
        if capture.mandate_snapshot is None:
            raise OperationError("captured mandate is unavailable")
        try:
            spec = FundSpec.model_validate_json(capture.mandate_snapshot)
        except ValueError:
            raise OperationError("captured mandate is invalid") from None
        if spec.name != operation.subject_id or mandate_hash(spec) != capture.mandate_digest or capture.credential_versions or capture.credential_handles:
            raise OperationError("captured paper inputs changed")
        session = payload.get("session")
        if kind == "manual-tick" and not isinstance(session, str):
            raise OperationError("stored paper session is invalid")
        model_calls = _estimate_paper_model_calls(spec, len(capture.universe))
        if model_calls > 1000:
            raise AuthorizationDenied("manual model-call bound is invalid")
        now = _utcnow()
        dispatch = None
        if kind == "manual-tick":
            dispatch = self._authorize_manual_capture(
                capture,
                now=now,
                model_calls=model_calls,
                operation=operation,
                cancelled=cancelled,
            )
        progress(10)
        if cancelled():
            raise JobCancelled()

        directory = self._safe_child("paper", operation.subject_id)
        try:
            with self._fund_lock(operation.subject_id):
                with self._paper_manual_lane(operation.subject_id):
                    self._verify_root_inventory()
                    deployed = load_deployed(directory)
                    if deployed.broker != "paper" or mandate_hash(deployed.spec) != capture.mandate_digest or tuple(deployed.universe) != tuple(capture.universe):
                        raise ServiceError(409, "Paper deployment changed after review.", code="stale-preview")
                    ledger = Ledger(directory)
                    state, latest = self._replay_paper_state(deployed, ledger)
                    head = latest.hash if latest is not None else None
                    if head != payload["expected_head"]:
                        raise ServiceError(409, "Paper ledger head changed after review.", code="stale-preview")
                    if state.halted is not None:
                        raise ServiceError(423, "Halted funds cannot run a paper tick.", code="halted")
                    self._require_paper_work_ready(deployed, ledger, state)
                    if head != payload["expected_head"]:
                        raise ServiceError(409, "Paper ledger head changed after review.", code="stale-preview")
                    progress(20)
                    if kind == "manual-tick":
                        progress(30)
                        with self._make_data_client(
                            capture.data_provider,
                            dispatch=dispatch,
                        ) as client:
                            due = self._next_paper_session(
                                deployed,
                                state.last_session,
                                provider=capture.data_provider,
                                now=now,
                                data_client=client,
                            )
                            if due != session:
                                raise ServiceError(409, "Paper due-set changed after review.", code="stale-preview")
                            record = tick(
                                directory,
                                client,
                                session=session,
                                expected_head=payload["expected_head"],
                                build_fund=self._captured_fund_factory(
                                    capture,
                                    dispatch,
                                ),
                                now=lambda: now.astimezone(NEW_YORK),
                                operation_id=operation.operation_id,
                                request_id=operation.request_id,
                                capture_id=capture.capture_id,
                                capture_digest=capture.digest,
                                on_progress=progress,
                            )
        except ServiceError:
            raise
        except LedgerHeadPublicationError:
            raise ServiceError(423, "Paper tick recorded; root head inventory requires offline review.", code="reconciliation-required") from None
        except (AdmissionError, HandoverError, LedgerError, OSError, ValueError):
            raise ServiceError(409, "Paper tick could not be executed safely.") from None
        progress(95)
        if kind == "manual-no-work":
            return {
                "outcome": "nothing-due",
                "capture_id": capture.capture_id,
                "capture_digest": capture.digest,
            }
        return {
            "session": record.session,
            "ledger_head": record.hash,
            "capture_id": capture.capture_id,
            "capture_digest": capture.digest,
        }

    def _execute_runner_start(
        self,
        operation: OperationRecord,
        capture: FrozenCapture,
        progress: Callable[[int], None],
        cancelled: Callable[[], bool],
    ) -> dict[str, object]:
        payload = dict(operation.payload)
        expected = {
            "kind",
            "expected_head",
            "initial_due_set",
            "max_sessions",
            "max_runtime_minutes",
            "max_calls",
            "max_resources",
            "maximum_model_calls_per_session",
        }
        if set(payload) != expected or payload.get("kind") != "runner-start":
            raise OperationError("stored runner request is invalid")
        if capture.code_version != code_version() or capture.broker != "paper":
            raise OperationError("captured runner is incompatible")
        if capture.mandate_snapshot is None:
            raise OperationError("captured mandate is unavailable")
        try:
            spec = FundSpec.model_validate_json(capture.mandate_snapshot)
        except ValueError:
            raise OperationError("captured mandate is invalid") from None
        if spec.name != operation.subject_id or mandate_hash(spec) != capture.mandate_digest or capture.credential_versions or capture.credential_handles:
            raise OperationError("captured runner inputs changed")
        with self._settings_lock:
            settings = self._runtime_settings
            if settings.version != capture.settings_version or settings.data_provider != capture.data_provider or settings.llm_provider != capture.llm_provider or settings.model != capture.model or settings.endpoint != capture.endpoint:
                raise OperationError("captured runner settings changed")
            self._require_local_paper_policy(settings)
        initial_due = payload.get("initial_due_set")
        if not isinstance(initial_due, (list, tuple)) or len(initial_due) > 1 or any(not isinstance(session, str) for session in initial_due):
            raise OperationError("stored runner due-set is invalid")
        max_sessions = payload.get("max_sessions")
        max_runtime_minutes = payload.get("max_runtime_minutes")
        max_calls, max_resources = _runner_limits(
            spec,
            universe_size=len(capture.universe),
            max_sessions=max_sessions,
            max_runtime_minutes=max_runtime_minutes,
        )
        if max_calls != payload.get("max_calls") or max_resources != payload.get("max_resources") or _estimate_paper_model_calls(spec, len(capture.universe)) != payload.get("maximum_model_calls_per_session"):
            raise OperationError("stored runner bounds changed")
        if cancelled():
            raise JobCancelled()
        progress(10)
        try:
            state = self._runner_manager.start(
                operation.subject_id,
                capture,
                expected_head=payload["expected_head"],
                initial_due_set=tuple(initial_due),
                max_sessions=max_sessions,
                expires_at=_utcnow() + timedelta(minutes=max_runtime_minutes),
                max_calls=max_calls,
                max_resources=max_resources,
                operation_id=operation.operation_id,
                operation_digest=operation.request_digest,
            )
        except (OwnedRunnerError, AdmissionError, OSError, ValueError):
            raise ServiceError(409, "Owned runner could not be started safely.") from None
        if cancelled() and state.get("available"):
            try:
                self._runner_manager.request_stop(operation.subject_id)
            except OwnedRunnerError:
                pass
        progress(95)
        return {
            "runner": state,
            "capture_id": capture.capture_id,
            "capture_digest": capture.digest,
        }

    def _resolve_paper_schedule(
        self,
        name: str,
        capture: FrozenCapture,
    ) -> tuple[str | None, tuple[str, ...]]:
        self._verify_root_inventory()
        directory, deployed, ledger, state, latest = self._paper_state(
            name,
            local_paper_only=True,
        )
        if deployed.broker != "paper" or mandate_hash(deployed.spec) != capture.mandate_digest or tuple(deployed.universe) != tuple(capture.universe):
            raise ServiceError(409, "Paper deployment changed after review.", code="stale-preview")
        if state.halted is not None:
            raise ServiceError(423, "Halted funds cannot accept a paper operation.", code="halted")
        self._require_paper_work_ready(deployed, ledger, state)
        head = latest.hash if latest is not None else None
        preview_dispatch = self._authorize_manual_capture(
            capture,
            now=_utcnow(),
            model_calls=_estimate_paper_model_calls(
                deployed.spec,
                len(capture.universe),
            ),
        )
        due = self._next_paper_session(
            deployed,
            state.last_session,
            provider=capture.data_provider,
            now=_utcnow(),
            dispatch=preview_dispatch,
        )
        return head, (due,) if due is not None else ()

    def _next_paper_session(
        self,
        deployed: DeployedFund,
        last_session: str | None,
        *,
        provider: str,
        now,
        data_client=None,
        dispatch: ProviderDispatch | None = None,
    ) -> str | None:
        moment = now.astimezone(NEW_YORK)
        if deployed.spec.is_intraday:
            return next_session(
                None,
                deployed.spec,
                last_session,
                now=lambda: moment,
            )
        if data_client is not None:
            return next_session(
                data_client,
                deployed.spec,
                last_session,
                now=lambda: moment,
            )
        with self._make_data_client(
            provider,
            dispatch=dispatch,
        ) as client:
            return next_session(
                client,
                deployed.spec,
                last_session,
                now=lambda: moment,
            )

    def _authorize_manual_capture(
        self,
        capture: FrozenCapture,
        *,
        now,
        model_calls: int,
        operation: OperationRecord | None = None,
        cancelled: Callable[[], bool] | None = None,
    ) -> ProviderDispatch | None:
        if not self.network_enabled:
            raise ServiceError(403, "Network capability is disabled for this server.")
        try:
            breakpoints_target = KEN_FRENCH_BREAKPOINTS_TARGET
            data_target = ProviderTarget(
                kind="data",
                provider=capture.data_provider,
            )
            llm_target = ProviderTarget(
                kind="llm",
                provider=capture.llm_provider,
                model=capture.model,
                endpoint=capture.endpoint,
            )
            validate_llm_transport(llm_target)
            data_class = classify_provider(data_target)
            llm_class = classify_provider(
                llm_target,
                approved_local_models={capture.model},
            )
            if data_class is not ProviderClass.FREE_DATA or llm_class is not ProviderClass.LOCAL:
                raise AuthorizationDenied("manual paper providers are not local/free")
        except AuthorizationDenied:
            raise ServiceError(403, "Paper operations require free market data and a local model.") from None
        if operation is None:
            preview_calls = 10
            preview_id = uuid4().hex
            try:
                return make_one_shot_dispatch(
                    root_id=capture.root_id,
                    subject_id=capture.subject_id,
                    capture_digest=capture.digest,
                    operation_id=preview_id,
                    operation_digest=capture.digest,
                    expires_at=now + timedelta(minutes=10),
                    targets=(data_target,),
                    max_calls=preview_calls,
                    max_cost=Decimal("0"),
                    max_resources=preview_calls,
                    upper_bound_costs={
                        data_target.identity: Decimal("0"),
                    },
                    per_target_bounds={
                        data_target.identity: (
                            preview_calls,
                            Decimal("0"),
                            preview_calls,
                        ),
                    },
                    clock=_utcnow,
                    boundary_check=lambda: self._check_preview_dispatch_fence(
                        capture,
                    ),
                )
            except AuthorizationDenied:
                raise ServiceError(403, "Paper preview provider authorization could not be established.") from None
        calls = min(10000, max(100, model_calls + 100 * len(capture.universe)))
        expires_at = self._preview_expiries.get(operation.preview_id)
        if expires_at is None:
            raise ServiceError(409, "Paper operation deadline is unavailable; review again.", code="stale-preview")
        targets = (
            data_target,
            llm_target,
            breakpoints_target,
        )
        per_target_bounds = {
            data_target.identity: (calls, Decimal("0"), calls),
            llm_target.identity: (calls, Decimal("0"), calls),
            breakpoints_target.identity: (1, Decimal("0"), 1),
        }
        max_calls = sum(bounds[0] for bounds in per_target_bounds.values())
        max_resources = sum(bounds[2] for bounds in per_target_bounds.values())
        try:
            return make_one_shot_dispatch(
                root_id=capture.root_id,
                subject_id=capture.subject_id,
                capture_digest=capture.digest,
                operation_id=operation.operation_id,
                operation_digest=operation.request_digest,
                expires_at=expires_at,
                targets=targets,
                max_calls=max_calls,
                max_cost=Decimal("0"),
                max_resources=max_resources,
                upper_bound_costs={target.identity: Decimal("0") for target in targets},
                per_target_bounds=per_target_bounds,
                approved_local_models={capture.model},
                clock=_utcnow,
                boundary_check=lambda: self._check_dispatch_fence(
                    operation,
                    capture,
                    cancelled or (lambda: False),
                    paper=True,
                ),
            )
        except AuthorizationDenied:
            raise ServiceError(403, "Paper provider authorization could not be established.") from None

    def _check_preview_dispatch_fence(self, capture: FrozenCapture) -> None:
        try:
            self.root_context.revalidate()
        except RootPathError:
            raise AuthorizationDenied("preview root is unavailable") from None
        if not self.network_enabled:
            raise AuthorizationDenied("network capability is disabled")
        with self._settings_lock:
            settings = self._runtime_settings
            if settings.version != capture.settings_version or settings.data_provider != capture.data_provider or settings.llm_provider != capture.llm_provider or settings.model != capture.model or settings.endpoint != capture.endpoint:
                raise AuthorizationDenied("preview settings changed")

    def _require_local_paper_policy(self, settings: RuntimeSettings) -> None:
        if not self.network_enabled:
            raise ServiceError(403, "Network capability is disabled for this server.")
        data = ProviderTarget(kind="data", provider=settings.data_provider)
        llm = ProviderTarget(
            kind="llm",
            provider=settings.llm_provider,
            model=settings.model,
            endpoint=settings.endpoint,
        )
        try:
            validate_llm_transport(llm)
            data_class = classify_provider(data)
            llm_class = classify_provider(
                llm,
                approved_local_models={settings.model},
            )
        except AuthorizationDenied:
            raise ServiceError(
                422,
                "Provider configuration is not supported for local-paper operations.",
                code="readiness-denied",
            ) from None
        if data_class is not ProviderClass.FREE_DATA:
            raise ServiceError(422, "Paper operations require free yfinance market data.", code="readiness-denied")
        if llm_class is not ProviderClass.LOCAL:
            raise ServiceError(422, "Paper operations require a local Ollama model endpoint.", code="readiness-denied")

    def _captured_fund_factory(
        self,
        capture: FrozenCapture,
        dispatch: ProviderDispatch,
    ) -> Callable[[FundSpec], Fund]:
        if self._custom_fund_factory:
            return self._fund_factory
        return lambda spec: self._default_fund_factory(
            spec,
            capture,
            dispatch,
        )

    def _check_dispatch_fence(
        self,
        operation: OperationRecord,
        capture: FrozenCapture,
        cancelled: Callable[[], bool],
        *,
        paper: bool,
    ) -> None:
        if cancelled():
            raise JobCancelled()
        try:
            self.root_context.revalidate()
        except RootPathError:
            raise AuthorizationDenied("operation root is unavailable") from None
        if not self.network_enabled:
            raise AuthorizationDenied("network capability is disabled")
        with self._settings_lock:
            settings = self._runtime_settings
            if settings.version != capture.settings_version or settings.data_provider != capture.data_provider or settings.llm_provider != capture.llm_provider or settings.model != capture.model or settings.endpoint != capture.endpoint:
                raise AuthorizationDenied("captured provider settings changed")
        if capture.credential_versions:
            if self._credential_store is None:
                raise AuthorizationDenied("captured credentials are unavailable")
            for provider, version in capture.credential_versions.items():
                try:
                    current, configured = self._credential_store.version(provider)
                except CredentialStoreError:
                    raise AuthorizationDenied("captured credentials are unavailable") from None
                if current != version or not configured:
                    raise AuthorizationDenied("captured credentials changed")
        # Backtests use accepted capture; live mandate edits apply to later work.
        if paper:
            try:
                self._verify_root_inventory()
                directory = self._safe_child("paper", operation.subject_id)
                deployed = load_deployed(directory)
                state, latest = self._replay_paper_state(
                    deployed,
                    Ledger(directory),
                )
            except (HandoverError, LedgerError, OSError, RootPathError, ValueError):
                raise AuthorizationDenied("paper operation state is unavailable") from None
            current_head = latest.hash if latest is not None else None
            if deployed.broker != "paper" or mandate_hash(deployed.spec) != capture.mandate_digest or tuple(deployed.universe) != capture.universe or current_head != operation.payload.get("expected_head") or state.halted is not None:
                raise AuthorizationDenied("paper operation fence changed")

    def _verify_root_inventory(self) -> None:
        try:
            verify_root_inventory(self.root_context)
        except (LedgerError, LedgerInventoryCorrupt):
            raise ServiceError(423, "Paper state is invalid (LedgerError).", code="replay-corrupt") from None
        except HandoverError:
            raise ServiceError(423, "Offline paper ledger inventory changed; writes are denied.", code="reconciliation-required") from None

    def get_valuation(self, name: str) -> dict:
        """Return current-head estimate; never contacts a provider."""
        return self.paper_detail(name)["live_value"]

    def refresh_valuation(self, name: str, request: ValuationRefreshRequest) -> dict:
        self._require_writes()
        if not self.network_enabled:
            raise ServiceError(403, "Network capability is disabled for this server.")
        if not isinstance(request, ValuationRefreshRequest):
            raise ServiceError(400, "Valuation request is invalid.")
        normalized = self._validated_name(name)
        self._guard_protected(normalized)
        with self._fund_lock(normalized):
            with self._paper_execution_lane(normalized):
                _, deployed, _, state, latest = self._paper_state(
                    normalized,
                    local_paper_only=True,
                )
                if deployed.broker != "paper":
                    raise ServiceError(403, "Valuation requires a local-paper deployment.", code="broker-not-web-supported")
                expected_head = latest.hash if latest is not None else None
                if request.expected_head != expected_head:
                    raise ServiceError(409, "Paper ledger changed; reload before refreshing valuation.", code="stale-preview")
                positions = {ticker: shares for ticker, shares in state.positions.items() if shares != 0}
                if len(positions) > MAX_VALUATION_POSITIONS:
                    raise ServiceError(409, "Paper holdings exceed the quote-call bound.")
                if set(positions) - set(deployed.universe):
                    raise ServiceError(409, "Paper holdings do not match the deployed universe.")
                cash = state.cash
                recorded_nav = latest.nav if latest is not None else None

        identity = _windows_name_key(deployed.name)
        with self._valuation_lock:
            generation = self._valuation_generations.get(identity, 0) + 1
            self._valuation_generations[identity] = generation

        quotes: dict[str, PriceSnapshot | None] = {}
        errors: dict[str, str] = {}
        if positions:
            try:
                with self._settings_lock:
                    settings = self._runtime_settings
                    capture_settings = RuntimeSettings(
                        data_provider="yfinance",
                        llm_provider=settings.llm_provider,
                        model=settings.model,
                        endpoint=settings.endpoint,
                        timeout_seconds=settings.timeout_seconds,
                        parameters=settings.parameters,
                        version=settings.version,
                        provenance=settings.provenance,
                    )
                capture = freeze_capture(
                    root=self.root_context,
                    subject_id=normalized,
                    mandate_digest=mandate_hash(deployed.spec),
                    universe=tuple(deployed.universe),
                    broker=deployed.broker,
                    settings=capture_settings,
                    credential_versions={},
                    code_version=code_version(),
                    mandate_snapshot=deployed.spec.model_dump(mode="json"),
                )
                operation_id = uuid4().hex
                operation_digest = hashlib.sha256(
                    json.dumps(
                        {
                            "capture": capture.digest,
                            "expected_head": expected_head,
                            "generation": generation,
                            "positions": sorted(positions),
                        },
                        sort_keys=True,
                        separators=(",", ":"),
                    ).encode("utf-8")
                ).hexdigest()

                def boundary_check() -> None:
                    if not self.network_enabled:
                        raise AuthorizationDenied("network capability is disabled")
                    try:
                        self.root_context.revalidate()
                    except RootPathError:
                        raise AuthorizationDenied("valuation root is unavailable") from None
                    with self._settings_lock:
                        if self._runtime_settings.version != capture_settings.version:
                            raise AuthorizationDenied("valuation settings changed")
                    try:
                        self._verify_root_inventory()
                        _, current_deployed, _, current_state, current_latest = self._paper_state(
                            normalized,
                            local_paper_only=True,
                        )
                    except ServiceError:
                        raise AuthorizationDenied("valuation state is unavailable") from None
                    current_head = current_latest.hash if current_latest is not None else None
                    if current_head != expected_head or current_state.halted is not None or mandate_hash(current_deployed.spec) != capture.mandate_digest:
                        raise AuthorizationDenied("valuation fence changed")

                data_target = ProviderTarget(kind="data", provider="yfinance")
                dispatch = make_one_shot_dispatch(
                    root_id=capture.root_id,
                    subject_id=capture.subject_id,
                    capture_digest=capture.digest,
                    operation_id=operation_id,
                    operation_digest=operation_digest,
                    expires_at=_utcnow() + timedelta(minutes=10),
                    targets=(data_target,),
                    max_calls=MAX_VALUATION_POSITIONS * 10,
                    max_cost=Decimal("0"),
                    max_resources=MAX_VALUATION_POSITIONS * 10,
                    upper_bound_costs={data_target.identity: Decimal("0")},
                    clock=_utcnow,
                    boundary_check=boundary_check,
                )
                with self._make_data_client(
                    provider="yfinance",
                    dispatch=dispatch,
                ) as client:
                    for ticker in sorted(positions):
                        try:
                            quote = client.get_snapshot(ticker)
                            if quote is not None and not isinstance(quote, PriceSnapshot):
                                errors[ticker] = "InvalidQuote"
                            else:
                                quotes[ticker] = quote
                        except BudgetDenied:
                            raise
                        except Exception as exc:
                            errors[ticker] = type(exc).__name__
            except BudgetDenied:
                raise ServiceError(
                    429,
                    "The valuation's authorized provider budget was exhausted; no further quotes were requested.",
                    code="budget-exhausted",
                    subject_id=normalized,
                ) from None
            except Exception as exc:
                errors.update({ticker: type(exc).__name__ for ticker in positions})

        estimate = estimate_valuation(
            cash=cash,
            positions=positions,
            quotes=quotes,
            errors=errors,
            as_of=_utcnow(),
            expected_head=expected_head,
            recorded_nav=recorded_nav,
        )
        estimate.update(
            {
                "request_id": uuid4().hex,
                "deployment": deployed.name,
            }
        )

        with self._fund_lock(normalized):
            with self._paper_execution_lane(normalized):
                _, current, _, current_state, current_latest = self._paper_state(
                    normalized,
                    local_paper_only=True,
                )
                current_head = current_latest.hash if current_latest is not None else None
                if current.name != deployed.name or current_head != expected_head or current_state.cash != cash or current_state.positions != state.positions:
                    raise ServiceError(409, "Paper ledger changed during valuation; result discarded.")

        with self._valuation_lock:
            if self._valuation_generations.get(identity) != generation:
                estimate.update(
                    {
                        "status": "obsolete",
                        "value": None,
                        "partial_estimate": None,
                        "reason": "A newer valuation request superseded this result.",
                    }
                )
                return estimate
            self._valuation_estimates[identity] = estimate
        return estimate

    def session_report(self, name: str, session: str) -> dict:
        return self._session_report(self._verified_session_record(name, session))

    def session_report_download(self, name: str, session: str, expected_hash: str) -> str:
        record = self._verified_session_record(name, session)
        if record.hash != expected_hash:
            raise ServiceError(409, "Session report changed; reload the report before downloading.", code="stale-preview", current_head=record.hash)
        return record.model_dump_json(indent=2)

    def _verified_session_record(self, name: str, session: str) -> SessionRecord:
        normalized = self._validated_name(name)
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}(?:T\d{2}:\d{2}:\d{2})?", session):
            raise ServiceError(400, "Session key is invalid.")
        directory = self._safe_child("paper", normalized)
        if not directory.is_dir():
            raise ServiceError(404, "Paper fund not found.")
        try:
            deployed = load_deployed(directory)
        except (OSError, ValueError) as exc:
            raise ServiceError(409, f"Paper fund is invalid ({type(exc).__name__}).") from None
        ledger = Ledger(directory)
        record: SessionRecord | None = None

        def capture_verified(candidate: SessionRecord) -> None:
            nonlocal record
            if candidate.session == session:
                record = candidate

        try:
            ledger.replay(deployed.spec.capital, full=True, on_verified=capture_verified)
            if record is None:
                raise ServiceError(404, "Session report not found.")
        except ServiceError:
            raise
        except (LedgerError, OSError, ValueError) as exc:
            raise ServiceError(423, f"Ledger verification failed ({type(exc).__name__}).", code="replay-corrupt") from None
        return record

    def paper_scorecard(self, name: str) -> dict:
        snapshot = self.paper_detail(name)
        card = snapshot.get("scorecard")
        if card is None:
            raise ServiceError(409, snapshot.get("scorecard_error") or "No recorded sessions to score.")
        return card

    def list_research(
        self,
        *,
        limit: int = 50,
        cursor: str | None = None,
        search: str | None = None,
    ) -> dict:
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ServiceError(400, "Research page limit must be between 1 and 100.")
        if cursor is not None and (not isinstance(cursor, str) or not _REPORT_ID.fullmatch(cursor) or ".." in cursor):
            raise ServiceError(400, "Research cursor is invalid.")
        if search is not None and (not isinstance(search, str) or len(search) > 128 or any(ord(character) < 32 or ord(character) == 127 for character in search)):
            raise ServiceError(400, "Research search is invalid.")

        directory = self._safe_child("research")
        query = search.casefold() if search else ""
        response = {
            "items": [],
            "errors": [],
            "next_cursor": None,
            "limit": limit,
            "total": 0,
            "search": search or "",
        }
        if not directory.exists():
            return response
        if not directory.is_dir():
            raise ServiceError(409, "Research storage is not a directory.")

        entries = []
        paths = sorted(
            directory.glob("*.json"),
            key=lambda entry: (entry.name.casefold(), entry.name),
            reverse=True,
        )
        for path in paths:
            try:
                if not _REPORT_ID.fullmatch(path.name) or ".." in path.name:
                    raise ServiceError(400, "Research report identifier is invalid.")
                safe_path = self._safe_child("research", path.name)
                result = FundBacktestResult.model_validate_json(safe_path.read_text(encoding="utf-8"))
                item = self._research_summary(path.name, result)
                if query and query not in path.name.casefold() and query not in item["fund"].casefold():
                    continue
                entries.append({"id": path.name, "item": item})
            except ServiceError as exc:
                if not query or query in path.name.casefold():
                    entries.append({"id": path.name, "error": exc.detail})
            except (OSError, ValueError) as exc:
                if not query or query in path.name.casefold():
                    entries.append(
                        {
                            "id": path.name,
                            "error": f"Invalid research report ({type(exc).__name__}).",
                        }
                    )

        response["total"] = len(entries)
        if cursor is not None:
            cursor_key = (cursor.casefold(), cursor)
            entries = [entry for entry in entries if (entry["id"].casefold(), entry["id"]) < cursor_key]
        page = entries[:limit]
        response["items"] = [entry["item"] for entry in page if "item" in entry]
        response["errors"] = [{"id": entry["id"], "error": entry["error"]} for entry in page if "error" in entry]
        if len(entries) > limit:
            response["next_cursor"] = page[-1]["id"]
        return response

    def research_report(self, report_id: str) -> dict:
        if not _REPORT_ID.fullmatch(report_id) or ".." in report_id:
            raise ServiceError(404, "Research report not found.")
        path = self._safe_child("research", report_id)
        if not path.is_file():
            raise ServiceError(404, "Research report not found.")
        try:
            result = FundBacktestResult.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise ServiceError(422, f"Research report is invalid ({type(exc).__name__}).", code="readiness-denied") from None
        return {
            **self._research_summary(report_id, result),
            "dates": result.dates,
            "nav": result.nav,
            "benchmark_nav": result.benchmark_nav,
            "sessions": [self._session_summary(record) for record in result.records],
        }

    def settings(self) -> dict:
        model_options = [{"label": label, "id": model_id, "provider": provider} for label, model_id, provider in load_api_models() if is_supported(provider)]
        credential_status = self._credential_status_map()
        with self._settings_lock:
            effective = self._runtime_settings
        active_items = self._active_operation_captures()
        active_captures, active_captures_available = self._active_capture_views(active_items, effective)
        configuration = self._configuration_view(effective, active_items)
        providers = []
        for provider in [
            *PROVIDER_ENV_VARS,
            *sorted(KEYLESS_PROVIDERS),
            *sorted(DATA_PROVIDER_ENV_VARS),
        ]:
            env_var = env_var_for(provider) or DATA_PROVIDER_ENV_VARS.get(provider)
            saved = credential_status.get(
                provider,
                {"version": 0, "configured": False},
            )
            providers.append(
                {
                    "provider": provider,
                    "requires_key": env_var is not None,
                    "configured": saved["configured"] if env_var else True,
                    "version": saved["version"] if env_var else 0,
                }
            )
        public = _public_settings(effective)
        return {
            **public,
            "settings_error": self._settings_error,
            "models": model_options,
            "providers": providers,
            "data_providers": [
                {
                    "id": "fd",
                    "label": "Financial Datasets",
                    "requires_key": True,
                    "configured": credential_status.get(
                        "fd",
                        {"configured": False},
                    )["configured"],
                    "version": credential_status.get(
                        "fd",
                        {"version": 0},
                    )["version"],
                },
                {
                    "id": "yfinance",
                    "label": "Yahoo Finance",
                    "requires_key": False,
                    "configured": True,
                    "version": 0,
                },
            ],
            "active_captures": active_captures,
            "active_captures_available": active_captures_available,
            "configuration": configuration,
            "network_enabled": self.network_enabled,
        }

    def credential_status(self) -> dict:
        return {
            "items": [
                {
                    "provider": provider,
                    "requires_key": True,
                    **value,
                }
                for provider, value in self._credential_status_map().items()
            ]
        }

    def set_model(self, request: ModelRequest) -> dict:
        self._require_writes()
        provider = _supported_model_providers().get(request.model)
        if provider is None:
            raise ServiceError(400, "Model is not in the supported provider catalog.")
        values: dict[str, object] = {
            "model": request.model,
            "llm_provider": provider,
        }
        if provider != "Ollama" and "context_size" in self._runtime_settings.parameters:
            values["parameters"] = {name: value for name, value in self._runtime_settings.parameters.items() if name != "context_size"}
        _persisted, updated = self._persist_runtime_settings(
            values,
            expected_version=request.expected_version,
        )
        return {"model": updated.model, "scope": "root", "version": updated.version}

    def save_runtime_settings(self, request: RuntimeSettingsRequest) -> dict:
        self._require_writes()
        provider = _supported_model_providers().get(request.model)
        if provider is None:
            raise ServiceError(400, "Model is not in the supported provider catalog.")
        values = request.model_dump(exclude={"expected_version"})
        values["llm_provider"] = provider
        _persisted, updated = self._persist_runtime_settings(
            values,
            expected_version=request.expected_version,
        )
        return {
            **_public_settings(updated),
            "scope": "root",
        }

    def set_credential(self, request: CredentialRequest) -> dict:
        self._require_writes()
        provider = _credential_provider(request.provider)
        value = request.value.get_secret_value()
        if not value or any(unicodedata.category(char) in {"Cc", "Cf"} for char in value):
            raise ServiceError(400, "Credential value is empty or contains control characters.")
        with self._settings_lock:
            if self._credential_store is None:
                raise ServiceError(409, "Private credential storage is unavailable.")
            try:
                version = self._credential_store.save(
                    provider,
                    value,
                    expected_version=request.expected_version,
                )
            except CredentialVersionConflict:
                raise ServiceError(409, "Credential version changed; reload before saving.", code="stale-preview") from None
            except CredentialStoreError:
                raise ServiceError(409, "Credential could not be saved.") from None
        return {"provider": provider, "configured": True, "version": version}

    def delete_credential(self, provider: str, *, expected_version: int) -> dict:
        self._require_writes()
        provider_name = _credential_provider(provider)
        if type(expected_version) is not int or expected_version < 0:
            raise ServiceError(400, "Credential version is invalid.")
        with self._settings_lock:
            if self._credential_store is None:
                raise ServiceError(409, "Private credential storage is unavailable.")
            try:
                version = self._credential_store.delete(
                    provider_name,
                    expected_version=expected_version,
                )
            except CredentialVersionConflict:
                raise ServiceError(409, "Credential version changed; reload before saving.", code="stale-preview") from None
            except CredentialStoreError:
                raise ServiceError(409, "Credential could not be deleted.") from None
        return {"provider": provider_name, "configured": False, "version": version}

    @staticmethod
    def _archive_view(record: dict) -> dict:
        fields = (
            "archive_id",
            "kind",
            "identity",
            "source_path",
            "digest",
            "state",
            "updated_at",
            "restore_operation_id",
            "recovery_required",
            "recovery_action",
            "recovery_error",
        )
        return {key: record[key] for key in fields if key in record}

    def list_lifecycle_archives(self) -> dict:
        try:
            store = LifecycleArchiveStore(self.root_context, self._admission)
            records = {item["archive_id"]: item for item in store.list_archives()}
            for archive_id, record in records.items():
                if self._has_unprepared_restore(record):
                    records[archive_id] = self._inspect_lifecycle_recovery(store, archive_id, record=record)
            if self._operation_store is not None:
                for operation in self._operation_store.interrupted_lifecycle_archives():
                    archive_id = operation.payload.get("archive_id")
                    if archive_id not in records:
                        records[archive_id] = self._inspect_lifecycle_recovery(store, archive_id, operation=operation)
            return {"items": [self._archive_view(item) for item in records.values()]}
        except OperationBusy:
            raise ServiceError(503, "Archive history is busy; retry the read.", code="observation-conflict") from None
        except (ArchiveError, AdmissionError, OperationError, HandoverError, OSError, RootPathError):
            raise ServiceError(409, "Archive history is unavailable.") from None

    def get_lifecycle_archive(self, archive_id: str) -> dict:
        try:
            store = LifecycleArchiveStore(self.root_context, self._admission)
            try:
                record = store.inspect(archive_id)
                if self._has_unprepared_restore(record):
                    record = self._inspect_lifecycle_recovery(store, archive_id, record=record)
            except ArchiveNotFound:
                matches = [] if self._operation_store is None else [operation for operation in self._operation_store.interrupted_lifecycle_archives() if operation.payload.get("archive_id") == archive_id]
                if len(matches) != 1:
                    raise
                record = self._inspect_lifecycle_recovery(store, archive_id, operation=matches[0])
            return self._archive_view(record)
        except ArchiveNotFound:
            raise ServiceError(404, "Archive not found.") from None
        except OperationBusy:
            raise ServiceError(503, "Archive inspection is busy; retry the read.", code="observation-conflict") from None
        except (ArchiveError, AdmissionError, OperationError, HandoverError, OSError, RootPathError):
            raise ServiceError(409, "Archive inspection is unavailable.") from None

    def _inspect_lifecycle_recovery(self, archives: LifecycleArchiveStore, archive_id: str, *, record: dict | None = None, operation: OperationRecord | None = None) -> dict:
        try:
            return self._review_lifecycle_archive(archives, archive_id, action="recover")
        except (ArchiveConflict, ArchiveNotFound):
            if record is None:
                if operation is None:
                    raise ArchiveNotFound("interrupted archive evidence is unavailable") from None
                payload = operation.payload
                record = {
                    "archive_id": archive_id,
                    "kind": payload["kind"],
                    "identity": payload["identity"],
                    "source_path": payload["source_path"],
                    "digest": payload["object_digest"],
                    "state": "archive-unprepared",
                    "updated_at": operation.updated_at,
                }
            return {
                **record,
                "recovery_required": True,
                "recovery_action": "manual-review",
                "recovery_error": "Safe automatic recovery cannot be verified. Preserve both locations and perform offline manual review.",
            }

    def _review_lifecycle_archive(self, archives: LifecycleArchiveStore, archive_id: str, *, action: str) -> dict:
        try:
            return archives.review_archive(archive_id, action=action)
        except ArchiveNotFound:
            if action != "recover" or self._operation_store is None:
                raise
            matches = [operation for operation in self._operation_store.interrupted_lifecycle_archives() if operation.payload.get("archive_id") == archive_id]
            if len(matches) != 1:
                raise ArchiveNotFound("interrupted archive identity is unavailable") from None
            payload = matches[0].public_view()["payload"]
            return archives.review_unprepared(payload["kind"], payload["identity"], archive_id=archive_id, expected_digest=payload["object_digest"], deployment_before=payload.get("deployment_before"))
        except ArchiveConflict:
            if action != "recover":
                raise
            record = archives.inspect(archive_id)
            if not self._has_unprepared_restore(record):
                raise
            return archives.review_unprepared_restore(archive_id)

    def _has_unprepared_restore(self, record: dict) -> bool:
        if record["state"] != "archived" or self._operation_store is None:
            return False
        return any(operation.status is OperationStatus.INTERRUPTED and operation.action in {"lifecycle-restore", "lifecycle-recover"} and operation.payload.get("archive_id") == record["archive_id"] and operation.payload.get("object_digest") == record["digest"] and operation.operation_id not in record.get("reconciled_operations", []) for operation in self._operation_store.active_for_subject(record["lane_identity"]))

    @contextmanager
    def _lifecycle_lane(self, subject: str) -> Iterator[None]:
        with ExitStack() as stack:
            stack.enter_context(self._admission.registry_lock(timeout=0))
            for lane, factory in (
                ("deployment", self._admission.deployment_lock),
                ("runner", self._admission.runner_reservation),
                ("execution", self._admission.execution_lease),
                ("control", self._admission.control_lane),
                ("research", self._admission.research_lane),
            ):
                if not self._admission.lane_is_held(lane, subject):
                    stack.enter_context(factory(subject, timeout=0))
            yield

    def _lifecycle_review(
        self,
        request: LifecyclePreviewRequest,
        *,
        archive_id: str | None = None,
    ) -> tuple[str, dict]:
        archives = LifecycleArchiveStore(self.root_context, self._admission)
        if request.action == "archive":
            record = archives.preview(request.kind, request.identity)
            record["archive_id"] = archive_id
        else:
            record = self._review_lifecycle_archive(archives, request.archive_id, action=request.action)
        subject = self._validated_name(record["lane_identity"])
        self._guard_protected(subject)
        kind, identity = record["kind"], record["identity"]
        source = record.get("review_path", record["source_path"])
        if kind == "deployment":
            deployed = load_deployed(self.root_context.resolve(source))
            if deployed.broker != "paper":
                raise ServiceError(403, "Lifecycle mutations require a local-paper deployment.", code="broker-not-web-supported")
        elif kind == "template":
            spec = load_spec(self.root_context.resolve(source))
            if spec.name != identity:
                raise ServiceError(409, "Template identity does not match its contents.")
            if spec.broker != "paper":
                raise ServiceError(403, "Lifecycle mutations require a local-paper template.", code="broker-not-web-supported")
        references = {"deployments": [], "research": []}
        related_subjects = {subject}
        paper = self._safe_child("paper")
        entries = sorted(paper.iterdir()) if paper.exists() else []
        if len(entries) > 10000:
            raise ServiceError(409, "Deployment reference inventory exceeds its bound.")
        heads = require_enrollment(self.root_context)["heads"]
        for entry in entries:
            directory = self._safe_child("paper", entry.name)
            if not directory.is_dir() or not self._safe_child("paper", entry.name, "fund.yaml").is_file():
                continue
            self._guard_protected(directory.name)
            deployed = load_deployed(directory)
            if _windows_name_key(deployed.spec.name) == _windows_name_key(subject) or deployed.name == subject:
                head = heads.get(_windows_name_key(deployed.name))
                if not isinstance(head, dict):
                    raise ServiceError(409, "Deployment reference head is unavailable.")
                references["deployments"].append(
                    {
                        "identity": deployed.name,
                        "mandate_digest": mandate_hash(deployed.spec),
                        "broker": deployed.broker,
                        "ledger_head": head.get("head_hash"),
                    }
                )
                related_subjects.add(deployed.name)
        research = self._safe_child("research")
        reports = sorted(research.glob("*.json")) if research.exists() else []
        if len(reports) > 10000:
            raise ServiceError(409, "Research reference inventory exceeds its bound.")
        for path in reports:
            raw = self.root_context.read_bytes(f"research/{path.name}")
            report = json.loads(raw.decode("utf-8"))
            fund = report.get("fund") if isinstance(report, dict) else None
            if not isinstance(fund, str):
                raise ServiceError(409, "Research reference identity is unavailable.")
            if _windows_name_key(fund) == _windows_name_key(subject):
                references["research"].append(
                    {
                        "identity": path.name,
                        "digest": hashlib.sha256(raw).hexdigest(),
                    }
                )
        runner_states = {}
        for related in sorted(related_subjects):
            self._guard_protected(related)
            runner = self._runner_state(related)
            runner_status = runner.get("status")
            completed_and_reserved = runner_status == "completed" and runner.get("available") is False and self._admission.lane_is_held("runner", related)
            if runner_status != "stopped" and not completed_and_reserved:
                raise ServiceError(409, "Lifecycle requires a verified quiescent runner.", code="ownership-unknown")
            observed = {"status": runner_status, "available": False}
            for filename in ("state", "control"):
                relative = f"{RUNNER_ROOT}/{runner_key(related)}/{filename}.json"
                try:
                    raw = self.root_context.read_bytes(relative)
                except FileNotFoundError:
                    observed[f"{filename}_digest"] = None
                else:
                    observed[f"{filename}_digest"] = hashlib.sha256(raw).hexdigest()
            runner_states[related] = observed
            for operation in self._operation_store.active_for_subject(related):
                reconciled = False
                if operation.status is OperationStatus.INTERRUPTED and operation.action in {
                    "lifecycle-archive",
                    "lifecycle-restore",
                    "lifecycle-recover",
                }:
                    try:
                        journal = archives.inspect(operation.payload.get("archive_id"))
                    except ArchiveNotFound:
                        journal = None
                    if journal is not None and operation.operation_id in journal.get("reconciled_operations", []) and journal["digest"] == operation.payload.get("object_digest"):
                        reconciled = True
                recovering = request.action == "recover" and operation.status is OperationStatus.INTERRUPTED and operation.action in {"lifecycle-archive", "lifecycle-restore", "lifecycle-recover"} and operation.payload.get("archive_id") == record["archive_id"]
                if not recovering and not reconciled:
                    raise ServiceError(409, "Lifecycle conflicts with an unfinished operation.", code="writer-conflict")
        payload = {
            "action": request.action,
            "kind": kind,
            "identity": identity,
            "archive_id": record["archive_id"],
            "object_digest": record["digest"],
            "source_path": record["source_path"],
            "references": references,
            "runner_state": runner_states,
            "journal_state": record.get("state"),
            "recovery_action": record.get("recovery_action"),
            "review_digest": record.get("review_digest", record["digest"]),
            "deployment_before": record.get("deployment_before") if request.action == "recover" else heads.get(_windows_name_key(identity)) if kind == "deployment" else None,
        }
        return subject, payload

    @staticmethod
    def _lifecycle_head(payload: dict) -> str:
        reviewed = dict(payload)
        if reviewed["action"] == "archive":
            # The new journal identifier is not an existing object revision.
            reviewed.pop("archive_id", None)
        return hashlib.sha256(json.dumps(reviewed, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()

    def _require_lifecycle_authority(self, action: str, offline_recovery: bool) -> None:
        if type(offline_recovery) is not bool:
            raise ServiceError(403, "Offline recovery authority is invalid.")
        if offline_recovery and action == "recover" and self.emergency_halt_available and self._owner_lease is not None:
            self._admission.require_root_owner()
            return
        self._require_writes()

    def create_lifecycle_preview(
        self,
        request: LifecyclePreviewRequest,
        *,
        operator_session: str | None,
        offline_recovery: bool = False,
    ) -> dict:
        self._require_lifecycle_authority(request.action, offline_recovery)
        if not operator_session:
            raise ServiceError(403, "A server-owned operator session is required.")
        if self._operation_store is None:
            raise ServiceError(409, "Durable operation storage is unavailable.")
        try:
            # Resolve once to select the lane, then review again while all writers are fenced.
            archives = LifecycleArchiveStore(self.root_context, self._admission)
            initial = archives.preview(request.kind, request.identity) if request.action == "archive" else self._review_lifecycle_archive(archives, request.archive_id, action=request.action)
            subject = self._validated_name(initial["lane_identity"])
            with self._settings_lock, self._lifecycle_lane(subject):
                self._ensure_settings_available()
                subject, payload = self._lifecycle_review(
                    request,
                    archive_id=uuid4().hex if request.action == "archive" else request.archive_id,
                )
                head = self._lifecycle_head(payload)
                settings = self._runtime_settings
                capture = freeze_capture(
                    root=self.root_context,
                    subject_id=subject,
                    mandate_digest=head,
                    universe=["SPY"],
                    broker="paper",
                    settings=settings,
                    credential_versions={},
                    code_version=code_version(),
                )
                now = _utcnow()
                preview = self._operation_store.create_preview(
                    action=f"lifecycle-{request.action}",
                    subject_id=subject,
                    expected_head=head,
                    due_set=(),
                    capture=capture,
                    operator_session=operator_session,
                    payload=payload,
                    now=now,
                    expires_at=now + timedelta(minutes=10),
                )
                self._cache_preview_capture(preview.preview_id, capture, preview.expires_at)
                while len(self._lifecycle_previews) >= 1000:
                    self._lifecycle_previews.pop(next(iter(self._lifecycle_previews)))
                self._lifecycle_previews[preview.preview_id] = payload
            return {
                **preview.public_view(),
                "confirmation_token": preview.confirmation_token,
                "capture": capture.public_view(current_settings_version=settings.version),
                "references": payload["references"],
                "consequences": [
                    "Only the exact reviewed object is moved; unrelated objects and immutable history are retained.",
                    "Restore collision-checks the original identity and never starts a runner or replays decisions.",
                    "No provider dispatch, permanent deletion, or replacement is authorized.",
                ],
            }
        except ArchiveNotFound:
            raise ServiceError(404, "Lifecycle object not found.") from None
        except OperationBusy:
            raise ServiceError(409, "Operation storage is busy; nothing was reviewed. Retry later.", code="writer-conflict", retry_policy="retry-later") from None
        except HandoverError:
            raise ServiceError(423, "Root head inventory requires offline reconciliation; lifecycle review is denied.", code="reconciliation-required") from None
        except (ArchiveError, AdmissionError, OperationError, ConfigurationError, OSError, RootPathError, ValueError):
            raise ServiceError(409, "Lifecycle review is unavailable.", code="writer-conflict") from None

    def accept_lifecycle(
        self,
        request: LifecycleAcceptRequest,
        *,
        operator_session: str | None,
        offline_recovery: bool = False,
    ) -> dict:
        self._require_lifecycle_authority(request.action, offline_recovery)
        if not operator_session:
            raise ServiceError(403, "A server-owned operator session is required.")
        store = self._operation_store
        if store is None:
            raise ServiceError(409, "Durable operation storage is unavailable.")
        existing = None
        try:
            existing = store.get_by_request(request.request_id)
            payload = dict(existing.payload) if existing is not None else self._lifecycle_previews.get(request.preview_id)
            if payload is None:
                raise StalePreview("lifecycle review is unavailable")
            if request.action != payload.get("action") or (request.action == "archive" and (request.kind != payload.get("kind") or request.identity != payload.get("identity"))) or (request.action != "archive" and request.archive_id != payload.get("archive_id")):
                raise StalePreview("lifecycle identity changed")
            subject = existing.subject_id if existing is not None else self._captures[self._preview_captures[request.preview_id]].subject_id
            arguments = dict(
                request_id=request.request_id,
                action=f"lifecycle-{request.action}",
                subject_id=subject,
                preview_id=request.preview_id,
                preview_digest=request.preview_digest,
                confirmation_token=request.confirmation_token,
                operator_session=operator_session,
                expected_head=request.expected_head,
                due_set=(),
                payload=payload,
                now=_utcnow(),
            )
            # Authenticate durable replay before looking up a source that may already have moved.
            if existing is not None:
                return self._operation_view(store.accept_request(**arguments))
            preview_request = LifecyclePreviewRequest(
                action=request.action,
                kind=request.kind,
                identity=request.identity,
                archive_id=request.archive_id,
            )

            def current_state():
                current_subject, current_payload = self._lifecycle_review(
                    preview_request,
                    archive_id=payload["archive_id"],
                )
                if current_subject != subject:
                    raise StalePreview("lifecycle subject changed")
                return self._lifecycle_head(current_payload), ()

            def execute(operation):
                fence = store.claim_worker(operation.operation_id, worker_id=uuid4().hex, now=_utcnow())
                store.mark_running(operation.operation_id, fence, now=_utcnow())
                archives = LifecycleArchiveStore(self.root_context, self._admission)
                try:
                    if request.action == "archive":
                        result = archives.archive(
                            payload["kind"],
                            payload["identity"],
                            expected_digest=payload["object_digest"],
                            archive_id=payload["archive_id"],
                            operation_id=operation.operation_id,
                        )
                    elif request.action == "restore":
                        result = archives.restore(
                            payload["archive_id"],
                            expected_digest=payload["object_digest"],
                            operation_id=operation.operation_id,
                        )
                    else:
                        reconciled = (operation.operation_id,) + tuple(prior.operation_id for prior in store.active_for_subject(subject) if prior.status is OperationStatus.INTERRUPTED and prior.action in {"lifecycle-archive", "lifecycle-restore", "lifecycle-recover"} and prior.payload.get("archive_id") == payload["archive_id"] and prior.payload.get("object_digest") == payload["object_digest"])
                        if payload["recovery_action"] == "abandon-unprepared":
                            result = archives.abandon_unprepared(
                                payload["kind"],
                                payload["identity"],
                                archive_id=payload["archive_id"],
                                expected_digest=payload["object_digest"],
                                reconciled_operations=reconciled,
                                review_digest=payload["review_digest"],
                                deployment_before=payload.get("deployment_before"),
                            )
                        elif payload["recovery_action"] == "abandon-unprepared-restore":
                            result = archives.reconcile_unprepared_restore(payload["archive_id"], expected_digest=payload["object_digest"], reconciled_operations=reconciled)
                        else:
                            result = archives.recover(payload["archive_id"], expected_digest=payload["object_digest"], reconciled_operations=reconciled)
                except Exception:
                    store.interrupt(operation.operation_id, now=_utcnow())
                    # Only a new explicit recovery may reconcile an uncertain transition.
                    raise
                store.complete(
                    operation.operation_id,
                    fence,
                    result=self._archive_view(result),
                    now=_utcnow(),
                )

            with self._settings_lock, self._lifecycle_lane(subject):
                operation = store.accept_request(
                    **arguments,
                    current_state_resolver=current_state,
                    start_worker=execute,
                    admission_held=True,
                )
                try:
                    return self._operation_view(store.get_operation(operation.operation_id))
                except OperationBusy:
                    # The transition is already durable; report the accepted record, never "nothing accepted".
                    return self._operation_view(operation)
        except ConfirmationExpired:
            raise ServiceError(410, "Confirmation expired; review lifecycle again.") from None
        except (ConfirmationRejected, StalePreview, ArchiveConflict, ArchiveNotFound):
            raise ServiceError(409, "Lifecycle review is stale or mismatched.", code="stale-preview") from None
        except OperationStartUncertain:
            raise ServiceError(409, "Lifecycle transition was interrupted; inspect operation and archive journal.", code="ownership-unknown") from None
        except OperationBusy:
            if existing is not None:
                raise ServiceError(409, "Operation storage is busy; this request was already recorded. Inspect its operation status.", code="writer-conflict") from None
            raise ServiceError(409, "Operation storage is busy; this request was not processed now. Retry later; if this request was submitted before, inspect its operation status first.", code="writer-conflict", retry_policy="retry-later") from None
        except HandoverError:
            raise ServiceError(423, "Root head inventory requires offline reconciliation; inspect lifecycle status before continuing.", code="reconciliation-required") from None
        except (ArchiveError, AdmissionError, OperationError, OSError, RootPathError, ValueError, KeyError):
            raise ServiceError(409, "Lifecycle admission is unavailable; inspect operation and archive status.", code="writer-conflict") from None

    def create_operation_preview(
        self,
        request: OperationPreviewRequest,
        *,
        operator_session: str | None,
    ) -> dict:
        self._require_writes()
        if not operator_session:
            raise ServiceError(403, "A server-owned operator session is required.")
        if not self.network_enabled:
            raise ServiceError(403, "Network capability is disabled for this server.")
        store = self._operation_store
        if store is None:
            raise ServiceError(409, "Durable operation storage is unavailable.")
        subject = self._validated_name(request.subject_id)
        self._guard_protected(subject)
        payload = request.payload
        if payload.fund != subject or payload.mandate_hash != request.expected_head:
            raise ServiceError(400, "Backtest subject and reviewed head do not match.")
        try:
            universe = normalize_universe(payload.universe)
        except (OSError, ValueError):
            raise ServiceError(400, "Backtest universe is invalid.") from None
        if universe != payload.universe:
            raise ServiceError(400, "Backtest universe must use canonical uppercase tickers.")
        spec = self._load_mandate_by_name(subject)
        if spec.name != subject or mandate_hash(spec) != request.expected_head:
            raise ServiceError(409, "Mandate changed; reload before previewing.", code="stale-preview", subject_id=subject, current_head=mandate_hash(spec))
        if spec.broker != "paper":
            raise ServiceError(403, "Only local-paper backtests are supported.", code="broker-not-web-supported")
        with self._settings_lock:
            self._ensure_settings_available()
            settings = self._runtime_settings
            if payload.provider != settings.data_provider or payload.model != settings.model:
                raise ServiceError(409, "Provider or model changed; reload before previewing.", code="stale-preview")
            data_target = ProviderTarget(
                kind="data",
                provider=settings.data_provider,
            )
            llm_target = ProviderTarget(
                kind="llm",
                provider=settings.llm_provider,
                model=settings.model,
                endpoint=settings.endpoint,
            )
            try:
                validate_llm_transport(llm_target)
                data_class = classify_provider(data_target)
                llm_class = classify_provider(
                    llm_target,
                    approved_local_models={settings.model},
                )
            except AuthorizationDenied:
                raise ServiceError(422, "Provider configuration has no guarded production transport.", code="readiness-denied") from None
            paid_targets = [
                (target, provider_class)
                for target, provider_class in (
                    (data_target, data_class),
                    (llm_target, llm_class),
                )
                if provider_class is ProviderClass.PAID_CLOUD
            ]
            if len(paid_targets) > 1:
                raise ServiceError(400, "Only one paid provider may be authorized per backtest.")
            if paid_targets and not payload.authorize_paid_provider:
                raise ServiceError(403, "Paid provider use requires explicit bounded authorization.")
            if not paid_targets and payload.authorize_paid_provider:
                raise ServiceError(400, "Paid authorization does not match the captured providers.")
            fd_pricing_attestation_required = any(target.kind == "data" and target.provider == "fd" for target, _provider_class in paid_targets)
            if fd_pricing_attestation_required and not payload.confirm_fd_self_service_pricing:
                raise ServiceError(403, "Financial Datasets dispatch requires explicit self-service pricing confirmation.")
            if payload.confirm_fd_self_service_pricing and not fd_pricing_attestation_required:
                raise ServiceError(400, "Financial Datasets pricing confirmation does not match the captured provider.")
            paid_cost_model_id = None
            if paid_targets:
                paid_target = paid_targets[0][0]
                paid_cost_model_id = cost_model_identity(paid_target)
                minimum_cost = minimum_attempt_cost(paid_target)
                if not has_verified_cost_model(paid_target) or minimum_cost is None:
                    raise ServiceError(422, "Paid provider has no verified upper-bound cost model.", code="readiness-denied")
                if Decimal(payload.paid_max_attempt_cost_usd) < minimum_cost:
                    raise ServiceError(422, "Per-attempt cost bound is below the provider's verified maximum.", code="readiness-denied")
            if payload.authorize_paid_provider and len(paid_targets) == 1 and paid_targets[0][0].kind == "llm" and self._custom_fund_factory:
                raise ServiceError(403, "Injected model providers cannot authorize paid dispatch.")
            if payload.authorize_paid_provider and len(paid_targets) == 1 and paid_targets[0][0].kind == "data" and self._data_client_factory is not None:
                raise ServiceError(403, "Injected data providers cannot authorize paid dispatch.")
            estimated_model_calls, estimated_llm_calls = _estimate_backtest_bounds(
                payload.start,
                payload.end,
                len(universe),
                spec,
                local_llm_fallback=llm_class is ProviderClass.LOCAL,
            )
            if estimated_model_calls > 1000:
                raise ServiceError(422, "Estimated model calls exceed the 1000-call bound.", code="readiness-denied")
            paid_call_bound = max(1, estimated_llm_calls) if paid_targets and paid_targets[0][0].kind == "llm" else min(10000, max(100, estimated_model_calls * 10))
            if paid_targets:
                if payload.paid_max_calls > paid_call_bound:
                    raise ServiceError(422, "Paid call bound exceeds the captured operation estimate.", code="readiness-denied")
            elif settings.llm_provider not in KEYLESS_PROVIDERS:
                raise ServiceError(403, "Paid model providers require explicit bounded authorization.")

            credential_versions = {}
            if paid_targets:
                target = paid_targets[0][0]
                provider_id = target.provider.casefold()
                status = next(
                    (value for name, value in self._credential_status_map().items() if name.casefold() == provider_id),
                    None,
                )
                if not status or not status["configured"]:
                    raise ServiceError(422, "Selected provider credential is not configured.", code="readiness-denied")
                credential_versions[provider_id] = status["version"]
            now = _utcnow()
            operation_payload = payload.model_dump(mode="json")
            operation_payload["cost_model_id"] = paid_cost_model_id
            operation_payload["cost_model_version"] = COST_MODEL_VERSION if paid_cost_model_id is not None else None
            try:
                capture = freeze_capture(
                    root=self.root_context,
                    subject_id=subject,
                    mandate_digest=request.expected_head,
                    universe=universe,
                    broker=spec.broker,
                    settings=settings,
                    credential_versions=credential_versions,
                    code_version=code_version(),
                    mandate_snapshot=spec.model_dump(mode="json"),
                )
                preview = store.create_preview(
                    action="backtest",
                    subject_id=subject,
                    expected_head=request.expected_head,
                    due_set=(),
                    capture=capture,
                    operator_session=operator_session,
                    payload=operation_payload,
                    now=now,
                    expires_at=now + timedelta(hours=1),
                )
            except OperationError:
                raise ServiceError(409, "Backtest preview could not be persisted.") from None
            self._cache_preview_capture(
                preview.preview_id,
                capture,
                preview.expires_at,
            )
        return {
            **preview.public_view(),
            "confirmation_token": preview.confirmation_token,
            "capture": capture.public_view(current_settings_version=settings.version),
            "estimate": {
                "maximum_model_calls": estimated_model_calls,
                "paid_provider": (paid_targets[0][0].provider if paid_targets else None),
                "maximum_paid_calls": payload.paid_max_calls if paid_targets else 0,
                "maximum_cost_usd": (None if self._custom_fund_factory or self._data_client_factory is not None else float(Decimal(payload.paid_max_cost_usd)) if paid_targets else 0.0),
                "maximum_attempt_cost_usd": (None if self._custom_fund_factory or self._data_client_factory is not None else float(Decimal(payload.paid_max_attempt_cost_usd)) if paid_targets else 0.0),
                "cost_model_id": paid_cost_model_id,
                "cost_model_version": (COST_MODEL_VERSION if paid_cost_model_id is not None else None),
                "cost_model": (cost_model_description(paid_targets[0][0]) if paid_targets else None),
                "market_data_provider": settings.data_provider,
            },
            "warnings": (["Injected test providers only; no live provider call is authorized."] if self._custom_fund_factory or self._data_client_factory is not None else [f"Each paid attempt reserves its declared cap before transport. Cost model: {cost_model_description(paid_targets[0][0])}"] if paid_targets else ["No paid provider calls are enabled."]),
        }

    def accept_operation(
        self,
        request: OperationAcceptRequest,
        *,
        operator_session: str | None,
    ) -> dict:
        self._require_writes()
        if not operator_session:
            raise ServiceError(403, "A server-owned operator session is required.")
        store = self._operation_store
        worker = self._operation_jobs
        if store is None or worker is None:
            raise ServiceError(409, "Durable operation worker is unavailable.")
        subject = self._validated_name(request.subject_id)
        self._guard_protected(subject)
        if request.action != "backtest" or request.payload.fund != subject or request.payload.mandate_hash != request.expected_head or request.due_set:
            raise ServiceError(400, "Backtest acceptance does not match the reviewed operation.")
        capture_id = self._preview_captures.get(request.preview_id)
        capture = self._captures.get(capture_id or "")
        if capture is None or capture.subject_id != subject:
            raise ServiceError(409, "Backtest preview is no longer available; review again.", code="stale-preview")
        payload = request.payload.model_dump(mode="json")

        def current_state() -> tuple[str | None, tuple[str, ...]]:
            current = self._load_mandate_by_name(subject)
            return mandate_hash(current), ()

        def start_worker(operation: OperationRecord) -> None:
            selected_capture = self._captures.get(operation.capture_id)
            if selected_capture is None or selected_capture.digest != operation.capture_digest:
                raise OperationError("captured operation inputs are unavailable")

            def work(progress, cancelled, apply_if_current):
                return self._execute_captured_backtest(
                    operation,
                    selected_capture,
                    progress,
                    cancelled,
                    apply_if_current,
                )

            worker.submit(operation, work, reservation=reservation)

        reservation = self._reserve_operation_slot(worker, subject_id=subject, request_id=request.request_id)
        try:
            operation = self._accept_backtest_locked(request, operator_session, store, subject, capture, payload, current_state, start_worker, reservation)
        finally:
            worker.release(reservation)
        return self._operation_view(operation)

    def _accept_backtest_locked(self, request, operator_session, store, subject, capture, payload, current_state, start_worker, reservation) -> OperationRecord:
        with self._settings_lock:
            self._ensure_settings_available()
            if self._runtime_settings.version != capture.settings_version or self._runtime_settings.model != capture.model or self._runtime_settings.data_provider != capture.data_provider:
                raise ServiceError(409, "Runtime settings changed; review the operation again.", code="stale-preview")
            for provider_id, version in capture.credential_versions.items():
                if self._credential_store is None:
                    raise ServiceError(409, "Captured credential storage is unavailable.")
                try:
                    current_version, _configured = self._credential_store.version(provider_id)
                except CredentialStoreError:
                    raise ServiceError(409, "Captured credential version is unavailable.") from None
                if current_version != version:
                    raise ServiceError(409, "Credential version changed; review the operation again.", code="stale-preview")
            try:
                operation = store.accept_request(
                    request_id=request.request_id,
                    action=request.action,
                    subject_id=subject,
                    preview_id=request.preview_id,
                    preview_digest=request.preview_digest,
                    confirmation_token=request.confirmation_token,
                    operator_session=operator_session,
                    expected_head=request.expected_head,
                    due_set=tuple(request.due_set),
                    payload=payload,
                    now=_utcnow(),
                    start_worker=start_worker,
                    current_state_resolver=current_state,
                    capacity=(_BACKTEST_POOL_ACTIONS, _BACKTEST_POOL_CAPACITY if reservation is not None else 0),
                )
            except ConfirmationExpired:
                raise ServiceError(410, "Confirmation expired; review the operation again.") from None
            except (ConfirmationRejected, StalePreview):
                raise ServiceError(409, "Reviewed operation is stale or no longer valid.", code="stale-preview") from None
            except OperationCapacityExceeded:
                raise _capacity_denied(subject, request.request_id) from None
            except OperationStartUncertain:
                raise ServiceError(409, "Operation start is uncertain; inspect its durable status.", code="ownership-unknown") from None
            except (OperationConflict, JobConflict):
                raise ServiceError(409, "Operation request conflicts with durable state.") from None
            except ServiceError:
                raise
            except OperationBusy:
                raise ServiceError(409, "Operation storage is busy; this request was not processed now. Retry later; if this request was submitted before, inspect its operation status first.", code="writer-conflict", retry_policy="retry-later") from None
            except OperationError:
                raise ServiceError(409, "Operation could not be accepted.") from None
        return operation

    def get_operation(self, operation_id: str) -> dict:
        store = self._operation_store
        if store is None:
            # Unavailable storage must not look like an unknown (forgettable) operation ID.
            raise ServiceError(503, "Operation status storage is unavailable; the operation outcome is unknown. Retry the read.", code="observation-conflict", subject_id=operation_id)
        try:
            operation = store.get_operation(operation_id)
        except OperationBusy:
            raise ServiceError(503, "Operation status is busy; retry the read.", code="observation-conflict") from None
        except OperationError as exc:
            status = 404 if "not found" in str(exc) else 409
            raise ServiceError(status, "Operation is unavailable.") from None
        return self._operation_view(operation)

    def get_operation_by_request(self, request_id: str) -> dict:
        store = self._operation_store
        if store is None:
            raise ServiceError(503, "Operation status storage is unavailable; the request outcome is unknown. Retry the read.", code="observation-conflict", request_id=request_id)
        try:
            operation = store.get_by_request(request_id)
        except OperationBusy:
            raise ServiceError(503, "Operation status is busy; retry the read.", code="observation-conflict", request_id=request_id) from None
        except OperationError:
            raise ServiceError(409, "Operation status is unavailable; the request outcome is unknown.", request_id=request_id) from None
        if operation is None:
            raise ServiceError(404, "No operation was found for this request; the outcome is still unknown.", code="not-found", request_id=request_id)
        return self._operation_view(operation)

    def list_operations(self, *, limit: int = 100) -> dict:
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ServiceError(400, "Operation page size is invalid.")
        store = self._operation_store
        if store is None:
            return {"items": []}
        try:
            operations = store.list_operations(limit=limit)
        except OperationBusy:
            raise ServiceError(503, "Operation history is busy; retry the read.", code="observation-conflict") from None
        except OperationError:
            raise ServiceError(409, "Operation history is unavailable.") from None
        return {"items": [self._operation_view(item) for item in operations]}

    def cancel_operation(
        self,
        operation_id: str,
        request: OperationCancelRequest,
    ) -> dict:
        self._require_writes()
        worker = self._operation_jobs
        if worker is None:
            raise ServiceError(409, "Durable operation worker is unavailable.")
        try:
            operation = worker.cancel(
                operation_id,
                request_id=request.request_id,
                now=_utcnow(),
            )
        except (JobConflict, OperationError):
            raise ServiceError(409, "Operation cannot be cancelled in its current state.") from None
        return self._operation_view(operation)

    def _execute_captured_backtest(
        self,
        operation: OperationRecord,
        capture: FrozenCapture,
        progress: Callable[[int], None],
        cancelled: Callable[[], bool],
        apply_if_current: Callable[[Callable[[], object]], object],
    ) -> dict[str, object]:
        try:
            request = BacktestRequest.model_validate(dict(operation.payload))
        except ValueError:
            raise OperationError("stored backtest request is invalid") from None
        if capture.mandate_snapshot is None:
            raise OperationError("captured mandate snapshot is unavailable")
        try:
            spec = FundSpec.model_validate(json.loads(capture.mandate_snapshot))
        except ValueError:
            raise OperationError("captured mandate snapshot is invalid") from None
        if spec.name != operation.subject_id or mandate_hash(spec) != capture.mandate_digest or spec.broker != "paper":
            raise OperationError("captured mandate is stale")
        model_calls, llm_calls = _estimate_backtest_bounds(
            request.start,
            request.end,
            len(capture.universe),
            spec,
            local_llm_fallback=False,
        )
        dispatch = self._backtest_dispatch(
            operation,
            capture,
            request,
            model_calls,
            llm_calls,
            cancelled,
        )
        if self._custom_fund_factory:
            fund = self._fund_factory(spec)
        else:
            fund = self._default_fund_factory(spec, capture, dispatch)

        def on_valuation(index: int, total: int, _value) -> None:
            if cancelled():
                raise JobCancelled()
            percent = int(100 * (index + 1) / total) if total > 0 else 0
            progress(min(99, max(0, percent)))

        data_key = self._captured_data_key(capture)
        with self._make_data_client(
            capture.data_provider,
            dispatch=dispatch,
            api_key=data_key,
        ) as data_client:
            result = backtest_fund(
                fund,
                request.start,
                request.end,
                data_client,
                list(capture.universe),
                on_valuation=on_valuation,
            )
        if cancelled():
            raise JobCancelled()
        path = apply_if_current(
            lambda: save_result(
                result,
                directory=self._safe_child("research"),
                admission=self._admission,
            )
        )
        if not isinstance(path, Path):
            raise OperationError("backtest report path is invalid")
        return {
            "report_id": path.name,
            "capture_id": capture.capture_id,
            "capture_digest": capture.digest,
        }

    def _backtest_dispatch(
        self,
        operation: OperationRecord,
        capture: FrozenCapture,
        request: BacktestRequest,
        model_calls: int,
        llm_calls: int,
        cancelled: Callable[[], bool],
    ) -> ProviderDispatch:
        if type(model_calls) is not int or model_calls <= 0 or type(llm_calls) is not int or not 0 <= llm_calls <= model_calls:
            raise OperationError("captured model-call estimate is invalid")
        breakpoints_target = KEN_FRENCH_BREAKPOINTS_TARGET
        data_target = ProviderTarget(
            kind="data",
            provider=capture.data_provider,
        )
        llm_target = ProviderTarget(
            kind="llm",
            provider=capture.llm_provider,
            model=capture.model,
            endpoint=capture.endpoint,
        )
        try:
            validate_llm_transport(llm_target)
            data_class = classify_provider(data_target)
            llm_class = classify_provider(
                llm_target,
                approved_local_models={capture.model},
            )
        except AuthorizationDenied:
            raise OperationError("captured provider transport is unavailable") from None
        paid_targets = [
            (target, provider_class)
            for target, provider_class in (
                (data_target, data_class),
                (llm_target, llm_class),
            )
            if provider_class is ProviderClass.PAID_CLOUD
        ]
        if len(paid_targets) > 1 or bool(paid_targets) != request.authorize_paid_provider:
            raise OperationError("captured paid authorization does not match providers")
        fd_pricing_attestation_required = any(target.kind == "data" and target.provider == "fd" for target, _provider_class in paid_targets)
        if request.confirm_fd_self_service_pricing != fd_pricing_attestation_required:
            raise OperationError("captured Financial Datasets pricing confirmation does not match")
        if paid_targets:
            paid_target = paid_targets[0][0]
            expected_cost_model = cost_model_identity(paid_target)
            minimum_cost = minimum_attempt_cost(paid_target)
            if not has_verified_cost_model(paid_target) or expected_cost_model is None or request.cost_model_id != expected_cost_model or request.cost_model_version != COST_MODEL_VERSION or minimum_cost is None or Decimal(request.paid_max_attempt_cost_usd) < minimum_cost:
                raise OperationError("captured paid cost model is unavailable")
        expiry = self._preview_expiries.get(operation.preview_id)
        if expiry is None:
            raise OperationError("operation deadline is unavailable")
        if llm_class is ProviderClass.LOCAL:
            model_calls += llm_calls
            llm_calls *= 2
        if model_calls > 1000:
            raise OperationError("captured model-call estimate exceeds its bound")
        free_call_bound = min(
            10000,
            max(100, model_calls + 100 * len(capture.universe), llm_calls),
        )
        per_target_bounds = {}
        upper_bound_costs = {}
        paid_cost = Decimal("0")
        if paid_targets:
            paid_target, _paid_class = paid_targets[0]
            paid_calls = request.paid_max_calls
            per_call = Decimal(request.paid_max_attempt_cost_usd)
            paid_cost = Decimal(request.paid_max_cost_usd)
            paid_call_bound = max(1, llm_calls) if paid_target.kind == "llm" else min(10000, max(100, model_calls * 10))
            if paid_calls is None or paid_calls > paid_call_bound or paid_cost <= 0 or per_call <= 0 or per_call > paid_cost:
                raise OperationError("captured paid budget is invalid")
            for target in (
                data_target,
                llm_target,
                breakpoints_target,
            ):
                if target.identity == paid_target.identity:
                    per_target_bounds[target.identity] = (
                        paid_calls,
                        paid_cost,
                        paid_calls,
                    )
                    upper_bound_costs[target.identity] = per_call
                elif target.identity == breakpoints_target.identity:
                    per_target_bounds[target.identity] = (
                        1,
                        Decimal("0"),
                        1,
                    )
                    upper_bound_costs[target.identity] = Decimal("0")
                else:
                    per_target_bounds[target.identity] = (
                        free_call_bound,
                        Decimal("0"),
                        free_call_bound,
                    )
                    upper_bound_costs[target.identity] = Decimal("0")
        else:
            for target in (
                data_target,
                llm_target,
                breakpoints_target,
            ):
                if target.identity == breakpoints_target.identity:
                    per_target_bounds[target.identity] = (
                        1,
                        Decimal("0"),
                        1,
                    )
                else:
                    per_target_bounds[target.identity] = (
                        free_call_bound,
                        Decimal("0"),
                        free_call_bound,
                    )
                upper_bound_costs[target.identity] = Decimal("0")
        if sum(bounds[0] for bounds in per_target_bounds.values()) > 20000:
            raise OperationError("operation transport-call bound exceeds its limit")
        try:
            return make_one_shot_dispatch(
                root_id=capture.root_id,
                subject_id=capture.subject_id,
                capture_digest=capture.digest,
                operation_id=operation.operation_id,
                operation_digest=operation.request_digest,
                expires_at=expiry,
                targets=(
                    data_target,
                    llm_target,
                    breakpoints_target,
                ),
                max_calls=sum(bounds[0] for bounds in per_target_bounds.values()),
                max_cost=paid_cost,
                max_resources=sum(bounds[2] for bounds in per_target_bounds.values()),
                upper_bound_costs=upper_bound_costs,
                per_target_bounds=per_target_bounds,
                approved_local_models={capture.model},
                clock=_utcnow,
                boundary_check=lambda: self._check_dispatch_fence(
                    operation,
                    capture,
                    cancelled,
                    paper=False,
                ),
            )
        except AuthorizationDenied:
            raise OperationError("provider authorization could not be established") from None

    def _captured_data_key(self, capture: FrozenCapture) -> str | None:
        if capture.data_provider not in {"fd"}:
            return None
        version = capture.credential_versions.get("fd")
        if version is None or self._credential_store is None:
            raise OperationError("captured data credential is unavailable")
        try:
            value = self._credential_store.read_version("fd", version)
        except CredentialStoreError:
            raise OperationError("captured data credential is unavailable") from None
        if not isinstance(value, str) or not value:
            raise OperationError("captured data credential is unavailable")
        return value

    def _cache_preview_capture(
        self,
        preview_id: str,
        capture: FrozenCapture,
        expires_at: datetime,
    ) -> None:
        while len(self._preview_captures) >= 1000:
            oldest_preview_id = next(iter(self._preview_captures))
            old_capture_id = self._preview_captures.pop(oldest_preview_id)
            self._preview_expiries.pop(oldest_preview_id, None)
            self._captures.pop(old_capture_id, None)
        self._preview_captures[preview_id] = capture.capture_id
        self._preview_expiries[preview_id] = expires_at
        self._captures[capture.capture_id] = capture

    @staticmethod
    def _operation_view(operation: OperationRecord) -> dict:
        result = None if operation.result is None else dict(operation.result)
        payload = dict(operation.payload)
        return {
            **operation.public_view(),
            "id": operation.operation_id,
            "fund": operation.subject_id,
            "provider": payload.get("provider"),
            "model": payload.get("model"),
            "report_id": result.get("report_id") if result else None,
            "error": result.get("error_code") if result else None,
            "cancel_requested": operation.status is OperationStatus.CANCEL_REQUESTED,
            "status_url": f"/api/operations/{operation.operation_id}",
        }

    def approve(self, name: str, request: ApprovalRequest) -> dict:
        self._require_writes()
        normalized = self._validated_name(name)
        self._guard_protected(normalized)
        with self._fund_lock(normalized):
            self._verify_root_inventory()
            _directory, deployed, ledger = self._paper_control_state(normalized)
            try:
                previous = ledger.approval_request_result(
                    request.request_id,
                    request.verdict,
                    request.decision_as_of,
                    request.source_record_hash,
                    "web",
                )
            except PaperRequestConflict:
                raise ServiceError(
                    409,
                    "Request ID was already used for a different or failed verdict.",
                    code="request-conflict",
                    request_id=request.request_id,
                ) from None
            except LedgerError:
                raise ServiceError(
                    423,
                    "Approval history or root inventory is unavailable.",
                    code="reconciliation-required",
                    request_id=request.request_id,
                ) from None
            if previous is not None:
                return {"verdict": previous["verdict"], "decision_as_of": previous["decision_as_of"], "saved": True}
            state, latest = self._replay_paper_state(deployed, ledger)
            if not deployed.spec.approval_required:
                raise ServiceError(409, "This fund does not require approval.")
            if state.halted is not None:
                raise ServiceError(423, "Halted funds cannot accept a verdict.", code="halted")
            pending = state.pending
            if pending is None or latest is None:
                raise ServiceError(409, "No pending decision is available.")
            if request.decision_as_of != pending.as_of or request.source_record_hash != latest.hash:
                raise ServiceError(409, "Pending decision changed; reload before submitting a verdict.", code="stale-preview")
            try:
                with paper_approval_transition(self._admission, normalized) as proof:
                    vote = ledger.set_approval(
                        request.verdict,
                        pending.as_of,
                        latest.hash,
                        "web",
                        request_id=request.request_id,
                        admission=proof,
                    )
            except ApprovalHalted:
                raise ServiceError(423, "Halted funds cannot accept a verdict.", code="halted") from None
            except ApprovalStale:
                raise ServiceError(409, "Pending decision changed; reload before submitting a verdict.", code="stale-preview") from None
            except ApprovalExpired:
                raise ServiceError(409, "This decision is already consumed or expired.") from None
            except PaperRequestConflict:
                raise ServiceError(
                    409,
                    "Request ID was already used for a different or failed verdict.",
                    code="request-conflict",
                    request_id=request.request_id,
                ) from None
            except LedgerInventoryCorrupt:
                raise ServiceError(423, "Paper state is invalid (LedgerError).", code="replay-corrupt") from None
            except LedgerError:
                raise ServiceError(423, "Approval history or root inventory is unavailable.", code="reconciliation-required") from None
            except AdmissionError:
                raise ServiceError(409, "Paper control admission is unavailable.") from None
            except HandoverError:
                raise ServiceError(423, "Offline paper ledger inventory changed; writes are denied.", code="reconciliation-required") from None
            except (OSError, ValueError) as exc:
                raise ServiceError(409, f"Verdict could not be saved ({type(exc).__name__}).") from None
        return {"verdict": vote["verdict"], "decision_as_of": vote["decision_as_of"], "saved": True}

    def halt_fund(self, name: str, reason: str, request_id: str) -> dict:
        if not self.allow_writes and not self.emergency_halt_available:
            self._require_writes()
        normalized = self._validated_name(name)
        self._guard_protected(normalized)
        if not isinstance(request_id, str) or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", request_id) is None:
            raise ServiceError(400, "Halt request identity is invalid.")
        if not isinstance(reason, str) or not reason.strip() or len(reason) > 240 or any(ord(char) < 32 or ord(char) == 127 for char in reason):
            raise ServiceError(400, "Halt reason is invalid.")
        with self._paper_halt_lane(normalized):
            _, _, ledger = self._paper_control_state(normalized)
            try:
                previous = ledger.control_request_result(request_id, "halt", {"reason": reason})
                if previous is not None:
                    return previous
            except PaperRequestConflict:
                raise ServiceError(
                    409,
                    "Request ID was already used for a different Halt request.",
                    code="request-conflict",
                    request_id=request_id,
                ) from None
            except LedgerError:
                previous = None
            try:
                ledger.halt(reason, request_id=request_id)
            except HaltAuditUnavailable:
                raise ServiceError(
                    423,
                    "Halt was applied, but its audit record is unavailable; reconciliation is required.",
                    code="reconciliation-required",
                    request_id=request_id,
                ) from None
            except PaperRequestConflict:
                raise ServiceError(
                    409,
                    "Request ID was already used for a different Halt request.",
                    code="request-conflict",
                    request_id=request_id,
                ) from None
            except PaperReconciliationRequired:
                raise ServiceError(
                    423,
                    "Halt request outcome is uncertain; inspect paper state.",
                    code="reconciliation-required",
                    request_id=request_id,
                ) from None
            except LedgerError:
                raise ServiceError(423, "Halt request history is unavailable.", code="reconciliation-required", request_id=request_id) from None
            except OSError as exc:
                raise ServiceError(409, f"Fund could not be halted ({type(exc).__name__}).", request_id=request_id) from None
        return {"name": normalized, "halted": True}

    def resume_fund(self, name: str, request: PaperResumeRequest | None = None) -> dict:
        if not self.emergency_halt_available:
            self._require_writes()
        normalized = self._validated_name(name)
        self._guard_protected(normalized)
        if request is not None and not isinstance(request, PaperResumeRequest):
            raise ServiceError(400, "Resume confirmation is invalid.")
        with self._fund_lock(normalized):
            with self._paper_control_lane(normalized):
                directory, deployed, ledger = self._paper_control_state(normalized)
                if request is not None:
                    try:
                        previous = ledger.resume_request_result(
                            request.request_id,
                            failure_id=request.failure_id,
                            preview_digest=request.preview_digest,
                            decision=request.decision,
                            operator="web",
                        )
                    except PaperRequestConflict:
                        raise ServiceError(
                            409,
                            "Request ID was already used for a different Resume request.",
                            code="request-conflict",
                            request_id=request.request_id,
                        ) from None
                    except PaperReconciliationRequired:
                        raise ServiceError(
                            423,
                            "Resume request outcome is uncertain; inspect paper state before further action.",
                            code="reconciliation-required",
                            request_id=request.request_id,
                        ) from None
                    except LedgerError:
                        raise ServiceError(
                            423,
                            "Resume request history is unavailable.",
                            code="reconciliation-required",
                            request_id=request.request_id,
                        ) from None
                    if previous is not None:
                        return previous
                self._safe_child("paper", normalized, "broker.json")
                state, latest = self._replay_paper_state(deployed, ledger)
                try:
                    halted = ledger.halted()
                    snapshot = build_reconciliation_snapshot(directory, deployed, ledger, state, latest)
                except (LedgerError, OSError, ValueError):
                    raise ServiceError(423, "Paper state is invalid (LedgerError).", code="replay-corrupt") from None
                preview = snapshot.preview
                if halted is not None and preview.required:
                    if request is None:
                        raise ServiceError(
                            423,
                            "Paper work remains halted until the current reconciliation preview is reviewed.",
                            code="reconciliation-required",
                        )
                    if request.failure_id != preview.failure_id or request.preview_digest != preview.preview_digest:
                        raise ServiceError(
                            409,
                            "Paper state changed after reconciliation review.",
                            code="stale-preview",
                            request_id=request.request_id,
                        )
                    if not preview.recoverable:
                        raise ServiceError(
                            423,
                            "The current local paper book does not match the replayed ledger; Halt remains active.",
                            code="reconciliation-required",
                            request_id=request.request_id,
                        )
                elif halted is not None and request is not None and request.failure_id is not None:
                    raise ServiceError(
                        409,
                        "No ambiguous tick failure requires this reconciliation confirmation.",
                        code="request-conflict",
                        request_id=request.request_id,
                    )
                try:
                    reconciliation = request.model_dump(mode="json") if request is not None and request.failure_id is not None else None
                    receipt_id = ledger.resume(
                        deployed.spec.capital,
                        approval_required=deployed.spec.approval_required,
                        reconciliation=reconciliation,
                        request_id=request.request_id if request is not None else None,
                        operator="web",
                    )
                except PaperRequestConflict:
                    raise ServiceError(
                        409,
                        "Request ID was already used for a different Resume request.",
                        code="request-conflict",
                        request_id=request.request_id if request is not None else None,
                    ) from None
                except PaperReconciliationRequired:
                    raise ServiceError(
                        423,
                        "Resume request outcome is uncertain; inspect paper state before further action.",
                        code="reconciliation-required",
                        request_id=request.request_id if request is not None else None,
                    ) from None
                except LedgerError as exc:
                    message = str(exc).casefold()
                    if "stale" in message:
                        raise ServiceError(
                            409,
                            "Paper state changed after reconciliation review.",
                            code="stale-preview",
                            request_id=request.request_id if request is not None else None,
                        ) from None
                    if any(term in message for term in ("reconciliation", "receipt", "reconcilable")):
                        raise ServiceError(
                            423,
                            "Paper work remains halted; reconciliation could not be verified.",
                            code="reconciliation-required",
                            request_id=request.request_id if request is not None else None,
                        ) from None
                    if "not halted" in message:
                        raise ServiceError(
                            409,
                            "Paper fund is not halted.",
                            code="request-conflict",
                            request_id=request.request_id if request is not None else None,
                        ) from None
                    raise ServiceError(423, "Paper state is invalid (LedgerError).", code="replay-corrupt") from None
                except AdmissionError:
                    raise ServiceError(409, "Paper control admission is unavailable.") from None
                except HandoverError:
                    raise ServiceError(423, "Offline paper ledger inventory changed; writes are denied.", code="reconciliation-required") from None
                except (OSError, ValueError):
                    raise ServiceError(
                        423,
                        "Resume outcome is uncertain; inspect paper state before any further action.",
                        code="reconciliation-required",
                        request_id=request.request_id if request is not None else None,
                    ) from None
        return {"name": normalized, "halted": False, "reconciliation_id": receipt_id}

    @contextmanager
    def _paper_halt_lane(self, name: str) -> Iterator[None]:
        try:
            with self._admission.halt_lane(name, timeout=0.1):
                yield
        except AdmissionError:
            raise ServiceError(409, "Paper Halt admission is unavailable.") from None

    @contextmanager
    def _paper_control_lane(
        self,
        name: str,
        *,
        verify_inventory: bool = True,
    ) -> Iterator[None]:
        if verify_inventory:
            self._verify_root_inventory()
        try:
            with self._admission.control_lane(name, timeout=0.1):
                yield
        except AdmissionError:
            raise ServiceError(409, "Paper control admission is unavailable.") from None

    @contextmanager
    def _paper_execution_lane(self, name: str) -> Iterator[None]:
        try:
            with self._admission.execution_lease(name, timeout=0.1):
                yield
        except AdmissionError:
            raise ServiceError(409, "Paper execution admission is unavailable.") from None

    @contextmanager
    def _paper_manual_lane(self, name: str) -> Iterator[None]:
        try:
            with self._admission.manual_session(name, timeout=0.1):
                yield
        except WriterConflict:
            raise ServiceError(409, "Paper session conflicts with another writer.", code="writer-conflict") from None
        except OwnershipUnknown:
            raise ServiceError(409, "Paper session ownership is unavailable.", code="ownership-unknown") from None
        except AdmissionError:
            raise ServiceError(409, "Paper session admission is unavailable.") from None

    @contextmanager
    def _paper_deployment_lane(self, name: str) -> Iterator[None]:
        try:
            with self._admission.deployment_lock(name, timeout=0.1):
                yield
        except AdmissionError:
            raise ServiceError(409, "Paper deployment admission is unavailable.") from None

    def _cached_valuation_view(self, name: str, expected_head: str | None) -> dict[str, object]:
        identity = _windows_name_key(name)
        with self._valuation_lock:
            estimate = self._valuation_estimates.get(identity)
            if estimate is not None and estimate.get("expected_head") == expected_head:
                return dict(estimate)
        return {
            "status": "unavailable",
            "value": None,
            "partial_estimate": None,
            "as_of": None,
            "provenance": None,
            "expected_head": expected_head,
            "recorded_nav": None,
            "coverage": {"total": 0, "quoted": 0, "usable": 0, "missing": 0, "stale": 0, "errors": 0},
            "quotes": [],
            "reason": ("Network capability is disabled." if not self.network_enabled else "No authorized estimate is available for this ledger head."),
        }

    def _paper_snapshot(self, deployed: DeployedFund, directory: Path, *, include_records: bool = False) -> dict:
        ledger = Ledger(directory)
        try:
            halted = ledger.halted()
            halt_state = "halted" if halted is not None else "clear"
        except (LedgerError, OSError, ValueError):
            halted = None
            halt_state = "unreadable"
        try:
            records: list[SessionRecord] = []
            state = ledger.replay(deployed.spec.capital, full=True, on_verified=records.append)
            ledger_status = {"ok": True, "error": None}
        except (LedgerError, OSError, ValueError) as exc:
            records = []
            state = None
            ledger_status = {"ok": False, "error": f"Ledger verification failed ({type(exc).__name__})."}
        latest = records[-1] if records else None
        positions = []
        if state is not None:
            for ticker, shares in sorted(state.positions.items()):
                mark = latest.marks.get(ticker) if latest is not None else None
                positions.append(
                    {
                        "ticker": ticker,
                        "shares": shares,
                        "mark": mark,
                        "market_value": shares * mark if mark is not None else None,
                    }
                )
        pending = state.pending if state is not None else None
        approval = None
        if state is not None:
            try:
                approval = ledger.observe_approval_for_display(state, approval_required=deployed.spec.approval_required)
            except PaperReconciliationRequired:
                ledger_status = {"ok": False, "error": "Paper work is in progress or requires reconciliation."}
            except (LedgerError, OSError, ValueError):
                ledger_status = {"ok": False, "error": "Approval history is unavailable."}
        try:
            next_run = following_session(deployed.spec, state.last_session if state is not None else None, _utcnow())
        except (OverflowError, ValueError):
            next_run = None
        curve = []
        baseline = records[0].benchmark_close if records else None
        for record in records:
            benchmark_nav = deployed.spec.capital * record.benchmark_close / baseline if baseline else None
            curve.append({"session": record.session, "nav": record.nav, "benchmark_nav": benchmark_nav})
        scorecard = None
        scorecard_error = None
        if records:
            try:
                scorecard = score(records).model_dump(mode="json")
            except ValueError as exc:
                scorecard_error = str(exc)
        elif ledger_status["ok"]:
            scorecard_error = "No recorded sessions to score."
        snapshot = {
            "name": deployed.name,
            "spec": deployed.spec.model_dump(mode="json"),
            "universe": deployed.universe,
            "broker": deployed.broker,
            "created": deployed.created,
            "cadence": deployed.spec.cadence_label,
            "last_session": latest.session if latest is not None else None,
            "last_record_hash": latest.hash if latest is not None else None,
            "nav": latest.nav if latest is not None else None,
            "cash": state.cash if state is not None and ledger_status["ok"] else None,
            "positions": positions,
            "curve": curve,
            "sessions": [self._session_summary(record) for record in records[-100:]],
            "pending": self._decision_summary(pending, latest.hash if latest else None) if pending is not None else None,
            "approval": approval,
            "next_run": next_run,
            "halted": halted,
            "halt_state": halt_state,
            "ledger": ledger_status,
            "runner": self._runner_state(deployed.name),
            "live_value": self._cached_valuation_view(
                deployed.name,
                latest.hash if latest is not None else None,
            ),
            "scorecard": scorecard,
            "scorecard_error": scorecard_error,
        }
        if include_records:
            snapshot["session_reports"] = [self._session_report(record) for record in records[-100:]]
        return snapshot

    def _paper_state(self, name: str, *, local_paper_only: bool = False):
        directory = self._safe_child("paper", name)
        if not directory.is_dir():
            raise ServiceError(404, "Paper fund not found.")
        try:
            deployed = load_deployed(directory)
            if local_paper_only and deployed.broker != "paper":
                raise ServiceError(403, "Web paper mutations require a local-paper deployment.", code="broker-not-web-supported")
            ledger = Ledger(directory)
            state, latest = self._replay_paper_state(deployed, ledger)
        except (LedgerError, OSError, ValueError) as exc:
            raise ServiceError(423, f"Paper state is invalid ({type(exc).__name__}).", code="replay-corrupt") from None
        return directory, deployed, ledger, state, latest

    def _replay_paper_state(self, deployed: DeployedFund, ledger: Ledger):
        latest = None

        def capture(record: SessionRecord) -> None:
            nonlocal latest
            latest = record

        try:
            state = ledger.replay(deployed.spec.capital, full=True, on_verified=capture)
        except (LedgerError, OSError, ValueError) as exc:
            raise ServiceError(423, f"Paper state is invalid ({type(exc).__name__}).", code="replay-corrupt") from None
        return state, latest

    def _require_paper_work_ready(self, deployed: DeployedFund, ledger: Ledger, state: FundState) -> None:
        try:
            with self._paper_control_lane(deployed.name, verify_inventory=False):
                if ledger.halted() is not None:
                    raise ServiceError(423, "Halted funds cannot accept a paper operation.", code="halted")
                try:
                    ledger.require_ready_for_work(state, approval_required=deployed.spec.approval_required)
                except PaperReconciliationRequired:
                    if self._admission.lane_is_held("runner", deployed.name) and self._admission.lane_is_held("execution", deployed.name):
                        ledger.halt("approval journal requires reconciliation")
                    raise
        except LedgerError:
            raise ServiceError(423, "Paper work requires reconciliation before it can continue.", code="reconciliation-required") from None

    def _paper_control_state(self, name: str) -> tuple[Path, DeployedFund, Ledger]:
        directory = self._safe_child("paper", name)
        if not directory.is_dir():
            raise ServiceError(404, "Paper fund not found.")
        self._safe_child("paper", name, "fund.yaml")
        self._safe_child("paper", name, "control.json")
        self._safe_child("paper", name, "events.jsonl")
        self._safe_child("paper", name, "pending-approval.json")
        try:
            deployed = load_deployed(directory)
        except (OSError, ValueError) as exc:
            raise ServiceError(409, f"Paper fund is invalid ({type(exc).__name__}).") from None
        if _windows_name_key(deployed.name) != _windows_name_key(name):
            raise ServiceError(409, "Paper deployment identity does not match its directory.")
        if deployed.broker != "paper":
            raise ServiceError(403, "Web paper mutations require a local-paper deployment.", code="broker-not-web-supported")
        return directory, deployed, Ledger(directory)

    def _session_report(self, record: SessionRecord) -> dict:
        executed = record.executed
        decision = record.decision
        executed_report = executed.model_dump(mode="json") if executed is not None else None
        if executed_report is not None:
            executed_report.update(
                {
                    "trading_cost": executed.trading_cost,
                    "traded_notional": executed.traded_notional,
                    "commission": executed.commission,
                    "slippage": executed.slippage,
                }
            )
        return {
            "session": record.session,
            "fund": record.fund,
            "hash": record.hash,
            "prev_hash": record.prev_hash,
            "code_version": record.code_version,
            "mandate_hash": record.mandate_hash,
            "nav": record.nav,
            "cash": record.cash,
            "positions": record.positions,
            "marks": record.marks,
            "benchmark": record.benchmark,
            "benchmark_close": record.benchmark_close,
            "rebalance": record.rebalance,
            "executed": executed_report,
            "proposed": {
                "as_of": decision.as_of,
                "universe": decision.universe,
                "target_weights": decision.target_weights,
                "final_weights": decision.final_weights,
                "clamps": [clamp.model_dump(mode="json") for clamp in decision.clamps],
                "risk": decision.spec.risk.model_dump(mode="json"),
                "risk_scale_factor": decision.risk_scale_factor,
                "strategies": [strategy.model_dump(mode="json") for strategy in decision.strategies],
            }
            if decision is not None
            else None,
        }

    def _session_summary(self, record: SessionRecord) -> dict:
        return {
            "session": record.session,
            "hash": record.hash,
            "nav": record.nav,
            "cash": record.cash,
            "rebalance": record.rebalance,
            "orders": len(record.executed.orders) if record.executed is not None else 0,
            "fills": len(record.executed.fills) if record.executed is not None else 0,
            "decision_as_of": record.decision.as_of if record.decision is not None else None,
        }

    def _decision_summary(self, decision, source_hash: str | None) -> dict:
        return {
            "decision_as_of": decision.as_of,
            "source_record_hash": source_hash,
            "universe": decision.universe,
            "target_weights": decision.target_weights,
            "final_weights": decision.final_weights,
            "strategies": [strategy.name for strategy in decision.strategies],
        }

    def _research_summary(self, report_id: str, result: FundBacktestResult) -> dict:
        return {
            "id": report_id,
            "fund": result.fund,
            "start": result.start,
            "end": result.end,
            "rebalance": result.rebalance,
            "benchmark": result.benchmark,
            "universe": result.universe,
            "metrics": result.metrics.model_dump(mode="json"),
            "session_count": len(result.records),
        }

    def _mandate_summary(self, spec: FundSpec, *, include_spec: bool = False) -> dict:
        data = {
            "name": spec.name,
            "mandate_hash": mandate_hash(spec),
            "strategies": [{"name": strategy.name, "title": strategy.title, "mode": strategy.blend.mode, "weight": strategy.weight} for strategy in spec.strategies],
            "cadence": spec.cadence_label,
            "capital": spec.capital,
            "benchmark": spec.benchmark,
            "approval_required": spec.approval_required,
            "broker": spec.broker,
            "agent_count": sum(len(strategy.models) for strategy in spec.strategies),
        }
        if include_spec:
            data["spec"] = spec.model_dump(mode="json")
        return data

    def _strategy_library(self) -> dict[str, StrategySpec]:
        strategy_dir = Path(__file__).resolve().parents[1] / "strategies"
        strategies = {}
        for path in sorted(strategy_dir.glob("*.yaml")):
            try:
                strategy = load_strategy(path)
            except (OSError, ValueError):
                continue
            strategies[strategy.name] = strategy
        return strategies

    def _validate_mandate_strategies(self, spec: FundSpec) -> None:
        library_names = set(self._strategy_library())
        for strategy in spec.strategies:
            if strategy.name != "custom" and strategy.name not in library_names:
                raise ServiceError(400, "Strategy must use a backend library entry or the custom identity.")

    def _validated_mandate(self, payload: dict) -> FundSpec:
        try:
            spec = FundSpec.model_validate(payload)
        except ValueError as exc:
            raise ServiceError(400, f"Mandate validation failed ({type(exc).__name__}).") from None
        _reject_secret_fields(spec.model_dump(mode="python"))
        self._validate_mandate_strategies(spec)
        return spec

    @contextmanager
    def _mandate_writer(self) -> Iterator[None]:
        lane = self._admission.registry_lock(timeout=0)
        try:
            lane.__enter__()
        except (AdmissionError, OSError, RootPathError):
            raise ServiceError(409, "Mandate writer admission is unavailable.") from None
        try:
            self._verify_root_inventory()
            yield
        finally:
            lane.__exit__(None, None, None)

    def _recheck_mandate_authority(self, *, renamed: bool = False) -> None:
        """Deny the next mandate effect when root ownership or write authority changed."""
        try:
            self._admission.require_root_owner()
        except (AdmissionError, OSError, RootPathError):
            if renamed:
                raise ServiceError(409, "Mandate writer authority changed after rename; the renamed file keeps its previous contents and needs reconciliation.") from None
            raise ServiceError(409, "Mandate writer authority changed; nothing was written.") from None

    def _assert_mandate_name_available(
        self,
        name: str,
        directory: Path,
        *,
        exclude_path: Path | None = None,
    ) -> None:
        self._assert_unique(
            directory,
            f"{name}.yaml",
            exclude_path=exclude_path,
        )
        try:
            self._load_mandate_by_name(name)
        except ServiceError as exc:
            if exc.status_code != 404:
                raise
        else:
            raise ServiceError(409, "A mandate with this name already exists.")

    def _default_fund_factory(
        self,
        spec: FundSpec,
        capture: FrozenCapture | None = None,
        dispatch: ProviderDispatch | None = None,
    ) -> Fund:
        cache = PromptCache(self._safe_child("cache", "llm"))
        if capture is None:
            return Fund(spec, blind=True, cache=cache)
        if not isinstance(dispatch, ProviderDispatch):
            raise AuthorizationDenied("captured LLM dispatch authorization is required")

        def llm_factory(_model_spec):
            provider_key = capture.llm_provider.casefold()
            version = capture.credential_versions.get(provider_key, 0)
            api_key = self._credential_store.read_version(capture.llm_provider, version) if capture.llm_provider not in KEYLESS_PROVIDERS and self._credential_store is not None else None
            return make_llm(
                model=capture.model,
                timeout=capture.timeout_seconds,
                max_tokens=int(capture.parameters.get("max_tokens", 4096)),
                temperature=capture.parameters.get("temperature"),
                top_p=capture.parameters.get("top_p"),
                context_size=(int(capture.parameters.get("context_size", 8192)) if capture.llm_provider == "Ollama" else None),
                api_key=api_key,
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

    @contextmanager
    def _make_data_client(
        self,
        provider: str | None = None,
        *,
        dispatch: ProviderDispatch | None = None,
        api_key: str | None = None,
    ) -> Iterator[object]:
        if not self.network_enabled or not isinstance(dispatch, ProviderDispatch):
            raise AuthorizationDenied("provider operation authorization is required")
        selected_provider = data_provider(self._runtime_settings.data_provider if provider is None else provider)
        if self._data_client_factory is not None:
            if not isinstance(dispatch, ProviderDispatch):
                raise AuthorizationDenied("provider operation authorization is required")
            target = ProviderTarget(kind="data", provider=selected_provider)
            url = "https://api.financialdatasets.ai/" if selected_provider == "fd" else "https://query1.finance.yahoo.com/"
            with self._data_client_factory() as client:
                yield _DispatchGuardedInjectedDataClient(
                    client,
                    dispatch,
                    target,
                    url,
                )
            return
        cache = self._ensure_dir("cache")
        with make_data_client(
            provider=selected_provider,
            dispatch=dispatch,
            api_key=api_key,
        ) as client:
            yield CachedDataClient(client, cache_dir=cache)

    def _runner_state(self, name: str) -> dict:
        try:
            return self._runner_manager.status(name)
        except OwnedRunnerError:
            return {
                "status": "unknown",
                "available": False,
                "reason": "Runner ownership is not verified.",
            }

    def _safe_child(self, *parts: str) -> Path:
        try:
            self.root_context.revalidate()
        except RootPathError:
            raise ServiceError(409, "Configured data root is no longer available.") from None
        candidate = self.root
        for part in parts:
            if not isinstance(part, str) or part in {"", ".", ".."} or Path(part).is_absolute():
                raise ServiceError(400, "Storage path is invalid.")
            candidate = candidate / part
            if _is_reparse_point(candidate):
                raise ServiceError(403, "Storage path contains a symlink or reparse point.", code="protected-root")
        resolved = candidate.resolve(strict=False)
        if resolved != self.root and self.root not in resolved.parents:
            raise ServiceError(403, "Storage path escapes the configured data root.", code="protected-root")
        return resolved

    def _ensure_dir(self, *parts: str) -> Path:
        self._require_writes()
        self._safe_child(*parts)
        try:
            self.root_context.mkdir(Path(*parts).as_posix(), parents=True)
        except (OSError, RootPathError):
            raise ServiceError(409, "Storage directory could not be created.") from None
        return self._safe_child(*parts)

    def _assert_unique(
        self,
        directory: Path,
        filename: str,
        *,
        exclude_path: Path | None = None,
    ) -> None:
        candidate = Path(filename)
        excluded = os.path.normcase(os.path.abspath(os.fspath(exclude_path))) if exclude_path is not None else None
        for existing in directory.iterdir():
            if excluded is not None and os.path.normcase(os.path.abspath(os.fspath(existing))) == excluded:
                continue
            if _windows_name_key(existing.name) == _windows_name_key(candidate.name):
                raise ServiceError(409, "A resource with this name already exists.")

    def _validated_name(self, name: str) -> str:
        try:
            return validate_fund_name(name)
        except ValueError:
            raise ServiceError(400, "Fund name is invalid.") from None

    def _load_mandate_by_name(self, name: str) -> FundSpec:
        return self._load_mandate_entry(name)[0]

    def _load_mandate_entry(self, name: str) -> tuple[FundSpec, Path]:
        directory = self._safe_child("mandates")
        if not directory.exists():
            raise ServiceError(404, "Mandate not found.")
        if not directory.is_dir():
            raise ServiceError(409, "Mandate storage is not a directory.")
        name_key = _windows_name_key(name)
        matches: list[tuple[FundSpec, Path]] = []
        invalid_type = None
        try:
            paths = sorted(directory.iterdir(), key=lambda entry: entry.name.casefold())
        except OSError as exc:
            raise ServiceError(409, f"Mandate storage could not be read ({type(exc).__name__}).") from None
        for path in paths:
            if path.suffix.lower() not in {".yaml", ".yml"}:
                continue
            try:
                safe_path = self._safe_child("mandates", path.name)
                if not safe_path.is_file():
                    continue
                spec = load_spec(safe_path)
            except ServiceError:
                if _windows_name_key(path.stem) == name_key:
                    raise
                continue
            except (OSError, ValueError) as exc:
                if _windows_name_key(path.stem) == name_key:
                    invalid_type = type(exc).__name__
                continue
            if _windows_name_key(spec.name) == name_key:
                matches.append((spec, safe_path))
        if len(matches) > 1:
            raise ServiceError(409, "Multiple mandates share this name.")
        if matches:
            return matches[0]
        if invalid_type is not None:
            raise ServiceError(422, f"Mandate is invalid ({invalid_type}).", code="readiness-denied")
        raise ServiceError(404, "Mandate not found.")

    def _guard_protected(self, name: str) -> None:
        if _windows_name_key(name) in {_windows_name_key(entry) for entry in PROTECTED_NAMES}:
            raise ServiceError(403, "Protected fund names cannot be modified by the web UI.", code="protected-root")

    def _require_writes(self) -> None:
        if not self.allow_writes:
            raise ServiceError(403, "Write capability is disabled for this server.")
        if not self._refresh_write_authority():
            raise ServiceError(403, "Offline root enrollment is unavailable." if self.write_authority == "unavailable" else "Root write authority is unavailable; the root is read-only.")

    def _refresh_write_authority(self) -> bool:
        """Re-classify the root; revoke capabilities unless current authority permits writes.

        Ordinary writes need an enrolled root. A service that started in drift keeps its
        emergency halt while authority remains valid; mid-session drift revokes all.
        """
        try:
            status = enrollment_status(self.root_context)
        except Exception:
            status = {"state": "unavailable", "reason": "handover-unavailable"}
        authority = write_authority(self.root_context) if status["state"] in {"enrolled", "drift"} else None
        authorized = authority is not None and has_write_authority(authority)
        if authorized and status["state"] == "enrolled":
            return True
        if authorized and not self.allow_writes and self.emergency_halt_available:
            return False
        self.allow_writes = False
        self.emergency_halt_available = False
        self.network_enabled = False
        self.enrollment_state = status["state"]
        self.write_unavailable_reason = (authority["reason"] if authority is not None else status["reason"]) or "handover-unavailable"
        self.write_authority = authority["authority"] if authority is not None else "unavailable"
        if self._owner_lease is not None:
            self._owner_lease.close()
            self._owner_lease = None
        self._admission = AdmissionCoordinator(self.root_context)
        return False

    def _credential_status_map(self) -> dict[str, dict[str, int | bool]]:
        provider_ids = {provider.casefold() for provider in (*PROVIDER_ENV_VARS, *DATA_PROVIDER_ENV_VARS)}
        if self._credential_store is None:
            return {provider: {"version": 0, "configured": False} for provider in provider_ids}
        try:
            return self._credential_store.status()
        except CredentialStoreError:
            self._settings_error = "private-credentials-unavailable"
            return {provider: {"version": 0, "configured": False} for provider in provider_ids}

    def _active_operation_captures(self) -> list[tuple[object, FrozenCapture | None]] | None:
        if self._operation_store is None:
            return None
        try:
            operations = self._operation_store.list_operations(limit=100)
        except OperationError:
            return None
        return [
            (operation, self._captures.get(operation.capture_id))
            for operation in operations
            if operation.status
            in {
                OperationStatus.ACCEPTED,
                OperationStatus.RUNNING,
                OperationStatus.CANCEL_REQUESTED,
            }
        ]

    def _active_capture_views(
        self,
        items: list[tuple[object, FrozenCapture | None]] | None,
        effective: RuntimeSettings,
    ) -> tuple[list[dict[str, object]], bool]:
        if items is None:
            return [], False
        active = []
        for operation, capture in items:
            view = capture.public_view(current_settings_version=effective.version) if capture is not None else {}
            endpoint = view.get("endpoint")
            active.append(
                {
                    "capture_id": operation.capture_id,
                    "subject_id": operation.subject_id,
                    "status": operation.status.value,
                    "capture_details_available": capture is not None,
                    "settings_version": view.get("settings_version"),
                    "data_provider": view.get(
                        "data_provider",
                        operation.payload.get("provider"),
                    ),
                    "llm_provider": view.get("llm_provider"),
                    "model": view.get("model", operation.payload.get("model")),
                    "endpoint": endpoint,
                    "restart_needed": view.get("restart_needed"),
                }
            )
        return active, True

    def _configuration_view(
        self,
        effective: RuntimeSettings,
        items: list[tuple[object, FrozenCapture | None]] | None,
    ) -> dict[str, object]:
        stored: RuntimeSettings | None = None
        if self._settings_error is None:
            try:
                stored = load_settings(self.root_context, admission=self._admission)
            except (ConfigurationError, OSError, RootPathError):
                stored = None
        view = describe_configuration(
            stored=stored,
            effective=effective,
            startup_version=self._startup_settings_version,
        )
        stale = 0
        credentials: list[dict[str, object]] = []
        for operation, capture in items or []:
            if capture is None:
                continue
            if capture.settings_version != effective.version:
                stale += 1
            for provider_id, version in sorted(capture.credential_versions.items()):
                current: int | None = None
                configured: bool | None = None
                retained: bool | None = None
                if self._credential_store is not None:
                    try:
                        current, configured = self._credential_store.version(provider_id)
                        retained = self._credential_store.retains_version(provider_id, version) if version >= 1 else False
                    except CredentialStoreError:
                        current, configured, retained = None, None, None
                if current is None:
                    state = "unavailable"
                elif version < 1:
                    state = "not-captured"
                elif current == version and configured:
                    state = "current"
                elif not configured:
                    state = "deleted-after-capture"
                else:
                    state = "superseded"
                credentials.append(
                    {
                        "capture_id": operation.capture_id,
                        "subject_id": operation.subject_id,
                        "status": operation.status.value,
                        "provider": provider_id,
                        "captured_version": version,
                        "current_version": current,
                        "configured": configured,
                        "captured_version_retained": retained,
                        "state": state,
                    }
                )
        reasons = list(view["restart_reasons"])
        if stale:
            # Captured work is fenced, never hot-swapped: its next dispatch or
            # start is denied, so it must be restarted (re-reviewed) to apply.
            reasons.append("active-capture-stale")
        runners = self._runner_capture_summary(effective)
        if runners["stale_count"] or runners["stale_unverified_count"]:
            # Owned runners do not re-check settings after launch; they keep
            # their captured version until stopped and started again.
            reasons.append("owned-runner-stale")
        if runners["ownership_unknown_count"]:
            # Runner owner is not verified in this server process, so its
            # captured version is unknown and it cannot be stopped from here.
            reasons.append("owned-runner-unverified")
        stored_values = None
        if stored is not None and stored.version == effective.version:
            stored_values = stored.to_mapping()
        return {
            **view,
            "restart_required": bool(reasons),
            "restart_reasons": reasons,
            "stored_values": stored_values,
            "active": {
                "available": items is not None,
                "count": len(items or []),
                "stale_count": stale,
            },
            "runners": runners,
            "credential_captures": credentials,
            "policy": {
                "hot_reload": False,
                "environment_read_at": "startup",
                "process_environment_credentials_used": False,
                "restart_action": "manual",
            },
        }

    def _runner_capture_summary(self, effective: RuntimeSettings) -> dict[str, object]:
        """Count launched owned runners whose capture predates ``effective``.

        Uses only the latest completed runner start per fund and the public
        runner status; nothing is started, stopped or reloaded here.
        """
        if self._operation_store is None:
            return {"available": False, "count": 0, "stale_count": 0, "stale_unverified_count": 0, "ownership_unknown_count": 0}
        try:
            operations = self._operation_store.list_operations(limit=100)
        except OperationError:
            return {"available": False, "count": 0, "stale_count": 0, "stale_unverified_count": 0, "ownership_unknown_count": 0}
        count = stale_count = unverified = ownership_unknown = 0
        seen: set[str] = set()
        for operation in operations:
            if operation.action != "paper-runner-start" or operation.status != OperationStatus.COMPLETED:
                continue
            if operation.subject_id in seen:
                continue
            seen.add(operation.subject_id)
            status = self._runner_state(operation.subject_id).get("status")
            if status == "unknown":
                # Not owned by this server process (e.g. after a restart): it
                # cannot be stopped here and needs offline recovery.
                ownership_unknown += 1
                continue
            if status not in {"running", "stopping"}:
                continue
            count += 1
            capture = self._captures.get(operation.capture_id)
            if capture is None:
                unverified += 1
            elif capture.settings_version != effective.version:
                stale_count += 1
        return {
            "available": True,
            "count": count,
            "stale_count": stale_count,
            "stale_unverified_count": unverified,
            "ownership_unknown_count": ownership_unknown,
        }

    def _ensure_settings_available(self) -> None:
        if self._settings_error is not None:
            raise ServiceError(409, "Private runtime settings are unavailable.")

    def _persist_runtime_settings(
        self,
        values: dict[str, object],
        *,
        expected_version: int,
    ) -> tuple[RuntimeSettings, RuntimeSettings]:
        with self._settings_lock:
            self._ensure_settings_available()
            try:
                RuntimeSettings(**{**self._runtime_settings.to_mapping(), **values})
            except ConfigurationError:
                raise ServiceError(400, "Runtime settings are invalid.") from None
            try:
                persisted = save_settings(
                    self.root_context,
                    values,
                    expected_version=expected_version,
                    admission=self._admission,
                )
            except SettingsConflict:
                raise ServiceError(409, "Runtime settings changed; reload before saving.", code="stale-preview") from None
            except ConfigurationError:
                raise ServiceError(409, "Runtime settings could not be saved.") from None
            except (OSError, RootPathError):
                raise ServiceError(409, "Runtime settings could not be saved.") from None
            try:
                effective = resolve_settings(
                    self.root_context,
                    admission=self._admission,
                    environment=self._environment_settings,
                    persisted=persisted,
                )
            except ConfigurationError:
                self._settings_error = "private-settings-unavailable"
                raise ServiceError(409, "Effective runtime settings are unavailable.") from None
            self._runtime_settings = effective
            return persisted, effective

    def _fund_lock(self, name: str) -> threading.RLock:
        key = _windows_name_key(name)
        with self._locks_guard:
            return self._locks.setdefault(key, threading.RLock())


def _is_reparse_point(path: Path) -> bool:
    try:
        info = path.lstat()
    except FileNotFoundError:
        return False
    attributes = getattr(info, "st_file_attributes", 0)
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return stat.S_ISLNK(info.st_mode) or bool(attributes & reparse_flag)


def _windows_name_key(name: str) -> str:
    return unicodedata.normalize("NFKC", name).rstrip(" .").casefold()


def _public_settings(settings: RuntimeSettings) -> dict[str, object]:
    """Public settings view; override-sourced endpoint origins are never echoed."""
    public = settings.public_view()
    redacted = settings.provenance["endpoint"] in {"environment", "launch"}
    if redacted:
        public["endpoint"] = None
    public["endpoint_redacted"] = redacted
    return public


def _credential_provider(value: str) -> str:
    if not isinstance(value, str):
        raise ServiceError(400, "Provider is not an allowlisted credential provider.")
    provider = next(
        (name for name in (*PROVIDER_ENV_VARS, *DATA_PROVIDER_ENV_VARS) if name.casefold() == value.casefold()),
        None,
    )
    if provider is None:
        raise ServiceError(400, "Provider is not an allowlisted credential provider.")
    return provider


def _supported_model_providers() -> dict[str, str]:
    return {model_id: provider for _label, model_id, provider in load_api_models() if is_supported(provider)}


def _is_loopback_endpoint(value: str | None) -> bool:
    if value is None:
        return True
    try:
        parts = urlsplit(value)
        if parts.scheme != "http" or parts.hostname is None:
            return False
        return ip_address(parts.hostname).is_loopback
    except ValueError:
        return False


def _estimate_backtest_bounds(
    start_text: str,
    end_text: str,
    universe_size: int,
    spec: FundSpec,
    *,
    local_llm_fallback: bool,
) -> tuple[int, int]:
    try:
        start = date.fromisoformat(start_text)
        end = date.fromisoformat(end_text)
    except (TypeError, ValueError):
        raise ServiceError(400, "Backtest dates are invalid.") from None
    if end < start or (end - start).days > 730:
        raise ServiceError(400, "Backtest date range exceeds its bound.")
    if type(universe_size) is not int or not 1 <= universe_size <= 20:
        raise ServiceError(400, "Backtest universe exceeds its bound.")
    if not isinstance(spec, FundSpec) or type(local_llm_fallback) is not bool:
        raise ServiceError(400, "Backtest model-call estimate is invalid.")
    weekdays = sum(1 for offset in range((end - start).days + 1) if (start + timedelta(days=offset)).weekday() < 5)
    try:
        model_calls, llm_calls = model_call_bounds(
            spec,
            local_llm_fallback=local_llm_fallback,
        )
    except ValueError:
        raise ServiceError(400, "Backtest model-call estimate is invalid.") from None
    return weekdays * universe_size * model_calls, weekdays * universe_size * llm_calls


def _estimate_paper_model_calls(spec: FundSpec, universe_size: int) -> int:
    if not isinstance(spec, FundSpec) or type(universe_size) is not int or not 1 <= universe_size <= 25:
        raise ServiceError(400, "Paper model-call estimate is invalid.")
    try:
        model_calls, _llm_calls = model_call_bounds(
            spec,
            local_llm_fallback=True,
        )
    except ValueError:
        raise ServiceError(400, "Paper model-call estimate is invalid.") from None
    calls = universe_size * model_calls * 2
    if type(calls) is not int or not 1 <= calls <= 1000:
        raise ServiceError(422, "Paper model-call estimate exceeds the 1000-call bound.", code="readiness-denied")
    return calls


def _runner_limits(
    spec: FundSpec,
    *,
    universe_size: int,
    max_sessions: int,
    max_runtime_minutes: int,
) -> tuple[int, int]:
    if not isinstance(spec, FundSpec) or type(universe_size) is not int or not 1 <= universe_size <= 25 or type(max_sessions) is not int or not 1 <= max_sessions <= 100 or type(max_runtime_minutes) is not int or not 1 <= max_runtime_minutes <= 1440:
        raise ServiceError(400, "Finite runner bounds are invalid.")
    model_calls = _estimate_paper_model_calls(spec, universe_size)
    calls_per_session = model_calls + 40 * universe_size + 20
    max_calls = 2 * max_runtime_minutes + 1 + max_sessions * calls_per_session
    max_resources = max_calls
    if not 1 <= max_calls <= 1_000_000 or not 1 <= max_resources <= 1_000_000:
        raise ServiceError(422, "Finite runner resource estimate exceeds its bound.", code="readiness-denied")
    return max_calls, max_resources


def _reject_secret_fields(value) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if _SECRET_FIELD.search(str(key)):
                raise ServiceError(400, "Mandates cannot store credential-like fields.")
            _reject_secret_fields(child)
    elif isinstance(value, list):
        for child in value:
            _reject_secret_fields(child)


def _utcnow():
    from datetime import datetime, timezone

    return datetime.now(timezone.utc)
