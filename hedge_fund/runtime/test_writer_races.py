"""Spec005 T027 cross-process paper writer races.

Real child interpreters compete for the same synthetic, test-owned paper fund
through the production admission lanes and ``Ledger`` writers used by the
CLI, web services and runner (``manual_session`` + ``Ledger.append``), redo
(``Ledger.rewind``) and lifecycle/archive (``deployment_lock``). Outcomes are
decided by OS locks and file handshakes, never by sleeps. No provider, LLM or
real fund is touched.
"""

from __future__ import annotations

import os
import time
from contextlib import contextmanager
from pathlib import Path

import pytest

from hedge_fund import paths
from hedge_fund.fund import FundSpec
from hedge_fund.paper.deployed import deploy
from hedge_fund.paper.ledger import Ledger, LedgerError
from hedge_fund.pipeline.session import code_version, mandate_hash, SessionRecord
from hedge_fund.runtime.admission import AdmissionCoordinator, MAX_CONTROL_WAIT_SECONDS, OwnershipUnknown, RootOwnerLease, WriterConflict
from hedge_fund.runtime.handover import enroll_fresh, write_authority
from hedge_fund.runtime.root import RootContext

FUNDS = ("alpha", "beta")


def _spec(name: str) -> FundSpec:
    return FundSpec.model_validate(
        {
            "schema_version": 2,
            "name": name,
            "strategies": [{"name": "solo", "models": [{"name": "pead"}], "blend": {"mode": "long_short"}}],
            "risk": {"max_position_pct": 1, "max_gross_exposure": 1},
            "capital": 100_000,
            "rebalance": "daily",
        }
    )


def _record(name: str, session: str = "2024-06-07", prev_hash: str | None = None) -> SessionRecord:
    spec = _spec(name)
    record = SessionRecord(
        fund=name,
        session=session,
        universe=["AAPL"],
        nav=spec.capital,
        cash=spec.capital,
        positions={},
        marks={},
        benchmark=spec.benchmark,
        benchmark_close=100.0,
        rebalance=True,
        code_version=code_version(),
        mandate_hash=mandate_hash(spec),
        prev_hash=prev_hash,
    )
    record.hash = record.compute_hash()
    return record


@pytest.fixture
def race_root(tmp_path):
    root_path = tmp_path / "root"
    root_path.mkdir()
    with RootContext.open(root_path) as root:
        enroll_fresh(root)
        with RootOwnerLease.acquire(root) as owner:
            admission = AdmissionCoordinator(root, owner_lease=owner)
            for name in FUNDS:
                with admission.deployment_lock(name):
                    deploy(name, _spec(name), ["AAPL"], root=root_path / "paper")
            with paths.bound_root(root):
                yield root_path, admission


_MANUAL_WRITER = """
import sys, time
from pathlib import Path
from hedge_fund import paths
from hedge_fund.paper.ledger import Ledger, LedgerError
from hedge_fund.pipeline.session import SessionRecord
from hedge_fund.runtime.admission import AdmissionCoordinator, RootOwnerLease, WriterConflict
from hedge_fund.runtime.root import RootContext

root_path, fund, record_file = Path(ROOT), FUND, Path(RECORD)
ready, go, status, release, final = Path(READY), Path(GO), Path(STATUS), Path(RELEASE), Path(FINAL)
record = SessionRecord.model_validate_json(record_file.read_text(encoding="utf-8"))


def wait_for(path):
    deadline = time.monotonic() + 60
    while not path.exists():
        if time.monotonic() > deadline:
            sys.exit(3)
        time.sleep(0.01)


with RootContext.open(root_path) as root:
    with RootOwnerLease.acquire(root, timeout=5) as owner, paths.bound_root(root):
        coordinator = AdmissionCoordinator(root, owner_lease=owner)
        ledger = Ledger(root_path / "paper" / fund)
        ready.write_text("ready", encoding="utf-8")
        wait_for(go)
        try:
            with coordinator.manual_session(fund, timeout=0):
                status.write_text("admitted", encoding="utf-8")
                wait_for(release)
                try:
                    ledger.append(record)
                    result = "appended"
                except LedgerError:
                    result = "ledger-error"
        except WriterConflict:
            status.write_text("conflict", encoding="utf-8")
            result = "conflict"
        final.write_text(result, encoding="utf-8")
sys.exit(0)
"""

