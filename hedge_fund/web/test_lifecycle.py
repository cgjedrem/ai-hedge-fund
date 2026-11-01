"""Lifecycle adapter contracts, exercised only against synthetic enrolled roots."""

import json
import os
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from hedge_fund import run
from hedge_fund.web.app import create_app
from hedge_fund.web.demo import seed_demo
from hedge_fund.web.schemas import LifecycleAcceptRequest, LifecyclePreviewRequest
from hedge_fund.web.services import DeskService, ServiceError


@pytest.fixture
def demo_root():
    return seed_demo(Path(os.environ["HEDGE_FUND_TEST_ROOT"]) / f"lifecycle-{uuid4().hex}")


def _accept(service, preview, request_id, *, session="operator-test"):
    payload = preview["payload"]
    request = LifecycleAcceptRequest(
        request_id=request_id,
        action=payload["action"],
        kind=payload["kind"] if payload["action"] == "archive" else None,
        identity=payload["identity"] if payload["action"] == "archive" else None,
        archive_id=payload["archive_id"] if payload["action"] != "archive" else None,
        preview_id=preview["preview_id"],
        preview_digest=preview["preview_digest"],
        confirmation_token=preview["confirmation_token"],
        expected_head=preview["expected_head"],
    )
    return service.accept_lifecycle(request, operator_session=session), request


def test_reviewed_template_archive_retains_deployment_and_restores_stopped(demo_root):
    service = DeskService(demo_root, allow_writes=True, demo=True)
    try:
        preview = service.create_lifecycle_preview(
            LifecyclePreviewRequest(action="archive", kind="template", identity="demo-quality"),
            operator_session="operator-test",
        )
        assert preview["references"]["deployments"][0]["identity"] == "demo-quality"
        archived, request = _accept(service, preview, "archive-template")
        assert archived["status"] == "completed"
        archive_id = archived["result"]["archive_id"]
        assert not (demo_root / "mandates" / "demo-quality.yaml").exists()
        assert (demo_root / "paper" / "demo-quality" / "fund.yaml").is_file()
        assert service.accept_lifecycle(request, operator_session="operator-test")["id"] == archived["id"]
        assert service.list_lifecycle_archives()["items"][0]["archive_id"] == archive_id
        restore = service.create_lifecycle_preview(
            LifecyclePreviewRequest(action="restore", archive_id=archive_id),
            operator_session="operator-test",
        )
        restored, _request = _accept(service, restore, "restore-template")
        assert restored["status"] == "completed"
        assert (demo_root / "mandates" / "demo-quality.yaml").is_file()
        assert service.runner_status("demo-quality")["status"] == "stopped"
    finally:
        service.close()


def test_lifecycle_routes_require_session_origin_and_confirmation(demo_root):
    app = create_app(root=demo_root, allow_writes=True, demo=True)
    with TestClient(app, client=("127.0.0.1", 50000)) as client:
        capabilities = client.get("/api/capabilities", headers={"host": "127.0.0.1"}).json()
        assert "delete" not in capabilities["deferred_actions"]
        headers = {
            "host": "127.0.0.1",
            "origin": "http://127.0.0.1",
            "x-csrf-token": capabilities["mutation_token"],
        }
        body = {"action": "archive", "kind": "template", "identity": "demo-quality"}
        denied = client.post("/api/lifecycle/preview", json=body, headers={"host": "127.0.0.1"})
        assert denied.status_code == 403
        response = client.post("/api/lifecycle/preview", json=body, headers=headers)
        assert response.status_code == 200
        preview = response.json()
        accepted = client.post(
            "/api/lifecycle/accept",
            headers=headers,
            json={
                **body,
                "request_id": "browser-archive",
                "preview_id": preview["preview_id"],
                "preview_digest": preview["preview_digest"],
                "confirmation_token": preview["confirmation_token"],
                "expected_head": preview["expected_head"],
            },
        )
        assert accepted.status_code == 202
        assert accepted.json()["status"] == "completed"
        archive_id = accepted.json()["result"]["archive_id"]
        assert client.get("/api/lifecycle/archives", headers=headers).json()["items"][0]["archive_id"] == archive_id
        assert client.get(f"/api/lifecycle/archives/{archive_id}", headers=headers).json()["state"] == "archived"


