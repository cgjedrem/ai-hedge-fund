import json
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone

import pytest

from hedge_fund import paths
from hedge_fund.data.protocol import DataClientError
from hedge_fund.news.filings import filing_news_entries, FilingRecord
from hedge_fund.news.models import (
    NewsQuery,
    RefreshLimits,
    RefreshRun,
    SourceDefinition,
    SourceOutcome,
)
from hedge_fund.news.parsing import parse_feed, ParsedNewsEntry
from hedge_fund.news.store import NewsRevisionConflict, NewsStore
from hedge_fund.news.test_catalog import source
from hedge_fund.runtime.handover import enroll_fresh
from hedge_fund.runtime.root import RootContext, RootPathError

NOW = datetime(2026, 11, 25, 18, 0, tzinfo=timezone.utc)


@contextmanager
def synthetic_store(tmp_path):
    with RootContext.open(tmp_path) as root:
        enroll_fresh(root)
        with paths.bound_root(root):
            yield NewsStore(root), root


def definition(**changes) -> SourceDefinition:
    return SourceDefinition.model_validate(source(**changes))


def entry(value: SourceDefinition, *, url="https://ir.example.com/story?id=1", title="Results", original_id=None) -> ParsedNewsEntry:
    identity = f"<guid>{original_id}</guid>" if original_id else ""
    payload = f"<rss><channel><item><title>{title}</title><link>{url}</link>{identity}<pubDate>Wed, 25 Nov 2026 12:34:56 -0500</pubDate></item></channel></rss>".encode()
    return parse_feed(payload, value, NOW).entries[0]


def run(source_id="example-company-ir", run_id="run-1", started_at=NOW, outcome_status="healthy", accepted_count=1, new_count=1, rejected_count=0) -> RefreshRun:
    outcome = SourceOutcome(source_id=source_id, status=outcome_status, started_at=started_at, finished_at=started_at, request_count=1, accepted_count=accepted_count, rejected_count=rejected_count, new_count=new_count)
    status = "failed" if outcome_status == "failed" else "partial" if outcome_status == "degraded" else "succeeded"
    return RefreshRun(run_id=run_id, catalog_digest="a" * 64, source_ids=(source_id,), started_at=started_at, ended_at=started_at, limits=RefreshLimits(), status=status, outcomes=(outcome,), total_requests=1, total_new_items=new_count)


def test_query_filters_dates_and_orders_items_with_injected_health_clock(tmp_path):
    with synthetic_store(tmp_path) as (_store, root):
        configured = definition(freshness_seconds=60)
        older = entry(configured, url="https://ir.example.com/older", title="Older")
        older = older.model_copy(update={"attribution": older.attribution.model_copy(update={"published_at": NOW - timedelta(hours=1)})})
        newer = entry(configured, url="https://ir.example.com/newer", title="Newer")
        undated = entry(configured, url="https://ir.example.com/undated", title="Undated")
        undated = undated.model_copy(
            update={
                "attribution": undated.attribution.model_copy(
                    update={
                        "published_at": None,
                        "published_on": None,
                        "publication_precision": "unknown",
                    }
                )
            }
        )
        store = NewsStore(root, clock=lambda: NOW + timedelta(days=2))
        store.commit(
            expected_revision=0,
            run=run(accepted_count=3, new_count=3),
            entries=(older, undated, newer),
            sources=(configured,),
        )

        page = store.query(
            NewsQuery(
                ticker="EXAMPLE",
                start_date=date(2026, 11, 25),
                end_date=date(2026, 11, 25),
                include_undated=False,
            )
        )

        assert [item.title for item in page.items] == ["Newer", "Older"]
        assert [view.source_id for view in page.health] == [configured.source_id]
        assert page.health[0].freshness == "stale"
        assert page.health[0].is_stale is True


