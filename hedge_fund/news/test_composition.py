"""Offline acceptance tests for production analyst composition."""

from __future__ import annotations

import argparse
import io
from types import SimpleNamespace

from rich.console import Console

from hedge_fund import paths
from hedge_fund.data.cached import CachedDataClient
from hedge_fund.news.client import CuratedNewsDataClient
from hedge_fund.news.store import NewsStore
from hedge_fund.runtime.handover import enroll_fresh
from hedge_fund.runtime.root import RootContext


class _RawContext:
    def __init__(self, client):
        self.client = client

    def __enter__(self):
        return self.client

    def __exit__(self, *_args):
        return False


class _BacktestResult:
    start = "2026-01-05"
    end = "2026-01-06"
    dates = []
    records = []
    metrics = SimpleNamespace(
        n_cycles=0,
        n_orders=0,
        trading_cost=0,
        traded_notional=0,
        total_return_pct=0,
        benchmark_return_pct=0,
        sharpe_ratio=0,
        max_drawdown_pct=0,
    )

    def model_dump_json(self, *, indent):
        assert indent == 2
        return "{}"


class _Owner:
    def close(self):
        return None


def test_backtest_constructs_cached_curated_adapter_around_the_raw_client(monkeypatch, tmp_path):
    from hedge_fund import run
    from hedge_fund.runtime.admission import AdmissionCoordinator, RootOwnerLease

    root_path = tmp_path / "synthetic-backtest"
    root_path.mkdir()
    raw = object()
    captured = []
    args = SimpleNamespace(
        universe="ACME",
        mandate="synthetic.yaml",
        rebalance=None,
        start="2026-01-05",
        end="2026-01-06",
        out=None,
    )
    spec = SimpleNamespace(name="Synthetic fund", rebalance="monthly", benchmark="SPY")
    monkeypatch.setattr(run, "_universe", lambda *_args: ["ACME"])
    monkeypatch.setattr(paths, "resolve_user_path", lambda value: value)
    monkeypatch.setattr(run, "load_spec", lambda _path: spec)
    monkeypatch.setattr(run, "_override_rebalance", lambda spec, _value: spec)
    monkeypatch.setattr("hedge_fund.fund.model_call_bounds", lambda _spec: (1, 0))
    monkeypatch.setattr(
        run,
        "_cli_settings",
        lambda _root, _args, _parser: (SimpleNamespace(data_provider="synthetic"), object()),
    )
    monkeypatch.setattr(
        run,
        "_authorize_cli_operation",
        lambda *_args, **_kwargs: {
            "llm_key": None,
            "data_key": None,
            "paid_provider": None,
            "dispatch": object(),
        },
    )
    monkeypatch.setattr(run, "_cli_fund", lambda *_args: object())
    monkeypatch.setattr(run, "make_data_client", lambda **_kwargs: _RawContext(raw))
    monkeypatch.setattr(run, "CachedDataClient", CachedDataClient)

    def capture_backtest(_fund, _start, _end, client, _universe):
        captured.append(client)
        return _BacktestResult()

    monkeypatch.setattr(run, "backtest_fund", capture_backtest)
    monkeypatch.setattr(run, "save_result", lambda _result, admission: "synthetic-result")
    monkeypatch.setattr(run, "score", lambda _records: {})
    monkeypatch.setattr(run, "cost_line", lambda *_args: "no cost")
    monkeypatch.setattr(run, "analyst_table", lambda _score: "analysts")
    monkeypatch.setattr(run, "strategy_table", lambda _score: "strategies")
    monkeypatch.setattr(RootOwnerLease, "acquire", lambda *_args, **_kwargs: _Owner())
    monkeypatch.setattr(AdmissionCoordinator, "__init__", lambda self, *_args, **_kwargs: None)

    with RootContext.open(root_path) as root:
        monkeypatch.setattr(paths, "root_context", lambda: root)
        run._backtest(args, argparse.ArgumentParser(), Console(file=io.StringIO()), root)

    assert len(captured) == 1
    client = captured[0]
    assert isinstance(client, CuratedNewsDataClient)
    assert isinstance(client.client, CachedDataClient)
    assert client.client._client is raw
    assert isinstance(client.store, NewsStore)
    assert client.store.root.path == root_path


