"""Bounded, operation-authorized HTTP retrieval for reviewed news sources."""

from __future__ import annotations

import math
import re
import zlib
from collections.abc import Callable, Sequence
from contextlib import AbstractContextManager, nullcontext
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit

import httpx

from hedge_fund.news.models import RefreshLimits
from hedge_fund.runtime.dispatch import ProviderDispatch
from hedge_fund.runtime.policy import AuthorizationDenied, ProviderTarget


class DestinationDenied(AuthorizationDenied):
    """A request or redirect escaped its frozen origin authority."""


class RequestTimeout(RuntimeError):
    """A bounded source request exceeded its network deadline."""


class ResponseLimitExceeded(RuntimeError):
    """A response exceeded its compressed or decompressed byte bound."""


class InvalidResponse(RuntimeError):
    """The origin returned unusable status, metadata, or content."""


@dataclass(frozen=True, slots=True)
class FetchRequest:
    source_id: str
    url: str
    accepted_media_types: tuple[str, ...]
    # Informational request metadata; SEC identity selection is host-based on every redirect hop.
    sec_identity_required: bool


@dataclass(frozen=True, slots=True)
class FetchResponse:
    final_url: str
    status_code: int
    media_type: str | None
    content: bytes
    redirect_count: int
    compressed_bytes: int = 0
    decompressed_bytes: int = 0


def validate_sec_identity(identity: str | None) -> str:
    if not isinstance(identity, str) or not 4 <= len(identity) <= 200:
        raise AuthorizationDenied("a descriptive SEC identity is required")
    if any(ord(character) < 32 or ord(character) == 127 for character in identity):
        raise AuthorizationDenied("a descriptive SEC identity is required")
    lowered = identity.casefold()
    if any(token in lowered for token in ("sample company", "your company", "admincontact", "placeholder")):
        raise AuthorizationDenied("a descriptive SEC identity is required")
    match = re.fullmatch(
        r"([A-Za-z0-9][A-Za-z0-9 .&/'()-]{1,100}?)\s+" r"([A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}|https://[^\s]+)",
        identity,
    )
    if match is None or "@" not in match.group(2) and not match.group(2).startswith("https://"):
        raise AuthorizationDenied("a descriptive SEC identity is required")
    if match.group(2).casefold().endswith(("@example.com", "@example.org", "@example.net")):
        raise AuthorizationDenied("a descriptive SEC identity is required")
    return identity


