"""LLMAgent + BuffettAgent tests — fake LLM and data client, no network."""

import json

import pytest

from hedge_fund.data.client import FDClientError
from hedge_fund.data.models import CompanyNews, FinancialMetrics
from hedge_fund.features.breakpoints import MEBreakpoints
from hedge_fund.llm import PromptCache, extract_json
from hedge_fund.llm.client import LLMParseError
from hedge_fund.models import Signal
from hedge_fund.signals import (
    AckmanAgent,
    BuffettAgent,
    BurryAgent,
    DamodaranAgent,
    FisherAgent,
    JhunjhunwalaAgent,
    PabraiAgent,
    WoodAgent,
)


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------

class FakeLLM:
    """Canned-response LLM; counts calls; can raise instead.

    `responses` serves a sequence (one per call, popped in order) for
    ensemble tests; `response` serves the same answer every call.
    """

    model = "fake-model"

    def __init__(self, response="", error=None, responses=None):
        self._response = response
        self._error = error
        self._responses = list(responses) if responses is not None else None
        self.calls = 0
        self.prompts = []

    def complete(self, system, user):
        self.calls += 1
        self.prompts.append(user)
        if self._error is not None:
            raise self._error
        if self._responses is not None:
            if not self._responses:
                raise AssertionError("FakeLLM ran out of canned responses")
            return self._responses.pop(0)
        return self._response


class MockDataClient:
    def __init__(self, metrics=None, error=None, news=None):
        self._metrics = metrics or []
        self._error = error
        self._news = news

    def get_financial_metrics(self, ticker, end_date, period="ttm", limit=10):
        if self._error is not None:
            raise self._error
        return self._metrics

    def get_company_facts(self, ticker):
        return None

    def get_news(self, ticker, end_date, start_date=None, limit=100):
        return self._news or []


def _history(n=8):
    quarters = ["2024-12-31", "2024-09-30", "2024-06-30", "2024-03-31",
                "2023-12-31", "2023-09-30", "2023-06-30", "2023-03-31"]
    return [
        FinancialMetrics(
            ticker="TEST", report_period=q, period="ttm", filing_date=q,
            return_on_equity=0.2, gross_margin=0.4, book_value_per_share=10.0,
            market_cap=1e9,
        )
        for q in quarters[:n]
    ]


BULLISH = json.dumps({"signal": "bullish", "confidence": 80, "reasoning": "Wonderful business."})


def _agent(tmp_path, llm):
    return BuffettAgent(llm=llm, cache=PromptCache(tmp_path / "llm"))


# ---------------------------------------------------------------------------
# Signal folding
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("signal,confidence,expected", [
    ("bullish", 80, 0.8),
    ("bearish", 60, -0.6),
    ("neutral", 90, 0.0),
])
def test_value_folding(tmp_path, signal, confidence, expected):
    response = json.dumps({"signal": signal, "confidence": confidence, "reasoning": "r"})
    agent = _agent(tmp_path, FakeLLM(response))

    sig = agent.predict("TEST", "2025-01-15", MockDataClient(metrics=_history()))

    assert isinstance(sig, Signal)
    assert sig.model_name == "buffett"
    assert sig.value == pytest.approx(expected)
    assert sig.metadata["abstained"] is False


# ---------------------------------------------------------------------------
# Failure contract
# ---------------------------------------------------------------------------

def test_malformed_json_abstains(tmp_path):
    agent = _agent(tmp_path, FakeLLM("I am bullish, trust me."))
    sig = agent.predict("TEST", "2025-01-15", MockDataClient(metrics=_history()))
    assert sig.value == 0.0
    assert sig.metadata["abstained"] is True


def test_llm_error_abstains(tmp_path):
    agent = _agent(tmp_path, FakeLLM(error=TimeoutError("llm timed out")))
    sig = agent.predict("TEST", "2025-01-15", MockDataClient(metrics=_history()))
    assert sig.value == 0.0
    assert sig.metadata["abstained"] is True
    assert "timed out" in sig.metadata["abstain_reason"]


