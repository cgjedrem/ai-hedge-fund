"""Every provider must construct, and every response shape must flatten.

The constructor tests are the point: a wrong kwarg name for one provider is a
TypeError that would otherwise surface only mid-run, after minutes of warming.
Nothing here touches the network — building a langchain chat model does not
call the API.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import httpx
import pytest
import requests

from hedge_fund.data.client import FDClientError
from hedge_fund.llm import ChatLLM
from hedge_fund.llm import client as client_module
from hedge_fund.llm import (
    contract,
    LLMCallError,
    LLMClient,
    load_api_models,
    make_llm,
    prompt_key,
    PromptCache,
    provider_for,
    SUPPORTED_PROVIDERS,
)
from hedge_fund.llm.client import _flatten, JevLLM
from hedge_fund.llm.registry import PROVIDER_ENV_VARS
from hedge_fund.llm.test_contract import _response
from hedge_fund.runtime.dispatch import make_one_shot_dispatch, ProviderDispatch
from hedge_fund.runtime.policy import (
    AuthorizationDenied,
    classify_provider,
    ProviderTarget,
)
from hedge_fund.signals import ALPHA_MODEL_REGISTRY, BuffettAgent, LLMAgent, MungerAgent
from hedge_fund.signals.test_llm_agents import (
    _history,
    BULLISH,
    FakeLLM,
    MockDataClient,
)

# One model id per provider, taken from the registry so this test fails loudly
# if a provider is dropped from api_models.json.
_BY_PROVIDER = {provider: model for _, model, provider in load_api_models() if provider in SUPPORTED_PROVIDERS and (provider != "Ollama" or model == "gemma3:4b")}


@pytest.fixture
def keyed(monkeypatch):
    """Every provider key present, so make_llm gets past its key check."""
    for env_var in PROVIDER_ENV_VARS.values():
        monkeypatch.setenv(env_var, "test-key-not-real")
    monkeypatch.delenv("HEDGE_FUND_LLM_MODEL", raising=False)
    monkeypatch.delenv("OPENAI_API_BASE", raising=False)


@pytest.mark.parametrize("provider", sorted(SUPPORTED_PROVIDERS))
def test_every_supported_provider_constructs(provider, keyed):
    """A supported provider builds a client with the model id it was given."""
    model_id = _BY_PROVIDER.get(provider)
    assert model_id, f"{provider} is supported but absent from the registry"
    llm = _authorized_make_llm(model_id)
    assert llm.model == model_id
    assert hasattr(llm, "complete")


def test_registry_and_clients_agree():
    """Every provider in the registry is one we can actually reach — the
    picker greys out the rest, so a mismatch means a dead row or a broken run.
    """
    listed = {prov for _, _, prov in load_api_models() if prov in SUPPORTED_PROVIDERS}
    assert listed.intersection(SUPPORTED_PROVIDERS) == SUPPORTED_PROVIDERS


@pytest.mark.parametrize(
    "provider",
    ["DeepSeek", "Kimi", "OpenAI", "xAI"],
)
def test_cloud_langchain_clients_disable_retries(provider, keyed):
    client = _authorized_make_llm(_BY_PROVIDER[provider])

    assert client._chat.max_retries == 0


@pytest.mark.parametrize(
    "provider",
    ["DeepSeek", "Kimi", "OpenAI", "xAI"],
)
def test_cloud_langchain_transport_denies_unknown_cost_before_inner_http(
    provider,
    keyed,
    http,
):
    client = _authorized_make_llm(_BY_PROVIDER[provider])

    with pytest.raises(AuthorizationDenied, match="upper-bound cost is unknown") as caught:
        client.complete("system", "user")

    assert "test-key-not-real" not in str(caught.value)
    http[0].assert_not_called()
    authorization = client._dispatch._one_shot[client._target.identity]
    assert authorization.calls_reserved == 0


def test_missing_captured_key_denies_even_when_a_provider_is_selected(monkeypatch):
    monkeypatch.delenv("HEDGE_FUND_LLM_MODEL", raising=False)
    for env_var in PROVIDER_ENV_VARS.values():
        monkeypatch.delenv(env_var, raising=False)
    monkeypatch.delenv("MOONSHOT_API_KEY", raising=False)
    with pytest.raises(AuthorizationDenied, match="captured provider credential"):
        _authorized_make_llm("gpt-6-sol")


def test_ambient_key_cannot_supply_captured_provider_credential(monkeypatch):
    target = _authorized_target("jev-1.13.0")
    monkeypatch.setenv("TYPESAFE_API_KEY", API_KEY)

    with pytest.raises(AuthorizationDenied, match="captured provider credential"):
        make_llm("jev-1.13.0", dispatch=_dispatch(target))


def test_missing_dispatch_denies_before_provider_construction(keyed, monkeypatch):
    import langchain_openai

    construct = Mock(side_effect=AssertionError("provider constructed without operation authority"))
    monkeypatch.setattr(langchain_openai, "ChatOpenAI", construct)

    with pytest.raises(AuthorizationDenied, match="operation authorization"):
        make_llm(
            _BY_PROVIDER["OpenAI"],
            api_key="fixture-only-key",
        )

    construct.assert_not_called()


def test_unlisted_model_fails_closed():
    with pytest.raises(AuthorizationDenied, match="provider is unknown"):
        make_llm("unlisted-model")


def test_kimi_accepts_moonshot_key(monkeypatch):
    """v1 reads MOONSHOT_API_KEY first; the same .env must work here."""
    monkeypatch.delenv("HEDGE_FUND_LLM_MODEL", raising=False)
    monkeypatch.delenv("KIMI_API_KEY", raising=False)
    monkeypatch.setenv("MOONSHOT_API_KEY", "test-key-not-real")
    assert _authorized_make_llm(_BY_PROVIDER["Kimi"]).model == _BY_PROVIDER["Kimi"]


def test_ollama_needs_no_key(monkeypatch):
    """The free local path runs with every API key unset."""
    monkeypatch.delenv("HEDGE_FUND_LLM_MODEL", raising=False)
    for env_var in (*PROVIDER_ENV_VARS.values(), "MOONSHOT_API_KEY"):
        monkeypatch.delenv(env_var, raising=False)
    llm = _authorized_make_llm(_BY_PROVIDER["Ollama"])
    assert llm.model == _BY_PROVIDER["Ollama"]
    assert hasattr(llm, "complete")


def test_temperature_reaches_the_chat_model(keyed):
    """make_llm's temperature lands on the underlying chat model."""
    llm = _authorized_make_llm(_BY_PROVIDER["Kimi"], temperature=0.7)
    assert llm._chat.temperature == 0.7


