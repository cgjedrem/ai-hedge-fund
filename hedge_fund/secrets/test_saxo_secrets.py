from types import SimpleNamespace

import pytest

from hedge_fund.brokers.factory import build_broker


def test_startup_reports_missing_reference_variable_without_value(tmp_path):
    deployed = SimpleNamespace(broker="saxo", spec=SimpleNamespace(broker="saxo"))
    environment = {
        "SAXO_APP_KEY_REF": "op://private-vault/private-item/private-key",
        "SAXO_APP_SECRET_REF": "op://private-vault/private-item/private-secret",
    }

    with pytest.raises(ValueError) as error:
        build_broker(deployed, directory=tmp_path / "saxo", environ=environment)
    assert "SAXO_REFRESH_TOKEN_REF" in str(error.value)
    assert "private" not in str(error.value)
