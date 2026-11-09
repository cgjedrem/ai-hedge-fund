from pathlib import Path

import yaml


def test_opt_in_operator_compose_uses_named_volume_without_host_exposure():
    compose_path = Path(__file__).resolve().parents[2] / "docker-compose.op-runtime.yml"
    config = yaml.safe_load(compose_path.read_text(encoding="utf-8"))
    service = config["services"]["web-operator"]

    assert config["name"] == "${AIHF_OP_RUNTIME_PROJECT:?Set a unique AIHF_OP_RUNTIME_PROJECT}"
    assert service["profiles"] == ["op-runtime"]
    assert service["network_mode"] == "none"
    assert "ports" not in service
    assert "env_file" not in service
    assert "secrets" not in service
    assert service["volumes"] == ["operator-data:/data"]
    assert service["image"] == "${AIHF_OP_RUNTIME_IMAGE:?Set a unique AIHF_OP_RUNTIME_IMAGE}"
    assert service["environment"]["HEDGE_FUND_RUNTIME_ROLE"] == "web-operator"
    assert set(service["environment"]) == {
        "HEDGE_FUND_DATA_PROVIDER",
        "HEDGE_FUND_LLM_ENDPOINT",
        "HEDGE_FUND_RUNTIME_ROLE",
        "HEDGE_FUND_RUNTIME_PROVIDERS",
    }
    assert service["environment"]["HEDGE_FUND_RUNTIME_PROVIDERS"] == "${HEDGE_FUND_RUNTIME_PROVIDERS:-}"
    assert service["read_only"] is True
    assert service["cap_drop"] == ["ALL"]
    assert service["security_opt"] == ["no-new-privileges:true"]
    assert service["tmpfs"] == ["/tmp"]
    assert service["command"] == [
        "--port",
        "8876",
        "--enable-writes-after-trust",
        "--enable-network-after-trust",
    ]
    assert config["volumes"]["operator-data"]["name"] == "${AIHF_OP_RUNTIME_VOLUME:?Set a unique AIHF_OP_RUNTIME_VOLUME}"
