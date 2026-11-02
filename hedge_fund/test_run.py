"""The CLI: configuration preflight, the backtest command, and the paper flow."""

import hashlib
import importlib
import json
import os
import sys
from contextlib import nullcontext
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock

import pytest
import yaml

from hedge_fund import paths, run
from hedge_fund.data import sessions
from hedge_fund.fund import custom_strategy, FundSpec


@pytest.fixture
def offline(tmp_path, monkeypatch):
    """No credentials, no HTTP, user dirs under tmp, fakes for the engine."""
    from hedge_fund.backtesting.test_fund import FakeAnalyst, FakeDataClient
    from hedge_fund.fund import Fund

    tick_module = importlib.import_module("hedge_fund.paper.tick")

    class OfflineClient(FakeDataClient):
        def __init__(self, *_args, **_kwargs):
            super().__init__({ticker: {"2025-01-06": 100, "2025-01-07": 100, "2025-01-08": 110, "2025-01-13": 110} for ticker in ("AAPL", "MSFT", "SPY")})

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    def build_fund(
        spec,
        blind=False,
        llm_factory=None,
        breakpoints_dispatch=None,
    ):
        return Fund(spec, models={s.name: [FakeAnalyst(m.name, {"AAPL": 0.8, "MSFT": -0.6}) for m in s.models] for s in spec.strategies})

    monkeypatch.setattr(run, "ensure_mandates_dir", lambda: tmp_path)
    monkeypatch.setattr(run, "Fund", build_fund)
    monkeypatch.setattr(tick_module, "Fund", build_fund)
    monkeypatch.setattr(run, "make_data_client", OfflineClient)
    monkeypatch.setattr(run, "CachedDataClient", lambda client, **kwargs: client)
    monkeypatch.setattr(run, "PAPER_DIR", tmp_path / "paper")
    monkeypatch.setattr(paths, "RESEARCH_DIR", tmp_path / "research")

    def save_fake_result(result, *, admission=None):
        assert admission is not None
        destination = paths.RESEARCH_DIR / f"{result.fund}-{result.start}-{result.end}-fixture.json"
        with admission.research_lane(result.fund):
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(result.model_dump_json(indent=2), encoding="utf-8")
        return destination

    monkeypatch.setattr(run, "save_result", save_fake_result)

    def set_today(day):
        y, m, d = map(int, day.split("-"))

        class Clock:
            @staticmethod
            def now(tz):
                return datetime(y, m, d, 12, tzinfo=tz)

        monkeypatch.setattr(sessions, "datetime", Clock)

    set_today("2025-01-14")
    return set_today


def _mandate(tmp_path, mode="long_short", name="mixed"):
    spec = FundSpec(schema_version=2, name=name, strategies=[custom_strategy(["buffett", "druckenmiller"])], risk={"max_position_pct": 0.25, "max_gross_exposure": 1})
    spec.strategies[0].blend.mode = mode
    path = tmp_path / f"{name}.yaml"
    path.write_text(yaml.safe_dump(spec.model_dump()))
    return path


def _main(monkeypatch, *argv):
    root = Path(run.PAPER_DIR).parent if run.PAPER_DIR is not None else Path(os.environ["HEDGE_FUND_TEST_ROOT"])
    if argv and argv[0] == "backtest" and "--enable-network" not in argv:
        argv = ("--enable-network", *argv)
    if argv and argv[0] == "paper":
        action = argv[1] if len(argv) > 1 else None
        if action == "tick" and "--enable-network" not in argv:
            argv = ("--enable-network", *argv)
        if action == "approve" and "--now" in argv and "--enable-network" not in argv:
            argv = ("--enable-network", *argv)
    monkeypatch.setattr(sys, "argv", ["aihf", "--root", str(root), *argv])
    run.main()


def _enroll_test_root(root):
    from hedge_fund.test_support.handover import enroll_synthetic_root

    enroll_synthetic_root(root)


def test_cli_requires_explicit_root(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["aihf"])

    with pytest.raises(SystemExit) as missing:
        run.main()

    assert missing.value.code == 2
    assert "--root" in capsys.readouterr().err


def test_offline_handover_cli_skips_runtime_and_mandate_setup(tmp_path, monkeypatch, capsys):
    root = tmp_path / "fresh-root"
    root.mkdir()
    monkeypatch.setattr(run, "PAPER_DIR", root / "paper")
    forbidden = Mock(side_effect=AssertionError("offline handover initialized the engine"))
    monkeypatch.setattr(run, "_load_runtime", forbidden)
    monkeypatch.setattr(run, "ensure_mandates_dir", forbidden)
    monkeypatch.setattr(paths, "load_root_dotenv", forbidden)

    _main(monkeypatch, "handover", "enroll-fresh")

    enrolled = json.loads(capsys.readouterr().out)
    assert enrolled["state"] == "enrolled"
    assert enrolled["mode"] == "fresh"
    assert (root / "runtime" / "private" / "v1" / "handover.json").is_file()
    assert not (root / "mandates").exists()
    assert forbidden.call_count == 0


def test_cli_reports_unenrolled_mandate_writer_denial(tmp_path, monkeypatch, capsys):
    root = tmp_path / "unenrolled-root"
    root.mkdir()
    monkeypatch.setattr(run, "PAPER_DIR", root / "paper")
    monkeypatch.setattr(run, "_load_runtime", Mock())
    monkeypatch.setattr(run, "ensure_mandates_dir", paths.ensure_mandates_dir)

    with pytest.raises(SystemExit) as denied:
        _main(monkeypatch)

    assert denied.value.code == 2
    assert "offline enrollment" in capsys.readouterr().err
    assert not (root / "mandates").exists()


def test_cli_writer_admission_rejects_missing_handover_with_admission_artifacts(
    tmp_path,
    monkeypatch,
):
    from hedge_fund.runtime.handover import enroll_fresh, HANDOVER_PATH
    from hedge_fund.runtime.root import RootContext

    root = tmp_path / "former-enrolled-root"
    root.mkdir()
    with RootContext.open(root) as context:
        enroll_fresh(context)
        (root / HANDOVER_PATH).unlink()
        monkeypatch.setattr(paths, "root_context", lambda: context)

        with pytest.raises(run.PaperWriterDenied, match="blocked"):
            with run._paper_writer_admission():
                pytest.fail("orphaned admission state entered legacy writer mode")


def test_unenrolled_explicit_root_paper_writer_denies_before_deploy(tmp_path, monkeypatch, capsys, offline):
    path = _mandate(tmp_path)
    forbidden = Mock(side_effect=AssertionError("unenrolled root reached deployment effects"))
    monkeypatch.setattr(run, "deploy", forbidden)

    with pytest.raises(SystemExit) as denied:
        _main(monkeypatch, "paper", "create", "alpha", "--mandate", str(path), "--universe", "AAPL")

    assert denied.value.code == 1
    assert "offline enrollment" in capsys.readouterr().err
    assert forbidden.call_count == 0
    assert not (tmp_path / "paper").exists()


def test_handover_cli_inspects_then_migrates_with_exact_attestation(
    tmp_path,
    monkeypatch,
    capsys,
):
    root = tmp_path / "legacy-root"
    root.mkdir()
    (root / "mandates").mkdir()
    monkeypatch.setattr(run, "PAPER_DIR", root / "paper")
    forbidden = Mock(side_effect=AssertionError("offline handover initialized the engine"))
    monkeypatch.setattr(run, "_load_runtime", forbidden)
    monkeypatch.setattr(paths, "load_root_dotenv", forbidden)

    _main(monkeypatch, "handover", "inspect")
    inspection = json.loads(capsys.readouterr().out)
    assert inspection["state"] == "unenrolled"
    assert inspection["heads"] == {}
    assert inspection["inventory_digest"]
    assert inspection["operator_attestation"]

    _main(
        monkeypatch,
        "handover",
        "migrate-existing",
        "--inventory-digest",
        inspection["inventory_digest"],
        "--operator-attestation",
        inspection["operator_attestation"],
    )
    migrated = json.loads(capsys.readouterr().out)
    assert migrated["state"] == "enrolled"
    assert migrated["mode"] == "migrate-existing"
    assert migrated["inventory_digest"] == inspection["inventory_digest"]
    assert forbidden.call_count == 0


