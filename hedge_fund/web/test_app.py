import pytest
from fastapi.testclient import TestClient

from hedge_fund.runtime.admission import WriterConflict
from hedge_fund.test_support.handover import enroll_synthetic_root
from hedge_fund.web.app import create_app

LOOPBACK = {"host": "127.0.0.1"}


def test_default_capabilities_are_immutable_read_only_and_disk_quiet(tmp_path):
    app = create_app(root=tmp_path)
    with TestClient(app) as client:
        response = client.get("/api/capabilities", headers=LOOPBACK)

    assert response.status_code == 200
    assert response.json()["read_only"] is True
    assert response.json()["writes"] is False
    assert response.json()["network"] is False
    assert response.json()["local_operator_only"] is True
    assert response.json()["csrf_authenticates_users"] is False
    assert response.json()["mutation_token"] is None
    assert not (tmp_path / "paper").exists()
    assert not (tmp_path / "mandates").exists()


def test_host_and_origin_must_stay_loopback_same_origin(tmp_path):
    with TestClient(create_app(root=tmp_path)) as client:
        remote_host = client.get("/api/capabilities", headers={"host": "desk.attacker.example"})
        foreign_origin = client.get(
            "/api/capabilities",
            headers={"host": "127.0.0.1", "origin": "https://desk.attacker.example"},
        )
        same_origin = client.get(
            "/api/capabilities",
            headers={"host": "127.0.0.1", "origin": "http://127.0.0.1"},
        )

    assert remote_host.status_code == 403
    assert foreign_origin.status_code == 403
    assert same_origin.status_code == 200


