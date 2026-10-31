from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from hedge_fund.runtime.policy import AuthorizationDenied, authorize_dispatch, authorize_session, BudgetDenied, classify_provider, DispatchBudget, OneShotAuthorization, OperationScope, ProviderClass, ProviderTarget, RunnerAuthorization


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
        model="llama3.2",
        endpoint="http://127.0.0.1:11434",
    )
    remote_target = ProviderTarget(
        kind="llm",
        provider="ollama",
        model="llama3.2",
        endpoint="https://models.example.invalid",
    )

    assert classify_provider(cloud_target, approved_local_models={"llama3.2"}) is ProviderClass.PAID_CLOUD
    assert classify_provider(local_target, approved_local_models={"llama3.2"}) is ProviderClass.LOCAL
    assert classify_provider(remote_target, approved_local_models={"llama3.2"}) is ProviderClass.PAID_CLOUD


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
