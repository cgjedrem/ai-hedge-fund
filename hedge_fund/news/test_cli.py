import json
from datetime import datetime, UTC
from importlib.resources import files

import pytest

from hedge_fund import paths, run
from hedge_fund.news.catalog import load_catalog
from hedge_fund.news.models import RefreshLimits, RefreshRun, SourceOutcome
from hedge_fund.news.store import NewsStore
from hedge_fund.runtime.handover import enroll_fresh
from hedge_fund.runtime.root import RootContext, RootPathError


def invoke(monkeypatch, root, *arguments):
    monkeypatch.setattr(run, "_load_runtime", lambda: None)
    run.main(["--root", str(root), *arguments])


def test_news_status_is_offline_and_refresh_requires_network(tmp_path, monkeypatch, capsys):
    with RootContext.open(tmp_path) as root:
        enroll_fresh(root)
    monkeypatch.setattr(run, "make_data_client", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("network client constructed")))

    invoke(monkeypatch, tmp_path, "news", "status", "--json")
    status = json.loads(capsys.readouterr().out)
    assert status["status"] == "ok"
    assert any(item["source_id"] == "federal-reserve-all-press" and item["status"] == "never-run" for item in status["sources"])

    with pytest.raises(SystemExit) as denied:
        invoke(monkeypatch, tmp_path, "news", "refresh", "--ticker", "NOT-CONFIGURED")
    assert denied.value.code == 2


def test_news_refresh_empty_ticker_selection_is_json_noop(tmp_path, monkeypatch, capsys):
    with RootContext.open(tmp_path) as root:
        enroll_fresh(root)

    invoke(
        monkeypatch,
        tmp_path,
        "--enable-network",
        "news",
        "refresh",
        "--ticker",
        "NOT-CONFIGURED",
        "--json",
    )

    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "no-op"
    assert payload["source_ids"] == []
    assert payload["total_requests"] == 0


def test_sec_feed_identity_is_validated_before_transport_construction(tmp_path, monkeypatch):
    from hedge_fund.news import cli

    with RootContext.open(tmp_path) as root:
        enroll_fresh(root)
    monkeypatch.setenv("HEDGE_FUND_NEWS_SEC_IDENTITY", "python-httpx")

    def forbidden_dispatch(*args, **kwargs):
        raise AssertionError("dispatch constructed before SEC identity validation")

    monkeypatch.setattr(cli, "make_one_shot_dispatch", forbidden_dispatch)
    with pytest.raises(SystemExit) as invalid:
        invoke(
            monkeypatch,
            tmp_path,
            "--enable-network",
            "news",
            "refresh",
            "--source",
            "sec-press-releases",
        )

    assert invalid.value.code == 2


def test_news_status_reports_unknown_absent_and_known_disabled(tmp_path, monkeypatch, capsys):
    with RootContext.open(tmp_path) as root:
        enroll_fresh(root)

    invoke(
        monkeypatch,
        tmp_path,
        "news",
        "status",
        "--source",
        "not-reviewed",
        "--source",
        "amd-investor-relations",
        "--json",
    )

    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ok"
    assert payload["absent_source_ids"] == ["not-reviewed"]
    assert [(item["source_id"], item["status"]) for item in payload["sources"]] == [("amd-investor-relations", "disabled")]


def test_status_uses_current_disabled_catalog_state_over_stored_health(tmp_path, monkeypatch, capsys):
    with RootContext.open(tmp_path) as root:
        enroll_fresh(root)
    catalog = load_catalog(files("hedge_fund.news").joinpath("catalog.json"))
    disabled = next(item for item in catalog.sources if item.source_id == "amd-investor-relations")
    previously_enabled = disabled.model_copy(update={"enabled": True})
    now = datetime(2026, 11, 25, tzinfo=UTC)
    run_result = RefreshRun(
        run_id="before-source-was-disabled",
        catalog_digest=catalog.digest,
        source_ids=(disabled.source_id,),
        started_at=now,
        ended_at=now,
        limits=RefreshLimits(),
        status="succeeded",
        outcomes=(
            SourceOutcome(
                source_id=disabled.source_id,
                status="healthy-empty",
                started_at=now,
                finished_at=now,
            ),
        ),
    )
    with RootContext.open(tmp_path) as root, paths.bound_root(root):
        NewsStore(root).commit(
            expected_revision=0,
            run=run_result,
            entries=(),
            sources=(previously_enabled,),
        )

    invoke(monkeypatch, tmp_path, "news", "status", "--source", disabled.source_id, "--json")

    item = json.loads(capsys.readouterr().out)["sources"][0]
    assert item["enabled"] is False
    assert item["status"] == "disabled"


def test_refresh_runtime_value_error_is_sanitized_not_reported_as_usage(tmp_path, monkeypatch, capsys):
    from hedge_fund.news import cli

    with RootContext.open(tmp_path) as root:
        enroll_fresh(root)

    class FailingRefresher:
        def refresh(self, _request):
            raise ValueError(r"invalid persisted value at C:\private\desk\state.json")

    monkeypatch.setattr(cli, "NewsRefresher", FailingRefresher)
    with pytest.raises(SystemExit) as failure:
        invoke(
            monkeypatch,
            tmp_path,
            "--enable-network",
            "news",
            "refresh",
            "--source",
            "federal-reserve-all-press",
        )

    captured = capsys.readouterr()
    assert failure.value.code == 1
    assert captured.out == ""
    assert captured.err == "curated news refresh failed\n"
    assert "private" not in captured.err


@pytest.mark.parametrize(
    "error",
    [
        OSError(r"cannot read C:\private\desk\state.json"),
        RootPathError(r"escaped C:\private\desk\state.json"),
    ],
    ids=["os-error", "root-path-error"],
)
def test_refresh_runtime_filesystem_errors_are_sanitized(tmp_path, monkeypatch, capsys, error):
    from hedge_fund.news import cli

    with RootContext.open(tmp_path) as root:
        enroll_fresh(root)

    class FailingRefresher:
        def refresh(self, _request):
            raise error

    monkeypatch.setattr(cli, "NewsRefresher", FailingRefresher)
    with pytest.raises(SystemExit) as failure:
        invoke(
            monkeypatch,
            tmp_path,
            "--enable-network",
            "news",
            "refresh",
            "--source",
            "federal-reserve-all-press",
        )

    captured = capsys.readouterr()
    assert failure.value.code == 1
    assert captured.out == ""
    assert captured.err == "curated news refresh failed\n"
    assert "private" not in captured.err


def test_refresh_rejects_malformed_source_selector_as_usage(tmp_path, monkeypatch, capsys):
    from hedge_fund.news import cli

    with RootContext.open(tmp_path) as root:
        enroll_fresh(root)
    monkeypatch.setattr(
        cli,
        "make_one_shot_dispatch",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("dispatch constructed")),
    )

    with pytest.raises(SystemExit) as failure:
        invoke(
            monkeypatch,
            tmp_path,
            "--enable-network",
            "news",
            "refresh",
            "--source",
            "../private",
        )

    captured = capsys.readouterr()
    assert failure.value.code == 2
    assert captured.out == ""
    assert "news source selection or request bounds are invalid" in captured.err
    assert "../private" not in captured.err