def test_insufficient_data_abstains(tmp_path):
    agent = _agent(tmp_path, FakeLLM(BULLISH))
    sig = agent.predict("TEST", "2025-01-15", MockDataClient(metrics=_history(2)))
    assert sig.value == 0.0
    assert sig.metadata["abstained"] is True


def test_data_layer_error_propagates(tmp_path):
    """Fail loud: an infrastructure failure must NOT become a neutral view."""
    client = MockDataClient(error=FDClientError("API down", status_code=500))
    agent = _agent(tmp_path, FakeLLM(BULLISH))
    with pytest.raises(FDClientError):
        agent.predict("TEST", "2025-01-15", client)


# ---------------------------------------------------------------------------
# Cache = persistence
# ---------------------------------------------------------------------------

def test_cache_hit_skips_llm_call(tmp_path):
    llm = FakeLLM(BULLISH)
    client = MockDataClient(metrics=_history())
    agent = _agent(tmp_path, llm)

    first = agent.predict("TEST", "2025-01-15", client)
    second = agent.predict("TEST", "2025-01-15", client)

    assert llm.calls == 1  # second predict served from cache
    assert first.value == second.value
    assert first.metadata["cached"] is False
    assert second.metadata["cached"] is True


def test_new_as_of_same_data_hits_cache(tmp_path):
    """A new date with unchanged fundamentals must be free: the snapshot
    renders identically, so the prompt cache hits — no second LLM call."""
    llm = FakeLLM(BULLISH)
    client = MockDataClient(metrics=_history())
    agent = _agent(tmp_path, llm)

    first = agent.predict("TEST", "2025-01-15", client)
    second = agent.predict("TEST", "2025-02-20", client)

    assert llm.calls == 1
    assert second.metadata["cached"] is True
    assert second.date == "2025-02-20"  # Signal date is the predict arg, not the cache's
    assert first.metadata["snapshot_hash"] == second.metadata["snapshot_hash"]


def test_new_filing_forces_new_llm_call(tmp_path):
    """A new filing changes the snapshot — the agent must re-reason."""
    llm = FakeLLM(BULLISH)
    agent = _agent(tmp_path, llm)

    first = agent.predict("TEST", "2025-01-15", MockDataClient(metrics=_history(7)))
    second = agent.predict("TEST", "2025-02-20", MockDataClient(metrics=_history(8)))

    assert llm.calls == 2
    assert first.metadata["snapshot_hash"] != second.metadata["snapshot_hash"]


class BarClient(MockDataClient):
    """Fundamentals plus a day: the quote at the bar, a prior close, headlines."""

    def __init__(self, news=()):
        super().__init__(metrics=_history())
        self.news = list(news)

    def get_prices(self, ticker, start_date, end_date, interval="day", interval_multiplier=1):
        from hedge_fund.data.models import Price
        return [Price(open=100, close=100, high=100, low=100, volume=1, time="2025-01-14T00:00:00Z")]

    def get_snapshot(self, ticker):
        from hedge_fund.data.models import PriceSnapshot
        return PriceSnapshot(ticker=ticker, price=100.0, time="2025-01-15T09:30:00-05:00")

    def get_news(self, ticker, end_date, start_date=None, limit=1000):
        return self.news

    def get_earnings_history(self, ticker, limit=12):
        return []