_RESEARCH_HOLDER = """
import sys, time
from pathlib import Path
from hedge_fund.runtime.admission import AdmissionCoordinator, RootOwnerLease
from hedge_fund.runtime.root import RootContext

root_path, identity, ready, release = Path(ROOT), IDENTITY, Path(READY), Path(RELEASE)
with RootContext.open(root_path) as root:
    with RootOwnerLease.acquire(root, timeout=5) as owner:
        coordinator = AdmissionCoordinator(root, owner_lease=owner)
        with coordinator.research_lane(identity, timeout=0):
            ready.write_text("held", encoding="utf-8")
            deadline = time.monotonic() + 60
            while not release.exists() and time.monotonic() < deadline:
                time.sleep(0.01)
sys.exit(0 if release.exists() else 3)
"""


def _render(template: str, **values: str) -> str:
    for key, value in values.items():
        template = template.replace(key, repr(value))
    return template


def _wait_file(path: Path, process, what: str, timeout: float = 30) -> str:
    deadline = time.monotonic() + timeout
    while not path.exists():
        if process is not None and process.poll() is not None and not path.exists():
            raise AssertionError(f"{what} exited early: {process.returncode}")
        if time.monotonic() > deadline:
            raise AssertionError(f"{what} did not report")
        time.sleep(0.01)
    return path.read_text(encoding="utf-8")


class _Racer:
    def __init__(self, owned_test_process, workdir: Path, root: Path, fund: str, record: SessionRecord, go: Path, release: Path, tag: str):
        self.workdir = workdir
        record_file = workdir / f"record-{tag}.json"
        record_file.write_text(record.model_dump_json(), encoding="utf-8")
        self.ready = workdir / f"ready-{tag}"
        self.status = workdir / f"status-{tag}"
        self.final = workdir / f"final-{tag}"
        script = _render(
            _MANUAL_WRITER,
            ROOT=str(root),
            FUND=fund,
            RECORD=str(record_file),
            READY=str(self.ready),
            GO=str(go),
            STATUS=str(self.status),
            RELEASE=str(release),
            FINAL=str(self.final),
        )
        self.process = owned_test_process(script)
        self.tag = tag

    def wait_ready(self) -> None:
        _wait_file(self.ready, self.process, f"racer {self.tag}")

    def wait_status(self) -> str:
        return _wait_file(self.status, self.process, f"racer {self.tag} status")

    def wait_final(self) -> str:
        result = _wait_file(self.final, self.process, f"racer {self.tag} result")
        assert self.process.wait(timeout=15) == 0
        return result


def _start_racers(owned_test_process, workdir: Path, root: Path, fund: str, record: SessionRecord, count: int, *, release: Path, prefix: str) -> list[_Racer]:
    go = workdir / f"go-{prefix}"
    racers = [_Racer(owned_test_process, workdir, root, fund, record, go, release, f"{prefix}-{index}") for index in range(count)]
    for racer in racers:
        racer.wait_ready()
    go.write_text("go", encoding="utf-8")
    return racers


@contextmanager
def _session_held_by_child(owned_test_process, workdir: Path, root: Path, fund: str, record: SessionRecord, tag: str):
    release = workdir / f"release-{tag}"
    (racer,) = _start_racers(owned_test_process, workdir, root, fund, record, 1, release=release, prefix=tag)
    assert racer.wait_status() == "admitted"
    yield racer, release


