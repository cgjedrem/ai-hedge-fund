"""LLM provider protocol + the concrete clients.

Mirrors the DataClient pattern (hedge_fund/data/protocol.py): agents depend on the
`LLMClient` protocol, never a concrete provider. Any class with a
`complete(system, user) -> str` method plugs in — community providers welcome.

We deliberately do NOT use langchain's structured-output machinery: its
forced-tool mode breaks on Anthropic reasoning models (v1 carries the same
workaround). For chat providers, we ask for JSON in the prompt and parse it
ourselves; Jev adapts native typed answers into the same JSON contract.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import time
from collections.abc import Callable
from typing import Protocol, runtime_checkable
from urllib.parse import urlsplit

import httpx

from hedge_fund.llm import contract
from hedge_fund.llm.registry import (
    is_supported,
    KEYLESS_PROVIDERS,
    provider_for,
    SUPPORTED_PROVIDERS,
)
from hedge_fund.runtime.dispatch import (
    blocked_async_httpx_client,
    DenyingAsyncHTTPTransport,
    ProviderDispatch,
)
from hedge_fund.runtime.endpoints import provider_base_url, validate_provider_target
from hedge_fund.runtime.policy import AuthorizationDenied, ProviderTarget

DEFAULT_MODEL = "gemma3:4b"
_GUARDED_PROVIDERS = frozenset({"deepseek", "kimi", "ollama", "openai", "typesafe", "xai"})

# Called with each piece of text as it arrives. None means don't stream.
TokenListener = Callable[[str], None] | None


class LLMParseError(ValueError):
    """The model's response did not contain parseable JSON."""


class LLMCallError(RuntimeError):
    """Provider failure with optional, credential-free persistence context."""

    def __init__(self, message: str, diagnostic_record: dict | None = None) -> None:
        super().__init__(message)
        self.diagnostic_record = diagnostic_record


@runtime_checkable
class LLMClient(Protocol):
    """Protocol all LLM providers must satisfy.

    complete() returns text (native text or an adapter's compatibility JSON).
    Providers may optionally implement cache_key(agent, system, user) when
    their request contains additional semantics beyond the two prompts.
    Providers should raise on
    transport failure — the LLMAgent layer decides to abstain, not the
    provider.
    """

    model: str

    def complete(self, system: str, user: str) -> str:
        ...


class ChatLLM:
    """A langchain chat model behind the LLMClient protocol.

    Chat providers share this wrapper — only *constructing* the chat model
    differs, and that lives in make_llm(). Their response handling is written
    once; JevLLM handles TypeSafe's native typed responses separately.

    With an `on_token` listener the same call streams: the listener sees text
    as it arrives, and complete() still returns the whole response. Watching
    is a property of the client, not of the caller — so LLMAgent.predict(),
    the prompt cache, and the parse are untouched by it.
    """

    def __init__(
        self,
        model: str,
        chat,
        on_token: TokenListener = None,
        *,
        dispatch: ProviderDispatch,
        target: ProviderTarget,
    ) -> None:
        if not isinstance(dispatch, ProviderDispatch) or not isinstance(target, ProviderTarget):
            raise AuthorizationDenied("provider operation authorization is required")
        dispatch.validate_target(target)
        self.model = model
        self._chat = chat
        self._on_token = on_token
        self._dispatch = dispatch
        self._target = target
        self._no_think_chat = None

    def complete(self, system: str, user: str) -> str:
        messages = [("system", system), ("human", user)]
        with self._dispatch.invocation(self._target):
            text = self._generate(self._chat, messages)
            if text.strip() or not hasattr(self._chat, "reasoning"):
                return text
            if self._no_think_chat is None:
                self._no_think_chat = self._chat.model_copy(update={"reasoning": False})
            return self._generate(self._no_think_chat, messages)

    def _generate(self, chat, messages) -> str:
        try:
            return self._generate_unchecked(chat, messages)
        except AuthorizationDenied:
            raise
        except Exception as exc:
            cause = exc
            seen: set[int] = set()
            while cause is not None and id(cause) not in seen:
                if isinstance(cause, AuthorizationDenied):
                    raise cause from None
                seen.add(id(cause))
                cause = cause.__cause__ or cause.__context__
            raise LLMCallError("LLM provider request failed") from None

    def _generate_unchecked(self, chat, messages) -> str:
        if self._on_token is None:
            return _flatten(chat.invoke(messages).content)
        parts: list[str] = []
        for chunk in chat.stream(messages):
            text = _flatten(chunk.content, sep="")
            if text:
                parts.append(text)
                self._on_token(text)
        return "".join(parts)


