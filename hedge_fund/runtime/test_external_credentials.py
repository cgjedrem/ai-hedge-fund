import os
import socket

import pytest

from hedge_fund.runtime.credential_delivery import (
    CredentialDeliveryServer,
    DeliveryProtocolError,
)
from hedge_fund.runtime.external_credentials import (
    ExternalCredentialError,
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
    socket_dir = tmp_path / "existing"
    socket_dir.mkdir()
    socket_path = socket_dir / "credential.sock"
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
