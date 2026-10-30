"""Thin adapters over validated fund, ledger, research and key services."""

from __future__ import annotations

import os
import re
import stat
import threading
import unicodedata
from contextlib import contextmanager
from pathlib import Path
from typing import Callable, Iterator

from dotenv import dotenv_values

from hedge_fund.backtesting.fund import backtest_fund, FundBacktestResult
from hedge_fund.backtesting.research import save_result
from hedge_fund.data import CachedDataClient, data_provider, make_data_client
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
from hedge_fund.llm import DEFAULT_MODEL, env_var_for, PROVIDER_ENV_VARS
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
from hedge_fund.pipeline.session import mandate_hash, SessionRecord
from hedge_fund.scorecard import score
from hedge_fund.tui.keys import save_credential
from hedge_fund.web.jobs import JobCancelled, JobConflict, JobRegistry
from hedge_fund.web.schemas import (
    ApprovalRequest,
    BacktestRequest,
    CredentialRequest,
    DeployRequest,
    ModelRequest,
)

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
    ) -> None:
        self.root = Path(root).expanduser().resolve()
        self.allow_writes = bool(allow_writes)
        self.network_enabled = bool(network_enabled)
        self.demo = bool(demo)
        self._data_client_factory = data_client_factory
        self._fund_factory = fund_factory or Fund
        self.jobs = JobRegistry()
        self._locks: dict[str, threading.RLock] = {}
        self._locks_guard = threading.Lock()
        self._settings_lock = threading.RLock()
        self._load_root_environment()
        self._selected_model = os.environ.get("HEDGE_FUND_LLM_MODEL") or DEFAULT_MODEL

    def close(self) -> None:
        self.jobs.close()

    def capabilities(self, mutation_token: str | None) -> dict:
        return {
            "mode": "demo" if self.demo else "live",
            "read_only": not self.allow_writes,
            "writes": self.allow_writes,
            "network": self.network_enabled,
            "protected_names": list(PROTECTED_NAMES),
            "mutation_token": mutation_token if self.allow_writes else None,
            "deferred_actions": {
                "runner": "Runner ownership is not verified by the web process; start and stop controls are disabled.",
                "manual_run": "Manual execution is disabled; the web process does not own the fund runner.",
                "delete": "Fund and report deletion is not available.",
                "redo": "Ledger redo is not available from the web UI.",
                "live_value": "Live quotes are not fetched by the web process.",
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
        try:
            ledger.replay(deployed.spec.capital, full=True)
            if session not in ledger.sessions():
                raise ServiceError(404, "Session report not found.")
            record = ledger.read(session)
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
        selected_model = self._selected_model
        providers = []
        for provider in [*PROVIDER_ENV_VARS, *sorted(KEYLESS_PROVIDERS)]:
            env_var = env_var_for(provider)
            providers.append(
                {
                    "provider": provider,
                    "requires_key": env_var is not None,
                    "configured": bool(os.environ.get(env_var)) if env_var else True,
                }
            )
        return {
            "model": selected_model,
            "models": model_options,
            "providers": providers,
            "data_provider": data_provider(),
            "network_enabled": self.network_enabled,
        }

    def set_model(self, request: ModelRequest) -> dict:
        self._require_writes()
        allowed = {model_id for _, model_id, provider in load_api_models() if is_supported(provider)}
        if request.model not in allowed:
            raise ServiceError(422, "Model is not in the supported provider catalog.")
        with self._settings_lock:
            self._ensure_no_active_job()
            os.environ["HEDGE_FUND_LLM_MODEL"] = request.model
            self._selected_model = request.model
        return {"model": request.model, "scope": "process"}

    def set_credential(self, request: CredentialRequest) -> dict:
        self._require_writes()
        provider = request.provider
        env_var = PROVIDER_ENV_VARS.get(provider)
        if env_var is None:
            raise ServiceError(422, "Provider is not an allowlisted credential provider.")
        value = request.value.get_secret_value()
        if not value or any(unicodedata.category(char) in {"Cc", "Cf"} for char in value):
            raise ServiceError(422, "Credential value is empty or contains control characters.")
        with self._settings_lock:
            self._ensure_no_active_job()
            self._guard_settings_write()
            env_path = self._safe_child(".env")
            try:
                save_credential(env_var, value, path=env_path)
            except (OSError, ValueError) as exc:
                raise ServiceError(409, f"Credential could not be saved ({type(exc).__name__}).") from None
        return {"provider": provider, "configured": True}

    def submit_backtest(self, request: BacktestRequest) -> dict:
        self._require_writes()
        if not self.network_enabled:
            raise ServiceError(403, "Network capability is disabled; restart with explicit network consent.")
        name = self._validated_name(request.fund)
        self._guard_protected(name)
        spec = self._load_mandate_by_name(name)
        _reject_secret_fields(spec.model_dump(mode="python"))
        try:
            universe = normalize_universe(request.universe)
        except (OSError, ValueError) as exc:
            raise ServiceError(422, f"Backtest request is invalid ({type(exc).__name__}).") from None
        if request.mandate_hash != mandate_hash(spec):
            raise ServiceError(409, "Mandate configuration changed; reload before confirming this backtest.")

        def work(progress: Callable[[int], None], cancelled: Callable[[], bool]) -> dict:
            with self._make_data_client() as data_client:
                fund = self._fund_factory(spec)

                def on_valuation(index: int, total: int, _value) -> None:
                    if cancelled():
                        raise JobCancelled()
                    progress(int(100 * (index + 1) / total))

                result = backtest_fund(
                    fund,
                    request.start,
                    request.end,
                    data_client,
                    universe,
                    on_valuation=on_valuation,
                )
                if cancelled():
                    raise JobCancelled()
                path = save_result(result, directory=self._ensure_dir("research"))
                return {"report_id": path.name}

        with self._settings_lock:
            provider = data_provider()
            model = self._selected_model
            allowed = {model_id for _, model_id, listed_provider in load_api_models() if is_supported(listed_provider)}
            if request.provider != provider or request.model != model:
                raise ServiceError(409, "Research provider or model changed; reload before confirming this backtest.")
            if model not in allowed:
                raise ServiceError(422, "Model is not in the supported provider catalog.")
            try:
                return self.jobs.submit(name, provider, model, work)
            except JobConflict as exc:
                raise ServiceError(409, str(exc)) from None

    def get_job(self, job_id: str) -> dict:
        if not re.fullmatch(r"[a-f0-9]{32}", job_id):
            raise ServiceError(404, "Research job not found.")
        job = self.jobs.get(job_id)
        if job is None:
            raise ServiceError(404, "Research job not found.")
        return job

    def list_jobs(self) -> dict:
        return {"items": self.jobs.list()}

    def cancel_job(self, job_id: str) -> dict:
        self._require_writes()
        if not re.fullmatch(r"[a-f0-9]{32}", job_id):
            raise ServiceError(404, "Research job not found.")
        try:
            return self.jobs.cancel(job_id)
        except JobConflict as exc:
            raise ServiceError(409, str(exc)) from None

    def approve(self, name: str, request: ApprovalRequest) -> dict:
        self._require_writes()
        normalized = self._validated_name(name)
        self._guard_protected(normalized)
        with self._fund_lock(normalized):
            directory, deployed, ledger, state, latest = self._paper_state(normalized)
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
            _, ledger = self._paper_control_state(normalized)
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
            _, _, ledger, _, _ = self._paper_state(normalized)
            try:
                ledger.resume()
            except OSError as exc:
                raise ServiceError(409, f"Fund could not be resumed ({type(exc).__name__}).") from None
        return {"name": normalized, "halted": False}

    def _paper_snapshot(self, deployed: DeployedFund, directory: Path, *, include_records: bool = False) -> dict:
        ledger = Ledger(directory)
        try:
            halted = ledger.halted()
        except (LedgerError, OSError, ValueError):
            halted = None
        try:
            records = ledger.records()
            state = ledger.replay(deployed.spec.capital, full=True)
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
            "ledger": ledger_status,
            "runner": self._runner_state(),
            "live_value": {
                "status": "unavailable",
                "value": None,
                "as_of": None,
                "provenance": None,
                "reason": "Live quotes are not fetched by the web process.",
            },
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
            state = ledger.replay(deployed.spec.capital, full=True)
            latest = ledger.latest()
        except (LedgerError, OSError, ValueError) as exc:
            raise ServiceError(409, f"Paper state is invalid ({type(exc).__name__}).") from None
        return directory, deployed, ledger, state, latest

    def _paper_control_state(self, name: str) -> tuple[Path, Ledger]:
        directory = self._safe_child("paper", name)
        if not directory.is_dir():
            raise ServiceError(404, "Paper fund not found.")
        self._safe_child("paper", name, "fund.yaml")
        self._safe_child("paper", name, "control.json")
        self._safe_child("paper", name, "events.jsonl")
        try:
            deployed = load_deployed(directory)
        except (OSError, ValueError) as exc:
            raise ServiceError(409, f"Paper fund is invalid ({type(exc).__name__}).") from None
        if _windows_name_key(deployed.name) != _windows_name_key(name):
            raise ServiceError(409, "Paper deployment identity does not match its directory.")
        return directory, Ledger(directory)

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

    @contextmanager
    def _make_data_client(self) -> Iterator[object]:
        if self._data_client_factory is not None:
            with self._data_client_factory() as client:
                yield client
            return
        cache = self._ensure_dir("cache")
        with make_data_client() as client:
            yield CachedDataClient(client, cache_dir=cache)

    def _runner_state(self) -> dict:
        return {
            "status": "unknown",
            "available": False,
            "reason": "Runner ownership is not verified; web process controls are disabled.",
        }

    def _safe_child(self, *parts: str) -> Path:
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
        if not self.root.exists():
            self.root.mkdir(parents=True, exist_ok=True)
        directory = self._safe_child(*parts)
        directory.mkdir(parents=True, exist_ok=True)
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

    def _guard_settings_write(self) -> None:
        self._ensure_root()
        self._safe_child(".env")

    def _ensure_root(self) -> None:
        self._require_writes()
        if not self.root.exists():
            self.root.mkdir(parents=True, exist_ok=True)

    def _ensure_no_active_job(self) -> None:
        if any(job["status"] in {"queued", "running"} for job in self.jobs.list()):
            raise ServiceError(409, "Settings cannot change while a research job is active.")

    def _load_root_environment(self) -> None:
        if not self.allow_writes and not self.network_enabled:
            return
        env_path = self._safe_child(".env")
        if not env_path.is_file():
            return
        try:
            values = dotenv_values(env_path)
        except (OSError, UnicodeError, ValueError):
            return
        for name, value in values.items():
            if value is not None:
                os.environ.setdefault(name, value)

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