def test_handover_cli_relocates_legacy_root_without_writing_source(tmp_path, monkeypatch, capsys):
    from hedge_fund.paper.deployed import deploy

    source = tmp_path / "legacy-source"
    (source / "paper").mkdir(parents=True)
    deploy("alpha", FundSpec(schema_version=2, name="alpha", strategies=[custom_strategy(["buffett"])], risk={"max_position_pct": 0.25, "max_gross_exposure": 1}), ["AAPL"], root=source / "paper")
    (source / ".env").write_text("SYNTHETIC_ONLY=1\n", encoding="utf-8")
    before = {item.relative_to(source).as_posix(): (item.is_dir() or item.read_bytes()) for item in sorted(source.rglob("*"))}
    target = tmp_path / "native-target"
    target.mkdir()
    forbidden = Mock(side_effect=AssertionError("offline handover initialized the engine"))
    monkeypatch.setattr(run, "_load_runtime", forbidden)
    monkeypatch.setattr(paths, "load_root_dotenv", forbidden)

    monkeypatch.setattr(run, "PAPER_DIR", source / "paper")
    _main(monkeypatch, "handover", "inspect-source")
    described = json.loads(capsys.readouterr().out)
    assert described["funds"] == 1

    monkeypatch.setattr(run, "PAPER_DIR", target / "paper")
    _main(monkeypatch, "handover", "relocate-from", str(source), "--content-digest", described["content_digest"])
    relocated = json.loads(capsys.readouterr().out)
    assert relocated == {"state": "enrolled", "mode": "relocated", "inventory_digest": relocated["inventory_digest"], "write_authority": "protocol-native"}
    assert before == {item.relative_to(source).as_posix(): (item.is_dir() or item.read_bytes()) for item in sorted(source.rglob("*"))}
    assert not (target / ".env").exists()
    assert forbidden.call_count == 0

    with pytest.raises(SystemExit) as again:
        _main(monkeypatch, "handover", "relocate-from", str(source), "--content-digest", described["content_digest"])
    assert again.value.code == 2


def test_cli_paper_writer_denies_attested_migration_as_ownership_unknown(tmp_path, monkeypatch):
    from hedge_fund.runtime.handover import build_head_inventory, inventory_digest, migrate_existing, OPERATOR_ATTESTATION
    from hedge_fund.runtime.root import RootContext

    root = tmp_path / "attested-root"
    (root / "mandates").mkdir(parents=True)
    with RootContext.open(root) as context:
        migrate_existing(context, expected_inventory_digest=inventory_digest(build_head_inventory(context)), operator_attestation=OPERATOR_ATTESTATION)
        monkeypatch.setattr(paths, "root_context", lambda: context)
        with pytest.raises(run.PaperWriterDenied, match="ownership-unknown \\(attested-migration-read-only\\)"):
            with run._paper_writer_admission():
                pytest.fail("attested root entered writer mode")


def test_handover_inspects_orphaned_admission_for_explicit_offline_recovery(
    tmp_path,
    monkeypatch,
    capsys,
):
    from hedge_fund.runtime.handover import enroll_fresh, HANDOVER_PATH
    from hedge_fund.runtime.root import RootContext

    root = tmp_path / "orphaned-admission-root"
    root.mkdir()
    with RootContext.open(root) as context:
        enroll_fresh(context)
        (root / HANDOVER_PATH).unlink()
    monkeypatch.setattr(run, "PAPER_DIR", root / "paper")

    _main(monkeypatch, "handover", "inspect")
    inspection = json.loads(capsys.readouterr().out)
    assert inspection["state"] == "invalid"
    assert inspection["heads"] == {}
    assert inspection["inventory_digest"]
    assert not (root / HANDOVER_PATH).exists()

    _main(
        monkeypatch,
        "handover",
        "migrate-existing",
        "--inventory-digest",
        inspection["inventory_digest"],
        "--operator-attestation",
        inspection["operator_attestation"],
    )
    migrated = json.loads(capsys.readouterr().out)
    assert migrated["state"] == "enrolled"
    assert migrated["mode"] == "migrate-existing"


def test_handover_cli_refuses_any_legacy_runner_pid_without_signaling(
    tmp_path,
    monkeypatch,
    capsys,
):
    root = tmp_path / "legacy-root"
    runner = root / "paper" / "alpha" / "runner.pid"
    runner.parent.mkdir(parents=True)
    runner.write_text("stale-or-unknown", encoding="utf-8")
    before = runner.read_bytes()
    monkeypatch.setattr(run, "PAPER_DIR", root / "paper")

    with pytest.raises(SystemExit) as exc:
        _main(monkeypatch, "handover", "inspect")

    assert exc.value.code == 2
    assert "runner.pid" in capsys.readouterr().err
    assert runner.read_bytes() == before
    assert not (root / "runtime" / "private" / "v1" / "handover.json").exists()


def test_documented_cli_examples_include_explicit_root():
    commands = [line.strip() for line in (run.__doc__ or "").splitlines() if line.strip().startswith("aihf ")]

    assert commands
    assert all(command.startswith("aihf --root ") for command in commands)


def test_supported_container_launchers_pass_explicit_root():
    repository = Path(__file__).resolve().parents[1]
    compose = yaml.safe_load((repository / "docker-compose.yml").read_text(encoding="utf-8"))
    linux_compose = yaml.safe_load((repository / "docker-compose.linux.yml").read_text(encoding="utf-8"))

    dockerfile = (repository / "Dockerfile").read_text(encoding="utf-8")
    web_dockerfile = (repository / "Dockerfile.web").read_text(encoding="utf-8")
    assert 'ENTRYPOINT ["aihf", "--root", "/data"]' in dockerfile
    assert 'ENTRYPOINT ["aihf-web", "--root", "/data"]' in web_dockerfile
    assert 'CMD ["--port", "8876", "--container-bind"]' in web_dockerfile
    for service_name in ("runner", "runner-weekly", "tui"):
        service = compose["services"][service_name]
        assert service["entrypoint"] == ["aihf", "--root", "/data"]
        assert "--root" not in service.get("command", [])
    web_service = compose["services"]["web"]
    assert web_service["entrypoint"] == ["aihf-web", "--root", "/data"]
    assert web_service["command"] == ["--port", "8876", "--container-bind"]
    assert web_service["ports"] == ["127.0.0.1:8876:8876"]
    assert "--root" in linux_compose["services"]["tui-web"]["entrypoint"]
    assert "/data" in linux_compose["services"]["tui-web"]["entrypoint"]


def test_makefile_write_targets_require_caller_selected_absolute_root():
    repository = Path(__file__).resolve().parents[1]
    makefile = (repository / "Makefile").read_text(encoding="utf-8")

    assert "AIHF_ROOT ?=\n" in makefile
    assert "AIHF_ROOT ?= $(HOME)" not in makefile
    assert "dev: require-root" in makefile
    assert "web-local: require-root" in makefile
    assert "os.path.isabs(sys.argv[1])" in makefile
    assert "poetry run aihf --root '$(AIHF_ROOT)'" in makefile
    assert 'poetry run aihf-web --root "$(AIHF_ROOT)"' in makefile


@pytest.mark.parametrize("command", ["backtest", "create"])
@pytest.mark.parametrize("unversioned", [False, True])
def test_cli_rejects_invalid_configuration_before_clients(tmp_path, monkeypatch, capsys, command, unversioned):
    spec = FundSpec(schema_version=2, name="mixed", strategies=[custom_strategy(["buffett", "druckenmiller"])], risk={"max_position_pct": 0.25, "max_gross_exposure": 1})
    data = spec.model_dump()
    if unversioned:
        data.pop("schema_version")
    else:
        data["strategies"][0]["blend"]["mode"] = "invalid"
    path = tmp_path / "fund.yaml"
    path.write_text(yaml.safe_dump(data))
    original = path.read_bytes()
    forbidden = Mock(side_effect=AssertionError("external activity"))
    monkeypatch.setattr(run, "ensure_mandates_dir", lambda: tmp_path)
    monkeypatch.setattr(run, "Fund", forbidden)
    monkeypatch.setattr(run, "make_data_client", forbidden)
    monkeypatch.setattr(run, "deploy", forbidden)
    monkeypatch.setattr(run, "PAPER_DIR", tmp_path / "paper")
    argv = ["backtest", str(path), "--universe", "AAPL"] if command == "backtest" else ["paper", "create", "alpha", "--mandate", str(path), "--universe", "AAPL"]
    with pytest.raises(SystemExit) as exc:
        _main(monkeypatch, *argv)
    assert exc.value.code == 2
    assert forbidden.call_count == 0
    output = capsys.readouterr()
    assert output.out == ""
    assert ("older format" if unversioned else "blend.mode") in output.err
    assert path.read_bytes() == original
    assert not (tmp_path / "paper").exists()