def test_read_only_mutation_is_denied_before_storage_or_domain_access(tmp_path, monkeypatch):
    app = create_app(root=tmp_path)
    service = app.state.service
    called = False

    def forbidden(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("write adapter must not run")

    monkeypatch.setattr(service, "halt_fund", forbidden)
    with TestClient(app) as client:
        response = client.post(
            "/api/paper/demo/halt",
            headers=LOOPBACK,
            json={"reason": "test"},
        )

    assert response.status_code == 403
    assert not called
    assert not (tmp_path / "paper").exists()


def test_writes_require_same_origin_token_and_loopback_peer(tmp_path):
    enroll_synthetic_root(tmp_path)
    app = create_app(root=tmp_path, allow_writes=True)
    with TestClient(app, client=("127.0.0.1", 50000)) as client:
        capabilities = client.get("/api/capabilities", headers=LOOPBACK).json()
        token = capabilities["mutation_token"]
        missing_origin = client.post(
            "/api/paper/demo/halt",
            headers={"host": "127.0.0.1", "x-csrf-token": token},
            json={"reason": "test"},
        )
        missing_token = client.post(
            "/api/paper/demo/halt",
            headers={"host": "127.0.0.1", "origin": "http://127.0.0.1"},
            json={"reason": "test"},
        )
        wrong_token = client.post(
            "/api/paper/demo/halt",
            headers={
                "host": "127.0.0.1",
                "origin": "http://127.0.0.1",
                "x-csrf-token": "wrong",
            },
            json={"reason": "test"},
        )
        remote_peer = TestClient(
            app,
            client=("192.0.2.10", 50000),
        ).post(
            "/api/paper/demo/halt",
            headers={
                "host": "127.0.0.1",
                "origin": "http://127.0.0.1",
                "x-csrf-token": token,
            },
            json={"reason": "test"},
        )

    assert isinstance(token, str) and len(token) >= 32
    assert missing_origin.status_code == 403
    assert missing_token.status_code == 403
    assert wrong_token.status_code == 403
    assert remote_peer.status_code == 403
    assert remote_peer.json()["detail"] == "Writable server requires a loopback client connection."
    assert not (tmp_path / "paper").exists()


def test_api_errors_never_fall_through_to_spa_and_assets_get_csp(tmp_path):
    static_dir = tmp_path / "static"
    static_dir.mkdir()
    (static_dir / "index.html").write_text("<html>desk</html>", encoding="utf-8")
    (static_dir / "assets").mkdir()
    (static_dir / "assets" / "app.js").write_text("void 0", encoding="utf-8")
    data_root = tmp_path / "data"
    data_root.mkdir()
    app = create_app(root=data_root, static_dir=static_dir)

    with TestClient(app) as client:
        deep_link = client.get("/paper/example", headers=LOOPBACK)
        dotted_fund = client.get("/paper/demo.fund", headers=LOOPBACK)
        json_report = client.get("/research/demo-report.json", headers=LOOPBACK)
        reloaded_report = client.get("/research/demo-report.json", headers=LOOPBACK)
        unknown_path = client.get("/missing.js", headers=LOOPBACK)
        missing_asset = client.get("/assets/missing.js", headers=LOOPBACK)
        api_missing = client.get("/api/not-a-route", headers=LOOPBACK)
        asset = client.get("/assets/app.js", headers=LOOPBACK)

    assert deep_link.status_code == 200
    assert "desk" in deep_link.text
    assert dotted_fund.status_code == 200
    assert json_report.status_code == 200
    assert reloaded_report.status_code == 200
    assert unknown_path.status_code == 200
    assert missing_asset.status_code == 404
    assert missing_asset.headers["content-type"].startswith("application/json")
    assert api_missing.status_code == 404
    assert api_missing.headers["content-type"].startswith("application/json")
    assert asset.text == "void 0"
    assert "default-src 'self'" in deep_link.headers["content-security-policy"]
    assert "default-src 'self'" in asset.headers["content-security-policy"]
    assert "access-control-allow-origin" not in asset.headers


def test_streamed_body_limit_checks_actual_bytes_without_content_length(tmp_path):
    enroll_synthetic_root(tmp_path)
    with TestClient(
        create_app(root=tmp_path, allow_writes=True),
        client=("127.0.0.1", 50000),
    ) as client:
        token = client.get("/api/capabilities", headers=LOOPBACK).json()["mutation_token"]
        headers = {
            "host": "127.0.0.1",
            "origin": "http://127.0.0.1",
            "x-csrf-token": token,
        }
        within_limit = client.post(
            "/api/capabilities",
            headers=headers,
            content=iter([b"x" * 600_000, b"x" * 400_000]),
        )
        over_limit = client.post(
            "/api/capabilities",
            headers=headers,
            content=iter([b"x" * 500_000, b"x" * 500_001]),
        )

    assert within_limit.status_code == 405
    assert over_limit.status_code == 413
    assert over_limit.json() == {"detail": "Request body exceeds the 1 MB limit."}
    assert over_limit.headers["cache-control"] == "no-store"
    assert "default-src 'self'" in over_limit.headers["content-security-policy"]


def test_operation_cancellation_requires_startup_write_capability(tmp_path):
    with TestClient(create_app(root=tmp_path)) as client:
        response = client.post(
            "/api/operations/" + "a" * 32 + "/cancel",
            headers=LOOPBACK,
            json={"request_id": "read-only-cancel"},
        )

    assert response.status_code == 403
    assert response.json()["detail"] == "Write capability is disabled for this server."


def test_shared_participants_join_while_fund_lanes_remain_exclusive(tmp_path):
    enroll_synthetic_root(tmp_path)
    first = create_app(root=tmp_path, allow_writes=True)
    second = create_app(root=tmp_path, allow_writes=True)
    try:
        assert first.state.service.allow_writes is True
        assert second.state.service.allow_writes is True
        with first.state.service._admission.manual_session("alpha", timeout=0):
            with pytest.raises(WriterConflict):
                with second.state.service._admission.manual_session("alpha", timeout=0):
                    pass
        with second.state.service._admission.manual_session("beta", timeout=0):
            pass
    finally:
        first.state.service.close()
        second.state.service.close()

    assert not (tmp_path / "paper").exists()


def test_container_observer_cannot_be_promoted_by_spoofed_host(tmp_path):
    with pytest.raises(ValueError, match="projection is unavailable"):
        create_app(root=tmp_path, allow_writes=True, container_bind=True)

    assert not (tmp_path / "runtime" / "private").exists()
