"""Thin adapters over validated fund, ledger, research and key services."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import threading
import unicodedata
from contextlib import contextmanager
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
from hedge_fund.paper.ledger import Ledger, LedgerError
from hedge_fund.paper.tick import following_session, next_session, tick
from hedge_fund.pipeline.session import code_version, mandate_hash, SessionRecord
from hedge_fund.runtime.admission import (
    AdmissionCoordinator,
    AdmissionError,
    RootOwnerLease,
)
from hedge_fund.runtime.capture import freeze_capture, FrozenCapture
from hedge_fund.runtime.configuration import (
    ConfigurationError,
    environment_settings,
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
    record_ledger_head,
    verify_root_inventory,
)
from hedge_fund.runtime.operations import (
    ConfirmationExpired,
    ConfirmationRejected,
    OperationBusy,
    OperationConflict,
    OperationError,
    OperationRecord,
    OperationStartUncertain,
    OperationStatus,
    OperationStore,
    StalePreview,
)
from hedge_fund.runtime.owned_runner import OwnedRunnerError, OwnedRunnerManager
from hedge_fund.runtime.policy import (
    AuthorizationDenied,
    classify_provider,
    KEN_FRENCH_BREAKPOINTS_TARGET,
    ProviderClass,
    ProviderTarget,
)
from hedge_fund.runtime.root import RootContext, RootPathError
from hedge_fund.scorecard import score
from hedge_fund.web.jobs import JobCancelled, JobConflict, OperationJobRegistry
from hedge_fund.web.schemas import (
    ApprovalRequest,
    BacktestRequest,
    CredentialRequest,
    DeployRequest,
    error_code_for,
    ModelRequest,
    OperationAcceptRequest,
    OperationCancelRequest,
    OperationPreviewRequest,
    PaperTickAcceptRequest,
    PaperTickPreviewRequest,
    RunnerPreviewRequest,
    RunnerStartAcceptRequest,
    RuntimeSettingsRequest,
    ValuationRefreshRequest,
)
from hedge_fund.web.valuation import estimate_valuation, MAX_VALUATION_POSITIONS

PROTECTED_NAMES = ("watchtower", "watchtower-weekly", "umbrella")
_REPORT_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,180}\.json$")
_SESSION_CURSOR = re.compile(r"\d{4}-\d{2}-\d{2}(?:T\d{2}:\d{2}:\d{2})?$")
_SECRET_FIELD = re.compile(r"(?:api.?key|secret|token|password|credential|authorization)", re.IGNORECASE)


class ServiceError(RuntimeError):
    def __init__(self, status_code: int, detail: str, *, code: str | None = None) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail
        self.code = error_code_for(status_code, code)


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
        self._admission = AdmissionCoordinator(root_context)
        self.allow_writes = False
        self.emergency_halt_available = False
        self.write_unavailable_reason: str | None = status["reason"]
        if not allow_writes and status["state"] == "enrolled":
            self.write_unavailable_reason = "write-capability-disabled"
        if allow_writes and status["state"] in {"enrolled", "drift"}:
            owner = None
            try:
                owner = RootOwnerLease.acquire(root_context)
                admission = AdmissionCoordinator(root_context, owner_lease=owner)
                self._owner_lease = owner
                self._admission = admission
                self.allow_writes = status["state"] == "enrolled"
                self.emergency_halt_available = status["state"] == "drift"
            except (AdmissionError, OSError, RootPathError, ValueError):
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
        try:
            self._environment_settings = environment_settings()
            self._runtime_settings = resolve_settings(
                root_context,
                admission=self._admission,
                environment=self._environment_settings,
            )
        except ConfigurationError:
            self._settings_error = "private-settings-unavailable"
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
                        max_active=1,
                    )
                    paper_operation_jobs = OperationJobRegistry(
                        self._operation_store,
                        max_active=2,
                    )
                    try:
                        operation_jobs.recover_unfinished()
                    except Exception:
                        operation_jobs.close()
                        paper_operation_jobs.close()
                        raise
                    self._operation_jobs = operation_jobs
                    self._paper_operation_jobs = paper_operation_jobs
            except (AdmissionError, JobConflict, OperationError, OSError, ValueError):
                self._operation_store = None
                if self.allow_writes:
                    self.allow_writes = False
                    self.network_enabled = False
                    self.write_unavailable_reason = "operation-recovery-unavailable"
                    if self._owner_lease is not None:
                        self._owner_lease.close()
                        self._owner_lease = None
                    self._admission = AdmissionCoordinator(root_context)
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
                    if self._owner_lease is not None:
                        self._owner_lease.close()
                        self._owner_lease = None
                finally:
                    if self._owns_root_context:
                        self.root_context.close()

    def capabilities(self, mutation_token: str | None) -> dict:
        return {
            "mode": "demo" if self.demo else "live",
            "read_only": not self.allow_writes,
            "writes": self.allow_writes,
            "network": self.network_enabled,
            "local_operator_only": True,
            "csrf_authenticates_users": False,
            "container_observer": self.container_observer,
            "enrollment_state": self.enrollment_state,
            "write_unavailable_reason": self.write_unavailable_reason,
            "protected_names": list(PROTECTED_NAMES),
            "mutation_token": mutation_token if self.allow_writes or self.emergency_halt_available else None,
            "deferred_actions": {
                "runner": ("Finite local-paper runner start and stop require an explicit reviewed operation." if self.allow_writes else "Runner controls are unavailable because root writes are disabled."),
                "manual_run": ("One-session local-paper ticks require a reviewed head and due-set confirmation." if self.allow_writes and self.network_enabled else "Manual ticks are unavailable because writes or network capability are disabled."),
                "delete": "Fund and report deletion is not available.",
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
                    raise ServiceError(422, f"Mandate could not be saved ({type(exc).__name__}).") from None
        return self._mandate_summary(spec, include_spec=True)

    def update_mandate(self, name: str, payload: dict, *, expected_hash: str) -> dict:
        self._require_writes()
        normalized = self._validated_name(name)
        self._guard_protected(normalized)
        if not isinstance(expected_hash, str) or re.fullmatch(r"[0-9a-f]{64}", expected_hash) is None:
            raise ServiceError(422, "Mandate revision is invalid.")
        spec = self._validated_mandate(payload)
        target = self._validated_name(spec.name)
        self._guard_protected(target)
        with self._mandate_writer():
            with self._fund_lock(normalized):
                current, path = self._load_mandate_entry(normalized)
                if mandate_hash(current) != expected_hash:
                    raise ServiceError(409, "Mandate changed; reload before editing.", code="stale-preview")
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
            raise ServiceError(422, "Mandate revision is invalid.")
        spec = self._validated_mandate(payload)
        target = self._validated_name(spec.name)
        self._guard_protected(target)
        if _windows_name_key(target) == _windows_name_key(source):
            raise ServiceError(422, "A clone must use a distinct mandate name.")
        with self._mandate_writer():
            with self._fund_lock(source):
                current, _source_path = self._load_mandate_entry(source)
                if mandate_hash(current) != expected_hash:
                    raise ServiceError(409, "Mandate changed; reload before cloning.", code="stale-preview")
                directory = self._ensure_dir("mandates")
                self._assert_mandate_name_available(target, directory)
                try:
                    save_spec(spec, directory, admission=self._admission)
                except FileExistsError:
                    raise ServiceError(409, "A mandate with this name already exists.") from None
                except StorageAdmissionError:
                    raise ServiceError(409, "Mandate could not be saved safely.") from None
                except (OSError, ValueError) as exc:
                    raise ServiceError(422, f"Mandate could not be saved ({type(exc).__name__}).") from None
        return self._mandate_summary(spec, include_spec=True)

    def deploy_mandate(self, name: str, request: DeployRequest) -> dict:
        self._require_writes()
        normalized = self._validated_name(name)
        self._guard_protected(normalized)
        try:
            universe = normalize_universe(request.universe)
        except ValueError:
            raise ServiceError(422, "Deployment universe is invalid.") from None
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
                except ValueError as exc:
                    raise ServiceError(422, f"Deployment validation failed ({type(exc).__name__}).") from None
                except OSError as exc:
                    raise ServiceError(409, f"Deployment could not be written ({type(exc).__name__}).") from None
                try:
                    record_ledger_head(
                        self.root_context,
                        normalized,
                        admission=self._admission,
                    )
                except HandoverError:
                    raise ServiceError(409, "Deployment was written; root head inventory requires offline review.", code="reconciliation-required") from None
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
            raise ServiceError(422, f"Paper fund is invalid ({type(exc).__name__}).") from None
        return self._paper_snapshot(deployed, directory, include_records=True)

    def paper_sessions(
        self,
        name: str,
        *,
        limit: int = 50,
        cursor: str | None = None,
        search: str | None = None,
    ) -> dict:
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ServiceError(422, "Session page limit must be between 1 and 100.")
        if cursor is not None:
            if not isinstance(cursor, str) or not _SESSION_CURSOR.fullmatch(cursor):
                raise ServiceError(422, "Session cursor is invalid.")
            try:
                if "T" in cursor:
                    datetime.strptime(cursor, "%Y-%m-%dT%H:%M:%S")
                else:
                    date.fromisoformat(cursor)
            except ValueError:
                raise ServiceError(422, "Session cursor is invalid.") from None
        if search is not None and (not isinstance(search, str) or len(search) > 128 or any(ord(character) < 32 or ord(character) == 127 for character in search)):
            raise ServiceError(422, "Session search is invalid.")

        normalized = self._validated_name(name)
        directory = self._safe_child("paper", normalized)
        if not directory.is_dir():
            raise ServiceError(404, "Paper fund not found.")
        try:
            deployed = load_deployed(directory)
        except ValueError as exc:
            raise ServiceError(422, f"Paper fund is invalid ({type(exc).__name__}).") from None

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
            raise ServiceError(422, "Paper tick preview is invalid.")
        return self._create_local_paper_preview(
            name,
            expected_head=request.expected_head,
            action="paper-tick",
            operator_session=operator_session,
            require_due=True,
            payload_builder=lambda head, due, _spec, _calls, _universe_size: {
                "kind": "manual-tick",
                "session": due[0],
                "expected_head": head,
            },
        )

    def create_runner_preview(
        self,
        name: str,
        request: RunnerPreviewRequest,
        *,
        operator_session: str | None,
    ) -> dict:
        if not isinstance(request, RunnerPreviewRequest):
            raise ServiceError(422, "Runner preview is invalid.")

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
                directory, deployed, _ledger, state, latest = self._paper_state(
                    normalized,
                    local_paper_only=True,
                )
                if deployed.broker != "paper":
                    raise ServiceError(403, "Paper operations require a local-paper deployment.", code="broker-not-web-supported")
                current_head = latest.hash if latest is not None else None
                if expected_head != current_head:
                    raise ServiceError(409, "Paper ledger changed; reload before previewing.", code="stale-preview")
                if state.halted is not None:
                    raise ServiceError(409, "Halted funds cannot accept a paper operation.", code="halted")
                with self._settings_lock:
                    self._ensure_settings_available()
                    settings = self._runtime_settings
                    self._require_local_paper_policy(settings)
                    model_calls = _estimate_paper_model_calls(
                        deployed.spec,
                        len(deployed.universe),
                    )
                    if model_calls > 1000:
                        raise ServiceError(422, "Estimated local model calls exceed the 1000-call bound.")
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
            raise ServiceError(422, "Paper tick acceptance is invalid.")
        if len(request.due_set) != 1:
            raise ServiceError(422, "Manual tick requires exactly one reviewed session.")
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
            raise ServiceError(422, "Runner acceptance is invalid.")
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

            worker.submit(operation, work)

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
                )
            except ConfirmationExpired:
                raise ServiceError(410, "Confirmation expired; review the paper operation again.") from None
            except (ConfirmationRejected, StalePreview):
                raise ServiceError(409, "Reviewed paper operation is stale or no longer valid.", code="stale-preview") from None
            except OperationStartUncertain:
                raise ServiceError(409, "Paper operation start is uncertain; inspect its durable status.", code="ownership-unknown") from None
            except (AdmissionError, JobConflict, OperationConflict):
                raise ServiceError(409, "Paper operation conflicts with current runner or execution state.", code="writer-conflict") from None
            except OperationError:
                raise ServiceError(409, "Paper operation could not be accepted.") from None
        return self._operation_view(operation)

    def _execute_manual_tick(
        self,
        operation: OperationRecord,
        capture: FrozenCapture,
        progress: Callable[[int], None],
        cancelled: Callable[[], bool],
    ) -> dict[str, object]:
        payload = dict(operation.payload)
        expected = {"kind", "session", "expected_head"}
        if set(payload) != expected or payload.get("kind") != "manual-tick":
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
        if not isinstance(session, str):
            raise OperationError("stored paper session is invalid")
        model_calls = _estimate_paper_model_calls(spec, len(capture.universe))
        if model_calls > 1000:
            raise AuthorizationDenied("manual model-call bound is invalid")
        now = _utcnow()
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
                    state, latest = self._replay_paper_state(
                        deployed,
                        Ledger(directory),
                    )
                    head = latest.hash if latest is not None else None
                    if head != payload["expected_head"]:
                        raise ServiceError(409, "Paper ledger head changed after review.", code="stale-preview")
                    if state.halted is not None:
                        raise ServiceError(409, "Halted funds cannot run a paper tick.", code="halted")
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
                            build_fund=self._captured_fund_factory(
                                capture,
                                dispatch,
                            ),
                            now=lambda: now.astimezone(NEW_YORK),
                        )
        except ServiceError:
            raise
        except (AdmissionError, HandoverError, LedgerError, OSError, ValueError):
            raise ServiceError(409, "Paper tick could not be executed safely.") from None
        try:
            record_ledger_head(
                self.root_context,
                operation.subject_id,
                admission=self._admission,
            )
        except HandoverError:
            raise ServiceError(409, "Paper tick recorded; root head inventory requires offline review.", code="reconciliation-required") from None
        progress(95)
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
        directory, deployed, _ledger, state, latest = self._paper_state(
            name,
            local_paper_only=True,
        )
        if deployed.broker != "paper" or mandate_hash(deployed.spec) != capture.mandate_digest or tuple(deployed.universe) != tuple(capture.universe):
            raise ServiceError(409, "Paper deployment changed after review.", code="stale-preview")
        if state.halted is not None:
            raise ServiceError(409, "Halted funds cannot accept a paper operation.", code="halted")
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
            ) from None
        if data_class is not ProviderClass.FREE_DATA:
            raise ServiceError(422, "Paper operations require free yfinance market data.")
        if llm_class is not ProviderClass.LOCAL:
            raise ServiceError(422, "Paper operations require a local Ollama model endpoint.")

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
        except LedgerError:
            raise ServiceError(409, "Paper state is invalid (LedgerError).", code="replay-corrupt") from None
        except HandoverError:
            raise ServiceError(409, "Offline paper ledger inventory changed; writes are denied.", code="reconciliation-required") from None

    def get_valuation(self, name: str) -> dict:
        """Return current-head estimate; never contacts a provider."""
        return self.paper_detail(name)["live_value"]

    def refresh_valuation(self, name: str, request: ValuationRefreshRequest) -> dict:
        self._require_writes()
        if not self.network_enabled:
            raise ServiceError(403, "Network capability is disabled for this server.")
        if not isinstance(request, ValuationRefreshRequest):
            raise ServiceError(422, "Valuation request is invalid.")
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
                        except Exception as exc:
                            errors[ticker] = type(exc).__name__
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
        normalized = self._validated_name(name)
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}(?:T\d{2}:\d{2}:\d{2})?", session):
            raise ServiceError(422, "Session key is invalid.")
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
            raise ServiceError(409, f"Ledger verification failed ({type(exc).__name__}).", code="replay-corrupt") from None
        return self._session_report(record)

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
            raise ServiceError(422, "Research page limit must be between 1 and 100.")
        if cursor is not None and (not isinstance(cursor, str) or not _REPORT_ID.fullmatch(cursor) or ".." in cursor):
            raise ServiceError(422, "Research cursor is invalid.")
        if search is not None and (not isinstance(search, str) or len(search) > 128 or any(ord(character) < 32 or ord(character) == 127 for character in search)):
            raise ServiceError(422, "Research search is invalid.")

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
                    raise ServiceError(422, "Research report identifier is invalid.")
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
            raise ServiceError(422, f"Research report is invalid ({type(exc).__name__}).") from None
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
        active_captures, active_captures_available = self._active_capture_views()
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
        return {
            **self._runtime_settings.public_view(),
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
            raise ServiceError(422, "Model is not in the supported provider catalog.")
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
            raise ServiceError(422, "Model is not in the supported provider catalog.")
        values = request.model_dump(exclude={"expected_version"})
        values["llm_provider"] = provider
        _persisted, updated = self._persist_runtime_settings(
            values,
            expected_version=request.expected_version,
        )
        return {
            **updated.public_view(),
            "scope": "root",
        }

    def set_credential(self, request: CredentialRequest) -> dict:
        self._require_writes()
        provider = _credential_provider(request.provider)
        value = request.value.get_secret_value()
        if not value or any(unicodedata.category(char) in {"Cc", "Cf"} for char in value):
            raise ServiceError(422, "Credential value is empty or contains control characters.")
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
            raise ServiceError(422, "Credential version is invalid.")
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
            raise ServiceError(422, "Backtest subject and reviewed head do not match.")
        try:
            universe = normalize_universe(payload.universe)
        except (OSError, ValueError):
            raise ServiceError(422, "Backtest universe is invalid.") from None
        if universe != payload.universe:
            raise ServiceError(422, "Backtest universe must use canonical uppercase tickers.")
        spec = self._load_mandate_by_name(subject)
        if spec.name != subject or mandate_hash(spec) != request.expected_head:
            raise ServiceError(409, "Mandate changed; reload before previewing.", code="stale-preview")
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
                raise ServiceError(422, "Provider configuration has no guarded production transport.") from None
            paid_targets = [
                (target, provider_class)
                for target, provider_class in (
                    (data_target, data_class),
                    (llm_target, llm_class),
                )
                if provider_class is ProviderClass.PAID_CLOUD
            ]
            if len(paid_targets) > 1:
                raise ServiceError(422, "Only one paid provider may be authorized per backtest.")
            if paid_targets and not payload.authorize_paid_provider:
                raise ServiceError(403, "Paid provider use requires explicit bounded authorization.")
            if not paid_targets and payload.authorize_paid_provider:
                raise ServiceError(422, "Paid authorization does not match the captured providers.")
            fd_pricing_attestation_required = any(target.kind == "data" and target.provider == "fd" for target, _provider_class in paid_targets)
            if fd_pricing_attestation_required and not payload.confirm_fd_self_service_pricing:
                raise ServiceError(403, "Financial Datasets dispatch requires explicit self-service pricing confirmation.")
            if payload.confirm_fd_self_service_pricing and not fd_pricing_attestation_required:
                raise ServiceError(422, "Financial Datasets pricing confirmation does not match the captured provider.")
            paid_cost_model_id = None
            if paid_targets:
                paid_target = paid_targets[0][0]
                paid_cost_model_id = cost_model_identity(paid_target)
                minimum_cost = minimum_attempt_cost(paid_target)
                if not has_verified_cost_model(paid_target) or minimum_cost is None:
                    raise ServiceError(422, "Paid provider has no verified upper-bound cost model.")
                if Decimal(payload.paid_max_attempt_cost_usd) < minimum_cost:
                    raise ServiceError(422, "Per-attempt cost bound is below the provider's verified maximum.")
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
                raise ServiceError(422, "Estimated model calls exceed the 1000-call bound.")
            paid_call_bound = max(1, estimated_llm_calls) if paid_targets and paid_targets[0][0].kind == "llm" else min(10000, max(100, estimated_model_calls * 10))
            if paid_targets:
                if payload.paid_max_calls > paid_call_bound:
                    raise ServiceError(422, "Paid call bound exceeds the captured operation estimate.")
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
                    raise ServiceError(422, "Selected provider credential is not configured.")
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
            raise ServiceError(422, "Backtest acceptance does not match the reviewed operation.")
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

            worker.submit(operation, work)

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
                )
            except ConfirmationExpired:
                raise ServiceError(410, "Confirmation expired; review the operation again.") from None
            except (ConfirmationRejected, StalePreview):
                raise ServiceError(409, "Reviewed operation is stale or no longer valid.", code="stale-preview") from None
            except OperationStartUncertain:
                raise ServiceError(409, "Operation start is uncertain; inspect its durable status.", code="ownership-unknown") from None
            except (OperationConflict, JobConflict):
                raise ServiceError(409, "Operation request conflicts with durable state.") from None
            except ServiceError:
                raise
            except OperationError:
                raise ServiceError(409, "Operation could not be accepted.") from None
        return self._operation_view(operation)

    def get_operation(self, operation_id: str) -> dict:
        store = self._operation_store
        if store is None:
            raise ServiceError(404, "Operation not found.")
        try:
            operation = store.get_operation(operation_id)
        except OperationBusy:
            raise ServiceError(503, "Operation status is busy; retry the read.", code="observation-conflict") from None
        except OperationError as exc:
            status = 404 if "not found" in str(exc) else 409
            raise ServiceError(status, "Operation is unavailable.") from None
        return self._operation_view(operation)

    def list_operations(self, *, limit: int = 100) -> dict:
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ServiceError(422, "Operation page size is invalid.")
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
            with self._paper_control_lane(normalized):
                _directory, deployed, ledger = self._paper_control_state(normalized)
                state, latest = self._replay_paper_state(deployed, ledger)
                if not deployed.spec.approval_required:
                    raise ServiceError(409, "This fund does not require approval.")
                if state.halted is not None:
                    raise ServiceError(409, "Halted funds cannot accept a verdict.", code="halted")
                pending = state.pending
                if pending is None or latest is None:
                    raise ServiceError(409, "No pending decision is available.")
                if request.decision_as_of != pending.as_of or request.source_record_hash != latest.hash:
                    raise ServiceError(409, "Pending decision changed; reload before submitting a verdict.", code="stale-preview")
                resolved, mailbox = ledger.resolve_approval(pending.as_of, latest.hash)
                if resolved is not None and mailbox is None:
                    raise ServiceError(409, "This decision is already consumed or expired.")
                latest_event = self._latest_approval_event(ledger, pending.as_of, latest.hash)
                if latest_event is not None and latest_event.get("kind") == "expire":
                    raise ServiceError(409, "This decision has expired.")
                try:
                    vote = ledger.set_approval(
                        request.verdict,
                        pending.as_of,
                        latest.hash,
                        "web",
                    )
                except (OSError, ValueError) as exc:
                    raise ServiceError(409, f"Verdict could not be saved ({type(exc).__name__}).") from None
        return {"verdict": vote["verdict"], "decision_as_of": vote["decision_as_of"], "saved": True}

    def halt_fund(self, name: str, reason: str) -> dict:
        if not self.allow_writes and not self.emergency_halt_available:
            self._require_writes()
        normalized = self._validated_name(name)
        self._guard_protected(normalized)
        if not isinstance(reason, str) or not reason.strip() or len(reason) > 240 or any(ord(char) < 32 or ord(char) == 127 for char in reason):
            raise ServiceError(422, "Halt reason is invalid.")
        with self._paper_control_lane(normalized, verify_inventory=False):
            _, _, ledger = self._paper_control_state(normalized)
            try:
                ledger.halt(reason)
            except OSError as exc:
                raise ServiceError(409, f"Fund could not be halted ({type(exc).__name__}).") from None
        return {"name": normalized, "halted": True}

    def resume_fund(self, name: str) -> dict:
        if not self.allow_writes and not self.emergency_halt_available:
            self._require_writes()
        normalized = self._validated_name(name)
        self._guard_protected(normalized)
        with self._fund_lock(normalized):
            with self._paper_control_lane(normalized):
                self._paper_control_state(normalized)
                raise ServiceError(409, "Resume is disabled until a reconciliation receipt is available.", code="reconciliation-required")

    @contextmanager
    def _paper_control_lane(
        self,
        name: str,
        *,
        verify_inventory: bool = True,
    ) -> Iterator[None]:
        try:
            with self._admission.control_lane(name, timeout=0.1):
                if verify_inventory:
                    self._verify_root_inventory()
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
        if pending is not None and latest is not None:
            try:
                current, mailbox = ledger.resolve_approval(pending.as_of, latest.hash)
                approval = current or (mailbox if mailbox and mailbox["decision_as_of"] == pending.as_of else None)
            except (OSError, ValueError):
                approval = None
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
            raise ServiceError(409, f"Paper state is invalid ({type(exc).__name__}).", code="replay-corrupt") from None
        return directory, deployed, ledger, state, latest

    def _replay_paper_state(self, deployed: DeployedFund, ledger: Ledger):
        latest = None

        def capture(record: SessionRecord) -> None:
            nonlocal latest
            latest = record

        try:
            state = ledger.replay(deployed.spec.capital, full=True, on_verified=capture)
        except (LedgerError, OSError, ValueError) as exc:
            raise ServiceError(409, f"Paper state is invalid ({type(exc).__name__}).", code="replay-corrupt") from None
        return state, latest

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
                raise ServiceError(422, "Strategy must use a backend library entry or the custom identity.")

    def _validated_mandate(self, payload: dict) -> FundSpec:
        try:
            spec = FundSpec.model_validate(payload)
        except ValueError as exc:
            raise ServiceError(422, f"Mandate validation failed ({type(exc).__name__}).") from None
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
                raise ServiceError(422, "Storage path is invalid.")
            candidate = candidate / part
            if _is_reparse_point(candidate):
                raise ServiceError(403, "Storage path contains a symlink or reparse point.")
        resolved = candidate.resolve(strict=False)
        if resolved != self.root and self.root not in resolved.parents:
            raise ServiceError(403, "Storage path escapes the configured data root.")
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
            raise ServiceError(422, "Fund name is invalid.") from None

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
            raise ServiceError(422, f"Mandate is invalid ({invalid_type}).")
        raise ServiceError(404, "Mandate not found.")

    def _guard_protected(self, name: str) -> None:
        if _windows_name_key(name) in {_windows_name_key(entry) for entry in PROTECTED_NAMES}:
            raise ServiceError(403, "Protected fund names cannot be modified by the web UI.")

    def _require_writes(self) -> None:
        if not self.allow_writes:
            raise ServiceError(403, "Write capability is disabled for this server.")
        status = enrollment_status(self.root_context)
        if status["state"] != "enrolled":
            self.allow_writes = False
            self.network_enabled = False
            self.enrollment_state = status["state"]
            self.write_unavailable_reason = status["reason"] or "handover-unavailable"
            if self._owner_lease is not None:
                self._owner_lease.close()
                self._owner_lease = None
            self._admission = AdmissionCoordinator(self.root_context)
            raise ServiceError(403, "Offline root enrollment is unavailable.")

    def _credential_status_map(self) -> dict[str, dict[str, int | bool]]:
        provider_ids = {provider.casefold() for provider in (*PROVIDER_ENV_VARS, *DATA_PROVIDER_ENV_VARS)}
        if self._credential_store is None:
            return {provider: {"version": 0, "configured": False} for provider in provider_ids}
        try:
            return self._credential_store.status()
        except CredentialStoreError:
            self._settings_error = "private-credentials-unavailable"
            return {provider: {"version": 0, "configured": False} for provider in provider_ids}

    def _active_capture_views(self) -> tuple[list[dict[str, object]], bool]:
        if self._operation_store is None:
            return [], False
        try:
            operations = self._operation_store.list_operations(limit=100)
        except OperationError:
            return [], False
        active = []
        for operation in operations:
            if operation.status not in {
                OperationStatus.ACCEPTED,
                OperationStatus.RUNNING,
                OperationStatus.CANCEL_REQUESTED,
            }:
                continue
            capture = self._captures.get(operation.capture_id)
            view = capture.public_view(current_settings_version=self._runtime_settings.version) if capture is not None else {}
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
                    "endpoint": view.get("endpoint"),
                    "restart_needed": view.get("restart_needed"),
                }
            )
        return active, True

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
                raise ServiceError(422, "Runtime settings are invalid.") from None
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

    def _latest_approval_event(self, ledger: Ledger, decision_as_of: str, decision_hash: str) -> dict | None:
        try:
            events = ledger.events()
        except (OSError, UnicodeError, ValueError):
            return None
        for event in reversed(events):
            if not isinstance(event, dict):
                continue
            if event.get("decision_as_of") == decision_as_of and event.get("decision_hash") == decision_hash:
                if event.get("kind") in {"approve", "reject", "expire"} or (event.get("kind") == "tick" and event.get("approval_verdict") in {"approve", "reject"}):
                    return event
        return None


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


def _credential_provider(value: str) -> str:
    if not isinstance(value, str):
        raise ServiceError(422, "Provider is not an allowlisted credential provider.")
    provider = next(
        (name for name in (*PROVIDER_ENV_VARS, *DATA_PROVIDER_ENV_VARS) if name.casefold() == value.casefold()),
        None,
    )
    if provider is None:
        raise ServiceError(422, "Provider is not an allowlisted credential provider.")
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
        raise ServiceError(422, "Backtest dates are invalid.") from None
    if end < start or (end - start).days > 730:
        raise ServiceError(422, "Backtest date range exceeds its bound.")
    if type(universe_size) is not int or not 1 <= universe_size <= 20:
        raise ServiceError(422, "Backtest universe exceeds its bound.")
    if not isinstance(spec, FundSpec) or type(local_llm_fallback) is not bool:
        raise ServiceError(422, "Backtest model-call estimate is invalid.")
    weekdays = sum(1 for offset in range((end - start).days + 1) if (start + timedelta(days=offset)).weekday() < 5)
    try:
        model_calls, llm_calls = model_call_bounds(
            spec,
            local_llm_fallback=local_llm_fallback,
        )
    except ValueError:
        raise ServiceError(422, "Backtest model-call estimate is invalid.") from None
    return weekdays * universe_size * model_calls, weekdays * universe_size * llm_calls


def _estimate_paper_model_calls(spec: FundSpec, universe_size: int) -> int:
    if not isinstance(spec, FundSpec) or type(universe_size) is not int or not 1 <= universe_size <= 25:
        raise ServiceError(422, "Paper model-call estimate is invalid.")
    try:
        model_calls, _llm_calls = model_call_bounds(
            spec,
            local_llm_fallback=True,
        )
    except ValueError:
        raise ServiceError(422, "Paper model-call estimate is invalid.") from None
    calls = universe_size * model_calls * 2
    if type(calls) is not int or not 1 <= calls <= 1000:
        raise ServiceError(422, "Paper model-call estimate exceeds the 1000-call bound.")
    return calls


def _runner_limits(
    spec: FundSpec,
    *,
    universe_size: int,
    max_sessions: int,
    max_runtime_minutes: int,
) -> tuple[int, int]:
    if not isinstance(spec, FundSpec) or type(universe_size) is not int or not 1 <= universe_size <= 25 or type(max_sessions) is not int or not 1 <= max_sessions <= 100 or type(max_runtime_minutes) is not int or not 1 <= max_runtime_minutes <= 1440:
        raise ServiceError(422, "Finite runner bounds are invalid.")
    model_calls = _estimate_paper_model_calls(spec, universe_size)
    calls_per_session = model_calls + 40 * universe_size + 20
    max_calls = 2 * max_runtime_minutes + 1 + max_sessions * calls_per_session
    max_resources = max_calls
    if not 1 <= max_calls <= 1_000_000 or not 1 <= max_resources <= 1_000_000:
        raise ServiceError(422, "Finite runner resource estimate exceeds its bound.")
    return max_calls, max_resources


def _reject_secret_fields(value) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if _SECRET_FIELD.search(str(key)):
                raise ServiceError(422, "Mandates cannot store credential-like fields.")
            _reject_secret_fields(child)
    elif isinstance(value, list):
        for child in value:
            _reject_secret_fields(child)


def _utcnow():
    from datetime import datetime, timezone

    return datetime.now(timezone.utc)