def test_backtest_without_network_consent_denies_before_provider_or_result_effects(
    tmp_path,
    monkeypatch,
    capsys,
):
    path = _mandate(tmp_path)
    monkeypatch.setenv("HEDGE_FUND_LLM_MODEL", "gpt-6-sol")
    monkeypatch.setenv("OPENAI_API_KEY", "fixture-provider-secret")
    forbidden = Mock(side_effect=AssertionError("provider/result effect before consent"))
    monkeypatch.setattr(run, "PAPER_DIR", tmp_path / "paper")
    monkeypatch.setattr(run, "ensure_mandates_dir", lambda: tmp_path / "mandates")
    monkeypatch.setattr(run, "make_data_client", forbidden)
    monkeypatch.setattr(run, "_cli_fund", forbidden)
    monkeypatch.setattr(run, "backtest_fund", forbidden)
    monkeypatch.setattr(run, "save_result", forbidden)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "aihf",
            "--root",
            str(tmp_path),
            "backtest",
            str(path),
            "--universe",
            "AAPL",
            "--start",
            "2025-01-06",
            "--end",
            "2025-01-07",
        ],
    )

    with pytest.raises(SystemExit) as denied:
        run.main()

    output = capsys.readouterr()
    assert denied.value.code == 2
    assert "explicit --enable-network" in output.err
    assert "fixture-provider-secret" not in output.out + output.err
    assert forbidden.call_count == 0
    assert not (tmp_path / "research").exists()
    assert not (tmp_path / "paper").exists()


def test_paid_provider_requires_explicit_consent_even_with_network_and_env_key(
    tmp_path,
    monkeypatch,
    capsys,
):
    from hedge_fund.runtime.handover import enroll_fresh
    from hedge_fund.runtime.root import RootContext

    root = tmp_path / "paid-consent-root"
    root.mkdir()
    with RootContext.open(root) as context:
        enroll_fresh(context)
    path = _mandate(root, name="paid-consent")
    monkeypatch.setattr(run, "PAPER_DIR", root / "paper")
    monkeypatch.setattr(run, "ensure_mandates_dir", lambda: root / "mandates")
    monkeypatch.setattr(paths, "RESEARCH_DIR", root / "research")
    monkeypatch.setenv("HEDGE_FUND_DATA_PROVIDER", "fd")
    monkeypatch.setenv("FINANCIAL_DATASETS_API_KEY", "ambient-fixture-secret")
    forbidden = Mock(side_effect=AssertionError("paid provider/result effect before consent"))
    monkeypatch.setattr(run, "make_data_client", forbidden)
    monkeypatch.setattr(run, "_cli_fund", forbidden)
    monkeypatch.setattr(run, "backtest_fund", forbidden)
    monkeypatch.setattr(run, "save_result", forbidden)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "aihf",
            "--root",
            str(root),
            "--enable-network",
            "--model",
            "gemma3:4b",
            "backtest",
            str(path),
            "--universe",
            "AAPL",
            "--start",
            "2025-01-06",
            "--end",
            "2025-01-07",
        ],
    )

    with pytest.raises(SystemExit) as denied:
        run.main()

    output = capsys.readouterr()
    assert denied.value.code == 2
    assert "paid dispatch requires --authorize-paid-provider fd" in output.err
    assert "ambient-fixture-secret" not in output.out + output.err
    assert forbidden.call_count == 0
    assert not (root / "research").exists()
    assert not (root / "paper").exists()

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "aihf",
            "--root",
            str(root),
            "--enable-network",
            "--model",
            "gemma3:4b",
            "backtest",
            str(path),
            "--universe",
            "AAPL",
            "--start",
            "2025-01-06",
            "--end",
            "2025-01-07",
            "--authorize-paid-provider",
            "fd",
            "--paid-max-calls",
            "1",
            "--paid-max-cost-usd",
            "1",
            "--paid-max-attempt-cost-usd",
            "0.16",
        ],
    )
    with pytest.raises(SystemExit) as tier_denied:
        run.main()

    tier_output = capsys.readouterr()
    assert tier_denied.value.code == 2
    assert "requires --confirm-fd-self-service-pricing" in tier_output.err
    assert forbidden.call_count == 0
    assert not (root / "research").exists()
    assert not (root / "paper").exists()


def test_paid_fd_cli_backtest_uses_guarded_client_and_fake_transport(
    tmp_path,
    monkeypatch,
    capsys,
    offline,
):
    from decimal import Decimal

    import httpx

    from hedge_fund.backtesting.test_fund import FakeAnalyst
    from hedge_fund.data import make_data_client as production_factory
    from hedge_fund.fund import Fund
    from hedge_fund.runtime.admission import AdmissionCoordinator, RootOwnerLease
    from hedge_fund.runtime.credentials import CredentialStore
    from hedge_fund.runtime.handover import enroll_fresh
    from hedge_fund.runtime.policy import ProviderTarget
    from hedge_fund.runtime.root import RootContext

    root = tmp_path / "paid-cli-root"
    root.mkdir()
    secret = "synthetic-fd-cli-key"
    with RootContext.open(root) as context:
        enroll_fresh(context)
        with RootOwnerLease.acquire(context) as owner:
            CredentialStore(
                context,
                AdmissionCoordinator(context, owner_lease=owner),
            ).save("fd", secret, expected_version=0)
    path = _mandate(root, name="paid-cli")
    monkeypatch.setattr(run, "PAPER_DIR", root / "paper")
    monkeypatch.setenv("HEDGE_FUND_DATA_PROVIDER", "fd")
    monkeypatch.setenv("HEDGE_FUND_LLM_MODEL", "gemma3:4b")
    monkeypatch.setattr(
        "hedge_fund.runtime.endpoints._resolve_system",
        lambda _host, _port: ["8.8.8.8"],
    )
    requests = []
    dispatches = []
    price_rows = [
        {
            "open": 100.0,
            "high": 100.0,
            "low": 100.0,
            "close": 100.0,
            "volume": 1000,
            "time": f"2025-01-{day:02d}T00:00:00Z",
        }
        for day in (6, 7, 8)
    ]

    def handle(request):
        requests.append(request)
        assert request.url.host == "api.financialdatasets.ai"
        assert request.headers.get("x-api-key") == secret
        return httpx.Response(
            200,
            json={"prices": price_rows, "next_page_url": None},
            request=request,
        )

    def guarded_factory(*, provider, dispatch, api_key):
        dispatches.append(dispatch)
        return production_factory(
            provider=provider,
            dispatch=dispatch,
            api_key=api_key,
            inner_transport=httpx.MockTransport(handle),
        )

    def build_fund(spec, blind=False, llm_factory=None, breakpoints_dispatch=None):
        del blind, llm_factory, breakpoints_dispatch
        return Fund(
            spec,
            models={strategy.name: [FakeAnalyst(model.name, {"AAPL": 0.6}) for model in strategy.models] for strategy in spec.strategies},
        )

    monkeypatch.setattr(run, "make_data_client", guarded_factory)
    monkeypatch.setattr(run, "Fund", build_fund)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "aihf",
            "--root",
            str(root),
            "--enable-network",
            "backtest",
            str(path),
            "--universe",
            "AAPL",
            "--start",
            "2025-01-06",
            "--end",
            "2025-01-08",
            "--rebalance",
            "monthly",
            "--authorize-paid-provider",
            "fd",
            "--confirm-fd-self-service-pricing",
            "--paid-max-calls",
            "100",
            "--paid-max-cost-usd",
            "16",
            "--paid-max-attempt-cost-usd",
            "0.16",
        ],
    )

    run.main()

    output = capsys.readouterr()
    assert "Paid dispatch authorized: fd" in output.err
    assert secret not in output.out + output.err
    assert len(requests) > 0
    assert len(dispatches) == 1
    target = ProviderTarget(kind="data", provider="fd")
    authorization = dispatches[0]._one_shot[target.identity]
    assert authorization.calls_reserved == len(requests)
    assert authorization.cost_reserved == Decimal("0.16") * len(requests)
    assert authorization.calls_reserved <= authorization.max_calls
    assert (root / "research").exists()
    assert not (root / "paper").exists()


def test_no_arguments_launches_the_app(monkeypatch):
    launched = Mock()
    monkeypatch.setattr(run, "ensure_mandates_dir", lambda: None)
    monkeypatch.setitem(sys.modules, "hedge_fund.tui.app", Mock(HedgeFundApp=lambda: launched))
    _main(monkeypatch)
    launched.run.assert_called_once()


