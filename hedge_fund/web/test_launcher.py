from pathlib import Path

import pytest

import hedge_fund.web.__main__ as launcher


def _set_launcher_root(monkeypatch, root: Path) -> Path:
    module = root / "hedge_fund" / "web" / "__main__.py"
    module.parent.mkdir(parents=True)
    monkeypatch.setattr(launcher, "__file__", str(module))
    return module


def test_build_frontend_runs_npm_lockfile_commands_from_checkout(tmp_path, monkeypatch):
    module = _set_launcher_root(monkeypatch, tmp_path)
    frontend = module.parents[2] / "frontend"
    frontend.mkdir()
    (frontend / "package.json").write_text("{}", encoding="utf-8")
    (frontend / "package-lock.json").write_text("{}", encoding="utf-8")
    calls = []
    monkeypatch.setattr(launcher.shutil, "which", lambda name: "npm" if name == "npm" else None)
    monkeypatch.setattr(
        launcher.subprocess,
        "run",
        lambda command, **kwargs: calls.append((command, kwargs)),
    )

    launcher._build_frontend()

    assert [command for command, _ in calls] == ["npm ci", "npm run build"]
    assert all(kwargs == {"cwd": frontend, "check": True, "shell": True} for _, kwargs in calls)


def test_build_frontend_requires_clean_checkout_manifests(tmp_path, monkeypatch):
    _set_launcher_root(monkeypatch, tmp_path)
    monkeypatch.setattr(launcher.shutil, "which", lambda _name: "npm")

    with pytest.raises(SystemExit, match="source checkout"):
        launcher._build_frontend()


def test_launcher_requires_static_bundle_without_build_flag(tmp_path, monkeypatch):
    module = _set_launcher_root(monkeypatch, tmp_path)

    with pytest.raises(SystemExit, match="React static assets are missing"):
        launcher._require_static_bundle()

    static = module.parent / "static"
    static.mkdir()
    (static / "index.html").write_text("<html></html>", encoding="utf-8")
    launcher._require_static_bundle()


def test_main_builds_static_assets_before_seeding_and_serving(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(launcher, "_build_frontend", lambda: calls.append("build"))
    monkeypatch.setattr(launcher, "_require_static_bundle", lambda: calls.append("static"))

    def fake_seed(root):
        calls.append(("seed", root))
        return root

    monkeypatch.setattr(launcher, "seed_demo", fake_seed)
    monkeypatch.setattr(
        launcher,
        "_serve",
        lambda context, args, host: calls.append(("serve", context.path, args.port, host)),
    )

    launcher.main(["--build", "--demo", "--root", str(tmp_path), "--port", "12345"])

    assert calls == [
        "build",
        "static",
        ("seed", tmp_path.resolve()),
        ("serve", tmp_path.resolve(), 12345, "127.0.0.1"),
    ]