def test_quiet_bars_share_one_prompt_and_a_headline_changes_it(tmp_path):
    """At a bar the prompt carries the day so far. Two quiet bars render the
    same prompt (one LLM call); a headline landing between them changes it."""
    from hedge_fund.data.models import CompanyNews
    llm = FakeLLM(BULLISH)
    agent = _agent(tmp_path, llm)
    client = BarClient()

    first = agent.predict("TEST", "2025-01-15T09:35:00", client)
    second = agent.predict("TEST", "2025-01-15T09:40:00", client)
    assert llm.calls == 1 and second.metadata["cached"] is True
    record = json.loads(next((tmp_path / "llm").glob("*.json")).read_text())
    assert "Since the previous close:" in record["user"] and "Headlines: none" in record["user"]
    assert "09:35" not in record["user"] and "09:40" not in record["user"]

    client.news.append(CompanyNews(ticker="TEST", title="Guidance cut", source="Wire", date="2025-01-15T14:42:00Z"))
    third = agent.predict("TEST", "2025-01-15T09:45:00", client)
    assert llm.calls == 2 and third.metadata["cached"] is False
    assert third.metadata["prompt_key"] != first.metadata["prompt_key"]
    assert third.metadata["snapshot_hash"] == first.metadata["snapshot_hash"]  # the fundamentals did not move

    # A daily session carries no such block.
    agent.predict("TEST", "2025-01-15", client)
    daily = [json.loads(p.read_text()) for p in (tmp_path / "llm").glob("*.json")
             if json.loads(p.read_text())["as_of"] == "2025-01-15"]
    assert daily and "Since the previous close" not in daily[0]["user"]


def test_prompt_and_response_persisted(tmp_path):
    agent = _agent(tmp_path, FakeLLM(BULLISH))
    agent.predict("TEST", "2025-01-15", MockDataClient(metrics=_history()))

    records = list((tmp_path / "llm").glob("*.json"))
    assert len(records) == 1
    record = json.loads(records[0].read_text())
    assert record["agent"] == "buffett"
    assert "You are Warren Buffett" in record["system"]
    assert "2024-12-31" in record["user"]  # the rendered snapshot
    assert record["response"] == BULLISH
    assert record["parsed"]["signal"] == "bullish"


def test_blind_agent_prompt_withholds_ticker_and_dates(tmp_path):
    # Nov 2024 thresholds 100M..2000M; the $1B history lands on the 50th.
    table = MEBreakpoints({"202411": tuple(100.0 * i for i in range(1, 21))})
    agent = BuffettAgent(llm=FakeLLM(BULLISH), cache=PromptCache(tmp_path / "llm"),
                         blind=True, breakpoints=table)
    signal = agent.predict("TEST", "2025-01-15", MockDataClient(metrics=_history()))

    record = json.loads(next((tmp_path / "llm").glob("*.json")).read_text())
    assert "TEST" not in record["user"]
    assert "2024-12-31" not in record["user"]
    assert "t-0 | " in record["user"]
    # Absolute size and the raw per-share print stay out of the prompt; size
    # is a percentile. Book value is $10 on every row, so the blind
    # column is the index 100.0.
    assert "Market cap" not in record["user"]
    assert "1.0B" not in record["user"]
    assert "Size: market cap at or above the 50th percentile of US stocks" in record["user"]
    assert "10.00" not in record["user"]
    assert "bvps_idx" in record["user"]
    assert "100.0" in record["user"]
    assert signal.ticker == "TEST"  # the Signal still names the ticker


def test_agents_are_not_blind_unless_asked(tmp_path):
    """A live run names the company; only a backtest passes blind=True."""
    agent = _agent(tmp_path, FakeLLM(BULLISH))
    agent.predict("TEST", "2025-01-15", MockDataClient(metrics=_history()))

    record = json.loads(next((tmp_path / "llm").glob("*.json")).read_text())
    assert "Company: TEST" in record["user"]
    assert "2024-12-31" in record["user"]
    assert "percentile" not in record["user"]  # live prompts never load breakpoints


def test_news_enabled_daily_prompt_carries_headlines(tmp_path):
    """news=True adds the week's headlines under the fundamentals; the
    default agent's prompt is unchanged."""
    news_client = MockDataClient(metrics=_history(), news=[
        CompanyNews(ticker="TEST", title="Chip demand surges", source="Reuters",
                    date="2025-01-12T15:00:00Z", url="u"),
    ])
    agent = BuffettAgent(llm=FakeLLM(BULLISH), cache=PromptCache(tmp_path / "llm"),
                         news=True)
    agent.predict("TEST", "2025-01-15", news_client)
    assert "Recent headlines" in agent._llm.prompts[0]
    assert "Chip demand surges" in agent._llm.prompts[0]

    plain = MockDataClient(metrics=_history(), news=[
        CompanyNews(ticker="TEST", title="Chip demand surges", source="Reuters",
                    date="2025-01-12T15:00:00Z", url="u"),
    ])
    default = _agent(tmp_path, FakeLLM(BULLISH))
    default.predict("TEST", "2025-01-15", plain)
    assert "Recent headlines" not in default._llm.prompts[0]