def test_temperature_none_keeps_provider_default(keyed):
    llm = _authorized_make_llm(_BY_PROVIDER["Kimi"])
    assert llm._chat.temperature is None


def test_ollama_receives_captured_generation_context_and_endpoint(monkeypatch):
    monkeypatch.setenv("OLLAMA_NUM_CTX", "4096")
    llm = _authorized_make_llm(
        "gemma3:4b",
        timeout=17,
        max_tokens=1024,
        temperature=0.4,
        top_p=0.8,
        context_size=16384,
        endpoint="http://127.0.0.1:11434",
        use_environment=False,
    )

    assert llm._chat.num_ctx == 16384
    assert llm._chat.num_predict == 1024
    assert llm._chat.temperature == 0.4
    assert llm._chat.top_p == 0.8
    assert llm._chat.base_url == "http://127.0.0.1:11434"


def test_typesafe_accepts_and_ignores_temperature(monkeypatch):
    """TypeSafe has no sampling knob; the factory takes the kwarg and drops it."""
    monkeypatch.delenv("HEDGE_FUND_LLM_MODEL", raising=False)
    monkeypatch.setenv("TYPESAFE_API_KEY", API_KEY)
    llm = _authorized_make_llm("jev-1.13.0", temperature=0.7)
    assert isinstance(llm, JevLLM)


def test_prompt_key_salt_is_legacy_compatible():
    """An empty salt reproduces the legacy key; any salt namespaces it."""
    assert prompt_key("a", "m", "s", "u") == prompt_key("a", "m", "s", "u", "")
    assert prompt_key("a", "m", "s", "u") != prompt_key("a", "m", "s", "u", "sample=1")
    assert prompt_key("a", "m", "s", "u", "temperature=0.7") != prompt_key("a", "m", "s", "u", "sample=1")


def test_salted_key_namespaces_a_provider_key():
    from hedge_fund.llm import salted_key

    base = "abcdef1234567890abcdef12"
    assert salted_key(base, "") != base  # a salted key is never the bare base
    assert salted_key(base, "sample=1") == salted_key(base, "sample=1")
    assert salted_key(base, "sample=1") != salted_key(base, "sample=2")


def test_provider_for_reads_the_registry():
    assert provider_for("claude-opus-5-5") == "Anthropic"
    assert provider_for("claude-fable-5-1") == "Anthropic"
    assert provider_for("gpt-6-sol") == "OpenAI"
    assert provider_for("gpt-6-astra") == "OpenAI"
    assert provider_for("not-a-model") is None


class FakeChunk:
    def __init__(self, content) -> None:
        self.content = content


class FakeChat:
    """Records which path was taken, so a test can prove streaming happened."""

    def __init__(self, chunks: list) -> None:
        self._chunks = chunks
        self.streamed = False
        self.invoked = False

    def invoke(self, messages):
        self.invoked = True
        return FakeChunk("".join(c.content if isinstance(c.content, str) else "" for c in self._chunks))

    def stream(self, messages):
        self.streamed = True
        yield from self._chunks


class TestStreaming:
    """A listener changes how the text arrives, never what comes back — the
    prompt cache and the parse must not be able to tell the difference.
    """

    def test_no_listener_does_not_stream(self):
        chat = FakeChat([FakeChunk("done")])
        assert _chat_client("gemma3:4b", chat).complete("s", "u") == "done"
        assert chat.invoked and not chat.streamed

    def test_listener_sees_every_piece_and_the_return_is_whole(self):
        chat = FakeChat([FakeChunk('{"sig'), FakeChunk('nal": '), FakeChunk('"buy"}')])
        seen: list[str] = []
        result = _chat_client("gemma3:4b", chat, seen.append).complete("s", "u")
        assert chat.streamed
        assert seen == ['{"sig', 'nal": ', '"buy"}']
        assert result == '{"signal": "buy"}'

    def test_chunk_blocks_join_without_a_separator(self):
        """Whole-message blocks join on a newline; stream blocks are fragments
        of one continuing string, and a newline would land mid-word."""
        chat = FakeChat([FakeChunk([{"type": "text", "text": "mo"}, {"type": "text", "text": "at"}])])
        assert _chat_client("gemma3:4b", chat, lambda _: None).complete("s", "u") == "moat"

    def test_thinking_chunks_reach_neither_the_listener_nor_the_result(self):
        chat = FakeChat(
            [
                FakeChunk([{"type": "thinking", "thinking": "weighing margins"}]),
                FakeChunk([{"type": "text", "text": "verdict"}]),
            ]
        )
        seen: list[str] = []
        assert _chat_client("gemma3:4b", chat, seen.append).complete("s", "u") == "verdict"
        assert seen == ["verdict"]

    def test_make_llm_passes_the_listener_through(self, keyed):
        """The TUI builds its agents with make_llm(on_token=...), so the
        listener has to survive the factory."""

        def listener(text: str) -> None:
            pass

        assert _authorized_make_llm("gpt-6-sol", on_token=listener)._on_token is listener


