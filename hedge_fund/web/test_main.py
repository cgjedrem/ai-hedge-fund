import os
import re
import uuid
from pathlib import Path

import pytest

from hedge_fund.test_support import network_guard
from hedge_fund.web import __main__ as launcher
from hedge_fund.web.demo import seed_demo


def test_default_launcher_uses_loopback_read_only_and_explicit_root(tmp_path, monkeypatch):
    observed = {}
    monkeypatch.setattr(launcher, "_require_static_bundle", lambda: None)

    def fake_run(app, **kwargs):
        observed["app"] = app
        observed["kwargs"] = kwargs

    monkeypatch.setattr(launcher.uvicorn, "run", fake_run)
    launcher.main(["--root", str(tmp_path), "--port", "8876"])

    app = observed["app"]
    service = app.state.service
    assert service.root == tmp_path.resolve()
    assert service.allow_writes is False
    assert service.network_enabled is False
    assert observed["kwargs"]["host"] == "127.0.0.1"
    assert observed["kwargs"]["port"] == 8876
    assert observed["kwargs"]["workers"] == 1
    assert list(tmp_path.iterdir()) == []
    service.close()


def test_web_launcher_requires_root_outside_demo_mode(monkeypatch):
    prepare = []
    monkeypatch.setattr(launcher, "_prepare_frontend", lambda _args: prepare.append(True))

    with pytest.raises(SystemExit) as missing:
        launcher.main(["--port", "8876"])

    assert missing.value.code == 2
    assert prepare == []


