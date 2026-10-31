"""Verify test processes cannot reach user state or external providers."""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import uuid
from pathlib import Path

import pytest
from dotenv import dotenv_values

from hedge_fund.llm import PROVIDER_ENV_VARS
from hedge_fund.test_support import network_guard
from hedge_fund.test_support.network_guard import (
    child_test_environment,
    cleanup_test_root,
    CREDENTIAL_ENV_VARS,
    PROXY_ENV_VARS,
)
from hedge_fund.web.services import DeskService, ServiceError


def test_pytest_process_uses_checkout_owned_home() -> None:
    repository = Path(__file__).resolve().parents[1]
    outputs = (repository / "outputs").resolve()
    home = Path.home().resolve()

    assert os.environ.get("HEDGE_FUND_TEST_MODE") == "1"
    assert os.environ.get("PYTHON_DOTENV_DISABLED") == "1"
    assert home.is_relative_to(outputs)
    assert Path(os.environ.get("USERPROFILE", "")).resolve() == home
    assert Path(os.environ.get("TEMP", "")).resolve().is_relative_to(outputs)
    assert Path(os.environ.get("TMP", "")).resolve().is_relative_to(outputs)


def test_provider_credentials_and_proxy_settings_are_cleared() -> None:
    remaining_credentials = set(CREDENTIAL_ENV_VARS).intersection(os.environ)
    remaining_proxies = set(PROXY_ENV_VARS).intersection(os.environ)
    provider_vars = set(PROVIDER_ENV_VARS.values())
    missing_provider_vars = provider_vars.difference(CREDENTIAL_ENV_VARS)
    assert not remaining_credentials, "provider env vars remain"
    assert not remaining_proxies, "proxy env vars remain"
    assert not missing_provider_vars, missing_provider_vars


def test_external_socket_connect_is_denied_before_io() -> None:
    connect = socket.socket.connect
    assert getattr(connect, "__hedge_fund_test_network_guard__", False)

    with socket.socket() as connection:
        with pytest.raises(AssertionError, match="external network disabled"):
            connection.connect(("203.0.113.1", 443))


def test_dotenv_is_disabled_for_test_owned_child(tmp_path: Path) -> None:
    parent = tmp_path / "parent"
    child = parent / "child"
    child.mkdir(parents=True)
    (parent / ".env").write_text(
        "AIHF_TEST_PARENT_SENTINEL=must-not-load\n",
        encoding="utf-8",
    )
    (child / ".env").write_text(
        "AIHF_TEST_DOTENV_SENTINEL=must-not-load\n",
        encoding="utf-8",
    )
    probe = "; ".join(
        (
            "import os",
            "from dotenv import load_dotenv",
            "load_dotenv()",
            "assert os.environ.get('PYTHON_DOTENV_DISABLED') == '1'",
            "assert 'AIHF_TEST_DOTENV_SENTINEL' not in os.environ",
            "assert 'AIHF_TEST_PARENT_SENTINEL' not in os.environ",
        )
    )
    env = child_test_environment()

    result = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=child,
        env=env,
        capture_output=True,
        check=False,
        text=True,
        timeout=10,
    )

    assert result.returncode == 0, result.stderr
    assert "must-not-load" not in result.stdout + result.stderr


def test_dotenv_values_reject_paths_outside_test_root() -> None:
    filename = f"spec005-denied-{uuid.uuid4().hex}.env"
    outside = Path(os.environ["HEDGE_FUND_TEST_ROOT"]).parent / filename
    unc_path = Path(r"\\203.0.113.1\share\ignored.env")
    error_message = "test dotenv path denied"

    for path in (outside, unc_path):
        with pytest.raises(AssertionError, match=error_message):
            dotenv_values(path)


def test_dotenv_values_reject_unc_before_filesystem_access(
    monkeypatch,
) -> None:
    root = Path(os.environ["HEDGE_FUND_TEST_ROOT"]).resolve()
    original = network_guard._is_reparse_point

    def deny_outside(path: Path) -> bool:
        candidate = Path(os.path.abspath(os.fspath(path)))
        if not candidate.is_relative_to(root):
            raise AssertionError("filesystem access escaped test root")
        return original(candidate)

    monkeypatch.setattr(network_guard, "_is_reparse_point", deny_outside)
    unc_path = Path(r"\\203.0.113.1\share\ignored.env")

    with pytest.raises(
        AssertionError,
        match="test dotenv path denied",
    ):
        dotenv_values(unc_path)