def test_store_merges_by_url_and_is_idempotent_across_restart(tmp_path):
    with synthetic_store(tmp_path) as (store, _root):
        original = definition()
        other = definition(source_id="example-syndicated", publisher="Syndicated IR", sequence=200)
        parsed = entry(original)
        repeated = entry(other)

        first = store.commit(expected_revision=0, run=run(), entries=(parsed,), sources=(original,))
        second = store.commit(expected_revision=1, run=run(run_id="run-2"), entries=(repeated,), sources=(other,))

        assert len(second.items) == 1
        item = next(iter(second.items.values()))
        assert item.news_id == next(iter(first.items))
        assert {a.source_id for a in item.attributions} == {"example-company-ir", "example-syndicated"}
        assert item.first_fetched_at == NOW
        replay = store.commit(expected_revision=2, run=run(), entries=(parsed,), sources=(original,))
        assert replay.revision == 2

        reopened = NewsStore(_root).load()
        assert reopened == second


def test_failed_replacement_preserves_previous_state(tmp_path, monkeypatch):
    with synthetic_store(tmp_path) as (store, root):
        store.commit(expected_revision=0, run=run(), entries=(entry(definition()),), sources=(definition(),))

        def fail_replace(*_args):
            raise OSError("simulated replacement failure")

        monkeypatch.setattr(RootContext, "replace_file", fail_replace)
        with pytest.raises(RootPathError):
            store.commit(expected_revision=1, run=run(run_id="run-2"), entries=(), sources=(definition(),))
        assert store.load().revision == 1
        assert list((root.path / "cache/news").glob("*.tmp")) == []


def test_bridging_observation_converges_existing_clusters(tmp_path):
    with synthetic_store(tmp_path) as (store, _root):
        configured = definition()
        first_url = "https://ir.example.com/first"
        second_url = "https://ir.example.com/second"
        first_accession = "0001193125-26-000001"
        second_accession = "0001193125-26-000002"
        initial = store.commit(
            expected_revision=0,
            run=run(),
            entries=(
                entry(configured, url=first_url, title="First", original_id=first_accession),
                entry(configured, url=second_url, title="Second", original_id=second_accession),
            ),
            sources=(configured,),
        )
        assert len(initial.items) == 2

        converged = store.commit(
            expected_revision=1,
            run=run(run_id="run-2"),
            entries=(entry(configured, url=first_url, title="Correction", original_id=second_accession),),
            sources=(configured,),
        )

        assert len(converged.items) == 1
        retained_id = min(initial.items)
        absorbed_id = max(initial.items)
        assert next(iter(converged.items)) == retained_id
        assert converged.aliases[absorbed_id] == retained_id
        item = converged.items[retained_id]
        assert len(item.attributions) == 3
        assert {a.original_url for a in item.attributions} == {first_url, second_url}
        assert {a.original_id for a in item.attributions} == {first_accession, second_accession}
        assert all(converged.aliases[key] == retained_id for key in item.dedupe_keys)


def test_title_fallback_does_not_bridge_conflicting_native_id_clusters(tmp_path):
    with synthetic_store(tmp_path) as (store, _root):
        configured = definition()
        third = definition(source_id="example-wire", publisher="Wire", url="https://wire.example.com/news.xml", allowed_hosts=["wire.example.com"], sequence=300)
        initial = store.commit(
            expected_revision=0,
            run=run(accepted_count=2, new_count=2),
            entries=(
                entry(configured, url="https://ir.example.com/first", title="Results", original_id="release-1"),
                entry(configured, url="https://ir.example.com/second", title="Results", original_id="release-2"),
            ),
            sources=(configured,),
        )
        assert len(initial.items) == 2

        observed = store.commit(
            expected_revision=1,
            run=run(run_id="run-2", source_id=third.source_id),
            entries=(entry(third, url="https://wire.example.com/results", title="Results"),),
            sources=(third,),
        )

        assert len(observed.items) == 3
        wire_items = [item for item in observed.items.values() if any(value.source_id == third.source_id for value in item.attributions)]
        assert len(wire_items) == 1
        assert len(wire_items[0].attributions) == 1
        native_ids = {tuple(value.original_id for value in item.attributions if value.source_id == configured.source_id) for item in observed.items.values() if any(value.source_id == configured.source_id for value in item.attributions)}
        assert native_ids == {("release-1",), ("release-2",)}


