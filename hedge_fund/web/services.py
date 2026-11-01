"""Thin adapters over validated fund, ledger, research and key services."""

from __future__ import annotations

import json
import re
import stat
import threading
import unicodedata
from contextlib import contextmanager
from datetime import date, timedelta
from ipaddress import ip_address
from pathlib import Path
from typing import Callable, Iterator
from urllib.parse import urlsplit
from uuid import uuid4

from hedge_fund.backtesting.fund import backtest_fund, FundBacktestResult
from hedge_fund.backtesting.research import save_result
from hedge_fund.data import CachedDataClient, make_data_client, PriceSnapshot
from hedge_fund.fund import (
    custom_strategy,
    Fund,
    FundSpec,
    load_spec,
    load_strategy,
    normalize_universe,
    save_spec,
    StrategySpec,
)
from hedge_fund.llm import (
    DEFAULT_MODEL,
    env_var_for,
    make_llm,
    PromptCache,
    PROVIDER_ENV_VARS,
)
from hedge_fund.llm.registry import is_supported, KEYLESS_PROVIDERS, load_api_models
from hedge_fund.paper.deployed import (
    deploy,
    DeployedFund,
    list_deployed,
    load_deployed,
    validate_fund_name,
)
from hedge_fund.paper.ledger import Ledger, LedgerError
from hedge_fund.paper.tick import following_session
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
from hedge_fund.runtime.credentials import (
    CredentialStore,
    CredentialStoreError,
    CredentialVersionConflict,
)
from hedge_fund.runtime.operations import (
    ConfirmationExpired,
    ConfirmationRejected,
    OperationConflict,
    OperationError,
    OperationRecord,
    OperationStartUncertain,
    OperationStatus,
    OperationStore,
    StalePreview,
)
from hedge_fund.runtime.root import RootContext, RootPathError
from hedge_fund.scorecard import score
from hedge_fund.web.jobs import JobCancelled, JobConflict, OperationJobRegistry
from hedge_fund.web.schemas import (
    ApprovalRequest,
    BacktestRequest,
    CredentialRequest,
    DeployRequest,
    ModelRequest,
    OperationAcceptRequest,
    OperationCancelRequest,
    OperationPreviewRequest,
    RuntimeSettingsRequest,
    ValuationRefreshRequest,
)
from hedge_fund.web.valuation import estimate_valuation, MAX_VALUATION_POSITIONS

PROTECTED_NAMES = ("watchtower", "watchtower-weekly", "umbrella")
_REPORT_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,180}\.json$")
_SECRET_FIELD = re.compile(r"(?:api.?key|secret|token|password|credential|authorization)", re.IGNORECASE)