def test_cli_archive_uses_reviewed_head_without_network_or_tui(demo_root, capsys, monkeypatch):
    def forbidden():
        raise AssertionError("lifecycle commands must bypass TUI/runtime dispatch loading")

    monkeypatch.setattr(run, "_load_runtime", forbidden)
    prefix = ["--root", str(demo_root), "lifecycle"]
    run.main([*prefix, "preview", "--action", "archive", "--kind", "template", "--identity", "demo-quality"])
    preview = json.loads(capsys.readouterr().out)
    command = [
        *prefix,
        "archive",
        "template",
        "demo-quality",
        "--expected-head",
        preview["expected_head"],
        "--request-id",
        "cli-template",
    ]
    run.main(command)
    archived = json.loads(capsys.readouterr().out)
    assert archived["status"] == "completed"
    run.main(command)
    assert json.loads(capsys.readouterr().out)["id"] == archived["id"]
    assert not (demo_root / "mandates" / "demo-quality.yaml").exists()


@pytest.mark.parametrize("kind", ["deployment", "research"])
def test_lifecycle_archives_only_selected_scope_and_restores(kind, demo_root):
    reports = sorted((demo_root / "research").glob("*.json"))
    identity = "demo-quality" if kind == "deployment" else reports[0].name
    source = demo_root / ("paper" if kind == "deployment" else "research") / identity
    service = DeskService(demo_root, allow_writes=True, demo=True)
    try:
        preview = service.create_lifecycle_preview(
            LifecyclePreviewRequest(action="archive", kind=kind, identity=identity),
            operator_session="operator-test",
        )
        result, request = _accept(service, preview, f"archive-{kind}")
        assert result["status"] == "completed"
        assert not source.exists()
        assert (demo_root / "mandates" / "demo-quality.yaml").is_file()
        if kind == "research":
            assert (demo_root / "paper" / "demo-quality" / "fund.yaml").is_file()
        else:
            assert reports[0].is_file()
        archive_id = result["result"]["archive_id"]
    finally:
        service.close()
    restarted = DeskService(demo_root, allow_writes=True, demo=True)
    try:
        assert restarted.accept_lifecycle(request, operator_session="operator-test")["id"] == result["id"]
        preview = restarted.create_lifecycle_preview(
            LifecyclePreviewRequest(action="restore", archive_id=archive_id),
            operator_session="operator-test",
        )
        restored, _ = _accept(restarted, preview, f"restore-{kind}")
        assert restored["status"] == "completed"
        assert source.exists()
        assert restarted.runner_status("demo-quality")["status"] == "stopped"
    finally:
        restarted.close()


@pytest.mark.parametrize("change", ["content", "references", "session", "confirmation", "identity", "runner"])
def test_archive_rejects_changed_review_without_moving_source(change, demo_root):
    service = DeskService(demo_root, allow_writes=True, demo=True)
    source = demo_root / "mandates" / "demo-quality.yaml"
    try:
        preview = service.create_lifecycle_preview(
            LifecyclePreviewRequest(action="archive", kind="template", identity="demo-quality"),
            operator_session="operator-test",
        )
        session = "operator-test"
        if change == "content":
            source.write_bytes(source.read_bytes() + b"\n# externally changed\n")
        elif change == "references":
            report = sorted((demo_root / "research").glob("*.json"))[0]
            (report.parent / "demo-quality-added.json").write_bytes(report.read_bytes())
        elif change == "session":
            session = "different-operator"
        elif change == "confirmation":
            preview["confirmation_token"] = "x" * 40
        elif change == "identity":
            preview["payload"]["identity"] = "other-template"
        else:
            from hedge_fund.runtime.owned_runner import runner_key, RUNNER_ROOT

            directory = service.root_context.resolve(f"{RUNNER_ROOT}/{runner_key('demo-quality')}")
            directory.mkdir(parents=True)
            (directory / "state.json").write_text("{}", encoding="utf-8")
        with pytest.raises(ServiceError) as denied:
            _accept(service, preview, f"denied-{change}", session=session)
        assert denied.value.status_code == 409
        assert source.is_file()
        assert service.list_operations()["items"] == []
    finally:
        service.close()