class TestFlatten:
    """Response shapes, matching v1's extract_json_from_response."""

    def test_plain_string_passes_through(self):
        assert _flatten('{"signal": "bullish"}') == '{"signal": "bullish"}'

    def test_text_blocks_are_joined(self):
        blocks = [{"type": "text", "text": '{"a":'}, {"type": "text", "text": " 1}"}]
        assert _flatten(blocks) == '{"a":\n 1}'

    def test_thinking_blocks_are_dropped(self):
        """The whole reason this exists: a reasoning block stringified into
        the payload is prose in front of the JSON, and the parse fails."""
        blocks = [
            {"type": "thinking", "thinking": "Let me weigh the margins..."},
            {"type": "text", "text": '{"signal": "bearish"}'},
        ]
        assert _flatten(blocks) == '{"signal": "bearish"}'

    def test_bare_strings_in_a_list_are_kept(self):
        assert _flatten(["a", "b"]) == "a\nb"

    def test_unknown_block_types_are_dropped_not_stringified(self):
        blocks = [{"type": "tool_use", "id": "x"}, {"type": "text", "text": "ok"}]
        assert _flatten(blocks) == "ok"

    def test_none_becomes_empty(self):
        assert _flatten(None) == ""


# Jev native transport and shared-agent integration.

API_KEY = "test-typesafe-secret-key"
_NOW = datetime(2026, 11, 1, 12, 0, tzinfo=timezone.utc)


def test_local_reasoning_fallback_reserves_each_transport():
    target = _authorized_target(
        "gemma3:4b",
        "http://127.0.0.1:11434",
    )
    dispatch = _dispatch(target)
    calls = []

    def handle(request):
        calls.append(request)
        return httpx.Response(200, json={}, request=request)

    with dispatch.httpx_client(
        target,
        inner_transport=httpx.MockTransport(handle),
    ) as client:

        class ReasoningChat:
            reasoning = True

            def __init__(self, no_think=False):
                self.no_think = no_think

            def model_copy(self, update):
                return ReasoningChat(no_think=update["reasoning"] is False)

            def invoke(self, _messages):
                client.get("http://127.0.0.1:11434/api/generate")
                return SimpleNamespace(content="answer" if self.no_think else "")

        model = ChatLLM(
            "gemma3:4b",
            ReasoningChat(),
            dispatch=dispatch,
            target=target,
        )
        assert model.complete("system", "user") == "answer"

    authorization = dispatch._one_shot[target.identity]
    assert len(calls) == authorization.calls_reserved == 2
    assert authorization.resources_reserved == 2


def _authorized_target(model, endpoint=None):
    provider = provider_for(model)
    if provider is None:
        raise ValueError("fixture model is not registered")
    return ProviderTarget(
        kind="llm",
        provider=provider.casefold(),
        model=model,
        endpoint=endpoint,
    )


def _dispatch(target):
    local = (
        classify_provider(
            target,
            approved_local_models={"gemma3:4b"},
        ).value
        == "local"
    )
    cost = Decimal("0") if local else Decimal("0.10")
    return make_one_shot_dispatch(
        root_id="llm-test-root",
        subject_id="llm-test",
        capture_digest="a" * 64,
        operation_id=f"llm-{uuid4().hex}",
        operation_digest="b" * 64,
        expires_at=_NOW + timedelta(hours=1),
        targets=(target,),
        max_calls=100,
        max_cost=Decimal("10.00"),
        max_resources=100,
        upper_bound_costs={target.identity: cost},
        approved_local_models={"gemma3:4b"},
        clock=lambda: _NOW,
        resolver=lambda _host, _port: ["8.8.8.8"],
    )


def _authorized_make_llm(model=None, **kwargs):
    selected = model or os.environ.get("HEDGE_FUND_LLM_MODEL") or client_module.DEFAULT_MODEL
    target = _authorized_target(selected, kwargs.get("endpoint"))
    provider = provider_for(selected)
    if "api_key" not in kwargs and provider not in {"Ollama", None}:
        key = os.environ.get("MOONSHOT_API_KEY") if provider == "Kimi" else None
        key = key or os.environ.get(PROVIDER_ENV_VARS.get(provider, ""))
        if key:
            kwargs["api_key"] = key
    return make_llm(model, dispatch=_dispatch(target), **kwargs)


def _jev_client(api_key=API_KEY, *, model="jev-1.13.0", timeout=60):
    target = _authorized_target(model)
    return JevLLM(
        api_key,
        model=model,
        timeout=timeout,
        dispatch=_dispatch(target),
        target=target,
    )


