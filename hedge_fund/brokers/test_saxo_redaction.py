from hedge_fund.brokers.saxo import SaxoAuthError, TokenManager
from hedge_fund.brokers.test_saxo_doubles import FakeClock, FakeTransport


class BrokenSecrets:
    def resolve(self, variable, reference):
        raise RuntimeError("refresh-material")

    def write_back(self, variable, reference, value):
        raise AssertionError


def test_failed_refresh_does_not_disclose_credentials_in_errors_or_repr(caplog):
    manager = TokenManager(
        app_key="app-key-private",
        app_secret="app-secret-private",
        refresh_token_ref="op://vault/item/refresh-private",
        secrets_provider=BrokenSecrets(),
        transport=FakeTransport(),
        clock=FakeClock(),
    )

    try:
        manager.get_access_token()
    except SaxoAuthError as error:
        assert "app-secret-private" not in str(error)
        assert "refresh-private" not in str(error)
    assert "app-secret-private" not in caplog.text
    assert "refresh-material" not in caplog.text
    assert "app-secret-private" not in repr(manager)
    assert "refresh-private" not in repr(manager)