def test_interrupted_archive_requires_explicit_reviewed_recovery(demo_root, monkeypatch):
    from hedge_fund.runtime.root import RootContext

    service = DeskService(demo_root, allow_writes=True, demo=True)
    original = RootContext.rename_file

    def interrupted_move(context, source, destination):
        original(context, source, destination)
        if source == "mandates/demo-quality.yaml":
            raise OSError("synthetic interruption after move")

    try:
        preview = service.create_lifecycle_preview(
            LifecyclePreviewRequest(action="archive", kind="template", identity="demo-quality"),
            operator_session="operator-test",
        )
        monkeypatch.setattr(RootContext, "rename_file", interrupted_move)
        with pytest.raises(ServiceError) as interrupted:
            _accept(service, preview, "interrupted-archive")
        assert interrupted.value.code == "ownership-unknown"
        monkeypatch.setattr(RootContext, "rename_file", original)
        operation = service.list_operations()["items"][0]
        assert operation["status"] == "interrupted"
        archive_id = preview["payload"]["archive_id"]
        assert service.get_lifecycle_archive(archive_id)["state"] == "archive-prepared"
        recovery = service.create_lifecycle_preview(
            LifecyclePreviewRequest(action="recover", archive_id=archive_id),
            operator_session="operator-test",
        )
        result, _ = _accept(service, recovery, "explicit-journal-recovery")
        assert result["status"] == "completed"
        assert service.get_lifecycle_archive(archive_id)["state"] == "archived"
        assert not (demo_root / "mandates" / "demo-quality.yaml").exists()
    finally:
        service.close()


def test_cli_recovers_deployment_inventory_drift_but_web_stays_read_only(demo_root, monkeypatch, capsys):
    from hedge_fund.runtime.root import RootContext

    original = RootContext.rename_directory

    def interrupted_move(context, source, destination):
        original(context, source, destination)
        if source == "paper/demo-quality":
            raise OSError("synthetic interruption before inventory transition")

    service = DeskService(demo_root, allow_writes=True, demo=True)
    try:
        preview = service.create_lifecycle_preview(
            LifecyclePreviewRequest(action="archive", kind="deployment", identity="demo-quality"),
            operator_session="operator-test",
        )
        monkeypatch.setattr(RootContext, "rename_directory", interrupted_move)
        with pytest.raises(ServiceError):
            _accept(service, preview, "drift-archive")
        monkeypatch.setattr(RootContext, "rename_directory", original)
        archive_id = preview["payload"]["archive_id"]
    finally:
        service.close()
    observer = DeskService(demo_root, allow_writes=True, demo=True)
    try:
        assert observer.allow_writes is False
        with pytest.raises(ServiceError) as denied:
            observer.create_lifecycle_preview(
                LifecyclePreviewRequest(action="recover", archive_id=archive_id),
                operator_session="operator-test",
            )
        assert denied.value.status_code == 403
    finally:
        observer.close()
    prefix = ["--root", str(demo_root), "lifecycle"]
    run.main([*prefix, "preview", "--action", "recover", "--archive-id", archive_id])
    recovery = json.loads(capsys.readouterr().out)
    run.main(
        [
            *prefix,
            "recover",
            archive_id,
            "--request-id",
            "cli-drift-recovery",
            "--expected-head",
            recovery["expected_head"],
        ]
    )
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "completed"
    assert result["result"]["state"] == "archived"
    restored_service = DeskService(demo_root, allow_writes=True, demo=True)
    try:
        assert restored_service.allow_writes is True
        restore = restored_service.create_lifecycle_preview(
            LifecyclePreviewRequest(action="restore", archive_id=archive_id),
            operator_session="operator-test",
        )
        result, _ = _accept(restored_service, restore, "restore-after-cli-recovery")
        assert result["status"] == "completed"
        assert restored_service.runner_status("demo-quality")["status"] == "stopped"
    finally:
        restored_service.close()


