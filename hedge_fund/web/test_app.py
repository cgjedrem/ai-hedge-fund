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
    assert over_limit.json() == {
        "detail": "Request body exceeds the 1 MB limit.",
        "code": "payload-too-large",
        "message": "Request body exceeds the 1 MB limit.",
        "refresh_required": False,
        "retry_policy": "none",
        "subject_id": None,
        "request_id": None,
        "current_head": None,
    }
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


_ENVELOPE_KEYS = {"detail", "code", "message", "refresh_required", "retry_policy", "subject_id", "request_id", "current_head"}


def _assert_envelope(response, status, code, *, root=None):
    body = response.json()
    assert response.status_code == status
    assert set(body) == _ENVELOPE_KEYS
    assert body["code"] == code
    assert isinstance(body["message"], str) and body["message"]
    assert isinstance(body["refresh_required"], bool)
    assert body["retry_policy"] in {"none", "review-again", "reload", "inspect-status", "retry-later", "retry-read-only"}
    assert response.headers["cache-control"] == "no-store"
    if root is not None:
        assert str(root) not in response.text
        assert str(root).replace("\\", "\\\\") not in response.text
    return body


def test_boundary_denials_use_common_error_envelope_without_side_effects(tmp_path):
    enroll_synthetic_root(tmp_path)
    app = create_app(root=tmp_path, allow_writes=True)
    before = sorted(path.relative_to(tmp_path) for path in tmp_path.rglob("*"))
    called = False

    def forbidden(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("write adapter must not run")

    app.state.service.halt_fund = forbidden
    with TestClient(app, client=("127.0.0.1", 50000)) as client:
        no_session = client.post(
            "/api/paper/demo/halt",
            headers={"host": "127.0.0.1", "origin": "http://127.0.0.1", "x-csrf-token": "x"},
            json={"reason": "test"},
        )
        token = client.get("/api/capabilities", headers=LOOPBACK).json()["mutation_token"]
        valid = {"host": "127.0.0.1", "origin": "http://127.0.0.1", "x-csrf-token": token}
        responses = {
            "foreign-host": client.post("/api/paper/demo/halt", headers={**valid, "host": "desk.attacker.example"}, json={"reason": "t"}),
            "foreign-origin": client.post("/api/paper/demo/halt", headers={**valid, "origin": "https://desk.attacker.example"}, json={"reason": "t"}),
            "absent-origin": client.post("/api/paper/demo/halt", headers={"host": "127.0.0.1", "x-csrf-token": token}, json={"reason": "t"}),
            "absent-csrf": client.post("/api/paper/demo/halt", headers={"host": "127.0.0.1", "origin": "http://127.0.0.1"}, json={"reason": "t"}),
            "wrong-csrf": client.post("/api/paper/demo/halt", headers={**valid, "x-csrf-token": "expired-or-forged"}, json={"reason": "t"}),
        }
        remote_peer = TestClient(app, client=("192.0.2.10", 50000)).post("/api/paper/demo/halt", headers=valid, json={"reason": "t"})
    # No-session request is denied before any cookie existed; session/token denials are renewable by read-only reload.
    session_denial = _assert_envelope(no_session, 403, "capability-denied", root=tmp_path)
    assert session_denial["detail"] == "A valid server-owned operator session is required."
    assert (session_denial["refresh_required"], session_denial["retry_policy"]) == (True, "reload")
    renewable = {"absent-csrf", "wrong-csrf"}
    for name, response in {**responses, "remote-peer": remote_peer}.items():
        body = _assert_envelope(response, 403, "capability-denied", root=tmp_path)
        assert body["refresh_required"] is (name in renewable), name
        assert body["retry_policy"] == ("reload" if name in renewable else "none"), name
        assert body["subject_id"] is None and body["request_id"] is None, name
    assert not called
    assert sorted(path.relative_to(tmp_path) for path in tmp_path.rglob("*")) == before


def test_read_only_server_denial_is_coded_read_only(tmp_path):
    with TestClient(create_app(root=tmp_path)) as client:
        response = client.post("/api/mandates", headers=LOOPBACK, json={"spec": {}})
        deleted = client.delete("/api/settings/credentials/openai?expected_version=0", headers=LOOPBACK)

    _assert_envelope(response, 403, "read-only", root=tmp_path)
    _assert_envelope(deleted, 403, "read-only", root=tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_validation_routing_and_unhandled_errors_are_coded_and_inert(tmp_path):
    enroll_synthetic_root(tmp_path)
    app = create_app(root=tmp_path, allow_writes=True)
    hostile = "<script>alert(1)</script>" + str(tmp_path) + "\u202e"

    def explode():
        raise RuntimeError(f"secret sk-test-123 at {tmp_path}")

    app.state.service.catalog = explode
    with TestClient(app, client=("127.0.0.1", 50000), raise_server_exceptions=False) as client:
        token = client.get("/api/capabilities", headers=LOOPBACK).json()["mutation_token"]
        headers = {"host": "127.0.0.1", "origin": "http://127.0.0.1", "x-csrf-token": token}
        invalid = client.post("/api/paper/demo/halt", headers=headers, json={"reason": "x", hostile: hostile})
        wrong_method = client.post("/api/capabilities", headers=headers, json={})
        missing = client.get("/api/not-a-route", headers=LOOPBACK)
        crashed = client.get("/api/catalog", headers=LOOPBACK)

    body = _assert_envelope(invalid, 400, "invalid-request", root=tmp_path)
    assert body["subject_id"] == "demo"
    assert isinstance(body["detail"], list) and body["message"] == "Invalid request."
    assert ["body", "<redacted>"] in [item["loc"] for item in body["detail"]]
    assert "<script>" not in invalid.text and "\u202e" not in invalid.text
    _assert_envelope(wrong_method, 405, "invalid-request", root=tmp_path)
    assert "POST" not in wrong_method.headers["allow"]
    _assert_envelope(missing, 404, "not-found", root=tmp_path)
    crash = _assert_envelope(crashed, 500, "internal-error", root=tmp_path)
    assert crash["detail"] == "Internal server error."
    assert "sk-test-123" not in crashed.text


@pytest.mark.parametrize(
    ("status", "code", "refresh", "retry"),
    [
        (409, "stale-preview", True, "review-again"),
        (410, None, True, "review-again"),
        (423, "halted", False, "none"),
        (409, "ownership-unknown", True, "inspect-status"),
        (409, "writer-conflict", False, "inspect-status"),
        (423, "replay-corrupt", False, "inspect-status"),
        (423, "reconciliation-required", False, "inspect-status"),
        (422, "readiness-denied", False, "none"),
        (422, None, False, "none"),
        (403, "protected-root", False, "none"),
        (429, "budget-exhausted", False, "none"),
        (409, "request-conflict", False, "reload"),
        (503, "observation-conflict", False, "retry-read-only"),
        (403, "broker-not-web-supported", False, "none"),
        (429, None, False, "retry-later"),
        (503, None, False, "retry-read-only"),
    ],
)
def test_service_errors_map_to_contract_codes(tmp_path, status, code, refresh, retry):
    from hedge_fund.web.services import ServiceError

    app = create_app(root=tmp_path)

    def fail():
        raise ServiceError(status, "Denied.", code=code)

    app.state.service.catalog = fail
    with TestClient(app) as client:
        response = client.get("/api/catalog", headers=LOOPBACK)

    body = _assert_envelope(response, status, code or {410: "expired-confirmation", 422: "readiness-denied", 429: "capacity-denied", 503: "assets-unavailable"}[status])
    assert body["refresh_required"] is refresh
    assert body["retry_policy"] == retry


def test_service_error_rejects_codes_outside_the_contract():
    from hedge_fund.web.services import ServiceError

    with pytest.raises(ValueError, match="unknown error code"):
        ServiceError(409, "Denied.", code="made-up")


def test_tagged_service_conflicts_reach_clients_with_contract_codes():
    import inspect

    import hedge_fund.web.services as web_services

    source = inspect.getsource(web_services)
    assert 'ServiceError(423, "Halted funds cannot run a paper tick.", code="halted")' in source
    assert 'ServiceError(409, "Paper due-set changed after review.", code="stale-preview")' in source
    assert 'code="ownership-unknown"' in source


def _writable_headers(client):
    token = client.get("/api/capabilities", headers=LOOPBACK).json()["mutation_token"]
    return {"host": "127.0.0.1", "origin": "http://127.0.0.1", "x-csrf-token": token}


def _lifecycle_accept_body(request_id="req-1", archive_id="a" * 32):
    return {
        "request_id": request_id,
        "action": "restore",
        "archive_id": archive_id,
        "preview_id": "b" * 32,
        "preview_digest": "c" * 64,
        "confirmation_token": "t" * 40,
        "expected_head": "d" * 64,
    }


def test_restarted_server_rejects_prior_session_with_renewable_reload_and_no_effects(tmp_path):
    enroll_synthetic_root(tmp_path)
    first = create_app(root=tmp_path, allow_writes=True)
    second = create_app(root=tmp_path, allow_writes=True)
    calls = []
    second.state.service.halt_fund = lambda *a, **k: calls.append(a)
    with TestClient(first, client=("127.0.0.1", 50000)) as old_client:
        old_headers = _writable_headers(old_client)
        old_cookies = dict(old_client.cookies)
    before = sorted(path.relative_to(tmp_path) for path in tmp_path.rglob("*"))
    with TestClient(second, client=("127.0.0.1", 50000)) as client:
        client.cookies.update(old_cookies)
        stale = client.post("/api/paper/demo/halt", headers=old_headers, json={"reason": "t"})
        renewed = _writable_headers(client)

    body = _assert_envelope(stale, 403, "capability-denied", root=tmp_path)
    assert (body["refresh_required"], body["retry_policy"]) == (True, "reload")
    assert renewed["x-csrf-token"] != old_headers["x-csrf-token"]
    assert calls == []
    assert sorted(path.relative_to(tmp_path) for path in tmp_path.rglob("*")) == before


def test_accept_errors_echo_durable_request_and_subject_identity(tmp_path):
    from hedge_fund.web.services import ServiceError

    enroll_synthetic_root(tmp_path)
    app = create_app(root=tmp_path, allow_writes=True)

    def expired(*args, **kwargs):
        raise ServiceError(410, "Confirmation expired; review again.", code="expired-confirmation")

    def stale_with_own_identity(*args, **kwargs):
        raise ServiceError(409, "Lifecycle head changed.", code="stale-preview", subject_id="site-owned", current_head="e" * 64)

    with TestClient(app, client=("127.0.0.1", 50000)) as client:
        headers = _writable_headers(client)
        app.state.service.accept_lifecycle = expired
        expired_response = client.post("/api/lifecycle/accept", headers=headers, json=_lifecycle_accept_body())
        app.state.service.accept_lifecycle = stale_with_own_identity
        stale_response = client.post("/api/lifecycle/accept", headers=headers, json=_lifecycle_accept_body("req-2"))
        app.state.service.get_lifecycle_archive = expired
        path_response = client.get("/api/lifecycle/archives/" + "f" * 32, headers=LOOPBACK)

    body = _assert_envelope(expired_response, 410, "expired-confirmation", root=tmp_path)
    assert (body["request_id"], body["subject_id"], body["current_head"]) == ("req-1", "a" * 32, None)
    assert (body["refresh_required"], body["retry_policy"]) == (True, "review-again")
    stale = _assert_envelope(stale_response, 409, "stale-preview", root=tmp_path)
    assert (stale["request_id"], stale["subject_id"], stale["current_head"]) == ("req-2", "site-owned", "e" * 64)
    path_body = _assert_envelope(path_response, 410, "expired-confirmation", root=tmp_path)
    assert (path_body["subject_id"], path_body["request_id"]) == ("f" * 32, None)


@pytest.mark.parametrize("hostile", ["../etc/passwd", "<script>x</script>", "a" * 400, "name\u202e", "C:\\secret", ""])
def test_error_identity_drops_unsafe_values_instead_of_echoing_them(hostile):
    from hedge_fund.web.schemas import error_payload

    body = error_payload(409, "Denied.", code="stale-preview", subject_id=hostile, request_id=hostile, current_head=hostile)

    assert (body["subject_id"], body["request_id"], body["current_head"]) == (None, None, None)
    assert body["code"] == "stale-preview" and body["retry_policy"] == "review-again"


def test_every_tagged_service_error_site_uses_a_contract_status():
    import ast
    import inspect

    import hedge_fund.web.services as web_services
    from hedge_fund.web.schemas import error_code_status_matches

    sites = []
    for node in ast.walk(ast.parse(inspect.getsource(web_services))):
        if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "ServiceError" and node.args:
            status = node.args[0]
            code = next((kw.value for kw in node.keywords if kw.arg == "code"), None)
            if isinstance(status, ast.Constant) and isinstance(code, ast.Constant):
                sites.append((node.lineno, status.value, code.value))
    assert len(sites) >= 20
    mismatched = [site for site in sites if not error_code_status_matches(site[1], site[2])]
    assert mismatched == []
    assert not error_code_status_matches(409, "halted")
    assert not error_code_status_matches(422, "invalid-request")
    assert error_code_status_matches(423, "reconciliation-required")


def test_registry_busy_reads_are_read_only_retryable_but_permanent_faults_are_not(tmp_path, monkeypatch):
    import hedge_fund.web.services as web_services
    from hedge_fund.runtime.lifecycle import ArchiveError
    from hedge_fund.runtime.operations import OperationBusy

    enroll_synthetic_root(tmp_path)
    app = create_app(root=tmp_path, allow_writes=True)

    def busy(*args, **kwargs):
        raise OperationBusy("operation admission lock is unavailable")

    def corrupt(*args, **kwargs):
        raise ArchiveError("synthetic corrupt archive")

    with TestClient(app, client=("127.0.0.1", 50000)) as client:
        monkeypatch.setattr(web_services.LifecycleArchiveStore, "list_archives", busy)
        busy_list = client.get("/api/lifecycle/archives", headers=LOOPBACK)
        monkeypatch.setattr(web_services.LifecycleArchiveStore, "list_archives", corrupt)
        corrupt_list = client.get("/api/lifecycle/archives", headers=LOOPBACK)

    busy_body = _assert_envelope(busy_list, 503, "observation-conflict", root=tmp_path)
    assert (busy_body["refresh_required"], busy_body["retry_policy"]) == (False, "retry-read-only")
    corrupt_body = _assert_envelope(corrupt_list, 409, "request-conflict", root=tmp_path)
    assert corrupt_body["retry_policy"] not in {"retry-later", "retry-read-only"}


def test_only_operation_busy_lifecycle_faults_are_retryable(tmp_path, monkeypatch):
    import hedge_fund.web.services as web_services
    from hedge_fund.runtime.handover import LedgerDrift
    from hedge_fund.runtime.operations import OperationBusy, OperationConflict

    enroll_synthetic_root(tmp_path)
    app = create_app(root=tmp_path, allow_writes=True)
    outcomes = {}
    faults = {
        "busy": OperationBusy("operation admission lock is unavailable"),
        "drift": LedgerDrift("synthetic offline inventory change"),
        "conflict": OperationConflict("request identity conflicts with durable state"),
        "os": OSError("synthetic disk fault"),
    }
    with TestClient(app, client=("127.0.0.1", 50000)) as client:
        headers = _writable_headers(client)
        for name, fault in faults.items():

            def fail(*args, _fault=fault, **kwargs):
                raise _fault

            monkeypatch.setattr(web_services.OperationStore, "get_by_request", fail)
            outcomes[name] = client.post("/api/lifecycle/accept", headers=headers, json=_lifecycle_accept_body(f"req-{name}"))

    policies = {}
    for name, response in outcomes.items():
        body = _assert_envelope(response, response.status_code, response.json()["code"], root=tmp_path)
        assert "synthetic" not in response.text
        policies[name] = (response.status_code, body["code"], body["retry_policy"], body["request_id"])
    assert policies["busy"] == (409, "writer-conflict", "retry-later", "req-busy")
    assert policies["drift"] == (423, "reconciliation-required", "inspect-status", "req-drift")
    for name in ("conflict", "os"):
        assert policies[name][2] not in {"retry-later", "retry-read-only"}, name


def test_unavailable_operation_storage_is_not_reported_as_an_unknown_operation(tmp_path):
    app = create_app(root=tmp_path)
    app.state.service._operation_store = None
    with TestClient(app) as client:
        response = client.get("/api/operations/" + "f" * 32, headers=LOOPBACK)
        by_request = client.get("/api/operations/by-request/synthetic-request", headers=LOOPBACK)

    body = _assert_envelope(response, 503, "observation-conflict", root=tmp_path)
    assert body["code"] != "not-found"
    assert (body["retry_policy"], body["subject_id"]) == ("retry-read-only", "f" * 32)
    request_body = _assert_envelope(by_request, 503, "observation-conflict", root=tmp_path)
    assert request_body["retry_policy"] == "retry-read-only"


def test_service_error_rejects_unknown_retry_policy():
    from hedge_fund.web.services import ServiceError

    with pytest.raises(ValueError, match="unknown retry policy"):
        ServiceError(409, "Denied.", code="writer-conflict", retry_policy="always")
