import json
import os
from datetime import date, timedelta

import pytest
import yaml
from fastapi.testclient import TestClient

from hedge_fund.fund.spec import FundSpec
from hedge_fund.paper.deployed import load_deployed
from hedge_fund.paper.ledger import Ledger
from hedge_fund.pipeline.session import SessionRecord
from hedge_fund.test_support.handover import enroll_synthetic_root
from hedge_fund.web.app import create_app
from hedge_fund.web.schemas import DeployRequest
from hedge_fund.web.services import DeskService, ServiceError


def test_read_adapters_match_seeded_mandate_paper_ledger_and_report(demo_root):
    with TestClient(create_app(root=demo_root, demo=True)) as client:
        mandates = client.get("/api/mandates", headers={"host": "127.0.0.1"}).json()
        paper_list = client.get("/api/paper", headers={"host": "127.0.0.1"}).json()
        detail = client.get("/api/paper/demo-quality", headers={"host": "127.0.0.1"}).json()
        scorecard = client.get("/api/paper/demo-quality/scorecard", headers={"host": "127.0.0.1"}).json()
        report = client.get(
            "/api/paper/demo-quality/sessions/2024-06-04",
            headers={"host": "127.0.0.1"},
        ).json()
        research = client.get("/api/research", headers={"host": "127.0.0.1"}).json()

    assert mandates["items"][0]["name"] == "demo-quality"
    assert paper_list["items"][0]["nav"] == 100_995
    assert detail["ledger"] == {"ok": True, "error": None}
    assert detail["nav"] == 100_995
    assert detail["cash"] == 89_995
    assert detail["positions"] == [{"ticker": "AAPL", "shares": 100, "mark": 110, "market_value": 11_000}]
    assert [point["nav"] for point in detail["curve"]] == [100_000, 100_495, 100_995]
    assert detail["live_value"]["status"] == "unavailable"
    assert detail["live_value"]["value"] is None
    assert detail["runner"]["available"] is False
    assert detail["pending"]["source_record_hash"] == detail["last_record_hash"]
    assert detail["pending"]["decision_as_of"] == "2024-06-05"
    assert scorecard["fund"] == "demo-quality"
    assert report["executed"]["orders"][0]["ticker"] == "AAPL"
    assert report["executed"]["fills"][0]["quantity"] == 100
    executed = Ledger(demo_root / "paper" / "demo-quality").read("2024-06-04").executed
    assert executed is not None
    assert report["executed"]["trading_cost"] == executed.trading_cost
    assert report["executed"]["traded_notional"] == executed.traded_notional
    assert report["executed"]["commission"] == executed.commission
    assert report["executed"]["slippage"] == executed.slippage
    assert report["proposed"]["as_of"] == "2024-06-04"
    assert report["proposed"]["target_weights"] == {"AAPL": 0.1}
    assert len(research["items"]) == 1
    assert research["items"][0]["fund"] == "demo-quality"


def test_service_revalidates_its_bound_root_before_storage_access(tmp_path):
    service = DeskService(tmp_path)
    moved = tmp_path.with_name(f"{tmp_path.name}-moved")

    try:
        if os.name == "nt":
            with pytest.raises(OSError):
                tmp_path.rename(moved)
            assert service.list_mandates()["items"] == []
            assert not moved.exists()
        else:
            tmp_path.rename(moved)
            tmp_path.mkdir()
            with pytest.raises(ServiceError) as changed:
                service.list_mandates()
            assert changed.value.status_code == 409
            assert not (tmp_path / "mandates").exists()
    finally:
        service.close()


def test_read_only_enrolled_service_reports_explicit_write_denial(demo_root):
    service = DeskService(demo_root, allow_writes=False)
    try:
        capabilities = service.capabilities(None)
    finally:
        service.close()

    assert capabilities["enrollment_state"] == "enrolled"
    assert capabilities["writes"] is False
    assert capabilities["write_unavailable_reason"] == "write-capability-disabled"


def test_catalog_preserves_canonical_library_models_and_blend(demo_root):
    service = DeskService(demo_root)
    strategies = {item["name"]: item for item in service.catalog()["strategies"]}
    service.close()

    deep_value = strategies["deep-value"]
    contrarian = strategies["contrarian-value"]
    assert next(item for item in deep_value["models"] if item["name"] == "graham")["weight"] == 2.0
    assert next(item for item in contrarian["models"] if item["name"] == "burry")["weight"] == 2.0
    assert deep_value["blend"] == {
        "method": "conviction_weighted",
        "gross_target": 1.0,
        "mode": "long_only",
    }
    assert contrarian["blend"] == {
        "method": "conviction_weighted",
        "gross_target": 1.0,
        "mode": "long_short",
    }