def test_jev_constructor_requires_model_bound_to_authorization():
    target = _authorized_target("jev-1.13.0")
    dispatch = _dispatch(target)

    with pytest.raises(AuthorizationDenied, match="TypeSafe model"):
        JevLLM(API_KEY, model="jev-9.99.0", dispatch=dispatch, target=target)


def _chat_client(model, chat, on_token=None):
    target = _authorized_target("gemma3:4b")
    return ChatLLM(
        model,
        chat,
        on_token,
        dispatch=_dispatch(target),
        target=target,
    )


@pytest.mark.parametrize("use_environment", [False, True])
def test_factory_routes_jev_with_only_its_key(use_environment, monkeypatch, http):
    for variable in (*PROVIDER_ENV_VARS.values(), "MOONSHOT_API_KEY", "HEDGE_FUND_LLM_MODEL"):
        monkeypatch.delenv(variable, raising=False)
    monkeypatch.setenv("TYPESAFE_API_KEY", API_KEY)
    # If routing regresses, fail at chat construction rather than making a call.
    import langchain_anthropic
    import langchain_openai

    monkeypatch.setattr(langchain_anthropic, "ChatAnthropic", Mock(side_effect=AssertionError("chat construction")))
    monkeypatch.setattr(langchain_openai, "ChatOpenAI", Mock(side_effect=AssertionError("chat construction")))
    if use_environment:
        monkeypatch.setenv("HEDGE_FUND_LLM_MODEL", "jev-1.13.0")
    listener = Mock()
    llm = _authorized_make_llm(None if use_environment else "jev-1.13.0", timeout=17, max_tokens=1, on_token=listener)
    assert isinstance(llm, JevLLM)
    assert provider_for(llm.model) == "TypeSafe"
    assert ("Jev", "jev-1.13.0", "TypeSafe") in load_api_models()
    _serve(http, _http_response())
    llm.complete("investor", "snapshot")
    assert http[0].call_args.kwargs["timeout"] == 17
    assert "max_tokens" not in http[0].call_args.kwargs["json"]
    listener.assert_not_called()


def test_factory_missing_jev_key_names_variable(monkeypatch):
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    with pytest.raises(AuthorizationDenied, match="captured provider credential"):
        _authorized_make_llm("jev-1.13.0")