class JevLLM:
    """Native TypeSafe adapter returning compatibility JSON without streaming.

    Provider metadata travels with the result so cache replay needs no mutable
    last-response state. Native response bodies are preserved except for echoed
    credentials, which are redacted. Credentials are passed in explicitly.
    """

    ENDPOINT = "https://api.typesafe.ai/v1/systemone"

    def __init__(
        self,
        api_key: str,
        model: str = "jev-1.13.0",
        timeout: float = 60.0,
        *,
        dispatch: ProviderDispatch | None = None,
        target: ProviderTarget | None = None,
    ) -> None:
        if not isinstance(api_key, str) or not api_key.strip():
            raise ValueError("A non-empty TypeSafe API key is required")
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("timeout must be a positive finite number")
        if dispatch is None or not isinstance(dispatch, ProviderDispatch) or not isinstance(target, ProviderTarget):
            raise AuthorizationDenied("TypeSafe operation authorization is required")
        if target.kind != "llm" or target.provider != "typesafe" or target.model != model:
            raise AuthorizationDenied("TypeSafe model does not match provider authorization")
        dispatch.validate_target(target)
        self.model = model
        self._api_key = api_key
        self._timeout = timeout
        self._dispatch = dispatch
        self._target = target
        self._http_client = dispatch.httpx_client(target, timeout=timeout)

    def cache_key(self, agent: str, system: str, user: str) -> str:
        """Hash semantic inputs only; do not disturb legacy prompt keys."""
        identity = {
            "provider": "TypeSafe",
            "endpoint": self.ENDPOINT,
            "agent": agent,
            "request": contract.build_jev_request(system, user, self.model),
            "contract_version": contract.JEV_CONTRACT_VERSION,
        }
        canonical = json.dumps(identity, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode()).hexdigest()[:24]

    def complete(self, system: str, user: str) -> str:
        request = contract.build_jev_request(system, user, self.model)
        started = time.monotonic()
        diagnostics = {
            "provider": "TypeSafe",
            "contract_version": contract.JEV_CONTRACT_VERSION,
            "request": request,
            "attempt_count": 0,
            "status_code": None,
            "raw_response": None,
        }

        def fail(category: str, message: str) -> None:
            diagnostics.update(failure_category=category, elapsed_seconds=time.monotonic() - started)
            # Do not chain transport exceptions: their message/request can carry
            # credentials. Diagnostics intentionally omit all HTTP headers.
            raise LLMCallError(message, self._redact(diagnostics)) from None

        diagnostics["attempt_count"] = 1
        try:
            with self._dispatch.invocation(self._target):
                response = self._http_client.post(
                    self.ENDPOINT,
                    json=request,
                    headers={"Authorization": f"Bearer {self._api_key}"},
                    timeout=self._timeout,
                )
                status = response.status_code
                raw = response.text
        except AuthorizationDenied:
            raise
        except httpx.RequestError:
            fail("transport", "TypeSafe request failed during transport")

        diagnostics.update(status_code=status, raw_response=raw)
        if not 200 <= status < 300:
            fail("http", f"TypeSafe returned HTTP {status}")
        try:
            native_response = json.loads(raw)
        except ValueError:
            fail("json_decode", "TypeSafe returned invalid JSON")
        try:
            payload, metadata = contract.normalize_jev_response(native_response)
        except contract.JevContractError as exc:
            fail("contract", f"TypeSafe response failed validation: {exc}")

        metadata.update(diagnostics, elapsed_seconds=time.monotonic() - started)
        payload["provider_metadata"] = {"jev": self._redact(metadata)}
        return json.dumps(payload)

    def _redact(self, value):
        """Protect against a service echoing the API key in an error body."""
        if isinstance(value, str):
            return value.replace(self._api_key, "[REDACTED]")
        if isinstance(value, dict):
            return {self._redact(key): self._redact(item) for key, item in value.items()}
        if isinstance(value, list):
            return [self._redact(item) for item in value]
        return value


