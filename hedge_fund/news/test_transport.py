import gzip
from contextlib import nullcontext
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import httpx
import pytest

from hedge_fund.news.models import RefreshLimits
from hedge_fund.news.transport import FetchRequest, GuardedNewsTransport, RequestTimeout
from hedge_fund.runtime.dispatch import make_one_shot_dispatch
from hedge_fund.runtime.policy import AuthorizationDenied, ProviderTarget

NOW = datetime(2026, 11, 25, 18, 0, tzinfo=timezone.utc)


class StreamingTransport(httpx.BaseTransport):
    def __init__(self, handler):
        self.handler = handler

    def handle_request(self, request):
        response = self.handler(request)
        content = b"".join(response.stream)

        class Stream(httpx.SyncByteStream):
            def __iter__(self):
                yield content

        return httpx.Response(
            response.status_code,
            headers=response.headers,
            stream=Stream(),
            request=request,
        )


def target(host="www.federalreserve.gov"):
    return ProviderTarget(
        kind="data",
        provider="curated-news",
        endpoint=f"https://{host}",
    )


def dispatch_for(*targets, max_calls=20):
    return make_one_shot_dispatch(
        root_id="synthetic-root",
        subject_id="news-refresh",
        capture_digest="capture-digest",
        operation_id="news-operation",
        operation_digest="a" * 64,
        expires_at=NOW + timedelta(minutes=2),
        targets=targets,
        max_calls=max_calls,
        max_cost=Decimal("0"),
        max_resources=max_calls,
        upper_bound_costs={item.identity: Decimal("0") for item in targets},
        clock=lambda: NOW,
        resolver=lambda _host, _port: ["93.184.216.34"],
    )


def test_fetch_returns_bounded_bytes_and_disables_ambient_redirects():
    configured = target()
    dispatch = dispatch_for(configured)
    observed = []

    def handler(request):
        observed.append(request)
        return httpx.Response(
            200,
            headers={"Content-Type": "application/rss+xml; charset=utf-8"},
            content=b"<rss><channel /></rss>",
        )

    transport = GuardedNewsTransport(
        dispatch,
        targets=(configured,),
        limits=RefreshLimits(),
        client_factory=lambda selected: dispatch.httpx_client(
            selected,
            inner_transport=StreamingTransport(handler),
        ),
    )
    response = transport.fetch(
        FetchRequest(
            source_id="fed-press",
            url="https://www.federalreserve.gov/feeds/press_all.xml",
            accepted_media_types=("application/rss+xml", "application/xml", "text/xml"),
            sec_identity_required=False,
        )
    )

    assert response.content == b"<rss><channel /></rss>"
    assert response.final_url == "https://www.federalreserve.gov/feeds/press_all.xml"
    assert response.redirect_count == 0
    assert response.status_code == 200
    assert response.media_type == "application/rss+xml"
    assert observed[0].method == "GET"
    assert observed[0].headers["accept-encoding"] == "gzip, deflate"


def test_default_client_preserves_timeout_policy_and_guarded_transport(monkeypatch):
    configured = target()
    dispatch = dispatch_for(configured)
    constructed = {}

    class Client:
        def __init__(self, **kwargs):
            constructed.update(kwargs)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def close(self):
            return None

        def stream(self, method, url, headers):
            request = httpx.Request(method, url, headers=headers)

            class Body(httpx.SyncByteStream):
                def __iter__(self):
                    yield b"<rss><channel /></rss>"

            response = httpx.Response(
                200,
                headers={"content-type": "application/rss+xml"},
                stream=Body(),
                request=request,
            )

            class Stream:
                def __enter__(self):
                    return response

                def __exit__(self, *args):
                    return False

            return Stream()

    monkeypatch.setattr(httpx, "Client", Client)
    transport = GuardedNewsTransport(dispatch, targets=(configured,), limits=RefreshLimits())
    response = transport.fetch(
        FetchRequest(
            source_id="fed-press",
            url="https://www.federalreserve.gov/feeds/press_all.xml",
            accepted_media_types=("application/rss+xml",),
            sec_identity_required=False,
        )
    )

    assert response.content == b"<rss><channel /></rss>"
    assert constructed["timeout"] == httpx.Timeout(5.0, read=15.0, write=5.0, pool=5.0)
    assert constructed["follow_redirects"] is False
    assert constructed["trust_env"] is False
    assert constructed["transport"] is not None


