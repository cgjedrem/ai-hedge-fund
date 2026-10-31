"""Local web desk launcher."""

from __future__ import annotations

import argparse
import os
import shutil
import stat
import subprocess
import tempfile
from pathlib import Path
from typing import Sequence

try:
    import uvicorn
except ModuleNotFoundError:
    uvicorn = None

from hedge_fund import paths
from hedge_fund.runtime.root import RootContext, RootPathError


def _port(value: str) -> int:
    try:
        port = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError("port must be an integer") from None
    if not 1 <= port <= 65535:
        raise argparse.ArgumentTypeError("port must be between 1 and 65535")
    return port


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="aihf-web",
        description="Serve the local React desk with immutable startup capabilities.",
    )
    parser.add_argument(
        "--port",
        type=_port,
        default=8876,
        help="loopback port (default: 8876)",
    )
    parser.add_argument("--root", type=Path, help="existing absolute local data root")
    parser.add_argument(
        "--load-dotenv",
        action="store_true",
        help="load safe non-secret settings from this root's .env",
    )
    parser.add_argument("--allow-writes", action="store_true", help="enable explicit local mutations")
    parser.add_argument("--enable-network", action="store_true", help="allow explicitly submitted external research")
    parser.add_argument("--demo", action="store_true", help="seed synthetic data in an isolated temporary root")
    parser.add_argument(
        "--build",
        action="store_true",
        help="run npm ci and build the React bundle before serving; requires Node.js and npm",
    )
    parser.add_argument(
        "--container-bind",
        action="store_true",
        help="bind container interfaces; publish only to host loopback",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    parser = _parser()
    args = parser.parse_args(argv)
    if not args.demo and args.root is None:
        parser.error("--root is required unless --demo is selected")
    host = "0.0.0.0" if args.container_bind else "127.0.0.1"

    if not args.demo:
        try:
            context = RootContext.open(args.root)
        except RootPathError as exc:
            parser.error(str(exc))
        try:
            _prepare_frontend(args)
            _run(context, args, host)
        finally:
            context.close()
        return

    if args.demo:
        if args.root is not None:
            root = _demo_root(args.root)
            _prepare_frontend(args)
            root.mkdir(parents=True, exist_ok=True)
            try:
                context = RootContext.open(root)
            except RootPathError as exc:
                parser.error(str(exc))
            try:
                _run(context, args, host)
            finally:
                context.close()
            return
        _prepare_frontend(args)
        with tempfile.TemporaryDirectory(prefix="aihf-web-demo-") as directory:
            context = RootContext.open(Path(directory))
            try:
                _run(context, args, host)
            finally:
                context.close()


def _prepare_frontend(args: argparse.Namespace) -> None:
    if args.build:
        _build_frontend()
    _require_static_bundle()


def _run(context: RootContext, args: argparse.Namespace, host: str) -> None:
    if uvicorn is None:
        raise SystemExit("Web server dependencies are missing; install with 'poetry install -E web'.")

    with paths.bound_root(context):
        try:
            paths.load_root_dotenv(context, enabled=args.load_dotenv)
        except (RootPathError, UnicodeError, ValueError) as exc:
            raise SystemExit(str(exc)) from None
        if args.demo:
            seed_demo(context.path)
        _serve(context, args, host)


def _serve(context: RootContext, args: argparse.Namespace, host: str) -> None:
    from hedge_fund.web.app import create_app

    app = create_app(
        root=context.path,
        root_context=context,
        allow_writes=args.allow_writes,
        network_enabled=args.enable_network,
        demo=args.demo,
        static_dir=_static_directory(),
    )
    uvicorn.run(
        app,
        host=host,
        port=args.port,
        workers=1,
        proxy_headers=False,
        access_log=False,
    )


def seed_demo(root: str | Path) -> Path:
    from hedge_fund.web.demo import seed_demo as seed

    return seed(root)


def _build_frontend() -> None:
    repository = Path(__file__).resolve().parents[2]
    frontend = repository / "frontend"
    if not (frontend / "package.json").is_file() or not (frontend / "package-lock.json").is_file():
        raise SystemExit("--build requires a source checkout with frontend/package.json and frontend/package-lock.json.")
    if shutil.which("npm") is None:
        raise SystemExit("--build requires Node.js and npm on PATH.")
    subprocess.run("npm ci", cwd=frontend, check=True, shell=True)
    subprocess.run("npm run build", cwd=frontend, check=True, shell=True)


def _require_static_bundle() -> None:
    index = _static_directory() / "index.html"
    if not index.is_file():
        raise SystemExit("React static assets are missing. From a source checkout, run " "'python -m hedge_fund.web --build' or 'npm --prefix frontend ci' " "and 'npm --prefix frontend run build'.")


def _static_directory() -> Path:
    value = os.environ.get("AIHF_WEB_STATIC_DIR")
    if os.environ.get("HEDGE_FUND_TEST_MODE") != "1" or not value:
        return Path(__file__).resolve().parent / "static"

    test_root_value = os.environ.get("HEDGE_FUND_TEST_ROOT", "")
    test_root = Path(test_root_value)
    candidate = Path(value)
    if not test_root_value:
        raise ValueError("test static directory requires absolute owned paths")
    if not test_root.is_absolute():
        raise ValueError("test static directory requires absolute owned paths")
    if not candidate.is_absolute():
        raise ValueError("test static directory requires absolute owned paths")

    repository = Path(__file__).resolve().parents[2]
    outputs = repository / "outputs"
    test_root = Path(os.path.abspath(os.fspath(test_root)))
    candidate = Path(os.path.abspath(os.fspath(candidate)))
    if _is_reparse_point(outputs) or _is_reparse_point(test_root):
        raise ValueError("test static root cannot contain reparse points")
    resolved_outputs = outputs.resolve(strict=True)
    resolved_test_root = test_root.resolve(strict=True)
    if resolved_test_root.parent != resolved_outputs:
        raise ValueError("test static root is not checkout-owned")
    if not resolved_test_root.name.startswith("spec005-test-"):
        raise ValueError("test static root is not checkout-owned")

    marker = test_root / ".test-owned"
    if _is_reparse_point(marker) or not marker.is_file():
        raise ValueError("test static root marker is invalid")
    if marker.read_text(encoding="utf-8") != "test-owned\n":
        raise ValueError("test static root marker is invalid")

    try:
        relative = candidate.relative_to(test_root)
    except ValueError:
        raise ValueError(
            "static directory must stay inside test-owned root",
        ) from None
    if not relative.parts:
        raise ValueError(
            "static directory must stay inside test-owned root",
        )

    current = test_root
    for part in relative.parts:
        current = current / part
        if _is_reparse_point(current):
            raise ValueError(
                "test static directory cannot contain reparse points",
            )
    resolved_candidate = candidate.resolve(strict=False)
    if not resolved_candidate.is_relative_to(resolved_test_root):
        raise ValueError(
            "static directory must stay inside test-owned root",
        )
    return resolved_candidate


def _demo_root(root: str | Path) -> Path:
    candidate = Path(root)
    if os.environ.get("HEDGE_FUND_TEST_MODE") != "1":
        return candidate.expanduser().resolve()

    test_root_value = os.environ.get("HEDGE_FUND_TEST_ROOT", "")
    test_root = Path(test_root_value)
    if not test_root_value or not test_root.is_absolute():
        raise RuntimeError("test demo requires an absolute test root")
    if not candidate.is_absolute():
        raise ValueError("test demo root must be absolute")

    repository = Path(__file__).resolve().parents[2]
    outputs = repository / "outputs"
    test_root = Path(os.path.abspath(os.fspath(test_root)))
    demo_root = Path(os.path.abspath(os.fspath(candidate)))
    if _is_reparse_point(outputs) or _is_reparse_point(test_root):
        raise ValueError("test root cannot contain reparse points")
    resolved_outputs = outputs.resolve(strict=True)
    resolved_test_root = test_root.resolve(strict=True)
    if resolved_test_root.parent != resolved_outputs:
        raise ValueError("test root is not checkout-owned")
    if not resolved_test_root.name.startswith("spec005-test-"):
        raise ValueError("test root is not checkout-owned")

    try:
        relative = demo_root.relative_to(test_root)
    except ValueError:
        raise ValueError("demo root must stay inside test-owned root") from None
    if not relative.parts:
        raise ValueError("demo root must stay inside test-owned root")
    current = test_root
    for part in relative.parts:
        current = current / part
        if _is_reparse_point(current):
            raise ValueError("demo root cannot contain reparse points")
    resolved_demo_root = demo_root.resolve(strict=False)
    if not resolved_demo_root.is_relative_to(resolved_test_root):
        raise ValueError("demo root must stay inside test-owned root")
    return resolved_demo_root


def _is_reparse_point(path: Path) -> bool:
    try:
        info = path.lstat()
    except FileNotFoundError:
        return False
    attributes = getattr(info, "st_file_attributes", 0)
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    return stat.S_ISLNK(info.st_mode) or bool(attributes & reparse_flag)


if __name__ == "__main__":
    main()
