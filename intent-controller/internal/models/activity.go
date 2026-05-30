package models

// ActivityType identifies a unit of work the controller dispatches to the
// Python ML service or to infrastructure resolution.
type ActivityType string

// Activity types dispatched by the controller.
const (
	ActivityResolveInfra ActivityType = "resolve_infra"
	ActivityRunEval      ActivityType = "run_eval"
	ActivityDeployModel  ActivityType = "deploy_model"
	ActivityMLCall       ActivityType = "ml_call"
)

// ActivityResult is the normalized outcome of a dispatched activity. The raw
// ML/infra payload is carried in Data; Status mirrors the "status" field that
// handlers set on infra-resolution maps ("scaled", "staged", "failed", ...).
type ActivityResult struct {
	Type   ActivityType           `json:"type"`
	Status string                 `json:"status"`
	Data   map[string]interface{} `json:"data,omitempty"`
	Error  *string                `json:"error,omitempty"`
}
