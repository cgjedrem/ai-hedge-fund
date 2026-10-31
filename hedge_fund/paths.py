"""Root-scoped user data paths."""

from __future__ import annotations

import os
import re
import stat
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from hedge_fund.runtime.root import RootConfigurationError, RootContext, RootFileInfo

USER_DIR: Path | None = None
MANDATES_DIR: Path | None = None
PAPER_DIR: Path | None = None
RESEARCH_DIR: Path | None = None
CACHE_DIR: Path | None = None
ENV_PATH: Path | None = None

_ROOT_CONTEXT: RootContext | None = None
_SAFE_DOTENV_VARIABLES = frozenset(
    {
        "HEDGE_FUND_DATA_PROVIDER",
        "HEDGE_FUND_LLM_MODEL",
    }
)

# Packaged example seeds user mandates.
EXAMPLE_MANDATE = Path(__file__).resolve().parent / "fund" / "example.yaml"


def root_context(*, required: bool = True) -> RootContext | None:
    if type(required) is not bool:
        raise TypeError("required must be a bool")
    if _ROOT_CONTEXT is None and required:
        raise RootConfigurationError("an explicit root must be configured first")
    return _ROOT_CONTEXT


def configure_root(context: RootContext) -> None:
    if not isinstance(context, RootContext):
        raise RootConfigurationError("an opened root context is required")
    context.revalidate()
    global _ROOT_CONTEXT, USER_DIR, MANDATES_DIR, PAPER_DIR
    global RESEARCH_DIR, CACHE_DIR, ENV_PATH
    _ROOT_CONTEXT = context
    USER_DIR = context.path
    MANDATES_DIR = context.path / "mandates"
    PAPER_DIR = context.path / "paper"
    RESEARCH_DIR = context.path / "research"
    CACHE_DIR = context.path / "cache"
    ENV_PATH = context.path / ".env"


def clear_root(context: RootContext | None = None) -> None:
    global _ROOT_CONTEXT, USER_DIR, MANDATES_DIR, PAPER_DIR
    global RESEARCH_DIR, CACHE_DIR, ENV_PATH
    if context is not None and context is not _ROOT_CONTEXT:
        raise RootConfigurationError("root context does not match configured root")
    _ROOT_CONTEXT = None
    USER_DIR = None
    MANDATES_DIR = None
    PAPER_DIR = None
    RESEARCH_DIR = None
    CACHE_DIR = None
    ENV_PATH = None


@contextmanager
def bound_root(context: RootContext) -> Iterator[RootContext]:
    previous = root_context(required=False)
    configure_root(context)
    try:
        yield context
    finally:
        clear_root(context)
        if previous is not None:
            configure_root(previous)


def load_root_dotenv(
    context: RootContext | None = None,
    *,
    enabled: bool = False,
) -> None:
    if type(enabled) is not bool:
        raise TypeError("enabled must be a bool")
    if context is not None and not isinstance(context, RootContext):
        raise RootConfigurationError("an opened root context is required")
    if not enabled:
        return
    selected = context if context is not None else root_context()
    if selected is None:
        raise RootConfigurationError("an explicit root must be configured first")

    try:
        content = selected.read_bytes(".env").decode("utf-8")
    except FileNotFoundError:
        return
    except UnicodeError:
        raise RootConfigurationError("root .env must be UTF-8") from None

    values = _safe_dotenv_values(content)
    for name in _SAFE_DOTENV_VARIABLES:
        value = values.get(name)
        if value is not None and len(value) <= 256:
            os.environ.setdefault(name, value)


def _safe_dotenv_values(content: str) -> dict[str, str]:
    values = {}
    for line in content.splitlines():
        candidate = line.strip()
        if not candidate or candidate.startswith("#"):
            continue
        if candidate.startswith("export "):
            candidate = candidate[7:].lstrip()
        name, separator, raw_value = candidate.partition("=")
        name = name.strip()
        if not separator or name not in _SAFE_DOTENV_VARIABLES:
            continue
        value = raw_value.strip()
        if value[:1] in {"'", '"'}:
            quote = value[0]
            end = value.find(quote, 1)
            if end < 0:
                continue
            value = value[1:end]
        else:
            value = re.split(r"\s+#", value, maxsplit=1)[0].rstrip()
        if len(value) <= 256 and not any(ord(char) < 32 or ord(char) == 127 for char in value):
            values[name] = value
    return values