def make_llm(
    model: str | None = None,
    timeout: float = 60.0,
    max_tokens: int = 4096,
    on_token: TokenListener = None,
    temperature: float | None = None,
    top_p: float | None = None,
    context_size: int | None = None,
    *,
    api_key: str | None = None,
    endpoint: str | None = None,
    use_environment: bool = True,
    dispatch: ProviderDispatch | None = None,
) -> LLMClient:
    """Build guarded client; environment resolves only the default model."""
    if type(use_environment) is not bool:
        raise ValueError("environment policy is invalid")
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or not 0 < timeout <= 300:
        raise ValueError("timeout is invalid")
    if type(max_tokens) is not int or not 1 <= max_tokens <= 131072:
        raise ValueError("max tokens is invalid")
    if model is not None and (not isinstance(model, str) or not model or model != model.strip() or any(ord(char) < 32 or ord(char) == 127 for char in model)):
        raise ValueError("model is invalid")
    if temperature is not None and (isinstance(temperature, bool) or not isinstance(temperature, (int, float)) or not math.isfinite(temperature) or not 0 <= temperature <= 2):
        raise ValueError("temperature is invalid")
    if top_p is not None and (isinstance(top_p, bool) or not isinstance(top_p, (int, float)) or not math.isfinite(top_p) or not 0 <= top_p <= 1):
        raise ValueError("top-p is invalid")
    if context_size is not None and (type(context_size) is not int or not 256 <= context_size <= 131072):
        raise ValueError("context size is invalid")
    if endpoint is not None:
        if not isinstance(endpoint, str) or not endpoint or endpoint != endpoint.strip():
            raise ValueError("endpoint is invalid")
        try:
            parts = urlsplit(endpoint)
            port = parts.port
        except ValueError:
            raise ValueError("endpoint is invalid") from None
        if parts.scheme not in {"http", "https"} or not parts.hostname or parts.username is not None or parts.password is not None or parts.query or parts.fragment or (port is not None and not 1 <= port <= 65535):
            raise ValueError("endpoint is invalid")
    model = model or (os.environ.get("HEDGE_FUND_LLM_MODEL") if use_environment else None) or DEFAULT_MODEL
    provider = provider_for(model)
    if provider is None:
        raise AuthorizationDenied("LLM model provider is unknown")
    if not is_supported(provider):
        raise ValueError(f"No v2 client for {provider} (model {model}). " f"Supported: {', '.join(sorted(SUPPORTED_PROVIDERS))}.")
    target = ProviderTarget(
        kind="llm",
        provider=provider.casefold(),
        model=model,
        endpoint=endpoint,
    )
    validate_llm_transport(target)
    if not isinstance(dispatch, ProviderDispatch):
        raise AuthorizationDenied("provider operation authorization is required")
    dispatch.validate_target(target)
    if context_size is not None and (provider != "Ollama" or model.casefold().endswith(":cloud")):
        raise ValueError("context size is supported only by local Ollama.")

    if api_key is None:
        if provider in KEYLESS_PROVIDERS:
            api_key = ""
        else:
            raise AuthorizationDenied("captured provider credential is required")
    elif not isinstance(api_key, str) or (provider not in KEYLESS_PROVIDERS and not api_key.strip()) or any(ord(char) < 32 or ord(char) == 127 for char in api_key):
        raise ValueError("Provider credential is invalid.")

    # Only hand providers a temperature when one was asked for: several
    # constructors (Google's pydantic model among them) reject an explicit
    # None, and omitting it keeps each provider's own default.
    sampling = {"temperature": temperature} if temperature is not None else {}
    if top_p is not None:
        sampling["top_p"] = top_p

    if provider == "TypeSafe":
        # Typed judgments have no generated tokens or output-token budget.
        return JevLLM(
            api_key=api_key,
            model=model,
            timeout=timeout,
            dispatch=dispatch,
            target=target,
        )

    if provider == "OpenAI":
        from langchain_openai import ChatOpenAI

        chat = ChatOpenAI(
            model=model,
            api_key=api_key,
            timeout=timeout,
            max_retries=0,
            max_tokens=max_tokens,
            base_url=provider_base_url(target),
            http_client=dispatch.httpx_client(target, timeout=timeout),
            http_async_client=blocked_async_httpx_client(timeout=timeout),
            **sampling,
        )
    elif provider == "DeepSeek":
        from langchain_deepseek import ChatDeepSeek

        chat = ChatDeepSeek(
            model=model,
            api_key=api_key,
            timeout=timeout,
            max_retries=0,
            max_tokens=max_tokens,
            base_url=provider_base_url(target),
            http_client=dispatch.httpx_client(target, timeout=timeout),
            http_async_client=blocked_async_httpx_client(timeout=timeout),
            **sampling,
        )
    elif provider == "xAI":
        from langchain_xai import ChatXAI

        chat = ChatXAI(
            model=model,
            api_key=api_key,
            timeout=timeout,
            max_retries=0,
            max_tokens=max_tokens,
            xai_api_base=provider_base_url(target),
            http_client=dispatch.httpx_client(target, timeout=timeout),
            http_async_client=blocked_async_httpx_client(timeout=timeout),
            **sampling,
        )
    elif provider == "Kimi":
        from langchain_openai import ChatOpenAI

        chat = ChatOpenAI(
            model=model,
            api_key=api_key,
            timeout=timeout,
            max_retries=0,
            max_tokens=max_tokens,
            base_url=provider_base_url(target),
            http_client=dispatch.httpx_client(target, timeout=timeout),
            http_async_client=blocked_async_httpx_client(timeout=timeout),
            **sampling,
        )
    elif provider == "Ollama":
        from langchain_ollama import ChatOllama

        chat = ChatOllama(
            model=model,
            base_url=provider_base_url(target),
            num_ctx=(context_size if context_size is not None else 8192),
            num_predict=max_tokens,
            client_kwargs={
                "timeout": timeout,
                "trust_env": False,
                "transport": dispatch.httpx_transport(target),
                "headers": {"Authorization": "disabled"},
            },
            async_client_kwargs={
                "timeout": timeout,
                "trust_env": False,
                "transport": DenyingAsyncHTTPTransport(),
                "headers": {"Authorization": "disabled"},
            },
            **sampling,
        )
    else:  # pragma: no cover - validated provider names cover every branch
        raise ValueError(f"Unhandled provider {provider}")

    return ChatLLM(
        model,
        chat,
        on_token,
        dispatch=dispatch,
        target=target,
    )


