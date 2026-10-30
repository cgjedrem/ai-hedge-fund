from pathlib import Path

import pytest

from hedge_fund.web import __main__ as launcher


def test_default_launcher_uses_loopback_read_only_and_explicit_root(tmp_path, monkeypatch):
    observed = {}

    def fake_run(app, **kwargs):
        observed["app"] = app
        observed["kwargs"] = kwargs

    monkeypatch.setattr(launcher.uvicorn, "run", fake_run)
    launcher.main(["--root", str(tmp_path), "--port", "8765"])

    app = observed["app"]
    service = app.state.service
    assert service.root == tmp_path.resolve()
    assert service.allow_writes is False
    assert service.network_enabled is False
    assert observed["kwargs"]["host"] == "127.0.0.1"
    assert observed["kwargs"]["port"] == 8765
    assert observed["kwargs"]["workers"] == 1
    assert list(tmp_path.iterdir()) == []
    service.close()


def test_demo_launcher_uses_temporary_root_and_seeds_synthetic_records(monkeypatch):
    observed = {}

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


def test_container_bind_is_explicit_and_port_range_is_validated(monkeypatch):
    observed = {}

    def fake_run(app, **kwargs):
        observed["kwargs"] = kwargs
        app.state.service.close()

    monkeypatch.setattr(launcher.uvicorn, "run", fake_run)
    launcher.main(["--container-bind", "--port", "8765", "--root", "unused"])
    assert observed["kwargs"]["host"] == "0.0.0.0"

    with pytest.raises(SystemExit) as invalid_port:
        launcher.main(["--port", "70000"])
    assert invalid_port.value.code == 2
