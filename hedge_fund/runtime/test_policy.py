from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from hedge_fund.runtime.policy import AuthorizationDenied
from hedge_fund.runtime.policy import authorize_dispatch as _authorize_dispatch
from hedge_fund.runtime.policy import authorize_session as _authorize_session
from hedge_fund.runtime.policy import BudgetDenied, classify_provider, DispatchBudget
from hedge_fund.runtime.policy import OneShotAuthorization as _OneShotAuthorization
from hedge_fund.runtime.policy import OperationScope, ProviderClass, ProviderTarget
from hedge_fund.runtime.policy import RunnerAuthorization as _RunnerAuthorization

_OPERATION_ID = "operation-1"
_OPERATION_DIGEST = "f" * 64


def OneShotAuthorization(**kwargs):
    kwargs.setdefault("upper_bound_cost", Decimal("0.10"))
    return _OneShotAuthorization(
        operation_id=_OPERATION_ID,
        operation_digest=_OPERATION_DIGEST,
        **kwargs,
    )


def RunnerAuthorization(**kwargs):
    return _RunnerAuthorization(
        operation_id=_OPERATION_ID,
        operation_digest=_OPERATION_DIGEST,
        **kwargs,
    )


def authorize_dispatch(target, *args, **kwargs):
    kwargs.setdefault("network_authorized", True)
    return _authorize_dispatch(
        target,
        *args,
        operation_id=_OPERATION_ID,
        operation_digest=_OPERATION_DIGEST,
        **kwargs,
    )


def authorize_session(authorization, *args, **kwargs):
    return _authorize_session(
        authorization,
        *args,
        operation_id=_OPERATION_ID,
        operation_digest=_OPERATION_DIGEST,
        **kwargs,
    )


def test_cloud_labelled_keyless_ollama_is_not_classified_as_local():
    cloud_target = ProviderTarget(
        kind="llm",
        provider="ollama",
        model="cloud/remote",
        endpoint="http://127.0.0.1:11434",
    )
    local_target = ProviderTarget(
        kind="llm",
        provider="ollama",
        model="gemma3:4b",
        endpoint="http://127.0.0.1:11434",
    )
    remote_target = ProviderTarget(
        kind="llm",
        provider="ollama",
        model="gemma3:4b",
        endpoint="https://models.example.invalid",
    )

    assert classify_provider(cloud_target, approved_local_models={"gemma3:4b"}) is ProviderClass.PAID_CLOUD
    assert classify_provider(local_target, approved_local_models={"gemma3:4b"}) is ProviderClass.LOCAL
    assert classify_provider(remote_target, approved_local_models={"gemma3:4b"}) is ProviderClass.PAID_CLOUD


def test_paid_provider_requires_matching_manual_one_shot_authorization():
    now = datetime(2026, 10, 31, 12, 0, tzinfo=timezone.utc)
    target = ProviderTarget(kind="data", provider="fd")
    authorization = OneShotAuthorization(
        root_id="synthetic-root",
        subject_id="research-1",
        capture_digest="capture-digest",
        provider_id=target.identity,
        expires_at=now + timedelta(minutes=1),
        max_calls=1,
        max_cost=Decimal("0.25"),
        upper_bound_cost=Decimal("0.20"),
    )

    assert (
        authorize_dispatch(
            target,
            scope=OperationScope.MANUAL_ONE_SHOT,
            root_id="synthetic-root",
            subject_id="research-1",
            capture_digest="capture-digest",
            now=now,
            one_shot=authorization,
            network_authorized=True,
            upper_bound_cost=Decimal("0.20"),
        )
        is ProviderClass.PAID_CLOUD
    )

    with pytest.raises(AuthorizationDenied):
        authorize_dispatch(
            target,
            scope=OperationScope.SCHEDULED,
            root_id="synthetic-root",
            subject_id="deployment-1",
            capture_digest="capture-digest",
            now=now,
            one_shot=authorization,
            network_authorized=True,
            upper_bound_cost=Decimal("0.20"),
        )