def test_cli_paid_fd_backtest_uses_captured_dispatch_and_saved_result(
    tmp_path,
    monkeypatch,
    http,
    capsys,
):
    """CLI paid data uses root credential and guarded requests; no live I/O."""
    import sys
    from datetime import date, timedelta
    from urllib.parse import parse_qs, urlsplit

    from hedge_fund import paths, run
    from hedge_fund.backtesting import FundBacktestResult
    from hedge_fund.backtesting.test_fund import FakeAnalyst
    from hedge_fund.data import CachedDataClient, make_data_client
    from hedge_fund.fund import Fund
    from hedge_fund.runtime.admission import AdmissionCoordinator, RootOwnerLease
    from hedge_fund.runtime.credentials import CredentialStore
    from hedge_fund.runtime.handover import enroll_fresh
    from hedge_fund.runtime.policy import ProviderTarget
    from hedge_fund.runtime.root import RootContext

    monkeypatch.chdir(tmp_path)
    for variable in (*PROVIDER_ENV_VARS.values(), "MOONSHOT_API_KEY", "FINANCIAL_DATASETS_API_KEY"):
        monkeypatch.delenv(variable, raising=False)
    monkeypatch.setenv("HEDGE_FUND_DATA_PROVIDER", "fd")
    with RootContext.open(tmp_path) as root:
        enroll_fresh(root)
        owner = RootOwnerLease.acquire(root)
        try:
            admission = AdmissionCoordinator(root, owner_lease=owner)
            store = CredentialStore(root, admission)
            store.save("fd", "fixture-only-fd-credential", expected_version=0)
        finally:
            owner.close()
    monkeypatch.setattr(run, "ensure_mandates_dir", lambda: tmp_path)
    monkeypatch.setattr(paths, "RESEARCH_DIR", tmp_path / "research")
    monkeypatch.setattr(run, "make_data_client", make_data_client)
    monkeypatch.setattr(run, "CachedDataClient", CachedDataClient)

    def fake_fund(spec, _settings, _dispatch, _api_key):
        return Fund(
            spec,
            models={strategy.name: [FakeAnalyst(model.name, {"AAPL": 0.8, "MSFT": -0.4}) for model in strategy.models] for strategy in spec.strategies},
        )

    monkeypatch.setattr(run, "_cli_fund", fake_fund)

    class FrozenDateTime:
        @classmethod
        def now(cls, tz=None):
            fixed = datetime(2026, 11, 1, 12, 0, tzinfo=timezone.utc)
            return fixed if tz is None else fixed.astimezone(tz)

    monkeypatch.setattr(run, "datetime", FrozenDateTime)
    monkeypatch.setattr(run, "uuid4", lambda: SimpleNamespace(hex="1" * 32))
    authorizer = run._authorize_cli_operation
    authorizations = []

    def capture_authorization(*args, **kwargs):
        kwargs["resolver"] = lambda _host, _port: ["8.8.8.8"]
        authority = authorizer(*args, **kwargs)
        authorizations.append(authority)
        return authority

    monkeypatch.setattr(run, "_authorize_cli_operation", capture_authorization)

    def fd_prices(request):
        params = parse_qs(urlsplit(str(request.url)).query)
        start = date.fromisoformat(params["start_date"][0])
        end = date.fromisoformat(params["end_date"][0])
        rows = []
        current = start
        while current <= end:
            if current.weekday() < 5:
                close = 100.0 + (current - date(2025, 1, 14)).days
                rows.append(
                    {
                        "open": close,
                        "high": close,
                        "low": close,
                        "close": close,
                        "volume": 1000,
                        "time": f"{current.isoformat()}T00:00:00Z",
                    }
                )
            current += timedelta(days=1)
        return httpx.Response(
            200,
            json={"prices": rows},
            request=request,
        )

    _serve(http, *(fd_prices for _ in range(100)))
    mandate = tmp_path / "fund.yaml"
    mandate.write_text(
        """schema_version: 2
name: fd-cli-test
strategies:
  - name: value
    blend:
      mode: long_short
    models:
      - name: druckenmiller
risk:
  max_position_pct: 0.25
  max_gross_exposure: 1.0
capital: 100000
"""
    )

    def set_backtest_args(start, end):
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "aihf",
                "--root",
                str(tmp_path),
                "--enable-network",
                "--model",
                "gemma3:4b",
                "backtest",
                str(mandate),
                "--universe",
                "AAPL,MSFT",
                "--start",
                start,
                "--end",
                end,
                "--authorize-paid-provider",
                "fd",
                "--confirm-fd-self-service-pricing",
                "--paid-max-calls",
                "100",
                "--paid-max-cost-usd",
                "10.00",
                "--paid-max-attempt-cost-usd",
                "0.16",
            ],
        )

    set_backtest_args("2025-01-14", "2025-01-15")
    run.main()
    captured = capsys.readouterr()
    result = FundBacktestResult.model_validate_json(captured.out)
    assert [r.session for r in result.records] == ["2025-01-14", "2025-01-15"]
    assert result.records[0].decision is not None
    assert result.records[1].executed is not None
    assert result.records[1].executed.positions["AAPL"] > 0
    assert result.records[1].executed.positions["MSFT"] < 0
    assert "Paid dispatch authorized: fd" in captured.err
    assert "fixture-only-fd-credential" not in captured.out + captured.err
    assert len(list((tmp_path / "research").glob("fd-cli-test-2025-01-14-2025-01-15-*.json"))) == 1
    first_transport_calls = http[0].call_count
    assert 0 < first_transport_calls <= 100
    assert all(call.kwargs["headers"]["X-API-Key"] == "fixture-only-fd-credential" for call in http[0].calls)
    target = ProviderTarget(kind="data", provider="fd")
    reservation = authorizations[0]["dispatch"]._one_shot[target.identity]
    first_operation_digest = authorizations[0]["dispatch"].operation_digest
    assert reservation.calls_reserved == first_transport_calls
    assert reservation.cost_reserved == reservation.calls_reserved * Decimal("0.16")

    http[0].calls.clear()
    _serve(http, *(fd_prices for _ in range(100)))
    set_backtest_args("2025-01-14", "2025-01-16")
    run.main()
    second_captured = capsys.readouterr()
    second_result = FundBacktestResult.model_validate_json(second_captured.out)
    assert [r.session for r in second_result.records] == ["2025-01-14", "2025-01-15", "2025-01-16"]
    assert len(list((tmp_path / "research").glob("fd-cli-test-2025-01-14-2025-01-16-*.json"))) == 1
    assert "fixture-only-fd-credential" not in second_captured.out + second_captured.err
    second_transport_calls = http[0].call_count
    assert 0 < second_transport_calls <= 100
    second_reservation = authorizations[1]["dispatch"]._one_shot[target.identity]
    assert second_reservation.calls_reserved == second_transport_calls
    assert second_reservation.cost_reserved == second_reservation.calls_reserved * Decimal("0.16")
    assert authorizations[1]["dispatch"].operation_digest != first_operation_digest


def _http_response(body=None, status=200, raw=None, retry_after=None):
    content = (raw if raw is not None else json.dumps(body if body is not None else _response())).encode()
    headers = {"content-type": "application/json"}
    if retry_after is not None:
        headers["Retry-After"] = retry_after
    return httpx.Response(status, content=content, headers=headers)


class _GuardedHTTPRecorder:
    def __init__(self):
        self.responses = []
        self.calls = []
        self.authorizations = []

    @property
    def side_effect(self):
        return self.responses

    @side_effect.setter
    def side_effect(self, responses):
        self.responses = list(responses)

    @property
    def call_count(self):
        return len(self.calls)

    @property
    def call_args(self):
        return self.calls[-1] if self.calls else None

    def handle(self, request, timeout):
        body = json.loads(request.content) if request.content else None
        headers = {}
        authorization = request.headers.get("authorization")
        api_key = request.headers.get("x-api-key")
        if authorization is not None:
            self.authorizations.append(authorization)
            headers["Authorization"] = authorization
        if api_key is not None:
            headers["X-API-Key"] = api_key
        kwargs = {
            "json": body,
            "headers": headers,
            "timeout": timeout,
            "allow_redirects": False,
        }
        self.calls.append(SimpleNamespace(args=(str(request.url),), kwargs=kwargs))
        if not self.responses:
            raise AssertionError("Unexpected guarded HTTP call")
        response = self.responses.pop(0)
        if callable(response):
            response = response(request)
        if isinstance(response, BaseException):
            if isinstance(response, requests.Timeout):
                raise httpx.TimeoutException(str(response), request=request)
            if isinstance(response, requests.RequestException):
                raise httpx.ConnectError(str(response), request=request)
            if isinstance(response, httpx.RequestError):
                raise response
            raise response
        return httpx.Response(
            response.status_code,
            content=response.content,
            headers=dict(response.headers),
            request=request,
        )

    def assert_called_once(self):
        assert self.call_count == 1

    def assert_called_once_with(self, *args, **kwargs):
        self.assert_called_once()
        assert self.call_args.args == args
        assert self.call_args.kwargs == kwargs

    def assert_not_called(self):
        assert self.call_count == 0


