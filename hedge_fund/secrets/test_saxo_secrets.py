from types import SimpleNamespace

import pytest

from hedge_fund.brokers.factory import build_broker
from hedge_fund.runtime.admission import OwnershipUnknown


def test_unknown_account_control_does_not_echo_supplied_secret_references(tmp_path):
    deployed = SimpleNamespace(broker="saxo", spec=SimpleNamespace(broker="saxo"))
    environment = {
        "SAXO_APP_KEY_REF": "op://private-vault/private-item/private-key",
        "SAXO_APP_SECRET_REF": "op://private-vault/private-item/private-secret",
    }

    with pytest.raises(OwnershipUnknown) as error:
        build_broker(deployed, directory=tmp_path / "saxo", environ=environment)
    assert "ownership-unknown" in str(error.value)
    for value in environment.values():
        assert value not in str(error.value)
    assert "private" not in str(error.value)