def test_blind_agent_never_sees_news(tmp_path):
    """Headlines name events a model could recall — a blind backtest gets
    neither the block nor even a news call's output."""
    client = MockDataClient(metrics=_history(), news=[
        CompanyNews(ticker="TEST", title="Chip demand surges", source="Reuters",
                    date="2025-01-12T15:00:00Z", url="u"),
    ])
    # Nov 2024 thresholds 100M..2000M; the $1B history lands on the 50th.
    table = MEBreakpoints({"202411": tuple(100.0 * i for i in range(1, 21))})
    agent = BuffettAgent(llm=FakeLLM(BULLISH), cache=PromptCache(tmp_path / "llm"),
                         blind=True, breakpoints=table, news=True)
    agent.predict("TEST", "2025-01-15", client)
    assert "Recent headlines" not in agent._llm.prompts[0]
    assert "Chip demand surges" not in agent._llm.prompts[0]


def test_failed_parse_still_persists_response(tmp_path):
    agent = _agent(tmp_path, FakeLLM("garbage"))
    agent.predict("TEST", "2025-01-15", MockDataClient(metrics=_history()))

    records = list((tmp_path / "llm").glob("*.json"))
    assert len(records) == 1
    record = json.loads(records[0].read_text())
    assert record["response"] == "garbage"
    assert "parse_error" in record


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

def test_registry_names_match_keys(tmp_path):
    """Every registry entry instantiates and reports its own key as name."""
    from hedge_fund.signals import ALPHA_MODEL_REGISTRY, LLMAgent

    for key, cls in ALPHA_MODEL_REGISTRY.items():
        if issubclass(cls, LLMAgent):
            model = cls(llm=FakeLLM(), cache=PromptCache(tmp_path / "llm"))
        else:
            model = cls()
        assert model.name == key


def test_llm_personas_share_the_contract(tmp_path):
    """Every persona prompt keeps the PIT rule and the JSON schema."""
    from hedge_fund.signals import ALPHA_MODEL_REGISTRY, LLMAgent

    for cls in ALPHA_MODEL_REGISTRY.values():
        if not issubclass(cls, LLMAgent):
            continue
        prompt = cls(llm=FakeLLM(), cache=PromptCache(tmp_path / "llm")).get_system_prompt()
        assert "most recent filing date" in prompt  # the point-in-time hard rule
        assert '"signal"' in prompt and '"confidence"' in prompt  # the schema


# ---------------------------------------------------------------------------
# Ported personas (the All About AI roster)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name,cls,voice", [
    ("damodaran", DamodaranAgent, "Aswath Damodaran"),
    ("ackman", AckmanAgent, "Bill Ackman"),
    ("wood", WoodAgent, "Cathie Wood"),
    ("burry", BurryAgent, "Michael Burry"),
    ("pabrai", PabraiAgent, "Mohnish Pabrai"),
    ("fisher", FisherAgent, "Phil Fisher"),
    ("jhunjhunwala", JhunjhunwalaAgent, "Rakesh Jhunjhunwala"),
])
def test_ported_personas_signal_in_voice(tmp_path, name, cls, voice):
    """Each ported persona folds a canned LLM verdict into a Signal and
    persists a prompt written in its own voice."""
    llm = FakeLLM(BULLISH)
    agent = cls(llm=llm, cache=PromptCache(tmp_path / "llm"))

    sig = agent.predict("TEST", "2025-01-15", MockDataClient(metrics=_history()))

    assert isinstance(sig, Signal)
    assert sig.model_name == name
    assert sig.value == pytest.approx(0.8)
    assert sig.metadata["abstained"] is False
    record = json.loads(next((tmp_path / "llm").glob("*.json")).read_text())
    assert record["agent"] == name
    assert voice in record["system"]


