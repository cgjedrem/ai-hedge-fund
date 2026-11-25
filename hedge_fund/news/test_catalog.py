import json

import pytest
from pydantic import ValidationError

from hedge_fund.news.catalog import CatalogValidationError, load_catalog
from hedge_fund.news.models import RefreshLimits

REGISTRY = {
    "name": "plenaryapp/awesome-rss-feeds",
    "commit": "9ab2482cae9031a5a39635c887fcfc8ece7e130a",
    "license": "CC0-1.0",
    "repository_url": "https://github.com/plenaryapp/awesome-rss-feeds",
    "reviewed_on": "2026-11-25",
}


def source(**changes):
    value = {
        "source_id": "example-company-ir",
        "kind": "feed",
        "publisher": "Example Company Investor Relations",
        "category": "investor-relations",
        "url": "https://ir.example.com/news.xml",
        "enabled": True,
        "allowed_hosts": ["ir.example.com"],
        "scope": "company",
        "tickers": ["EXAMPLE"],
        "cik": None,
        "forms": [],
        "company_aliases": ["Example Company"],
        "freshness_seconds": 86400,
        "limits": None,
        "curation": {
            "basis": "independently-verified",
            "registry_opml_path": None,
            "registry_xml_url": None,
            "discovery_url": "https://ir.example.com/",
            "verified_on": "2026-11-25",
            "purpose": "Official company investor-relations announcements.",
            "rights_note": "Use feed title, link, attribution and timestamps only; no article body or summary retained.",
            "approved_by": "catalog-review-change",
        },
        "summary_policy": "none",
        "sequence": 100,
    }
    value.update(changes)
    return value


def catalog_bytes(*sources):
    return json.dumps(
        {
            "schema_version": 1,
            "catalog_id": "test-catalog",
            "registry": REGISTRY,
            "sources": list(sources),
        }
    ).encode("utf-8")


@pytest.mark.parametrize(
    "limits",
    [
        {"global_concurrency": 5},
        {"per_host_concurrency": 2},
        {"minimum_host_interval_seconds": 0.5},
    ],
)
def test_refresh_limits_cannot_weaken_documented_bounds(limits):
    with pytest.raises(ValidationError):
        RefreshLimits(**limits)


def test_load_catalog_validates_and_digests_reviewed_source(tmp_path):
    resource = tmp_path / "catalog.json"
    resource.write_bytes(catalog_bytes(source()))

    catalog = load_catalog(resource)

    assert catalog.schema_version == 1
    assert catalog.sources[0].source_id == "example-company-ir"
    assert catalog.sources[0].tickers == ("EXAMPLE",)
    assert len(catalog.digest) == 64
    assert catalog.digest == load_catalog(resource).digest


def test_catalog_accepts_non_yahoo_lookalikes_and_reviewed_editorial_aliases(tmp_path):
    resource = tmp_path / "catalog.json"
    resource.write_bytes(
        catalog_bytes(
            source(url="https://notyahoo.com/news.xml", allowed_hosts=["notyahoo.com"]),
            source(source_id="reviewed-editorial", category="editorial", company_aliases=["Example Incorporated"]),
        )
    )

    catalog = load_catalog(resource)

    assert [item.source_id for item in catalog.sources] == ["example-company-ir", "reviewed-editorial"]


@pytest.mark.parametrize(
    "sources",
    [
        [source(url="http://ir.example.com/news.xml")],
        [source(url="https://ir.example.com:444/news.xml")],
        [source(url="https://127.0.0.1/news.xml", allowed_hosts=["127.0.0.1"])],
        [source(url="https://ir.example.com/news.xml#fragment")],
        [source(allowed_hosts=["elsewhere.example.com"])],
        [source(url="https://feeds.yahoo.com/news.xml", allowed_hosts=["feeds.yahoo.com"])],
        [source(allowed_hosts=["ir.example.com", "feeds.yahoo.com"])],
        [source(allowed_hosts=["ir.example.com", "192.0.2.1"])],
        [source(allowed_hosts=["ir.example.com", "bad_host.example.com"])],
        [source(allowed_hosts=["ir.example.com", "-bad.example.com"])],
        [source(source_id="bad", allowed_hosts=["IR.EXAMPLE.COM"])],
        [source(category="editorial", company_aliases=[])],
        [source(category="editorial", company_aliases=["Example Incorporated"], scope="market", tickers=[])],
        [source(category="editorial", company_aliases=["Example Incorporated"], tickers=["EXAMPLE", "OTHER"])],
        [source(tickers=[])],
        [source(scope="market")],
        [source(kind="feed", cik="0000000001")],
        [source(kind="sec-edgar", cik=None, forms=["8-K"], category="sec-filing")],
        [source(kind="sec-edgar", cik="0000000001", forms=[], category="sec-filing", url="https://data.sec.gov/submissions/CIK0000000001.json", allowed_hosts=["data.sec.gov", "www.sec.gov"])],
        [source(curation={**source()["curation"], "approved_by": "TODO"})],
        [source(curation={**source()["curation"], "basis": "registry-reviewed"})],
        [source(curation={**source()["curation"], "registry_opml_path": "README.md"})],
        [source(summary_policy="feed-supplied")],
        [source(), source()],
    ],
    ids=[
        "https-only",
        "default-port-only",
        "no-ip-literal",
        "no-fragment",
        "origin-must-be-allowed",
        "yahoo-denied",
        "yahoo-redirect-host-denied",
        "allowed-host-ip-denied",
        "allowed-host-underscore-denied",
        "allowed-host-label-denied",
        "canonical-host",
        "editorial-needs-reviewed-alias",
        "editorial-needs-company-scope",
        "editorial-needs-one-explicit-ticker",
        "company-needs-ticker",
        "market-has-no-tickers",
        "feed-cannot-have-cik",
        "sec-needs-cik",
        "sec-needs-forms",
        "approval-not-placeholder",
        "registry-evidence-required",
        "independent-cannot-claim-registry",
        "summary-rights-required",
        "unique-source-id",
    ],
)
def test_catalog_rejects_invalid_semantics_before_a_plan_exists(tmp_path, sources):
    resource = tmp_path / "catalog.json"
    resource.write_bytes(catalog_bytes(*sources))

    with pytest.raises(CatalogValidationError):
        load_catalog(resource)