@pytest.mark.parametrize("mode", ["long_only", "long_short", "dollar_neutral"])
def test_backtest_prints_json_and_files_a_research_copy(tmp_path, monkeypatch, capsys, offline, mode):
    path = _mandate(tmp_path, mode)
    _enroll_test_root(tmp_path)
    _main(monkeypatch, "backtest", str(path), "--universe", "AAPL,MSFT", "--start", "2025-01-06", "--end", "2025-01-13")
    output = capsys.readouterr()
    result = json.loads(output.out)
    assert result["dates"] == ["2025-01-06", "2025-01-07", "2025-01-08", "2025-01-13"]
    # Monday decides, Tuesday executes; the next Monday decides again.
    assert [r["executed"] is not None for r in result["records"]] == [False, True, False, False]
    assert result["records"][-1]["decision"] is not None
    cycle = result["records"][1]["executed"]
    assert cycle["positions"]["AAPL"] > 0
    assert (cycle["positions"].get("MSFT", 0) < 0) == (mode != "long_only")
    if mode == "dollar_neutral":
        assert sum(cycle["final_weights"].values()) == pytest.approx(0)
    assert "1 rebalances" in output.err and "sessions" in output.err
    saved = list((tmp_path / "research").glob("mixed-2025-01-06-2025-01-13-*.json"))
    assert len(saved) == 1 and json.loads(saved[0].read_text()) == result
    assert not (tmp_path / "paper").exists()  # research never touches the paper funds


def test_backtest_defaults_end_to_the_latest_completed_session(tmp_path, monkeypatch, capsys, offline):
    path = _mandate(tmp_path)
    _enroll_test_root(tmp_path)
    _main(monkeypatch, "backtest", str(path), "--universe", "AAPL", "--start", "2025-01-06")
    result = json.loads(capsys.readouterr().out)
    assert result["end"] == "2025-01-13"


def test_backtest_without_rebalance_key_defaults_to_weekly(tmp_path, monkeypatch, capsys, offline):
    from hedge_fund.pipeline import session as pipeline_session

    path = _mandate(tmp_path)
    mandate = yaml.safe_load(path.read_text())
    mandate.pop("rebalance")
    path.write_text(yaml.safe_dump(mandate))
    _enroll_test_root(tmp_path)
    # Freeze revision stamp → compare CLI JSON across commits.
    monkeypatch.setattr(pipeline_session, "code_version", lambda: "2.6.1+cd662f4")

    _main(monkeypatch, "backtest", str(path), "--universe", "AAPL,MSFT", "--start", "2025-01-06", "--end", "2025-01-13")
    output = capsys.readouterr()
    result = json.loads(output.out)

    assert result["rebalance"] == "weekly"
    assert "1 rebalances" in output.err
    assert hashlib.sha256(output.out.encode()).hexdigest() == "8dbc24919e7ae535220364a45f9f9c8b04863f6afa4ad07c1db1872275f38623"


def test_backtest_rebalance_override_changes_monthly_cycle_count(tmp_path, monkeypatch, capsys, offline):
    from hedge_fund.backtesting.test_fund import FakeDataClient

    dates = ["2025-01-06", "2025-01-07", "2025-01-08", "2025-01-13", "2025-02-03", "2025-02-04", "2025-02-10", "2025-03-03"]
    series = {ticker: {day: 100.0 + index for index, day in enumerate(dates)} for ticker in ("AAPL", "MSFT", "SPY")}

    class MultiMonthClient(FakeDataClient):
        def __init__(self, *_args, **_kwargs):
            super().__init__(series)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(run, "make_data_client", MultiMonthClient)
    path = _mandate(tmp_path)
    _enroll_test_root(tmp_path)
    original = path.read_bytes()
    args = ("backtest", str(path), "--universe", "AAPL,MSFT", "--start", dates[0], "--end", dates[-1])
    offline("2025-03-04")

    _main(monkeypatch, *args)
    weekly = json.loads(capsys.readouterr().out)
    _main(monkeypatch, *args, "--rebalance", "monthly")
    monthly = json.loads(capsys.readouterr().out)

    assert weekly["rebalance"] == "weekly"
    assert monthly["rebalance"] == "monthly"
    assert monthly["metrics"]["n_cycles"] < weekly["metrics"]["n_cycles"]
    assert path.read_bytes() == original


def test_paper_create_rebalance_override_is_frozen_and_reported(tmp_path, monkeypatch, capsys, offline):
    path = _mandate(tmp_path)
    original = path.read_bytes()
    _enroll_test_root(tmp_path)

    _main(monkeypatch, "paper", "create", "alpha", "--mandate", str(path), "--universe", "AAPL", "--rebalance", "daily")
    output = capsys.readouterr()
    deployed = yaml.safe_load((tmp_path / "paper" / "alpha" / "fund.yaml").read_text())

    assert output.out == ""
    assert "daily" in output.err
    assert deployed["spec"]["rebalance"] == "daily"
    assert path.read_bytes() == original


@pytest.mark.parametrize("command", ["backtest", "create"])
def test_invalid_rebalance_override_is_usage_error_before_engine_work(tmp_path, monkeypatch, capsys, offline, command):
    forbidden = Mock(side_effect=AssertionError("engine work ran before argument validation"))
    monkeypatch.setattr(run, "load_spec", forbidden)
    monkeypatch.setattr(run, "Fund", forbidden)
    monkeypatch.setattr(run, "make_data_client", forbidden)
    monkeypatch.setattr(run, "deploy", forbidden)
    argv = ["backtest", "unused.yaml", "--universe", "AAPL", "--rebalance", "hourly"] if command == "backtest" else ["paper", "create", "alpha", "--mandate", "unused.yaml", "--universe", "AAPL", "--rebalance", "hourly"]

    with pytest.raises(SystemExit) as exc:
        _main(monkeypatch, *argv)

    output = capsys.readouterr()
    assert exc.value.code == 2
    assert output.out == ""
    assert "hourly" in output.err
    assert all(value in output.err for value in ("minute", "daily", "weekly", "monthly"))
    assert forbidden.call_count == 0


def test_paper_create_overrides_minute_to_daily_without_minute_fields(tmp_path, monkeypatch, capsys, offline):
    path = _mandate(tmp_path)
    mandate = yaml.safe_load(path.read_text())
    mandate.update(rebalance="minute", interval=0.5, window={"start": "09:30", "end": "12:00"})
    path.write_text(yaml.safe_dump(mandate))
    original = path.read_bytes()
    _enroll_test_root(tmp_path)

    _main(monkeypatch, "paper", "create", "fast", "--mandate", str(path), "--universe", "AAPL", "--rebalance", "daily")
    output = capsys.readouterr()
    deployed = yaml.safe_load((tmp_path / "paper" / "fast" / "fund.yaml").read_text())
    deployed_spec = deployed["spec"]

    assert output.out == ""
    assert "daily" in output.err
    assert deployed_spec["rebalance"] == "daily"
    assert "interval" not in deployed_spec and "window" not in deployed_spec
    assert path.read_bytes() == original


def test_paper_create_overrides_day_grid_to_minute_with_standard_defaults(tmp_path, monkeypatch, capsys, offline):
    path = _mandate(tmp_path)
    mandate = yaml.safe_load(path.read_text())
    mandate["rebalance"] = "daily"
    mandate.pop("interval", None)
    mandate.pop("window", None)
    path.write_text(yaml.safe_dump(mandate))
    original = path.read_bytes()
    _enroll_test_root(tmp_path)

    _main(monkeypatch, "paper", "create", "fast", "--mandate", str(path), "--universe", "AAPL", "--rebalance", "minute")
    output = capsys.readouterr()
    deployed = yaml.safe_load((tmp_path / "paper" / "fast" / "fund.yaml").read_text())
    deployed_spec = deployed["spec"]

    assert output.out == ""
    rendered = " ".join(output.err.split())
    assert "every 1m" in rendered and "09:30–16:00 ET" in rendered
    assert deployed_spec["rebalance"] == "minute"
    assert deployed_spec["interval"] == 1.0
    assert deployed_spec["window"] == {"start": "09:30", "end": "16:00"}
    assert path.read_bytes() == original


@pytest.mark.parametrize("action", ["tick", "run"])
def test_deployed_fund_commands_do_not_accept_rebalance_override(capsys, action):
    parser = run._parser()

    with pytest.raises(SystemExit) as exc:
        parser.parse_args(
            [
                "--root",
                os.environ["HEDGE_FUND_TEST_ROOT"],
                "paper",
                action,
                "alpha",
                "--rebalance",
                "daily",
            ]
        )

    assert exc.value.code == 2
    assert "unrecognized arguments: --rebalance daily" in capsys.readouterr().err