# ---------------------------------------------------------------------------
# extract_json
# ---------------------------------------------------------------------------

def test_extract_json_fenced():
    assert extract_json('here:\n```json\n{"a": 1}\n```\ndone') == {"a": 1}


def test_extract_json_bare():
    assert extract_json('{"a": 1}') == {"a": 1}


def test_extract_json_embedded():
    assert extract_json('Sure! {"a": {"b": 2}} hope that helps') == {"a": {"b": 2}}


def test_extract_json_raises_on_garbage():
    with pytest.raises(LLMParseError):
        extract_json("no json here at all")


# ---------------------------------------------------------------------------
# Self-consistency ensemble (samples / temperature)
# ---------------------------------------------------------------------------

def _bullish(confidence, reasoning="r"):
    return json.dumps({"signal": "bullish", "confidence": confidence, "reasoning": reasoning})


def _bearish(confidence, reasoning="r"):
    return json.dumps({"signal": "bearish", "confidence": confidence, "reasoning": reasoning})


def test_ensemble_averages_samples_and_reports_spread(tmp_path):
    """Three samples fold to the mean value; reasoning comes from the
    median-valued sample; metadata carries the ensemble facts."""
    llm = FakeLLM(responses=[
        _bullish(80, "strong buy"),     # +0.8
        _bearish(60, "too expensive"),  # -0.6
        _bullish(60, "fair price"),     # +0.6  <- median
    ])
    agent = BuffettAgent(llm=llm, cache=PromptCache(tmp_path / "llm"), samples=3)

    sig = agent.predict("TEST", "2025-01-15", MockDataClient(metrics=_history()))

    assert llm.calls == 3
    assert sig.value == pytest.approx((0.8 - 0.6 + 0.6) / 3)
    assert sig.reasoning == "fair price"  # median sample's voice
    assert sig.metadata["signal"] == "bullish" and sig.metadata["confidence"] == 60
    assert sig.metadata["samples_requested"] == 3
    assert sorted(sig.metadata["sample_values"]) == pytest.approx([-0.6, 0.6, 0.8])
    assert sig.metadata["sample_spread"] == pytest.approx(1.4)
    assert len(sig.metadata["prompt_keys"]) == 3
    assert len(set(sig.metadata["prompt_keys"])) == 3  # every sample keyed apart
    assert "temperature" not in sig.metadata
    assert sig.metadata["cached"] is False


def test_ensemble_second_predict_serves_all_samples_from_cache(tmp_path):
    llm = FakeLLM(responses=[_bullish(80), _bearish(60), _bullish(60)])
    client = MockDataClient(metrics=_history())
    agent = BuffettAgent(llm=llm, cache=PromptCache(tmp_path / "llm"), samples=3)

    first = agent.predict("TEST", "2025-01-15", client)
    second = agent.predict("TEST", "2025-01-15", client)

    assert llm.calls == 3  # no new calls on the replay
    assert first.value == second.value
    assert second.metadata["cached"] is True
    assert second.metadata["prompt_keys"] == first.metadata["prompt_keys"]


def test_ensemble_persists_one_record_per_sample(tmp_path):
    agent = BuffettAgent(llm=FakeLLM(responses=[_bullish(80), _bearish(60), _bullish(60)]),
                         cache=PromptCache(tmp_path / "llm"), samples=3)
    agent.predict("TEST", "2025-01-15", MockDataClient(metrics=_history()))

    records = [json.loads(p.read_text()) for p in (tmp_path / "llm").glob("*.json")]
    assert len(records) == 3
    assert sorted(r["sample"] for r in records) == [0, 1, 2]


def test_single_sample_keeps_legacy_shape(tmp_path):
    """samples=1, no temperature: metadata carries no ensemble keys."""
    agent = _agent(tmp_path, FakeLLM(BULLISH))
    sig = agent.predict("TEST", "2025-01-15", MockDataClient(metrics=_history()))

    assert sig.value == pytest.approx(0.8)
    assert set(sig.metadata) == {"signal", "confidence", "model", "prompt_key",
                                 "snapshot_hash", "cached", "abstained"}


