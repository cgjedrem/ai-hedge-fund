import io
import json
import subprocess
from datetime import datetime, timezone

import pytest

from hedge_fund.runtime.credential_delivery import (
    CredentialDeliveryServer,
    DeliveryEnvelope,
    DeliveryProtocolError,
    DeliveryReply,
    encode_delivery_frame,
    encode_delivery_reply,
    read_delivery_frame,
    read_delivery_reply,
)
from hedge_fund.runtime.external_credentials import (
    ExternalCredentialError,
    runtime_provider_destinations,
    RuntimeCredentialLeaseStore,
)
from hedge_fund.secrets import docker_delivery
from hedge_fund.secrets.docker_delivery import (
    DockerCredentialDelivery,
    DockerCredentialDeliveryError,
    load_source_mappings,
)
from hedge_fund.secrets.docker_delivery import main as delivery_main
from hedge_fund.secrets.docker_delivery import SourceMapping

ROOT_ID = "a" * 64
INSTANCE_ID = "operator-boot-1"
DELIVERY_ID = "delivery-1"
SENTINEL = "synthetic-only-value"
CONTAINER_ID = "b" * 64
IMAGE_ID = "sha256:" + "c" * 64
SOURCE_SHA256 = "d" * 64


def test_delivery_frame_round_trip_contains_value_only_in_private_payload():
    request = DeliveryEnvelope(
        action="publish",
        provider_id="openai",
        destination="openai",
        root_id=ROOT_ID,
        instance_id=INSTANCE_ID,
        expected_generation=0,
        delivery_id=DELIVERY_ID,
        value=SENTINEL,
    )

    frame = encode_delivery_frame(request)
    parsed = read_delivery_frame(io.BytesIO(frame))

    assert parsed == request
    assert SENTINEL not in repr(parsed)
    assert SENTINEL.encode("utf-8") in frame


@pytest.mark.parametrize(
    "frame",
    [b"", b"\x00", b"\x00\x00\x00\x10short", (33 * 1024).to_bytes(4, "big")],
    ids=["empty", "partial-header", "partial-body", "oversized-frame"],
)
def test_delivery_frame_rejects_empty_partial_and_oversized_input(frame):
    with pytest.raises(DeliveryProtocolError):
        read_delivery_frame(io.BytesIO(frame))


def test_delivery_frame_rejects_trailing_records_and_unknown_fields():
    valid = encode_delivery_frame(
        DeliveryEnvelope(
            action="status",
            provider_id="openai",
            destination="openai",
        )
    )

    with pytest.raises(DeliveryProtocolError):
        read_delivery_frame(io.BytesIO(valid + valid))

    with pytest.raises(DeliveryProtocolError):
        encode_delivery_frame(
            {
                "action": "status",
                "provider_id": "openai",
                "destination": "openai",
                "extra": SENTINEL,
            }
        )


@pytest.mark.parametrize(
    "value",
    ["", " ", "line\nbreak", "line\rbreak", "nul\x00byte", "x" * (16 * 1024 + 1)],
    ids=["empty", "whitespace", "newline", "carriage-return", "nul", "oversized-value"],
)
def test_delivery_frame_rejects_invalid_secret_values(value):
    with pytest.raises(DeliveryProtocolError):
        DeliveryEnvelope(
            action="publish",
            provider_id="openai",
            destination="openai",
            root_id=ROOT_ID,
            instance_id=INSTANCE_ID,
            expected_generation=0,
            delivery_id=DELIVERY_ID,
            value=value,
        )


def test_backend_preflight_denies_empty_allowlist_without_secret_resolution():
    store = RuntimeCredentialLeaseStore(
        root_id=ROOT_ID,
        instance_id=INSTANCE_ID,
    )
    server = CredentialDeliveryServer(store)

    reply = server.handle(
        DeliveryEnvelope(
            action="status",
            provider_id="openai",
            destination="openai",
        )
    )

    assert reply.state == "denied"
    assert reply.reason_code == "provider-not-allowed"
    assert reply.root_id is None
    assert SENTINEL not in repr(reply)


def test_backend_publishes_fake_value_only_to_allowed_runtime_lease():
    store = RuntimeCredentialLeaseStore(
        root_id=ROOT_ID,
        instance_id=INSTANCE_ID,
        allowed_destinations={"openai": "openai"},
    )
    server = CredentialDeliveryServer(store)
    preflight = server.handle(
        DeliveryEnvelope(
            action="status",
            provider_id="openai",
            destination="openai",
        )
    )
    request = DeliveryEnvelope(
        action="publish",
        provider_id="openai",
        destination="openai",
        root_id=ROOT_ID,
        instance_id=INSTANCE_ID,
        expected_generation=preflight.generation,
        delivery_id=DELIVERY_ID,
        value=SENTINEL,
    )

    reply = server.handle(request)
    capture = store.capture("openai", destination="openai")

    assert reply.state == "available"
    assert reply.generation == 1
    assert SENTINEL not in repr(reply)
    assert store.value_for_dispatch(capture, destination="openai") == SENTINEL
    assert read_delivery_reply(io.BytesIO(encode_delivery_reply(reply))) == reply


def test_backend_authority_denial_precedes_status_or_publication():
    store = RuntimeCredentialLeaseStore(
        root_id=ROOT_ID,
        instance_id=INSTANCE_ID,
        allowed_destinations={"openai": "openai"},
    )

    def deny_admission():
        raise RuntimeError(SENTINEL)

    server = CredentialDeliveryServer(
        store,
        admission_check=deny_admission,
    )
    reply = server.handle(
        DeliveryEnvelope(
            action="status",
            provider_id="openai",
            destination="openai",
        )
    )

    assert reply.state == "denied"
    assert reply.reason_code == "delivery-denied"
    assert SENTINEL not in repr(reply)
    assert store.status()["openai"] == {"state": "requires-auth", "generation": 0}