def _relative_user_path(path: str | os.PathLike[str]) -> tuple[RootContext, str] | None:
    selected = root_context(required=False)
    if selected is None:
        return None
    candidate = Path(path)
    if not candidate.is_absolute():
        return None
    try:
        relative = candidate.relative_to(selected.path)
    except ValueError:
        return None
    if not relative.parts:
        raise RootConfigurationError("a file path under the root is required")
    return selected, relative.as_posix()


def resolve_user_path(path: str | os.PathLike[str]) -> Path:
    """Bind relative paths; validate paths inside root."""
    selected = root_context()
    try:
        candidate = Path(path)
    except TypeError:
        raise RootConfigurationError("user path must be text or path-like") from None
    if candidate.is_absolute():
        try:
            relative = candidate.relative_to(selected.path)
        except ValueError:
            return candidate
    else:
        relative = candidate
    return selected.resolve(relative)


def read_bytes(path: str | os.PathLike[str]) -> bytes:
    selected = _relative_user_path(path)
    if selected is not None:
        context, relative = selected
        return context.read_bytes(relative)
    return Path(path).read_bytes()


def read_text(
    path: str | os.PathLike[str],
    *,
    encoding: str = "utf-8",
) -> str:
    return read_bytes(path).decode(encoding)


def write_bytes(
    path: str | os.PathLike[str],
    data: bytes,
    *,
    mode: int = 0o600,
) -> None:
    if not isinstance(data, bytes):
        raise TypeError("data must be bytes")
    if type(mode) is not int or not 0 <= mode <= 0o777:
        raise ValueError("mode must contain permission bits")
    candidate = Path(path)
    selected = _relative_user_path(candidate)
    if selected is not None:
        context, relative = selected
        parent = Path(relative).parent
        if parent.parts:
            context.mkdir(parent.as_posix(), parents=True)
        context.write_bytes(relative, data, mode=mode)
        return
    candidate.parent.mkdir(parents=True, exist_ok=True)
    candidate.write_bytes(data)


def write_text(
    path: str | os.PathLike[str],
    text: str,
    *,
    encoding: str = "utf-8",
    mode: int = 0o600,
) -> None:
    if not isinstance(text, str):
        raise TypeError("text must be str")
    write_bytes(path, text.encode(encoding), mode=mode)


def file_info(path: str | os.PathLike[str]) -> RootFileInfo:
    selected = _relative_user_path(path)
    if selected is not None:
        context, relative = selected
        return context.file_info(relative)
    candidate = Path(path).stat()
    if not stat.S_ISREG(candidate.st_mode):
        raise RootConfigurationError("only regular files can be inspected")
    return RootFileInfo(size=candidate.st_size, mtime_ns=candidate.st_mtime_ns)


def file_mtime(path: str | os.PathLike[str]) -> float | None:
    try:
        return file_info(path).mtime_ns / 1_000_000_000
    except FileNotFoundError:
        return None


def ensure_directory(
    path: str | os.PathLike[str],
    *,
    mode: int = 0o700,
) -> Path:
    candidate = Path(path)
    selected = _relative_user_path(candidate)
    if selected is not None:
        context, relative = selected
        return context.mkdir(relative, parents=True, mode=mode)
    candidate.mkdir(parents=True, exist_ok=True)
    return candidate


def ensure_mandates_dir() -> Path:
    context = root_context()
    if context is None or MANDATES_DIR is None:
        raise RootConfigurationError("an explicit root must be configured first")
    context.mkdir("mandates", parents=True)
    try:
        context.file_info("mandates/example.yaml")
    except FileNotFoundError:
        context.write_bytes(
            "mandates/example.yaml",
            EXAMPLE_MANDATE.read_bytes(),
        )
    return MANDATES_DIR


def write_atomic(path: Path, text: str, *, mode: int | None = None) -> None:
    """Atomically replace a file; root files use handle-relative writes."""
    path = Path(path)
    if mode is not None and (type(mode) is not int or not 0 <= mode <= 0o777):
        raise ValueError("mode must contain permission bits")
    selected = _relative_user_path(path)
    if selected is not None:
        write_bytes(
            path,
            text.encode("utf-8"),
            mode=mode if mode is not None else 0o600,
        )
        return

    tmp = path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    descriptor = None
    try:
        descriptor = os.open(tmp, os.O_CREAT | os.O_EXCL | os.O_WRONLY, mode if mode is not None else 0o666)
        if mode is not None:
            if os.name == "posix":
                os.fchmod(descriptor, mode)
            else:
                os.chmod(tmp, mode)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            descriptor = None
            handle.write(text)
        os.replace(tmp, path)
    except BaseException:
        if descriptor is not None:
            os.close(descriptor)
        tmp.unlink(missing_ok=True)
        raise
