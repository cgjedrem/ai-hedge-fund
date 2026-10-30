"""Local React trading desk API."""

__all__ = ["create_app"]


def create_app(*args, **kwargs):
    """Load optional web dependencies only when requested."""
    from hedge_fund.web.app import create_app as factory

    return factory(*args, **kwargs)