def test_pre_move_interruption_retains_abandoned_journal_and_allows_new_review(demo_root, monkeypatch):
    from hedge_fund.runtime.root import RootContext

    original = RootContext.rename_file

    def before_move(context, source, destination):
        if source == "mandates/demo-quality.yaml":
            raise OSError("synthetic interruption before move")
        return original(context, source, destination)

    service = DeskService(demo_root, allow_writes=True, demo=True)
    try:
        preview = service.create_lifecycle_preview(
            LifecyclePreviewRequest(action="archive", kind="template", identity="demo-quality"),
            operator_session="operator-test",
        )
        monkeypatch.setattr(RootContext, "rename_file", before_move)
        with pytest.raises(ServiceError):
            _accept(service, preview, "before-move")
        monkeypatch.setattr(RootContext, "rename_file", original)
        archive_id = preview["payload"]["archive_id"]
        recovery = service.create_lifecycle_preview(
            LifecyclePreviewRequest(action="recover", archive_id=archive_id),
            operator_session="operator-test",
        )
        result, _ = _accept(service, recovery, "abandon-before-move")
        assert result["status"] == "completed"
        assert service.get_lifecycle_archive(archive_id)["state"] == "abandoned"
        retry = service.create_lifecycle_preview(
            LifecyclePreviewRequest(action="archive", kind="template", identity="demo-quality"),
            operator_session="operator-test",
        )
        archived = _accept(service, retry, "new-reviewed-archive")[0]
        assert archived["status"] == "completed"
        restore = service.create_lifecycle_preview(
            LifecyclePreviewRequest(action="restore", archive_id=archived["result"]["archive_id"]),
            operator_session="operator-test",
        )
        assert _accept(service, restore, "restore-after-new-archive")[0]["status"] == "completed"
    finally:
        service.close()


@pytest.mark.parametrize("point", ["before-worker", "before-journal", "after-final-journal"])
def test_lifecycle_interruption_before_or_after_journal_remains_recoverable(point, demo_root, monkeypatch):
    from hedge_fund.runtime.lifecycle import LifecycleArchiveStore

    service = DeskService(demo_root, allow_writes=True, demo=True)
    try:
        preview = service.create_lifecycle_preview(
            LifecyclePreviewRequest(action="archive", kind="template", identity="demo-quality"),
            operator_session="operator-test",
        )

        def crash(*args, **kwargs):
            raise OSError("synthetic lifecycle crash")

        with monkeypatch.context() as patch:
            if point == "before-worker":
                patch.setattr(service._operation_store, "claim_worker", crash)
            elif point == "before-journal":
                patch.setattr(LifecycleArchiveStore, "archive", crash)
            else:
                patch.setattr(service._operation_store, "complete", crash)
            with pytest.raises(ServiceError):
                _accept(service, preview, f"crash-{point}")
        archive_id = preview["payload"]["archive_id"]
        if point in {"before-worker", "before-journal"}:
            assert service.list_lifecycle_archives()["items"][0]["archive_id"] == archive_id
            assert service.get_lifecycle_archive(archive_id)["recovery_required"]
            recovery = service.create_lifecycle_preview(
                LifecyclePreviewRequest(action="recover", archive_id=archive_id),
                operator_session="operator-test",
            )
            result, _ = _accept(service, recovery, "explicit-absent-journal-recovery")
            assert result["result"]["state"] == "abandoned"
            retry = service.create_lifecycle_preview(
                LifecyclePreviewRequest(action="archive", kind="template", identity="demo-quality"),
                operator_session="operator-test",
            )
            assert _accept(service, retry, "archive-after-explicit-recovery")[0]["status"] == "completed"
        else:
            journal = LifecycleArchiveStore(service.root_context, service._admission).inspect(archive_id)
            operation = service._operation_store.active_for_subject("demo-quality")[0]
            assert operation.status.value == "interrupted", operation
            assert operation.operation_id in journal["reconciled_operations"], journal
            restore = service.create_lifecycle_preview(
                LifecyclePreviewRequest(action="restore", archive_id=archive_id),
                operator_session="operator-test",
            )
            with monkeypatch.context() as patch:
                patch.setattr(service._operation_store, "complete", crash)
                with pytest.raises(ServiceError):
                    _accept(service, restore, "restore-after-commit-gap")
            retry = service.create_lifecycle_preview(
                LifecyclePreviewRequest(action="archive", kind="template", identity="demo-quality"),
                operator_session="operator-test",
            )
            assert _accept(service, retry, "archive-after-restore-commit-gap")[0]["status"] == "completed"
    finally:
        service.close()


