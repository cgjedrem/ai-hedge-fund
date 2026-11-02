"""Apply test isolation before Python child imports."""

from __future__ import annotations

import os

if os.environ.get("HEDGE_FUND_TEST_MODE") == "1":
    try:
        from network_guard import configure_test_child

        configure_test_child()
    except BaseException:
        try:
            os.write(2, b"test isolation initialization failed\n")
        finally:
            os._exit(70)
