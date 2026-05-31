package models

import "time"

// WorkflowStatus is the execution state of a workflow run.
type WorkflowStatus string

// Workflow execution states.
const (
	WorkflowStatusPending   WorkflowStatus = "pending"
	WorkflowStatusRunning   WorkflowStatus = "running"
	WorkflowStatusCompleted WorkflowStatus = "completed"
	WorkflowStatusFailed    WorkflowStatus = "failed"
	WorkflowStatusCancelled WorkflowStatus = "cancelled"
)

// WorkflowExecution is one run of a workflow definition. It maps one-to-one to
// a row in the workflow_executions table.
type WorkflowExecution struct {
	ID              int64                  `json:"id"`
	WorkflowID      string                 `json:"workflow_id"`
	WorkflowType    string                 `json:"workflow_type"`
	Status          WorkflowStatus         `json:"status"`
	CurrentPhase    string                 `json:"current_phase"`
	PhasesCompleted []string               `json:"phases_completed"`
	Params          map[string]interface{} `json:"params"`
	StartedAt       time.Time              `json:"started_at"`
	CompletedAt     *time.Time             `json:"completed_at,omitempty"`
	Result          map[string]interface{} `json:"result"`
	Error           *string                `json:"error,omitempty"`
}

// TriggerWorkflowRequest is the body of POST /api/v1/workflows.
type TriggerWorkflowRequest struct {
	WorkflowType string                 `json:"workflow_type"`
	Params       map[string]interface{} `json:"params"`
}
