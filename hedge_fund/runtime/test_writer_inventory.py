"""Spec005 T021 writer inventory ratchet.

Every production call site that can mutate the filesystem is enumerated by AST
and must map to a reviewed admission class. A new or moved raw write fails this
test until it is classified, so hidden direct-write paths cannot bypass the
central admission primitives unnoticed. The race matrix in
``test_writer_admission_race_matrix.py`` exercises each admission class.
"""

from __future__ import annotations

import ast
from collections import Counter
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1]

_PRIMITIVES = frozenset(
    {
        "write_text",
        "write_bytes",
        "append_bytes",
        "mkdir",
        "unlink",
        "rename",
        "rmdir",
        "touch",
        "symlink_to",
        "hardlink_to",
        "rmtree",
        "makedirs",
        "remove",
        "fdopen",
        "rename_file",
        "rename_directory",
        "open_lock_file",
        "prepare_private_storage",
        "replace",
        "copy",
        "copy2",
        "copyfile",
        "copytree",
        "move",
        "chmod",
    }
)

# Admission classes (each is exercised by test_writer_admission_race_matrix.py):
PATHS_ROUTED = "paths-routed: paths._root_write_admission for the configured or enclosing enrolled root"
REGISTRY = "registry-lane: root_registry_writer / AdmissionCoordinator.registry_lock"
PAPER_LANES = "paper-lanes: require_paper_write_lanes + paper inventory/control/audit transition"
DEPLOYMENT = "deployment-lane: AdmissionCoordinator.deployment_lock/control_lane"
WEB_GATED = "web-gated: DeskService._require_writes authority refresh then admission lane"
BOOTSTRAP = "bootstrap: offline enrollment/relocation/recovery under RootMigrationLease"
LOCK_FILE = "lock-primitive: creates only private lock files/directories for admission itself"
ROOT_PRIMITIVE = "root-primitive: RootContext handle-relative implementation used by admitted callers"
DISABLED = "disabled: legacy writer always raises before writing"
OUTSIDE_ROOT = "outside-root: writes only to a process temp directory, never an engine root"
TEST_HARNESS = "test-harness: test-owned demo root creation, validated inside HEDGE_FUND_TEST_ROOT"
USER_REGISTRY = "per-user-registry: private per-user SIM account registry outside every fund root, under its own " "OS lock; bind/release also require write_authority plus fund-root registry/deployment lanes"