def test_mandate_detail_api_resolves_yml_file_by_spec_name(demo_root, tmp_path):
    payload = yaml.safe_load((demo_root / "mandates" / "demo-quality.yaml").read_text(encoding="utf-8"))
    payload["name"] = "legacy-mandate"
    directory = tmp_path / "mandates"
    directory.mkdir()
    (directory / "legacy-file.yml").write_text(yaml.safe_dump(payload), encoding="utf-8")

    with TestClient(create_app(root=tmp_path)) as client:
        headers = {"host": "127.0.0.1"}
        collection = client.get("/api/mandates", headers=headers)
        detail = client.get("/api/mandates/legacy-mandate", headers=headers)

    assert collection.status_code == 200
    assert [item["name"] for item in collection.json()["items"]] == ["legacy-mandate"]
    assert detail.status_code == 200
    assert detail.json()["name"] == "legacy-mandate"
    assert detail.json()["spec"]["name"] == "legacy-mandate"


def test_deploy_resolves_yml_file_by_spec_name(demo_root, tmp_path):
    payload = yaml.safe_load((demo_root / "mandates" / "demo-quality.yaml").read_text(encoding="utf-8"))
    payload["name"] = "legacy-mandate"
    directory = tmp_path / "mandates"
    directory.mkdir()
    (directory / "legacy-file.yml").write_text(yaml.safe_dump(payload), encoding="utf-8")
    enroll_synthetic_root(tmp_path)
    service = DeskService(tmp_path, allow_writes=True)

    deployed = service.deploy_mandate("legacy-mandate", DeployRequest(universe=["AAPL"]))
    service.close()

    assert deployed["name"] == "legacy-mandate"
    assert (tmp_path / "paper" / "legacy-mandate" / "fund.yaml").is_file()


@pytest.mark.parametrize(
    ("existing_name", "filename", "requested_name"),
    [
        ("legacy-mandate", "alternate-name.yml", "legacy-mandate"),
        ("legacy-case", "unrelated.yaml", "LEGACY-CASE"),
    ],
)
def test_create_mandate_rejects_duplicate_canonical_name(demo_root, tmp_path, existing_name, filename, requested_name):
    payload = yaml.safe_load((demo_root / "mandates" / "demo-quality.yaml").read_text(encoding="utf-8"))
    payload["name"] = existing_name
    directory = tmp_path / "mandates"
    directory.mkdir()
    existing = directory / filename
    original = yaml.safe_dump(payload, sort_keys=False)
    existing.write_text(original, encoding="utf-8")
    requested = dict(payload)
    requested["name"] = requested_name
    enroll_synthetic_root(tmp_path)
    service = DeskService(tmp_path, allow_writes=True)

    try:
        with pytest.raises(ServiceError) as conflict:
            service.create_mandate(requested)
    finally:
        service.close()

    assert conflict.value.status_code == 409
    assert conflict.value.detail == "A mandate with this name already exists."
    assert existing.read_text(encoding="utf-8") == original
    assert not (directory / f"{requested_name}.yaml").exists()


def test_mandate_detail_rejects_ambiguous_spec_names(demo_root, tmp_path):
    payload = yaml.safe_load((demo_root / "mandates" / "demo-quality.yaml").read_text(encoding="utf-8"))
    directory = tmp_path / "mandates"
    directory.mkdir()
    (directory / "first.yaml").write_text(yaml.safe_dump(payload), encoding="utf-8")
    (directory / "second.yml").write_text(yaml.safe_dump(payload), encoding="utf-8")
    service = DeskService(tmp_path)

    with pytest.raises(ServiceError) as conflict:
        service.get_mandate(payload["name"])
    service.close()

    assert conflict.value.status_code == 409
    assert conflict.value.detail == "Multiple mandates share this name."


def test_mandate_detail_keeps_invalid_exact_file_error(tmp_path):
    directory = tmp_path / "mandates"
    directory.mkdir()
    (directory / "broken.yaml").write_text("schema_version: [", encoding="utf-8")
    service = DeskService(tmp_path)

    with pytest.raises(ServiceError) as invalid:
        service.get_mandate("broken")
    service.close()

    assert invalid.value.status_code == 422
    assert invalid.value.detail == "Mandate is invalid (ValueError)."


