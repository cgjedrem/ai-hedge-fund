import json

import pytest
import yaml
from fastapi.testclient import TestClient

from hedge_fund.paper.ledger import Ledger
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
    ledger = Ledger(demo_root / "paper" / "demo-quality")
    ledger.halt("preserve control state")
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

    monkeypatch.setattr(Ledger, "read", swap_on_reread)
    with TestClient(create_app(root=demo_root, demo=True)) as client:
        response = client.get(
            f"/api/paper/demo-quality/sessions/{target_session}",
            headers={"host": "127.0.0.1"},
        )

    assert response.status_code == 200
    assert reads == 1
    assert response.json()["nav"] == 100_495


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
