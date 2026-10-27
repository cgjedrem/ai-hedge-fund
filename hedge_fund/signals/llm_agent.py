"""LLMAgent — base class for LLM investor agents (the second AlphaModel flavor).

An LLMAgent reasons over a point-in-time FundamentalsSnapshot in a persona's
voice and emits the same Signal every quant model does. The base class owns
all the machinery; a persona is just a name + a system prompt:

    class BuffettAgent(LLMAgent):
        @property
        def name(self) -> str:
            return "buffett"

        def get_system_prompt(self) -> str:
            return "You are Warren Buffett..."

Failure contract (locked decisions):
- Data-layer errors PROPAGATE (fail loud — a broken snapshot must never
  silently become a neutral view).
- LLM call/parse failures ABSTAIN: Signal(value=0.0, metadata.abstained=True).
- Every LLM decision persists its exact prompt + response (via PromptCache),
  and an unchanged snapshot never pays for a second LLM call.

At a bar (a minute fund's session) the prompt also carries the day so far
— the move since the previous close, results released, headlines — see
features/intraday.py. It is bucketed so quiet bars stay cache hits.

A daily fund can carry the week's headlines instead: constructed with
news=True (a mandate's model params), the prompt gains features/news.py's
block under the fundamentals. Blind backtests never see it — headlines
name events a model could recall — and intraday bars keep the day-so-far
context, which already carries headlines.

Self-consistency ensemble (mandate params `samples` and `temperature`):
with samples=N the same prompt is asked N times and the folded values are
averaged into one Signal — the reasoning comes from the median-valued
sample, and metadata carries sample_values/sample_spread so the spread
reads as an uncertainty signal. temperature adds sampling creativity
(0 = deterministic, up to 2 = creative). Both salt the cache key, so a
changed temperature or a different sample never replays another sample's
cached answer; the default single-sample, no-temperature run keeps the
legacy keys, so existing funds' caches stay valid. Failures are
per-sample: a fund proceeds with the samples that succeeded and abstains
only when none did.
"""

from __future__ import annotations

import logging

from hedge_fund.data.bars import is_intraday
from hedge_fund.data.protocol import DataClient
from hedge_fund.features.breakpoints import MEBreakpoints, shared_breakpoints
from hedge_fund.features.intraday import build_intraday_context
from hedge_fund.features.news import build_news_context
from hedge_fund.features.snapshot import FundamentalsSnapshot, InsufficientData, build_snapshot
from hedge_fund.llm import (
    LLMCallError,
    LLMClient,
    PromptCache,
    extract_json,
    make_llm,
    prompt_key,
    salted_key,
)
from hedge_fund.models import Signal
from hedge_fund.signals.base import AlphaModel

logger = logging.getLogger(__name__)

# What the model must return; folded into Signal.value below.
_SIGNAL_TO_SIGN = {"bullish": 1.0, "neutral": 0.0, "bearish": -1.0}