def test_title_fallback_does_not_bridge_conflicting_sec_clusters(tmp_path):
    with synthetic_store(tmp_path) as (store, _root):
        configured = definition()
        syndicated = definition(source_id="example-syndicated", publisher="Syndicated IR", sequence=200)
        third = definition(source_id="example-wire", publisher="Wire", url="https://wire.example.com/news.xml", allowed_hosts=["wire.example.com"], sequence=300)
        initial = store.commit(
            expected_revision=0,
            run=run(accepted_count=2, new_count=2),
            entries=(
                entry(configured, url="https://ir.example.com/first", title="Results", original_id="0001193125-26-000001"),
                entry(syndicated, url="https://ir.example.com/second", title="Results", original_id="0001193125-26-000002"),
            ),
            sources=(configured, syndicated),
        )
        assert len(initial.items) == 2

        observed = store.commit(
            expected_revision=1,
            run=run(run_id="run-2", source_id=third.source_id),
            entries=(entry(third, url="https://wire.example.com/results", title="Results"),),
            sources=(third,),
        )

        assert len(observed.items) == 3
        wire_items = [item for item in observed.items.values() if any(value.source_id == third.source_id for value in item.attributions)]
        assert len(wire_items) == 1
        sec_identities = {tuple(key for key in item.dedupe_keys if key.startswith("sec:")) for item in observed.items.values() if any(key.startswith("sec:") for key in item.dedupe_keys)}
        assert sec_identities == {("sec:000119312526000001",), ("sec:000119312526000002",)}


def test_title_fallback_merges_matching_minute_and_scope_without_native_ids(tmp_path):
    with synthetic_store(tmp_path) as (store, _root):
        first_source = definition(scope="market")
        second_source = definition(source_id="example-second", publisher="Second publisher", sequence=200, scope="market")
        state = store.commit(
            expected_revision=0,
            run=run(),
            entries=(
                entry(first_source, url="https://ir.example.com/one", title="Shared title"),
                entry(second_source, url="https://ir.example.com/two", title="Shared title"),
            ),
            sources=(first_source, second_source),
        )
        assert len(state.items) == 1
        item = next(iter(state.items.values()))
        assert len(item.attributions) == 2
        assert item.canonical_url == "https://ir.example.com/one"


def test_title_fallback_matches_any_shared_ticker(tmp_path):
    with synthetic_store(tmp_path) as (store, _root):
        first_source = definition(tickers=["FIRST", "SHARED"])
        second_source = definition(source_id="example-second", publisher="Second publisher", sequence=200, tickers=["OTHER", "SHARED"])
        state = store.commit(
            expected_revision=0,
            run=run(),
            entries=(
                entry(first_source, url="https://ir.example.com/one", title="Shared title"),
                entry(second_source, url="https://ir.example.com/two", title="Shared title"),
            ),
            sources=(first_source, second_source),
        )
        assert len(state.items) == 1


def test_conflicting_native_ids_from_one_source_do_not_merge_by_title(tmp_path):
    with synthetic_store(tmp_path) as (store, _root):
        configured = definition(scope="market")
        state = store.commit(
            expected_revision=0,
            run=run(),
            entries=(
                entry(configured, url="https://ir.example.com/one", title="Shared title", original_id="native-one"),
                entry(configured, url="https://ir.example.com/two", title="Shared title", original_id="native-two"),
            ),
            sources=(configured,),
        )
        assert len(state.items) == 2
        assert state.merge_conflict_count == 1


def test_merge_conflict_counter_saturates_and_persists(tmp_path, monkeypatch):
    with synthetic_store(tmp_path) as (store, _root):
        configured = definition(scope="market")
        previous = store.commit(
            expected_revision=0,
            run=run(),
            entries=(entry(configured, url="https://ir.example.com/one", title="Shared title", original_id="native-one"),),
            sources=(configured,),
        )
        near_limit = previous.model_copy(update={"merge_conflict_count": 999999})
        original_load = store.load
        monkeypatch.setattr(store, "load", lambda: near_limit)

        saturated = store.commit(
            expected_revision=1,
            run=run(run_id="run-2"),
            entries=(entry(configured, url="https://ir.example.com/two", title="Shared title", original_id="native-two"),),
            sources=(configured,),
        )

        monkeypatch.setattr(store, "load", original_load)
        assert saturated.merge_conflict_count == 1000000
        assert store.load().merge_conflict_count == 1000000


