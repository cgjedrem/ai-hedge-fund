"""Out-of-band writer exclusion basis for production write authority.

Spec005 A3 decision: cooperative registry/OS locks only exclude writers that
participate in the protocol. They do not prove that an unaware or out-of-band
writer running under the same account (an older checkout, a shell script, a
copied engine) cannot mutate the root. Write authority therefore additionally
requires an explicit exclusion basis.

No production basis (OS sandbox, dedicated account, or ACL proof) is
implemented, so production roots stay read-only. The only basis recognised is
the synthetic test harness: a test-mode process whose root lies inside a
checkout-owned ``outputs/spec005-test-*`` directory carrying the exact
``.test-owned`` marker. Those roots are created by the harness and are not
addressable by any shipped writer.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path

from hedge_fund.runtime.root import RootContext

SYNTHETIC_TEST_OWNED = "synthetic-test-owned"
UNPROVEN_REASON = "out-of-band-exclusion-unproven"
_MARKER_NAME = ".test-owned"
_MARKER_CONTENT = "test-owned\n"
_TEST_ROOT_PREFIX = "spec005-test-"


def out_of_band_exclusion_basis(root: RootContext | Path | str) -> str | None:
    """Return the exclusion basis for ``root`` or ``None`` when unproven."""
    try:
        return _synthetic_basis(Path(root.path if isinstance(root, RootContext) else root))
    except (OSError, ValueError, RuntimeError):
        return None


def _synthetic_basis(root_path: Path) -> str | None:
    if os.environ.get("HEDGE_FUND_TEST_MODE") != "1":
        return None
    test_root_value = os.environ.get("HEDGE_FUND_TEST_ROOT", "")
    if not test_root_value:
        return None
    test_root = Path(test_root_value)
    if not test_root.is_absolute() or not root_path.is_absolute():
        return None
    test_root = Path(os.path.abspath(os.fspath(test_root)))
    outputs = Path(__file__).resolve().parents[2] / "outputs"
    if _is_reparse_point(outputs) or test_root.parent != outputs.resolve(strict=True):
        return None
    if not test_root.name.startswith(_TEST_ROOT_PREFIX) or _is_reparse_point(test_root):
        return None
    marker = test_root / _MARKER_NAME
    info = marker.lstat()
    if not stat.S_ISREG(info.st_mode) or _is_reparse_point(marker):
        return None
    if marker.read_text(encoding="utf-8") != _MARKER_CONTENT:
        return None
    candidate = Path(os.path.abspath(os.fspath(root_path)))
    try:
        relative = candidate.relative_to(test_root)
    except ValueError:
        return None
    if not relative.parts:
        return None
    current = test_root
    for part in relative.parts:
        current = current / part
        if _is_reparse_point(current):
            return None
    resolved_test_root = Path(os.path.realpath(os.fspath(test_root), strict=True))
    resolved = Path(os.path.realpath(os.fspath(candidate), strict=True))
    if resolved == resolved_test_root or not resolved.is_relative_to(resolved_test_root):
        return None
    return SYNTHETIC_TEST_OWNED


def _is_reparse_point(path: Path) -> bool:
    try:
        info = path.lstat()
    except FileNotFoundError:
        return False
    if stat.S_ISLNK(info.st_mode):
        return True
    attributes = getattr(info, "st_file_attributes", 0)
    return bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))