def test_paper_flow_resume_requires_reconciliation_receipt(tmp_path, monkeypatch, capsys, offline):
    set_today = offline
    path = _mandate(tmp_path)
    _enroll_test_root(tmp_path)

    set_today("2025-01-07")  # deployed Tuesday morning: Monday 01-06 is the latest close
    _main(monkeypatch, "paper", "create", "alpha", "--mandate", str(path), "--universe", "AAPL, MSFT")
    err = capsys.readouterr().err
    assert "alpha" in err and "deployed" in err
    with pytest.raises(SystemExit):
        _main(monkeypatch, "paper", "create", "alpha", "--mandate", str(path), "--universe", "AAPL")
    assert "already exists" in capsys.readouterr().err

    _main(monkeypatch, "paper", "list")
    listed = capsys.readouterr().out
    assert "alpha" in listed and "not started" in listed

    _main(monkeypatch, "paper", "tick", "alpha")
    output = capsys.readouterr()
    record = json.loads(output.out)
    assert record["session"] == "2025-01-06" and record["decision"] is not None and record["executed"] is None
    assert "decided on" in output.err and "executes next close" in output.err

    with pytest.raises(SystemExit) as exc:
        _main(monkeypatch, "paper", "tick", "alpha")  # nothing new has closed
    assert exc.value.code == 1
    assert "no completed SPY session after 2025-01-06" in capsys.readouterr().err

    set_today("2025-01-08")
    _main(monkeypatch, "paper", "tick", "alpha")
    output = capsys.readouterr()
    record = json.loads(output.out)
    assert record["session"] == "2025-01-07" and record["executed"]["positions"]["AAPL"] > 0
    assert "executed" in output.err

    _main(monkeypatch, "paper", "status", "alpha")
    status = capsys.readouterr().out
    assert "alpha" in status and "2 sessions" in status and "last 2025-01-07" in status
    assert "AAPL:" in status and "book:" in status and "HALTED" not in status

    _main(monkeypatch, "paper", "halt", "alpha", "--reason", "operator review")
    _main(monkeypatch, "paper", "status", "alpha")
    assert "HALTED: operator review" in capsys.readouterr().out
    set_today("2025-01-09")
    with pytest.raises(SystemExit) as exc:
        _main(monkeypatch, "paper", "tick", "alpha")
    assert exc.value.code == 1 and "halted" in capsys.readouterr().err

    control = tmp_path / "paper" / "alpha" / "control.json"
    before_resume = control.read_bytes()
    with pytest.raises(SystemExit) as exc:
        _main(monkeypatch, "paper", "resume", "alpha")
    assert exc.value.code == 1
    assert "reconciliation receipt" in capsys.readouterr().err
    assert control.read_bytes() == before_resume
    with pytest.raises(SystemExit) as exc:
        _main(monkeypatch, "paper", "tick", "alpha")
    assert exc.value.code == 1 and "halted" in capsys.readouterr().err
    _main(monkeypatch, "paper", "list")
    listed = capsys.readouterr().out
    assert "2 sessions" in listed and "HALTED: operator review" in listed

    with pytest.raises(SystemExit) as exc:
        _main(monkeypatch, "paper", "status", "nobody")
    assert exc.value.code == 2 and "no paper fund named 'nobody'" in capsys.readouterr().err


def test_cli_interrupted_redo_denies_before_provider_and_allows_halt(tmp_path, monkeypatch, capsys, offline):
    from hedge_fund.paper.ledger import Ledger
    from hedge_fund.runtime.admission import AdmissionCoordinator, RootOwnerLease
    from hedge_fund.runtime.root import RootContext

    path = _mandate(tmp_path)
    _enroll_test_root(tmp_path)
    offline("2025-01-07")
    _main(monkeypatch, "paper", "create", "alpha", "--mandate", str(path), "--universe", "AAPL")
    _main(monkeypatch, "paper", "tick", "alpha")
    capsys.readouterr()
    ledger = Ledger(tmp_path / "paper" / "alpha")
    with RootContext.open(tmp_path) as root:
        owner = RootOwnerLease.acquire(root)
        try:
            admission = AdmissionCoordinator(root, owner_lease=owner)
            with paths.bound_root(root), admission.manual_session("alpha", timeout=0):
                ledger.begin_redo(ledger.latest())
        finally:
            owner.close()

    def forbidden(*_args, **_kwargs):
        pytest.fail("interrupted redo reached a data provider")

    monkeypatch.setattr(run, "make_data_client", forbidden)
    with pytest.raises(SystemExit) as exc:
        _main(monkeypatch, "paper", "tick", "alpha")
    assert exc.value.code == 1
    assert "interrupted redo" in capsys.readouterr().err
    _main(monkeypatch, "paper", "halt", "alpha", "--reason", "emergency")
    assert ledger.halted() == "emergency"


def test_cli_halt_does_not_wait_for_a_busy_control_lane(tmp_path, monkeypatch, capsys, offline):
    from threading import Event, Thread

    from hedge_fund.paper.ledger import Ledger
    from hedge_fund.runtime.admission import AdmissionCoordinator, RootOwnerLease
    from hedge_fund.runtime.root import RootContext

    path = _mandate(tmp_path)
    _enroll_test_root(tmp_path)
    offline("2025-01-07")
    _main(monkeypatch, "paper", "create", "alpha", "--mandate", str(path), "--universe", "AAPL")
    capsys.readouterr()
    entered = Event()
    release = Event()
    failures = []
    with RootContext.open(tmp_path) as root:
        owner = RootOwnerLease.acquire(root)
        admission = AdmissionCoordinator(root, owner_lease=owner)

        def hold_control():
            try:
                with admission.control_lane("alpha"):
                    entered.set()
                    if not release.wait(timeout=10):
                        raise TimeoutError("test did not release control")
            except BaseException as exc:
                failures.append(exc)

        worker = Thread(target=hold_control, name="cli-busy-control")
        worker.start()
        try:
            assert entered.wait(timeout=10), failures
            _main(monkeypatch, "paper", "halt", "alpha", "--reason", "emergency")
        finally:
            release.set()
            worker.join(timeout=10)
            owner.close()
        assert not worker.is_alive()
        assert failures == []
    assert Ledger(tmp_path / "paper" / "alpha").halted() == "emergency"


def test_cli_halt_does_not_recreate_a_fund_archived_after_lookup(tmp_path, monkeypatch, capsys, offline):
    from hedge_fund.paper.ledger import Ledger
    from hedge_fund.runtime.admission import AdmissionCoordinator, RootOwnerLease
    from hedge_fund.runtime.lifecycle import LifecycleArchiveStore
    from hedge_fund.runtime.root import RootContext

    path = _mandate(tmp_path)
    _enroll_test_root(tmp_path)
    offline("2025-01-07")
    _main(monkeypatch, "paper", "create", "alpha", "--mandate", str(path), "--universe", "AAPL")
    capsys.readouterr()
    lookup = run._fund_dir
    archived = []

    def archive_after_lookup(name, parser):
        directory = lookup(name, parser)
        with RootContext.open(tmp_path) as root:
            with RootOwnerLease.acquire(root) as owner:
                store = LifecycleArchiveStore(root, AdmissionCoordinator(root, owner_lease=owner))
                preview = store.preview("deployment", name)
                archived.append(
                    store.archive("deployment", name, expected_digest=preview["digest"], archive_id="d" * 32)
                )
        return directory

    monkeypatch.setattr(run, "_fund_dir", archive_after_lookup)
    error = None
    try:
        _main(monkeypatch, "paper", "halt", "alpha", "--reason", "emergency")
    except SystemExit as exc:
        error = exc

    assert archived and archived[0]["state"] == "archived"
    assert not (tmp_path / "paper" / "alpha").exists()
    assert Ledger(tmp_path / archived[0]["archive_path"]).halted() is None
    assert error is not None and error.code != 0
    assert "halted:" not in capsys.readouterr().out


