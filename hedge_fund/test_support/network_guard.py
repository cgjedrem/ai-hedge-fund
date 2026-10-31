"""Isolate Python test processes from user state and external network."""

from __future__ import annotations

import ipaddress
import os
import socket
import stat
from pathlib import Path
from typing import Any

_GUARD = "__hedge_fund_test_network_guard__"
CREDENTIAL_ENV_VARS = (
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
    "XAI_API_KEY",
    "DEEPSEEK_API_KEY",
    "GOOGLE_API_KEY",
    "KIMI_API_KEY",
    "TYPESAFE_API_KEY",
    "MOONSHOT_API_KEY",
    "FINANCIAL_DATASETS_API_KEY",
    "SAXO_API_KEY",
    "SAXO_CLIENT_ID",
    "SAXO_CLIENT_SECRET",
    "SAXO_APP_KEY_REF",
    "SAXO_APP_SECRET_REF",
    "SAXO_REFRESH_TOKEN_REF",
    "HEDGE_FUND_LLM_MODEL",
    "HEDGE_FUND_DATA_PROVIDER",
    "HEDGE_FUND_ROOT",
    "HEDGE_FUND_HOME",
    "AIHF_ROOT",
    "OLLAMA_BASE_URL",
    "OLLAMA_NUM_CTX",
    "OLLAMA_TIMEOUT",
    "MOONSHOT_BASE_URL",
    "OPENAI_API_BASE",
    "SAXO_REFRESH_LOCK_DIR",
    "OPENROUTER_API_KEY",
    "MISTRAL_API_KEY",
    "COHERE_API_KEY",
    "GROQ_API_KEY",
    "HF_TOKEN",
    "HUGGINGFACEHUB_API_TOKEN",
    "AZURE_OPENAI_API_KEY",
)
PROXY_ENV_VARS = (
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "NO_PROXY",
    "http_proxy",
    "https_proxy",
    "all_proxy",
    "no_proxy",
)


def prepare_test_output_root(output_root: Path) -> Path:
    repository = Path(__file__).resolve().parents[2]
    expected = repository / "outputs"
    candidate = Path(output_root)
    if candidate != expected:
        raise RuntimeError("test output root must be checkout outputs")
    if _is_reparse_point(expected):
        raise RuntimeError("test output root cannot be a reparse point")
    expected.mkdir(exist_ok=True)
    if _is_reparse_point(expected):
        raise RuntimeError("test output root cannot be a reparse point")
    resolved = expected.resolve(strict=True)
    if resolved.parent != repository or resolved.name.casefold() != "outputs":
        raise RuntimeError("test output root escaped checkout")
    return resolved


def configure_test_environment(test_root: Path) -> None:
    root = _validate_test_root(test_root)
    home = root / "home"
    temporary = root / "tmp"
    home.mkdir(parents=True, exist_ok=True)
    temporary.mkdir(parents=True, exist_ok=True)

    appdata = home / "AppData" / "Roaming"
    local_appdata = home / "AppData" / "Local"
    env_values = {
        "HEDGE_FUND_TEST_MODE": "1",
        "HEDGE_FUND_TEST_ROOT": str(root),
        "PYTHON_DOTENV_DISABLED": "1",
        "HOME": str(home),
        "USERPROFILE": str(home),
        "HOMEDRIVE": home.drive,
        "HOMEPATH": str(home).removeprefix(home.drive),
        "TEMP": str(temporary),
        "TMP": str(temporary),
        "APPDATA": str(appdata),
        "LOCALAPPDATA": str(local_appdata),
        "XDG_CACHE_HOME": str(home / ".cache"),
        "XDG_CONFIG_HOME": str(home / ".config"),
        "XDG_DATA_HOME": str(home / ".local" / "share"),
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONPATH": str(Path(__file__).resolve().parent),
    }
    os.environ.update(env_values)
    import tempfile

    tempfile.tempdir = str(temporary)
    _clear_environment()
    _disable_dotenv(root)
    install_network_guard()


def configure_test_child() -> None:
    if os.environ.get("HEDGE_FUND_TEST_MODE") != "1":
        return

    root_value = os.environ.get("HEDGE_FUND_TEST_ROOT", "")
    root = _validate_test_root(Path(root_value))
    home = root / "home"
    temporary = root / "tmp"
    expected_paths = {
        "HOME": home,
        "USERPROFILE": home,
        "TEMP": temporary,
        "TMP": temporary,
        "APPDATA": home / "AppData" / "Roaming",
        "LOCALAPPDATA": home / "AppData" / "Local",
        "XDG_CACHE_HOME": home / ".cache",
        "XDG_CONFIG_HOME": home / ".config",
        "XDG_DATA_HOME": home / ".local" / "share",
    }
    for name, path in expected_paths.items():
        if not _path_matches(os.environ.get(name, ""), path):
            raise RuntimeError("test child isolation path mismatch")
    expected_homepath = str(home).removeprefix(home.drive)
    home_drive = os.path.normcase(home.drive)
    if os.path.normcase(os.environ.get("HOMEDRIVE", "")) != home_drive:
        raise RuntimeError("test child isolation path mismatch")
    home_path = os.path.normcase(expected_homepath)
    if os.path.normcase(os.environ.get("HOMEPATH", "")) != home_path:
        raise RuntimeError("test child isolation path mismatch")
    if os.environ.get("PYTHON_DOTENV_DISABLED") != "1":
        raise RuntimeError("test child dotenv must be disabled")
    if os.environ.get("PYTHONDONTWRITEBYTECODE") != "1":
        raise RuntimeError("test child bytecode writes must be disabled")
    if os.environ.get("PYTHONPATH", "") != _child_pythonpath():
        raise RuntimeError("test child import path mismatch")
    _clear_environment()
    _disable_dotenv(root)
    install_network_guard()