def test_host_maps_huge_integer_reply_to_outcome_unknown():
    payload = b'{"generation":' + b"9" * 5000 + b"}"
    malformed_reply = len(payload).to_bytes(4, "big") + payload

    def runner(args, **_kwargs):
        return subprocess.CompletedProcess(args, 0, stdout=malformed_reply, stderr=b"")

    delivery = DockerCredentialDelivery(runner=runner)
    request = DeliveryEnvelope(
        action="publish",
        provider_id="openai",
        destination="openai",
        root_id=ROOT_ID,
        instance_id=INSTANCE_ID,
        expected_generation=0,
        delivery_id=DELIVERY_ID,
        value=SENTINEL,
    )

    with pytest.raises(DockerCredentialDeliveryError, match="delivery-outcome-unknown"):
        delivery._exchange(
            CONTAINER_ID,
            request,
            docker_delivery.time.monotonic() + 5,
            publish=True,
        )


class FakeDockerRunner:
    def __init__(
        self,
        *,
        remote=False,
        invalid_mount=False,
        lose_publish_ack=False,
        root_id=ROOT_ID,
        extra_container_env=(),
        runtime_providers="",
        host_config_overrides=None,
        inspection_profile=False,
        inspection_overrides=None,
    ):
        self.inspection_profile = inspection_profile
        self.inspection_overrides = inspection_overrides or {}
        self.store = RuntimeCredentialLeaseStore(
            root_id=root_id,
            instance_id=INSTANCE_ID,
            allowed_destinations={"openai": "openai"},
            allowed_capabilities={"saxo-demo-token": "saxo-sim-readonly"} if inspection_profile else {},
            clock=lambda: datetime(2026, 11, 9, 12, 0, tzinfo=timezone.utc),
        )
        self.server = CredentialDeliveryServer(self.store)
        self.calls = []
        self.remote = remote
        self.invalid_mount = invalid_mount
        self.lose_publish_ack = lose_publish_ack
        self.extra_container_env = list(extra_container_env)
        self.runtime_providers = runtime_providers
        self.host_config = {
            "Tmpfs": {"/tmp": "rw"},
            "Privileged": False,
            "ReadonlyRootfs": True,
            "NetworkMode": "none",
            "CapDrop": ["ALL"],
            "CapAdd": [],
            "SecurityOpt": ["no-new-privileges:true"],
            "PidMode": "",
            "IpcMode": "private",
            "Devices": [],
        }
        if inspection_profile:
            self.host_config.update(
                {
                    "NetworkMode": "synthetic-project_saxo-inspection",
                    "PublishAllPorts": False,
                    "PortBindings": {"8876/tcp": [{"HostIp": "127.0.0.1", "HostPort": "8877"}]},
                }
            )
        self.host_config.update(host_config_overrides or {})
        self.publish_count = 0

    def __call__(self, args, **kwargs):
        self.calls.append((tuple(args), dict(kwargs)))
        if args[:3] == ["docker", "context", "show"]:
            return subprocess.CompletedProcess(args, 0, stdout=b"desktop-linux\n", stderr=b"")
        if args[:3] == ["docker", "context", "inspect"]:
            host = "tcp://remote.invalid:2376" if self.remote else "npipe:////./pipe/dockerDesktopLinuxEngine"
            body = [{"Endpoints": {"docker": {"Host": host}}}]
            return subprocess.CompletedProcess(args, 0, stdout=json.dumps(body).encode(), stderr=b"")
        if args[:3] == ["docker", "info", "--format"]:
            return subprocess.CompletedProcess(args, 0, stdout=b"linux\n", stderr=b"")
        if args[:3] == ["docker", "inspect", "--type"]:
            mount = (
                {"Type": "bind", "Source": "C:/Users/operator", "Destination": "/data"}
                if self.invalid_mount
                else {
                    "Type": "volume",
                    "Name": "synthetic-ext4",
                    "Destination": "/data",
                    "RW": True,
                }
            )
            labels = {
                "com.docker.compose.service": "web-operator",
                "org.opencontainers.image.revision": "e" * 40,
                "org.opencontainers.image.source-sha256": SOURCE_SHA256,
            }
            environment = [
                "HEDGE_FUND_DATA_PROVIDER=yfinance",
                "HEDGE_FUND_RUNTIME_ROLE=web-operator",
                f"HEDGE_FUND_RUNTIME_PROVIDERS={self.runtime_providers}",
            ] + self.extra_container_env
            config = {"Entrypoint": ["aihf-web-supervisor", "--root", "/data"], "Labels": labels, "Env": environment, "User": ""}
            host_config = self.host_config
            mount_list = [mount]
            network_settings = {}
            if self.inspection_profile:
                labels.update(
                    {
                        "com.docker.compose.service": "saxo-inspection-operator",
                        "com.docker.compose.project": "synthetic-project",
                        "aihf.runtime.profile": "saxo-inspection",
                        "aihf.runtime.root-purpose": "saxo-inspection",
                        "org.opencontainers.image.revision": "e" * 40,
                        "org.opencontainers.image.source-sha256": SOURCE_SHA256,
                    }
                )
                environment = [
                    "HEDGE_FUND_DATA_PROVIDER=yfinance",
                    "HEDGE_FUND_RUNTIME_ROLE=web-operator",
                    "HEDGE_FUND_RUNTIME_PROVIDERS=",
                    "HEDGE_FUND_RUNTIME_CAPABILITIES=saxo-demo-token",
                ] + self.extra_container_env
                host_config = dict(self.host_config)
                config = {
                    "Entrypoint": ["aihf-web-supervisor", "--root", "/data"],
                    "Labels": labels,
                    "Env": environment,
                    "User": "",
                    "ExposedPorts": {"8876/tcp": {}},
                }
                mount["Name"] = "synthetic-inspection-root"
                mount_list = [mount]
                network_settings = {
                    "Networks": {
                        "synthetic-project_saxo-inspection": {
                            "NetworkID": "f" * 64,
                        }
                    }
                }
                for key, value in self.inspection_overrides.items():
                    if key == "labels":
                        labels.update(value)
                    elif key == "env":
                        environment[:] = value
                        config["Env"] = environment
                    elif key == "mounts":
                        mount_list = value
                    elif key == "networks":
                        network_settings["Networks"] = value
                    elif key == "host_config":
                        host_config.update(value)
                    elif key == "exposed_ports":
                        config["ExposedPorts"] = value
            body = [
                {
                    "Id": CONTAINER_ID,
                    "Image": self.inspection_overrides.get("image", IMAGE_ID),
                    "State": {"Status": "running", "StartedAt": "2026-11-09T10:00:00Z"},
                    "Config": config,
                    "HostConfig": host_config,
                    "Mounts": mount_list,
                    "NetworkSettings": network_settings,
                }
            ]
            return subprocess.CompletedProcess(args, 0, stdout=json.dumps(body).encode(), stderr=b"")
        if args[:3] == ["docker", "volume", "inspect"]:
            volume_name = "synthetic-inspection-root" if self.inspection_profile else "synthetic-ext4"
            body = [
                {
                    "Name": volume_name,
                    "Driver": "local",
                    "Scope": "local",
                    "CreatedAt": "2026-11-09T10:00:00Z",
                    "Labels": self.inspection_overrides.get(
                        "volume_labels",
                        {"aihf.runtime.root-purpose": "saxo-inspection", "com.docker.compose.volume": "saxo-inspection-data"},
                    ),
                }
            ]
            return subprocess.CompletedProcess(args, 0, stdout=json.dumps(body).encode(), stderr=b"")
        if args[:3] == ["docker", "network", "inspect"]:
            network = {
                "Id": "f" * 64,
                "Driver": "bridge",
                "Scope": "local",
                "Internal": False,
                "Attachable": False,
                "Labels": {
                    "aihf.runtime.profile": "saxo-inspection",
                    "com.docker.compose.network": "saxo-inspection",
                    "com.docker.compose.project": "synthetic-project",
                },
                "Containers": {CONTAINER_ID: {}},
            }
            network.update(self.inspection_overrides.get("network", {}))
            body = [network]
            return subprocess.CompletedProcess(args, 0, stdout=json.dumps(body).encode(), stderr=b"")
        if args[:2] == ["docker", "exec"]:
            request = read_delivery_frame(io.BytesIO(kwargs["input"]))
            reply = self.server.handle(request)
            if request.action == "publish":
                self.publish_count += 1
                if self.lose_publish_ack:
                    raise subprocess.TimeoutExpired(args, kwargs["timeout"])
            return subprocess.CompletedProcess(args, 0, stdout=encode_delivery_reply(reply), stderr=b"")
        raise AssertionError("unexpected fake Docker command")


