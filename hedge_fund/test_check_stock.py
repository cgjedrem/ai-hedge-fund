"""Stock-check CLI coverage with synthetic roots and guarded fake clients."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock

import pytest

from hedge_fund.data.models import CompanyFacts, FinancialMetrics
from hedge_fund.runtime.dispatch import ProviderDispatch
from hedge_fund.runtime.handover import enroll_fresh
from hedge_fund.runtime.policy import AuthorizationDenied, ProviderTarget
from hedge_fund.runtime.root import RootContext


@pytest.fixture
def enrolled_root(tmp_path):
    root = tmp_path / "stock-root"
    root.mkdir()
    with RootContext.open(root) as context:
        enroll_fresh(context)
    return root


def _arguments(root):
    return [
        "AAPL",
        "--root",
        str(root),
        "--enable-network",
        "--date",
        "2024-12-31",
    ]


def _paid_data_budget(calls, total, attempt):
    return [
        "--authorize-paid-provider",
        "fd",
        "--confirm-fd-self-service-pricing",
        "--paid-max-calls",
        calls,
        "--paid-max-cost-usd",
        total,
        "--paid-max-attempt-cost-usd",
        attempt,
    ]


def test_stock_check_requires_an_explicit_root_before_provider_construction(
    monkeypatch,
    capsys,
):
    import check_stock
    import hedge_fund.data

    forbidden = Mock(side_effect=AssertionError("provider constructed before root"))
    monkeypatch.setattr(hedge_fund.data, "make_data_client", forbidden)

    with pytest.raises(SystemExit) as denied:
        check_stock.main(["AAPL", "--enable-network"])

    assert denied.value.code == 2
    assert "--root" in capsys.readouterr().err
    assert forbidden.call_count == 0


def test_advertised_stock_command_rejects_missing_root_before_guarded_io(
    monkeypatch,
    capsys,
):
    import check_stock
    from hedge_fund.data.yfinance_client import YFinanceClient

    def guarded_request(client, *_args, **_kwargs):
        return client._session._request_once(
            "GET",
            "https://query1.finance.yahoo.com/synthetic",
        )

    monkeypatch.setattr(YFinanceClient, "_statements", guarded_request)
    monkeypatch.setattr(
        "sys.argv",
        ["check_stock.py", "AAPL", "--date", "2024-12-31", "--agents", "burry"],
    )

    with pytest.raises(SystemExit) as denied:
        check_stock.main()

    assert denied.value.code == 2
    assert "--root" in capsys.readouterr().err


def test_stock_check_free_default_panel_uses_root_bound_guarded_clients(
    enrolled_root,
    monkeypatch,
    capsys,
):
    import check_stock
    import hedge_fund.data
    import hedge_fund.llm
    import hedge_fund.runtime.endpoints

    events = []
    dispatches = []
    monkeypatch.setattr(
        hedge_fund.runtime.endpoints,
        "_resolve_system",
        lambda _host, _port: ["93.184.216.34"],
    )

    class OfflineData:
        def __init__(self, dispatch):
            self.dispatch = dispatch
            self.target = ProviderTarget(kind="data", provider="yfinance")

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def _authorize(self):
            self.dispatch.authorize_transport(
                self.target,
                url="https://query1.finance.yahoo.com/synthetic",
                method="GET",
            )
            self.dispatch.recheck_transport_fence(self.target)
            events.append("data")

        def get_financial_metrics(self, ticker, end_date, period="ttm", limit=20):
            self._authorize()
            return [
                FinancialMetrics(
                    ticker=ticker,
                    report_period=day,
                    period=period,
                    return_on_equity=0.1,
                )
                for day in ("2024-12-31", "2024-09-30", "2024-06-30", "2024-03-31")
            ]

        def get_company_facts(self, ticker):
            self._authorize()
            return CompanyFacts(ticker=ticker, sector="Synthetic")

        def get_earnings_history(self, ticker, limit=12):
            self._authorize()
            return []

    def data_factory(*, provider, dispatch, api_key):
        assert provider == "yfinance"
        assert api_key is None
        assert isinstance(dispatch, ProviderDispatch)
        dispatches.append(dispatch)
        return OfflineData(dispatch)

    class OfflineLLM:
        def __init__(self, model, dispatch, endpoint):
            self.model = model
            self.dispatch = dispatch
            self.target = ProviderTarget(
                kind="llm",
                provider="ollama",
                model=model,
                endpoint=endpoint,
            )

        def complete(self, _system, _user):
            self.dispatch.authorize_transport(
                self.target,
                url="http://127.0.0.1:11434/api/chat",
                method="POST",
            )
            self.dispatch.recheck_transport_fence(self.target)
            events.append("llm")
            return '{"signal":"bullish","confidence":80,"reasoning":"synthetic"}'

    def llm_factory(*, model, dispatch, endpoint, api_key, use_environment, **_kwargs):
        assert api_key is None
        assert use_environment is False
        assert isinstance(dispatch, ProviderDispatch)
        return OfflineLLM(model, dispatch, endpoint)

    monkeypatch.setattr(hedge_fund.data, "make_data_client", data_factory)
    monkeypatch.setattr(hedge_fund.llm, "make_llm", llm_factory)

    check_stock.main(_arguments(enrolled_root))
    output = capsys.readouterr()
    assert all(name in output.out for name in ("burry", "pabrai", "damodaran", "ackman", "pead"))
    assert events.count("data") == 3
    assert events.count("llm") == 4
    assert (enrolled_root / "cache" / "data").is_dir()
    assert len(list((enrolled_root / "cache" / "llm").glob("*.json"))) == 4

    check_stock.main(_arguments(enrolled_root))
    second_output = capsys.readouterr()
    assert second_output.out.count("(cached)") == 4
    assert events.count("data") == 3
    assert events.count("llm") == 4
    assert len(dispatches) == 2
    assert all(dispatch.root_id and dispatch.operation_id for dispatch in dispatches)


def test_earnings_cache_refreshes_across_stock_checks_on_reused_root(enrolled_root, monkeypatch):
    import check_stock
    import hedge_fund.data
    import hedge_fund.data.cached as cached
    import hedge_fund.llm
    import hedge_fund.runtime.endpoints
    from hedge_fund.data.models import EarningsRecord

    now = datetime(2026, 10, 30, 12, tzinfo=cached.NEW_YORK)

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return now.astimezone(tz)

    monkeypatch.setattr(cached, "datetime", Clock)
    monkeypatch.setattr(
        hedge_fund.runtime.endpoints,
        "_resolve_system",
        lambda _host, _port: ["93.184.216.34"],
    )
    clients = []
    results = []

    class FakeRawClient:
        def __init__(self):
            self.closed = False
            self.calls = 0

        def __enter__(self):
            return self

        def __exit__(self, *_exc_info):
            self.closed = True

        def get_earnings_history(self, ticker, limit=12):
            self.calls += 1
            return [
                EarningsRecord(
                    ticker=ticker,
                    report_period="2026-09-30",
                    source_type="8-K",
                    filing_date=now.date().isoformat(),
                )
            ]

    def fake_data_client(*, provider, dispatch, api_key):
        assert provider == "yfinance"
        assert api_key is None
        assert isinstance(dispatch, ProviderDispatch)
        assert dispatch.root_id and dispatch.operation_id
        client = FakeRawClient()
        clients.append(client)
        return client

    def read_earnings(ticker, as_of, data_client, agents):
        assert [agent.name for agent in agents] == ["pead"]
        assert data_client._dir == enrolled_root / "cache" / "data"
        results.append(data_client.get_earnings_history(ticker))

    monkeypatch.setattr(hedge_fund.data, "make_data_client", fake_data_client)
    monkeypatch.setattr(
        hedge_fund.llm,
        "make_llm",
        Mock(side_effect=AssertionError("earnings cache check must not construct an LLM")),
    )
    monkeypatch.setattr(check_stock, "show_snapshot", lambda *_args: None)
    monkeypatch.setattr(check_stock, "ask_agents", read_earnings)
    arguments = _arguments(enrolled_root) + ["--agents", "pead"]

    check_stock.main(arguments)
    check_stock.main(arguments)
    assert results[1] == results[0]
    assert [client.calls for client in clients] == [1, 0]
    assert all(client.closed for client in clients)

    now += timedelta(days=1, seconds=cached.SAME_DAY_TTL + 1)
    check_stock.main(arguments)
    check_stock.main(arguments)
    assert [client.calls for client in clients] == [1, 0, 1, 0]
    assert results[2][0].filing_date != results[0][0].filing_date
    assert results[3] == results[2]
    assert all(client.closed for client in clients)
    assert len(list((enrolled_root / "cache" / "data").glob("*.json"))) == 1


@pytest.mark.parametrize(
    ("paid_arguments", "message"),
    [
        ([], "paid dispatch requires --authorize-paid-provider fd"),
        (["--authorize-paid-provider", "fd"], "requires --confirm-fd-self-service-pricing"),
        (
            ["--authorize-paid-provider", "fd", "--confirm-fd-self-service-pricing"],
            "paid call bound",
        ),
        (
            [
                "--authorize-paid-provider",
                "fd",
                "--confirm-fd-self-service-pricing",
                "--paid-max-calls",
                "1",
                "--paid-max-cost-usd",
                "1",
            ],
            "paid total and per-attempt cost bounds are required",
        ),
        (
            [
                "--authorize-paid-provider",
                "fd",
                "--confirm-fd-self-service-pricing",
                "--paid-max-calls",
                "1",
                "--paid-max-cost-usd",
                "1",
                "--paid-max-attempt-cost-usd",
                "0.16",
            ],
            "paid provider credential is not saved under this root",
        ),
        (_paid_data_budget("0", "1", "0.16"), "paid call bound must be between 1 and 10000"),
        (_paid_data_budget("10001", "1", "0.16"), "paid call bound must be between 1 and 10000"),
        (_paid_data_budget("101", "100", "0.16"), "paid call bound exceeds the operation estimate"),
        (_paid_data_budget("1", "100.01", "0.16"), "paid cost bounds exceed the allowed finite range"),
        (_paid_data_budget("1", "1", "NaN"), "paid cost bounds exceed the allowed finite range"),
        (_paid_data_budget("1", "1", "0.159999"), "per-attempt cost bound is below"),
        (_paid_data_budget("100", "100", "10"), "paid provider credential is not saved under this root"),
    ],
)
def test_stock_check_paid_data_denies_without_explicit_bounded_consent(
    enrolled_root,
    monkeypatch,
    capsys,
    paid_arguments,
    message,
):
    import check_stock
    import hedge_fund.data
    import hedge_fund.llm

    forbidden = Mock(side_effect=AssertionError("provider effect before consent"))
    monkeypatch.setattr(hedge_fund.data, "make_data_client", forbidden)
    monkeypatch.setattr(hedge_fund.llm, "make_llm", forbidden)
    monkeypatch.setenv("HEDGE_FUND_DATA_PROVIDER", "fd")
    monkeypatch.setenv("FINANCIAL_DATASETS_API_KEY", "synthetic-ambient-key")

    with pytest.raises(SystemExit) as denied:
        check_stock.main(_arguments(enrolled_root) + paid_arguments)

    output = capsys.readouterr()
    assert denied.value.code == 2
    assert message in output.err
    assert "synthetic-ambient-key" not in output.out + output.err
    assert forbidden.call_count == 0
    assert not (enrolled_root / "cache").exists()


@pytest.mark.parametrize(
    ("minutes", "message"),
    [
        ("0", "one-shot deadline must be between 1 and 1440 minutes"),
        ("1", "paid dispatch requires --authorize-paid-provider fd"),
        ("1440", "paid dispatch requires --authorize-paid-provider fd"),
        ("1441", "one-shot deadline must be between 1 and 1440 minutes"),
    ],
)
def test_stock_check_enforces_deadline_boundaries_before_provider_effects(
    enrolled_root,
    monkeypatch,
    capsys,
    minutes,
    message,
):
    import check_stock
    import hedge_fund.data

    forbidden = Mock(side_effect=AssertionError("provider effect before consent"))
    monkeypatch.setattr(hedge_fund.data, "make_data_client", forbidden)
    monkeypatch.setenv("HEDGE_FUND_DATA_PROVIDER", "fd")

    with pytest.raises(SystemExit) as denied:
        check_stock.main(_arguments(enrolled_root) + ["--deadline-minutes", minutes])

    assert denied.value.code == 2
    assert message in capsys.readouterr().err
    assert forbidden.call_count == 0
    assert not (enrolled_root / "cache").exists()


def test_stock_check_denies_network_without_explicit_consent(enrolled_root, monkeypatch, capsys):
    import check_stock
    import hedge_fund.data

    forbidden = Mock(side_effect=AssertionError("provider constructed without consent"))
    monkeypatch.setattr(hedge_fund.data, "make_data_client", forbidden)
    arguments = [arg for arg in _arguments(enrolled_root) if arg != "--enable-network"]

    with pytest.raises(SystemExit) as denied:
        check_stock.main(arguments)

    assert denied.value.code == 2
    assert "explicit --enable-network" in capsys.readouterr().err
    assert forbidden.call_count == 0
    assert not (enrolled_root / "cache").exists()


@pytest.mark.parametrize(
    "arguments",
    [
        ["AAPL/extra"],
        ["AAPL", "--date", "2024-02-30"],
        ["AAPL", "--date", "20241231"],
        ["AAPL", "--agents", "burry,unknown"],
        ["AAPL", "--agents", "burry,"],
    ],
)
def test_stock_check_rejects_invalid_inputs_before_provider_effects(
    enrolled_root,
    monkeypatch,
    arguments,
):
    import check_stock
    import hedge_fund.data
    import hedge_fund.llm

    forbidden = Mock(side_effect=AssertionError("provider constructed for invalid input"))
    monkeypatch.setattr(hedge_fund.data, "make_data_client", forbidden)
    monkeypatch.setattr(hedge_fund.llm, "make_llm", forbidden)

    with pytest.raises(SystemExit) as denied:
        check_stock.main(arguments + ["--root", str(enrolled_root), "--enable-network"])

    assert denied.value.code == 2
    assert forbidden.call_count == 0
    assert not (enrolled_root / "cache").exists()


def test_stock_check_rejects_unenrolled_root_before_provider_effects(tmp_path, monkeypatch):
    import check_stock
    import hedge_fund.data

    root = tmp_path / "unenrolled"
    root.mkdir()
    forbidden = Mock(side_effect=AssertionError("provider constructed for unenrolled root"))
    monkeypatch.setattr(hedge_fund.data, "make_data_client", forbidden)

    with pytest.raises(SystemExit) as denied:
        check_stock.main(_arguments(root))

    assert denied.value.code == 2
    assert forbidden.call_count == 0
    assert not (root / "cache").exists()


def test_analyst_authorization_denial_is_not_swallowed(capsys):
    import check_stock

    class DeniedAgent:
        name = "denied"

        def predict(self, *_args):
            raise AuthorizationDenied("synthetic denial")

    class UnexpectedAgent:
        name = "unexpected"

        def predict(self, *_args):
            pytest.fail("analyst execution continued after authorization denial")

    with pytest.raises(AuthorizationDenied):
        check_stock.ask_agents("AAPL", "2024-12-31", object(), [DeniedAgent(), UnexpectedAgent()])

    assert "unexpected" not in capsys.readouterr().out


@pytest.mark.parametrize("error_kind", ["data", "llm", "root", "ledger", "handover"])
def test_analyst_infrastructure_failures_abort_without_retry(capsys, error_kind):
    import check_stock
    from hedge_fund.data.protocol import DataClientError
    from hedge_fund.llm.client import LLMCallError
    from hedge_fund.paper.ledger import LedgerError
    from hedge_fund.runtime.handover import HandoverError
    from hedge_fund.runtime.root import RootConfigurationError

    error_type = {
        "data": DataClientError,
        "llm": LLMCallError,
        "root": RootConfigurationError,
        "ledger": LedgerError,
        "handover": HandoverError,
    }[error_kind]

    class FailedAgent:
        name = "failed"

        def predict(self, *_args):
            raise error_type("synthetic infrastructure failure")

    class UnexpectedAgent:
        name = "unexpected"

        def predict(self, *_args):
            pytest.fail("analyst execution continued after infrastructure failure")

    with pytest.raises(error_type):
        check_stock.ask_agents("AAPL", "2024-12-31", object(), [FailedAgent(), UnexpectedAgent()])

    assert "unexpected" not in capsys.readouterr().out


@pytest.mark.parametrize("error", [ValueError("synthetic"), RuntimeError("synthetic")])
def test_reported_analyst_error_does_not_skip_other_analysts(capsys, error):
    import check_stock
    from hedge_fund.models import Signal

    class BrokenAgent:
        name = "broken"

        def predict(self, *_args):
            raise error

    class WorkingAgent:
        name = "working"

        def predict(self, *_args):
            return Signal(model_name="working", ticker="AAPL", date="2024-12-31", value=0.5)

    check_stock.ask_agents("AAPL", "2024-12-31", object(), [BrokenAgent(), WorkingAgent()])

    output = capsys.readouterr().out
    assert "broken" in output and "ERROR" in output and type(error).__name__ in output
    assert "working" in output and "+0.50" in output


def test_quant_only_stock_check_does_not_authorize_unused_cloud_llm(
    enrolled_root,
    monkeypatch,
    capsys,
):
    import check_stock
    import hedge_fund.data
    import hedge_fund.llm
    import hedge_fund.runtime.endpoints

    monkeypatch.setattr(
        hedge_fund.runtime.endpoints,
        "_resolve_system",
        lambda _host, _port: ["93.184.216.34"],
    )
    dispatches = []
    effects = []

    class OfflineData:
        def __init__(self, dispatch):
            self.dispatch = dispatch

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def get_earnings_history(self, *_args, **_kwargs):
            target = ProviderTarget(kind="data", provider="yfinance")
            self.dispatch.authorize_transport(
                target,
                url="https://query1.finance.yahoo.com/synthetic",
                method="GET",
            )
            self.dispatch.recheck_transport_fence(target)
            effects.append("fake-data")
            return []

    def data_factory(*, provider, dispatch, api_key):
        assert provider == "yfinance" and api_key is None
        dispatches.append(dispatch)
        return OfflineData(dispatch)

    monkeypatch.setattr(hedge_fund.data, "make_data_client", data_factory)
    monkeypatch.setattr(hedge_fund.llm, "make_llm", Mock(side_effect=AssertionError("unused LLM")))
    monkeypatch.setattr(check_stock, "show_snapshot", lambda *_args: None)

    check_stock.main(_arguments(enrolled_root) + ["--agents", "pead", "--model", "gpt-6-sol"])

    assert "pead" in capsys.readouterr().out
    assert effects == ["fake-data"]
    cloud_target = ProviderTarget(kind="llm", provider="openai", model="gpt-6-sol")
    with pytest.raises(AuthorizationDenied):
        dispatches[0].validate_target(cloud_target)


@pytest.mark.parametrize("failure", ["malformed-control", "paper-permission"])
def test_stock_check_inventory_failure_denies_before_any_llm_effect(
    enrolled_root,
    monkeypatch,
    capsys,
    failure,
):
    from types import SimpleNamespace

    import check_stock
    import hedge_fund.data
    import hedge_fund.llm
    import hedge_fund.runtime.endpoints
    from hedge_fund.fund import FundSpec
    from hedge_fund.llm.client import ChatLLM
    from hedge_fund.paper.deployed import deploy
    from hedge_fund.runtime.admission import AdmissionCoordinator, RootOwnerLease

    spec = FundSpec.model_validate(
        {
            "schema_version": 2,
            "name": "alpha",
            "strategies": [{"name": "solo", "models": [{"name": "pead"}], "blend": {"mode": "long_short"}}],
            "risk": {"max_position_pct": 1, "max_gross_exposure": 1},
            "capital": 100_000,
            "rebalance": "daily",
        }
    )
    with RootContext.open(enrolled_root) as root, RootOwnerLease.acquire(root) as owner:
        admission = AdmissionCoordinator(root, owner_lease=owner)
        with admission.deployment_lock("alpha"):
            deploy("alpha", spec, ["AAPL"], root=root.path / "paper")

    monkeypatch.setattr(
        hedge_fund.runtime.endpoints,
        "_resolve_system",
        lambda _host, _port: ["93.184.216.34"],
    )
    attempts = []
    effects = []

    class OfflineData:
        def __init__(self, dispatch):
            self.dispatch = dispatch

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def _authorize(self):
            target = ProviderTarget(kind="data", provider="yfinance")
            self.dispatch.authorize_transport(
                target,
                url="https://query1.finance.yahoo.com/synthetic",
                method="GET",
            )
            self.dispatch.recheck_transport_fence(target)

        def get_financial_metrics(self, ticker, end_date, period="ttm", limit=20):
            self._authorize()
            return [FinancialMetrics(ticker=ticker, report_period=day, period=period, return_on_equity=0.1) for day in ("2024-12-31", "2024-09-30", "2024-06-30", "2024-03-31")]

        def get_company_facts(self, ticker):
            self._authorize()
            return CompanyFacts(ticker=ticker, sector="Synthetic")

    monkeypatch.setattr(
        hedge_fund.data,
        "make_data_client",
        lambda *, provider, dispatch, api_key: OfflineData(dispatch),
    )

    def llm_factory(*, model, dispatch, endpoint, **_kwargs):
        target = ProviderTarget(kind="llm", provider="ollama", model=model, endpoint=endpoint)

        class FakeChat:
            def invoke(self, _messages):
                attempts.append("invoked")
                dispatch.authorize_transport(target, url="http://127.0.0.1:11434/api/chat", method="POST")
                dispatch.recheck_transport_fence(target)
                effects.append("llm-transport")
                return SimpleNamespace(content='{"signal":"neutral","confidence":50,"reasoning":"fake"}')

        return ChatLLM(model, FakeChat(), dispatch=dispatch, target=target)

    monkeypatch.setattr(hedge_fund.llm, "make_llm", llm_factory)
    show_snapshot = check_stock.show_snapshot

    original_iterdir = Path.iterdir

    def deny_paper_iteration(path):
        if path == enrolled_root / "paper":
            raise PermissionError("synthetic inventory read failure")
        return original_iterdir(path)

    def corrupt_after_admission(*args):
        show_snapshot(*args)
        if failure == "malformed-control":
            (enrolled_root / "paper" / "alpha" / "control.json").write_text("{invalid", encoding="utf-8")
        else:
            monkeypatch.setattr(Path, "iterdir", deny_paper_iteration)

    monkeypatch.setattr(check_stock, "show_snapshot", corrupt_after_admission)

    with pytest.raises(SystemExit) as denied:
        check_stock.main(_arguments(enrolled_root) + ["--agents", "burry,pabrai"])

    assert denied.value.code == 1
    assert "provider operation denied" in capsys.readouterr().err
    assert attempts == ["invoked"]
    assert effects == []
    if failure == "malformed-control":
        with RootContext.open(enrolled_root) as root:
            from hedge_fund.runtime.handover import enrollment_status

            assert enrollment_status(root, verify_inventory=True)["state"] == "drift"


def test_stock_check_stops_after_first_failed_bounded_paid_transport(
    enrolled_root,
    monkeypatch,
    capsys,
):
    import httpx

    import check_stock
    import hedge_fund.data
    import hedge_fund.llm
    import hedge_fund.runtime.endpoints
    from hedge_fund.llm.client import JevLLM
    from hedge_fund.runtime.credentials import CredentialStore

    monkeypatch.setattr(
        hedge_fund.runtime.endpoints,
        "_resolve_system",
        lambda _host, _port: ["93.184.216.34"],
    )
    monkeypatch.setattr(CredentialStore, "version", lambda _self, _name: (1, True))
    monkeypatch.setattr(CredentialStore, "read_version", lambda _self, _name, _version: "synthetic-key")
    paid_attempts = []

    class OfflineData:
        def __init__(self, dispatch):
            self.dispatch = dispatch

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def _authorize(self):
            target = ProviderTarget(kind="data", provider="yfinance")
            self.dispatch.authorize_transport(
                target,
                url="https://query1.finance.yahoo.com/synthetic",
                method="GET",
            )
            self.dispatch.recheck_transport_fence(target)

        def get_financial_metrics(self, ticker, end_date, period="ttm", limit=20):
            self._authorize()
            return [FinancialMetrics(ticker=ticker, report_period=day, period=period, return_on_equity=0.1) for day in ("2024-12-31", "2024-09-30", "2024-06-30", "2024-03-31")]

        def get_company_facts(self, ticker):
            self._authorize()
            return CompanyFacts(ticker=ticker, sector="Synthetic")

    monkeypatch.setattr(
        hedge_fund.data,
        "make_data_client",
        lambda *, provider, dispatch, api_key: OfflineData(dispatch),
    )

    def llm_factory(*, model, dispatch, api_key, **_kwargs):
        target = ProviderTarget(kind="llm", provider="typesafe", model=model)
        client = JevLLM(api_key, model, dispatch=dispatch, target=target)
        client._http_client.close()

        def failed_transport(request):
            paid_attempts.append("synthetic-paid-request")
            raise httpx.ConnectError("synthetic transport failure", request=request)

        client._http_client = httpx.Client(transport=httpx.MockTransport(failed_transport))
        return client

    monkeypatch.setattr(hedge_fund.llm, "make_llm", llm_factory)
    arguments = _arguments(enrolled_root) + [
        "--agents",
        "burry,pabrai",
        "--model",
        "jev-1.13.0",
        "--authorize-paid-provider",
        "typesafe",
        "--paid-max-calls",
        "2",
        "--paid-max-cost-usd",
        "2",
        "--paid-max-attempt-cost-usd",
        "1",
    ]

    with pytest.raises(SystemExit) as failed:
        check_stock.main(arguments)

    output = capsys.readouterr()
    assert failed.value.code == 1
    assert "provider request failed" in output.err
    assert "synthetic-key" not in output.out + output.err
    assert paid_attempts == ["synthetic-paid-request"]


def test_stock_check_rechecks_root_inventory_before_each_transport(
    enrolled_root,
    monkeypatch,
    capsys,
):
    import check_stock
    import hedge_fund.data
    import hedge_fund.runtime.endpoints

    monkeypatch.setattr(
        hedge_fund.runtime.endpoints,
        "_resolve_system",
        lambda _host, _port: ["93.184.216.34"],
    )
    effects = []

    class OfflineData:
        def __init__(self, dispatch):
            self.dispatch = dispatch

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def get_earnings_history(self, *_args, **_kwargs):
            self.dispatch.authorize_transport(
                ProviderTarget(kind="data", provider="yfinance"),
                url="https://query1.finance.yahoo.com/synthetic",
                method="GET",
            )
            effects.append("transport")
            return []

    monkeypatch.setattr(
        hedge_fund.data,
        "make_data_client",
        lambda *, provider, dispatch, api_key: OfflineData(dispatch),
    )

    def introduce_external_drift(*_args):
        unknown = enrolled_root / "paper" / "unknown"
        unknown.mkdir(parents=True)
        (unknown / "unrecognized").write_text("synthetic drift", encoding="utf-8")

    monkeypatch.setattr(check_stock, "show_snapshot", introduce_external_drift)

    with pytest.raises(SystemExit) as denied:
        check_stock.main(_arguments(enrolled_root) + ["--agents", "pead"])

    assert denied.value.code == 1
    assert "provider operation denied" in capsys.readouterr().err
    assert effects == []