def validate_llm_transport(target: ProviderTarget) -> None:
    """Reject providers without a guarded synchronous production transport."""
    if not isinstance(target, ProviderTarget) or target.kind != "llm":
        raise AuthorizationDenied("LLM provider target is invalid")
    validate_provider_target(target)
    if target.provider not in _GUARDED_PROVIDERS:
        raise AuthorizationDenied("provider transport is unsupported")


def AnthropicLLM(model: str | None = None, **kwargs) -> LLMClient:  # noqa: N802
    """Back-compat shim: v2 was Anthropic-only, and this name is exported.
    Prefer make_llm(), which honours whichever model is selected."""
    return make_llm(model or DEFAULT_MODEL, **kwargs)


def _flatten(content, sep: str = "\n") -> str:
    """One provider's response as plain text.

    Reasoning models (Anthropic extended thinking, and Gemini/DeepSeek in
    their thinking modes) return a LIST of blocks rather than a string. Only
    the text blocks are the answer — a thinking block stringified into the
    payload is prose in front of the JSON, which is exactly what breaks the
    parse. Mirrors v1's extract_json_from_response (src/utils/llm.py:109).

    *sep* joins the blocks: "\\n" for a whole message, "" for a stream chunk
    whose blocks are fragments of one continuing string.
    """
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
        return sep.join(parts)
    return "" if content is None else str(content)


def extract_json(text: str) -> dict:
    """Pull the first JSON object out of an LLM response.

    Tries: ```json fence -> whole string -> first balanced {...} block.
    Raises LLMParseError if nothing parses.
    """
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence:
        try:
            return json.loads(fence.group(1))
        except json.JSONDecodeError:
            pass

    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        pass

    start = text.find("{")
    if start != -1:
        depth = 0
        for i, ch in enumerate(text[start:], start):
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start : i + 1])
                    except json.JSONDecodeError:
                        break

    raise LLMParseError(f"no JSON object found in response: {text[:200]!r}")