def test_cli_halt_rejects_a_replacement_deployment_after_lookup(tmp_path, monkeypatch, capsys, offline):
    from contextlib import contextmanager
    from threading import Event, Thread

    from hedge_fund import paths
    from hedge_fund.paper.deployed import deploy, load_deployed
    from hedge_fund.paper.ledger import Ledger
    from hedge_fund.runtime.admission import AdmissionCoordinator, RootOwnerLease
    from hedge_fund.runtime.lifecycle import LifecycleArchiveStore
    from hedge_fund.runtime.root import RootContext

    path = _mandate(tmp_path)
    _enroll_test_root(tmp_path)
    offline("2025-01-07")
    _main(monkeypatch, "paper", "create", "alpha", "--mandate", str(path), "--universe", "AAPL")
    capsys.readouterr()
    directory = tmp_path / "paper" / "alpha"
    deployed = load_deployed(directory)
    before_lane = Event()
    resume = Event()
    errors = []
    original_lane = run._paper_lane

    @contextmanager
    def pause_before_lane(participant, name, lane):
        if lane == "halt_lane":
            before_lane.set()
            if not resume.wait(timeout=10):
                raise TimeoutError("test did not replace the deployment")
        with original_lane(participant, name, lane):
            yield

    def halt():
        try:
            _main(monkeypatch, "paper", "halt", "alpha", "--reason", "emergency")
        except BaseException as exc:
            errors.append(exc)

    monkeypatch.setattr(run, "_paper_lane", pause_before_lane)
    worker = Thread(target=halt)
    worker.start()
    try:
        assert before_lane.wait(timeout=10), errors
        with RootContext.open(tmp_path) as root:
            with RootOwnerLease.acquire(root) as owner:
                admission = AdmissionCoordinator(root, owner_lease=owner)
                store = LifecycleArchiveStore(root, admission)
                preview = store.preview("deployment", "alpha")
                archive = store.archive("deployment", "alpha", expected_digest=preview["digest"], archive_id="e" * 32)
                with paths.bound_root(root):
                    with admission.deployment_lock("alpha"):
                        deploy("alpha", deployed.spec, deployed.universe, root=tmp_path / "paper")
        resume.set()
        worker.join(timeout=10)
    finally:
        resume.set()
        worker.join(timeout=10)

    assert not worker.is_alive()
    assert len(errors) == 1 and isinstance(errors[0], SystemExit) and errors[0].code != 0
    assert Ledger(directory).halted() is None
    assert Ledger(tmp_path / archive["archive_path"]).halted() is None
    assert "halted:" not in capsys.readouterr().out


def _consume_cli_approval(root_path, ledger):
    from hedge_fund.runtime.admission import AdmissionCoordinator, RootOwnerLease
    from hedge_fund.runtime.root import RootContext

    approval = ledger.approval()
    with RootContext.open(root_path) as root:
        owner = RootOwnerLease.acquire(root)
        try:
            admission = AdmissionCoordinator(root, owner_lease=owner)
            with admission.control_lane("alpha", timeout=0):
                ledger.log_event(
                    "consume",
                    decision_as_of=approval["decision_as_of"],
                    decision_hash=approval["decision_hash"],
                    approval_verdict=approval["verdict"],
                    approval_by=approval["by"],
                    approval_id=approval["approval_id"],
                    session="2025-01-07",
                    durable=True,
                )
        finally:
            owner.close()


@pytest.mark.parametrize("journal_state", ["unfinished", "malformed"])
def test_cli_unfinished_consumption_halts_before_provider(tmp_path, monkeypatch, capsys, offline, journal_state):
    from hedge_fund.paper.ledger import Ledger

    path = _mandate(tmp_path)
    _enroll_test_root(tmp_path)
    offline("2025-01-07")
    _main(monkeypatch, "paper", "create", "alpha", "--mandate", str(path), "--universe", "AAPL", "--approval")
    directory = tmp_path / "paper" / "alpha"
    _offline_tick(directory)
    _main(monkeypatch, "paper", "approve", "alpha")
    capsys.readouterr()
    ledger = Ledger(directory)
    if journal_state == "malformed":
        with ledger.events_path.open("a", encoding="utf-8") as history:
            history.write("{invalid\n")
    else:
        _consume_cli_approval(tmp_path, ledger)

    monkeypatch.setattr(run, "make_data_client", lambda *_args, **_kwargs: pytest.fail("provider was constructed"))
    with pytest.raises(SystemExit) as exc:
        _main(monkeypatch, "paper", "tick", "alpha")
    assert exc.value.code == 1
    expected_error = "approval history is unavailable" if journal_state == "malformed" else "consumption is incomplete"
    assert expected_error in capsys.readouterr().err
    assert ledger.halted() == "approval journal requires reconciliation"


@pytest.mark.parametrize("action", ["list", "status"])
@pytest.mark.parametrize("interleaving", ["before_read", "during_verdict_read"])
def test_cli_status_does_not_claim_unfinished_consumption_is_awaiting(
    tmp_path, monkeypatch, capsys, offline, action, interleaving
):
    from hedge_fund.paper.ledger import Ledger

    path = _mandate(tmp_path)
    _enroll_test_root(tmp_path)
    offline("2025-01-07")
    _main(monkeypatch, "paper", "create", "alpha", "--mandate", str(path), "--universe", "AAPL", "--approval")
    directory = tmp_path / "paper" / "alpha"
    _offline_tick(directory)
    _main(monkeypatch, "paper", "approve", "alpha")
    capsys.readouterr()
    ledger = Ledger(directory)
    if interleaving == "before_read":
        _consume_cli_approval(tmp_path, ledger)
    else:
        resolve = Ledger.resolve_approval
        consumed = False

        def consume_before_resolution(self, *args, **kwargs):
            nonlocal consumed
            if self.directory == directory and not consumed:
                consumed = True
                _consume_cli_approval(tmp_path, ledger)
            return resolve(self, *args, **kwargs)

        monkeypatch.setattr(Ledger, "resolve_approval", consume_before_resolution)
    args = ("paper", "list") if action == "list" else ("paper", "status", "alpha")
    _main(monkeypatch, *args)
    output = capsys.readouterr().out.lower()
    assert "in progress or requires reconciliation" in output
    assert "awaiting approval" not in output


@pytest.mark.parametrize("action", ["list", "status"])
@pytest.mark.parametrize(
    "scenario",
    ["weekly_no_decision", "first_redo_approval", "first_redo_no_approval", "redo_no_approval_with_decision"],
)
def test_cli_status_reports_reconciliation_across_ledger_states(
    tmp_path, monkeypatch, capsys, offline, action, scenario
):
    from hedge_fund.paper.ledger import Ledger
    from hedge_fund.runtime.admission import AdmissionCoordinator, RootOwnerLease
    from hedge_fund.runtime.root import RootContext

    path = _mandate(tmp_path)
    _enroll_test_root(tmp_path)
    offline("2025-01-07")
    args = ["paper", "create", "alpha", "--mandate", str(path), "--universe", "AAPL"]
    if scenario not in {"first_redo_no_approval", "redo_no_approval_with_decision"}:
        args.append("--approval")
    _main(monkeypatch, *args)
    directory = tmp_path / "paper" / "alpha"
    _offline_tick(directory)
    ledger = Ledger(directory)
    if scenario == "weekly_no_decision":
        _main(monkeypatch, "paper", "approve", "alpha")
        offline("2025-01-08")
        _offline_tick(directory)
        latest = ledger.latest()
        assert latest.decision is None
        events = [
            event for event in ledger.events()
            if not (event["kind"] == "tick" and event["session"] == latest.session)
        ]
        ledger.events_path.write_text("".join(json.dumps(event) + "\n" for event in events), encoding="utf-8")
    else:
        with RootContext.open(tmp_path) as root:
            owner = RootOwnerLease.acquire(root)
            try:
                admission = AdmissionCoordinator(root, owner_lease=owner)
                with paths.bound_root(root), admission.manual_session("alpha", timeout=0):
                    ledger.begin_redo(ledger.latest())
                    if scenario != "redo_no_approval_with_decision":
                        ledger.rewind()
            finally:
                owner.close()
        if scenario != "redo_no_approval_with_decision":
            assert ledger.latest() is None
    capsys.readouterr()

    args = ("paper", "list") if action == "list" else ("paper", "status", "alpha")
    _main(monkeypatch, *args)
    output = capsys.readouterr().out.lower()
    assert "in progress or requires reconciliation" in output
    assert "awaiting approval" not in output
    assert "to execute at the next" not in output