def _mapping():
    return {
        "openai": SourceMapping(
            "openai",
            "op://SyntheticVault/SyntheticItem/api-key",
            "openai",
            ROOT_ID,
            CONTAINER_ID,
            IMAGE_ID,
            "e" * 40,
            SOURCE_SHA256,
            "synthetic-ext4",
        )
    }


def _mapping_config():
    return {
        "schema": 1,
        "mappings": [
            {
                "provider_id": "openai",
                "reference": "op://SyntheticVault/SyntheticItem/api-key",
                "destination": "openai",
                "root_id": ROOT_ID,
                "container_id": CONTAINER_ID,
                "image_id": IMAGE_ID,
                "revision": "e" * 40,
                "source_sha256": SOURCE_SHA256,
                "volume_name": "synthetic-ext4",
            }
        ],
    }


def _inspection_mapping():
    return SourceMapping(
        "saxo-demo-token",
        "op://SyntheticVault/SyntheticItem/access-token",
        "saxo-sim-readonly",
        ROOT_ID,
        CONTAINER_ID,
        IMAGE_ID,
        "e" * 40,
        SOURCE_SHA256,
        "synthetic-inspection-root",
        "saxo-inspection",
        "2026-11-10T11:59:59Z",
    )


def test_saxo_inspection_delivery_uses_exact_capability_profile_and_expiry_before_private_publish():
    runner = FakeDockerRunner(inspection_profile=True)
    resolver_calls = []
    delivery = DockerCredentialDelivery(
        runner=runner,
        resolver=lambda reference, _timeout: resolver_calls.append(reference) or SENTINEL,
        source_mappings={"saxo-demo-token": _inspection_mapping()},
        environment={},
        utc_clock=lambda: datetime(2026, 11, 9, 12, 0, tzinfo=timezone.utc),
    )

    result = delivery.deliver(CONTAINER_ID, "saxo-demo-token")
    handle = runner.store.capture_capability("saxo-demo-token", destination="saxo-sim-readonly")

    assert result.state == "available"
    assert result.generation == handle.generation == 1
    assert runner.store.capability_value_for_dispatch(handle, destination="saxo-sim-readonly") == SENTINEL
    assert resolver_calls == ["op://SyntheticVault/SyntheticItem/access-token"]
    requests = [read_delivery_frame(io.BytesIO(kwargs["input"])) for args, kwargs in runner.calls if args[:2] == ("docker", "exec")]
    assert [request.action for request in requests] == ["status", "publish"]
    assert all(request.purpose == "saxo-sim-readonly" for request in requests)
    assert requests[1].expires_at == _inspection_mapping().expires_at
    assert all(SENTINEL not in " ".join(args) for args, _kwargs in runner.calls)
    assert SENTINEL not in repr(result)


