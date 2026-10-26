from pathlib import Path

from hedge_fund.paths import write_atomic


def test_write_atomic_survives_non_ascii(tmp_path: Path) -> None:
    # Ledger records embed LLM rationale text, which is not guaranteed to fit
    # the platform default encoding (cp1252 on Windows). The write must be
    # UTF-8 regardless of locale.
    path = tmp_path / "record.json"
    text = '{"rationale": "cheap \u2192 buy \u2192 \U0001f4c8"}'
    write_atomic(path, text)
    assert path.read_text(encoding="utf-8") == text
    assert not path.with_name(f".{path.name}.tmp").exists()


def test_write_atomic_replaces_atomically(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    write_atomic(path, "old")
    write_atomic(path, "new")
    assert path.read_text(encoding="utf-8") == "new"