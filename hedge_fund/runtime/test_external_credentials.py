import io
import json
import os
import socket
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest

from hedge_fund.runtime import credential_delivery
from hedge_fund.runtime.credential_delivery import (
    CredentialDeliveryServer,
    DeliveryEnvelope,
    DeliveryProtocolError,
    encode_delivery_frame,
    read_delivery_frame,
    read_delivery_reply,
    receive_delivery_request,
)
from hedge_fund.runtime.external_credentials import (
    ExternalCredentialError,
    INSPECTION_CAPABILITY_DESTINATIONS,
    runtime_inspection_capability_destinations,
    runtime_provider_destinations,
    RuntimeCredentialLeaseStore,
)

ROOT_ID = "a" * 64
INSTANCE_ID = "container-boot-1"
DELIVERY_ID = "delivery-1"
DESTINATION = "openai"
PROVIDER = "openai"


def _store(allowed=None, instance_id=INSTANCE_ID):
    return RuntimeCredentialLeaseStore(
        root_id=ROOT_ID,
        instance_id=instance_id,
        allowed_destinations=allowed or {},
    )


def _short_test_socket_path() -> Path:
    return Path("/tmp") / f"aihf-test-{os.getpid()}-{uuid4().hex[:8]}" / "credential.sock"


def test_external_runtime_allowlist_defaults_empty_and_denies_before_publication():
    store = _store()

    with pytest.raises(ExternalCredentialError, match="provider is not allowed"):
        store.publish(
            PROVIDER,
            "synthetic-secret",
            expected_generation=0,
            delivery_id=DELIVERY_ID,
            root_id=ROOT_ID,
            instance_id=INSTANCE_ID,
            destination=DESTINATION,
        )

    assert store.status() == {}


def test_inspection_capability_is_separate_from_application_provider_catalog():
    assert runtime_inspection_capability_destinations(None) == {}
    assert runtime_inspection_capability_destinations("") == {}
    assert runtime_inspection_capability_destinations("SAXO-DEMO-TOKEN") == INSPECTION_CAPABILITY_DESTINATIONS
    with pytest.raises(ExternalCredentialError, match="provider allowlist is invalid"):
        runtime_provider_destinations("saxo-demo-token")


@pytest.mark.parametrize(
    "configured",
    ["saxo", "saxo-sim-readonly", "saxo-demo-token,openai", "saxo-demo-token,saxo-demo-token", " saxo-demo-token", "saxo-demo-token,"],
    ids=["broker", "destination", "mixed-purpose", "duplicate", "leading-space", "empty-entry"],
)
def test_inspection_capability_parser_rejects_non_exact_configuration(configured):
    with pytest.raises(ExternalCredentialError, match="capability allowlist is invalid"):
        runtime_inspection_capability_destinations(configured)


def _capability_store(now=None):
    moment = now or datetime(2026, 11, 9, 12, 0, tzinfo=timezone.utc)
    return RuntimeCredentialLeaseStore(
        root_id=ROOT_ID,
        instance_id=INSTANCE_ID,
        allowed_capabilities=INSPECTION_CAPABILITY_DESTINATIONS,
        clock=lambda: moment,
    )


def _publish_capability(store, *, value="synthetic-inspection-token", generation=0, delivery_id=DELIVERY_ID, expires_at="2026-11-10T11:59:59Z"):
    return store.publish_capability(
        "saxo-demo-token",
        value,
        expected_generation=generation,
        delivery_id=delivery_id,
        root_id=ROOT_ID,
        instance_id=INSTANCE_ID,
        destination="saxo-sim-readonly",
        expires_at=expires_at,
    )