@pytest.fixture
def http(monkeypatch):
    recorder = _GuardedHTTPRecorder()
    sleep = Mock()
    original = ProviderDispatch.httpx_client

    def guarded_client(dispatch, target, *, timeout=60.0, inner_transport=None):
        transport = inner_transport or httpx.MockTransport(lambda request: recorder.handle(request, timeout))
        return original(
            dispatch,
            target,
            timeout=timeout,
            inner_transport=transport,
        )

    monkeypatch.setattr(ProviderDispatch, "httpx_client", guarded_client)
    monkeypatch.setattr(client_module.time, "sleep", sleep)
    return recorder, sleep


def _serve(http, *responses):
    http[0].side_effect = responses


def _agent(tmp_path, persona=BuffettAgent):
    return persona(llm=_jev_client(), cache=PromptCache(tmp_path))


def test_native_request_and_auditable_compatibility_response(http):
    raw = json.dumps(_response(), indent=2) + "\n"
    _serve(http, _http_response(raw=raw))
    llm = _jev_client(timeout=12)
    assert isinstance(llm, LLMClient)
    payload = json.loads(llm.complete(" investor prompt\n", "financial snapshot\n"))
    request = contract.build_jev_request(" investor prompt\n", "financial snapshot\n", "jev-1.13.0")
    http[0].assert_called_once_with(
        JevLLM.ENDPOINT,
        json=request,
        headers={"Authorization": f"Bearer {API_KEY}"},
        timeout=12,
        allow_redirects=False,
    )
    http[1].assert_not_called()
    assert payload["signal"] == "bullish" and payload["confidence"] == 80
    assert "No written thesis generated" in payload["reasoning"]
    metadata = payload["provider_metadata"]["jev"]
    assert metadata["request"] == request
    assert metadata["response"] == _response()
    assert metadata["raw_response"] == raw
    assert metadata["contract_version"] == contract.JEV_CONTRACT_VERSION
    assert http[0].calls[0].kwargs["headers"]["Authorization"] == f"Bearer {API_KEY}"
    assert metadata["attempt_count"] == 1 and metadata["status_code"] == 200
    assert metadata["elapsed_seconds"] >= 0
    assert llm.model == "jev-1.13.0"
    assert API_KEY not in json.dumps(payload)


def test_jev_sends_captured_key_only_in_guarded_authorization_header(http):
    _serve(http, _http_response(_response()))

    result = _jev_client().complete("s", "u")

    assert http[0].authorizations == [f"Bearer {API_KEY}"]
    assert API_KEY not in result


@pytest.mark.parametrize("key", [None, "", " \t\n"])
def test_empty_key_is_rejected(key, http):
    with pytest.raises(ValueError, match="non-empty TypeSafe API key"):
        JevLLM(key)
    http[0].assert_not_called()


@pytest.mark.parametrize("timeout", [0, -1, True, float("inf"), float("nan")])
def test_timeout_is_bounded(timeout):
    with pytest.raises(ValueError, match="timeout"):
        JevLLM(API_KEY, timeout=timeout)


@pytest.mark.parametrize("status", [429, 500, 502, 503, 504, 529])
def test_transient_http_failure_is_not_retried(status, http):
    _serve(http, _http_response(status=status), _http_response(status=status))
    with pytest.raises(LLMCallError, match=f"HTTP {status}") as caught:
        _jev_client().complete("s", "u")
    assert caught.value.diagnostic_record["attempt_count"] == 1
    http[0].assert_called_once()
    http[1].assert_not_called()


def test_retry_after_is_ignored(http):
    _serve(http, _http_response(status=429, retry_after="61"), _http_response(status=429))
    with pytest.raises(LLMCallError, match="HTTP 429") as caught:
        _jev_client().complete("s", "u")
    assert caught.value.diagnostic_record["attempt_count"] == 1
    http[0].assert_called_once()
    http[1].assert_not_called()


@pytest.mark.parametrize("status", [401, 403, 422, 429, 529])
def test_http_failures_have_one_attempt(status, http):
    _serve(
        http,
        _http_response(status=status, raw="failure"),
        _http_response(status=status, raw="failure"),
    )
    with pytest.raises(LLMCallError, match=f"HTTP {status}") as caught:
        _jev_client().complete("s", "u")
    record = caught.value.diagnostic_record
    assert record["status_code"] == status
    assert record["raw_response"] == "failure"
    assert record["failure_category"] == "http"
    assert record["attempt_count"] == http[0].call_count == 1
    http[1].assert_not_called()


def test_redirect_is_denied_by_guarded_transport(http):
    _serve(http, _http_response(status=302), _http_response(status=200))
    with pytest.raises(AuthorizationDenied, match="redirects are disabled"):
        _jev_client().complete("s", "u")
    http[0].assert_called_once()


