"""Tests for the intent controller lifecycle logic."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from evals import EvalResult
from intents.assurance import AssuranceLoop
from intents.controller import IntentController
from intents.infra_resolver import InfrastructureResolver
from intents.schemas import IntentStatus


@pytest.fixture
def mock_resolver():
    resolver = MagicMock(spec=InfrastructureResolver)
    resolver.resolve = AsyncMock(
        return_value={
            "worker_scaled": {"status": "scaled"},
            "gcs_data_staged": {"status": "staged"},
        }
    )
    resolver.all_resolved = MagicMock(return_value=True)
    return resolver


@pytest.fixture
def mock_assurance():
    assurance = MagicMock(spec=AssuranceLoop)
    assurance.evaluate = AsyncMock(
        return_value={
            "biological_validity": EvalResult(
                name="biological_validity",
                passed=True,
                score=0.75,
                threshold=0.60,
            ),
            "reproducibility": EvalResult(
                name="reproducibility",
                passed=True,
                score=0.90,
                threshold=0.85,
            ),
        }
    )
    assurance.all_passed = MagicMock(return_value=True)
    return assurance


@pytest.fixture
def controller(mock_resolver, mock_assurance):
    return IntentController(resolver=mock_resolver, assurance=mock_assurance)


# ---------------------------------------------------------------------------
# InfrastructureResolver unit tests
# ---------------------------------------------------------------------------


def test_resolver_all_resolved_happy():
    resolver = InfrastructureResolver()
    state = {
        "worker_scaled": {"status": "scaled"},
        "gcs_data_staged": {"status": "staged"},
    }
    assert resolver.all_resolved(state) is True


def test_resolver_all_resolved_with_failure():
    resolver = InfrastructureResolver()
    state = {
        "worker_scaled": {"status": "scaled"},
        "gcs_data_staged": {"status": "failed", "error": "no data"},
    }
    assert resolver.all_resolved(state) is False


def test_resolver_gpu_quota_within_limit():
    from intents.models import Intent

    resolver = InfrastructureResolver()
    intent = Intent(
        intent_id="training-test",
        intent_type="training",
        params={"num_gpus": 2},
    )

    import asyncio

    result = asyncio.run(resolver._check_gpu_quota(intent))
    assert result["status"] == "approved"
    assert result["num_gpus"] == 2


def test_resolver_gpu_quota_exceeds_limit():
    from intents.models import Intent

    resolver = InfrastructureResolver()
    intent = Intent(
        intent_id="training-test",
        intent_type="training",
        params={"num_gpus": 8},
    )

    import asyncio

    result = asyncio.run(resolver._check_gpu_quota(intent))
    assert result["status"] == "failed"
    assert "exceeds limit" in result["error"]


# ---------------------------------------------------------------------------
# AssuranceLoop unit tests
# ---------------------------------------------------------------------------


def test_assurance_all_passed_true():
    loop = AssuranceLoop()
    results = {
        "biological_validity": EvalResult(
            name="biological_validity",
            passed=True,
            score=0.75,
            threshold=0.60,
        ),
        "reproducibility": EvalResult(
            name="reproducibility",
            passed=True,
            score=0.90,
            threshold=0.85,
        ),
    }
    assert loop.all_passed(results) is True


def test_assurance_all_passed_false():
    loop = AssuranceLoop()
    results = {
        "biological_validity": EvalResult(
            name="biological_validity",
            passed=True,
            score=0.75,
            threshold=0.60,
        ),
        "reproducibility": EvalResult(
            name="reproducibility",
            passed=False,
            score=0.50,
            threshold=0.85,
        ),
    }
    assert loop.all_passed(results) is False


def test_assurance_empty_results_pass():
    loop = AssuranceLoop()
    assert loop.all_passed({}) is True


# ---------------------------------------------------------------------------
# Controller state transition validation
# ---------------------------------------------------------------------------


def test_valid_transitions_cover_happy_path():
    """The happy path DECLARED → RESOLVING → ACTIVE → VERIFYING → ACHIEVED
    must be valid according to the state machine."""
    from intents.schemas import VALID_TRANSITIONS

    path = [
        (IntentStatus.DECLARED, IntentStatus.RESOLVING),
        (IntentStatus.RESOLVING, IntentStatus.ACTIVE),
        (IntentStatus.ACTIVE, IntentStatus.VERIFYING),
        (IntentStatus.VERIFYING, IntentStatus.ACHIEVED),
    ]
    for from_state, to_state in path:
        assert to_state in VALID_TRANSITIONS[from_state], f"Transition {from_state} → {to_state} should be valid"


def test_cancel_from_any_non_terminal():
    """CANCELLED should be reachable from all non-terminal states."""
    from intents.schemas import TERMINAL_STATES, VALID_TRANSITIONS

    for state, allowed in VALID_TRANSITIONS.items():
        if state not in TERMINAL_STATES:
            assert IntentStatus.CANCELLED in allowed, f"CANCELLED should be reachable from {state}"


def test_blocked_can_retry():
    """BLOCKED should be able to go back to RESOLVING."""
    from intents.schemas import VALID_TRANSITIONS

    allowed = VALID_TRANSITIONS[IntentStatus.BLOCKED]
    assert IntentStatus.RESOLVING in allowed