@pytest.mark.parametrize("tamper", [False, True])
def test_enrolled_cli_redo_preserves_guarded_dispatch_and_expires_approval(
    tmp_path,
    monkeypatch,
    capsys,
    offline,
    tamper,
):
    from hedge_fund.backtesting.test_fund import FakeDataClient
    from hedge_fund.paper.ledger import Ledger
    from hedge_fund.runtime import endpoints
    from hedge_fund.runtime.handover import verify_root_inventory
    from hedge_fund.runtime.policy import ProviderTarget
    from hedge_fund.runtime.root import RootContext

    calls = []
    monkeypatch.setattr(endpoints, "_resolve_system", lambda _host, _port: ["93.184.216.34"])

    class GuardedOfflineClient(FakeDataClient):
        def __init__(self, dispatch):
            super().__init__(
                {
                    ticker: {"2025-01-06": 100, "2025-01-07": 100, "2025-01-08": 110}
                    for ticker in ("AAPL", "SPY")
                }
            )
            self.dispatch = dispatch

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def get_prices(self, ticker, start_date, end_date, **kwargs):
            target = ProviderTarget(kind="data", provider="yfinance")
            self.dispatch.authorize_transport(
                target,
                url="https://query1.finance.yahoo.com/synthetic",
                method="GET",
            )
            self.dispatch.recheck_transport_fence(target)
            calls.append(ticker)
            return super().get_prices(ticker, start_date, end_date, **kwargs)

    monkeypatch.setattr(
        run,
        "make_data_client",
        lambda *, provider, dispatch, api_key: GuardedOfflineClient(dispatch),
    )
    path = _mandate(tmp_path)
    _enroll_test_root(tmp_path)
    offline("2025-01-07")

    _main(monkeypatch, "paper", "create", "alpha", "--mandate", str(path), "--universe", "AAPL", "--approval")
    capsys.readouterr()
    _main(monkeypatch, "paper", "tick", "alpha")
    original = json.loads(capsys.readouterr().out)
    _main(monkeypatch, "paper", "approve", "alpha")
    capsys.readouterr()
    assert Ledger(tmp_path / "paper" / "alpha").approval()["decision_hash"] == original["hash"]
    before_redo = len(calls)

    if tamper:
        rewind = Ledger.rewind

        def altered_rewind(ledger):
            return rewind(ledger).model_copy(update={"hash": "0" * 64})

        monkeypatch.setattr(Ledger, "rewind", altered_rewind)
        with pytest.raises(SystemExit) as denied:
            _main(monkeypatch, "paper", "tick", "alpha", "--again")
        assert denied.value.code == 1
        assert "denied" in capsys.readouterr().err
        ledger = Ledger(tmp_path / "paper" / "alpha")
        assert len(calls) == before_redo
        assert ledger.halted() == "redo authorization denied after rewind"
        assert ledger.approval() is None
        assert ledger._latest_approval_event(
            original["decision"]["as_of"], original["hash"], strict=True
        )["kind"] == "expire"
        with RootContext.open(tmp_path) as root:
            verify_root_inventory(root)
        return

    _main(monkeypatch, "paper", "tick", "alpha", "--again")

    redone = json.loads(capsys.readouterr().out)
    ledger = Ledger(tmp_path / "paper" / "alpha")
    assert len(calls) > before_redo
    assert redone["session"] == original["session"]
    assert redone["prev_hash"] == original["prev_hash"]
    assert ledger.approval() is None
    assert any(event.get("reason") == "decision redone" for event in ledger.events())
    with RootContext.open(tmp_path) as root:
        verify_root_inventory(root)


def test_enrolled_cli_tick_lane_conflict_leaves_ledger_unchanged(
    tmp_path,
    owned_test_process,
):
    from hedge_fund.paper.deployed import deploy
    from hedge_fund.runtime.admission import AdmissionCoordinator, RootOwnerLease
    from hedge_fund.runtime.handover import (
        build_head_inventory,
        enroll_fresh,
        record_ledger_head,
    )
    from hedge_fund.runtime.root import RootContext

    root = Path(os.environ["HEDGE_FUND_TEST_ROOT"]) / "cli-tick-conflict"
    root.mkdir()
    spec = FundSpec(
        schema_version=2,
        name="alpha",
        strategies=[custom_strategy(["buffett"])],
        risk={"max_position_pct": 0.25, "max_gross_exposure": 1},
    )
    result_path = root.parent / "cli-tick-result.txt"
    with RootContext.open(root) as context:
        enroll_fresh(context)
        owner = RootOwnerLease.acquire(context, timeout=0)
        admission = AdmissionCoordinator(context, owner_lease=owner)
        try:
            with admission.deployment_lock("alpha", timeout=0):
                directory = deploy("alpha", spec, ["AAPL"], root=root / "paper")
            record_ledger_head(context, "alpha", admission=admission)
            before_inventory = build_head_inventory(context)
            before_files = {path.relative_to(directory).as_posix(): path.read_bytes() for path in directory.rglob("*") if path.is_file()}
            script = "\n".join(
                [
                    "import sys",
                    "from pathlib import Path",
                    "from hedge_fund import run",
                    f"sys.argv = ['aihf', '--root', {str(root)!r}, '--enable-network', 'paper', 'tick', 'alpha']",
                    "try:",
                    "    run.main()",
                    "except SystemExit as exc:",
                    f"    Path({str(result_path)!r}).write_text(str(exc.code), encoding='utf-8')",
                    "else:",
                    f"    Path({str(result_path)!r}).write_text('returned', encoding='utf-8')",
                ]
            )
            with admission.manual_session("alpha", timeout=0):
                child = owned_test_process(script)
                assert child.wait(timeout=20) == 0
        finally:
            owner.close()

        assert result_path.read_text(encoding="utf-8") == "1"
        assert build_head_inventory(context) == before_inventory
        after_files = {path.relative_to(directory).as_posix(): path.read_bytes() for path in directory.rglob("*") if path.is_file()}
        assert after_files == before_files


def test_cli_resolves_relative_mandate_under_root(tmp_path, monkeypatch, capsys, offline):
    root_mandate = tmp_path / "mandates"
    root_mandate.mkdir()
    spec = FundSpec(
        schema_version=2,
        name="root-mandate",
        strategies=[custom_strategy(["buffett", "druckenmiller"])],
        risk={"max_position_pct": 0.25, "max_gross_exposure": 1},
    )
    (root_mandate / "root-mandate.yaml").write_text(yaml.safe_dump(spec.model_dump()))

    decoy = tmp_path / "cwd"
    (decoy / "mandates").mkdir(parents=True)
    (decoy / "mandates" / "root-mandate.yaml").write_text("not: a valid mandate")
    _enroll_test_root(tmp_path)
    monkeypatch.chdir(decoy)

    _main(
        monkeypatch,
        "backtest",
        "mandates/root-mandate.yaml",
        "--universe",
        "AAPL",
        "--start",
        "2025-01-06",
        "--end",
        "2025-01-08",
    )

    output = capsys.readouterr()
    assert "root-mandate" in output.err
    assert json.loads(output.out)["fund"] == "root-mandate"


def test_paper_minute_fund_ticks_and_denies_legacy_runner(tmp_path, monkeypatch, capsys, offline):
    """Manual ticks use captured authority; legacy headless loops fail closed."""
    from hedge_fund.data.sessions import NEW_YORK
    from hedge_fund.pipeline.test_clock import Tape

    spec = FundSpec(schema_version=2, name="bars", strategies=[custom_strategy(["buffett"])], risk={"max_position_pct": 0.25, "max_gross_exposure": 1}, rebalance="minute", interval=0.5, window={"start": "09:30", "end": "12:00"})
    path = tmp_path / "bars.yaml"
    path.write_text(yaml.safe_dump(spec.model_dump()))
    _enroll_test_root(tmp_path)

    _main(monkeypatch, "paper", "create", "fast", "--mandate", str(path), "--universe", "AAPL")
    err = " ".join(capsys.readouterr().err.split())  # the console wraps; read it as one line
    assert "every 30s" in err and "09:30–12:00 ET" in err
    root_argument = "--root <selected-root>"
    assert f"aihf {root_argument} --enable-network paper tick fast` to authorize one bounded session" in err
    assert "Headless scheduled runners are disabled" in err

    class CliTape(Tape):
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    tape = CliTape({"AAPL": {"2025-01-07T09:30:00": 100.0, "2025-01-07T09:30:30": 101.0}, "SPY": {"2025-01-07T09:30:00": 500.0}}, now=datetime(2025, 1, 7, 9, 30, 40, tzinfo=NEW_YORK))  # 10s into the 09:30:30 bar
    monkeypatch.setattr(run, "make_data_client", lambda *_args, **_kwargs: tape)
    tick_module = importlib.import_module("hedge_fund.paper.tick")

    class Clock(datetime):  # the tick's wall clock is the tape's; everything else is datetime's
        @classmethod
        def now(cls, tz=None):
            return tape.now.astimezone(tz)

    monkeypatch.setattr(tick_module, "datetime", Clock)

    _main(monkeypatch, "paper", "tick", "fast")
    output = capsys.readouterr()
    record = json.loads(output.out)
    assert record["session"] == "2025-01-07T09:30:30" and record["decision"] is not None
    assert "decided on" in output.err and "executes next bar" in output.err

    with pytest.raises(SystemExit) as exc:
        _main(monkeypatch, "paper", "tick", "fast")  # no new bar yet
    assert exc.value.code == 1
    assert "no bar after 2025-01-07T09:30:30; next 09:31:00 ET" in capsys.readouterr().err

    with pytest.raises(SystemExit) as denied_stop:
        _main(monkeypatch, "paper", "stop", "fast")
    assert denied_stop.value.code == 2
    assert "Legacy unattended paper runner controls are disabled" in capsys.readouterr().err
    _main(monkeypatch, "paper", "list")
    listed = capsys.readouterr().out
    assert "every 30s" in listed and "running" not in listed

    with pytest.raises(SystemExit) as denied:
        _main(monkeypatch, "paper", "run", "fast")
    assert denied.value.code == 2
    assert "Legacy unattended paper runner controls are disabled" in capsys.readouterr().err
    stop_runner = Mock(return_value=True)
    monkeypatch.setattr(run, "stop_runner", stop_runner, raising=False)
    with pytest.raises(SystemExit) as second_denial:
        _main(monkeypatch, "paper", "stop", "fast")
    assert second_denial.value.code == 2
    assert "Legacy unattended paper runner controls are disabled" in capsys.readouterr().err
    stop_runner.assert_not_called()


