from pathlib import Path

import hedge_fund.paths as paths
from hedge_fund.paths import write_atomic


def test_write_atomic_survives_non_ascii(tmp_path: Path) -> None:
    # Ledger records embed LLM rationale text, which is not guaranteed to fit
    # the platform default encoding (cp1252 on Windows). The write must be
    # UTF-8 regardless of locale.
    path = tmp_path / "record.json"
    text = '{"rationale": "cheap \u2192 buy \u2192 \U0001f4c8"}'
    write_atomic(path, text)
    assert path.read_text(encoding="utf-8") == text
    assert list(tmp_path.glob(f".{path.name}.*.tmp")) == []


def test_write_atomic_replaces_atomically(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    write_atomic(path, "old")
    write_atomic(path, "new")
    assert path.read_text(encoding="utf-8") == "new"


def test_write_atomic_uses_a_unique_temp_path_per_write(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "state.json"
    temporary_names = []
    replace = paths.os.replace

    def record_replace(source, target):
        temporary_names.append(Path(source).name)
        replace(source, target)

    monkeypatch.setattr(paths.os, "replace", record_replace)
    write_atomic(path, "first")
    write_atomic(path, "second")

    assert len(set(temporary_names)) == 2
    assert path.read_text(encoding="utf-8") == "second"
