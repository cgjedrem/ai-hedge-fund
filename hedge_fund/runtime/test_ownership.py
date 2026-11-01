import os

import pytest

from hedge_fund.runtime.ownership import (
    current_process_identity,
    identity_matches,
    process_identity,
    ProcessIdentityError,
)


def test_current_process_has_native_incarnation_and_namespace_identity():
    identity = current_process_identity()

    assert identity["pid"] == os.getpid()
    assert identity["creation_time"]
    assert identity["host"]
    assert identity["namespace"]
    assert identity_matches(os.getpid(), identity)


def test_process_identity_rejects_pid_only_and_invalid_inputs():
    identity = current_process_identity()

    assert not identity_matches(os.getpid(), {"pid": os.getpid()})
    assert not identity_matches(
        os.getpid(),
        {**identity, "creation_time": "unrelated-incarnation"},
    )
    with pytest.raises(ProcessIdentityError):
        process_identity(0)