def child_test_environment(
    extra: dict[str, str] | None = None,
) -> dict[str, str]:
    inherited = (
        "PATH",
        "PATHEXT",
        "SYSTEMROOT",
        "WINDIR",
        "HOME",
        "USERPROFILE",
        "HOMEDRIVE",
        "HOMEPATH",
        "TEMP",
        "TMP",
        "APPDATA",
        "LOCALAPPDATA",
        "XDG_CACHE_HOME",
        "XDG_CONFIG_HOME",
        "XDG_DATA_HOME",
        "HEDGE_FUND_TEST_MODE",
        "HEDGE_FUND_TEST_ROOT",
        "PYTHON_DOTENV_DISABLED",
        "PYTHONDONTWRITEBYTECODE",
    )
    env = {name: os.environ[name] for name in inherited if name in os.environ}
    env["PYTHONPATH"] = _child_pythonpath()
    if extra is not None:
        if not isinstance(extra, dict):
            raise TypeError("child environment values must be strings")
        for name, value in extra.items():
            if not isinstance(name, str) or not isinstance(value, str):
                raise TypeError("child environment values must be strings")
        allowed = set(CREDENTIAL_ENV_VARS) | set(PROXY_ENV_VARS)
        for name in extra:
            if name in allowed or name.startswith("AIHF_TEST_"):
                continue
            raise ValueError("child environment override denied")
        env.update(extra)
    return env


def cleanup_test_root(test_root: Path, marker: Path) -> bool:
    repository = Path(__file__).resolve().parents[2]
    outputs = repository / "outputs"
    if _is_reparse_point(outputs):
        return False
    try:
        resolved_outputs = outputs.resolve(strict=True)
        root_candidate = Path(os.path.abspath(os.fspath(test_root)))
        marker_candidate = Path(os.path.abspath(os.fspath(marker)))
    except (OSError, TypeError, ValueError):
        return False
    if root_candidate.parent != resolved_outputs:
        return False
    if not root_candidate.name.startswith("spec005-test-"):
        return False
    if marker_candidate != root_candidate / ".test-owned":
        return False
    if _is_reparse_point(root_candidate):
        return False
    if _is_reparse_point(marker_candidate):
        return False
    try:
        resolved_root = root_candidate.resolve(strict=True)
        resolved_marker = marker_candidate.resolve(strict=True)
    except OSError:
        return False
    if resolved_root.parent != resolved_outputs:
        return False
    if resolved_marker.parent != resolved_root:
        return False
    if marker_candidate.read_text(encoding="utf-8") != "test-owned\n":
        return False
    _remove_test_tree(resolved_root)
    return not resolved_root.exists()


def install_network_guard() -> None:
    for name in ("connect", "connect_ex", "sendto"):
        original = getattr(socket.socket, name)
        if getattr(original, _GUARD, False):
            continue

        def guarded(sock, *args, _original=original, _name=name, **kwargs):
            address = args[0] if args else kwargs.get("address")
            if _name == "sendto":
                address = args[-1] if args else kwargs.get("address")
            is_unix = getattr(sock, "family", None) == getattr(
                socket,
                "AF_UNIX",
                object(),
            )
            if not is_unix and not _is_loopback_address(address):
                raise AssertionError("external network disabled in tests")
            return _original(sock, *args, **kwargs)

        setattr(guarded, _GUARD, True)
        setattr(socket.socket, name, guarded)

    module_names = (
        "create_connection",
        "getaddrinfo",
        "gethostbyname",
        "gethostbyname_ex",
        "gethostbyaddr",
    )
    for module_name in module_names:
        original = getattr(socket, module_name)
        if getattr(original, _GUARD, False):
            continue

        def guarded(*args, _original=original, _name=module_name, **kwargs):
            host = args[0] if args else kwargs.get("host")
            if _name == "create_connection":
                address = host
                allowed = _is_loopback_address(address)
            elif _name == "getaddrinfo":
                flags = args[5] if len(args) > 5 else kwargs.get("flags", 0)
                allowed = host is not None and _is_loopback_host(host)
                passive_flag = getattr(socket, "AI_PASSIVE", 0)
                passive = host is None and bool(flags & passive_flag)
                allowed = allowed or passive
            else:
                allowed = _is_loopback_host(host)
            if not allowed:
                raise AssertionError("external network disabled in tests")
            return _original(*args, **kwargs)

        setattr(guarded, _GUARD, True)
        setattr(socket, module_name, guarded)