@contextmanager
def _research_held_by_child(owned_test_process, workdir: Path, root: Path, identity: str):
    ready = workdir / f"research-ready-{identity}"
    release = workdir / f"research-release-{identity}"
    process = owned_test_process(_render(_RESEARCH_HOLDER, ROOT=str(root), IDENTITY=identity, READY=str(ready), RELEASE=str(release)))
    try:
        _wait_file(ready, process, f"research holder {identity}")
        yield
    finally:
        release.write_text("release", encoding="utf-8")
        assert process.wait(timeout=15) == 0


def _recorded(root: Path, fund: str) -> list[str]:
    return Ledger(root / "paper" / fund).sessions()


def test_concurrent_manual_appends_to_one_fund_admit_exactly_one_writer(race_root, tmp_path, owned_test_process):
    root, admission = race_root
    record = _record("alpha")
    release = tmp_path / "release-first"
    racers = _start_racers(owned_test_process, tmp_path, root, "alpha", record, 4, release=release, prefix="first")
    statuses = sorted(racer.wait_status() for racer in racers)
    assert statuses == ["admitted", "conflict", "conflict", "conflict"]

    # Every other in-process entrypoint for the same fund is refused while the winner holds it.
    with pytest.raises(WriterConflict):
        with admission.manual_session("alpha", timeout=0):
            pytest.fail("a second manual/runner session was admitted")
    with pytest.raises(WriterConflict):
        with admission.deployment_lock("alpha", timeout=0):
            pytest.fail("archive/lifecycle was admitted during a running session")
    with pytest.raises(LedgerError, match="admission denied"):
        Ledger(root / "paper" / "alpha").append(record)
    assert _recorded(root, "alpha") == []

    release.write_text("release", encoding="utf-8")
    finals = sorted(racer.wait_final() for racer in racers)
    assert finals == ["appended", "conflict", "conflict", "conflict"]
    assert _recorded(root, "alpha") == [record.session]

    # A second wave replaying the same session cannot duplicate the append.
    replay_release = tmp_path / "release-replay"
    replay_release.write_text("release", encoding="utf-8")
    replays = _start_racers(owned_test_process, tmp_path, root, "alpha", record, 3, release=replay_release, prefix="replay")
    replay_finals = [racer.wait_final() for racer in replays]
    assert set(replay_finals) <= {"ledger-error", "conflict"}
    assert "ledger-error" in replay_finals
    assert _recorded(root, "alpha") == [record.session]


def test_independent_fund_progresses_while_another_fund_session_is_held(race_root, tmp_path, owned_test_process):
    root, admission = race_root
    alpha = _record("alpha")
    beta = _record("beta")
    with _session_held_by_child(owned_test_process, tmp_path, root, "alpha", alpha, "alpha-held") as (racer, release):
        with admission.manual_session("beta", timeout=0):
            Ledger(root / "paper" / "beta").append(beta)
        with admission.deployment_lock("beta", timeout=0):
            pass
        assert _recorded(root, "beta") == [beta.session]
        assert _recorded(root, "alpha") == []
        release.write_text("release", encoding="utf-8")
        assert racer.wait_final() == "appended"
    assert _recorded(root, "alpha") == [alpha.session]


def test_redo_cannot_interleave_with_a_running_append(race_root, tmp_path, owned_test_process):
    root, admission = race_root
    ledger = Ledger(root / "paper" / "alpha")
    first = _record("alpha", "2024-06-07")
    with admission.manual_session("alpha", timeout=0):
        ledger.append(first)
    second = _record("alpha", "2024-06-10", prev_hash=first.hash)
    with _session_held_by_child(owned_test_process, tmp_path, root, "alpha", second, "redo") as (racer, release):
        with pytest.raises(WriterConflict):
            with admission.manual_session("alpha", timeout=0):
                ledger.rewind()
        with pytest.raises(LedgerError, match="admission denied"):
            ledger.rewind()
        assert _recorded(root, "alpha") == [first.session]
        release.write_text("release", encoding="utf-8")
        assert racer.wait_final() == "appended"
    assert _recorded(root, "alpha") == [first.session, second.session]
    with admission.manual_session("alpha", timeout=0):
        assert ledger.rewind().session == second.session
    assert _recorded(root, "alpha") == [first.session]