class GuardedNewsTransport:
    def __init__(
        self,
        dispatch: ProviderDispatch,
        *,
        targets: Sequence[ProviderTarget],
        limits: RefreshLimits,
        sec_identity: str | None = None,
        client_factory: Callable[[ProviderTarget], httpx.Client] | None = None,
        request_gate: Callable[[str], AbstractContextManager[object]] | None = None,
    ) -> None:
        if not targets or any(target.kind != "data" or target.provider != "curated-news" for target in targets):
            raise DestinationDenied("curated news targets are invalid")
        self._dispatch = dispatch
        self._targets = tuple(targets)
        self._limits = limits
        self._sec_identity = sec_identity
        self._request_gate = request_gate or (lambda _url: nullcontext())
        self._client_factory = client_factory

    def _client_for(self, target: ProviderTarget, deadline_check) -> httpx.Client:
        if self._client_factory is not None:
            return self._client_factory(target)
        connect = self._limits.connect_timeout_seconds
        read = self._limits.read_timeout_seconds
        remaining_callback = getattr(deadline_check, "remaining_seconds", None)
        if callable(remaining_callback):
            try:
                remaining = float(remaining_callback())
            except (TypeError, ValueError, OverflowError):
                raise RequestTimeout("news origin exceeded its request deadline") from None
            if not math.isfinite(remaining) or remaining <= 0:
                raise RequestTimeout("news origin exceeded its request deadline")
            connect = min(connect, remaining)
            read = min(read, remaining)
        return httpx.Client(
            transport=self._dispatch.httpx_transport(target, allow_manual_redirects=True),
            timeout=httpx.Timeout(connect=connect, read=read, write=connect, pool=connect),
            follow_redirects=False,
            trust_env=False,
        )

    def fetch(self, request: FetchRequest) -> FetchResponse:
        current_url = request.url
        redirect_count = 0
        while True:
            target = self._target_for(current_url)
            headers = {
                "Accept": ", ".join(request.accepted_media_types),
                "Accept-Encoding": "gzip, deflate",
                "User-Agent": "ai-hedge-fund curated-news/1",
            }
            hostname = (urlsplit(current_url).hostname or "").casefold()
            if hostname == "sec.gov" or hostname.endswith(".sec.gov"):
                headers["User-Agent"] = self._validated_sec_identity()
            with self._request_gate(current_url) as deadline_check:
                if deadline_check is None:

                    def deadline_check():
                        return None

                deadline_check()
                client = self._client_for(target, deadline_check)
                try:
                    with client.stream("GET", current_url, headers=headers) as response:
                        deadline_check()
                        if response.status_code in (301, 302, 303, 307, 308):
                            if redirect_count >= self._limits.max_redirects:
                                raise InvalidResponse("news origin exceeded its redirect bound")
                            location = response.headers.get("location")
                            if not location:
                                raise InvalidResponse("news origin returned an invalid redirect")
                            current_url = urljoin(current_url, location)
                            redirect_count += 1
                            continue
                        if response.status_code != 200:
                            raise InvalidResponse("news origin returned an unsuccessful status")
                        media_type = response.headers.get("content-type", "").partition(";")[0].strip().casefold() or None
                        if media_type not in request.accepted_media_types:
                            raise InvalidResponse("news origin returned an unaccepted media type")
                        content, compressed_bytes = self._read_bounded(response, deadline_check)
                        return FetchResponse(
                            final_url=current_url,
                            status_code=response.status_code,
                            media_type=media_type,
                            content=content,
                            redirect_count=redirect_count,
                            compressed_bytes=compressed_bytes,
                            decompressed_bytes=len(content),
                        )
                except httpx.TimeoutException as exc:
                    raise RequestTimeout("news origin exceeded its request deadline") from exc
                except httpx.HTTPError as exc:
                    raise InvalidResponse("news origin request failed") from exc
                finally:
                    client.close()

    def _validated_sec_identity(self) -> str:
        return validate_sec_identity(self._sec_identity)

    def _target_for(self, url: str) -> ProviderTarget:
        try:
            parts = urlsplit(url)
            port = parts.port
        except ValueError:
            raise DestinationDenied("news destination is invalid") from None
        host = parts.hostname.casefold() if parts.hostname else ""
        for target in self._targets:
            endpoint = urlsplit(target.endpoint or "")
            if parts.scheme.casefold() == "https" and port in (None, 443) and host == (endpoint.hostname or "").casefold():
                return target
        raise DestinationDenied("news destination is outside the frozen origin set")

    def _read_bounded(self, response: httpx.Response, deadline_check=lambda: None) -> tuple[bytes, int]:
        length = response.headers.get("content-length")
        if length is not None:
            try:
                declared = int(length)
            except ValueError:
                raise InvalidResponse("news origin returned an invalid content length") from None
            if declared < 0:
                raise InvalidResponse("news origin returned an invalid content length")
            if declared > self._limits.max_compressed_bytes:
                raise ResponseLimitExceeded("news response exceeded its compressed byte bound")
        encoding = response.headers.get("content-encoding", "identity").strip().casefold()
        if encoding in ("", "identity"):
            decoder = None
        elif encoding == "gzip":
            decoder = zlib.decompressobj(16 + zlib.MAX_WBITS)
        elif encoding == "deflate":
            decoder = zlib.decompressobj()
        else:
            raise InvalidResponse("news origin returned an unsupported content encoding")
        compressed_size = 0
        content = bytearray()
        try:
            for chunk in response.iter_raw():
                deadline_check()
                compressed_size += len(chunk)
                if compressed_size > self._limits.max_compressed_bytes:
                    raise ResponseLimitExceeded("news response exceeded its compressed byte bound")
                decoded = (
                    chunk
                    if decoder is None
                    else decoder.decompress(
                        chunk,
                        self._limits.max_decompressed_bytes - len(content) + 1,
                    )
                )
                if len(content) + len(decoded) > self._limits.max_decompressed_bytes:
                    raise ResponseLimitExceeded("news response exceeded its decompressed byte bound")
                content.extend(decoded)
                while decoder is not None and decoder.unconsumed_tail:
                    decoded = decoder.decompress(
                        decoder.unconsumed_tail,
                        self._limits.max_decompressed_bytes - len(content) + 1,
                    )
                    if len(content) + len(decoded) > self._limits.max_decompressed_bytes:
                        raise ResponseLimitExceeded("news response exceeded its decompressed byte bound")
                    content.extend(decoded)
            if decoder is not None:
                if not decoder.eof or decoder.unused_data:
                    raise InvalidResponse("news origin returned invalid compressed content")
                decoded = decoder.flush()
                if len(content) + len(decoded) > self._limits.max_decompressed_bytes:
                    raise ResponseLimitExceeded("news response exceeded its decompressed byte bound")
                content.extend(decoded)
        except zlib.error:
            raise InvalidResponse("news origin returned invalid compressed content") from None
        deadline_check()
        return bytes(content), compressed_size