@pytest.mark.parametrize(
    "expiry",
    ["2026-11-09T11:59:59Z", "2026-11-10T12:00:01Z"],
    ids=["expired", "over-24-hours"],
)
def test_saxo_expiry_is_rejected_before_target_or_resolver(expiry):
    runner = FakeDockerRunner(inspection_profile=True)
    resolver_calls = []
    mapping = _inspection_mapping()
    mapping = SourceMapping(
        mapping.provider_id,
        mapping.reference,
        mapping.destination,
        mapping.root_id,
        mapping.container_id,
        mapping.image_id,
        mapping.revision,
        mapping.source_sha256,
        mapping.volume_name,
        mapping.topology_profile,
        expiry,
    )

    with pytest.raises(DockerCredentialDeliveryError, match="mapping-invalid"):
        DockerCredentialDelivery(
            runner=runner,
            resolver=lambda *_args: resolver_calls.append(True),
            source_mappings={"saxo-demo-token": mapping},
            environment={},
            utc_clock=lambda: datetime(2026, 11, 9, 12, 0, tzinfo=timezone.utc),
        ).deliver(CONTAINER_ID, "saxo-demo-token")
    assert runner.calls == []
    assert resolver_calls == []


def test_saxo_malformed_expiry_is_rejected_when_mapping_is_created():
    with pytest.raises(DockerCredentialDeliveryError, match="mapping-invalid"):
        SourceMapping(
            "saxo-demo-token",
            "op://SyntheticVault/SyntheticItem/access-token",
            "saxo-sim-readonly",
            ROOT_ID,
            CONTAINER_ID,
            IMAGE_ID,
            "e" * 40,
            SOURCE_SHA256,
            "synthetic-inspection-root",
            "saxo-inspection",
            "invalid",
        )


@pytest.mark.parametrize(
    "overrides",
    [
        {"host_config": {"NetworkMode": "host"}},
        {"host_config": {"PortBindings": {"8876/tcp": [{"HostIp": "0.0.0.0", "HostPort": "8877"}]}}},
        {"host_config": {"PortBindings": {"8876/tcp": [{"HostIp": "127.0.0.1", "HostPort": "8878"}]}}},
        {"host_config": {"PortBindings": {"8876/tcp": [{"HostIp": "127.0.0.1", "HostPort": "8877"}], "9000/tcp": [{"HostIp": "127.0.0.1", "HostPort": "9000"}]}}},
        {"networks": {"extra": {"NetworkID": "f" * 64}}},
        {"network": {"Containers": {CONTAINER_ID: {}, "e" * 64: {}}}},
        {"network": {"Driver": "host"}},
        {"labels": {"aihf.runtime.root-purpose": "fund"}},
        {"labels": {"aihf.runtime.profile": "op-runtime"}},
        {"labels": {"com.docker.compose.service": "web-operator"}},
        {"labels": {"org.opencontainers.image.revision": "f" * 40}},
        {"image": "sha256:" + "f" * 64},
        {"env": ["HEDGE_FUND_RUNTIME_ROLE=observer", "HEDGE_FUND_RUNTIME_PROVIDERS=", "HEDGE_FUND_RUNTIME_CAPABILITIES=saxo-demo-token"]},
        {"env": ["HEDGE_FUND_RUNTIME_ROLE=web-operator", "HEDGE_FUND_RUNTIME_PROVIDERS=", "HEDGE_FUND_RUNTIME_CAPABILITIES=saxo-demo-token", "HTTPS_PROXY=http://proxy.invalid"]},
        {"mounts": [{"Type": "volume", "Name": "fund-state", "Destination": "/data", "RW": True}, {"Type": "volume", "Name": "extra", "Destination": "/extra", "RW": True}]},
    ],
    ids=["host-network", "wildcard-port", "wrong-port", "extra-port", "extra-network", "extra-network-member", "wrong-network-driver", "fund-root", "wrong-profile", "wrong-service", "source-drift", "image-drift", "wrong-role", "proxy", "extra-volume"],
)
def test_saxo_inspection_topology_denial_precedes_secret_resolution(overrides):
    runner = FakeDockerRunner(inspection_profile=True, inspection_overrides=overrides)
    resolver_calls = []
    with pytest.raises(DockerCredentialDeliveryError):
        DockerCredentialDelivery(
            runner=runner,
            resolver=lambda *_args: resolver_calls.append(True),
            source_mappings={"saxo-demo-token": _inspection_mapping()},
            environment={},
            utc_clock=lambda: datetime(2026, 11, 9, 12, 0, tzinfo=timezone.utc),
        ).deliver(CONTAINER_ID, "saxo-demo-token")
    assert resolver_calls == []
    assert runner.publish_count == 0


def test_inspection_mapping_requires_exact_profile_and_expiry_metadata(tmp_path):
    good = _inspection_mapping()
    config = {
        "schema": 1,
        "mappings": [
            {
                "provider_id": good.provider_id,
                "reference": good.reference,
                "destination": good.destination,
                "root_id": good.root_id,
                "container_id": good.container_id,
                "image_id": good.image_id,
                "revision": good.revision,
                "source_sha256": good.source_sha256,
                "volume_name": good.volume_name,
                "topology_profile": good.topology_profile,
                "expires_at": good.expires_at,
            }
        ],
    }
    mapping_file = tmp_path / "inspection-mapping.json"
    mapping_file.write_text(json.dumps(config), encoding="utf-8")
    mappings = load_source_mappings(mapping_file)
    assert mappings["saxo-demo-token"] == good

    config["mappings"][0]["topology_profile"] = "op-runtime"
    mapping_file.write_text(json.dumps(config), encoding="utf-8")
    with pytest.raises(DockerCredentialDeliveryError, match="mapping-config-invalid"):
        load_source_mappings(mapping_file)


def test_saxo_compose_profile_is_separate_and_op_runtime_stays_network_none():
    import yaml

    with open("docker-compose.op-runtime.yml", encoding="utf-8") as stream:
        original = yaml.safe_load(stream)
    with open("docker-compose.saxo-inspection.yml", encoding="utf-8") as stream:
        inspection = yaml.safe_load(stream)

    original_service = original["services"]["web-operator"]
    assert original_service["network_mode"] == "none"
    assert "ports" not in original_service
    service = inspection["services"]["saxo-inspection-operator"]
    assert service["profiles"] == ["saxo-inspection"]
    assert service["ports"] == ["127.0.0.1:8877:8876"]
    assert service["networks"] == ["saxo-inspection"]
    assert service["volumes"] == ["saxo-inspection-data:/data"]
    assert service["environment"]["HEDGE_FUND_RUNTIME_PROVIDERS"] == ""
    assert service["environment"]["HEDGE_FUND_RUNTIME_CAPABILITIES"] == "${HEDGE_FUND_RUNTIME_CAPABILITIES:-}"
    assert inspection["volumes"]["saxo-inspection-data"]["external"] is True
    assert inspection["networks"]["saxo-inspection"]["driver"] == "bridge"


