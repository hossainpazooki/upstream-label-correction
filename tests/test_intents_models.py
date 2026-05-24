"""Tests for intent data models, schemas, and type specs."""

from __future__ import annotations

from intents.models import Intent, IntentEvent
from intents.schemas import TERMINAL_STATES, VALID_TRANSITIONS, IntentStatus
from intents.types import (
    INTENT_SPECS,
    AnalysisIntentSpec,
    TrainingIntentSpec,
    ValidationIntentSpec,
)

# ---------------------------------------------------------------------------
# IntentStatus enum
# ---------------------------------------------------------------------------


def test_intent_status_values():
    assert IntentStatus.DECLARED == "declared"
    assert IntentStatus.RESOLVING == "resolving"
    assert IntentStatus.BLOCKED == "blocked"
    assert IntentStatus.ACTIVE == "active"
    assert IntentStatus.VERIFYING == "verifying"
    assert IntentStatus.ACHIEVED == "achieved"
    assert IntentStatus.FAILED == "failed"
    assert IntentStatus.CANCELLED == "cancelled"


def test_terminal_states():
    assert IntentStatus.ACHIEVED in TERMINAL_STATES
    assert IntentStatus.FAILED in TERMINAL_STATES
    assert IntentStatus.CANCELLED in TERMINAL_STATES
    assert IntentStatus.ACTIVE not in TERMINAL_STATES


def test_valid_transitions_declared():
    allowed = VALID_TRANSITIONS[IntentStatus.DECLARED]
    assert IntentStatus.RESOLVING in allowed
    assert IntentStatus.CANCELLED in allowed
    assert IntentStatus.ACTIVE not in allowed


def test_valid_transitions_resolving():
    allowed = VALID_TRANSITIONS[IntentStatus.RESOLVING]
    assert IntentStatus.ACTIVE in allowed
    assert IntentStatus.BLOCKED in allowed
    assert IntentStatus.FAILED in allowed


def test_valid_transitions_active():
    allowed = VALID_TRANSITIONS[IntentStatus.ACTIVE]
    assert IntentStatus.VERIFYING in allowed
    assert IntentStatus.FAILED in allowed
    assert IntentStatus.DECLARED not in allowed


def test_valid_transitions_verifying():
    allowed = VALID_TRANSITIONS[IntentStatus.VERIFYING]
    assert IntentStatus.ACHIEVED in allowed
    assert IntentStatus.FAILED in allowed


def test_terminal_states_have_no_transitions():
    for state in TERMINAL_STATES:
        assert state not in VALID_TRANSITIONS


# ---------------------------------------------------------------------------
# Intent type specs
# ---------------------------------------------------------------------------


def test_intent_specs_registry():
    assert "analysis" in INTENT_SPECS
    assert "training" in INTENT_SPECS
    assert "validation" in INTENT_SPECS


def test_analysis_spec():
    spec = INTENT_SPECS["analysis"]
    assert isinstance(spec, AnalysisIntentSpec)
    assert spec.intent_type == "analysis"
    assert "worker_scaled" in spec.required_infra
    assert "gcs_data_staged" in spec.required_infra
    # Eval criteria: biological_validity >= 0.60, reproducibility >= 0.85
    eval_names = [name for name, _ in spec.eval_criteria]
    assert "biological_validity" in eval_names
    assert "reproducibility" in eval_names
    thresholds = dict(spec.eval_criteria)
    assert thresholds["biological_validity"] == 0.60
    assert thresholds["reproducibility"] == 0.85
    assert spec.validation_gate_stage == 2


def test_training_spec():
    spec = INTENT_SPECS["training"]
    assert isinstance(spec, TrainingIntentSpec)
    assert "vertex_ai_job" in spec.required_infra
    assert "gpu_allocated" in spec.required_infra
    assert spec.eval_criteria == ()
    assert spec.max_gpu_count == 4
    assert spec.triggers_deploy is True


def test_validation_spec():
    spec = INTENT_SPECS["validation"]
    assert isinstance(spec, ValidationIntentSpec)
    assert spec.required_infra == ()
    thresholds = dict(spec.eval_criteria)
    assert thresholds["hallucination_detection"] == 0.90


def test_specs_are_frozen():
    spec = INTENT_SPECS["analysis"]
    try:
        spec.intent_type = "something_else"
        raise AssertionError("Should have raised FrozenInstanceError")
    except AttributeError:
        pass


# ---------------------------------------------------------------------------
# SQLModel table schemas
# ---------------------------------------------------------------------------


def test_intent_model_defaults():
    intent = Intent(intent_id="test-123", intent_type="analysis")
    assert intent.status == "declared"
    assert intent.params == {}
    assert intent.infra_state == {}
    assert intent.workflow_ids == []
    assert intent.eval_results == {}
    assert intent.requested_by == "agent"
    assert intent.error is None


def test_intent_event_defaults():
    event = IntentEvent(intent_id="test-123", event_type="state_change")
    assert event.from_status is None
    assert event.to_status is None
    assert event.payload == {}
