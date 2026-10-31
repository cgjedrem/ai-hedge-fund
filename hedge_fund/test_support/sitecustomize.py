"""Apply test isolation before Python child imports."""

from __future__ import annotations

import os

if os.environ.get("HEDGE_FUND_TEST_MODE") == "1":
    from network_guard import configure_test_child

    configure_test_child()
