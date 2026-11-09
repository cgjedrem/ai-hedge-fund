import io
from datetime import datetime, timezone

import pytest

from hedge_fund.runtime.credential_delivery import (
    CredentialDeliveryServer,
    DeliveryEnvelope,
    DeliveryProtocolError,
    encode_delivery_frame,
    read_delivery_frame,
    read_delivery_reply,
)
from hedge_fund.runtime.external_credentials import (
    INSPECTION_CAPABILITY_DESTINATIONS,
    RuntimeCredentialLeaseStore,
)

ROOT_ID = "a" * 64
INSTANCE_ID = "synthetic-instance"
DESTINATION = "saxo-sim-readonly"
PURPOSE = "saxo-sim-readonly"
EXPIRY = "2026-11-10T11:59:59Z"
SENTINEL = "SYNTHETIC_BEARER_SENTINEL"


def _store():
    return RuntimeCredentialLeaseStore(
        root_id=ROOT_ID,
        instance_id=INSTANCE_ID,
        allowed_capabilities=INSPECTION_CAPABILITY_DESTINATIONS,
        clock=lambda: datetime(2026, 11, 9, 12, 0, tzinfo=timezone.utc),
    )


def test_legacy_application_frames_keep_their_existing_shape():
    legacy = DeliveryEnvelope("status", "openai", "openai")

    decoded = read_delivery_frame(io.BytesIO(encode_delivery_frame(legacy)))

    assert decoded == legacy
    assert set(legacy.to_mapping()) == {"action", "provider_id", "destination"}


def test_capability_expiry_is_published_only_in_the_private_frame_and_reply():
    store = _store()
    server = CredentialDeliveryServer(store)
    request = DeliveryEnvelope(
        action="publish",
        provider_id="saxo-demo-token",
        destination=DESTINATION,
        root_id=ROOT_ID,
        instance_id=INSTANCE_ID,
        expected_generation=0,
        delivery_id="synthetic-delivery",
        value=SENTINEL,
        purpose=PURPOSE,
        expires_at=EXPIRY,
    )
    frame = encode_delivery_frame(request)

    assert SENTINEL.encode() in frame
    assert SENTINEL not in repr(request)
    assert set(read_delivery_frame(io.BytesIO(frame)).to_mapping()) == {
        "action",
        "provider_id",
        "destination",
        "root_id",
        "instance_id",
        "expected_generation",
        "delivery_id",
        "value",
        "purpose",
        "expires_at",
    }

    reply = server.handle(read_delivery_frame(io.BytesIO(frame)))
    decoded = read_delivery_reply(io.BytesIO(server_reply(reply)))

    assert reply.state == "available"
    assert reply.purpose == PURPOSE
    assert decoded.expires_at == EXPIRY
    assert SENTINEL not in repr(reply)
    assert SENTINEL not in repr(decoded)
    assert SENTINEL not in repr(store.capability_status("saxo-demo-token", destination=DESTINATION))


@pytest.mark.parametrize(
    "changes",
    [
        {"purpose": "application"},
        {"purpose": "saxo-sim-readonly", "expires_at": None},
        {"purpose": "saxo-sim-readonly", "expires_at": "2026-11-10T12:00:00+01:00"},
        {"purpose": "saxo-sim-readonly", "expires_at": EXPIRY, "unexpected": True},
    ],
)
def test_delivery_envelope_rejects_wrong_purpose_or_malformed_capability_metadata(changes):
    fields = {
        "action": "publish",
        "provider_id": "saxo-demo-token",
        "destination": DESTINATION,
        "root_id": ROOT_ID,
        "instance_id": INSTANCE_ID,
        "expected_generation": 0,
        "delivery_id": "delivery",
        "value": SENTINEL,
        **changes,
    }
    with pytest.raises(DeliveryProtocolError):
        DeliveryEnvelope.from_mapping(fields)


def server_reply(reply):
    from hedge_fund.runtime.credential_delivery import encode_delivery_reply

    return encode_delivery_reply(reply)