@pytest.mark.parametrize("exception", [requests.Timeout, requests.ConnectionError])
def test_network_failures_do_not_retry_or_leak_credentials(exception, http):
    _serve(http, exception(f"Authorization: Bearer {API_KEY}"))
    with pytest.raises(LLMCallError) as caught:
        _jev_client().complete("s", "u")
    assert caught.value.diagnostic_record["failure_category"] == "transport"
    assert caught.value.diagnostic_record["status_code"] is None
    assert caught.value.diagnostic_record["raw_response"] is None
    assert API_KEY not in str(caught.value)
    assert API_KEY not in json.dumps(caught.value.diagnostic_record)
    assert caught.value.__suppress_context__ is True
    http[0].assert_called_once()
    http[1].assert_not_called()


@pytest.mark.parametrize("raw,category", [("<html>bad gateway</html>", "json_decode"), ('{"answers": {}}', "contract")])
def test_invalid_success_response_is_not_retried(raw, category, http):
    _serve(http, _http_response(raw=raw))
    with pytest.raises(LLMCallError) as caught:
        _jev_client().complete("s", "u")
    record = caught.value.diagnostic_record
    assert record["raw_response"] == raw
    assert record["status_code"] == 200
    assert record["failure_category"] == category
    http[0].assert_called_once()
    http[1].assert_not_called()


def test_echoed_key_is_redacted_from_success_and_failure_metadata(http):
    native = _response()
    native["debug"] = {API_KEY: [API_KEY]}
    _serve(http, _http_response(native), _http_response(status=401, raw=f"Invalid key: {API_KEY}"))
    llm = _jev_client()
    result = llm.complete("s", "u")
    assert API_KEY not in result
    assert "[REDACTED]" in result
    with pytest.raises(LLMCallError) as caught:
        llm.complete("s", "u")
    assert caught.value.diagnostic_record["raw_response"] == "Invalid key: [REDACTED]"


@pytest.mark.parametrize("persona", [cls for cls in ALPHA_MODEL_REGISTRY.values() if issubclass(cls, LLMAgent)], ids=lambda cls: cls.__name__)
@pytest.mark.parametrize("direction,strength,expected", [("bullish", 3.2, 0.8), ("bearish", 1.6, -0.4), ("neutral", 4, 0), ("bullish", 0, 0), ("bearish", 0, 0)])
def test_every_agent_maps_and_replays_native_metadata(persona, direction, strength, expected, tmp_path, http):
    native = _response(direction, bullish=strength, bearish=strength)
    raw = json.dumps(native, indent=2)
    _serve(http, _http_response(raw=raw))
    agent = _agent(tmp_path, persona)
    data = MockDataClient(metrics=_history())
    first = agent.predict("TEST", "2025-01-15", data)
    # Use a fresh client/agent to prove replay does not depend on live state.
    second = _agent(tmp_path, persona).predict("TEST", "2025-02-20", data)
    assert first.value == second.value == pytest.approx(expected)
    assert second.date == "2025-02-20"
    assert first.metadata["signal"] == second.metadata["signal"] == direction
    assert first.metadata["abstained"] is second.metadata["abstained"] is False
    assert first.metadata["cached"] is False and second.metadata["cached"] is True
    assert first.metadata["provider_metadata"] == second.metadata["provider_metadata"]
    assert first.metadata["provider_metadata"]["jev"]["response"] == native
    record = PromptCache(tmp_path).get(first.metadata["prompt_key"])
    assert record["parsed"]["provider_metadata"] == first.metadata["provider_metadata"]
    assert record["system"] == agent.get_system_prompt()
    audit = record["parsed"]["provider_metadata"]["jev"]
    assert audit["raw_response"] == raw
    assert audit["request"]["state"] == {"investor_prompt": record["system"], "financial_snapshot": record["user"]}
    assert json.loads(record["response"])["provider_metadata"] == first.metadata["provider_metadata"]
    http[0].assert_called_once()


@pytest.mark.parametrize("change", ["snapshot", "persona", "model", "questions", "version"])
def test_changed_semantics_miss_cache(change, tmp_path, http, monkeypatch):
    _serve(http, _http_response(), _http_response())
    agent = _agent(tmp_path)
    data = MockDataClient(metrics=_history())
    first = agent.predict("TEST", "2025-01-15", data)
    if change == "snapshot":
        data = MockDataClient(metrics=_history(7))
    elif change == "persona":
        agent = _agent(tmp_path, MungerAgent)
    elif change == "model":
        agent._llm.model = "jev-another-version"
        snapshot = agent.build_snapshot("TEST", "2025-01-15", data)
        key = agent._llm.cache_key(
            agent.name,
            agent.get_system_prompt(),
            agent.build_user_prompt(snapshot),
        )
        assert key != first.metadata["prompt_key"]
        http[0].assert_called_once()
        return
    elif change == "version":
        monkeypatch.setattr(contract, "JEV_CONTRACT_VERSION", contract.JEV_CONTRACT_VERSION + 1)
    else:
        build = contract.build_jev_request

        def changed(*args):
            request = build(*args)
            request["questions"]["bullish_strength"]["criteria"][0] += " Changed rubric."
            return request

        monkeypatch.setattr(contract, "build_jev_request", changed)
    second = agent.predict("TEST", "2025-01-15", data)
    assert second.metadata["cached"] is False
    assert first.metadata["prompt_key"] != second.metadata["prompt_key"]
    assert http[0].call_count == 2