def _validate_test_root(test_root: Path) -> Path:
    repository = Path(__file__).resolve().parents[2]
    outputs = repository / "outputs"
    if _is_reparse_point(outputs):
        raise RuntimeError("test output root cannot be a symlink")
    output_root = outputs.resolve(strict=True)
    candidate = Path(os.path.abspath(os.fspath(test_root)))
    if candidate.parent != output_root:
        raise RuntimeError("test root must be inside checkout outputs")
    if not candidate.name.startswith("spec005-test-"):
        raise RuntimeError("test root must be inside checkout outputs")
    if _is_reparse_point(candidate):
        raise RuntimeError("test root cannot be a symlink")
    root = candidate.resolve(strict=True)
    if root.parent != output_root:
        raise RuntimeError("test root escaped checkout outputs")
    return root


def _remove_test_tree(root: Path) -> None:
    with os.scandir(root) as entries:
        for entry in entries:
            path = Path(entry.path)
            info = entry.stat(follow_symlinks=False)
            if _is_reparse_point(path):
                if stat.S_ISDIR(info.st_mode):
                    os.rmdir(path)
                else:
                    os.unlink(path)
            elif stat.S_ISDIR(info.st_mode):
                _remove_test_tree(path)
            else:
                os.unlink(path)
    os.rmdir(root)


def _is_reparse_point(path: Path) -> bool:
    try:
        info = Path(path).lstat()
    except OSError:
        return False
    attributes = getattr(info, "st_file_attributes", 0)
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    return stat.S_ISLNK(info.st_mode) or bool(attributes & reparse_flag)


def _clear_environment() -> None:
    for name in (*CREDENTIAL_ENV_VARS, *PROXY_ENV_VARS):
        os.environ.pop(name, None)


def _disable_dotenv(test_root: Path) -> None:
    try:
        import dotenv
        import dotenv.main
    except ImportError:
        return

    root = Path(test_root).resolve(strict=True)
    original_values = dotenv.main.dotenv_values

    def disabled(*_args: Any, **_kwargs: Any) -> bool:
        return False

    def empty_path(*_args: Any, **_kwargs: Any) -> str:
        return ""

    def isolated_values(
        dotenv_path: str | os.PathLike[str] | None = None,
        *args: Any,
        **kwargs: Any,
    ) -> dict:
        if dotenv_path is None:
            raise AssertionError("implicit dotenv lookup disabled")
        if args and args[0] is not None:
            raise AssertionError("dotenv streams disabled in tests")
        if kwargs.get("stream") is not None:
            raise AssertionError("implicit dotenv lookup disabled")
        try:
            candidate = _isolated_dotenv_path(dotenv_path, root)
        except (OSError, RuntimeError, TypeError):
            raise AssertionError("test dotenv path invalid") from None
        except ValueError:
            raise AssertionError("test dotenv path denied") from None
        return original_values(candidate, *args, **kwargs)

    dotenv.load_dotenv = disabled
    dotenv.find_dotenv = empty_path
    dotenv.dotenv_values = isolated_values
    dotenv.main.load_dotenv = disabled
    dotenv.main.find_dotenv = empty_path
    dotenv.main.dotenv_values = isolated_values


def _isolated_dotenv_path(
    dotenv_path: str | os.PathLike[str],
    root: Path,
) -> Path:
    candidate = Path(os.path.abspath(os.fspath(dotenv_path)))
    relative = candidate.relative_to(root)
    if not relative.parts:
        raise ValueError("dotenv path must be inside test root")
    current = root
    for part in relative.parts:
        current = current / part
        if _is_reparse_point(current):
            raise ValueError("dotenv path cannot contain a reparse point")
    return candidate


def _child_pythonpath() -> str:
    support = Path(__file__).resolve().parent
    repository = Path(__file__).resolve().parents[2]
    return os.pathsep.join((str(support), str(repository)))


def _path_matches(actual: str, expected: Path) -> bool:
    if not actual:
        return False
    actual_path = os.path.normcase(os.path.abspath(actual))
    expected_path = os.path.normcase(os.path.abspath(expected))
    return actual_path == expected_path


def _is_loopback_address(address: Any) -> bool:
    if not isinstance(address, tuple) or not address:
        return False
    return _is_loopback_host(address[0])


def _is_loopback_host(host: Any) -> bool:
    if isinstance(host, bytes):
        try:
            host = host.decode("ascii")
        except UnicodeDecodeError:
            return False
    if not isinstance(host, str):
        return False
    if host.casefold() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host.split("%", 1)[0]).is_loopback
    except ValueError:
        return False
