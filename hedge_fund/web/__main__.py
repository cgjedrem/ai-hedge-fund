"""Local web desk launcher."""

from __future__ import annotations

import argparse
import tempfile
from pathlib import Path
from typing import Sequence

import uvicorn

from hedge_fund.paths import USER_DIR
from hedge_fund.web.app import create_app
from hedge_fund.web.demo import seed_demo


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
    parser.add_argument("--port", type=_port, default=8765, help="loopback port (default: 8765)")
    parser.add_argument("--root", type=Path, help="explicit local data root; defaults to ~/.hedge-fund")
    parser.add_argument("--allow-writes", action="store_true", help="enable explicit local mutations")
    parser.add_argument("--enable-network", action="store_true", help="allow explicitly submitted external research")
    parser.add_argument("--demo", action="store_true", help="seed synthetic data in an isolated temporary root")
    parser.add_argument(
        "--container-bind",
        action="store_true",
        help="bind container interfaces; publish only to host loopback",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    args = _parser().parse_args(argv)
    host = "0.0.0.0" if args.container_bind else "127.0.0.1"
    if args.demo:
        if args.root is not None:
            root = args.root.expanduser().resolve()
            seed_demo(root)
            _serve(root, args, host)
            return
        with tempfile.TemporaryDirectory(prefix="aihf-web-demo-") as directory:
            root = Path(directory)
            seed_demo(root)
            _serve(root, args, host)
        return
    _serve(args.root or USER_DIR, args, host)


def _serve(root: str | Path, args: argparse.Namespace, host: str) -> None:
    app = create_app(
        root=root,
        allow_writes=args.allow_writes,
        network_enabled=args.enable_network,
        demo=args.demo,
    )
    uvicorn.run(
        app,
        host=host,
        port=args.port,
        workers=1,
        proxy_headers=False,
        access_log=False,
    )


if __name__ == "__main__":
    main()