def test_scheduled_scope_requires_finite_free_or_local_authorization():
    now = datetime(2026, 10, 31, 12, 0, tzinfo=timezone.utc)
    target = ProviderTarget(kind="data", provider="yfinance")
    authorization = RunnerAuthorization(
        root_id="synthetic-root",
        deployment_id="deployment-1",
        capture_digest="capture-digest",
        provider_ids=(target.identity,),
        expires_at=now + timedelta(hours=1),
        max_sessions=2,
        max_calls=20,
        max_resources=10,
        initial_due_set=("2026-10-31",),
    )
    authorize_session(
        authorization,
        root_id="synthetic-root",
        deployment_id="deployment-1",
        capture_digest="capture-digest",
        due_set=("2026-10-31",),
        now=now,
    )

    assert (
        authorize_dispatch(
            target,
            scope=OperationScope.SCHEDULED,
            root_id="synthetic-root",
            subject_id="deployment-1",
            capture_digest="capture-digest",
            now=now,
            runner=authorization,
            upper_bound_cost=Decimal("0"),
        )
        is ProviderClass.FREE_DATA
    )

    paid_target = ProviderTarget(kind="data", provider="fd")
    with pytest.raises(AuthorizationDenied):
        authorize_dispatch(
            paid_target,
            scope=OperationScope.SCHEDULED,
            root_id="synthetic-root",
            subject_id="deployment-1",
            capture_digest="capture-digest",
            now=now,
            runner=authorization,
            upper_bound_cost=Decimal("0"),
        )

    with pytest.raises(AuthorizationDenied):
        authorize_dispatch(
            target,
            scope=OperationScope.SCHEDULED,
            root_id="other-root",
            subject_id="deployment-1",
            capture_digest="capture-digest",
            now=now,
            runner=authorization,
            upper_bound_cost=Decimal("0"),
        )


@pytest.mark.parametrize(
    "bounds",
    [
        {"max_sessions": 0, "max_calls": 1, "max_resources": 1},
        {"max_sessions": 1, "max_calls": 0, "max_resources": 1},
        {"max_sessions": 1, "max_calls": 1, "max_resources": 0},
    ],
)
def test_runner_authorization_requires_positive_finite_bounds(bounds):
    now = datetime(2026, 10, 31, 12, 0, tzinfo=timezone.utc)

    with pytest.raises(ValueError):
        RunnerAuthorization(
            root_id="synthetic-root",
            deployment_id="deployment-1",
            capture_digest="capture-digest",
            provider_ids=("yfinance:data",),
            expires_at=now + timedelta(hours=1),
            initial_due_set=("2026-10-31",),
            **bounds,
        )


def test_paid_dispatch_denies_unknown_cost_and_retries_before_reserving():
    now = datetime(2026, 10, 31, 12, 0, tzinfo=timezone.utc)
    target = ProviderTarget(kind="data", provider="fd")
    authorization = OneShotAuthorization(
        root_id="synthetic-root",
        subject_id="research-1",
        capture_digest="capture-digest",
        provider_id=target.identity,
        expires_at=now + timedelta(minutes=1),
        max_calls=3,
        max_cost=Decimal("1.00"),
        upper_bound_cost=Decimal("0.10"),
    )
    inputs = {
        "scope": OperationScope.MANUAL_ONE_SHOT,
        "root_id": "synthetic-root",
        "subject_id": "research-1",
        "capture_digest": "capture-digest",
        "now": now,
        "one_shot": authorization,
        "network_authorized": True,
    }

    with pytest.raises(AuthorizationDenied):
        authorize_dispatch(target, **inputs)
    with pytest.raises(AuthorizationDenied):
        authorize_dispatch(
            target,
            **inputs,
            upper_bound_cost=Decimal("0.10"),
            attempt=2,
        )

    assert authorization.calls_reserved == 0
    assert authorization.cost_reserved == Decimal("0")


@pytest.mark.parametrize(
    "target,approved_models",
    [
        (ProviderTarget(kind="data", provider="yfinance"), frozenset()),
        (
            ProviderTarget(
                kind="llm",
                provider="ollama",
                model="gemma3:4b",
                endpoint="http://127.0.0.1:11434",
            ),
            frozenset({"gemma3:4b"}),
        ),
    ],
)
def test_free_and_local_dispatch_require_network_and_operation_authority(
    target,
    approved_models,
):
    now = datetime(2026, 10, 31, 12, 0, tzinfo=timezone.utc)
    identity = {
        "scope": OperationScope.MANUAL_ONE_SHOT,
        "root_id": "synthetic-root",
        "subject_id": "research-1",
        "capture_digest": "capture-digest",
        "now": now,
        "approved_local_models": approved_models,
    }

    with pytest.raises(AuthorizationDenied):
        authorize_dispatch(
            target,
            **identity,
            network_authorized=False,
        )

    with pytest.raises(AuthorizationDenied):
        authorize_dispatch(
            target,
            **identity,
            network_authorized=True,
        )