def test_web_dotenv_is_opt_in_exact_root_and_non_secret_only(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text(
        "HEDGE_FUND_LLM_MODEL=safe-model\nHEDGE_FUND_DATA_PROVIDER=yfinance\nOPENAI_API_KEY=synthetic-secret\nHEDGE_FUND_ROOT=decoy-root\nAIHF_ALLOW_WRITES=1\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("HOME", str(tmp_path / "decoy"))
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "decoy"))
    for name in (
        "HEDGE_FUND_LLM_MODEL",
        "HEDGE_FUND_DATA_PROVIDER",
        "OPENAI_API_KEY",
        "HEDGE_FUND_ROOT",
        "AIHF_ALLOW_WRITES",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(launcher, "_require_static_bundle", lambda: None)
    observed = {}

    def fake_run(app, **_kwargs):
        observed["settings"] = app.state.service.settings()
        app.state.service.close()

    monkeypatch.setattr(launcher.uvicorn, "run", fake_run)
    launcher.main(["--root", str(tmp_path), "--load-dotenv"])

    assert observed["settings"]["model"] == "safe-model"
    assert observed["settings"]["data_provider"] == "yfinance"
    assert os.environ["HEDGE_FUND_LLM_MODEL"] == "safe-model"
    assert os.environ["HEDGE_FUND_DATA_PROVIDER"] == "yfinance"
    assert "OPENAI_API_KEY" not in os.environ
    assert "HEDGE_FUND_ROOT" not in os.environ
    assert "AIHF_ALLOW_WRITES" not in os.environ


def test_web_without_dotenv_flag_ignores_root_environment(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text(
        "HEDGE_FUND_LLM_MODEL=must-not-load\nOPENAI_API_KEY=synthetic-secret\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("HEDGE_FUND_LLM_MODEL", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(launcher, "_require_static_bundle", lambda: None)
    observed = {}

    def fake_run(app, **_kwargs):
        observed["settings"] = app.state.service.settings()
        app.state.service.close()

    monkeypatch.setattr(launcher.uvicorn, "run", fake_run)
    launcher.main(["--root", str(tmp_path)])

    assert observed["settings"]["model"] != "must-not-load"
    assert "HEDGE_FUND_LLM_MODEL" not in os.environ
    assert "OPENAI_API_KEY" not in os.environ


def test_web_launcher_default_port_avoids_creator_preview():
    assert launcher._parser().parse_args(["--root", "unused"]).port == 8876


def test_demo_launcher_uses_temporary_root_and_seeds_synthetic_records(monkeypatch):
    observed = {}
    monkeypatch.setattr(launcher, "_require_static_bundle", lambda: None)

    def fake_run(app, **kwargs):
        observed["app"] = app
        observed["kwargs"] = kwargs
        service = app.state.service
        observed["root"] = service.root
        observed["paper"] = service.list_paper()
        observed["capabilities"] = service.capabilities(app.state.capability_token)
        service.close()

    monkeypatch.setattr(launcher.uvicorn, "run", fake_run)
    launcher.main(["--demo", "--port", "8766"])

    assert observed["kwargs"]["host"] == "127.0.0.1"
    assert observed["kwargs"]["port"] == 8766
    assert observed["capabilities"]["mode"] == "demo"
    assert observed["capabilities"]["writes"] is False
    assert observed["capabilities"]["network"] is False
    assert observed["paper"]["items"][0]["name"] == "demo-quality"
    assert not Path(observed["root"]).exists()


def test_demo_seed_rejects_root_outside_test_root_before_resolution(
    monkeypatch,
):
    test_root = Path(os.environ["HEDGE_FUND_TEST_ROOT"])
    outside_name = f"spec005-test-denied-demo-{uuid.uuid4().hex}"
    outside_root = test_root.parent / outside_name
    original_resolve = Path.resolve

    def resolve_inside_test_root(path, *args, **kwargs):
        if not Path(path).is_relative_to(test_root):
            raise AssertionError("filesystem access escaped test root")
        return original_resolve(path, *args, **kwargs)

    monkeypatch.setattr(Path, "resolve", resolve_inside_test_root)

    with pytest.raises(ValueError, match="inside test-owned root"):
        seed_demo(outside_root)

    assert not outside_root.exists()


def test_demo_launcher_uses_owned_static_assets(monkeypatch):
    test_root = Path(os.environ["HEDGE_FUND_TEST_ROOT"])
    static_root = test_root / "web-static"
    static_root.mkdir()
    (static_root / "index.html").write_text(
        "<html>owned</html>",
        encoding="utf-8",
    )
    demo_root = test_root / "demo-root"
    observed = {}
    monkeypatch.setenv("AIHF_WEB_STATIC_DIR", str(static_root))

    def fake_run(app, **kwargs):
        observed["static_root"] = app.state.static_root
        app.state.service.close()

    monkeypatch.setattr(launcher.uvicorn, "run", fake_run)
    launcher.main(["--demo", "--port", "8876", "--root", str(demo_root)])

    assert observed["static_root"] == static_root.resolve()


def test_demo_launcher_rejects_static_assets_outside_test_root(monkeypatch):
    test_root = Path(os.environ["HEDGE_FUND_TEST_ROOT"])
    outside_name = f"spec005-test-denied-static-{uuid.uuid4().hex}"
    outside_root = test_root.parent / outside_name
    monkeypatch.setenv("AIHF_WEB_STATIC_DIR", str(outside_root))
    demo_root = test_root / "demo-root-negative"

    with pytest.raises(ValueError, match="inside test-owned root"):
        launcher.main(["--demo", "--port", "8876", "--root", str(demo_root)])

    assert not outside_root.exists()
    assert not demo_root.exists()


def test_browser_runner_clears_provider_and_proxy_variables():
    repository = Path(__file__).resolve().parents[2]
    source_path = repository / "frontend" / "e2e" / "run-owned.mjs"
    source = source_path.read_text(encoding="utf-8")
    expected = {
        "credentialVariables": set(network_guard.CREDENTIAL_ENV_VARS),
        "proxyVariables": set(network_guard.PROXY_ENV_VARS),
    }

    for array_name, required in expected.items():
        match = re.search(
            rf"const {array_name} = \[(.*?)\];",
            source,
            flags=re.DOTALL,
        )
        assert match is not None
        configured = set(re.findall(r'"([^"]+)"', match.group(1)))
        assert required <= configured


def test_container_bind_is_explicit_and_port_range_is_validated(monkeypatch):
    observed = {}
    monkeypatch.setattr(launcher, "_require_static_bundle", lambda: None)

    def fake_run(app, **kwargs):
        observed["kwargs"] = kwargs
        app.state.service.close()

    monkeypatch.setattr(launcher.uvicorn, "run", fake_run)
    root = Path(os.environ["HEDGE_FUND_TEST_ROOT"]) / "container-bind-root"
    root.mkdir()
    launcher.main(["--container-bind", "--port", "8876", "--root", str(root)])
    assert observed["kwargs"]["host"] == "0.0.0.0"

    with pytest.raises(SystemExit) as invalid_port:
        launcher.main(["--port", "70000"])
    assert invalid_port.value.code == 2
