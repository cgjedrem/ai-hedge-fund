# Quickstart Validation

The implementation must publish exact commands in README. Planned workflow:

1. Install Python dependencies through Poetry and frontend dependencies through the lockfile.
2. Build production frontend; use `make web` where GNU Make is available or `poetry run aihf-web --build --demo` on Windows. The plain launcher requires an existing static bundle.
3. Default startup reads the existing home without writes/network; isolated demo flag supplies synthetic data.
4. Open loopback URL and inspect home, funds, builder, paper list/detail, session reports, research/backtests, scorecards, settings and command palette.
5. Test mutations only in a temporary root with fake dependencies. Never enable writes on protected live funds for acceptance.
6. Run targeted API pytest, frontend tests/build, existing suite and changed-file style gates. Capture exact outcomes and baseline exceptions.
7. Browser acceptance uses the built artifact, local-only request allowlist, desktop/narrow viewports, screenshots and negative-action scenarios.

Actual final commands, revision/artifact identity, timestamps and any blocked scenarios belong in acceptance-evidence.md.