def test_legacy_runner_presence_denies_every_racing_writer(race_root, tmp_path, owned_test_process):
    root, admission = race_root
    record = _record("alpha")
    (root / "paper" / "alpha" / "runner.pid").write_text("1", encoding="utf-8")
    release = tmp_path / "release-legacy"
    release.write_text("release", encoding="utf-8")
    go = tmp_path / "go-legacy"
    go.write_text("go", encoding="utf-8")
    racers = [_Racer(owned_test_process, tmp_path, root, "alpha", record, go, release, f"legacy-{index}") for index in range(3)]
    for racer in racers:
        assert racer.process.wait(timeout=60) != 0
        assert not racer.status.exists()
        assert not racer.final.exists()
    with RootContext.open(root) as context:
        assert write_authority(context) == {"authority": "ownership-unknown", "reason": "legacy-runner-present"}
    with pytest.raises(OwnershipUnknown):
        with admission.manual_session("alpha", timeout=0):
            pytest.fail("a writer was admitted while legacy runner presence is unknown")
    with pytest.raises(OwnershipUnknown):
        with admission.manual_session("beta", timeout=0):
            pytest.fail("legacy presence must make the whole root read-only")
    assert _recorded(root, "alpha") == []
    assert _recorded(root, "beta") == []


@pytest.mark.parametrize("revocation", ["legacy-runner", "exclusion-proof"])
def test_authority_revoked_across_processes_blocks_an_admitted_append(race_root, tmp_path, owned_test_process, revocation):
    root, _admission = race_root
    marker = Path(os.environ["HEDGE_FUND_TEST_ROOT"]) / ".test-owned"
    moved_marker = tmp_path / "revoked-test-marker"
    record = _record("alpha")
    with _session_held_by_child(owned_test_process, tmp_path, root, "alpha", record, f"revoked-{revocation}") as (racer, release):
        try:
            if revocation == "legacy-runner":
                (root / "paper" / "alpha" / "runner.pid").write_text("unverified", encoding="utf-8")
                reason = "legacy-runner-present"
            else:
                marker.rename(moved_marker)
                reason = "out-of-band-exclusion-unproven"
            with RootContext.open(root) as context:
                assert write_authority(context) == {"authority": "ownership-unknown", "reason": reason}
            release.write_text("release", encoding="utf-8")
            assert racer.wait_final() == "ledger-error"
            assert _recorded(root, "alpha") == []
        finally:
            if moved_marker.exists():
                moved_marker.rename(marker)


def test_halt_and_verdict_lanes_stay_responsive_under_research_saturation(race_root, tmp_path, owned_test_process):
    root, admission = race_root
    identities = ("alpha", "beta", "research-1", "research-2", "research-3")
    with _research_held_by_child(owned_test_process, tmp_path, root, identities[0]), _research_held_by_child(owned_test_process, tmp_path, root, identities[1]), _research_held_by_child(owned_test_process, tmp_path, root, identities[2]), _research_held_by_child(owned_test_process, tmp_path, root, identities[3]), _research_held_by_child(owned_test_process, tmp_path, root, identities[4]):
        with _session_held_by_child(owned_test_process, tmp_path, root, "alpha", _record("alpha"), "saturated") as (racer, release):
            for identity in identities:
                with pytest.raises(WriterConflict):
                    with admission.research_lane(identity, timeout=0):
                        pass
            ledger = Ledger(root / "paper" / "alpha")
            started = time.monotonic()
            with admission.halt_lane("alpha", timeout=0.1):
                ledger.halt("T027 saturation halt")
            with admission.control_lane("alpha", timeout=0.1):
                pass
            elapsed = time.monotonic() - started
            assert elapsed < MAX_CONTROL_WAIT_SECONDS + 5
            assert ledger.halted() is not None
            release.write_text("release", encoding="utf-8")
            racer.wait_final()
