import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

WORKER = Path(__file__).with_name("edgar_worker.py")


def isolated_environment(scratch):
    environment = {key: value for key, value in os.environ.items() if key.upper() in {"SYSTEMROOT", "SYSTEMDRIVE", "WINDIR"}}
    environment.update(
        {
            "HOME": str(scratch),
            "USERPROFILE": str(scratch),
            "TMP": str(scratch),
            "TEMP": str(scratch),
            "PYTHONDONTWRITEBYTECODE": "1",
        }
    )
    return environment


def run_audit_probe(tmp_path, operation):
    tmp_path.mkdir(parents=True, exist_ok=True)
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    probe = "from pathlib import Path\n" f"scratch = Path({str(scratch)!r})\n" "(scratch / 'probe-started').write_text('started')\n" f"{operation}\n" "(scratch / 'probe-completed').write_text('completed')\n"
    bootstrap = "import importlib.util\n" f"spec = importlib.util.spec_from_file_location('edgar_worker', {str(WORKER)!r})\n" "module = importlib.util.module_from_spec(spec)\n" "spec.loader.exec_module(module)\n" f"module._install_audit_hook({str(scratch)!r})\n" f"exec({probe!r})\n"
    result = subprocess.run(
        [sys.executable, "-I", "-B", "-S", "-c", bootstrap],
        capture_output=True,
        env=isolated_environment(scratch),
        timeout=15,
        check=False,
    )
    return result, scratch


def test_worker_never_executes_pth_files_from_package_directories(tmp_path):
    scratch = tmp_path / "scratch"
    package = tmp_path / "probe-package"
    scratch.mkdir()
    package.mkdir()
    (package / "probe.py").write_text(
        f"from pathlib import Path\nPath({str(scratch / 'pth-executed')!r}).write_text('forbidden')\n",
        encoding="utf-8",
    )
    (package / "probe.pth").write_text("import probe\n", encoding="ascii")

    result = subprocess.run(
        [sys.executable, "-I", "-B", "-S", str(WORKER), str(scratch), str(package)],
        input=b'{"protocol":1,"source":{"cik":"0000320193","forms":["8-K"]},"document":"{}","limit":1}',
        capture_output=True,
        env=isolated_environment(scratch),
        timeout=15,
        check=False,
    )

    assert result.returncode == 0
    response = json.loads(result.stdout)
    assert response["protocol"] == 1
    assert response["ok"] is False
    assert not (scratch / "pth-executed").exists()


@pytest.mark.parametrize(
    "operation",
    [
        "import socket\nsocket.getaddrinfo('example.invalid', 443)",
        "import socket\nsocket.socket().connect(('192.0.2.1', 9))",
        "import socket\nsocket.socket().bind(('127.0.0.1', 0))",
        "import socket\nsocket.socket().sendto(b'x', ('192.0.2.1', 9))",
        "import subprocess, sys\nsubprocess.Popen([sys.executable, '-c', 'pass'])",
        "import sys\nsys.audit('os.startfile', 'forbidden')",
        "import sys\nsys.audit('os.chown', 'forbidden', 0, 0)",
        "import sys\nsys.audit('ctypes.dlopen', 'forbidden')",
    ],
    ids=["dns", "connect", "bind", "send", "child-process", "startfile", "chown", "ctypes-load"],
)
def test_worker_audit_denies_network_and_child_process_events(tmp_path, operation):
    result, scratch = run_audit_probe(tmp_path, operation)

    assert b"AuditDenied" in result.stderr
    assert not (scratch / "probe-completed").exists()


def test_worker_audit_denies_external_writes_and_links(tmp_path):
    outside = tmp_path / "outside.txt"
    outside.write_text("original", encoding="utf-8")
    operation = "import os\n" f"open({str(tmp_path / 'external-write.txt')!r}, 'w').write('forbidden')"
    result, scratch = run_audit_probe(tmp_path / "write", operation)
    assert b"AuditDenied" in result.stderr
    assert not (tmp_path / "external-write.txt").exists()

    operation = f"import os\nos.link({str(outside)!r}, str(scratch / 'linked.txt'))"
    result, scratch = run_audit_probe(tmp_path / "write" / "link", operation)
    assert b"AuditDenied" in result.stderr
    assert not (scratch / "linked.txt").exists()
    assert outside.read_text(encoding="utf-8") == "original"


def test_worker_audit_denies_even_a_contained_symlink(tmp_path):
    operation = "import os\n(scratch / 'target.txt').write_text('target')\nos.symlink(scratch / 'target.txt', scratch / 'link.txt')"

    result, scratch = run_audit_probe(tmp_path, operation)

    assert b"AuditDenied" in result.stderr
    assert not (scratch / "link.txt").exists()


def test_worker_allows_hostname_contained_hardlinks_and_null_device_writes(tmp_path):
    operation = "import os, socket\n" "socket.gethostname()\n" "(scratch / 'source.txt').write_text('source')\n" "os.link(scratch / 'source.txt', scratch / 'hardlink.txt')\n" "open(os.devnull, 'w').write('discard')\n"

    result, scratch = run_audit_probe(tmp_path, operation)

    assert b"AuditDenied" not in result.stderr
    assert (scratch / "probe-completed").read_text(encoding="utf-8") == "completed"
    assert (scratch / "hardlink.txt").read_text(encoding="utf-8") == "source"