def _offline_tick(directory):
    from hedge_fund.runtime.admission import AdmissionCoordinator, RootOwnerLease
    from hedge_fund.runtime.root import RootContext

    with RootContext.open(Path(directory).parent.parent) as root:
        owner = RootOwnerLease.acquire(root, timeout=0)
        admission = AdmissionCoordinator(root, owner_lease=owner)
        try:
            with paths.bound_root(root):
                with admission.manual_session(Path(directory).name, timeout=0):
                    with run.make_data_client() as raw:
                        run.tick(directory, run.CachedDataClient(raw))
                from hedge_fund.runtime.handover import record_ledger_head

                record_ledger_head(root, Path(directory).name, admission=admission)
        finally:
            owner.close()


def _disable_status_animation(monkeypatch):
    monkeypatch.setattr(run.Console, "status", lambda *args, **kwargs: nullcontext())


def test_paper_create_approval_and_approve_commands_show_status(tmp_path, monkeypatch, capsys, offline):
    set_today = offline
    path = _mandate(tmp_path)
    set_today("2025-01-07")
    _enroll_test_root(tmp_path)

    _main(monkeypatch, "paper", "create", "alpha", "--mandate", str(path), "--universe", "AAPL", "--approval")
    created = capsys.readouterr()
    directory = tmp_path / "paper" / "alpha"
    deployed = yaml.safe_load((directory / "fund.yaml").read_text())
    assert deployed["spec"]["approval_required"] is True
    assert "approval" in created.err.lower()

    _offline_tick(directory)
    _main(monkeypatch, "paper", "status", "alpha")
    status = capsys.readouterr().out
    assert "awaiting approval" in status and "AAPL:" in status
    _main(monkeypatch, "paper", "list")
    assert "awaiting approval" in capsys.readouterr().out

    _main(monkeypatch, "paper", "approve", "alpha")
    approved = capsys.readouterr()
    mailbox = json.loads((directory / "pending-approval.json").read_text())
    events = [json.loads(line) for line in (directory / "events.jsonl").read_text().splitlines()]
    assert mailbox["verdict"] == "approve" and mailbox["by"] == "cli"
    assert [event["kind"] for event in events] == ["tick", "approve"]
    assert "approved" in approved.err.lower()


def test_paper_approve_now_executes_when_a_session_is_due(tmp_path, monkeypatch, capsys, offline):
    set_today = offline
    path = _mandate(tmp_path)
    set_today("2025-01-07")
    _enroll_test_root(tmp_path)
    _main(monkeypatch, "paper", "create", "alpha", "--mandate", str(path), "--universe", "AAPL", "--approval")
    capsys.readouterr()
    directory = tmp_path / "paper" / "alpha"
    _offline_tick(directory)

    set_today("2025-01-08")
    _disable_status_animation(monkeypatch)
    _main(monkeypatch, "paper", "approve", "alpha", "--now")
    output = capsys.readouterr()

    record = json.loads(output.out)
    assert record["session"] == "2025-01-07"
    assert record["executed"] is not None
    assert not (directory / "pending-approval.json").exists()
    assert "executed" in output.err.lower()


def test_paper_approve_now_without_a_due_session_schedules_next_close(tmp_path, monkeypatch, capsys, offline):
    path = _mandate(tmp_path)
    _enroll_test_root(tmp_path)
    _main(monkeypatch, "paper", "create", "alpha", "--mandate", str(path), "--universe", "AAPL", "--approval")
    capsys.readouterr()
    directory = tmp_path / "paper" / "alpha"
    _offline_tick(directory)

    _disable_status_animation(monkeypatch)
    _main(monkeypatch, "paper", "approve", "alpha", "--now")
    output = capsys.readouterr()

    assert output.out == ""
    assert "will execute at the next close" in output.err.lower()
    assert json.loads((directory / "pending-approval.json").read_text())["verdict"] == "approve"


def test_paper_reject_records_verdict_and_event(tmp_path, monkeypatch, capsys, offline):
    set_today = offline
    path = _mandate(tmp_path)
    set_today("2025-01-07")
    _enroll_test_root(tmp_path)
    _main(monkeypatch, "paper", "create", "alpha", "--mandate", str(path), "--universe", "AAPL", "--approval")
    capsys.readouterr()
    directory = tmp_path / "paper" / "alpha"
    _offline_tick(directory)

    _main(monkeypatch, "paper", "reject", "alpha")
    rejected = capsys.readouterr()

    assert json.loads((directory / "pending-approval.json").read_text())["verdict"] == "reject"
    events = [json.loads(line) for line in (directory / "events.jsonl").read_text().splitlines()]
    assert [event["kind"] for event in events] == ["tick", "reject"]
    assert "rejected" in rejected.err.lower()


@pytest.mark.parametrize("action", ["approve", "reject"])
def test_paper_approval_commands_refuse_when_gate_is_off(tmp_path, monkeypatch, capsys, offline, action):
    set_today = offline
    path = _mandate(tmp_path)
    set_today("2025-01-07")
    _enroll_test_root(tmp_path)
    _main(monkeypatch, "paper", "create", "alpha", "--mandate", str(path), "--universe", "AAPL")
    capsys.readouterr()
    _offline_tick(tmp_path / "paper" / "alpha")

    with pytest.raises(SystemExit) as exc:
        _main(monkeypatch, "paper", action, "alpha")

    assert exc.value.code == 2
    assert "approval gate is not enabled for 'alpha'" in capsys.readouterr().err


@pytest.mark.parametrize("action", ["approve", "reject"])
def test_paper_approval_commands_refuse_when_nothing_is_pending(tmp_path, monkeypatch, capsys, offline, action):
    path = _mandate(tmp_path)
    _enroll_test_root(tmp_path)
    _main(monkeypatch, "paper", "create", "alpha", "--mandate", str(path), "--universe", "AAPL", "--approval")
    capsys.readouterr()

    with pytest.raises(SystemExit) as exc:
        _main(monkeypatch, "paper", action, "alpha")

    assert exc.value.code == 2
    assert "nothing is awaiting approval for 'alpha'" in capsys.readouterr().err


@pytest.mark.parametrize("action", ["approve", "reject"])
def test_paper_approval_commands_refuse_halted_funds_without_touching_control(tmp_path, monkeypatch, capsys, offline, action):
    set_today = offline
    path = _mandate(tmp_path)
    set_today("2025-01-07")
    _enroll_test_root(tmp_path)
    _main(monkeypatch, "paper", "create", "alpha", "--mandate", str(path), "--universe", "AAPL", "--approval")
    capsys.readouterr()
    directory = tmp_path / "paper" / "alpha"
    _offline_tick(directory)
    _main(monkeypatch, "paper", "halt", "alpha", "--reason", "operator review")
    capsys.readouterr()
    control_before = (directory / "control.json").read_bytes()

    with pytest.raises(SystemExit) as exc:
        _main(monkeypatch, "paper", action, "alpha")

    assert exc.value.code == 1
    assert "alpha is halted: operator review" in capsys.readouterr().err
    assert (directory / "control.json").read_bytes() == control_before
    assert not (directory / "pending-approval.json").exists()