WRITER_INVENTORY: dict[tuple[str, str, str], tuple[int, str]] = {
    ("backtesting/research.py", "save_result", "mkdir"): (1, PATHS_ROUTED),
    ("backtesting/research.py", "save_result", "write_bytes"): (1, PATHS_ROUTED),
    ("brokers/account_binding.py", "AccountRegistry._locked", "open_lock_file"): (1, USER_REGISTRY),
    ("brokers/account_binding.py", "AccountRegistry._locked", "write_bytes"): (1, USER_REGISTRY),
    ("brokers/account_binding.py", "AccountRegistry.initialize", "mkdir"): (1, USER_REGISTRY),
    ("brokers/account_binding.py", "AccountRegistry.initialize", "prepare_private_storage"): (1, USER_REGISTRY),
    ("brokers/account_binding.py", "AccountRegistry.initialize", "write_bytes"): (2, USER_REGISTRY),
    ("brokers/saxo.py", "_refresh_lock", "mkdir"): (2, OUTSIDE_ROOT),
    ("brokers/saxo.py", "_refresh_lock", "rmdir"): (1, OUTSIDE_ROOT),
    ("brokers/saxo.py", "_refresh_lock", "unlink"): (1, OUTSIDE_ROOT),
    ("brokers/saxo.py", "_refresh_lock", "write_text"): (1, OUTSIDE_ROOT),
    ("data/cached.py", "CachedDataClient._write", "write_text"): (1, PATHS_ROUTED),
    ("features/breakpoints.py", "load_breakpoints", "write_text"): (1, PATHS_ROUTED),
    ("fund/storage.py", "save_spec", "mkdir"): (1, PATHS_ROUTED),
    ("fund/storage.py", "save_spec", "write_bytes"): (1, PATHS_ROUTED),
    ("llm/cache.py", "PromptCache.put", "write_text"): (1, PATHS_ROUTED),
    ("paper/deployed.py", "deploy", "mkdir"): (2, PAPER_LANES),
    ("paper/deployed.py", "deploy", "write_bytes"): (2, PAPER_LANES),
    ("paper/deployed.py", "deploy", "write_text"): (1, PAPER_LANES),
    ("paper/ledger.py", "Ledger._clear_approval", "unlink"): (1, PAPER_LANES),
    ("paper/ledger.py", "Ledger.log_event", "append_bytes"): (1, PAPER_LANES),
    ("paper/ledger.py", "Ledger.append", "mkdir"): (2, PAPER_LANES),
    ("paper/ledger.py", "Ledger.append", "write_text"): (1, PAPER_LANES),
    ("paper/ledger.py", "Ledger.init", "mkdir"): (2, PAPER_LANES),
    ("paper/ledger.py", "Ledger.rewind", "mkdir"): (2, PAPER_LANES),
    ("paper/ledger.py", "Ledger.rewind", "rename"): (1, PAPER_LANES),
    ("paper/ledger.py", "Ledger.rewind", "rename_file"): (1, PAPER_LANES),
    ("paper/ledger.py", "Ledger.rewind", "unlink"): (1, PAPER_LANES),
    ("paper/runner.py", "serve", "unlink"): (1, DISABLED),
    ("paper/runner.py", "serve", "write_text"): (1, DISABLED),
    ("paper/runner.py", "spawn_runner", "open"): (1, DISABLED),
    ("paths.py", "_write_in_root", "mkdir"): (1, PATHS_ROUTED),
    ("paths.py", "_write_in_root", "write_bytes"): (1, PATHS_ROUTED),
    ("paths.py", "ensure_directory", "mkdir"): (3, PATHS_ROUTED),
    ("paths.py", "ensure_mandates_dir", "mkdir"): (1, REGISTRY),
    ("paths.py", "ensure_mandates_dir", "write_bytes"): (1, REGISTRY),
    ("paths.py", "write_atomic", "os.chmod"): (1, PATHS_ROUTED),
    ("paths.py", "write_atomic", "os.replace"): (1, PATHS_ROUTED),
    ("paths.py", "write_atomic", "os.open"): (1, PATHS_ROUTED),
    ("paths.py", "write_atomic", "unlink"): (1, PATHS_ROUTED),
    ("paths.py", "write_bytes", "mkdir"): (1, PATHS_ROUTED),
    ("paths.py", "write_bytes", "write_bytes"): (1, PATHS_ROUTED),
    ("run.py", "_backtest", "write_text"): (1, PATHS_ROUTED),
    ("run.py", "_handover", "prepare_private_storage"): (1, BOOTSTRAP),
    ("runtime/admission.py", "AdmissionCoordinator._lock", "mkdir"): (1, LOCK_FILE),
    ("runtime/admission.py", "AdmissionCoordinator._lock", "open_lock_file"): (1, LOCK_FILE),
    ("runtime/admission.py", "AdmissionCoordinator.operation_service_lease", "mkdir"): (1, LOCK_FILE),
    ("runtime/admission.py", "AdmissionCoordinator.operation_service_lease", "open_lock_file"): (1, LOCK_FILE),
    ("runtime/admission.py", "RootMigrationLease.acquire", "mkdir"): (1, LOCK_FILE),
    ("runtime/admission.py", "RootMigrationLease.acquire", "open_lock_file"): (1, LOCK_FILE),
    ("runtime/admission.py", "RootOwnerLease.acquire", "mkdir"): (1, LOCK_FILE),
    ("runtime/admission.py", "RootOwnerLease.acquire", "open_lock_file"): (1, LOCK_FILE),
    ("runtime/admission.py", "_existing_read_lock", "open_lock_file"): (1, LOCK_FILE),
    ("runtime/admission.py", "_local_lane", "remove"): (1, LOCK_FILE),
    ("runtime/admission.py", "_standalone_paper_lane", "open_lock_file"): (1, LOCK_FILE),
    ("runtime/configuration.py", "build_child_environment", "mkdir"): (5, DEPLOYMENT),
    ("runtime/configuration.py", "save_settings", "mkdir"): (1, REGISTRY),
    ("runtime/configuration.py", "save_settings", "write_bytes"): (1, REGISTRY),
    ("runtime/credentials.py", "CredentialStore._write_bytes", "mkdir"): (1, REGISTRY),
    ("runtime/credentials.py", "CredentialStore._write_bytes", "write_bytes"): (1, REGISTRY),
    ("runtime/handover.py", "_write_record", "write_bytes"): (1, BOOTSTRAP),
    ("runtime/handover.py", "_write_stale_recovery_record", "write_bytes"): (1, BOOTSTRAP),
    ("runtime/handover.py", "_write_private_json", "write_bytes"): (1, BOOTSTRAP),
    ("runtime/handover.py", "_write_attestation_artifact", "mkdir"): (1, BOOTSTRAP),
    ("runtime/handover.py", "PaperInventoryTransition.mkdir", "mkdir"): (2, PAPER_LANES),
    ("runtime/handover.py", "PaperInventoryTransition.rename_file", "rename_file"): (1, PAPER_LANES),
    ("runtime/handover.py", "PaperInventoryTransition.write_bytes", "write_bytes"): (1, PAPER_LANES),
    ("runtime/handover.py", "PaperInventoryTransition.write_text", "write_bytes"): (1, PAPER_LANES),
    ("runtime/handover.py", "enroll_fresh", "prepare_private_storage"): (1, BOOTSTRAP),
    ("runtime/handover.py", "migrate_existing", "prepare_private_storage"): (1, BOOTSTRAP),
    ("runtime/handover.py", "recover_stale_reservation", "mkdir"): (1, BOOTSTRAP),
    ("runtime/handover.py", "relocate_existing", "mkdir"): (1, BOOTSTRAP),
    ("runtime/handover.py", "relocate_existing", "prepare_private_storage"): (1, BOOTSTRAP),
    ("runtime/handover.py", "relocate_existing", "write_bytes"): (1, BOOTSTRAP),
    ("runtime/lifecycle.py", "LifecycleArchiveStore._move", "rename_directory"): (1, REGISTRY),
    ("runtime/lifecycle.py", "LifecycleArchiveStore._move", "rename_file"): (1, REGISTRY),
    ("runtime/lifecycle.py", "LifecycleArchiveStore._write_index", "mkdir"): (1, REGISTRY),
    ("runtime/lifecycle.py", "LifecycleArchiveStore._write_index", "write_bytes"): (1, REGISTRY),
    ("runtime/lifecycle.py", "LifecycleArchiveStore.archive", "mkdir"): (1, REGISTRY),
    ("runtime/operations.py", "OperationStore._write_bytes", "mkdir"): (1, REGISTRY),
    ("runtime/operations.py", "OperationStore._write_bytes", "write_bytes"): (1, REGISTRY),
    ("runtime/owned_runner.py", "OwnedRunnerManager._start_locked", "mkdir"): (1, DEPLOYMENT),
    ("runtime/owned_runner.py", "_write_record", "write_bytes"): (1, DEPLOYMENT),
    ("runtime/root.py", "RootContext.prepare_private_storage", "mkdir"): (1, ROOT_PRIMITIVE),
    ("runtime/root.py", "_open_posix_chain", "os.open"): (2, ROOT_PRIMITIVE),
    ("runtime/root.py", "_posix_mkdir_relative", "os.mkdir"): (1, ROOT_PRIMITIVE),
    ("runtime/root.py", "_posix_mkdir_relative", "os.open"): (1, ROOT_PRIMITIVE),
    ("runtime/root.py", "_posix_open_lock_relative", "os.open"): (1, ROOT_PRIMITIVE),
    ("runtime/root.py", "_posix_append_relative", "os.open"): (1, ROOT_PRIMITIVE),
    ("runtime/root.py", "_posix_append_relative", "os.write"): (1, ROOT_PRIMITIVE),
    ("runtime/root.py", "_posix_parent_fd", "os.open"): (1, ROOT_PRIMITIVE),
    ("runtime/root.py", "_posix_read_relative", "os.open"): (1, ROOT_PRIMITIVE),
    ("runtime/root.py", "_posix_unlink_relative", "os.unlink"): (1, ROOT_PRIMITIVE),
    ("runtime/root.py", "_posix_secure_private_directory", "os.open"): (1, ROOT_PRIMITIVE),
    ("runtime/root.py", "_posix_verify_private_directory", "os.open"): (1, ROOT_PRIMITIVE),
    ("runtime/root.py", "_posix_write_relative", "os.replace"): (1, ROOT_PRIMITIVE),
    ("runtime/root.py", "_posix_write_relative", "os.open"): (1, ROOT_PRIMITIVE),
    ("runtime/root.py", "_posix_write_relative", "os.unlink"): (1, ROOT_PRIMITIVE),
    ("tui/funds.py", "wipe_fund", "shutil.rmtree"): (1, DISABLED),
    ("tui/funds.py", "wipe_fund", "unlink"): (2, DISABLED),
    ("web/__main__.py", "main", "mkdir"): (1, TEST_HARNESS),
    ("web/__main__.py", "main", "tempfile.TemporaryDirectory"): (1, OUTSIDE_ROOT),
    ("web/demo.py", "seed_demo", "mkdir"): (1, BOOTSTRAP),
    ("web/services.py", "DeskService._ensure_dir", "mkdir"): (1, WEB_GATED),
    ("web/services.py", "DeskService.update_mandate", "rename_file"): (1, WEB_GATED),
    ("web/services.py", "DeskService.update_mandate", "write_bytes"): (1, WEB_GATED),
}


