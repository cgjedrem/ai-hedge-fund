import json
import os
from pathlib import Path

import pytest

from hedge_fund import paths
from hedge_fund.runtime.root import RootConfigurationError, RootContext


@pytest.fixture
def configured_root(tmp_path):
    previous = paths.root_context(required=False)
    context = RootContext.open(tmp_path)
    paths.configure_root(context)
    try:
        yield context
    finally:
        paths.clear_root(context)
        if previous is not None:
            paths.configure_root(previous)
        context.close()


def test_paths_have_no_implicit_home_default(owned_test_process):
    process = owned_test_process("import hedge_fund.paths as paths\n" "assert paths.USER_DIR is None\n" "assert paths.MANDATES_DIR is None\n" "assert paths.PAPER_DIR is None\n" "assert paths.RESEARCH_DIR is None\n" "assert paths.CACHE_DIR is None\n" "assert paths.ENV_PATH is None\n")
    assert process.wait(timeout=10) == 0


def test_root_configuration_binds_every_store_path(tmp_path, configured_root):
    root = configured_root.path

    assert paths.root_context() is configured_root
    assert paths.USER_DIR == root
    assert paths.MANDATES_DIR == root / "mandates"
    assert paths.PAPER_DIR == root / "paper"
    assert paths.RESEARCH_DIR == root / "research"
    assert paths.CACHE_DIR == root / "cache"
    assert paths.ENV_PATH == root / ".env"


def test_root_path_helpers_keep_store_io_handle_relative(
    configured_root,
    monkeypatch,
):
    root = configured_root.path
    methods = ("mkdir", "read_bytes", "write_bytes", "read_text", "write_text", "resolve")

    for method in methods:
        original = getattr(Path, method)

        def guarded(path, *args, _original=original, **kwargs):
            if Path(path).is_relative_to(root):
                raise AssertionError(f"path-based {method} used under root")
            return _original(path, *args, **kwargs)

        monkeypatch.setattr(Path, method, guarded)

    paths.ensure_mandates_dir()
    target = root / "cache" / "config" / "settings.json"
    paths.write_atomic(target, '{"model":"local"}', mode=0o600)

    assert configured_root.read_bytes("mandates/example.yaml")
    assert configured_root.read_bytes("cache/config/settings.json") == b'{"model":"local"}'
    assert configured_root.file_info("cache/config/settings.json").size == len(b'{"model":"local"}')


@pytest.mark.parametrize("value", [None, "relative-root", Path("relative-root")])
def test_root_configuration_rejects_unopened_or_relative_roots(value):
    with pytest.raises((RootConfigurationError, TypeError)):
        paths.configure_root(value)