def test_corrupt_ledger_is_reported_instead_of_becoming_an_empty_valid_snapshot(demo_root):
    from hedge_fund.runtime.admission import AdmissionCoordinator, RootOwnerLease
    from hedge_fund.runtime.root import RootContext

    ledger = Ledger(demo_root / "paper" / "demo-quality")
    with RootContext.open(demo_root) as context:
        owner = RootOwnerLease.acquire(context, timeout=0)
        admission = AdmissionCoordinator(context, owner_lease=owner)
        try:
            with admission.control_lane("demo-quality", timeout=0):
                ledger.halt("preserve control state")
        finally:
            owner.close()
    path = demo_root / "paper" / "demo-quality" / "ledger" / "2024-06-04.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["cash"] = 1
    path.write_text(json.dumps(payload), encoding="utf-8")

    with TestClient(create_app(root=demo_root, demo=True)) as client:
        detail = client.get("/api/paper/demo-quality", headers={"host": "127.0.0.1"}).json()
        papers = client.get("/api/paper", headers={"host": "127.0.0.1"}).json()

    assert detail["ledger"]["ok"] is False
    assert detail["ledger"]["error"].startswith("Ledger verification failed")
    assert detail["nav"] is None
    assert detail["cash"] is None
    assert detail["sessions"] == []
    assert detail["halted"] == "preserve control state"
    assert papers["errors"][0]["name"] == "demo-quality"


@pytest.mark.parametrize("contents", ["{", "[]", "{}"])
def test_unreadable_control_is_explicit_in_paper_list_and_detail(demo_root, contents):
    control = demo_root / "paper" / "demo-quality" / "control.json"
    control.write_text(contents, encoding="utf-8")

    with TestClient(create_app(root=demo_root, demo=True)) as client:
        detail = client.get("/api/paper/demo-quality", headers={"host": "127.0.0.1"}).json()
        papers = client.get("/api/paper", headers={"host": "127.0.0.1"}).json()

    item = next(item for item in papers["items"] if item["name"] == "demo-quality")
    assert detail["halt_state"] == "unreadable"
    assert detail["halted"] is None
    assert detail["ledger"] == {"ok": False, "error": "Ledger verification failed (LedgerError)."}
    assert item["halt_state"] == "unreadable"
    assert item["halted"] is None
    assert papers["errors"] == [{"name": "demo-quality", "error": "Ledger verification failed (LedgerError)."}]


def test_session_report_verifies_entire_ledger_before_returning_a_later_record(demo_root):
    path = demo_root / "paper" / "demo-quality" / "ledger" / "2024-06-03.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["cash"] = 1
    path.write_text(json.dumps(payload), encoding="utf-8")

    with TestClient(create_app(root=demo_root, demo=True)) as client:
        response = client.get(
            "/api/paper/demo-quality/sessions/2024-06-05",
            headers={"host": "127.0.0.1"},
        )

    assert response.status_code == 409
    assert response.json() == {"detail": "Ledger verification failed (LedgerError)."}
    assert not {"session", "hash", "nav", "executed"} & set(response.json())


def test_session_report_returns_the_record_verified_during_replay(demo_root, monkeypatch):
    original_read = Ledger.read
    target_session = "2024-06-04"
    reads = 0

    def swap_on_reread(ledger, session):
        nonlocal reads
        record = original_read(ledger, session)
        if session == target_session:
            reads += 1
            if reads > 1:
                return record.model_copy(update={"nav": -1})
        return record

    app = create_app(root=demo_root, demo=True)
    monkeypatch.setattr(Ledger, "read", swap_on_reread)
    with TestClient(app) as client:
        response = client.get(
            f"/api/paper/demo-quality/sessions/{target_session}",
            headers={"host": "127.0.0.1"},
        )

    assert response.status_code == 200
    assert reads == 1
    assert response.json()["nav"] == 100_495


def test_paper_snapshot_uses_records_captured_by_the_verified_replay(demo_root, monkeypatch):
    directory = demo_root / "paper" / "demo-quality"
    ledger = Ledger(directory)
    original = ledger.latest()
    assert original is not None
    replacement = original.model_copy(update={"cash": original.cash + 17, "nav": original.nav + 17})
    replacement = replacement.model_copy(update={"hash": replacement.compute_hash()})
    original_read = Ledger.read
    swapped = False

    def swap_after_verified_read(book, session):
        nonlocal swapped
        record = original_read(book, session)
        if book.directory == directory and session == original.session and not swapped:
            book.path(session).write_text(replacement.model_dump_json(indent=2), encoding="utf-8")
            swapped = True
        return record

    service = DeskService(demo_root)
    monkeypatch.setattr(Ledger, "read", swap_after_verified_read)
    try:
        snapshot = service._paper_snapshot(load_deployed(directory), directory)
    finally:
        service.close()

    on_disk = original_read(ledger, original.session)
    assert swapped
    assert on_disk.hash == replacement.hash
    assert snapshot["ledger"]["ok"] is True
    assert snapshot["nav"] == original.nav
    assert snapshot["cash"] == original.cash
    assert snapshot["last_record_hash"] == original.hash
    assert snapshot["sessions"][-1]["nav"] == original.nav
    assert snapshot["pending"]["source_record_hash"] == original.hash