def test_default_request_timeouts_are_capped_by_remaining_deadline(monkeypatch):
    configured = target()
    dispatch = dispatch_for(configured)
    constructed = {}

    class Checkpoint:
        def __call__(self):
            return None

        def remaining_seconds(self):
            return 2.5

    class Gate:
        def __init__(self, _url):
            pass

        def __enter__(self):
            return Checkpoint()

        def __exit__(self, *args):
            return False

    class Client:
        def __init__(self, **kwargs):
            constructed.update(kwargs)

        def stream(self, method, url, headers):
            request = httpx.Request(method, url, headers=headers)

            class Body(httpx.SyncByteStream):
                def __iter__(self):
                    yield b"<rss/>"

            return nullcontext(httpx.Response(200, headers={"content-type": "application/rss+xml"}, stream=Body(), request=request))

        def close(self):
            pass

    monkeypatch.setattr(httpx, "Client", Client)
    transport = GuardedNewsTransport(dispatch, targets=(configured,), limits=RefreshLimits(), request_gate=Gate)

    transport.fetch(
        FetchRequest(
            source_id="fed-press",
            url="https://www.federalreserve.gov/feeds/press_all.xml",
            accepted_media_types=("application/rss+xml",),
            sec_identity_required=False,
        )
    )

    assert constructed["timeout"] == httpx.Timeout(2.5)


def test_every_request_hop_enters_the_shared_request_gate():
    configured = target()
    dispatch = dispatch_for(configured, max_calls=1)
    entered = []

    class Gate:
        def __init__(self, url):
            self.url = url

        def __enter__(self):
            entered.append(self.url)

        def __exit__(self, *args):
            return False

    transport = GuardedNewsTransport(
        dispatch,
        targets=(configured,),
        limits=RefreshLimits(),
        request_gate=Gate,
        client_factory=lambda selected: dispatch.httpx_client(
            selected,
            inner_transport=StreamingTransport(
                lambda request: httpx.Response(
                    200,
                    headers={"content-type": "application/rss+xml"},
                    content=b"<rss />",
                )
            ),
        ),
    )

    transport.fetch(
        FetchRequest(
            source_id="fed-press",
            url="https://www.federalreserve.gov/feeds/press_all.xml",
            accepted_media_types=("application/rss+xml",),
            sec_identity_required=False,
        )
    )

    assert entered == ["https://www.federalreserve.gov/feeds/press_all.xml"]


def test_sec_request_sends_validated_descriptive_identity():
    seen = {}

    def handler(request):
        seen.update(request.headers)
        return httpx.Response(200, headers={"content-type": "application/json"}, content=b"{}")

    sec = target("data.sec.gov")
    dispatch = dispatch_for(sec)
    transport = GuardedNewsTransport(
        dispatch,
        targets=[sec],
        limits=RefreshLimits(),
        sec_identity="Example Research news@example.test",
        client_factory=lambda selected: dispatch.httpx_client(selected, inner_transport=StreamingTransport(handler)),
    )

    transport.fetch(
        FetchRequest(
            source_id="sec",
            url="https://data.sec.gov/submissions/CIK0000000001.json",
            accepted_media_types=("application/json",),
            sec_identity_required=True,
        )
    )

    assert seen["user-agent"] == "Example Research news@example.test"


def test_sec_identity_is_not_forwarded_to_an_approved_non_sec_redirect():
    seen = []

    def handler(request):
        seen.append((request.url.host, request.headers.get("user-agent")))
        if request.url.host == "data.sec.gov":
            return httpx.Response(307, headers={"location": "https://www.federalreserve.gov/feed.xml"})
        return httpx.Response(200, headers={"content-type": "application/rss+xml"}, content=b"<rss/>")

    sec = target("data.sec.gov")
    fed = target()
    dispatch = dispatch_for(sec, fed, max_calls=2)
    transport = GuardedNewsTransport(
        dispatch,
        targets=(sec, fed),
        limits=RefreshLimits(),
        sec_identity="Example Research secret-contact@example.test",
        client_factory=lambda selected: dispatch.httpx_client(
            selected,
            inner_transport=StreamingTransport(handler),
            allow_manual_redirects=True,
        ),
    )

    transport.fetch(
        FetchRequest(
            source_id="sec",
            url="https://data.sec.gov/submissions/CIK0000000001.json",
            accepted_media_types=("application/rss+xml",),
            sec_identity_required=True,
        )
    )

    assert seen == [
        ("data.sec.gov", "Example Research secret-contact@example.test"),
        ("www.federalreserve.gov", "ai-hedge-fund curated-news/1"),
    ]