class ServiceError(RuntimeError):
    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


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
        self.container_observer = container_observer
        self._owner_lease: RootOwnerLease | None = None
        self._admission = AdmissionCoordinator(root_context)
        self.allow_writes = False
        self.write_unavailable_reason: str | None = None
        if allow_writes and not container_observer:
            try:
                root_context.prepare_private_storage()
                owner = RootOwnerLease.acquire(root_context)
                self._owner_lease = owner
                self._admission = AdmissionCoordinator(root_context, owner_lease=owner)
                self.allow_writes = True
            except (AdmissionError, OSError, RootPathError, ValueError):
                self.write_unavailable_reason = "private-storage-unverified" if not root_context.verify_private_storage() else "root-owner-unavailable"
        elif container_observer:
            self.write_unavailable_reason = "container-observer"
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
        self._captures: dict[str, FrozenCapture] = {}
        self._preview_captures: dict[str, str] = {}
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
                    try:
                        operation_jobs.recover_unfinished()
                    except Exception:
                        operation_jobs.close()
                        raise
                    self._operation_jobs = operation_jobs
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

    def close(self) -> None:
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
            "write_unavailable_reason": self.write_unavailable_reason,
            "protected_names": list(PROTECTED_NAMES),
            "mutation_token": mutation_token if self.allow_writes else None,
            "deferred_actions": {
                "runner": "Runner ownership is not verified by the web process; start and stop controls are disabled.",
                "manual_run": "Manual execution is disabled; the web process does not own the fund runner.",
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
            "research_count": len(reports["items"]),
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
            except (OSError, ValueError) as exc:
                errors.append({"name": path.stem, "error": f"Invalid mandate ({type(exc).__name__})."})
        return {"items": items, "errors": errors}

    def get_mandate(self, name: str) -> dict:
        normalized = self._validated_name(name)
        spec = self._load_mandate_by_name(normalized)
        _reject_secret_fields(spec.model_dump(mode="python"))
        return self._mandate_summary(spec, include_spec=True)

    def create_mandate(self, payload: dict) -> dict:
        self._require_writes()
        try:
            spec = FundSpec.model_validate(payload)
        except ValueError as exc:
            raise ServiceError(422, f"Mandate validation failed ({type(exc).__name__}).") from None
        _reject_secret_fields(spec.model_dump(mode="python"))
        self._validate_mandate_strategies(spec)
        name = self._validated_name(spec.name)
        self._guard_protected(name)
        with self._fund_lock(name):
            directory = self._ensure_dir("mandates")
            self._assert_unique(directory, f"{name}.yaml")
            try:
                self._load_mandate_by_name(name)
            except ServiceError as exc:
                if exc.status_code != 404:
                    raise
            else:
                raise ServiceError(409, "A mandate with this name already exists.")
            try:
                save_spec(spec, directory)
            except FileExistsError:
                raise ServiceError(409, "A mandate with this name already exists.") from None
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
            spec = self._load_mandate_by_name(normalized)
            _reject_secret_fields(spec.model_dump(mode="python"))
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
                        "runner": self._runner_state(),
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
                _, deployed, _, state, latest = self._paper_state(normalized)
                if deployed.broker != "paper":
                    raise ServiceError(403, "Valuation requires a local-paper deployment.")
                expected_head = latest.hash if latest is not None else None
                if request.expected_head != expected_head:
                    raise ServiceError(409, "Paper ledger changed; reload before refreshing valuation.")
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
                with self._make_data_client(provider="yfinance") as client:
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
                _, current, _, current_state, current_latest = self._paper_state(normalized)
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
            raise ServiceError(409, f"Ledger verification failed ({type(exc).__name__}).") from None
        return self._session_report(record)

    def paper_scorecard(self, name: str) -> dict:
        snapshot = self.paper_detail(name)
        card = snapshot.get("scorecard")
        if card is None:
            raise ServiceError(409, snapshot.get("scorecard_error") or "No recorded sessions to score.")
        return card

    def list_research(self) -> dict:
        directory = self._safe_child("research")
        if not directory.exists():
            return {"items": [], "errors": []}
        if not directory.is_dir():
            raise ServiceError(409, "Research storage is not a directory.")
        items = []
        errors = []
        for path in sorted(directory.glob("*.json"), key=lambda entry: entry.name.casefold(), reverse=True):
            try:
                safe_path = self._safe_child("research", path.name)
                result = FundBacktestResult.model_validate_json(safe_path.read_text(encoding="utf-8"))
                items.append(self._research_summary(path.name, result))
            except ServiceError as exc:
                errors.append({"id": path.name, "error": exc.detail})
            except (OSError, ValueError) as exc:
                errors.append({"id": path.name, "error": f"Invalid research report ({type(exc).__name__})."})
        return {"items": items[:100], "errors": errors}

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
        for provider in [*PROVIDER_ENV_VARS, *sorted(KEYLESS_PROVIDERS)]:
            env_var = env_var_for(provider)
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
                {"id": "fd", "label": "Financial Datasets"},
                {"id": "yfinance", "label": "Yahoo Finance"},
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
                raise ServiceError(409, "Credential version changed; reload before saving.") from None
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
                raise ServiceError(409, "Credential version changed; reload before saving.") from None
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
            raise ServiceError(409, "Mandate changed; reload before previewing.")
        if spec.broker != "paper":
            raise ServiceError(403, "Only local-paper backtests are supported.")
        with self._settings_lock:
            self._ensure_settings_available()
            settings = self._runtime_settings
            if payload.provider != settings.data_provider or payload.model != settings.model:
                raise ServiceError(409, "Provider or model changed; reload before previewing.")
            self._require_local_backtest_policy(settings)
            estimated_model_calls = _estimate_backtest_calls(
                payload.start,
                payload.end,
                len(universe),
                spec,
            )
            if estimated_model_calls > 1000:
                raise ServiceError(422, "Estimated local model calls exceed the 1000-call bound.")
            provider_id = settings.llm_provider.casefold()
            credential_versions = {}
            if settings.llm_provider not in KEYLESS_PROVIDERS:
                status = self._credential_status_map().get(settings.llm_provider)
                if not status or not status["configured"]:
                    raise ServiceError(422, "Selected provider credential is not configured.")
                credential_versions[provider_id] = status["version"]
            now = _utcnow()
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
                    payload=payload.model_dump(mode="json"),
                    now=now,
                    expires_at=now + timedelta(minutes=10),
                )
            except OperationError:
                raise ServiceError(409, "Backtest preview could not be persisted.") from None
            self._cache_preview_capture(preview.preview_id, capture)
        return {
            **preview.public_view(),
            "confirmation_token": preview.confirmation_token,
            "capture": capture.public_view(current_settings_version=settings.version),
            "estimate": {
                "maximum_model_calls": estimated_model_calls,
                "maximum_cost_usd": 0.0 if not self._custom_fund_factory else None,
                "market_data_provider": settings.data_provider,
            },
            "warnings": ["No paid provider calls are enabled." if not self._custom_fund_factory else "Injected test providers only; no live provider call is authorized."],
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
            raise ServiceError(409, "Backtest preview is no longer available; review again.")
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
                raise ServiceError(409, "Runtime settings changed; review the operation again.")
            for provider_id, version in capture.credential_versions.items():
                if self._credential_store is None:
                    raise ServiceError(409, "Captured credential storage is unavailable.")
                try:
                    current_version, _configured = self._credential_store.version(provider_id)
                except CredentialStoreError:
                    raise ServiceError(409, "Captured credential version is unavailable.") from None
                if current_version != version:
                    raise ServiceError(409, "Credential version changed; review the operation again.")
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
                raise ServiceError(409, "Reviewed operation is stale or no longer valid.") from None
            except OperationStartUncertain:
                raise ServiceError(409, "Operation start is uncertain; inspect its durable status.") from None
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
        if self._custom_fund_factory:
            fund = self._fund_factory(spec)
        else:
            fund = self._default_fund_factory(spec, capture)

        def on_valuation(index: int, total: int, _value) -> None:
            if cancelled():
                raise JobCancelled()
            percent = int(100 * (index + 1) / total) if total > 0 else 0
            progress(min(99, max(0, percent)))

        with self._make_data_client(capture.data_provider) as data_client:
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
        path = apply_if_current(lambda: save_result(result, directory=self._ensure_dir("research")))
        if not isinstance(path, Path):
            raise OperationError("backtest report path is invalid")
        return {
            "report_id": path.name,
            "capture_id": capture.capture_id,
            "capture_digest": capture.digest,
        }

    def _require_local_backtest_policy(self, settings: RuntimeSettings) -> None:
        if settings.data_provider != "yfinance":
            raise ServiceError(422, "Web backtests require the free yfinance data provider.")
        if settings.llm_provider != "Ollama" or settings.model.casefold().endswith(":cloud") or not _is_loopback_endpoint(settings.endpoint):
            raise ServiceError(422, "Web backtests require a local Ollama model endpoint.")

    def _cache_preview_capture(
        self,
        preview_id: str,
        capture: FrozenCapture,
    ) -> None:
        while len(self._preview_captures) >= 1000:
            oldest_preview_id = next(iter(self._preview_captures))
            old_capture_id = self._preview_captures.pop(oldest_preview_id)
            self._captures.pop(old_capture_id, None)
        self._preview_captures[preview_id] = capture.capture_id
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
                    raise ServiceError(409, "Halted funds cannot accept a verdict.")
                pending = state.pending
                if pending is None or latest is None:
                    raise ServiceError(409, "No pending decision is available.")
                if request.decision_as_of != pending.as_of or request.source_record_hash != latest.hash:
                    raise ServiceError(409, "Pending decision changed; reload before submitting a verdict.")
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
        self._require_writes()
        normalized = self._validated_name(name)
        self._guard_protected(normalized)
        if not isinstance(reason, str) or not reason.strip() or len(reason) > 240 or any(ord(char) < 32 or ord(char) == 127 for char in reason):
            raise ServiceError(422, "Halt reason is invalid.")
        with self._fund_lock(normalized):
            with self._paper_control_lane(normalized):
                _, _, ledger = self._paper_control_state(normalized)
                try:
                    ledger.halt(reason)
                except OSError as exc:
                    raise ServiceError(409, f"Fund could not be halted ({type(exc).__name__}).") from None
        return {"name": normalized, "halted": True}

    def resume_fund(self, name: str) -> dict:
        self._require_writes()
        normalized = self._validated_name(name)
        self._guard_protected(normalized)
        with self._fund_lock(normalized):
            with self._paper_control_lane(normalized):
                self._paper_control_state(normalized)
                raise ServiceError(
                    409,
                    "Resume is disabled until a reconciliation receipt is available.",
                )

    @contextmanager
    def _paper_control_lane(self, name: str) -> Iterator[None]:
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
            "runner": self._runner_state(),
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

    def _paper_state(self, name: str):
        directory = self._safe_child("paper", name)
        if not directory.is_dir():
            raise ServiceError(404, "Paper fund not found.")
        try:
            deployed = load_deployed(directory)
            ledger = Ledger(directory)
            state, latest = self._replay_paper_state(deployed, ledger)
        except (LedgerError, OSError, ValueError) as exc:
            raise ServiceError(409, f"Paper state is invalid ({type(exc).__name__}).") from None
        return directory, deployed, ledger, state, latest

    def _replay_paper_state(self, deployed: DeployedFund, ledger: Ledger):
        latest = None

        def capture(record: SessionRecord) -> None:
            nonlocal latest
            latest = record

        try:
            state = ledger.replay(deployed.spec.capital, full=True, on_verified=capture)
        except (LedgerError, OSError, ValueError) as exc:
            raise ServiceError(409, f"Paper state is invalid ({type(exc).__name__}).") from None
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
            raise ServiceError(403, "Web paper mutations require a local-paper deployment.")
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
        library = self._strategy_library()
        for strategy in spec.strategies:
            canonical = library.get(strategy.name)
            if canonical is not None:
                if strategy.models != canonical.models or strategy.blend != canonical.blend:
                    raise ServiceError(
                        422,
                        "Library strategies must retain their canonical analyst roster, weights, params, and blend policy.",
                    )
                continue
            if strategy.name != "custom":
                raise ServiceError(422, "Strategy must use a backend library entry or the canonical custom analyst roster.")
            try:
                canonical_custom = custom_strategy([model.name for model in strategy.models])
            except ValueError:
                raise ServiceError(422, "Custom analyst roster is invalid.") from None
            if strategy.models != canonical_custom.models or strategy.blend != canonical_custom.blend:
                raise ServiceError(422, "Custom strategy must use registered analysts and the canonical blend mode.")

    def _default_fund_factory(
        self,
        spec: FundSpec,
        capture: FrozenCapture | None = None,
    ) -> Fund:
        cache = PromptCache(self._safe_child("cache", "llm"))
        if capture is None:
            return Fund(spec, blind=True, cache=cache)

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
            )

        return Fund(spec, blind=True, cache=cache, llm_factory=llm_factory)

    @contextmanager
    def _make_data_client(self, provider: str | None = None) -> Iterator[object]:
        if self._data_client_factory is not None:
            with self._data_client_factory() as client:
                yield client
            return
        cache = self._ensure_dir("cache")
        selected_provider = self._runtime_settings.data_provider if provider is None else provider
        with make_data_client(provider=selected_provider) as client:
            yield CachedDataClient(client, cache_dir=cache)

    def _runner_state(self) -> dict:
        return {
            "status": "unknown",
            "available": False,
            "reason": "Runner ownership is not verified; web process controls are disabled.",
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

    def _assert_unique(self, directory: Path, filename: str) -> None:
        candidate = Path(filename)
        for existing in directory.iterdir():
            if _windows_name_key(existing.name) == _windows_name_key(candidate.name):
                raise ServiceError(409, "A resource with this name already exists.")

    def _validated_name(self, name: str) -> str:
        try:
            return validate_fund_name(name)
        except ValueError:
            raise ServiceError(422, "Fund name is invalid.") from None

    def _load_mandate_by_name(self, name: str) -> FundSpec:
        directory = self._safe_child("mandates")
        if not directory.exists():
            raise ServiceError(404, "Mandate not found.")
        if not directory.is_dir():
            raise ServiceError(409, "Mandate storage is not a directory.")
        name_key = _windows_name_key(name)
        matches = []
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
                matches.append(spec)
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

    def _credential_status_map(self) -> dict[str, dict[str, int | bool]]:
        if self._credential_store is None:
            return {provider: {"version": 0, "configured": False} for provider in PROVIDER_ENV_VARS}
        try:
            return self._credential_store.status()
        except CredentialStoreError:
            self._settings_error = "private-credentials-unavailable"
            return {provider: {"version": 0, "configured": False} for provider in PROVIDER_ENV_VARS}

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
                raise ServiceError(409, "Runtime settings changed; reload before saving.") from None
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
        (name for name in PROVIDER_ENV_VARS if name.casefold() == value.casefold()),
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


def _estimate_backtest_calls(
    start_text: str,
    end_text: str,
    universe_size: int,
    spec: FundSpec,
) -> int:
    try:
        start = date.fromisoformat(start_text)
        end = date.fromisoformat(end_text)
    except (TypeError, ValueError):
        raise ServiceError(422, "Backtest dates are invalid.") from None
    if end < start or (end - start).days > 730:
        raise ServiceError(422, "Backtest date range exceeds its bound.")
    if type(universe_size) is not int or not 1 <= universe_size <= 20:
        raise ServiceError(422, "Backtest universe exceeds its bound.")
    weekdays = sum(1 for offset in range((end - start).days + 1) if (start + timedelta(days=offset)).weekday() < 5)
    agent_count = sum(len(strategy.models) for strategy in spec.strategies)
    return weekdays * universe_size * max(1, agent_count)


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