def test_paper_state_returns_latest_record_from_replay_without_rereading(demo_root, monkeypatch):
    def reject_reread(_ledger):
        raise AssertionError("latest record must come from verified replay")

    monkeypatch.setattr(Ledger, "latest", reject_reread)
    service = DeskService(demo_root)
    try:
        _directory, _deployed, _ledger, state, latest = service._paper_state("demo-quality")
    finally:
        service.close()

    assert latest is not None
    assert latest.session == state.last_session
    assert latest.hash == state.prev_hash


def test_default_backtest_factory_blinds_agents_and_uses_root_prompt_cache(tmp_path, monkeypatch):
    import hedge_fund.signals.llm_agent as llm_agent
    import hedge_fund.web.services as web_services
    from hedge_fund.fund import FundSpec
    from hedge_fund.llm.cache import PromptCache

    cache_paths = []
    model_temperatures = []

    def scoped_prompt_cache(path):
        cache_paths.append(path)
        return PromptCache(path)

    def reject_default_prompt_cache(*_args, **_kwargs):
        raise AssertionError("web backtests must not construct the default prompt cache")

    class FakeLLM:
        model = "offline-test-model"

    def fake_make_llm(*, temperature=None):
        model_temperatures.append(temperature)
        return FakeLLM()

    monkeypatch.setattr(web_services, "PromptCache", scoped_prompt_cache, raising=False)
    monkeypatch.setattr(llm_agent, "PromptCache", reject_default_prompt_cache)
    monkeypatch.setattr(llm_agent, "make_llm", fake_make_llm)
    spec = FundSpec.model_validate(
        {
            "schema_version": 2,
            "name": "isolated-research",
            "strategies": [
                {
                    "name": "value",
                    "models": [
                        {
                            "name": "buffett",
                            "params": {"news": True, "samples": 3, "temperature": 0.7},
                        }
                    ],
                    "blend": {"mode": "long_only"},
                }
            ],
            "risk": {"max_position_pct": 1, "max_gross_exposure": 1},
        }
    )
    service = DeskService(tmp_path)
    try:
        fund = service._fund_factory(spec)
    finally:
        service.close()

    agent = fund.strategies[0][1][0]
    assert agent._blind is True
    assert agent._news is True
    assert agent._samples == 3
    assert agent._temperature == 0.7
    assert agent._cache._dir == tmp_path.resolve() / "cache" / "llm"
    assert cache_paths == [tmp_path.resolve() / "cache" / "llm"]
    assert model_temperatures == [0.7]


def test_backtest_preview_uses_local_paper_provider_policy(demo_root):
    from hedge_fund.runtime.configuration import RuntimeSettings
    from hedge_fund.web.schemas import BacktestRequest, OperationPreviewRequest

    service = DeskService(
        demo_root,
        allow_writes=True,
        network_enabled=True,
    )
    original = service.get_mandate("demo-quality")
    settings = RuntimeSettings(
        data_provider="yfinance",
        llm_provider="OpenAI",
        model="gpt-6-sol",
    )
    service._runtime_settings = settings
    request = OperationPreviewRequest(
        action="backtest",
        subject_id="demo-quality",
        expected_head=original["mandate_hash"],
        payload=BacktestRequest(
            fund="demo-quality",
            universe=["AAPL"],
            start="2024-06-03",
            end="2024-06-04",
            provider=settings.data_provider,
            model=settings.model,
            mandate_hash=original["mandate_hash"],
        ),
    )

    try:
        with pytest.raises(ServiceError) as denied:
            service.create_operation_preview(
                request,
                operator_session="synthetic-preview-session",
            )
        operations = service._operation_store.list_operations()
    finally:
        service.close()

    assert denied.value.status_code == 403
    assert denied.value.detail == "Paid provider use requires explicit bounded authorization."
    assert operations == ()


def test_report_path_traversal_and_symlink_are_denied(demo_root, tmp_path):
    service = DeskService(demo_root)
    with pytest.raises(ServiceError) as traversal:
        service.research_report("../outside.json")
    assert traversal.value.status_code == 404

    outside = tmp_path / "outside.json"
    outside.write_text("{}", encoding="utf-8")
    escape = demo_root / "research" / "escape.json"
    try:
        escape.symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation unavailable on this Windows environment")
    with pytest.raises(ServiceError) as symlink:
        service.research_report("escape.json")
    assert symlink.value.status_code == 403
    service.close()