def test_dotenv_is_opt_in_exact_root_and_non_secret_only(
    tmp_path,
    monkeypatch,
    configured_root,
):
    other = tmp_path / "decoy"
    other.mkdir()
    (other / ".env").write_text(
        "HEDGE_FUND_LLM_MODEL=decoy-model\n",
        encoding="utf-8",
    )
    configured_root.write_bytes(
        ".env",
        b"HEDGE_FUND_LLM_MODEL=root-model\nHEDGE_FUND_DATA_PROVIDER=yfinance\nOPENAI_API_KEY=synthetic-secret\nHEDGE_FUND_ROOT=decoy-root\nAIHF_ALLOW_WRITES=1\n",
    )
    monkeypatch.setenv("HOME", str(other))
    monkeypatch.setenv("USERPROFILE", str(other))
    monkeypatch.delenv("HEDGE_FUND_LLM_MODEL", raising=False)
    monkeypatch.delenv("HEDGE_FUND_DATA_PROVIDER", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("HEDGE_FUND_ROOT", raising=False)
    monkeypatch.delenv("AIHF_ALLOW_WRITES", raising=False)

    paths.load_root_dotenv(configured_root, enabled=False)
    assert "HEDGE_FUND_LLM_MODEL" not in os.environ

    paths.load_root_dotenv(configured_root, enabled=True)
    assert os.environ["HEDGE_FUND_LLM_MODEL"] == "root-model"
    assert os.environ["HEDGE_FUND_DATA_PROVIDER"] == "yfinance"
    assert "OPENAI_API_KEY" not in os.environ
    assert "HEDGE_FUND_ROOT" not in os.environ
    assert "AIHF_ALLOW_WRITES" not in os.environ


def test_run_import_does_not_load_engine_or_tui(owned_test_process):
    process = owned_test_process("import sys\n" "import hedge_fund.run\n" "for name in ('hedge_fund.backtesting', 'hedge_fund.data', " "'hedge_fund.fund', 'hedge_fund.paper', 'hedge_fund.tui'):\n" "    assert name not in sys.modules, name\n")
    assert process.wait(timeout=10) == 0


def test_web_launcher_import_does_not_load_engine_or_demo(owned_test_process):
    process = owned_test_process("import sys\n" "import hedge_fund.web.__main__\n" "for name in ('hedge_fund.backtesting', 'hedge_fund.data', " "'hedge_fund.fund', 'hedge_fund.paper', 'hedge_fund.web.demo', " "'hedge_fund.web.app'):\n" "    assert name not in sys.modules, name\n")
    assert process.wait(timeout=10) == 0


def test_cli_rejects_missing_root_before_engine_import(owned_test_process):
    process = owned_test_process(
        "import sys\n"
        "from hedge_fund import run\n"
        "try:\n"
        "    run.main(['backtest', 'unused.yaml', '--universe', 'AAPL'])\n"
        "except SystemExit as exc:\n"
        "    assert exc.code == 2\n"
        "else:\n"
        "    raise AssertionError('missing root was accepted')\n"
        "for name in ('hedge_fund.backtesting', 'hedge_fund.data', "
        "'hedge_fund.fund', 'hedge_fund.paper', 'hedge_fund.tui'):\n"
        "    assert name not in sys.modules, name\n"
    )
    assert process.wait(timeout=10) == 0


def test_cli_process_exits_two_without_root(owned_test_process):
    process = owned_test_process("from hedge_fund import run\n" "run.main(['backtest', 'unused.yaml', '--universe', 'AAPL'])\n")
    assert process.wait(timeout=10) == 2


def test_cache_defaults_follow_configured_root(owned_test_process, tmp_path):
    root = json.dumps(str(tmp_path))
    process = owned_test_process(
        "from pathlib import Path\n"
        "from hedge_fund.runtime.root import RootContext\n"
        "from hedge_fund import paths\n"
        f"context = RootContext.open({root})\n"
        "paths.configure_root(context)\n"
        "from hedge_fund.data.cached import DEFAULT_CACHE_DIR as data_cache\n"
        "from hedge_fund.data.cached import CachedDataClient\n"
        "from hedge_fund.features.breakpoints import DEFAULT_CACHE_PATH\n"
        "from hedge_fund.features.breakpoints import load_breakpoints\n"
        "from hedge_fund.llm.cache import DEFAULT_CACHE_DIR as llm_cache\n"
        "from hedge_fund.llm.cache import PromptCache\n"
        f"root = Path({root})\n"
        "assert data_cache == root / 'cache' / 'data'\n"
        "assert DEFAULT_CACHE_PATH == root / 'cache' / 'breakpoints' / 'ME_Breakpoints.csv'\n"
        "assert llm_cache == root / 'cache' / 'llm'\n"
        "class DataClient:\n"
        "    def get_company_facts(self, ticker): return None\n"
        "data_client = CachedDataClient(DataClient())\n"
        "data_client.get_company_facts('AAPL')\n"
        "data_client.get_company_facts('AAPL')\n"
        "data_key = data_client._key('get_company_facts', {'ticker': 'AAPL'})\n"
        "context.file_info(f'cache/data/{data_key}.json')\n"
        "prompt_cache = PromptCache()\n"
        "prompt_cache.put('synthetic', {'prompt': 'test'})\n"
        "assert prompt_cache.get('synthetic')['prompt'] == 'test'\n"
        "context.file_info('cache/llm/synthetic.json')\n"
        "csv = '202401,100,' + ','.join(str(i) for i in range(1, 21))\n"
        "assert load_breakpoints(fetch=lambda: csv).latest_month == '202401'\n"
        "assert load_breakpoints(fetch=lambda: (_ for _ in ()).throw(AssertionError())).latest_month == '202401'\n"
        "context.file_info('cache/breakpoints/ME_Breakpoints.csv')\n"
        "context.close()\n"
    )
    assert process.wait(timeout=10) == 0
