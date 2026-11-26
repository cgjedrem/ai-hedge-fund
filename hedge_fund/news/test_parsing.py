import builtins
import time
from datetime import datetime, timezone
from io import BytesIO

import feedparser
import pytest

from hedge_fund.news.models import SourceDefinition
from hedge_fund.news.parsing import FeedParseError, parse_feed
from hedge_fund.news.test_catalog import source

FETCHED_AT = datetime(2026, 11, 25, 18, 0, tzinfo=timezone.utc)


def definition(**changes) -> SourceDefinition:
    return SourceDefinition.model_validate(source(**changes))


def test_parse_bytes_returns_bounded_inert_attributions_without_network(monkeypatch):
    payload = b"""<?xml version="1.0"?><rss version="2.0"><channel><title>IR</title>
      <item><title>A &amp; B</title><link>https://ir.example.com/story?id=1&amp;utm_source=rss#top</link>
      <guid>release-1</guid><pubDate>Wed, 25 Nov 2026 12:34:56 -0500</pubDate>
      <description><![CDATA[<p>Hello <b>world</b></p><script>alert(1)</script>]]></description></item>
    </channel></rss>"""
    real_parse = feedparser.parse
    seen = []

    def checked_parse(value, *args, **kwargs):
        seen.append(value)
        return real_parse(value, *args, **kwargs)

    monkeypatch.setattr(feedparser, "parse", checked_parse)
    parsed = parse_feed(payload, definition(), FETCHED_AT)

    assert len(seen) == 1
    assert isinstance(seen[0], BytesIO)
    assert seen[0].getvalue() == payload
    assert parsed.rejected_count == 0
    assert len(parsed.entries) == 1
    entry = parsed.entries[0]
    assert entry.attribution.original_id == "release-1"
    assert entry.attribution.normalized_url == "https://ir.example.com/story?id=1"
    assert entry.attribution.published_at == datetime(2026, 11, 25, 17, 34, 56, tzinfo=timezone.utc)
    assert entry.summary is None
    assert entry.dedupe_keys[0] == "url:https://ir.example.com/story?id=1"


def test_path_shaped_bytes_are_never_reinterpreted_as_a_file(tmp_path, monkeypatch):
    document = tmp_path / "outside.xml"
    document.write_bytes(b'<rss version="2.0"><channel><item><title>Local file</title>' b"<link>https://ir.example.com/local</link></item></channel></rss>")
    opened = []
    real_open = builtins.open

    def checked_open(file, *args, **kwargs):
        opened.append(file)
        return real_open(file, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", checked_open)
    with pytest.raises(FeedParseError) as error:
        parse_feed(str(document).encode(), definition(), FETCHED_AT)

    assert error.value.reason_code == "malformed-feed"
    assert document.__fspath__().encode() not in opened


def test_well_formed_non_feed_xml_is_not_healthy_empty():
    with pytest.raises(FeedParseError) as error:
        parse_feed(
            b'<html xmlns="http://www.w3.org/1999/xhtml"><head><title>Not a feed</title></head></html>',
            definition(),
            FETCHED_AT,
        )

    assert error.value.reason_code == "malformed-feed"


@pytest.mark.parametrize(
    ("payload", "limit", "reason"),
    [
        (b"<rss><channel><item><title>broken</title></channel></rss>", 500, "malformed-feed"),
        (b"<rss><channel><item><title>A</title><link>https://ir.example.com/a</link></item><item><title>B</title><link>https://ir.example.com/b</link></item></channel></rss>", 1, "entry-limit"),
        (b"<rss><channel><item><title>Offsite</title><link>https://evil.example/story</link></item></channel></rss>", 500, None),
    ],
)
def test_parser_fails_or_rejects_without_secondary_fetches(payload, limit, reason):
    if reason:
        with pytest.raises(FeedParseError) as error:
            parse_feed(payload, definition(), FETCHED_AT, max_entries=limit)
        assert error.value.reason_code == reason
    else:
        parsed = parse_feed(payload, definition(), FETCHED_AT, max_entries=limit)
        assert parsed.entries == ()
        assert parsed.rejected_count == 1


def test_parser_uses_feedparser_timestamp_when_raw_timestamp_is_unusable(monkeypatch):
    parsed_time = time.struct_time((2026, 11, 25, 17, 34, 56, 2, 329, 0))
    monkeypatch.setattr(
        feedparser,
        "parse",
        lambda value: feedparser.FeedParserDict(
            {
                "bozo": False,
                "version": "rss20",
                "entries": [
                    {
                        "title": "Timestamp fallback",
                        "link": "https://ir.example.com/timestamp",
                        "published": "not-a-date",
                        "published_parsed": parsed_time,
                    }
                ],
            }
        ),
    )

    parsed = parse_feed(b"offline bytes", definition(), FETCHED_AT)

    assert parsed.entries[0].attribution.published_at == datetime(2026, 11, 25, 17, 34, 56, tzinfo=timezone.utc)


@pytest.mark.parametrize(
    ("title", "summary", "expected"),
    [
        ("Example (Holdings) announces results", "", 1),
        ("Example Holdings announces results", "", 0),
        ("Quarterly results", "Example (Holdings) released its report.", 1),
        ("Unrelated issuer announces results", "No reviewed company is named.", 0),
    ],
)
def test_editorial_entries_require_a_literal_reviewed_alias_match(title, summary, expected):
    payload = f"""<rss version="2.0"><channel><item><title>{title}</title>
      <link>https://ir.example.com/editorial</link><description>{summary}</description>
      </item></channel></rss>""".encode()
    selected = definition(category="editorial", company_aliases=["Example (Holdings)"])

    parsed = parse_feed(payload, selected, FETCHED_AT)

    assert len(parsed.entries) == expected
    assert parsed.rejected_count == 1 - expected
    if parsed.entries:
        assert parsed.entries[0].attribution.tickers == ("EXAMPLE",)
