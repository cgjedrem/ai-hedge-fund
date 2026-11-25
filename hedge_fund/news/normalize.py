"""Deterministic, inert normalization for untrusted news metadata."""

from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime, timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from time import struct_time
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit

_TRACKING = {"fbclid", "gclid", "mc_cid", "mc_eid", "igshid"}
_SPACE = re.compile(r"\s+")


class _TextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.hidden = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() in {"script", "style", "template", "svg"}:
            self.hidden += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"script", "style", "template", "svg"} and self.hidden:
            self.hidden -= 1

    def handle_data(self, data: str) -> None:
        if not self.hidden:
            self.parts.append(data)


def clean_text(value: object, max_length: int = 1000) -> str:
    parser = _TextParser()
    parser.feed(str(value or "")[: max_length * 4])
    parser.close()
    return _SPACE.sub(" ", unicodedata.normalize("NFKC", " ".join(parser.parts))).strip()[:max_length].strip()


def normalize_title(value: object) -> str:
    return clean_text(value).casefold()


def _decode_unreserved(value: str) -> str:
    return re.sub(r"%([0-7][0-9A-Fa-f])", lambda match: chr(int(match.group(1), 16)) if chr(int(match.group(1), 16)).isalnum() or chr(int(match.group(1), 16)) in "-._~" else match.group(0), value)


def normalize_url(value: str) -> str:
    parsed = urlsplit(value.strip())
    if parsed.scheme.lower() != "https" or not parsed.hostname or parsed.port not in (None, 443):
        raise ValueError("news links must use HTTPS on the default port")
    host = _decode_unreserved(parsed.hostname).encode("idna").decode("ascii").lower()
    path = quote(_decode_unreserved(parsed.path), safe="/%:@!$&'()*+,;=-._~")
    segments: list[str] = []
    for segment in path.split("/"):
        if segment == "..":
            if segments:
                segments.pop()
        elif segment != ".":
            segments.append(segment)
    path = "/".join(segments)
    if not path.startswith("/"):
        path = "/" + path
    if not path:
        path = ""
    query = urlencode(
        [(key, val) for key, val in parse_qsl(parsed.query, keep_blank_values=True) if not key.lower().startswith("utm_") and key.lower() not in _TRACKING],
        quote_via=quote,
        safe="-._~",
    )
    return urlunsplit(("https", host, path, query, ""))


def parse_publication_time(value: object) -> tuple[datetime | None, date | None, str]:
    if value is None:
        return None, None, "unknown"
    if isinstance(value, struct_time):
        try:
            parsed = datetime(*value[:6], tzinfo=timezone.utc)
        except (TypeError, ValueError):
            return None, None, "unknown"
    elif isinstance(value, datetime):
        parsed = value
    elif isinstance(value, date):
        return None, value, "day"
    else:
        text = str(value).strip()
        try:
            parsed = parsedate_to_datetime(text)
        except (TypeError, ValueError):
            try:
                parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
            except (TypeError, ValueError):
                return None, None, "unknown"
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None, parsed.date(), "day"
    precise = parsed.astimezone(timezone.utc)
    return precise, parsed.date(), "minute" if precise.second == 0 and precise.microsecond == 0 else "second"


def identity_keys(
    *,
    normalized_url: str | None,
    title: str,
    original_id: str | None,
    published_at: datetime | None,
    published_on: date | None,
    association: str | None = None,
    associations: tuple[str, ...] = (),
) -> tuple[str, ...]:
    keys: list[str] = []
    if original_id:
        accession = original_id.replace("-", "")
        if accession.isdigit() and len(accession) == 18:
            keys.append(f"sec:{accession}")
    if normalized_url:
        keys.append(f"url:{normalized_url}")
    if published_at is not None:
        minute = published_at.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M")
        values = associations or ((association,) if association else ())
        for value in values:
            keys.append(f"title:{normalize_title(title)}|{minute}|{value}")
    return tuple(keys)