class LLMAgent(AlphaModel):
    """Base for persona agents. Subclasses define `name` and `get_system_prompt`."""

    def __init__(
        self,
        llm: LLMClient | None = None,
        cache: PromptCache | None = None,
        blind: bool = False,
        breakpoints: MEBreakpoints | None = None,
        news: bool = False,
        samples: int = 1,
        temperature: float | None = None,
    ) -> None:
        if samples < 1:
            raise ValueError(f"samples must be >= 1, got {samples}")
        if temperature is not None and not 0 <= temperature <= 2:
            raise ValueError(f"temperature must be within [0, 2], got {temperature}")
        self._llm = llm if llm is not None else make_llm(temperature=temperature)
        self._cache = cache if cache is not None else PromptCache()
        # Blind prompts withhold the ticker, industry, calendar dates and
        # dollar values so a backtest can't lean on what the LLM remembers
        # about the company (FundamentalsSnapshot.render). Size survives only
        # as a market-cap percentile from a breakpoints table, loaded once per
        # process on first use unless one is injected (tests). Backtests set
        # blind; live runs don't and never touch the breakpoints.
        self._blind = blind
        self._breakpoints = breakpoints
        # Daily funds can read the week's headlines under the fundamentals
        # (features/news.py). Intraday bars get the day so far instead, and
        # blind backtests get neither: headlines name events a model could
        # recall.
        self._news = news
        # Self-consistency ensemble: samples > 1 asks the same prompt N times
        # and averages the folded values into one Signal (reasoning comes from
        # the median sample). temperature adds sampling creativity. Both are
        # mandate params (fund YAML `params:`) and both salt the cache key —
        # a changed temperature or a different sample must never replay
        # another sample's cached answer. When `llm` is injected, the caller
        # must build it with the same temperature (paper._warm does); the
        # agent trusts the param for keying.
        self._samples = int(samples)
        self._temperature = temperature

    # ------------------------------------------------------------------
    # AlphaModel interface
    # ------------------------------------------------------------------

    def predict(self, ticker: str, date: str, data_client: DataClient) -> Signal:
        try:
            snapshot = self.build_snapshot(ticker, date, data_client)
        except InsufficientData as exc:
            return self._abstain(ticker, date, f"insufficient data: {exc}")
        # Any other data-layer exception (e.g. FDClientError) propagates.

        system = self.get_system_prompt()
        user = self.build_user_prompt(snapshot)
        if is_intraday(date):
            # A bar, not a close: add the day so far. Bucketed, so a quiet
            # bar renders the same prompt as the last one and costs nothing.
            context = build_intraday_context(ticker, date, data_client)
            user = f"{user}\n\n{context.render(blind=self._blind)}"
        elif self._news and not self._blind:
            # A daily session with headlines enabled: the week's news under
            # the fundamentals. Cache-exact like the intraday block — the
            # same headlines render identically, so a quiet week is free.
            context = build_news_context(ticker, date, data_client)
            user = f"{user}\n\n{context.render()}"
        samples: list[tuple[str, dict, bool]] = []  # (key, parsed, cached)
        last_failure = ""
        last_failed_key = ""
        for index in range(self._samples):
            salt = self._salt(index)
            cache_key = getattr(self._llm, "cache_key", None)
            base = (cache_key(self.name, system, user) if callable(cache_key)
                    else prompt_key(self.name, self._llm.model, system, user))
            key = salted_key(base, salt) if salt else base

            cached = self._cache.get(key)
            if cached is not None and "parsed" in cached:
                samples.append((key, cached["parsed"], True))
                continue

            record = {
                "agent": self.name,
                "model": self._llm.model,
                "ticker": ticker,
                "as_of": date,
                "snapshot_hash": snapshot.content_hash,
                "system": system,
                "user": user,
            }
            if salt:
                record["sample"] = index
                if self._temperature is not None:
                    record["temperature"] = self._temperature

            try:
                response = self._llm.complete(system, user)
            except Exception as exc:
                if isinstance(exc, LLMCallError) and exc.diagnostic_record is not None:
                    self._cache.put(key, {**record, "call_error": str(exc),
                                          "diagnostics": exc.diagnostic_record})
                    last_failed_key = key
                last_failure = f"LLM call failed: {exc}"
                logger.warning("%s LLM call failed for %s@%s (sample %d): %s",
                               self.name, ticker, date, index, exc)
                continue

            record["response"] = response
            try:
                parsed = self._parse(response)
            except Exception as exc:
                # Persist the raw response even when unparseable — the debug trail.
                self._cache.put(key, {**record, "parse_error": str(exc)})
                logger.warning("%s parse failed for %s@%s (sample %d): %s",
                               self.name, ticker, date, index, exc)
                last_failure = f"parse failed: {exc}"
                continue

            self._cache.put(key, {**record, "parsed": parsed})
            samples.append((key, parsed, False))

        if not samples:
            signal = self._abstain(ticker, date, last_failure or "no samples completed")
            if last_failed_key:
                signal.metadata["prompt_key"] = last_failed_key
            return signal

        return self._combine(ticker, date, samples, snapshot)

    # ------------------------------------------------------------------
    # Subclass surface
    # ------------------------------------------------------------------

    def get_system_prompt(self) -> str:
        """The persona — every subclass must define its voice."""
        raise NotImplementedError(f"{type(self).__name__} must define get_system_prompt()")

    def build_snapshot(self, ticker: str, date: str, data_client: DataClient) -> FundamentalsSnapshot:
        """What this persona is allowed to know. Default: the shared
        point-in-time fundamentals snapshot — right for value/quality
        personas. Override for personas that reason over different data
        (macro, news); when a second snapshot TYPE exists, extract the
        implicit interface (ticker/as_of/content_hash/render) into a
        Protocol — not before."""
        breakpoints = None
        if self._blind:
            if self._breakpoints is None:
                self._breakpoints = shared_breakpoints()
            breakpoints = self._breakpoints
        return build_snapshot(ticker, date, data_client, breakpoints=breakpoints)

    def build_user_prompt(self, snapshot: FundamentalsSnapshot) -> str:
        """Default user prompt: the rendered snapshot. Override to enrich."""
        return snapshot.render(blind=self._blind)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _parse(self, response: str) -> dict:
        """Extract + validate {signal, confidence, reasoning}."""
        data = extract_json(response)
        signal = str(data.get("signal", "")).lower()
        if signal not in _SIGNAL_TO_SIGN:
            raise ValueError(f"invalid signal {data.get('signal')!r}")
        confidence = float(data.get("confidence", 0))
        if not 0 <= confidence <= 100:
            raise ValueError(f"confidence out of range: {confidence}")
        parsed = {
            "signal": signal,
            "confidence": confidence,
            "reasoning": str(data.get("reasoning", "")),
        }
        if "provider_metadata" in data:
            if not isinstance(data["provider_metadata"], dict):
                raise ValueError("provider_metadata must be an object")
            parsed["provider_metadata"] = data["provider_metadata"]
        return parsed

    def _salt(self, index: int) -> str:
        """Request semantics the prompts don't carry, for the cache key.

        Empty for the default single-sample, provider-default-temperature
        run — those keys stay byte-identical to the legacy ones.
        """
        parts = []
        if self._temperature is not None:
            parts.append(f"temperature={self._temperature}")
        if self._samples > 1:
            parts.append(f"sample={index}")
        return "|".join(parts)

    def _combine(self, ticker: str, date: str, samples, snapshot: FundamentalsSnapshot) -> Signal:
        """Fold N sample parses into one Signal: mean value, median voice.

        With one sample this is exactly the old single-response fold — same
        metadata keys, same value. With more, the ensemble facts ride along
        in metadata and the reasoning comes from the median-valued sample.
        """
        values = [_SIGNAL_TO_SIGN[parsed["signal"]] * parsed["confidence"] / 100.0
                  for _, parsed, _ in samples]
        ranked = sorted(zip(samples, values), key=lambda pair: pair[1])
        (median_key, median_parsed, _), _ = ranked[len(ranked) // 2]
        metadata = {
            "signal": median_parsed["signal"],
            "confidence": median_parsed["confidence"],
            "model": self._llm.model,
            "prompt_key": median_key,
            "snapshot_hash": snapshot.content_hash,
            "cached": all(cached for _, _, cached in samples),
            "abstained": False,
        }
        if "provider_metadata" in median_parsed:
            metadata["provider_metadata"] = median_parsed["provider_metadata"]
        if self._samples > 1:
            metadata.update(
                samples_requested=self._samples,
                sample_values=values,
                sample_spread=max(values) - min(values),
                prompt_keys=[key for key, _, _ in samples],
            )
        if self._temperature is not None:
            metadata["temperature"] = self._temperature
        return Signal(
            model_name=self.name,
            ticker=ticker,
            date=date,
            value=sum(values) / len(values),
            reasoning=median_parsed["reasoning"],
            metadata=metadata,
        )

    def _abstain(self, ticker: str, date: str, reason: str) -> Signal:
        return Signal(
            model_name=self.name,
            ticker=ticker,
            date=date,
            value=0.0,
            reasoning=f"abstained: {reason}",
            metadata={"abstained": True, "abstain_reason": reason, "cached": False},
        )