def test_capability_publication_serializes_validation_and_commit_with_revoke(monkeypatch):
    store = _capability_store()
    _publish_capability(store)
    handle = store.capture_capability("saxo-demo-token", destination="saxo-sim-readonly")
    checked, release, revoking = threading.Event(), threading.Event(), threading.Event()
    order = []
    original = store.assert_capability_dispatch_allowed

    def checked_before_commit(*args, **kwargs):
        original(*args, **kwargs)
        checked.set()
        assert release.wait(timeout=5)

    def commit():
        order.append("publication")
        return {"generation": handle.generation}

    def revoke():
        revoking.set()
        generation = store.revoke_capability("saxo-demo-token", expected_generation=1)
        order.append("revoke")
        return generation

    monkeypatch.setattr(store, "assert_capability_dispatch_allowed", checked_before_commit)
    with ThreadPoolExecutor(max_workers=2) as pool:
        publication = pool.submit(store.commit_capability_publication, handle, commit, destination="saxo-sim-readonly")
        try:
            assert checked.wait(timeout=5)
            acquired = store._lock.acquire(blocking=False)
            if acquired:
                store._lock.release()
            assert not acquired, "Validation and publication must hold the same revocation lock"
            revocation = pool.submit(revoke)
            assert revoking.wait(timeout=5)
            assert not revocation.done()
        finally:
            release.set()
        assert publication.result(timeout=5) == {"generation": 1}
        assert revocation.result(timeout=5) == 2
    assert order == ["publication", "revoke"]
    assert not store._capability_leases
    store.release(handle)


@pytest.mark.parametrize("loss", ["revoke", "invalidate", "close"])
def test_capability_publication_never_commits_when_lease_loss_wins(loss):
    store = _capability_store()
    _publish_capability(store)
    handle = store.capture_capability("saxo-demo-token", destination="saxo-sim-readonly")
    committed = []
    if loss == "revoke":
        store.revoke_capability("saxo-demo-token", expected_generation=1)
    elif loss == "invalidate":
        store.invalidate_capability(handle)
    else:
        store.close()
    with pytest.raises(ExternalCredentialError):
        store.commit_capability_publication(handle, lambda: committed.append(True), destination="saxo-sim-readonly")
    assert committed == []


def test_inspection_capability_requires_explicit_purpose_expiry_and_is_not_app_capture():
    store = _capability_store()
    with pytest.raises(ExternalCredentialError, match="provider is not allowed"):
        store.publish(
            "saxo-demo-token",
            "synthetic-token",
            expected_generation=0,
            delivery_id=DELIVERY_ID,
            root_id=ROOT_ID,
            instance_id=INSTANCE_ID,
            destination="saxo-sim-readonly",
        )

    handle = _publish_capability(store)

    assert handle.purpose == "saxo-sim-readonly"
    with pytest.raises(ExternalCredentialError, match="provider is not allowed"):
        store.current_handle("saxo-demo-token", destination="saxo-sim-readonly")
    with pytest.raises(ExternalCredentialError, match="purpose is not allowed"):
        store.acquire(handle)
    with pytest.raises(ExternalCredentialError, match="purpose is not allowed"):
        store.capture_capability("saxo-demo-token", destination="saxo-sim-readonly", purpose="application")
    assert store.capability_status("saxo-demo-token", destination="saxo-sim-readonly") == {
        "provider_id": "saxo-demo-token",
        "destination": "saxo-sim-readonly",
        "root_id": ROOT_ID,
        "instance_id": INSTANCE_ID,
        "purpose": "saxo-sim-readonly",
        "state": "available",
        "generation": 1,
        "expires_at": "2026-11-10T11:59:59Z",
    }


@pytest.mark.parametrize(
    "expires_at",
    [None, "invalid", "2026-11-09T11:59:59Z", "2026-11-10T12:00:01Z", "2026-11-10T12:00:00+01:00"],
    ids=["missing", "malformed", "past", "over-24-hours", "non-utc"],
)
def test_inspection_capability_rejects_invalid_expiry_without_generation(expires_at):
    store = _capability_store()
    with pytest.raises(ExternalCredentialError, match="credential expiry is invalid"):
        _publish_capability(store, expires_at=expires_at)
    assert store.capability_status("saxo-demo-token", destination="saxo-sim-readonly")["generation"] == 0


def test_capability_expiry_and_generation_local_rejection_fence_captured_work():
    moment = [datetime(2026, 11, 9, 12, 0, tzinfo=timezone.utc)]
    store = _capability_store()
    store._clock = lambda: moment[0]
    first = _publish_capability(store)
    captured = store.capture_capability("saxo-demo-token", destination="saxo-sim-readonly", purpose="saxo-sim-readonly")
    assert captured == first

    second = _publish_capability(store, value="synthetic-B", generation=1, delivery_id="delivery-2")
    store.invalidate_capability(first)
    with pytest.raises(ExternalCredentialError, match="credential handle is unavailable"):
        store.capability_value_for_dispatch(first, destination="saxo-sim-readonly")
    assert store.capability_status("saxo-demo-token", destination="saxo-sim-readonly")["generation"] == second.generation

    live = store.capture_capability("saxo-demo-token", destination="saxo-sim-readonly", purpose="saxo-sim-readonly")
    moment[0] += timedelta(days=2)
    with pytest.raises(ExternalCredentialError, match="credential is expired"):
        store.capability_value_for_dispatch(live, destination="saxo-sim-readonly")
    assert store.capability_status("saxo-demo-token", destination="saxo-sim-readonly")["state"] == "expired"


