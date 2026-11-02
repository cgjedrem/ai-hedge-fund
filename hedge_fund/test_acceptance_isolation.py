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
    guarded_test_python_command,
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
        guarded_test_python_command("-c", probe),
        cwd=child,
        env=env,
        capture_output=True,
        check=False,
        text=True,
        timeout=10,
    )

    assert result.returncode == 0, result.stderr
    assert "must-not-load" not in result.stdout + result.stderr


@pytest.mark.parametrize("failure", ["missing-hook", "hook-exception", "hook-syntax", "missing-mode"])
def test_owned_python_child_refuses_an_unavailable_site_hook(tmp_path: Path, failure: str) -> None:
    env = child_test_environment()
    env["OPENAI_API_KEY"] = "synthetic-should-never-be-printed"
    if failure == "missing-mode":
        env.pop("HEDGE_FUND_TEST_MODE")
    else:
        support = tmp_path / "fake-support"
        support.mkdir()
        if failure == "hook-exception":
            (support / "sitecustomize.py").write_text(
                "raise RuntimeError('synthetic site hook import failure')\n",
                encoding="utf-8",
            )
        elif failure == "hook-syntax":
            (support / "sitecustomize.py").write_text("def invalid syntax\n", encoding="utf-8")
        repository = Path(__file__).resolve().parents[1]
        env["PYTHONPATH"] = os.pathsep.join((str(support), str(repository)))
    result = subprocess.run(
        guarded_test_python_command("-c", "print('CHILD_SCRIPT_RAN')"),
        cwd=tmp_path,
        env=env,
        capture_output=True,
        check=False,
        text=True,
        timeout=10,
    )

    assert result.returncode != 0
    assert "CHILD_SCRIPT_RAN" not in result.stdout + result.stderr
    assert "synthetic-should-never-be-printed" not in result.stdout + result.stderr


@pytest.mark.parametrize("failure", ["missing-hook", "hook-exception", "missing-mode"])
def test_owned_runner_child_checks_guard_before_importing_its_module(tmp_path: Path, failure: str) -> None:
    from hedge_fund.runtime.owned_runner import _runner_command
    from hedge_fund.runtime.root import RootContext

    support = tmp_path / "fake-support"
    package = support / "hedge_fund" / "runtime"
    package.mkdir(parents=True)
    (package.parent / "__init__.py").write_text("", encoding="utf-8")
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "owned_runner_child.py").write_text("print('CHILD_SCRIPT_RAN')\n", encoding="utf-8")
    if failure == "hook-exception":
        (support / "sitecustomize.py").write_text("raise RuntimeError('synthetic hook failure')\n", encoding="utf-8")
    env = child_test_environment()
    if failure == "missing-mode":
        env.pop("HEDGE_FUND_TEST_MODE")
    else:
        repository = Path(__file__).resolve().parents[1]
        env["PYTHONPATH"] = os.pathsep.join((str(support), str(repository)))
    with RootContext.open(tmp_path) as root:
        command = _runner_command(root, "synthetic")

    result = subprocess.run(
        command,
        cwd=tmp_path,
        env=env,
        capture_output=True,
        check=False,
        text=True,
        timeout=10,
    )

    assert result.returncode != 0
    assert "test isolation initialization failed" in result.stderr
    assert "CHILD_SCRIPT_RAN" not in result.stdout + result.stderr


