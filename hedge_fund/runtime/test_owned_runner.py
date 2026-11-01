from datetime import datetime, timezone
from types import SimpleNamespace

from hedge_fund.pipeline.session import code_version
from hedge_fund.runtime.admission import PROTOCOL_VERSION
from hedge_fund.runtime.handover import root_binding
from hedge_fund.runtime.owned_runner import (
    validate_runner_control,
    validate_runner_state,
)
from hedge_fund.runtime.owned_runner_child import _runner_authorization
from hedge_fund.runtime.root import RootContext


def test_runner_authorization_accepts_frozen_authorization_record():
    capture = SimpleNamespace(
        root_id="a" * 64,
        subject_id="owned-runner",
        digest="b" * 64,
        data_provider="yfinance",
        llm_provider="Ollama",
        model="gemma3:4b",
        endpoint="http://127.0.0.1:11434",
    )
    raw = {
        "initial_due_set": [],
        "expires_at": "2027-01-01T00:00:00+00:00",
        "max_sessions": 1,
        "max_calls": 4,
        "max_resources": 8,
        "operation_id": "c" * 32,
        "operation_digest": "d" * 64,
    }

    authorization = _runner_authorization(raw, capture)

    assert authorization.root_id == capture.root_id
    assert authorization.deployment_id == capture.subject_id
    assert authorization.initial_due_set == ()
    assert authorization.expires_at == datetime(2027, 1, 1, tzinfo=timezone.utc)
    assert authorization.max_sessions == 1
    assert authorization.max_calls == 4
    assert authorization.max_resources == 8
    assert authorization.operation_id == "c" * 32
    assert authorization.operation_digest == "d" * 64


def test_runner_record_validators_require_timezone_aware_timestamps(tmp_path):
    with RootContext.open(tmp_path) as root:
        fund = "test-fund"
        nonce_hash = "a" * 64
        state = {
            "schema": 1,
            "protocol_version": PROTOCOL_VERSION,
            "build_id": code_version(),
            "root": root_binding(root),
            "fund": fund,
            "nonce_hash": nonce_hash,
            "status": "starting",
            "created_at": "2026-01-01T00:00:00+00:00",
            "expires_at": "2026-01-01T00:01:00+00:00",
            "max_sessions": 1,
            "sessions_completed": 0,
            "last_session": None,
            "reason": None,
            "pid": None,
            "process_identity": None,
        }
        assert validate_runner_state(root, fund, state)
        state["created_at"] = "2026-01-01T00:00:00"
        assert not validate_runner_state(root, fund, state)

        control = {
            "schema": 1,
            "protocol_version": PROTOCOL_VERSION,
            "build_id": code_version(),
            "root": root_binding(root),
            "fund": fund,
            "nonce_hash": nonce_hash,
            "launch_ready": True,
            "stop_requested": True,
            "requested_at": "2026-01-01T00:00:10+00:00",
        }
        assert validate_runner_control(root, fund, nonce_hash, control)
        control["requested_at"] = "2026-01-01T00:00:10"
        assert not validate_runner_control(root, fund, nonce_hash, control)