def test_dotenv_values_allow_explicit_test_root_file(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("AIHF_TEST_KEY=synthetic-value\n", encoding="utf-8")

    assert dotenv_values(env_file) == {"AIHF_TEST_KEY": "synthetic-value"}


def test_child_environment_rejects_boundary_overrides() -> None:
    with pytest.raises(ValueError, match="child environment override denied"):
        child_test_environment({"HOME": "C:\\untrusted"})
    with pytest.raises(ValueError, match="child environment override denied"):
        child_test_environment({"PYTHONPATH": "C:\\untrusted"})
    error_message = "child environment values must be strings"
    with pytest.raises(TypeError, match=error_message):
        child_test_environment({"AIHF_TEST_INVALID": 1})


def test_cleanup_rejects_unc_before_filesystem_access(monkeypatch) -> None:
    outputs = Path(__file__).resolve().parents[1] / "outputs"
    original = network_guard._is_reparse_point

    def deny_outside(path: Path) -> bool:
        candidate = Path(os.path.abspath(os.fspath(path)))
        if not candidate.is_relative_to(outputs):
            raise AssertionError("filesystem access escaped checkout outputs")
        return original(candidate)

    monkeypatch.setattr(network_guard, "_is_reparse_point", deny_outside)
    unc_root = Path(r"\\203.0.113.1\share\spec005-test-outside")

    assert cleanup_test_root(unc_root, unc_root / ".test-owned") is False


def test_spawned_python_inherits_network_and_credential_guards(
    tmp_path: Path,
) -> None:
    probe = """\
import os
import socket

assert os.environ.get("HEDGE_FUND_TEST_MODE") == "1"
assert os.environ.get("PYTHON_DOTENV_DISABLED") == "1"
assert os.environ.get("PYTHONDONTWRITEBYTECODE") == "1"
assert "OPENAI_API_KEY" not in os.environ
assert "HTTP_PROXY" not in os.environ
assert getattr(
    socket.socket.connect,
    "__hedge_fund_test_network_guard__",
    False,
)
from pathlib import Path

test_root = Path(os.environ["HEDGE_FUND_TEST_ROOT"])
assert Path.home().resolve().is_relative_to(test_root.resolve())
import hedge_fund.web.services

sock = socket.socket()
try:
    sock.connect(("203.0.113.2", 443))
except AssertionError:
    pass
else:
    raise SystemExit(3)
finally:
    sock.close()
print("isolated")
"""
    env = child_test_environment(
        {
            "OPENAI_API_KEY": "synthetic-test-sentinel",
            "HTTP_PROXY": "http://127.0.0.1:8123",
        }
    )

    result = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        check=False,
        text=True,
        timeout=10,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "isolated"
    assert "synthetic-test-sentinel" not in result.stdout + result.stderr


@pytest.mark.parametrize(
    "name",
    [
        "watchtower",
        "watchtower-weekly",
        "umbrella",
        "WATCHTOWER",
        "watchtower.",
    ],
)
def test_protected_name_aliases_are_denied_before_storage_access(
    name: str,
    tmp_path: Path,
) -> None:
    service = DeskService(root=tmp_path, allow_writes=True)
    try:
        with pytest.raises(ServiceError) as error:
            service._guard_protected(name)
        assert error.value.status_code == 403
    finally:
        service.close()


def test_test_root_cleanup_refuses_nested_fixture_paths(
    tmp_path: Path,
) -> None:
    nested_root = tmp_path / f"spec005-test-cleanup-{uuid.uuid4().hex}"
    nested_root.mkdir()
    marker = nested_root / ".test-owned"
    marker.write_text("test-owned\n", encoding="utf-8")
    sentinel = nested_root / "sentinel.txt"
    sentinel.write_text("retained", encoding="utf-8")

    assert cleanup_test_root(nested_root, marker) is False
    assert sentinel.read_text(encoding="utf-8") == "retained"


def test_cleanup_removes_marked_direct_test_root(request) -> None:
    outputs = Path(os.environ["HEDGE_FUND_TEST_ROOT"]).parent
    test_root = outputs / f"spec005-test-cleanup-{uuid.uuid4().hex}"
    test_root.mkdir()
    marker = test_root / ".test-owned"
    marker.write_text("test-owned\n", encoding="utf-8")

    def remove_root() -> None:
        if test_root.exists():
            cleanup_test_root(test_root, marker)

    request.addfinalizer(remove_root)
    (test_root / "synthetic.txt").write_text("synthetic", encoding="utf-8")

    assert cleanup_test_root(test_root, marker) is True
    assert not test_root.exists()


def test_cleanup_unlinks_directory_symlink_without_following_target(
    request,
) -> None:
    outputs = Path(os.environ["HEDGE_FUND_TEST_ROOT"]).parent
    test_root = outputs / f"spec005-test-link-{uuid.uuid4().hex}"
    target_root = outputs / f"spec005-test-target-{uuid.uuid4().hex}"
    test_root.mkdir()
    target_root.mkdir()
    marker = test_root / ".test-owned"
    target_marker = target_root / ".test-owned"
    marker.write_text("test-owned\n", encoding="utf-8")
    target_marker.write_text("test-owned\n", encoding="utf-8")

    def remove_target_root() -> None:
        if target_root.exists():
            cleanup_test_root(target_root, target_marker)

    def remove_test_root() -> None:
        if test_root.exists():
            cleanup_test_root(test_root, marker)

    request.addfinalizer(remove_target_root)
    request.addfinalizer(remove_test_root)
    sentinel = target_root / "sentinel.txt"
    sentinel.write_text("synthetic", encoding="utf-8")
    link = test_root / "linked-target"
    try:
        link.symlink_to(target_root, target_is_directory=True)
    except (NotImplementedError, OSError):
        assert cleanup_test_root(test_root, marker)
        assert cleanup_test_root(target_root, target_marker)
        pytest.skip("directory symlinks unavailable")

    assert cleanup_test_root(test_root, marker) is True
    assert sentinel.read_text(encoding="utf-8") == "synthetic"
    assert cleanup_test_root(target_root, target_marker) is True


def test_owned_process_fixture_reaps_exact_launched_child(
    owned_test_process,
) -> None:
    child = owned_test_process("import time; time.sleep(60)")
    assert child.poll() is None, "test child did not remain alive for cleanup"