@pytest.mark.parametrize("launcher", ["python", "owned-runner"])
def test_owned_child_rejects_partially_configured_guard(tmp_path: Path, launcher: str) -> None:
    from hedge_fund.runtime.owned_runner import _runner_command
    from hedge_fund.runtime.root import RootContext

    support = tmp_path / "partial-support"
    package = support / "hedge_fund" / "runtime"
    package.mkdir(parents=True)
    (package.parent / "__init__.py").write_text("", encoding="utf-8")
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "owned_runner_child.py").write_text("print('CHILD_SCRIPT_RAN')\n", encoding="utf-8")
    (support / "network_guard.py").write_text(
        "import socket\n"
        "def configure_test_child():\n"
        "    def denied(*args, **kwargs):\n"
        "        raise AssertionError('synthetic socket guard')\n"
        "    setattr(denied, '__hedge_fund_test_network_guard__', True)\n"
        "    for name in ('connect', 'connect_ex', 'sendto'):\n"
        "        setattr(socket.socket, name, denied)\n"
        "    for name in ('create_connection', 'getaddrinfo', 'gethostbyname', "
        "'gethostbyname_ex', 'gethostbyaddr'):\n"
        "        setattr(socket, name, denied)\n",
        encoding="utf-8",
    )
    (support / "sitecustomize.py").write_text(
        "from network_guard import configure_test_child\nconfigure_test_child()\n",
        encoding="utf-8",
    )
    env = child_test_environment()
    env["HOME"] = str(tmp_path / "wrong-home")
    env["PYTHONPATH"] = os.pathsep.join((str(support), str(Path(__file__).resolve().parents[1])))
    env["OPENAI_API_KEY"] = "synthetic-should-never-be-printed"
    if launcher == "python":
        command = guarded_test_python_command("-c", "print('CHILD_SCRIPT_RAN')")
    else:
        with RootContext.open(tmp_path) as root:
            command = _runner_command(root, "synthetic")

    result = subprocess.run(
        command,
        cwd=support,
        env=env,
        capture_output=True,
        check=False,
        text=True,
        timeout=15,
    )

    assert result.returncode != 0
    assert "test isolation initialization failed" in result.stderr
    assert "CHILD_SCRIPT_RAN" not in result.stdout + result.stderr
    assert "synthetic-should-never-be-printed" not in result.stdout + result.stderr


@pytest.mark.parametrize("launcher", ["python", "owned-runner"])
@pytest.mark.parametrize(
    "failure",
    ["missing-root", "invalid-root", "mismatched-home", "hook-import", "guard-import", "guard-setup"],
)
def test_owned_child_stops_on_canonical_hook_failures(
    tmp_path: Path,
    launcher: str,
    failure: str,
) -> None:
    from hedge_fund.runtime.owned_runner import _runner_command
    from hedge_fund.runtime.root import RootContext

    package = tmp_path / "hedge_fund" / "runtime"
    package.mkdir(parents=True)
    (package.parent / "__init__.py").write_text("", encoding="utf-8")
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "owned_runner_child.py").write_text("print('CHILD_SCRIPT_RAN')\n", encoding="utf-8")
    env = child_test_environment({"OPENAI_API_KEY": "synthetic-should-never-be-printed"})
    if failure == "missing-root":
        env.pop("HEDGE_FUND_TEST_ROOT")
    elif failure == "invalid-root":
        env["HEDGE_FUND_TEST_ROOT"] = str(tmp_path / "invalid")
    elif failure == "mismatched-home":
        env["HOME"] = str(tmp_path / "wrong-home")
    if launcher == "python":
        command = guarded_test_python_command("-c", "print('CHILD_SCRIPT_RAN')")
    else:
        with RootContext.open(tmp_path) as root:
            command = _runner_command(root, "synthetic")

    prefix = ""
    if failure in {"hook-import", "guard-import"}:
        denied = "sitecustomize" if failure == "hook-import" else "network_guard"
        prefix = (
            "import builtins\n"
            "_original_import = builtins.__import__\n"
            "def _deny_import(name, *args, **kwargs):\n"
            f"    if name == {denied!r}: raise ImportError('synthetic import failure')\n"
            "    return _original_import(name, *args, **kwargs)\n"
            "builtins.__import__ = _deny_import\n"
        )
    elif failure == "guard-setup":
        prefix = (
            "import network_guard\n"
            "def _deny_setup(): raise RuntimeError('synthetic setup failure')\n"
            "network_guard.configure_test_child = _deny_setup\n"
        )
    bootstrap_index = command.index("-c") + 1
    command[bootstrap_index] = prefix + command[bootstrap_index]

    result = subprocess.run(
        command,
        cwd=tmp_path,
        env=env,
        capture_output=True,
        check=False,
        text=True,
        timeout=15,
    )

    assert result.returncode != 0
    assert "test isolation initialization failed" in result.stderr
    assert "CHILD_SCRIPT_RAN" not in result.stdout + result.stderr
    assert "synthetic-should-never-be-printed" not in result.stdout + result.stderr