def test_mandate_revision_update_round_trips_advanced_fields_without_changing_deployment(demo_root):
    service = DeskService(demo_root, allow_writes=True)
    original = service.get_mandate("demo-quality")
    deployed_path = demo_root / "paper" / "demo-quality" / "fund.yaml"
    deployed_before = deployed_path.read_bytes()
    candidate = json.loads(json.dumps(original["spec"]))
    model = candidate["strategies"][0]["models"][0]
    model["weight"] = 2.75
    model["params"] = {
        "announcement_only": False,
        "earnings_limit": 12,
        "signal_window_days": 8,
    }
    candidate["strategies"][0]["weight"] = 3.125
    candidate["strategies"][0]["blend"] = {
        "method": "conviction_weighted",
        "gross_target": 0.75,
        "mode": "dollar_neutral",
    }
    candidate["min_order_pct_of_equity"] = 0.0025

    try:
        updated = service.update_mandate(
            "demo-quality",
            candidate,
            expected_hash=original["mandate_hash"],
        )
        current = service.get_mandate("demo-quality")
        with pytest.raises(ServiceError) as stale:
            service.update_mandate(
                "demo-quality",
                candidate,
                expected_hash=original["mandate_hash"],
            )
    finally:
        service.close()

    assert updated["mandate_hash"] == current["mandate_hash"]
    assert current["spec"] == FundSpec.model_validate(candidate).model_dump(mode="json")
    assert current["spec"]["strategies"][0]["models"][0]["weight"] == 2.75
    assert current["spec"]["strategies"][0]["models"][0]["params"] == model["params"]
    assert current["spec"]["strategies"][0]["weight"] == 3.125
    assert current["spec"]["strategies"][0]["blend"]["gross_target"] == 0.75
    assert current["spec"]["strategies"][0]["blend"]["mode"] == "dollar_neutral"
    assert current["spec"]["min_order_pct_of_equity"] == 0.0025
    assert "interval" not in current["spec"]
    assert "window" not in current["spec"]
    assert deployed_path.read_bytes() == deployed_before
    assert stale.value.status_code == 409
    assert stale.value.detail == "Mandate changed; reload before editing."


def test_mandate_clone_is_revision_bound_and_preserves_advanced_configuration(demo_root):
    service = DeskService(demo_root, allow_writes=True)
    original = service.get_mandate("demo-quality")
    candidate = json.loads(json.dumps(original["spec"]))
    candidate["name"] = "demo-quality-clone"
    candidate["strategies"][0]["models"][0]["params"] = {
        "announcement_only": False,
        "earnings_limit": 11,
        "signal_window_days": 7,
    }
    try:
        cloned = service.clone_mandate(
            "demo-quality",
            candidate,
            expected_hash=original["mandate_hash"],
        )
        loaded = service.get_mandate("demo-quality-clone")
        with pytest.raises(ServiceError) as stale:
            service.clone_mandate(
                "demo-quality",
                candidate,
                expected_hash="0" * 64,
            )
    finally:
        service.close()

    assert cloned["name"] == "demo-quality-clone"
    assert loaded["spec"]["strategies"][0]["models"][0]["params"] == candidate["strategies"][0]["models"][0]["params"]
    assert service.root_context.path.joinpath("paper", "demo-quality", "fund.yaml").is_file()
    assert not service.root_context.path.joinpath("paper", "demo-quality-clone").exists()
    assert stale.value.status_code == 409
    assert stale.value.detail == "Mandate changed; reload before cloning."


def test_clone_mandate_maps_storage_admission_failure_to_conflict(demo_root, monkeypatch):
    import hedge_fund.web.services as web_services
    from hedge_fund.fund.storage import StorageAdmissionError

    service = DeskService(demo_root, allow_writes=True)
    original = service.get_mandate("demo-quality")
    candidate = json.loads(json.dumps(original["spec"]))
    candidate["name"] = "demo-quality-clone"

    def deny_save(*_args, **_kwargs):
        raise StorageAdmissionError("private admission detail")

    monkeypatch.setattr(web_services, "save_spec", deny_save)
    try:
        with pytest.raises(ServiceError) as denied:
            service.clone_mandate(
                "demo-quality",
                candidate,
                expected_hash=original["mandate_hash"],
            )
    finally:
        service.close()

    assert denied.value.status_code == 409
    assert denied.value.detail == "Mandate could not be saved safely."
    assert not (demo_root / "mandates" / "demo-quality-clone.yaml").exists()


@pytest.mark.parametrize("renamed", [False, True])
def test_mandate_update_denies_paper_inventory_drift_before_mutation(demo_root, renamed):
    service = DeskService(demo_root, allow_writes=True)
    original = service.get_mandate("demo-quality")
    source_path = demo_root / "mandates" / "demo-quality.yaml"
    source_before = source_path.read_bytes()
    candidate = json.loads(json.dumps(original["spec"]))
    if renamed:
        candidate["name"] = "demo-quality-renamed"
    target_path = demo_root / "mandates" / f"{candidate['name']}.yaml"
    (demo_root / "paper" / "demo-quality" / "fund.yaml").write_text(
        "{",
        encoding="utf-8",
    )

    try:
        with pytest.raises(ServiceError) as drift:
            service.update_mandate(
                "demo-quality",
                candidate,
                expected_hash=original["mandate_hash"],
            )
    finally:
        service.close()

    assert drift.value.status_code == 409
    assert drift.value.detail == "Offline paper ledger inventory changed; writes are denied."
    assert source_path.read_bytes() == source_before
    if renamed:
        assert not target_path.exists()