def test_restore_collision_is_rejected_during_review_without_accepting_operation(demo_root):
    service = DeskService(demo_root, allow_writes=True, demo=True)
    try:
        preview = service.create_lifecycle_preview(
            LifecyclePreviewRequest(action="archive", kind="template", identity="demo-quality"),
            operator_session="operator-test",
        )
        original = (demo_root / "mandates" / "demo-quality.yaml").read_bytes()
        archived, _ = _accept(service, preview, "archive-collision-test")
        (demo_root / "mandates" / "demo-quality.yml").write_bytes(original)
        with pytest.raises(ServiceError):
            service.create_lifecycle_preview(
                LifecyclePreviewRequest(action="restore", archive_id=archived["result"]["archive_id"]),
                operator_session="operator-test",
            )
        assert len(service.list_operations()["items"]) == 1
        fresh = service.create_lifecycle_preview(
            LifecyclePreviewRequest(action="archive", kind="template", identity="demo-quality"),
            operator_session="operator-test",
        )
        assert fresh["payload"]["source_path"].endswith(".yml")
    finally:
        service.close()


@pytest.mark.parametrize("unsupported", ["changed-source", "archive-destination"])
def test_missing_journal_alone_never_authorizes_recovery(demo_root, monkeypatch, unsupported):
    from hedge_fund.runtime.lifecycle import ARCHIVE_ROOT, LifecycleArchiveStore

    service = DeskService(demo_root, allow_writes=True, demo=True)
    try:
        independent = json.loads(next((demo_root / "research").glob("*.json")).read_text())
        independent["fund"] = "independent"
        (demo_root / "research" / "independent-archive.json").write_text(json.dumps(independent))
        healthy = service.create_lifecycle_preview(
            LifecyclePreviewRequest(action="archive", kind="research", identity="independent-archive.json"),
            operator_session="operator-test",
        )
        healthy_id = _accept(service, healthy, "healthy-independent-archive")[0]["result"]["archive_id"]
        preview = service.create_lifecycle_preview(
            LifecyclePreviewRequest(action="archive", kind="template", identity="demo-quality"),
            operator_session="operator-test",
        )

        def crash(*args, **kwargs):
            raise RuntimeError("before archive journal")

        with monkeypatch.context() as patch:
            patch.setattr(LifecycleArchiveStore, "_write_index", crash)
            with pytest.raises(ServiceError):
                _accept(service, preview, f"unsupported-{unsupported}")
        archive_id = preview["payload"]["archive_id"]
        if unsupported == "changed-source":
            source = demo_root / "mandates" / "demo-quality.yaml"
            source.write_bytes(source.read_bytes() + b"\n# changed after interruption\n")
        else:
            destination = demo_root / ARCHIVE_ROOT / "objects" / archive_id
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(b"unknown destination")
        with pytest.raises(ServiceError) as denied:
            service.create_lifecycle_preview(
                LifecyclePreviewRequest(action="recover", archive_id=archive_id),
                operator_session="operator-test",
            )
        assert denied.value.status_code == 409
        records = {record["archive_id"]: record for record in service.list_lifecycle_archives()["items"]}
        assert records[healthy_id]["state"] == "archived"
        assert records[archive_id]["recovery_action"] == "manual-review"
        assert service.get_lifecycle_archive(archive_id)["recovery_error"]
        restore = service.create_lifecycle_preview(
            LifecyclePreviewRequest(action="restore", archive_id=healthy_id),
            operator_session="operator-test",
        )
        assert restore["payload"]["identity"] == healthy["payload"]["identity"]
        assert (demo_root / "mandates" / "demo-quality.yaml").is_file()
    finally:
        service.close()