@pytest.mark.parametrize("provider", ["saxo"])
def test_saxo_delivery_cli_denies_before_mapping_docker_or_resolution(monkeypatch, provider):
    def forbidden(*_args, **_kwargs):
        pytest.fail("broker delivery must be denied before accessing mappings or external systems")

    monkeypatch.setattr(docker_delivery, "load_source_mappings", forbidden)
    output = io.StringIO()

    result = delivery_main(
        ["--provider", provider],
        runner=forbidden,
        resolver=forbidden,
        environment={},
        stdout=output,
    )

    assert result == 2
    assert output.getvalue() == "delivery=denied reason=provider-not-allowed\n"


@pytest.mark.parametrize("provider", ["saxo"])
def test_saxo_delivery_mapping_cannot_grant_broker_authority(provider):
    row = _mapping_config()["mappings"][0]
    row.update(provider_id=provider, destination=provider)

    with pytest.raises(DockerCredentialDeliveryError, match="^provider-not-allowed$"):
        SourceMapping(**row)
    with pytest.raises(ExternalCredentialError, match="provider allowlist is invalid"):
        runtime_provider_destinations(provider)
    with pytest.raises(ExternalCredentialError, match="not an allowed application provider"):
        RuntimeCredentialLeaseStore(
            root_id=ROOT_ID,
            instance_id=INSTANCE_ID,
            allowed_destinations={provider: provider},
        )


@pytest.mark.parametrize("action", ["status", "publish"])
def test_saxo_delivery_backend_denies_without_changing_application_lease(action):
    store = RuntimeCredentialLeaseStore(
        root_id=ROOT_ID,
        instance_id=INSTANCE_ID,
        allowed_destinations={"openai": "openai"},
    )
    fields = {}
    if action == "publish":
        fields = {
            "root_id": ROOT_ID,
            "instance_id": INSTANCE_ID,
            "expected_generation": 0,
            "delivery_id": DELIVERY_ID,
            "value": SENTINEL,
        }

    reply = CredentialDeliveryServer(store).handle(DeliveryEnvelope(action=action, provider_id="saxo", destination="saxo", **fields))

    assert reply.state == "denied"
    assert reply.reason_code == "provider-not-allowed"
    assert SENTINEL not in repr(reply)
    assert store.status() == {"openai": {"state": "requires-auth", "generation": 0}}


def test_missing_host_mapping_config_is_empty_and_never_resolves(tmp_path):
    missing = tmp_path / "not-created.json"
    runner = FakeDockerRunner()
    resolver_calls = []
    output = io.StringIO()

    result = delivery_main(
        ["--config", str(missing), "--provider", "openai"],
        runner=runner,
        resolver=lambda *_args: resolver_calls.append(True),
        environment={},
        stdout=output,
    )

    assert result == 2
    assert output.getvalue() == "delivery=denied reason=provider-not-allowed\n"
    assert runner.calls == []
    assert resolver_calls == []


def test_host_mapping_config_drives_fake_cli_delivery_without_echoing_reference_or_value(tmp_path):
    mapping_file = tmp_path / "op-runtime-mappings.json"
    mapping_file.write_text(json.dumps(_mapping_config()), encoding="utf-8")
    runner = FakeDockerRunner()
    output = io.StringIO()

    result = delivery_main(
        ["--config", str(mapping_file), "--provider", "openai"],
        runner=runner,
        resolver=lambda *_args: SENTINEL,
        environment={},
        stdout=output,
    )
    capture = runner.store.capture("openai", destination="openai")

    assert result == 0
    assert output.getvalue() == "delivery=available provider=openai generation=1\n"
    assert SENTINEL not in output.getvalue()
    assert "SyntheticVault" not in output.getvalue()
    assert runner.store.value_for_dispatch(capture, destination="openai") == SENTINEL


@pytest.mark.parametrize(
    "config",
    [
        {"schema": 1, "mappings": [{"provider_id": "openai", "value": SENTINEL}]},
        {"schema": True, "mappings": []},
        {"schema": 1, "mappings": [_mapping_config()["mappings"][0]] * 2},
    ],
    ids=["unknown-secret-field", "bool-schema", "duplicate-provider"],
)
def test_host_mapping_config_rejects_ambiguous_or_secret_fields(tmp_path, config):
    mapping_file = tmp_path / "invalid.json"
    mapping_file.write_text(json.dumps(config), encoding="utf-8")

    with pytest.raises(DockerCredentialDeliveryError, match="mapping-config-invalid"):
        load_source_mappings(mapping_file)


def test_host_mapping_config_is_bounded_and_never_echoes_contents(tmp_path):
    mapping_file = tmp_path / "large.json"
    mapping_file.write_bytes(b"x" * (1024 * 1024 + 1))

    with pytest.raises(DockerCredentialDeliveryError, match="mapping-config-invalid"):
        load_source_mappings(mapping_file)


def test_host_mapping_config_rejects_duplicate_json_fields(tmp_path):
    mapping_file = tmp_path / "duplicate.json"
    mapping_file.write_text('{"schema":1,"schema":1,"mappings":[]}', encoding="utf-8")

    with pytest.raises(DockerCredentialDeliveryError, match="mapping-config-invalid"):
        load_source_mappings(mapping_file)


def test_host_mapping_config_sanitizes_excessive_json_nesting(tmp_path):
    mapping_file = tmp_path / "nested.json"
    mapping_file.write_text(
        '{"schema":1,"mappings":' + "[" * 2000 + "]" * 2000 + "}",
        encoding="utf-8",
    )

    with pytest.raises(DockerCredentialDeliveryError, match="mapping-config-invalid"):
        load_source_mappings(mapping_file)