def test_capability_rotation_pins_old_value_until_last_capture_releases():
    store = _capability_store()
    first = _publish_capability(store, value="synthetic-A")
    one = store.capture_capability("saxo-demo-token", destination="saxo-sim-readonly")
    two = store.capture_capability("saxo-demo-token", destination="saxo-sim-readonly")
    second = _publish_capability(store, value="synthetic-B", generation=1, delivery_id="delivery-B")
    assert one == two == first and second.generation == 2
    store.release(one)
    assert store.capability_value_for_dispatch(two, destination="saxo-sim-readonly") == "synthetic-A"
    store.release(two)
    with pytest.raises(ExternalCredentialError, match="handle is unavailable"):
        store.capability_value_for_dispatch(first, destination="saxo-sim-readonly")
    current = store.capture_capability("saxo-demo-token", destination="saxo-sim-readonly")
    assert store.capability_value_for_dispatch(current, destination="saxo-sim-readonly") == "synthetic-B"
    store.release(current)
    with pytest.raises(ExternalCredentialError, match="handle is unavailable"):
        store.assert_capability_dispatch_allowed(current, destination="saxo-sim-readonly")


def test_capability_cas_revoke_close_and_restart_never_reuse_stale_pin():
    store = _capability_store()
    _publish_capability(store)
    pinned = store.capture_capability("saxo-demo-token", destination="saxo-sim-readonly")
    with pytest.raises(ExternalCredentialError, match="generation changed"):
        store.revoke_capability("saxo-demo-token", expected_generation=0)
    store.assert_capability_dispatch_allowed(pinned, destination="saxo-sim-readonly")
    assert store.revoke_capability("saxo-demo-token", expected_generation=1) == 2
    with pytest.raises(ExternalCredentialError, match="revoked"):
        store.assert_capability_dispatch_allowed(pinned, destination="saxo-sim-readonly")
    _publish_capability(store, generation=2, delivery_id="after-revoke")
    with pytest.raises(ExternalCredentialError, match="handle is unavailable"):
        store.assert_capability_dispatch_allowed(pinned, destination="saxo-sim-readonly")
    store.close()
    store.release(pinned)
    with pytest.raises(ExternalCredentialError, match="closed"):
        store.capture_capability("saxo-demo-token", destination="saxo-sim-readonly")
    restarted = _capability_store()
    restarted._instance_id = "fresh-boot"
    assert restarted.capability_status("saxo-demo-token", destination="saxo-sim-readonly")["state"] == "requires-auth"
    with pytest.raises(ExternalCredentialError, match="instance changed"):
        restarted.assert_capability_dispatch_allowed(pinned, destination="saxo-sim-readonly")


@pytest.mark.parametrize("configured", [None, ""], ids=["unset", "empty"])
def test_operator_provider_allowlist_defaults_empty(configured):
    assert runtime_provider_destinations(configured) == {}


def test_operator_provider_allowlist_is_explicit_and_normalized():
    assert runtime_provider_destinations("OpenAI,fd") == {
        "openai": "openai",
        "fd": "fd",
    }


@pytest.mark.parametrize(
    "configured",
    [" openai", "openai,", "openai,openai", "saxo", "openai\nfd", "x" * 2049],
    ids=["leading-space", "empty-entry", "duplicate", "broker-provider", "newline", "oversized"],
)
def test_operator_provider_allowlist_rejects_ambiguous_values(configured):
    with pytest.raises(ExternalCredentialError, match="provider allowlist is invalid"):
        runtime_provider_destinations(configured)