def test_single_sample_prompt_key_is_legacy(tmp_path):
    from hedge_fund.llm import prompt_key
    agent = _agent(tmp_path, FakeLLM(BULLISH))
    sig = agent.predict("TEST", "2025-01-15", MockDataClient(metrics=_history()))

    record = json.loads(next((tmp_path / "llm").glob("*.json")).read_text())
    assert sig.metadata["prompt_key"] == prompt_key(
        "buffett", "fake-model", record["system"], record["user"])


def test_temperature_salts_cache_key(tmp_path):
    """Same prompt, different temperature → different cache entries; each
    agent replays its own."""
    client = MockDataClient(metrics=_history())
    hot = BuffettAgent(llm=FakeLLM(BULLISH), cache=PromptCache(tmp_path / "llm"),
                       temperature=0.7)
    cold = BuffettAgent(llm=FakeLLM(BULLISH), cache=PromptCache(tmp_path / "llm"))

    hot_sig = hot.predict("TEST", "2025-01-15", client)
    cold_sig = cold.predict("TEST", "2025-01-15", client)
    hot_again = hot.predict("TEST", "2025-01-15", client)

    assert hot_sig.metadata["prompt_key"] != cold_sig.metadata["prompt_key"]
    assert hot_sig.metadata["temperature"] == 0.7
    assert "temperature" not in cold_sig.metadata
    assert hot_again.metadata["cached"] is True  # hot replays its own entry
    records = [json.loads(p.read_text()) for p in (tmp_path / "llm").glob("*.json")]
    assert len(records) == 2
    assert any(r.get("temperature") == 0.7 for r in records)


def test_ensemble_proceeds_with_successful_samples(tmp_path):
    """One unparseable sample of three: the fund uses the two good ones."""
    llm = FakeLLM(responses=[_bullish(80), "garbage", _bullish(40)])
    agent = BuffettAgent(llm=llm, cache=PromptCache(tmp_path / "llm"), samples=3)

    sig = agent.predict("TEST", "2025-01-15", MockDataClient(metrics=_history()))

    assert llm.calls == 3
    assert sig.metadata["abstained"] is False
    assert sig.value == pytest.approx((0.8 + 0.4) / 2)
    assert sig.metadata["samples_requested"] == 3
    assert sig.metadata["sample_values"] == pytest.approx([0.8, 0.4])
    assert sig.metadata["sample_spread"] == pytest.approx(0.4)


def test_ensemble_abstains_only_when_every_sample_fails(tmp_path):
    llm = FakeLLM(responses=["garbage", "still garbage", "nope"])
    agent = BuffettAgent(llm=llm, cache=PromptCache(tmp_path / "llm"), samples=3)

    sig = agent.predict("TEST", "2025-01-15", MockDataClient(metrics=_history()))

    assert sig.value == 0.0
    assert sig.metadata["abstained"] is True
    assert "parse failed" in sig.metadata["abstain_reason"]


def test_ensemble_call_error_abstains_with_last_key(tmp_path):
    llm = FakeLLM(error=TimeoutError("llm timed out"))
    agent = BuffettAgent(llm=llm, cache=PromptCache(tmp_path / "llm"), samples=3)

    sig = agent.predict("TEST", "2025-01-15", MockDataClient(metrics=_history()))

    assert sig.metadata["abstained"] is True
    assert "timed out" in sig.metadata["abstain_reason"]


def test_ensemble_params_validate():
    with pytest.raises(ValueError):
        BuffettAgent(llm=FakeLLM(), samples=0)
    with pytest.raises(ValueError):
        BuffettAgent(llm=FakeLLM(), temperature=3)
    with pytest.raises(ValueError):
        BuffettAgent(llm=FakeLLM(), temperature=-0.1)
    BuffettAgent(llm=FakeLLM(), samples=1, temperature=2)  # boundary is fine