def test_host_delivery_refuses_empty_source_mapping_before_docker_or_resolver():
    runner = FakeDockerRunner()
    resolver_calls = []
    delivery = DockerCredentialDelivery(runner=runner, resolver=lambda *_args: resolver_calls.append(True))

    with pytest.raises(DockerCredentialDeliveryError, match="provider-not-allowed"):
        delivery.deliver(CONTAINER_ID, "openai")

    assert runner.calls == []
    assert resolver_calls == []


@pytest.mark.parametrize(
    "reference",
    [
        "op://SyntheticVault/SyntheticItem",
        "op://SyntheticVault/SyntheticItem/api-key?include=details",
        "op://SyntheticVault@other/SyntheticItem/api-key",
        "https://example.invalid/SyntheticItem/api-key",
    ],
    ids=["whole-item", "query", "authority", "wrong-scheme"],
)
def test_source_mapping_requires_one_explicit_secret_field(reference):
    with pytest.raises(DockerCredentialDeliveryError, match="reference-invalid"):
        SourceMapping(
            "openai",
            reference,
            "openai",
            ROOT_ID,
            CONTAINER_ID,
            IMAGE_ID,
            "e" * 40,
            SOURCE_SHA256,
            "synthetic-ext4",
        )


@pytest.mark.parametrize(
    "runner_options",
    [{"remote": True}, {"invalid_mount": True}],
    ids=["remote-daemon", "host-bind-root"],
)
def test_host_target_denial_precedes_resolver(runner_options):
    runner = FakeDockerRunner(**runner_options)
    resolver_calls = []
    delivery = DockerCredentialDelivery(
        runner=runner,
        resolver=lambda *_args: resolver_calls.append(True),
        source_mappings=_mapping(),
    )

    with pytest.raises(DockerCredentialDeliveryError):
        delivery.deliver(CONTAINER_ID, "openai")

    assert resolver_calls == []
    assert all(SENTINEL not in " ".join(args) for args, _kwargs in runner.calls)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("Privileged", True),
        ("ReadonlyRootfs", False),
        ("NetworkMode", "bridge"),
        ("CapDrop", []),
        ("CapAdd", ["SYS_ADMIN"]),
        ("SecurityOpt", ["no-new-privileges:false"]),
        ("PidMode", "host"),
        ("IpcMode", "host"),
        ("Devices", [{"PathOnHost": "/dev/synthetic"}]),
    ],
)
def test_host_target_rejects_unapproved_runtime_capabilities_before_resolution(field, value):
    runner = FakeDockerRunner(host_config_overrides={field: value})
    resolver_calls = []
    delivery = DockerCredentialDelivery(
        runner=runner,
        resolver=lambda *_args: resolver_calls.append(True),
        source_mappings=_mapping(),
        environment={},
    )

    with pytest.raises(DockerCredentialDeliveryError, match="target-invalid"):
        delivery.deliver(CONTAINER_ID, "openai")

    assert resolver_calls == []
    assert runner.publish_count == 0
    assert not any(args[:2] == ("docker", "exec") for args, _kwargs in runner.calls)


def test_host_mapping_binds_exact_root_and_container_before_resolution():
    runner = FakeDockerRunner(root_id="e" * 64)
    resolver_calls = []
    delivery = DockerCredentialDelivery(
        runner=runner,
        resolver=lambda *_args: resolver_calls.append(True),
        source_mappings=_mapping(),
        environment={},
    )

    with pytest.raises(DockerCredentialDeliveryError, match="target-status-invalid"):
        delivery.deliver(CONTAINER_ID, "openai")

    assert resolver_calls == []
    assert runner.publish_count == 0

    wrong_target = DockerCredentialDelivery(
        runner=FakeDockerRunner(),
        resolver=lambda *_args: resolver_calls.append(True),
        source_mappings={
            "openai": SourceMapping(
                "openai",
                "op://SyntheticVault/SyntheticItem/api-key",
                "openai",
                ROOT_ID,
                "f" * 64,
                IMAGE_ID,
                "e" * 40,
                SOURCE_SHA256,
                "synthetic-ext4",
            )
        },
        environment={},
    )
    with pytest.raises(DockerCredentialDeliveryError, match="target-not-allowed"):
        wrong_target.deliver(CONTAINER_ID, "openai")
    assert resolver_calls == []


def test_host_delivery_uses_private_stdin_and_only_selected_fake_consumer_receives_value():
    runner = FakeDockerRunner()
    resolver_calls = []

    def resolver(reference, timeout):
        resolver_calls.append((reference, timeout))
        return SENTINEL

    delivery = DockerCredentialDelivery(
        runner=runner,
        resolver=resolver,
        source_mappings=_mapping(),
        environment={},
    )
    result = delivery.deliver(CONTAINER_ID, "openai")
    capture = runner.store.capture("openai", destination="openai")

    assert result.state == "available"
    assert result.generation == 1
    assert resolver_calls and resolver_calls[0][0] == "op://SyntheticVault/SyntheticItem/api-key"
    assert runner.store.value_for_dispatch(capture, destination="openai") == SENTINEL
    assert all(SENTINEL not in " ".join(args) for args, _kwargs in runner.calls)
    assert all("input" not in kwargs or SENTINEL.encode() not in kwargs["input"] or args[1] == "exec" for args, kwargs in runner.calls)
    assert all(kwargs.get("capture_output") is True for _args, kwargs in runner.calls)
    assert all(kwargs.get("timeout", 61) <= 60 for _args, kwargs in runner.calls)
    assert SENTINEL not in repr(result)