_UNKNOWN_MODE = object()
_OS_WRITERS = frozenset({"replace", "rename", "renames", "remove", "unlink", "rmdir", "removedirs", "mkdir", "makedirs", "symlink", "link", "truncate", "chmod", "utime", "open", "write", "mkfifo"})
_SHUTIL_WRITERS = frozenset({"copy", "copy2", "copyfile", "copytree", "move", "rmtree", "copymode", "copystat", "chown"})
_TEMPFILE_WRITERS = frozenset({"mkstemp", "mkdtemp", "NamedTemporaryFile", "TemporaryFile", "SpooledTemporaryFile", "TemporaryDirectory"})
_MODULE_WRITERS = {"os": _OS_WRITERS, "shutil": _SHUTIL_WRITERS, "tempfile": _TEMPFILE_WRITERS}


def _open_mode(node: ast.Call, position: int) -> object:
    mode = None
    if len(node.args) > position:
        argument = node.args[position]
        mode = argument.value if isinstance(argument, ast.Constant) else _UNKNOWN_MODE
    for keyword in node.keywords:
        if keyword.arg == "mode":
            mode = keyword.value.value if isinstance(keyword.value, ast.Constant) else _UNKNOWN_MODE
        elif keyword.arg is None:
            mode = _UNKNOWN_MODE
    return mode