def test_owned_runner_reads_local_news_without_scheduling_a_refresh(monkeypatch, tmp_path):
    from hedge_fund.news.refresh import NewsRefresher
    from hedge_fund.runtime import owned_runner_child as runner

    root_path = tmp_path / "synthetic-runner"
    root_path.mkdir()
    raw = object()
    dispatch = object()
    monkeypatch.setattr(runner, "make_data_client", lambda **_kwargs: _RawContext(raw))

    def unexpected_refresh(*_args, **_kwargs):
        raise AssertionError("scheduled analyst retrieval must not refresh news")

    monkeypatch.setattr(NewsRefresher, "refresh", unexpected_refresh)
    with RootContext.open(root_path) as root:
        context = runner._client_context(
            root,
            SimpleNamespace(data_provider="synthetic"),
            None,
            dispatch,
        )
        with context as client:
            assert isinstance(client, CuratedNewsDataClient)
            assert isinstance(client.client, CachedDataClient)
            assert client.client._client is raw
            assert client.store.root is root
            assert client.get_news("ACME", "2026-01-31", "2026-01-01") == []


def test_owned_runner_preserves_an_injected_client_context(monkeypatch, tmp_path):
    from hedge_fund.runtime import owned_runner_child as runner

    root_path = tmp_path / "synthetic-injected-runner"
    root_path.mkdir()
    raw = object()
    injected = _RawContext(raw)
    factory_calls = []

    def factory(_capture, _root, _dispatch):
        factory_calls.append(True)
        return injected

    monkeypatch.setattr(
        runner,
        "make_data_client",
        lambda **_kwargs: (_ for _ in ()).throw(AssertionError("default factory must not run")),
    )
    with RootContext.open(root_path) as root:
        context = runner._client_context(
            root,
            SimpleNamespace(data_provider="synthetic"),
            factory,
            object(),
        )
        assert context is injected
        with context as client:
            assert client is raw
    assert factory_calls == [True]


def test_web_default_context_constructs_cached_curated_adapter(monkeypatch, tmp_path):
    from hedge_fund.news.test_transport import dispatch_for
    from hedge_fund.runtime.policy import ProviderTarget
    from hedge_fund.web import services
    from hedge_fund.web.services import DeskService

    root_path = tmp_path / "synthetic-web"
    root_path.mkdir()
    raw = object()
    monkeypatch.setattr(services, "make_data_client", lambda **_kwargs: _RawContext(raw))
    dispatch = dispatch_for(ProviderTarget(kind="data", provider="yahoo"))

    with RootContext.open(root_path) as root:
        enroll_fresh(root)
        service = DeskService(
            root_path,
            allow_writes=True,
            network_enabled=True,
            root_context=root,
        )
        try:
            with service._make_data_client("yahoo", dispatch=dispatch) as client:
                assert isinstance(client, CuratedNewsDataClient)
                assert isinstance(client.client, CachedDataClient)
                assert client.client._client is raw
                assert client.store.root is root
                assert client.get_news("ACME", "2026-01-31", "2026-01-01") == []
        finally:
            service.close()


def test_web_preserves_dispatch_guard_around_an_injected_client(tmp_path):
    from hedge_fund.news.test_transport import dispatch_for
    from hedge_fund.runtime.policy import ProviderTarget
    from hedge_fund.web.services import _DispatchGuardedInjectedDataClient, DeskService

    root_path = tmp_path / "synthetic-injected-web"
    root_path.mkdir()
    raw = object()
    dispatch = dispatch_for(ProviderTarget(kind="data", provider="yfinance"))

    with RootContext.open(root_path) as root:
        enroll_fresh(root)
        service = DeskService(
            root_path,
            allow_writes=True,
            network_enabled=True,
            data_client_factory=lambda: _RawContext(raw),
            root_context=root,
        )
        try:
            with service._make_data_client("yahoo", dispatch=dispatch) as client:
                assert isinstance(client, _DispatchGuardedInjectedDataClient)
                assert not isinstance(client, CuratedNewsDataClient)
                assert client._client is raw
        finally:
            service.close()