def test_host_child_processes_do_not_inherit_secret_environment_variables():
    runner = FakeDockerRunner()
    delivery = DockerCredentialDelivery(
        runner=runner,
        resolver=lambda *_args: SENTINEL,
        source_mappings=_mapping(),
        environment={
            "PATH": "C:/Windows/System32",
            "OPENAI_API_KEY": "synthetic-api-key",
            "CUSTOM_SECRET": "synthetic-custom-secret",
            "SAFE_SETTING": "safe",
        },
    )

    delivery.deliver(CONTAINER_ID, "openai")

    assert runner.calls
    for _args, kwargs in runner.calls:
        assert kwargs["env"] == {
            "PATH": "C:/Windows/System32",
            "SAFE_SETTING": "safe",
        }


def test_target_rejects_op_session_environment_before_resolver():
    runner = FakeDockerRunner(extra_container_env=["OP_SESSION_account=synthetic-session"])
    resolver_calls = []
    delivery = DockerCredentialDelivery(
        runner=runner,
        resolver=lambda *_args: resolver_calls.append(True),
        source_mappings=_mapping(),
        environment={},
    )

    with pytest.raises(DockerCredentialDeliveryError, match="target-invalid"):
        delivery.deliver(CONTAINER_ID, "openai")

    assert resolver_calls == []


def test_target_rejects_invalid_provider_allowlist_before_resolver():
    runner = FakeDockerRunner(runtime_providers="synthetic-secret")
    resolver_calls = []
    delivery = DockerCredentialDelivery(
        runner=runner,
        resolver=lambda *_args: resolver_calls.append(True),
        source_mappings=_mapping(),
        environment={},
    )

    with pytest.raises(DockerCredentialDeliveryError, match="target-invalid"):
        delivery.deliver(CONTAINER_ID, "openai")

    assert resolver_calls == []


def test_default_resolver_bounds_stdout_and_filters_child_environment(monkeypatch):
    observed = {}
    monkeypatch.setattr(
        docker_delivery,
        "_resolve_host_executable",
        lambda *_args, **_kwargs: "C:/op.exe",
    )

    def run(args, **kwargs):
        observed["args"] = args
        observed["env"] = kwargs["env"]
        observed["stdin"] = kwargs["stdin"]
        return subprocess.CompletedProcess(args, 0, stdout=b"x" * (16 * 1024 + 1), stderr=b"")

    monkeypatch.setattr(docker_delivery.subprocess, "run", run)
    with pytest.raises(DockerCredentialDeliveryError, match="invalid-value"):
        docker_delivery._resolve_op_reference(
            "op://SyntheticVault/SyntheticItem/api-key",
            1.0,
            environment={
                "OPENAI_API_KEY": "synthetic-key",
                "SAFE_SETTING": "safe",
                "OP_BIOMETRIC_UNLOCK_ENABLED": "true",
                "OP_SESSION_synthetic": "never-forward",
            },
        )

    assert observed["env"] == {
        "SAFE_SETTING": "safe",
        "OP_BIOMETRIC_UNLOCK_ENABLED": "true",
    }
    assert observed["stdin"] is None
    assert observed["args"][-1] == "op://SyntheticVault/SyntheticItem/api-key"


def test_op_resolution_ignores_working_directory_executable(tmp_path, monkeypatch):
    from pathlib import Path

    working = tmp_path / "working"
    trusted = tmp_path / "trusted"
    working.mkdir()
    trusted.mkdir()
    (working / "op.exe").write_bytes(b"not-executable")
    (trusted / "op.exe").write_bytes(b"not-executable")
    monkeypatch.chdir(working)
    monkeypatch.setenv("PATH", str(trusted))
    observed = {}

    def run(args, **kwargs):
        observed["args"] = args
        return subprocess.CompletedProcess(args, 0, stdout=b"synthetic-value", stderr=b"")

    monkeypatch.setattr(docker_delivery.subprocess, "run", run)
    docker_delivery._resolve_op_reference(
        "op://SyntheticVault/SyntheticItem/api-key",
        1.0,
        environment={"PATH": str(trusted)},
    )

    assert Path(observed["args"][0]).resolve() == (trusted / "op.exe").resolve()


def test_docker_cli_uses_absolute_executable_outside_working_directory(tmp_path, monkeypatch):
    import os
    import time
    from pathlib import Path

    working = tmp_path / "working"
    trusted = tmp_path / "trusted"
    working.mkdir()
    trusted.mkdir()
    (working / "docker.exe").write_bytes(b"not-executable")
    (trusted / "docker.exe").write_bytes(b"not-executable")
    monkeypatch.chdir(working)
    monkeypatch.setenv("PATH", str(trusted))
    observed = {}

    def run(args, **kwargs):
        observed["args"] = args
        return subprocess.CompletedProcess(args, 0, stdout=b"", stderr=b"")

    monkeypatch.setattr(docker_delivery.subprocess, "run", run)
    delivery = DockerCredentialDelivery(environment={"PATH": os.environ["PATH"]})
    delivery._run(
        ["docker", "version"],
        time.monotonic() + 2,
        error_code="docker-unavailable",
    )

    assert Path(observed["args"][0]).resolve() == (trusted / "docker.exe").resolve()


def test_invalid_container_type_returns_sanitized_delivery_error():
    delivery = DockerCredentialDelivery(
        runner=FakeDockerRunner(),
        resolver=lambda *_args: SENTINEL,
        source_mappings=_mapping(),
        environment={},
    )

    with pytest.raises(DockerCredentialDeliveryError, match="target-invalid"):
        delivery.deliver(None, "openai")


@pytest.mark.parametrize(
    "value",
    ["", " ", "line\nbreak", "line\x00break", "x" * (16 * 1024 + 1)],
    ids=["empty", "blank", "newline", "nul", "oversized"],
)
def test_invalid_resolver_output_never_reaches_docker_publication(value):
    runner = FakeDockerRunner()
    delivery = DockerCredentialDelivery(
        runner=runner,
        resolver=lambda *_args: value,
        source_mappings=_mapping(),
        environment={},
    )

    with pytest.raises(DockerCredentialDeliveryError, match="invalid-value") as caught:
        delivery.deliver(CONTAINER_ID, "openai")

    assert SENTINEL not in repr(caught.value)
    assert runner.publish_count == 0