def test_mandate_rename_write_failure_leaves_retryable_source(demo_root, monkeypatch):
    service = DeskService(demo_root, allow_writes=True)
    original = service.get_mandate("demo-quality")
    source_path = demo_root / "mandates" / "demo-quality.yaml"
    source_before = source_path.read_bytes()
    target_path = demo_root / "mandates" / "demo-quality-renamed.yaml"
    candidate = json.loads(json.dumps(original["spec"]))
    candidate["name"] = "demo-quality-renamed"
    original_write = service.root_context.write_bytes
    failed_once = False

    def fail_target_write_once(relative, payload):
        nonlocal failed_once
        if relative == "mandates/demo-quality-renamed.yaml" and not failed_once:
            failed_once = True
            raise OSError("injected write failure")
        return original_write(relative, payload)

    monkeypatch.setattr(service.root_context, "write_bytes", fail_target_write_once)
    try:
        with pytest.raises(ServiceError) as failed:
            service.update_mandate(
                "demo-quality",
                candidate,
                expected_hash=original["mandate_hash"],
            )
        target_after_failure = target_path.read_bytes()
        source_after_failure = source_path.exists()
        retried = service.update_mandate(
            "demo-quality",
            candidate,
            expected_hash=original["mandate_hash"],
        )
        current = service.get_mandate("demo-quality-renamed")
    finally:
        service.close()

    assert failed_once
    assert failed.value.status_code == 409
    assert failed.value.detail == "Mandate could not be updated safely."
    assert target_after_failure == source_before
    assert not source_after_failure
    assert retried["name"] == current["name"] == "demo-quality-renamed"
    assert current["mandate_hash"] != original["mandate_hash"]


def test_mandate_revision_rename_keeps_deployment_identity_immutable(demo_root):
    service = DeskService(demo_root, allow_writes=True)
    original = service.get_mandate("demo-quality")
    deployed_path = demo_root / "paper" / "demo-quality" / "fund.yaml"
    deployed_before = deployed_path.read_bytes()
    old_mandate_path = demo_root / "mandates" / "demo-quality.yaml"
    renamed_mandate_path = demo_root / "mandates" / "demo-quality-renamed.yaml"
    candidate = json.loads(json.dumps(original["spec"]))
    candidate["name"] = "demo-quality-renamed"

    try:
        renamed = service.update_mandate(
            "demo-quality",
            candidate,
            expected_hash=original["mandate_hash"],
        )
        current = service.get_mandate("demo-quality-renamed")
        with pytest.raises(ServiceError) as missing_old:
            service.get_mandate("demo-quality")
        old_path_removed = not old_mandate_path.exists()
        renamed_path_created = renamed_mandate_path.is_file()
        reused = service.create_mandate(original["spec"])
    finally:
        service.close()

    assert renamed["name"] == "demo-quality-renamed"
    assert current["spec"]["name"] == "demo-quality-renamed"
    assert missing_old.value.status_code == 404
    assert old_path_removed
    assert renamed_path_created
    assert reused["name"] == "demo-quality"
    assert old_mandate_path.is_file()
    assert deployed_path.read_bytes() == deployed_before


def test_mandate_rename_collision_preserves_source(demo_root):
    service = DeskService(demo_root, allow_writes=True)
    original = service.get_mandate("demo-quality")
    other = json.loads(json.dumps(original["spec"]))
    other["name"] = "existing-target"
    service.create_mandate(other)
    candidate = json.loads(json.dumps(original["spec"]))
    candidate["name"] = "existing-target"
    source_path = demo_root / "mandates" / "demo-quality.yaml"
    source_before = source_path.read_bytes()

    try:
        with pytest.raises(ServiceError) as collision:
            service.update_mandate(
                "demo-quality",
                candidate,
                expected_hash=original["mandate_hash"],
            )
        current = service.get_mandate("demo-quality")
    finally:
        service.close()

    assert collision.value.status_code == 409
    assert current["name"] == "demo-quality"
    assert source_path.read_bytes() == source_before
    assert (demo_root / "mandates" / "existing-target.yaml").is_file()