def test_paid_dispatch_denies_mismatched_identity_and_expiry_before_reserving():
    now = datetime(2026, 10, 31, 12, 0, tzinfo=timezone.utc)
    target = ProviderTarget(kind="data", provider="fd")
    authorization = OneShotAuthorization(
        root_id="synthetic-root",
        subject_id="research-1",
        capture_digest="capture-digest",
        provider_id=target.identity,
        expires_at=now + timedelta(minutes=1),
        max_calls=1,
        max_cost=Decimal("0.25"),
        upper_bound_cost=Decimal("0.10"),
    )
    inputs = {
        "scope": OperationScope.MANUAL_ONE_SHOT,
        "subject_id": "research-1",
        "capture_digest": "capture-digest",
        "now": now,
        "one_shot": authorization,
        "network_authorized": True,
        "upper_bound_cost": Decimal("0.10"),
    }

    with pytest.raises(AuthorizationDenied):
        authorize_dispatch(target, root_id="other-root", **inputs)
    with pytest.raises(AuthorizationDenied):
        authorize_dispatch(
            target,
            root_id="synthetic-root",
            **{**inputs, "now": now + timedelta(minutes=2)},
        )

    assert authorization.calls_reserved == 0
    assert authorization.cost_reserved == Decimal("0")


def test_paid_dispatch_binds_authorization_to_operation_id_and_digest():
    now = datetime(2026, 10, 31, 12, 0, tzinfo=timezone.utc)
    target = ProviderTarget(kind="data", provider="fd")
    authorization = OneShotAuthorization(
        root_id="synthetic-root",
        subject_id="research-1",
        capture_digest="capture-digest",
        provider_id=target.identity,
        expires_at=now + timedelta(minutes=1),
        max_calls=2,
        max_cost=Decimal("0.50"),
        upper_bound_cost=Decimal("0.10"),
    )
    arguments = {
        "scope": OperationScope.MANUAL_ONE_SHOT,
        "root_id": "synthetic-root",
        "subject_id": "research-1",
        "capture_digest": "capture-digest",
        "now": now,
        "one_shot": authorization,
        "network_authorized": True,
        "upper_bound_cost": Decimal("0.10"),
    }

    with pytest.raises(AuthorizationDenied):
        _authorize_dispatch(
            target,
            operation_id="operation-2",
            operation_digest="c" * 64,
            **arguments,
        )
    with pytest.raises(AuthorizationDenied):
        _authorize_dispatch(
            target,
            operation_id=_OPERATION_ID,
            operation_digest="c" * 64,
            **arguments,
        )

    assert authorization.calls_reserved == 0
    assert authorization.cost_reserved == Decimal("0")


def test_dispatch_budget_reserves_upper_bound_before_call_and_stops_at_caps():
    budget = DispatchBudget(
        max_calls=2,
        max_cost=Decimal("0.75"),
        max_resources=3,
    )
    budget.reserve(upper_bound_cost=Decimal("0.40"), resource_units=2)

    assert budget.calls_reserved == 1
    assert budget.cost_reserved == Decimal("0.40")
    assert budget.resources_reserved == 2

    with pytest.raises(BudgetDenied):
        budget.reserve(upper_bound_cost=Decimal("0.40"), resource_units=1)
    with pytest.raises(BudgetDenied):
        budget.reserve(upper_bound_cost=Decimal("0.10"), resource_units=2)

    assert budget.calls_reserved == 1
    assert budget.cost_reserved == Decimal("0.40")
    assert budget.resources_reserved == 2


def test_runner_session_due_set_and_call_caps_are_finite():
    now = datetime(2026, 10, 31, 12, 0, tzinfo=timezone.utc)
    target = ProviderTarget(kind="data", provider="yfinance")
    authorization = RunnerAuthorization(
        root_id="synthetic-root",
        deployment_id="deployment-1",
        capture_digest="capture-digest",
        provider_ids=(target.identity,),
        expires_at=now + timedelta(hours=1),
        max_sessions=1,
        max_calls=1,
        max_resources=1,
        initial_due_set=("2026-10-31",),
    )
    session = {
        "root_id": "synthetic-root",
        "deployment_id": "deployment-1",
        "capture_digest": "capture-digest",
        "due_set": ("2026-10-31",),
        "now": now,
    }
    authorize_session(authorization, **session)
    authorize_dispatch(
        target,
        scope=OperationScope.SCHEDULED,
        root_id="synthetic-root",
        subject_id="deployment-1",
        capture_digest="capture-digest",
        now=now,
        runner=authorization,
        upper_bound_cost=Decimal("0"),
    )

    with pytest.raises(AuthorizationDenied):
        authorize_session(authorization, **session)
    with pytest.raises(AuthorizationDenied):
        authorize_dispatch(
            target,
            scope=OperationScope.SCHEDULED,
            root_id="synthetic-root",
            subject_id="deployment-1",
            capture_digest="capture-digest",
            now=now,
            runner=authorization,
            upper_bound_cost=Decimal("0"),
        )

    assert authorization.sessions_started == 1
    assert authorization.calls_reserved == 1