def test_resolver_failures_are_sanitized_and_never_fall_back():
    runner = FakeDockerRunner()

    def failed_resolver(*_args):
        raise RuntimeError(f"private stderr {SENTINEL}")

    delivery = DockerCredentialDelivery(
        runner=runner,
        resolver=failed_resolver,
        source_mappings=_mapping(),
        environment={},
    )

    with pytest.raises(DockerCredentialDeliveryError, match="credential-resolution-failed") as caught:
        delivery.deliver(CONTAINER_ID, "openai")

    assert SENTINEL not in repr(caught.value)
    assert runner.publish_count == 0


def test_host_rejects_conflicting_auth_and_never_resolves_or_retries_lost_ack():
    conflicted = FakeDockerRunner()
    resolver_calls = []
    with pytest.raises(DockerCredentialDeliveryError, match="ambiguous-authentication"):
        DockerCredentialDelivery(
            runner=conflicted,
            resolver=lambda *_args: resolver_calls.append(True),
            source_mappings=_mapping(),
            environment={"OP_SERVICE_ACCOUNT_TOKEN": "synthetic-token"},
        ).deliver(CONTAINER_ID, "openai")
    assert conflicted.calls == []
    assert resolver_calls == []

    legacy_session = FakeDockerRunner()
    with pytest.raises(DockerCredentialDeliveryError, match="ambiguous-authentication"):
        DockerCredentialDelivery(
            runner=legacy_session,
            resolver=lambda *_args: resolver_calls.append(True),
            source_mappings=_mapping(),
            environment={"OP_SESSION_account": "synthetic-session"},
        ).deliver(CONTAINER_ID, "openai")
    assert legacy_session.calls == []
    assert resolver_calls == []

    lost_ack = FakeDockerRunner(lose_publish_ack=True)
    with pytest.raises(DockerCredentialDeliveryError, match="delivery-outcome-unknown") as caught:
        DockerCredentialDelivery(
            runner=lost_ack,
            resolver=lambda *_args: SENTINEL,
            source_mappings=_mapping(),
            environment={},
        ).deliver(CONTAINER_ID, "openai")
    assert lost_ack.publish_count == 1
    assert caught.value.reconciliation_state == "available"
    assert caught.value.reconciliation_generation == 1


def test_publish_timeout_reserves_deadline_for_status_reconciliation():
    clock = [0.0]

    class DeadlineRunner(FakeDockerRunner):
        def __call__(self, args, **kwargs):
            if args[:2] == ["docker", "exec"]:
                request = read_delivery_frame(io.BytesIO(kwargs["input"]))
                if request.action == "publish":
                    self.calls.append((tuple(args), dict(kwargs)))
                    self.server.handle(request)
                    self.publish_count += 1
                    clock[0] += kwargs["timeout"]
                    raise subprocess.TimeoutExpired(args, kwargs["timeout"])
            return super().__call__(args, **kwargs)

    runner = DeadlineRunner()
    delivery = DockerCredentialDelivery(
        runner=runner,
        resolver=lambda *_args: SENTINEL,
        source_mappings=_mapping(),
        environment={},
        timeout_seconds=60,
        clock=lambda: clock[0],
    )
    with pytest.raises(DockerCredentialDeliveryError, match="delivery-outcome-unknown") as caught:
        delivery.deliver(CONTAINER_ID, "openai")

    actions = [read_delivery_frame(io.BytesIO(call[1]["input"])).action for call in runner.calls if call[0][:2] == ("docker", "exec")]
    assert actions.count("publish") == 1
    assert actions.count("status") == 2
    assert caught.value.reconciliation_state == "available"
    assert caught.value.reconciliation_generation == 1


def test_receiver_post_send_outcome_unknown_triggers_host_status_reconciliation():
    class NoReplyRunner(FakeDockerRunner):
        def __call__(self, args, **kwargs):
            if args[:2] == ["docker", "exec"]:
                request = read_delivery_frame(io.BytesIO(kwargs["input"]))
                if request.action == "publish":
                    self.calls.append((tuple(args), dict(kwargs)))
                    self.publish_count += 1
                    self.server.handle(request)
                    reply = DeliveryReply(
                        "denied",
                        0,
                        request.provider_id,
                        request.destination,
                        reason_code="delivery-outcome-unknown",
                    )
                    return subprocess.CompletedProcess(
                        args,
                        2,
                        stdout=encode_delivery_reply(reply),
                        stderr=b"",
                    )
            return super().__call__(args, **kwargs)

    runner = NoReplyRunner()
    with pytest.raises(DockerCredentialDeliveryError, match="delivery-outcome-unknown") as caught:
        DockerCredentialDelivery(
            runner=runner,
            resolver=lambda *_args: SENTINEL,
            source_mappings=_mapping(),
            environment={},
        ).deliver(CONTAINER_ID, "openai")

    requests = [read_delivery_frame(io.BytesIO(call[1]["input"])) for call in runner.calls if call[0][:2] == ("docker", "exec")]
    assert [request.action for request in requests].count("publish") == 1
    assert [request.action for request in requests].count("status") == 2
    assert runner.publish_count == 1
    assert caught.value.reconciliation_state == "available"
    assert caught.value.reconciliation_generation == 1


@pytest.mark.parametrize(
    "name",
    ["DOCKER_HOST", "DOCKER_CONTEXT", "DOCKER_TLS_VERIFY", "DOCKER_CERT_PATH", "DOCKER_CONFIG"],
)
def test_docker_cli_overrides_fail_closed_before_any_inspection(name):
    runner = FakeDockerRunner()
    resolver_calls = []
    delivery = DockerCredentialDelivery(
        runner=runner,
        resolver=lambda *_args: resolver_calls.append(True),
        source_mappings=_mapping(),
        environment={name: "synthetic-override"},
    )

    with pytest.raises(DockerCredentialDeliveryError, match="ambiguous-docker-configuration"):
        delivery.deliver(CONTAINER_ID, "openai")

    assert runner.calls == []
    assert resolver_calls == []