def test_owned_python_child_runs_module_only_after_guard(tmp_path: Path) -> None:
    (tmp_path / "synthetic_child.py").write_text(
        "import socket, sys\n"
        "assert getattr(socket.socket.connect, '__hedge_fund_test_network_guard__', False)\n"
        "assert sys.argv[1:] == ['expected']\n"
        "print('isolated-module')\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        guarded_test_python_command("-m", "synthetic_child", "expected"),
        cwd=tmp_path,
        env=child_test_environment(),
        capture_output=True,
        check=False,
        text=True,
        timeout=10,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "isolated-module"


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


def test_reconfiguring_dotenv_guard_uses_only_the_current_test_root(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import dotenv
    import dotenv.main

    for module in (dotenv, dotenv.main):
        for name in ("load_dotenv", "find_dotenv", "dotenv_values"):
            monkeypatch.setattr(module, name, getattr(module, name))
    old_root = tmp_path / "old"
    new_root = tmp_path / "new"
    old_root.mkdir()
    new_root.mkdir()
    (old_root / ".env").write_text("AIHF_TEST_KEY=old\n", encoding="utf-8")
    (new_root / ".env").write_text("AIHF_TEST_KEY=new\n", encoding="utf-8")

    network_guard._disable_dotenv(old_root)
    network_guard._disable_dotenv(new_root)

    assert dotenv.dotenv_values(new_root / ".env") == {"AIHF_TEST_KEY": "new"}
    with pytest.raises(AssertionError, match="test dotenv path denied"):
        dotenv.dotenv_values(old_root / ".env")


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
        guarded_test_python_command("-c", probe),
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
    "failure",
    [
        "missing-root",
        "invalid-root",
        "mismatched-home",
        "dotenv-enabled",
        "bytecode-enabled",
        "invalid-pythonpath",
        "guard-import-failure",
        "guard-setup-failure",
    ],
)
def test_python_child_stops_before_script_when_isolation_bootstrap_fails(
    tmp_path: Path,
    failure: str,
) -> None:
    env = child_test_environment(
        {
            "OPENAI_API_KEY": "synthetic-test-sentinel",
            "HTTP_PROXY": "http://127.0.0.1:8123",
        }
    )
    if failure == "missing-root":
        env.pop("HEDGE_FUND_TEST_ROOT")
    elif failure == "invalid-root":
        env["HEDGE_FUND_TEST_ROOT"] = str(tmp_path / "invalid")
    elif failure == "mismatched-home":
        env["HOME"] = str(tmp_path)
    elif failure == "dotenv-enabled":
        env["PYTHON_DOTENV_DISABLED"] = "0"
    elif failure == "bytecode-enabled":
        env["PYTHONDONTWRITEBYTECODE"] = "0"
    elif failure == "invalid-pythonpath":
        env["PYTHONPATH"] = str(Path(network_guard.__file__).parent)
    else:
        support = tmp_path / "broken-support"
        support.mkdir()
        sitecustomize = Path(network_guard.__file__).with_name("sitecustomize.py")
        (support / "sitecustomize.py").write_bytes(sitecustomize.read_bytes())
        if failure == "guard-import-failure":
            source = "raise ImportError('synthetic guard import failure')\n"
        else:
            source = "def configure_test_child():\n    raise RuntimeError('synthetic guard setup failure')\n"
        (support / "network_guard.py").write_text(source, encoding="utf-8")
        env["PYTHONPATH"] = str(support)

    result = subprocess.run(
        [sys.executable, "-c", "print('CHILD_SCRIPT_RAN')"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        check=False,
        text=True,
        timeout=10,
    )

    assert result.returncode != 0
    assert "CHILD_SCRIPT_RAN" not in result.stdout + result.stderr
    assert "synthetic-test-sentinel" not in result.stdout + result.stderr
    assert "test isolation initialization failed" in result.stderr


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
