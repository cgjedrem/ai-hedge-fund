import json

import pytest
from fastapi.testclient import TestClient

from hedge_fund.web.app import create_app
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
    assert paper_list["items"][0]["nav"] == 101_000
    assert detail["ledger"] == {"ok": True, "error": None}
    assert detail["nav"] == 101_000
    assert detail["cash"] == 90_000
    assert detail["positions"] == [{"ticker": "AAPL", "shares": 100, "mark": 110, "market_value": 11_000}]
    assert [point["nav"] for point in detail["curve"]] == [100_000, 100_500, 101_000]
    assert detail["live_value"]["status"] == "unavailable"
    assert detail["live_value"]["value"] is None
    assert detail["runner"]["available"] is False
    assert detail["pending"]["source_record_hash"] == detail["last_record_hash"]
    assert detail["pending"]["decision_as_of"] == "2024-06-05"
    assert scorecard["fund"] == "demo-quality"
    assert report["executed"]["orders"][0]["ticker"] == "AAPL"
    assert report["executed"]["fills"][0]["quantity"] == 100
    assert report["proposed"]["as_of"] == "2024-06-04"
    assert report["proposed"]["target_weights"] == {"AAPL": 0.1}
    assert len(research["items"]) == 1
    assert research["items"][0]["fund"] == "demo-quality"


def test_corrupt_ledger_is_reported_instead_of_becoming_an_empty_valid_snapshot(demo_root):
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
    assert papers["errors"][0]["name"] == "demo-quality"


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


def test_corrupt_mandates_remain_visible_as_errors(demo_root):
    (demo_root / "mandates" / "broken.yaml").write_text("schema_version: [", encoding="utf-8")

    with TestClient(create_app(root=demo_root, demo=True)) as client:
        result = client.get("/api/mandates", headers={"host": "127.0.0.1"}).json()

    assert [item["name"] for item in result["items"]] == ["demo-quality"]
    assert result["errors"][0]["name"] == "broken"
    assert result["errors"][0]["error"].startswith("Invalid mandate")