def test_runner_rejects_changed_due_set_before_session_reservation():
    now = datetime(2026, 10, 31, 12, 0, tzinfo=timezone.utc)
    target = ProviderTarget(kind="data", provider="yfinance")
    authorization = RunnerAuthorization(
        root_id="synthetic-root",
        deployment_id="deployment-1",
        capture_digest="capture-digest",
        provider_ids=(target.identity,),
        expires_at=now + timedelta(hours=1),
        max_sessions=2,
        max_calls=2,
        max_resources=2,
        initial_due_set=("2026-10-31",),
    )

    with pytest.raises(AuthorizationDenied):
        authorize_session(
            authorization,
            root_id="synthetic-root",
            deployment_id="deployment-1",
            capture_digest="capture-digest",
            due_set=("2026-11-01",),
            now=now,
        )

    assert authorization.sessions_started == 0


def test_runner_accepts_later_due_sets_only_within_finite_session_limit():
    now = datetime(2026, 10, 31, 12, 0, tzinfo=timezone.utc)
    authorization = RunnerAuthorization(
        root_id="synthetic-root",
        deployment_id="deployment-1",
        capture_digest="capture-digest",
        provider_ids=("provider-identity",),
        expires_at=now + timedelta(hours=1),
        max_sessions=2,
        max_calls=2,
        max_resources=2,
        initial_due_set=("2026-10-31",),
    )
    identity = {
        "root_id": "synthetic-root",
        "deployment_id": "deployment-1",
        "capture_digest": "capture-digest",
        "now": now,
    }

    assert authorize_session(authorization, due_set=("2026-10-31",), **identity) == 1
    assert authorize_session(authorization, due_set=("2026-11-01",), **identity) == 2
    with pytest.raises(AuthorizationDenied):
        authorize_session(authorization, due_set=("2026-11-02",), **identity)

    assert authorization.sessions_started == 2


def test_runner_with_no_initially_due_session_uses_finite_future_schedule():
    now = datetime(2026, 10, 31, 12, 0, tzinfo=timezone.utc)
    authorization = RunnerAuthorization(
        root_id="synthetic-root",
        deployment_id="deployment-1",
        capture_digest="capture-digest",
        provider_ids=("provider-identity",),
        expires_at=now + timedelta(hours=1),
        max_sessions=2,
        max_calls=2,
        max_resources=2,
        initial_due_set=(),
    )
    identity = {
        "root_id": "synthetic-root",
        "deployment_id": "deployment-1",
        "capture_digest": "capture-digest",
        "now": now,
    }

    assert (
        authorize_session(
            authorization,
            due_set=("2026-11-02",),
            **identity,
        )
        == 1
    )
    assert (
        authorize_session(
            authorization,
            due_set=("2026-11-03",),
            **identity,
        )
        == 2
    )
    with pytest.raises(AuthorizationDenied):
        authorize_session(
            authorization,
            due_set=("2026-11-04",),
            **identity,
        )

    assert authorization.sessions_started == 2


def test_runner_allows_bounded_free_data_preflight_before_first_session():
    now = datetime(2026, 10, 31, 12, 0, tzinfo=timezone.utc)
    target = ProviderTarget(kind="data", provider="yfinance")
    authorization = RunnerAuthorization(
        root_id="synthetic-root",
        deployment_id="deployment-1",
        capture_digest="capture-digest",
        provider_ids=(target.identity,),
        expires_at=now + timedelta(hours=1),
        max_sessions=1,
        max_calls=2,
        max_resources=2,
        initial_due_set=(),
    )

    assert (
        authorize_dispatch(
            target,
            scope=OperationScope.SCHEDULED,
            root_id="synthetic-root",
            subject_id="deployment-1",
            capture_digest="capture-digest",
            now=now,
            runner=authorization,
            upper_bound_cost=Decimal("0"),
        )
        is ProviderClass.FREE_DATA
    )
    assert authorization.calls_reserved == 1
    authorization = RunnerAuthorization(
        root_id="synthetic-root",
        deployment_id="deployment-1",
        capture_digest="capture-digest",
        provider_ids=("provider-identity",),
        expires_at=now + timedelta(hours=1),
        max_sessions=1,
        max_calls=2,
        max_resources=2,
        initial_due_set=(),
    )

    assert (
        authorize_session(
            authorization,
            root_id="synthetic-root",
            deployment_id="deployment-1",
            capture_digest="capture-digest",
            due_set=("2026-11-02",),
            now=now,
        )
        == 1
    )
    with pytest.raises(AuthorizationDenied):
        authorize_session(
            authorization,
            root_id="synthetic-root",
            deployment_id="deployment-1",
            capture_digest="capture-digest",
            due_set=("2026-11-03",),
            now=now,
        )
