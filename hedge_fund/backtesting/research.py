"""Saved backtest results: research/<fund>-<start>-<end>-<stamp>.json.

Both `aihf backtest` and the app write here through `save_result`; the app's
mandate picker reads the directory back through the functions below. Results
are disposable research artifacts, never inputs to a run.
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime
from pathlib import Path

from hedge_fund import paths
from hedge_fund.backtesting.fund import FundBacktestResult
from hedge_fund.paper.deployed import validate_fund_name
from hedge_fund.runtime.admission import AdmissionCoordinator, root_registry_writer
from hedge_fund.runtime.root import RootContext


def save_result(
    result: FundBacktestResult,
    *,
    directory: str | Path | None = None,
    admission: AdmissionCoordinator | None = None,
) -> Path:
    """Write *result* under an admitted research root."""
    if not isinstance(result, FundBacktestResult):
        raise TypeError("a validated FundBacktestResult is required")
    if admission is not None and not isinstance(admission, AdmissionCoordinator):
        raise TypeError("admission must be an AdmissionCoordinator")
    if directory is not None and not isinstance(directory, (str, os.PathLike)):
        raise TypeError("research directory must be path-like")
    try:
        fund_name = validate_fund_name(result.fund)
        start = _safe_date_component(result.start)
        end = _safe_date_component(result.end)
    except (TypeError, ValueError):
        raise ValueError("backtest report identity is invalid") from None
    configured = paths.root_context(required=False)
    root = admission.root if admission is not None else configured
    if root is None:
        raise ValueError("research writes require an explicit root context")
    research_dir = Path(directory) if directory is not None else root.path / "research" if admission is not None else paths.RESEARCH_DIR
    if not isinstance(root, RootContext):
        raise TypeError("an explicit RootContext is required")
    if configured is not None and admission is None:
        _relative_root_path(configured, research_dir)
    relative_directory = _relative_root_path(root, research_dir)
    if relative_directory != "research":
        raise ValueError("backtest reports must use the research directory")
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    filename = f"{fund_name}-{start}-{end}-{stamp}.json"
    relative_file = "/".join(part for part in (relative_directory, filename) if part)
    try:
        with root_registry_writer(root, admission):
            if relative_directory:
                root.mkdir(relative_directory, parents=True)
            try:
                root.file_info(relative_file)
            except FileNotFoundError:
                pass
            else:
                raise FileExistsError(f"{root.path / Path(relative_file)}: report already exists")
            root.write_bytes(relative_file, result.model_dump_json(indent=2).encode("utf-8"))
    except FileExistsError:
        raise
    return root.path / Path(relative_file)


def _safe_date_component(value: str) -> str:
    if (
        not isinstance(value, str)
        or re.fullmatch(
            r"\d{4}-\d{2}-\d{2}(?:T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:[+-]\d{2}:\d{2})?)?",
            value,
        )
        is None
    ):
        raise ValueError("invalid ISO date")
    datetime.fromisoformat(value)
    return value.replace(":", "-").replace("+", "-")


def _relative_root_path(root: RootContext, path: Path) -> str:
    root_path = os.path.normcase(os.path.abspath(os.fspath(root.path)))
    target_path = os.path.normcase(os.path.abspath(os.fspath(path)))
    try:
        common = os.path.commonpath((root_path, target_path))
    except ValueError:
        raise ValueError("research directory is outside the configured root") from None
    if os.path.normcase(common) != root_path:
        raise ValueError("research directory is outside the configured root")
    relative = os.path.relpath(target_path, root_path)
    return "" if relative == "." else Path(relative).as_posix()


def summarize(path: Path, mtime: float) -> dict | None:
    """One saved backtest result as the light summary the history pane
    renders. None if the file is unreadable or not a backtest."""
    try:
        d = json.loads(path.read_text())
        if not isinstance(d, dict) or "metrics" not in d:
            return None
        m = d["metrics"]
        return {
            "kind": "backtest",
            "mtime": mtime,
            "fund": d.get("fund", ""),
            "universe": d.get("universe", []),
            "start": d.get("start", ""),
            "end": d.get("end", ""),
            "benchmark": d.get("benchmark", "SPY"),
            "total": m["total_return_pct"],
            "annualized": m["annualized_return_pct"],
            "sharpe": m["sharpe_ratio"],
            "maxdd": m["max_drawdown_pct"],
            "benchret": m["benchmark_return_pct"],
            "excess": m["excess_return_pct"],
            "n_cycles": m["n_cycles"],
        }
    except (json.JSONDecodeError, KeyError, OSError, TypeError, UnicodeError):
        return None


def receipts(name: str) -> list[Path]:
    """Every saved backtest of a mandate, newest first. Filenames start with
    the mandate's name, but names can be prefixes of each other, so the
    result's own `fund` field is what decides."""
    found = []
    for p in paths.RESEARCH_DIR.glob(f"{name}-*.json"):
        summary = summarize(p, 0.0)
        if summary is not None and summary["fund"] == name:
            found.append(p)
    return sorted(found, key=lambda p: p.stat().st_mtime, reverse=True)


def last_universe(name: str) -> list[str] | None:
    """The tickers this mandate was last backtested over — the ticker inputs
    prefill from it, so a returning user just presses enter."""
    for path in receipts(name):
        summary = summarize(path, 0.0)
        if summary and summary["universe"]:
            return summary["universe"]
    return None


def last_score(name: str) -> tuple[float, float, str] | None:
    """The mandate's most recent backtest result, if any: (total return,
    excess return, benchmark). A quiet scoreboard on each slot."""
    for path in receipts(name):
        summary = summarize(path, 0.0)
        if summary:
            return (summary["total"], summary["excess"], summary["benchmark"])
    return None
