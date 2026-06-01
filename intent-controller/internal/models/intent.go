// Package models defines the core domain types for the intent controller:
// intents, workflow executions, activities, and their lifecycle states.
//
// These types mirror the (being-decommissioned) Python intents/ package and
// are the single source of truth shared by the store, intent, workflow,
// activity, and api packages.
package models

import (
	"fmt"
	"time"
)

// IntentStatus is a point in the intent lifecycle state machine.
type IntentStatus string

// Intent lifecycle states. The happy path is:
//
//	declared -> resolving -> active -> verifying -> achieved
//
// resolving may divert to blocked (unmet infra) and any non-terminal state
// may move to failed or cancelled.
const (
	IntentStatusDeclared  IntentStatus = "declared"
	IntentStatusResolving IntentStatus = "resolving"
	IntentStatusBlocked   IntentStatus = "blocked"
	IntentStatusActive    IntentStatus = "active"
	IntentStatusVerifying IntentStatus = "verifying"
	IntentStatusAchieved  IntentStatus = "achieved"
	IntentStatusFailed    IntentStatus = "failed"
	IntentStatusCancelled IntentStatus = "cancelled"
)

// TerminalStates are intent states from which no further transition occurs.
var TerminalStates = map[IntentStatus]bool{
	IntentStatusAchieved:  true,
	IntentStatusFailed:    true,
	IntentStatusCancelled: true,
}

// validTransitions maps each state to the states it may legally move to.
var validTransitions = map[IntentStatus]map[IntentStatus]bool{
	IntentStatusDeclared: {
		IntentStatusResolving: true,
		IntentStatusCancelled: true,
	},
	IntentStatusResolving: {
		IntentStatusActive:    true,
		IntentStatusBlocked:   true,
		IntentStatusFailed:    true,
		IntentStatusCancelled: true,
	},
	IntentStatusBlocked: {
		IntentStatusResolving: true,
		IntentStatusCancelled: true,
	},
	IntentStatusActive: {
		IntentStatusVerifying: true,
		IntentStatusFailed:    true,
		IntentStatusCancelled: true,
	},
	IntentStatusVerifying: {
		IntentStatusAchieved:  true,
		IntentStatusFailed:    true,
		IntentStatusCancelled: true,
	},
}

// IsValidTransition reports whether moving from -> to is a legal lifecycle step.
func IsValidTransition(from, to IntentStatus) bool {
	return validTransitions[from][to]
}

// Intent is a declarative goal the platform reconciles toward a desired state.
// It maps one-to-one to a row in the intents table.
type Intent struct {
	ID          int64                  `json:"id"`
	IntentID    string                 `json:"intent_id"`
	IntentType  string                 `json:"intent_type"`
	Status      IntentStatus           `json:"status"`
	Params      map[string]interface{} `json:"params"`
	InfraState  map[string]interface{} `json:"infra_state"`
	WorkflowIDs []string               `json:"workflow_ids"`
	EvalResults map[string]interface{} `json:"eval_results"`
	CreatedAt   time.Time              `json:"created_at"`
	ResolvedAt  *time.Time             `json:"resolved_at,omitempty"`
	ActivatedAt *time.Time             `json:"activated_at,omitempty"`
	CompletedAt *time.Time             `json:"completed_at,omitempty"`
	Error       *string                `json:"error,omitempty"`
	RequestedBy string                 `json:"requested_by"`
}

// IntentEvent is an entry in an intent's append-only audit trail.
type IntentEvent struct {
	ID         int64                  `json:"id"`
	IntentID   string                 `json:"intent_id"`
	EventType  string                 `json:"event_type"`
	FromStatus *string                `json:"from_status,omitempty"`
	ToStatus   *string                `json:"to_status,omitempty"`
	Payload    map[string]interface{} `json:"payload"`
	Timestamp  time.Time              `json:"timestamp"`
}

// CreateIntentRequest is the body of POST /api/v1/intents.
type CreateIntentRequest struct {
	IntentType  string                 `json:"intent_type"`
	Params      map[string]interface{} `json:"params"`
	RequestedBy string                 `json:"requested_by"`
}

// Validate checks required fields and applies defaults in place.
func (r *CreateIntentRequest) Validate() error {
	if r.IntentType == "" {
		return fmt.Errorf("intent_type is required")
	}
	if _, ok := IntentSpecs[r.IntentType]; !ok {
		return fmt.Errorf("unknown intent type: %s", r.IntentType)
	}
	if r.RequestedBy == "" {
		r.RequestedBy = "agent"
	}
	return nil
}

// EvalCriterion is a named acceptance gate with a minimum passing score.
type EvalCriterion struct {
	Name      string  `json:"name"`
	Threshold float64 `json:"threshold"`
}

// IntentSpec is the frozen configuration for one intent type. It mirrors the
// dataclasses in the Python intents/types.py module.
type IntentSpec struct {
	IntentType          string          `json:"intent_type"`
	RequiredInfra       []string        `json:"required_infra"`
	EvalCriteria        []EvalCriterion `json:"eval_criteria"`
	ValidationGateStage int             `json:"validation_gate_stage,omitempty"`
	MaxGPUCount         int             `json:"max_gpu_count,omitempty"`
	TriggersDeploy      bool            `json:"triggers_deploy,omitempty"`
}

// IntentSpecs is the registry of supported intent types, keyed by intent_type.
// Mirrors INTENT_SPECS in intents/types.py.
var IntentSpecs = map[string]IntentSpec{
	"analysis": {
		IntentType:    "analysis",
		RequiredInfra: []string{"worker_scaled", "gcs_data_staged"},
		EvalCriteria: []EvalCriterion{
			{Name: "biological_validity", Threshold: 0.60},
			{Name: "reproducibility", Threshold: 0.85},
		},
		ValidationGateStage: 2,
	},
	"training": {
		IntentType:     "training",
		RequiredInfra:  []string{"vertex_ai_job", "gpu_allocated"},
		EvalCriteria:   []EvalCriterion{},
		MaxGPUCount:    4,
		TriggersDeploy: true,
	},
	"validation": {
		IntentType:    "validation",
		RequiredInfra: []string{},
		EvalCriteria: []EvalCriterion{
			{Name: "hallucination_detection", Threshold: 0.90},
			{Name: "adversarial_robustness", Threshold: 1.0},
		},
	},
}