@pytest.mark.parametrize(
    "identity",
    [None, "python-httpx", "Sample Company Name AdminContact@example.com", "news@example.test"],
)
def test_invalid_sec_identity_is_denied_before_request(identity):
    called = False

    def handler(request):
        nonlocal called
        called = True
        return httpx.Response(200, content=b"{}")

    sec = target("data.sec.gov")
    dispatch = dispatch_for(sec)
    transport = GuardedNewsTransport(
        dispatch,
        targets=[sec],
        limits=RefreshLimits(),
        sec_identity=identity,
        client_factory=lambda selected: dispatch.httpx_client(selected, inner_transport=StreamingTransport(handler)),
    )

    with pytest.raises(AuthorizationDenied):
        transport.fetch(
            FetchRequest(
                source_id="sec",
                url="https://data.sec.gov/submissions/CIK0000000001.json",
                accepted_media_types=("application/json",),
                sec_identity_required=True,
            )
        )
    assert not called


@pytest.mark.parametrize(
    "url",
    [
        "http://www.federalreserve.gov/feed.xml",
        "https://www.federalreserve.gov:444/feed.xml",
        "https://user:secret@www.federalreserve.gov/feed.xml",
        "https://www.federalreserve.gov/feed.xml#fragment",
        "https://www.federalreserve.gov/feed.xml?access_token=secret",
        "https://unapproved.example/feed.xml",
        "https://127.0.0.1/feed.xml",
    ],
)
def test_unsafe_destinations_are_denied_before_content_retrieval(url):
    requested = []

    def handler(request):
        requested.append(str(request.url))
        return httpx.Response(200, headers={"content-type": "application/rss+xml"}, content=b"<rss/>")

    origin = target()
    dispatch = dispatch_for(origin)
    transport = GuardedNewsTransport(
        dispatch,
        targets=[origin],
        limits=RefreshLimits(),
        client_factory=lambda selected: dispatch.httpx_client(selected, inner_transport=StreamingTransport(handler)),
    )

    with pytest.raises(AuthorizationDenied):
        transport.fetch(
            FetchRequest(
                source_id="fed",
                url=url,
                accepted_media_types=("application/rss+xml",),
                sec_identity_required=False,
            )
        )
    assert requested == []


def test_same_origin_redirect_is_reauthorized_and_followed():
    requested = []
    gated = []

    def handler(request):
        requested.append(str(request.url))
        if request.url.path == "/start":
            return httpx.Response(302, headers={"location": "/final"})
        return httpx.Response(
            200,
            headers={"content-type": "application/rss+xml"},
            content=b"<rss/>",
        )

    class Gate:
        def __init__(self, url):
            self.url = url

        def __enter__(self):
            gated.append(self.url)

        def __exit__(self, *args):
            return False

    origin = target()
    dispatch = dispatch_for(origin)
    transport = GuardedNewsTransport(
        dispatch,
        targets=[origin],
        limits=RefreshLimits(),
        request_gate=Gate,
        client_factory=lambda selected: dispatch.httpx_client(
            selected,
            inner_transport=StreamingTransport(handler),
            allow_manual_redirects=True,
        ),
    )

    response = transport.fetch(
        FetchRequest(
            source_id="fed",
            url="https://www.federalreserve.gov/start",
            accepted_media_types=("application/rss+xml",),
            sec_identity_required=False,
        )
    )

    assert response.final_url == "https://www.federalreserve.gov/final"
    assert response.redirect_count == 1
    assert response.content == b"<rss/>"
    assert requested == [
        "https://www.federalreserve.gov/start",
        "https://www.federalreserve.gov/final",
    ]
    assert gated == requested