@pytest.mark.parametrize(
    "value",
    [
        "",
        " \t",
        "synthetic\nsecret",
        "synthetic\rsecret",
        "synthetic\x00secret",
        "x" * (16 * 1024 + 1),
        "€" * (16 * 1024 // 3 + 1),
    ],
    ids=["empty", "whitespace", "newline", "carriage-return", "nul", "too-many-bytes", "multibyte-too-large"],
)
def test_external_runtime_rejects_invalid_values_without_generation(value):
    store = _store({PROVIDER: DESTINATION})

    with pytest.raises(ExternalCredentialError, match="credential value is invalid"):
        store.publish(
            PROVIDER,
            value,
            expected_generation=0,
            delivery_id=DELIVERY_ID,
            root_id=ROOT_ID,
            instance_id=INSTANCE_ID,
            destination=DESTINATION,
        )

    assert store.status()[PROVIDER]["generation"] == 0
    assert store.status()[PROVIDER]["state"] == "requires-auth"


def test_closed_runtime_status_reports_closed_before_provider_allowlist():
    store = _store({PROVIDER: DESTINATION})
    store.close()

    with pytest.raises(ExternalCredentialError, match="runtime credential store is closed"):
        store.delivery_status(PROVIDER, destination=DESTINATION)


def test_rotation_keeps_frozen_generation_and_never_exposes_values_in_status():
    store = _store({PROVIDER: DESTINATION})
    first = store.publish(
        PROVIDER,
        "synthetic-A",
        expected_generation=0,
        delivery_id=DELIVERY_ID,
        root_id=ROOT_ID,
        instance_id=INSTANCE_ID,
        destination=DESTINATION,
    )
    old_capture = store.capture(PROVIDER, destination=DESTINATION)

    second = store.publish(
        PROVIDER,
        "synthetic-B",
        expected_generation=1,
        delivery_id="delivery-2",
        root_id=ROOT_ID,
        instance_id=INSTANCE_ID,
        destination=DESTINATION,
    )
    new_capture = store.capture(PROVIDER, destination=DESTINATION)

    assert first.generation == old_capture.generation == 1
    assert second.generation == new_capture.generation == 2
    assert store.value_for_dispatch(old_capture, destination=DESTINATION) == "synthetic-A"
    assert store.value_for_dispatch(new_capture, destination=DESTINATION) == "synthetic-B"
    assert "synthetic-" not in repr(store.status())
    assert "op://" not in repr(store.status())
    assert store.status()[PROVIDER] == {"state": "available", "generation": 2}


def test_failed_refresh_cas_and_replayed_delivery_leave_active_generation_unchanged():
    store = _store({PROVIDER: DESTINATION})
    handle = store.publish(
        PROVIDER,
        "synthetic-A",
        expected_generation=0,
        delivery_id=DELIVERY_ID,
        root_id=ROOT_ID,
        instance_id=INSTANCE_ID,
        destination=DESTINATION,
    )

    with pytest.raises(ExternalCredentialError, match="generation changed"):
        store.publish(
            PROVIDER,
            "synthetic-B",
            expected_generation=0,
            delivery_id="delivery-2",
            root_id=ROOT_ID,
            instance_id=INSTANCE_ID,
            destination=DESTINATION,
        )
    with pytest.raises(ExternalCredentialError, match="delivery was already used"):
        store.publish(
            PROVIDER,
            "synthetic-B",
            expected_generation=1,
            delivery_id=DELIVERY_ID,
            root_id=ROOT_ID,
            instance_id=INSTANCE_ID,
            destination=DESTINATION,
        )

    capture = store.capture(PROVIDER, destination=DESTINATION)
    assert handle.generation == capture.generation == 1
    assert store.value_for_dispatch(capture, destination=DESTINATION) == "synthetic-A"


def test_revoke_fences_existing_and_new_dispatches_and_drops_active_lease():
    store = _store({PROVIDER: DESTINATION})
    store.publish(
        PROVIDER,
        "synthetic-A",
        expected_generation=0,
        delivery_id=DELIVERY_ID,
        root_id=ROOT_ID,
        instance_id=INSTANCE_ID,
        destination=DESTINATION,
    )
    capture = store.capture(PROVIDER, destination=DESTINATION)

    assert store.revoke(PROVIDER) == 2

    with pytest.raises(ExternalCredentialError, match="credential is revoked"):
        store.value_for_dispatch(capture, destination=DESTINATION)
    with pytest.raises(ExternalCredentialError, match="credential is unavailable"):
        store.capture(PROVIDER, destination=DESTINATION)
    assert store.status()[PROVIDER] == {"state": "revoked", "generation": 2}

    with pytest.raises(ExternalCredentialError, match="credential generation changed"):
        store.publish(
            PROVIDER,
            "synthetic-B",
            expected_generation=1,
            delivery_id="delivery-2",
            root_id=ROOT_ID,
            instance_id=INSTANCE_ID,
            destination=DESTINATION,
        )
    assert store.status()[PROVIDER] == {"state": "revoked", "generation": 2}

    redelivered = store.publish(
        PROVIDER,
        "synthetic-B",
        expected_generation=2,
        delivery_id="delivery-3",
        root_id=ROOT_ID,
        instance_id=INSTANCE_ID,
        destination=DESTINATION,
    )
    assert redelivered.generation == 3
    assert store.status()[PROVIDER] == {"state": "available", "generation": 3}


def test_closed_runtime_store_drops_generations_and_rejects_reuse():
    store = _store({PROVIDER: DESTINATION})
    store.publish(
        PROVIDER,
        "synthetic-A",
        expected_generation=0,
        delivery_id=DELIVERY_ID,
        root_id=ROOT_ID,
        instance_id=INSTANCE_ID,
        destination=DESTINATION,
    )
    store.close()

    with pytest.raises(ExternalCredentialError, match="store is closed"):
        store.status()
    with pytest.raises(ExternalCredentialError, match="store is closed"):
        store.publish(
            PROVIDER,
            "synthetic-B",
            expected_generation=1,
            delivery_id="delivery-2",
            root_id=ROOT_ID,
            instance_id=INSTANCE_ID,
            destination=DESTINATION,
        )


@pytest.mark.skipif(os.name != "posix", reason="Unix socket ownership check")
def test_delivery_server_does_not_unlink_an_unowned_socket(tmp_path):
    socket_path = _short_test_socket_path()
    socket_dir = socket_path.parent
    socket_dir.mkdir()
    owner = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    owner.bind(str(socket_path))
    server = CredentialDeliveryServer(
        _store(),
        socket_path=socket_path,
    )
    try:
        with pytest.raises(DeliveryProtocolError):
            server.start()
        assert socket_path.is_socket()
    finally:
        owner.close()
        socket_path.unlink(missing_ok=True)
        socket_dir.rmdir()


def test_restart_instance_rejects_stale_runtime_handle():
    store = _store({PROVIDER: DESTINATION})
    store.publish(
        PROVIDER,
        "synthetic-A",
        expected_generation=0,
        delivery_id=DELIVERY_ID,
        root_id=ROOT_ID,
        instance_id=INSTANCE_ID,
        destination=DESTINATION,
    )
    capture = store.capture(PROVIDER, destination=DESTINATION)
    restarted = _store({PROVIDER: DESTINATION}, instance_id="container-boot-2")

    with pytest.raises(ExternalCredentialError, match="runtime instance changed"):
        restarted.value_for_dispatch(capture, destination=DESTINATION)


def test_release_discards_rotated_generation_after_last_capture():
    store = _store({PROVIDER: DESTINATION})
    old = store.publish(
        PROVIDER,
        "synthetic-A",
        expected_generation=0,
        delivery_id=DELIVERY_ID,
        root_id=ROOT_ID,
        instance_id=INSTANCE_ID,
        destination=DESTINATION,
    )
    capture = store.capture(PROVIDER, destination=DESTINATION)
    store.publish(
        PROVIDER,
        "synthetic-B",
        expected_generation=1,
        delivery_id="delivery-2",
        root_id=ROOT_ID,
        instance_id=INSTANCE_ID,
        destination=DESTINATION,
    )

    store.release(capture)

    with pytest.raises(ExternalCredentialError, match="credential handle is unavailable"):
        store.value_for_dispatch(old, destination=DESTINATION)


def test_current_handle_does_not_pin_and_acquire_requires_current_cas_generation():
    store = _store({PROVIDER: DESTINATION})
    first = store.publish(
        PROVIDER,
        "synthetic-A",
        expected_generation=0,
        delivery_id="delivery-current-1",
        root_id=ROOT_ID,
        instance_id=INSTANCE_ID,
        destination=DESTINATION,
    )
    reviewed = store.current_handle(PROVIDER, destination=DESTINATION)
    assert reviewed == first
    with pytest.raises(ExternalCredentialError, match="credential handle is unavailable"):
        store.value_for_dispatch(reviewed, destination=DESTINATION)

    store.acquire(reviewed)
    store.publish(
        PROVIDER,
        "synthetic-B",
        expected_generation=1,
        delivery_id="delivery-current-2",
        root_id=ROOT_ID,
        instance_id=INSTANCE_ID,
        destination=DESTINATION,
    )
    assert store.value_for_dispatch(reviewed, destination=DESTINATION) == "synthetic-A"

    with pytest.raises(ExternalCredentialError, match="credential generation changed"):
        store.revoke(PROVIDER, expected_generation=1)
    assert store.status()[PROVIDER] == {"state": "available", "generation": 2}
    store.release(reviewed)
    with pytest.raises(ExternalCredentialError, match="credential handle is unavailable"):
        store.value_for_dispatch(reviewed, destination=DESTINATION)

    assert store.revoke(PROVIDER, expected_generation=2) == 3


def test_receive_cli_rejects_empty_stdin_without_process_crash():
    process = subprocess.run(
        [sys.executable, "-m", "hedge_fund.runtime.credential_delivery", "--receive"],
        input=b"",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=5,
        check=False,
        env={**os.environ, "HEDGE_FUND_TEST_MODE": ""},
    )

    assert process.returncode == 2
    assert not process.stderr
    frame_size = int.from_bytes(process.stdout[:4], "big")
    frame_end = 4 + frame_size
    response = json.loads(process.stdout[4:frame_end])
    assert frame_size == len(process.stdout) - 4
    assert response["state"] == "denied"
    assert response["reason_code"] in {"protocol-error", "transport-unavailable"}


def _raw_delivery_frame(payload):
    return len(payload).to_bytes(4, "big") + payload


def test_delivery_frame_converts_deep_json_recursion_to_protocol_error():
    nested = b'{"x":' + b"[" * 2000 + b"0" + b"]" * 2000 + b"}"

    with pytest.raises(DeliveryProtocolError, match="delivery frame is malformed"):
        read_delivery_frame(io.BytesIO(_raw_delivery_frame(nested)))
    with pytest.raises(DeliveryProtocolError, match="delivery status is malformed"):
        read_delivery_reply(io.BytesIO(_raw_delivery_frame(nested)))


def test_delivery_json_converts_integer_limit_value_error_to_protocol_error():
    huge_integer = b'{"generation":' + b"9" * 5000 + b"}"

    with pytest.raises(DeliveryProtocolError, match="delivery frame is malformed"):
        read_delivery_frame(io.BytesIO(_raw_delivery_frame(huge_integer)))
    with pytest.raises(DeliveryProtocolError, match="delivery status is malformed"):
        read_delivery_reply(io.BytesIO(_raw_delivery_frame(huge_integer)))


def test_receiver_marks_post_send_failure_outcome_unknown(monkeypatch):
    sent = []

    class NoReplySocket:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def settimeout(self, _timeout):
            pass

        def connect(self, _path):
            pass

        def sendall(self, frame):
            sent.append(frame)

        def shutdown(self, _how):
            pass

        def makefile(self, _mode):
            return io.BytesIO()

    monkeypatch.setattr(credential_delivery.socket, "AF_UNIX", 1, raising=False)
    monkeypatch.setattr(credential_delivery.socket, "socket", lambda *_args: NoReplySocket())
    request = DeliveryEnvelope(
        action="publish",
        provider_id=PROVIDER,
        destination=DESTINATION,
        root_id=ROOT_ID,
        instance_id=INSTANCE_ID,
        expected_generation=0,
        delivery_id="delivery-no-reply",
        value="synthetic-runtime-value",
    )
    output = io.BytesIO()

    result = receive_delivery_request(
        stdin=io.BytesIO(encode_delivery_frame(request)),
        stdout=output,
        socket_path=Path("/synthetic/credential.sock"),
    )
    reply = read_delivery_reply(io.BytesIO(output.getvalue()))

    assert result == 2
    assert len(sent) == 1
    assert reply.state == "denied"
    assert reply.reason_code == "delivery-outcome-unknown"


@pytest.mark.skipif(os.name != "posix", reason="Unix socket server required")
def test_delivery_server_survives_deep_frame_and_handles_next_status(tmp_path):
    socket_path = _short_test_socket_path()
    server = CredentialDeliveryServer(
        _store({PROVIDER: DESTINATION}),
        socket_path=socket_path,
        peer_validator=lambda _connection: True,
    )
    server.start()

    def exchange(frame):
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(3)
            client.connect(os.fspath(socket_path))
            client.sendall(frame)
            client.shutdown(socket.SHUT_WR)
            return read_delivery_reply(client.makefile("rb"))

    try:
        nested = b'{"x":' + b"[" * 2000 + b"0" + b"]" * 2000 + b"}"
        malformed = exchange(_raw_delivery_frame(nested))
        assert malformed.state == "denied"
        assert malformed.reason_code == "protocol-error"

        valid = exchange(encode_delivery_frame(DeliveryEnvelope("status", PROVIDER, DESTINATION)))
        assert valid.state == "requires-auth"
        assert valid.generation == 0
    finally:
        server.close()


@pytest.mark.skipif(os.name != "posix", reason="Unix socket server required")
def test_delivery_server_survives_huge_integer_frame_and_handles_next_status(tmp_path):
    socket_path = _short_test_socket_path()
    server = CredentialDeliveryServer(
        _store({PROVIDER: DESTINATION}),
        socket_path=socket_path,
        peer_validator=lambda _connection: True,
    )
    server.start()

    def exchange(frame):
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(3)
            client.connect(os.fspath(socket_path))
            client.sendall(frame)
            client.shutdown(socket.SHUT_WR)
            return read_delivery_reply(client.makefile("rb"))

    try:
        huge_integer = b'{"generation":' + b"9" * 5000 + b"}"
        malformed = exchange(_raw_delivery_frame(huge_integer))
        assert malformed.state == "denied"
        assert malformed.reason_code == "protocol-error"

        valid = exchange(encode_delivery_frame(DeliveryEnvelope("status", PROVIDER, DESTINATION)))
        assert valid.state == "requires-auth"
        assert valid.generation == 0
    finally:
        server.close()


@pytest.mark.skipif(os.name != "posix", reason="Unix socket ownership required")
def test_delivery_server_recovers_only_owned_stale_socket(tmp_path):
    socket_path = _short_test_socket_path()
    parent = socket_path.parent
    parent.mkdir(mode=0o700)
    os.chmod(parent, 0o700)
    stale = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    stale.bind(os.fspath(socket_path))
    stale.close()
    os.chmod(socket_path, 0o600)
    server = CredentialDeliveryServer(
        _store({PROVIDER: DESTINATION}),
        socket_path=socket_path,
        peer_validator=lambda _connection: False,
    )

    server.start()
    assert socket_path.exists()
    server.close()
    assert not socket_path.exists()
    assert not parent.exists()


@pytest.mark.skipif(os.name != "posix", reason="Unix socket ownership required")
@pytest.mark.parametrize("case", ["active", "wrong-mode", "wrong-socket-mode", "wrong-owner", "extra-entry"])
def test_delivery_server_preserves_untrusted_existing_socket_directory(tmp_path, monkeypatch, case):
    socket_path = _short_test_socket_path()
    parent = socket_path.parent
    parent.mkdir(mode=0o700)
    os.chmod(parent, 0o700)
    active = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    active.bind(os.fspath(socket_path))
    active.listen(1)
    os.chmod(socket_path, 0o600)
    extra = parent / "unexpected"
    if case == "wrong-mode":
        os.chmod(parent, 0o755)
    elif case == "wrong-socket-mode":
        os.chmod(socket_path, 0o644)
    elif case == "wrong-owner":
        owner = os.geteuid()
        monkeypatch.setattr(credential_delivery.os, "geteuid", lambda: owner + 1)
    elif case == "extra-entry":
        extra.write_text("synthetic", encoding="utf-8")
    server = CredentialDeliveryServer(
        _store({PROVIDER: DESTINATION}),
        socket_path=socket_path,
        peer_validator=lambda _connection: False,
    )

    try:
        with pytest.raises(DeliveryProtocolError, match="private local IPC is unavailable"):
            server.start()

        active.close()
        assert socket_path.exists()
        assert extra.exists() == (case == "extra-entry")
    finally:
        active.close()
        socket_path.unlink(missing_ok=True)
        extra.unlink(missing_ok=True)
        parent.rmdir()
