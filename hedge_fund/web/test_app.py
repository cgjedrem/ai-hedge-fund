from fastapi.testclient import TestClient

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


def test_writes_require_same_origin_and_per_launch_token(tmp_path):
    app = create_app(root=tmp_path, allow_writes=True)
    with TestClient(app) as client:
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

    assert isinstance(token, str) and len(token) >= 32
    assert missing_origin.status_code == 403
    assert missing_token.status_code == 403
    assert wrong_token.status_code == 403
    assert not (tmp_path / "paper").exists()


def test_api_errors_never_fall_through_to_spa_and_assets_get_csp(tmp_path):
    static_dir = tmp_path / "static"
    static_dir.mkdir()
    (static_dir / "index.html").write_text("<html>desk</html>", encoding="utf-8")
    (static_dir / "app.js").write_text("void 0", encoding="utf-8")
    app = create_app(root=tmp_path / "data", static_dir=static_dir)

    with TestClient(app) as client:
        deep_link = client.get("/paper/example", headers=LOOPBACK)
        api_missing = client.get("/api/not-a-route", headers=LOOPBACK)
        asset = client.get("/app.js", headers=LOOPBACK)

    assert deep_link.status_code == 200
    assert "desk" in deep_link.text
    assert api_missing.status_code == 404
    assert api_missing.headers["content-type"].startswith("application/json")
    assert asset.text == "void 0"
    assert "default-src 'self'" in deep_link.headers["content-security-policy"]
    assert "default-src 'self'" in asset.headers["content-security-policy"]
    assert "access-control-allow-origin" not in asset.headers