def test_advanced_mandate_parameters_are_constructor_validated(demo_root):
    service = DeskService(demo_root, allow_writes=True)
    current = service.get_mandate("demo-quality")
    candidate = json.loads(json.dumps(current["spec"]))
    candidate["name"] = "invalid-model-parameter"
    candidate["strategies"][0]["models"][0]["params"] = {"unsupported_option": True}

    try:
        with pytest.raises(ServiceError) as invalid:
            service.create_mandate(candidate)
    finally:
        service.close()

    assert invalid.value.status_code == 422
    assert invalid.value.detail == "Mandate validation failed (ValidationError)."
    assert not (demo_root / "mandates" / "invalid-model-parameter.yaml").exists()


def test_mandate_edit_route_requires_revision_and_preserves_full_spec(demo_root):
    app = create_app(root=demo_root, allow_writes=True, demo=True)
    with TestClient(app, client=("127.0.0.1", 50000)) as client:
        headers = {"host": "127.0.0.1"}
        capability = client.get("/api/capabilities", headers=headers).json()
        headers.update(
            {
                "origin": "http://127.0.0.1",
                "x-csrf-token": capability["mutation_token"],
            }
        )
        original = client.get("/api/mandates/demo-quality", headers=headers).json()
        candidate = json.loads(json.dumps(original["spec"]))
        candidate["strategies"][0]["models"][0]["params"] = {
            "announcement_only": False,
            "earnings_limit": 9,
            "signal_window_days": 6,
        }
        response = client.put(
            "/api/mandates/demo-quality",
            headers=headers,
            json={
                "expected_hash": original["mandate_hash"],
                "spec": candidate,
            },
        )
        current = client.get("/api/mandates/demo-quality", headers=headers).json()

    assert response.status_code == 200
    assert current["spec"]["strategies"][0]["models"][0]["params"] == candidate["strategies"][0]["models"][0]["params"]
    assert current["mandate_hash"] != original["mandate_hash"]


def test_resource_name_collision_uses_windows_canonical_key(tmp_path):
    existing = tmp_path / "demo.fund"
    existing.mkdir()
    service = DeskService(tmp_path)

    with pytest.raises(ServiceError) as conflict:
        service._assert_unique(tmp_path, "DEMO.FUND.")

    assert conflict.value.status_code == 409
    service.close()


def test_corrupt_mandates_remain_visible_as_errors(demo_root):
    (demo_root / "mandates" / "broken.yaml").write_text("schema_version: [", encoding="utf-8")

    with TestClient(create_app(root=demo_root, demo=True)) as client:
        result = client.get("/api/mandates", headers={"host": "127.0.0.1"}).json()

    assert [item["name"] for item in result["items"]] == ["demo-quality"]
    assert result["errors"][0]["name"] == "broken"
    assert result["errors"][0]["error"].startswith("Invalid mandate")


def test_research_pages_use_stable_cursor_search_and_bounded_limits(demo_root):
    research_dir = demo_root / "research"
    source = next(research_dir.glob("*.json"))
    payload = source.read_bytes()
    for index in range(105):
        (research_dir / f"history-{index:03d}.json").write_bytes(payload)
    (research_dir / "history-broken.json").write_text("{", encoding="utf-8")

    service = DeskService(demo_root)
    try:
        page1 = service.list_research(limit=40)
        page2 = service.list_research(limit=40, cursor=page1["next_cursor"])
        page3 = service.list_research(limit=40, cursor=page2["next_cursor"])
        matching1 = service.list_research(limit=100, search="DEMO-quality")
        matching2 = service.list_research(
            limit=100,
            cursor=matching1["next_cursor"],
            search="DEMO-quality",
        )
        for invalid in (
            {"limit": 0},
            {"limit": 101},
            {"limit": True},
            {"cursor": "../outside.json"},
            {"search": "x" * 129},
        ):
            with pytest.raises(ServiceError) as rejected:
                service.list_research(**invalid)
            assert rejected.value.status_code == 422
    finally:
        service.close()

    paths = sorted(
        research_dir.glob("*.json"),
        key=lambda entry: (entry.name.casefold(), entry.name),
        reverse=True,
    )
    expected_ids = [path.name for path in paths]
    pages = [page1, page2, page3]
    observed_ids = [identifier for page in pages for identifier in ([item["id"] for item in page["items"]] + [item["id"] for item in page["errors"]])]

    assert [page["total"] for page in pages] == [107, 107, 107]
    assert [page["next_cursor"] for page in pages] == [
        expected_ids[39],
        expected_ids[79],
        None,
    ]
    assert len(observed_ids) == len(set(observed_ids)) == 107
    assert set(observed_ids) == set(expected_ids)
    assert page1["errors"] == [
        {
            "id": "history-broken.json",
            "error": "Invalid research report (ValidationError).",
        }
    ]
    assert matching1["total"] == 106
    assert len(matching1["items"]) == 100
    assert matching1["errors"] == []
    assert len(matching2["items"]) == 6
    assert matching2["next_cursor"] is None

    with TestClient(create_app(root=demo_root, demo=True)) as client:
        response = client.get(
            "/api/research?limit=2&search=DEMO-quality",
            headers={"host": "127.0.0.1"},
        )
        full_page = client.get(
            "/api/research?limit=20",
            headers={"host": "127.0.0.1"},
        )
        home = client.get("/api/home", headers={"host": "127.0.0.1"})
        longest_cursor = f"a{'b' * 180}.json"
        long_cursor_response = client.get(
            f"/api/research?limit=1&cursor={longest_cursor}",
            headers={"host": "127.0.0.1"},
        )
        rejected = client.get(
            "/api/research?limit=101",
            headers={"host": "127.0.0.1"},
        )

    assert response.status_code == 200
    assert response.json()["total"] == 106
    assert len(response.json()["items"]) == 2
    assert full_page.status_code == 200
    assert full_page.json()["total"] == 107
    assert len(full_page.json()["items"]) + len(full_page.json()["errors"]) == 20
    assert full_page.json()["next_cursor"] is not None
    assert home.status_code == 200
    assert home.json()["research_count"] == 107
    assert long_cursor_response.status_code == 200
    assert rejected.status_code == 422