def test_cache_identity_excludes_credentials_and_timeout_but_includes_agent_and_endpoint(monkeypatch):
    llm = _jev_client()
    baseline = llm.cache_key("buffett", "system", "user")
    assert baseline == _jev_client("other-secret", timeout=5).cache_key("buffett", "system", "user")
    assert baseline != llm.cache_key("munger", "system", "user")
    assert baseline != llm.cache_key("buffett", "changed system", "user")
    assert baseline != llm.cache_key("buffett", "system", "changed user")
    monkeypatch.setattr(llm, "ENDPOINT", "https://example.invalid/changed")
    assert baseline != llm.cache_key("buffett", "system", "user")


@pytest.mark.parametrize("failure", ["http", "transport", "json_decode", "contract"])
def test_failure_diagnostics_abstain_then_retry_successfully(failure, tmp_path, http, caplog):
    failed = {
        "http": _http_response(status=401, raw=f"Invalid key: {API_KEY}"),
        "transport": requests.Timeout(API_KEY),
        "json_decode": _http_response(raw="invalid json"),
        "contract": _http_response({"answers": {}}),
    }[failure]
    _serve(http, failed, _http_response())
    agent = _agent(tmp_path)
    data = MockDataClient(metrics=_history())
    first = agent.predict("TEST", "2025-01-15", data)
    assert first.value == 0 and first.metadata["abstained"] is True
    record = PromptCache(tmp_path).get(first.metadata["prompt_key"])
    assert "parsed" not in record
    assert record["diagnostics"]["failure_category"] == failure
    assert record["diagnostics"]["request"]["state"]["investor_prompt"] == agent.get_system_prompt()
    assert record["diagnostics"]["elapsed_seconds"] >= 0
    assert API_KEY not in json.dumps(record) + first.reasoning + caplog.text
    second = agent.predict("TEST", "2025-01-15", data)
    assert second.value == 0.8 and second.metadata["abstained"] is False
    assert second.metadata["cached"] is False
    assert second.metadata["prompt_key"] == first.metadata["prompt_key"]
    assert http[0].call_count == 2


def test_data_errors_propagate_and_insufficient_history_skips_http(tmp_path, http):
    agent = _agent(tmp_path)
    with pytest.raises(FDClientError):
        agent.predict("TEST", "2025-01-15", MockDataClient(error=FDClientError("offline")))
    signal = agent.predict("TEST", "2025-01-15", MockDataClient(metrics=[]))
    assert signal.metadata["abstained"] is True
    http[0].assert_not_called()


@pytest.mark.parametrize("flavor", ["fake", "chat"])
def test_legacy_clients_keep_keys_and_signal_shape(flavor, tmp_path):
    chat = Mock()
    chat.invoke.return_value.content = BULLISH
    llm = FakeLLM(BULLISH) if flavor == "fake" else _chat_client("legacy-chat", chat)
    agent = BuffettAgent(llm=llm, cache=PromptCache(tmp_path))
    data = MockDataClient(metrics=_history())
    snapshot = agent.build_snapshot("TEST", "2025-01-15", data)
    key = prompt_key(agent.name, llm.model, agent.get_system_prompt(), agent.build_user_prompt(snapshot))
    first = agent.predict("TEST", "2025-01-15", data)
    second = agent.predict("TEST", "2025-01-15", data)
    assert first.value == second.value == 0.8
    assert first.metadata["prompt_key"] == key
    assert set(first.metadata) == {"signal", "confidence", "model", "prompt_key", "snapshot_hash", "cached", "abstained"}
    assert PromptCache(tmp_path).get(key)["parsed"] == json.loads(BULLISH)
    assert second.metadata["cached"] is True


def test_provider_metadata_cannot_override_signal_fields(tmp_path):
    metadata = {"abstained": True, "confidence": 0, "cached": True, "model": "wrong", "signal": "bearish"}
    payload = {**json.loads(BULLISH), "provider_metadata": metadata}
    agent = BuffettAgent(llm=FakeLLM(json.dumps(payload)), cache=PromptCache(tmp_path))
    signal = agent.predict("TEST", "2025-01-15", MockDataClient(metrics=_history()))
    assert signal.value == 0.8
    assert signal.metadata["abstained"] is signal.metadata["cached"] is False
    assert signal.metadata["confidence"] == 80
    assert signal.metadata["signal"] == "bullish"
    assert signal.metadata["model"] == "fake-model"
    assert signal.metadata["provider_metadata"] == metadata


def test_invalid_provider_metadata_is_a_parse_failure(tmp_path):
    payload = {**json.loads(BULLISH), "provider_metadata": []}
    agent = BuffettAgent(llm=FakeLLM(json.dumps(payload)), cache=PromptCache(tmp_path))
    signal = agent.predict("TEST", "2025-01-15", MockDataClient(metrics=_history()))
    assert signal.metadata["abstained"] is True
    assert "provider_metadata" in signal.metadata["abstain_reason"]


def test_ordinary_call_error_without_diagnostics_preserves_failure_shape(tmp_path):
    agent = BuffettAgent(llm=FakeLLM(error=LLMCallError("failed")), cache=PromptCache(tmp_path))
    signal = agent.predict("TEST", "2025-01-15", MockDataClient(metrics=_history()))
    assert signal.metadata == {"abstained": True, "abstain_reason": "LLM call failed: failed", "cached": False}
    assert not list(tmp_path.glob("*.json"))
