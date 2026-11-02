import ctypes
import os

import pytest

from hedge_fund.runtime import ownership
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


@pytest.mark.skipif(
    os.name != "nt" or not isinstance(getattr(ctypes, "_pointer_type_cache", None), dict),
    reason="Windows CPython pointer-type cache is unavailable",
)
def test_windows_process_identity_does_not_retain_pointer_types_per_call():
    def retained_types():
        return {entry for entry in ctypes._pointer_type_cache if getattr(entry, "__module__", None) == ownership.__name__}

    current_process_identity()
    before = retained_types()
    for _ in range(3):
        current_process_identity()
    assert retained_types() == before
