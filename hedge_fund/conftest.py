"""Install isolated test defaults before application imports."""

import os
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

from hedge_fund.test_support.network_guard import (
    child_test_environment,
    cleanup_test_root,
    configure_test_environment,
    prepare_test_output_root,
)

_REPOSITORY = Path(__file__).resolve().parent.parent
_OUTPUTS = prepare_test_output_root(_REPOSITORY / "outputs")
_TEST_ROOT = _OUTPUTS / f"spec005-test-{os.getpid()}-{uuid.uuid4().hex}"
_TEST_ROOT.mkdir(exist_ok=False)
_TEST_MARKER = _TEST_ROOT / ".test-owned"
_TEST_MARKER.write_text("test-owned\n", encoding="utf-8")
configure_test_environment(_TEST_ROOT)

from hedge_fund.features import breakpoints  # noqa: E402


def pytest_sessionfinish(session, exitstatus):
    if not cleanup_test_root(_TEST_ROOT, _TEST_MARKER):
        raise RuntimeError("test-owned home cleanup was denied")


@pytest.fixture
def owned_test_process():
    children = []

    def spawn(script: str) -> subprocess.Popen:
        process = subprocess.Popen(
            [sys.executable, "-c", script],
            cwd=_TEST_ROOT / "home",
            env=child_test_environment(),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        children.append(process)
        return process

    yield spawn

    for child in children:
        if child.poll() is None:
            child.terminate()
        try:
            child.wait(timeout=5)
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait(timeout=5)
        if child.poll() is None:
            raise RuntimeError("test-owned process did not terminate")


@pytest.fixture(autouse=True)
def _no_breakpoints_download(monkeypatch):
    """No breakpoint downloads without an injected table."""

    def refuse():
        raise RuntimeError("inject MEBreakpoints; downloads disabled")

    monkeypatch.setattr(breakpoints, "load_breakpoints", refuse)
    monkeypatch.setattr(breakpoints, "_shared", None)