def _writes(mode: object) -> bool:
    return mode is _UNKNOWN_MODE or (isinstance(mode, str) and any(flag in mode for flag in "wax+"))


def _primitive(node: ast.Call, imported: dict[str, str] | None = None) -> str | None:
    function = node.func
    if isinstance(function, ast.Name):
        if function.id == "open":
            return "open" if _writes(_open_mode(node, 1)) else None
        origin = (imported or {}).get(function.id)
        return origin
    if not isinstance(function, ast.Attribute):
        return None
    if isinstance(function.value, ast.Name) and function.value.id in _MODULE_WRITERS:
        if function.attr in _MODULE_WRITERS[function.value.id]:
            return f"{function.value.id}.{function.attr}"
        return None
    if function.attr == "open":
        if isinstance(function.value, ast.Name) and function.value.id == "RootContext":
            return None
        return "open" if _writes(_open_mode(node, 0)) else None
    if function.attr == "replace" and not (len(node.args) == 1 and not node.keywords):
        return None
    return function.attr if function.attr in _PRIMITIVES else None


def _imported_writers(tree: ast.AST) -> dict[str, str]:
    imported: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module in _MODULE_WRITERS:
            for alias in node.names:
                if alias.name in _MODULE_WRITERS[node.module]:
                    imported[alias.asname or alias.name] = f"{node.module}.{alias.name}"
    return imported


def scan_production_writers() -> Counter[tuple[str, str, str]]:
    found: Counter[tuple[str, str, str]] = Counter()
    for path in sorted(PACKAGE.rglob("*.py")):
        relative = path.relative_to(PACKAGE).as_posix()
        if path.name.startswith("test_") or path.name == "conftest.py" or relative.startswith("test_support/"):
            continue
        stack: list[str] = []
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imported = _imported_writers(tree)

        class Visitor(ast.NodeVisitor):
            def generic_visit(self, node: ast.AST) -> None:
                named = isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
                if named:
                    stack.append(node.name)
                if isinstance(node, ast.Call):
                    primitive = _primitive(node, imported)
                    if primitive is not None:
                        found[(relative, ".".join(stack) or "<module>", primitive)] += 1
                super().generic_visit(node)
                if named:
                    stack.pop()

        Visitor().visit(tree)
    return found


def test_every_production_writer_is_classified_by_admission_class():
    found = scan_production_writers()
    unclassified = sorted(site for site in found if site not in WRITER_INVENTORY)
    stale = sorted(site for site in WRITER_INVENTORY if site not in found)
    miscounted = sorted((site, found[site], WRITER_INVENTORY[site][0]) for site in found if site in WRITER_INVENTORY and found[site] != WRITER_INVENTORY[site][0])
    assert unclassified == [], f"unclassified raw writers: {unclassified}"
    assert stale == [], f"stale writer inventory entries: {stale}"
    assert miscounted == [], f"writer site counts changed: {miscounted}"


def test_scanner_detects_raw_writes_and_ignores_reads():
    source = "open(p, 'w')\nopen(p)\np.open('rb')\np.open('a')\ns.replace('a', 'b')\np.replace(q)\nos.open(p, f)\nos.replace(a, b)\nopen(p, m)\nshutil.move(a, b)\ntempfile.mkstemp(dir=d)\nos.symlink(a, b)\nreplace(a, b)\nos.path.join(a)\n"
    tree = ast.parse(source)
    calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)]
    found = sorted(filter(None, (_primitive(call, {"replace": "os.replace"}) for call in calls)))
    assert found == ["open", "open", "open", "os.open", "os.replace", "os.replace", "os.symlink", "replace", "shutil.move", "tempfile.mkstemp"]
    assert _imported_writers(ast.parse("from os import replace as r, getcwd\nfrom shutil import rmtree\n")) == {"r": "os.replace", "rmtree": "shutil.rmtree"}