@pytest.mark.parametrize("point", ["before-worker", "before-restore-journal", "collision"])
def test_restore_without_prepared_move_requires_explicit_no_effect_recovery(demo_root, monkeypatch, point):
    from hedge_fund.runtime.lifecycle import LifecycleArchiveStore

    service = DeskService(demo_root, allow_writes=True, demo=True)
    try:
        original = (demo_root / "mandates" / "demo-quality.yaml").read_bytes()
        archive = service.create_lifecycle_preview(
            LifecyclePreviewRequest(action="archive", kind="template", identity="demo-quality"),
            operator_session="operator-test",
        )
        archive_id = _accept(service, archive, "archive-for-early-restore")[0]["result"]["archive_id"]
        restore = service.create_lifecycle_preview(
            LifecyclePreviewRequest(action="restore", archive_id=archive_id),
            operator_session="operator-test",
        )

        def crash(*args, **kwargs):
            raise OSError("before restore prepared journal")

        with monkeypatch.context() as patch:
            if point == "before-worker":
                patch.setattr(service._operation_store, "claim_worker", crash)
            else:
                patch.setattr(LifecycleArchiveStore, "_write_index", crash)
            with pytest.raises(ServiceError):
                _accept(service, restore, f"early-restore-{point}")
        if point == "collision":
            (demo_root / "mandates" / "demo-quality.yaml").write_bytes(original)
        assert service.get_lifecycle_archive(archive_id)["recovery_action"] == "abandon-unprepared-restore"
        assert service.list_lifecycle_archives()["items"][0]["recovery_required"]
        recovery = service.create_lifecycle_preview(
            LifecyclePreviewRequest(action="recover", archive_id=archive_id),
            operator_session="operator-test",
        )
        assert _accept(service, recovery, "explicit-restore-no-effect")[0]["status"] == "completed"
        if point == "collision":
            with pytest.raises(ServiceError):
                service.create_lifecycle_preview(
                    LifecyclePreviewRequest(action="restore", archive_id=archive_id),
                    operator_session="operator-test",
                )
            assert (demo_root / "mandates" / "demo-quality.yaml").read_bytes() == original
            return
        restore = service.create_lifecycle_preview(
            LifecyclePreviewRequest(action="restore", archive_id=archive_id),
            operator_session="operator-test",
        )
        assert _accept(service, restore, "new-reviewed-restore")[0]["status"] == "completed"
    finally:
        service.close()


def test_unprepared_deployment_archive_recovery_preserves_legitimate_new_sessions(demo_root, monkeypatch):
    from hedge_fund.paper.ledger import Ledger
    from hedge_fund.runtime.handover import record_ledger_head
    from hedge_fund.runtime.lifecycle import LifecycleArchiveStore

    service = DeskService(demo_root, allow_writes=True, demo=True)
    try:
        preview = service.create_lifecycle_preview(
            LifecyclePreviewRequest(action="archive", kind="deployment", identity="demo-quality"),
            operator_session="operator-test",
        )

        def crash(*args, **kwargs):
            raise OSError("before archive prepared journal")

        with monkeypatch.context() as patch:
            patch.setattr(LifecycleArchiveStore, "_write_index", crash)
            with pytest.raises(ServiceError):
                _accept(service, preview, "unprepared-deployment-archive")
        ledger = Ledger(demo_root / "paper" / "demo-quality")
        previous = ledger.latest()
        record = previous.model_copy(update={"session": "2030-01-02", "prev_hash": previous.hash, "decision": None, "executed": None, "rebalance": False})
        record.hash = record.compute_hash()
        with service._admission.manual_session("demo-quality"):
            ledger.append(record)
        record_ledger_head(service.root_context, "demo-quality", admission=service._admission)
        archive_id = preview["payload"]["archive_id"]
        LifecycleArchiveStore(service.root_context, service._admission).review_unprepared(
            "deployment",
            "demo-quality",
            archive_id=archive_id,
            expected_digest=preview["payload"]["object_digest"],
            deployment_before=preview["payload"]["deployment_before"],
        )
        recovery = service.create_lifecycle_preview(
            LifecyclePreviewRequest(action="recover", archive_id=archive_id),
            operator_session="operator-test",
        )
        assert recovery["payload"]["review_digest"] != recovery["payload"]["object_digest"]
        assert _accept(service, recovery, "reviewed-current-head-recovery")[0]["status"] == "completed"
        assert ledger.latest().hash == record.hash
        fresh = service.create_lifecycle_preview(
            LifecyclePreviewRequest(action="archive", kind="deployment", identity="demo-quality"),
            operator_session="operator-test",
        )
        assert _accept(service, fresh, "archive-current-head")[0]["status"] == "completed"
    finally:
        service.close()
