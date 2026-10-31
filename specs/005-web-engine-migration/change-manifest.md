# Change Manifest — python-dev

## Created

- `hedge_fund/test_acceptance_isolation.py` — isolation boundary and process-cleanup regressions.
- `hedge_fund/test_support/__init__.py` — test-support package marker.
- `hedge_fund/test_support/network_guard.py` — isolated environment, dotenv, socket, child-process, and safe cleanup helpers.
- `hedge_fund/test_support/sitecustomize.py` — installs test isolation in Python children.
- `specs/005-web-engine-migration/implementation-evidence.md` — revision-bound harness test evidence.
- `specs/005-web-engine-migration/implementation-progress.md` — task checkpoints and next stop.
- `specs/005-web-engine-migration/change-manifest.md` — implementation file inventory.

## Modified

- `hedge_fund/conftest.py` — establish isolated test state before application imports; reap exact owned child.
- `hedge_fund/web/conftest.py` — retain offline web fixtures under the shared harness.
- `specs/005-web-engine-migration/tasks.md` — check off evidence-backed T001 and T002 only.

## Deleted

- None.