def test_different_publishers_native_ids_do_not_block_title_merge(tmp_path):
    with synthetic_store(tmp_path) as (store, _root):
        first_source = definition(scope="market")
        second_source = definition(source_id="example-second", publisher="Second publisher", sequence=200, scope="market")
        state = store.commit(
            expected_revision=0,
            run=run(new_count=2),
            entries=(
                entry(first_source, url="https://ir.example.com/one", title="Shared title", original_id="publisher-one"),
                entry(second_source, url="https://ir.example.com/two", title="Shared title", original_id="publisher-two"),
            ),
            sources=(first_source, second_source),
        )

        assert len(state.items) == 1
        assert {attribution.original_id for attribution in next(iter(state.items.values())).attributions} == {"publisher-one", "publisher-two"}
        assert state.merge_conflict_count == 0


def test_date_only_filing_publications_do_not_merge_by_title(tmp_path):
    with synthetic_store(tmp_path) as (store, _root):
        configured = definition(
            kind="sec-edgar",
            category="sec-filing",
            url="https://data.sec.gov/submissions/CIK0000000001.json",
            allowed_hosts=["data.sec.gov", "www.sec.gov"],
            cik="0000000001",
            forms=["8-K"],
        )
        records = tuple(
            FilingRecord(
                accession=accession,
                form="8-K",
                filing_date=date(2026, 11, 25),
                accepted_at=None,
                size=1,
                index_url=f"https://www.sec.gov/Archives/edgar/data/1/{accession.replace('-', '')}/{accession}-index.html",
            )
            for accession in ("0000000001-26-000001", "0000000001-26-000002")
        )
        state = store.commit(
            expected_revision=0,
            run=run(source_id=configured.source_id, new_count=2),
            entries=filing_news_entries(records, configured, NOW),
            sources=(configured,),
        )

        assert len(state.items) == 2
        assert all(item.publication_precision == "day" for item in state.items.values())


def test_degraded_valid_response_is_success_and_resets_failures(tmp_path):
    with synthetic_store(tmp_path) as (store, _root):
        configured = definition()
        store.commit(expected_revision=0, run=run(), entries=(entry(configured),), sources=(configured,))
        failed_at = NOW + timedelta(hours=1)
        failed = store.commit(
            expected_revision=1,
            run=run(run_id="run-2", started_at=failed_at, outcome_status="failed", accepted_count=0, new_count=0),
            entries=(),
            sources=(configured,),
        )
        assert failed.health[configured.source_id].consecutive_failures == 1

        degraded_at = NOW + timedelta(hours=2)
        degraded = store.commit(
            expected_revision=2,
            run=run(run_id="run-3", started_at=degraded_at, outcome_status="degraded", rejected_count=1),
            entries=(entry(configured, url="https://ir.example.com/degraded"),),
            sources=(configured,),
        )
        health = degraded.health[configured.source_id]
        assert health.status == "degraded"
        assert health.consecutive_failures == 0
        assert health.last_success_at == degraded_at


def test_health_publication_never_regresses(tmp_path):
    with synthetic_store(tmp_path) as (store, _root):
        configured = definition()
        newer = entry(configured, url="https://ir.example.com/newer")
        newer = newer.model_copy(update={"attribution": newer.attribution.model_copy(update={"published_at": NOW - timedelta(hours=1)})})
        store.commit(expected_revision=0, run=run(), entries=(newer,), sources=(configured,))
        older = entry(configured, url="https://ir.example.com/older")
        older = older.model_copy(update={"attribution": older.attribution.model_copy(update={"published_at": NOW - timedelta(hours=2)})})
        state = store.commit(
            expected_revision=1,
            run=run(run_id="run-2", started_at=NOW + timedelta(hours=1)),
            entries=(older,),
            sources=(configured,),
        )
        assert state.health[configured.source_id].last_publication_at == NOW - timedelta(hours=1)


