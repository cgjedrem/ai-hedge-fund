from datetime import date, datetime, timezone

from hedge_fund.news.normalize import (
    clean_text,
    identity_keys,
    normalize_title,
    normalize_url,
    parse_publication_time,
)


def test_normalization_preserves_semantics_and_removes_tracking_noise():
    assert normalize_url("HTTPS://user:secret@Ex%61mple.com:443/a/./b/../story/%7Ealice?utm_source=rss&id=1&fbclid=x&id=2#section") == "https://example.com/a/story/~alice?id=1&id=2"
    assert normalize_url("https://example.com/path/?a=hello%20world") == "https://example.com/path/?a=hello%20world"
    assert clean_text('<p onclick="evil()">Hello <b>world</b></p><script>alert(1)</script><img src="x">') == "Hello world"
    assert normalize_title("  The   FED&#x2019;s   Move  ") == "the fed’s move"


def test_final_dot_segments_preserve_the_directory_trailing_slash():
    assert normalize_url("https://example.com/a/.") == "https://example.com/a/"
    assert normalize_url("https://example.com/a/b/..") == "https://example.com/a/"
    assert normalize_url("https://example.com/a/%2E") == "https://example.com/a/"
    assert normalize_url("https://example.com/a/b/%2E%2E") == "https://example.com/a/"
    assert normalize_url("https://example.com/a") != normalize_url("https://example.com/a/")


def test_timestamp_precision_and_identity_are_conservative():
    precise = parse_publication_time("2026-11-25T12:34:56-05:00")
    assert parse_publication_time("25 Nov 2026 17:34:56 +0000") == precise
    assert precise == (datetime(2026, 11, 25, 17, 34, 56, tzinfo=timezone.utc), date(2026, 11, 25), "second")
    assert parse_publication_time("2026-11-25T12:34:56") == (None, date(2026, 11, 25), "day")
    assert parse_publication_time("2026-11-25") == (None, date(2026, 11, 25), "day")
    assert parse_publication_time("not a date") == (None, None, "unknown")

    published_at, published_on, _ = precise
    assert identity_keys(normalized_url="https://example.com/story", title="A result", original_id="guid", published_at=published_at, published_on=published_on, association="EXAMPLE") == (
        "url:https://example.com/story",
        "title:a result|2026-11-25T17:34|EXAMPLE",
    )
    assert identity_keys(normalized_url="https://example.com/other", title="A result", original_id="0000320193-26-000001", published_at=published_at, published_on=published_on, association="EXAMPLE") == (
        "sec:000032019326000001",
        "url:https://example.com/other",
        "title:a result|2026-11-25T17:34|EXAMPLE",
    )
    assert identity_keys(normalized_url=None, title="A result", original_id=None, published_at=None, published_on=published_on, association="EXAMPLE") == ()