def test_paper_session_pages_cover_verified_history_and_search(demo_root):
    ledger = Ledger(demo_root / "paper" / "demo-quality")
    previous = ledger.latest()
    assert previous is not None
    first_date = date.fromisoformat(previous.session) + timedelta(days=1)
    for index in range(105):
        record = SessionRecord(
            fund=previous.fund,
            session=(first_date + timedelta(days=index)).isoformat(),
            universe=previous.universe,
            nav=previous.nav,
            cash=previous.cash,
            positions=previous.positions,
            marks=previous.marks,
            benchmark=previous.benchmark,
            benchmark_close=previous.benchmark_close,
            rebalance=index % 5 == 0,
            prev_hash=previous.hash,
            code_version=previous.code_version,
            mandate_hash=previous.mandate_hash,
        )
        record.hash = record.compute_hash()
        path = ledger.path(record.session)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(record.model_dump_json(indent=2), encoding="utf-8")
        previous = record
    sessions = ledger.records()

    service = DeskService(demo_root)
    try:
        page1 = service.paper_sessions("demo-quality", limit=40)
        page2 = service.paper_sessions(
            "demo-quality",
            limit=40,
            cursor=page1["next_cursor"],
        )
        page3 = service.paper_sessions(
            "demo-quality",
            limit=40,
            cursor=page2["next_cursor"],
        )
        matching = service.paper_sessions("demo-quality", limit=10, search=sessions[0].session)
        hash_match = service.paper_sessions("demo-quality", limit=10, search=sessions[-1].hash[-12:])
        for invalid in (
            {"limit": 0},
            {"limit": 101},
            {"limit": True},
            {"cursor": "not-a-session"},
            {"cursor": "2025-02-31"},
            {"cursor": "2025-01-01T99:99:99"},
            {"search": "x" * 129},
        ):
            with pytest.raises(ServiceError) as rejected_request:
                service.paper_sessions("demo-quality", **invalid)
            assert rejected_request.value.status_code == 422
    finally:
        service.close()

    pages = [page1, page2, page3]
    expected_sessions = sorted(
        (record.session for record in sessions),
        reverse=True,
    )
    observed_sessions = [item["session"] for page in pages for item in page["items"]]
    assert [page["total"] for page in pages] == [108, 108, 108]
    assert [len(page["items"]) for page in pages] == [40, 40, 28]
    assert [page["next_cursor"] for page in pages] == [
        expected_sessions[39],
        expected_sessions[79],
        None,
    ]
    assert len(observed_sessions) == len(set(observed_sessions)) == 108
    assert set(observed_sessions) == set(expected_sessions)
    assert matching["total"] == 1
    assert matching["items"][0]["session"] == sessions[0].session
    assert hash_match["total"] == 1
    assert hash_match["items"][0]["session"] == sessions[-1].session
    assert all(page["ledger"] == {"ok": True, "error": None} for page in pages)

    with TestClient(create_app(root=demo_root, demo=True)) as client:
        response = client.get(
            f"/api/paper/demo-quality/sessions?limit=2&search={sessions[0].session}",
            headers={"host": "127.0.0.1"},
        )
        rejected = client.get(
            "/api/paper/demo-quality/sessions?limit=101",
            headers={"host": "127.0.0.1"},
        )

    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert len(response.json()["items"]) == 1
    assert rejected.status_code == 422
