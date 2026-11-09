import io
import json
import subprocess

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
from hedge_fund.runtime.external_credentials import RuntimeCredentialLeaseStore
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
    ):
        self.store = RuntimeCredentialLeaseStore(
            root_id=root_id,
            instance_id=INSTANCE_ID,
            allowed_destinations={"openai": "openai"},
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
            body = [
                {
                    "Id": CONTAINER_ID,
                    "Image": IMAGE_ID,
                    "State": {"Status": "running", "StartedAt": "2026-11-09T10:00:00Z"},
                    "Config": {
                        "Entrypoint": ["aihf-web-supervisor", "--root", "/data"],
                        "Labels": {
                            "com.docker.compose.service": "web-operator",
                            "org.opencontainers.image.revision": "e" * 40,
                            "org.opencontainers.image.source-sha256": SOURCE_SHA256,
                        },
                        "Env": [
                            "HEDGE_FUND_DATA_PROVIDER=yfinance",
                            "HEDGE_FUND_RUNTIME_ROLE=web-operator",
                            f"HEDGE_FUND_RUNTIME_PROVIDERS={self.runtime_providers}",
                        ]
                        + self.extra_container_env,
                        "User": "",
                    },
                    "HostConfig": self.host_config,
                    "Mounts": [mount],
                }
            ]
            return subprocess.CompletedProcess(args, 0, stdout=json.dumps(body).encode(), stderr=b"")
        if args[:3] == ["docker", "volume", "inspect"]:
            body = [
                {
                    "Name": "synthetic-ext4",
                    "Driver": "local",
                    "Scope": "local",
                    "CreatedAt": "2026-11-09T10:00:00Z",
                }
            ]
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