def test_default_client_factory_permits_guarded_manual_redirects(monkeypatch):
    origin = target()
    dispatch = dispatch_for(origin, max_calls=2)

    def handler(request):
        if request.url.path == "/start":
            return httpx.Response(307, headers={"location": "/final"})
        return httpx.Response(200, headers={"content-type": "application/rss+xml"}, content=b"<rss/>")

    real_transport = dispatch.httpx_transport

    def offline_transport(selected, **kwargs):
        return real_transport(selected, inner_transport=StreamingTransport(handler), **kwargs)

    monkeypatch.setattr(type(dispatch), "httpx_transport", lambda _self, selected, **kwargs: offline_transport(selected, **kwargs))
    transport = GuardedNewsTransport(dispatch, targets=(origin,), limits=RefreshLimits())

    response = transport.fetch(
        FetchRequest(
            source_id="fed",
            url="https://www.federalreserve.gov/start",
            accepted_media_types=("application/rss+xml",),
            sec_identity_required=False,
        )
    )

    assert response.final_url == "https://www.federalreserve.gov/final"
    assert response.redirect_count == 1
    assert response.content == b"<rss/>"


def test_gzip_response_is_decoded_with_independent_byte_bounds():
    document = b"<rss><channel><title>Curated</title></channel></rss>"
    compressed = gzip.compress(document, mtime=0)

    def handler(request):
        return httpx.Response(
            200,
            headers={
                "content-type": "application/rss+xml",
                "content-encoding": "gzip",
                "content-length": str(len(compressed)),
            },
            content=compressed,
        )

    origin = target()
    dispatch = dispatch_for(origin)
    transport = GuardedNewsTransport(
        dispatch,
        targets=[origin],
        limits=RefreshLimits(),
        client_factory=lambda selected: dispatch.httpx_client(selected, inner_transport=StreamingTransport(handler)),
    )

    response = transport.fetch(
        FetchRequest(
            source_id="fed",
            url="https://www.federalreserve.gov/feed.xml",
            accepted_media_types=("application/rss+xml",),
            sec_identity_required=False,
        )
    )

    assert response.content == document
    assert response.compressed_bytes == len(compressed)
    assert response.decompressed_bytes == len(document)


def test_streaming_response_checks_deadline_between_chunks():
    origin = target()
    dispatch = dispatch_for(origin)
    checks = []

    class Gate:
        def __init__(self, _url):
            pass

        def __enter__(self):
            def checkpoint():
                checks.append(len(checks) + 1)
                if len(checks) >= 2:
                    raise RequestTimeout("deadline elapsed")

            return checkpoint

        def __exit__(self, *args):
            return False

    class SlowDrip(httpx.SyncByteStream):
        def __iter__(self):
            yield b"<rss>"
            yield b"</rss>"

    def client_factory(_target):
        class Client:
            def stream(self, method, url, headers):
                request = httpx.Request(method, url, headers=headers)
                response = httpx.Response(
                    200,
                    headers={"content-type": "application/rss+xml"},
                    stream=SlowDrip(),
                    request=request,
                )
                return nullcontext(response)

            def close(self):
                pass

        return Client()

    transport = GuardedNewsTransport(
        dispatch,
        targets=(origin,),
        limits=RefreshLimits(),
        request_gate=Gate,
        client_factory=client_factory,
    )

    with pytest.raises(RequestTimeout):
        transport.fetch(
            FetchRequest(
                source_id="fed",
                url="https://www.federalreserve.gov/feed.xml",
                accepted_media_types=("application/rss+xml",),
                sec_identity_required=False,
            )
        )
    assert len(checks) >= 2


def test_sec_destination_cannot_bypass_identity_flag():
    called = False

    def handler(request):
        nonlocal called
        called = True
        return httpx.Response(200, headers={"content-type": "application/json"}, content=b"{}")

    sec = target("data.sec.gov")
    dispatch = dispatch_for(sec)
    transport = GuardedNewsTransport(
        dispatch,
        targets=[sec],
        limits=RefreshLimits(),
        client_factory=lambda selected: dispatch.httpx_client(selected, inner_transport=StreamingTransport(handler)),
    )

    with pytest.raises(AuthorizationDenied):
        transport.fetch(
            FetchRequest(
                source_id="misconfigured",
                url="https://data.sec.gov/submissions/CIK0000000001.json",
                accepted_media_types=("application/json",),
                sec_identity_required=False,
            )
        )
    assert not called
