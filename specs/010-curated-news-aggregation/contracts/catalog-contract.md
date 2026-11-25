# Curated Catalog Contract v1

Machine-readable syntax: [catalog-v1.schema.json](catalog-v1.schema.json). Field semantics and state rules: [../data-model.md](../data-model.md).

## Loading boundary

`load_catalog(resource: Traversable) -> CuratedCatalog` accepts only packaged catalog bytes. It does not resolve URLs or perform I/O outside the supplied resource. The JSON Schema documents and reviews the serialized shape; Pydantic is the normative runtime validator and adds semantic checks because schema patterns alone cannot prove host ownership, company/CIK consistency, rights, or stricter limits. No runtime JSON-Schema dependency is required.

Validation failures raise `CatalogValidationError` before dispatch construction. There is no partial catalog and no automatic fallback to a registry URL.

Semantic checks include:

1. Unique source IDs, canonical origins, and source bindings; canonical deterministic digest.
2. HTTPS, port 443 only, no credentials/fragments/secret-bearing query parameters, IP literals, wildcards, or unapproved redirect origins.
3. Deny Yahoo by reviewed provider identity and host suffix, not merely one literal hostname; deny podcast/blog/irrelevant categories regardless of registry membership.
4. `allowed_hosts` contains the source origin; only those exact hosts may receive provider targets. No host inherited from another source is implied.
5. Company sources have explicit ticker bindings. SEC EDGAR sources have one company, ten-digit CIK, bounded forms, an approved SEC submissions endpoint, and an explicitly approved official filing-index link host.
6. `summary_policy=feed-supplied` requires a meaningful rights note. The note never licenses article-body retrieval.
7. Registry-derived records reference the pinned commit and exact OPML path/original URL. Independent records reference an official discovery page.
8. Source limits may only tighten the global limits. A catalog cannot raise aggregate authorization.

## Minimal illustrative entry

This example describes shape only; it is not an enabled production source or a live-test instruction.

```json
{
  "schema_version": 1,
  "catalog_id": "example",
  "registry": {
    "name": "plenaryapp/awesome-rss-feeds",
    "commit": "9ab2482cae9031a5a39635c887fcfc8ece7e130a",
    "license": "CC0-1.0",
    "repository_url": "https://github.com/plenaryapp/awesome-rss-feeds",
    "reviewed_on": "2026-11-25"
  },
  "sources": [
    {
      "source_id": "example-company-ir",
      "kind": "feed",
      "publisher": "Example Company Investor Relations",
      "category": "investor-relations",
      "url": "https://ir.example.com/news.xml",
      "enabled": false,
      "allowed_hosts": ["ir.example.com"],
      "scope": "company",
      "tickers": ["EXAMPLE"],
      "cik": null,
      "forms": [],
      "company_aliases": ["Example Company"],
      "freshness_seconds": 86400,
      "limits": null,
      "curation": {
        "basis": "independently-verified",
        "registry_opml_path": null,
        "registry_xml_url": null,
        "discovery_url": "https://ir.example.com/",
        "verified_on": "2026-11-25",
        "purpose": "Official company investor-relations announcements.",
        "rights_note": "Use feed title, link, attribution and timestamps only; no article body or summary retained.",
        "approved_by": "catalog-review-change"
      },
      "summary_policy": "none",
      "sequence": 100
    }
  ]
}
```

## Change review

A catalog change review must show added/removed source IDs, origin and redirect-host changes, ticker/CIK/form changes, rights/summary changes, and registry commit movement. Reviewers must be able to reproduce the catalog digest without network access. A changed URL or owner is a new approval decision; an existing source ID does not grandfather trust.