def test_same_source_native_id_and_url_update_one_attribution(tmp_path):
    with synthetic_store(tmp_path) as (store, _root):
        configured = definition()
        store.commit(
            expected_revision=0,
            run=run(),
            entries=(entry(configured, title="Original", original_id="stable-id"),),
            sources=(configured,),
        )
        updated = entry(configured, title="Updated", original_id="stable-id")
        updated_at = NOW + timedelta(hours=1)
        updated = updated.model_copy(update={"attribution": updated.attribution.model_copy(update={"first_seen_at": updated_at, "last_seen_at": updated_at})})
        state = store.commit(
            expected_revision=1,
            run=run(run_id="run-2", started_at=updated_at),
            entries=(updated,),
            sources=(configured,),
        )
        item = next(iter(state.items.values()))
        assert len(item.attributions) == 1
        assert item.attributions[0].first_seen_at == NOW
        assert item.attributions[0].last_seen_at == updated_at


def test_replay_is_write_free_and_conflicting_revisions_fail(tmp_path, monkeypatch):
    with synthetic_store(tmp_path) as (store, _root):
        committed = store.commit(expected_revision=0, run=run(), entries=(entry(definition()),), sources=(definition(),))

        def unexpected_write(*_args, **_kwargs):
            raise AssertionError("a replay or rejected transaction must not write")

        monkeypatch.setattr(paths, "write_atomic", unexpected_write)
        replay = store.commit(expected_revision=0, run=run(), entries=(), sources=())
        assert replay == committed

        with pytest.raises(NewsRevisionConflict):
            store.commit(expected_revision=0, run=run(run_id="different-run"), entries=(), sources=())


def test_dangling_alias_is_rejected_on_load(tmp_path):
    with synthetic_store(tmp_path) as (store, root):
        configured = definition()
        store.commit(expected_revision=0, run=run(), entries=(entry(configured),), sources=(configured,))
        document = json.loads(root.read_bytes("cache/news/state.json"))
        document["aliases"]["absorbed-id"] = "news_" + "f" * 64
        root.write_bytes("cache/news/state.json", json.dumps(document).encode("utf-8"))
        with pytest.raises(DataClientError, match="curated news state is invalid"):
            store.load()


def test_missing_state_is_empty_and_corrupt_state_fails_closed(tmp_path):
    with synthetic_store(tmp_path) as (store, root):
        assert store.load().revision == 0
        root.mkdir("cache/news")
        root.write_bytes("cache/news/state.json", b'{"schema_version":1,"items":')
        with pytest.raises(DataClientError, match="curated news state is invalid"):
            store.load()


@pytest.mark.parametrize("sec_first", [False, True])
def test_exact_sec_accession_is_canonical_regardless_of_entry_order(tmp_path, sec_first):
    with synthetic_store(tmp_path) as (store, _root):
        url = "https://www.sec.gov/Archives/edgar/data/1045810/filing.htm"
        macro = definition(
            source_id="macro-release",
            publisher="Macro release",
            category="macro",
            scope="market",
            tickers=[],
            url=url,
            allowed_hosts=["www.sec.gov"],
            sequence=100,
        )
        sec = definition(
            source_id="sec-filing",
            kind="sec-edgar",
            publisher="SEC filing",
            category="sec-filing",
            url=url,
            allowed_hosts=["www.sec.gov"],
            cik="0001045810",
            forms=["8-K"],
            sequence=200,
        )
        sources = (sec, macro) if sec_first else (macro, sec)
        state = None
        for index, configured in enumerate(sources):
            original_id = "0001193125-26-000001" if configured is sec else None
            state = store.commit(
                expected_revision=index,
                run=run(source_id=configured.source_id, run_id=f"run-{index}"),
                entries=(entry(configured, url=url, original_id=original_id),),
                sources=(configured,),
            )

        assert state is not None
        assert len(state.items) == 1
        item = next(iter(state.items.values()))
        assert item.category == "sec-filing"
        assert next(attribution for attribution in item.attributions if attribution.source_id == "sec-filing").original_id == "0001193125-26-000001"
        assert item.title == "Results"
