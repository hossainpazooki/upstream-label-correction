package intent

import (
	"context"
	"fmt"
	"log/slog"
	"time"

	"github.com/google/uuid"
	"github.com/precision-genomics/intent-controller/internal/activity"
	"github.com/precision-genomics/intent-controller/internal/models"
	"github.com/precision-genomics/intent-controller/internal/store"
	"github.com/precision-genomics/intent-controller/internal/workflow"
)

// Manager orchestrates the observe-decide-act-verify loop for intents.
type Manager struct {
	intents    *store.IntentRepo
	workflows  *store.WorkflowRepo
	engine     *workflow.Engine
	dispatcher *activity.Dispatcher
}

// NewManager creates a new intent manager.
func NewManager(
	intents *store.IntentRepo,
	workflows *store.WorkflowRepo,
	engine *workflow.Engine,
	dispatcher *activity.Dispatcher,
) *Manager {
	return &Manager{
		intents:    intents,
		workflows:  workflows,
		engine:     engine,
		dispatcher: dispatcher,
	}
}

// Create initializes a new intent and persists it.
func (m *Manager) Create(ctx context.Context, req models.CreateIntentRequest) (*models.Intent, error) {
	if err := req.Validate(); err != nil {
		return nil, err
	}

	intentID := fmt.Sprintf("%s-%s", req.IntentType, uuid.New().String()[:12])
	now := time.Now().UTC()

	intent := &models.Intent{
		IntentID:    intentID,
		IntentType:  req.IntentType,
		Status:      models.IntentStatusDeclared,
		Params:      req.Params,
		InfraState:  map[string]interface{}{},
		WorkflowIDs: []string{},
		EvalResults: map[string]interface{}{},
		CreatedAt:   now,
		RequestedBy: req.RequestedBy,
	}
	if intent.Params == nil {
		intent.Params = map[string]interface{}{}
	}

	if err := m.intents.Create(ctx, intent); err != nil {
		return nil, fmt.Errorf("create intent: %w", err)
	}

	slog.Info("intent created", "intent_id", intentID, "type", req.IntentType)
	return intent, nil
}

// Process drives the intent through its lifecycle. Idempotent.
func (m *Manager) Process(ctx context.Context, intentID string) (*models.Intent, error) {
	intent, err := m.intents.GetByIntentID(ctx, intentID)
	if err != nil {
		return nil, err
	}
	if intent == nil {
		return nil, fmt.Errorf("intent %s not found", intentID)
	}

	// DECLARED -> RESOLVING
	if intent.Status == models.IntentStatusDeclared {
		if err := m.beginResolution(ctx, intent); err != nil {
			return nil, err
		}
		intent, _ = m.intents.GetByIntentID(ctx, intentID)
	}

	// RESOLVING -> ACTIVE
	if intent.Status == models.IntentStatusResolving {
		if err := m.resolveAndActivate(ctx, intent); err != nil {
			return nil, err
		}
		intent, _ = m.intents.GetByIntentID(ctx, intentID)
	}

	// ACTIVE -> VERIFYING
	if intent.Status == models.IntentStatusActive {
		if err := m.checkWorkflows(ctx, intent); err != nil {
			return nil, err
		}
		intent, _ = m.intents.GetByIntentID(ctx, intentID)
	}

	// VERIFYING -> ACHIEVED/FAILED
	if intent.Status == models.IntentStatusVerifying {
		if err := m.verify(ctx, intent); err != nil {
			return nil, err
		}
		intent, _ = m.intents.GetByIntentID(ctx, intentID)
	}

	return intent, nil
}

// Cancel cancels a non-terminal intent.
func (m *Manager) Cancel(ctx context.Context, intentID string) (*models.Intent, error) {
	intent, err := m.intents.GetByIntentID(ctx, intentID)
	if err != nil {
		return nil, err
	}
	if intent == nil {
		return nil, fmt.Errorf("intent %s not found", intentID)
	}
	if models.TerminalStates[intent.Status] {
		return intent, nil
	}

	if err := m.transition(ctx, intent, models.IntentStatusCancelled); err != nil {
		return nil, err
	}
	return m.intents.GetByIntentID(ctx, intentID)
}

// beginResolution validates params and transitions DECLARED -> RESOLVING.
func (m *Manager) beginResolution(ctx context.Context, intent *models.Intent) error {
	spec, ok := models.IntentSpecs[intent.IntentType]
	if !ok {
		errMsg := fmt.Sprintf("unknown intent type: %s", intent.IntentType)
		intent.Status = models.IntentStatusFailed
		e := errMsg
		intent.Error = &e
		return m.intents.Update(ctx, intent)
	}
	_ = spec
	return m.transition(ctx, intent, models.IntentStatusResolving)
}

// resolveAndActivate provisions infrastructure, triggers workflows, and transitions RESOLVING -> ACTIVE.
func (m *Manager) resolveAndActivate(ctx context.Context, intent *models.Intent) error {
	spec := models.IntentSpecs[intent.IntentType]

	// Resolve infrastructure requirements
	infraState := map[string]interface{}{}
	for _, req := range spec.RequiredInfra {
		result, err := m.dispatcher.ResolveInfra(ctx, req, intent)
		if err != nil {
			slog.Error("infra resolution failed", "intent_id", intent.IntentID, "requirement", req, "error", err)
			intent.Status = models.IntentStatusBlocked
			e := fmt.Sprintf("infra resolution failed: %s: %v", req, err)
			intent.Error = &e
			intent.InfraState = infraState
			return m.intents.Update(ctx, intent)
		}
		infraState[req] = result
	}

	// Check all resolved
	for _, v := range infraState {
		if vm, ok := v.(map[string]interface{}); ok {
			if vm["status"] == "failed" {
				intent.Status = models.IntentStatusBlocked
				e := "one or more infra requirements not met"
				intent.Error = &e
				intent.InfraState = infraState
				return m.intents.Update(ctx, intent)
			}
		}
	}

	// Trigger child workflows
	workflowIDs, err := m.triggerWorkflows(ctx, intent)
	if err != nil {
		slog.Error("failed to trigger workflows", "intent_id", intent.IntentID, "error", err)
		intent.Status = models.IntentStatusFailed
		e := fmt.Sprintf("workflow trigger failed: %v", err)
		intent.Error = &e
		return m.intents.Update(ctx, intent)
	}

	intent.InfraState = infraState
	intent.WorkflowIDs = workflowIDs
	now := time.Now().UTC()
	intent.ActivatedAt = &now
	intent.Status = models.IntentStatusActive

	m.emitEvent(ctx, intent.IntentID, "state_change", stringPtr(string(models.IntentStatusResolving)), stringPtr(string(models.IntentStatusActive)), nil)
	return m.intents.Update(ctx, intent)
}

// checkWorkflows polls child workflows for completion.
func (m *Manager) checkWorkflows(ctx context.Context, intent *models.Intent) error {
	if len(intent.WorkflowIDs) == 0 {
		return m.transition(ctx, intent, models.IntentStatusVerifying)
	}

	allDone := true
	anyFailed := false

	for _, wfID := range intent.WorkflowIDs {
		wf, err := m.workflows.GetByWorkflowID(ctx, wfID)
		if err != nil || wf == nil {
			continue
		}
		switch wf.Status {
		case models.WorkflowStatusPending, models.WorkflowStatusRunning:
			allDone = false
		case models.WorkflowStatusFailed:
			anyFailed = true
		}
	}

	if anyFailed {
		intent.Status = models.IntentStatusFailed
		e := "one or more child workflows failed"
		intent.Error = &e
		return m.intents.Update(ctx, intent)
	}

	if allDone {
		return m.transition(ctx, intent, models.IntentStatusVerifying)
	}

	return nil // still in progress
}

// verify runs eval assurance and transitions VERIFYING -> ACHIEVED/FAILED.
func (m *Manager) verify(ctx context.Context, intent *models.Intent) error {
	spec := models.IntentSpecs[intent.IntentType]

	if len(spec.EvalCriteria) == 0 {
		// No eval criteria — achieved by completion.
		return m.achieve(ctx, intent, spec)
	}

	// Run eval criteria via ML service
	evalResults := map[string]interface{}{}
	allPassed := true

	for _, criterion := range spec.EvalCriteria {
		result, err := m.dispatcher.RunEval(ctx, criterion.Name, criterion.Threshold, intent)
		if err != nil {
			evalResults[criterion.Name] = map[string]interface{}{
				"score": 0.0, "threshold": criterion.Threshold, "passed": false,
				"details": map[string]interface{}{"error": err.Error()},
			}
			allPassed = false
			continue
		}
		evalResults[criterion.Name] = result
		// Trust-boundary defense (gap #6): the Go controller is the single
		// authority for ACHIEVED, so it does NOT blindly trust the ML service's
		// self-reported `passed`. checkEvalConsistency corroborates that boolean
		// against the numeric evidence in the SAME response; a malformed,
		// self-inconsistent (passed=true yet score<threshold), or gate-weakening
		// (threshold below the requested bar) result fails closed.
		passed, cerr := checkEvalConsistency(result, criterion)
		if cerr != nil {
			slog.Error("eval result failed consistency check",
				"intent_id", intent.IntentID, "eval", criterion.Name, "error", cerr)
			result["passed"] = false
			result["consistency_error"] = cerr.Error()
			allPassed = false
			continue
		}
		if !passed {
			allPassed = false
		}
	}

	intent.EvalResults = evalResults
	m.intents.Update(ctx, intent)

	if allPassed {
		return m.achieve(ctx, intent, spec)
	}

	failedEvals := []string{}
	for name, r := range evalResults {
		if rm, ok := r.(map[string]interface{}); ok {
			if passed, ok := rm["passed"].(bool); !ok || !passed {
				failedEvals = append(failedEvals, name)
			}
		}
	}
	e := fmt.Sprintf("eval criteria not met: %v", failedEvals)
	intent.Error = &e
	intent.Status = models.IntentStatusFailed
	return m.intents.Update(ctx, intent)
}

// checkEvalConsistency corroborates the ML service's self-reported `passed`
// against the numeric evidence in the same response (gap #6). It returns the
// trustworthy verdict, or an error when the response is malformed, internally
// inconsistent (passed=true yet score < threshold), or reports a threshold below
// the one the controller demanded (a silently weakened gate). Every honest eval
// satisfies threshold == requested and passed ⇒ score >= threshold, so this only
// fires on a buggy, compromised, or optimistic ML response — which the caller
// treats as a failed criterion (fail-closed).
func checkEvalConsistency(result map[string]interface{}, criterion models.EvalCriterion) (bool, error) {
	passed, ok := result["passed"].(bool)
	if !ok {
		return false, fmt.Errorf("missing or non-boolean 'passed'")
	}
	score, ok := evalFloat(result["score"])
	if !ok {
		return false, fmt.Errorf("missing or non-numeric 'score'")
	}
	threshold, ok := evalFloat(result["threshold"])
	if !ok {
		return false, fmt.Errorf("missing or non-numeric 'threshold'")
	}

	const eps = 1e-9
	if threshold < criterion.Threshold-eps {
		return false, fmt.Errorf("returned threshold %.4f is below the requested %.4f (gate weakened)", threshold, criterion.Threshold)
	}
	if passed && score < threshold-eps {
		return false, fmt.Errorf("passed=true but score %.4f < threshold %.4f", score, threshold)
	}
	return passed, nil
}

// evalFloat coerces a JSON-decoded number to float64 (encoding/json decodes all
// JSON numbers as float64; int cases are belt-and-suspenders).
func evalFloat(v interface{}) (float64, bool) {
	switch n := v.(type) {
	case float64:
		return n, true
	case int:
		return float64(n), true
	case int64:
		return float64(n), true
	}
	return 0, false
}

// triggerWorkflows starts child workflows based on intent type.
func (m *Manager) triggerWorkflows(ctx context.Context, intent *models.Intent) ([]string, error) {
	params := intent.Params
	var workflowIDs []string

	switch intent.IntentType {
	case "analysis":
		dataset, _ := params["dataset"].(string)
		if dataset == "" {
			dataset = "train"
		}
		target, _ := params["target"].(string)
		if target == "" {
			target = "msi"
		}
		analysisType, _ := params["analysis_type"].(string)
		if analysisType == "" {
			analysisType = "biomarker_discovery"
		}

		wfType := "biomarker_discovery"
		if analysisType == "sample_qc" {
			wfType = "sample_qc"
		}

		wfID, err := m.engine.Start(ctx, wfType, params)
		if err != nil {
			return nil, err
		}
		workflowIDs = append(workflowIDs, wfID)

		m.emitEvent(ctx, intent.IntentID, "workflow_started", nil, nil, map[string]interface{}{
			"workflow_id": wfID, "analysis_type": analysisType, "dataset": dataset, "target": target,
		})

	case "training":
		infraState := intent.InfraState
		jobInfo, _ := infraState["vertex_ai_job"].(map[string]interface{})
		jobName := fmt.Sprintf("train-%s", uuid.New().String()[:8])
		if ji, ok := jobInfo["job"].(map[string]interface{}); ok {
			if jn, ok := ji["job_name"].(string); ok {
				jobName = jn
			}
		}
		workflowIDs = append(workflowIDs, jobName)

		m.emitEvent(ctx, intent.IntentID, "workflow_started", nil, nil, map[string]interface{}{
			"workflow_id": jobName, "job_info": jobInfo,
		})

	case "validation":
		dataset, _ := params["dataset"].(string)
		if dataset == "" {
			dataset = "train"
		}
		wfID, err := m.engine.Start(ctx, "sample_qc", map[string]interface{}{"dataset": dataset})
		if err != nil {
			return nil, err
		}
		workflowIDs = append(workflowIDs, wfID)

		m.emitEvent(ctx, intent.IntentID, "workflow_started", nil, nil, map[string]interface{}{
			"workflow_id": wfID, "validation": true,
		})
	}

	return workflowIDs, nil
}

// achieve transitions an intent to ACHIEVED and, for deploy-triggering specs,
// chains to model deployment. It is shared by both VERIFY success paths — the
// no-criteria fast path and the gated all-passed path — so a TriggersDeploy
// intent deploys only after it actually reaches ACHIEVED. Previously the deploy
// chain lived solely in the no-criteria branch, so adding eval criteria to a
// deploy-triggering intent would have silently dropped the deploy.
func (m *Manager) achieve(ctx context.Context, intent *models.Intent, spec models.IntentSpec) error {
	if err := m.transition(ctx, intent, models.IntentStatusAchieved); err != nil {
		return err
	}
	if spec.TriggersDeploy {
		m.triggerDeploy(ctx, intent)
	}
	return nil
}

// triggerDeploy chains a training intent's success to model deployment.
func (m *Manager) triggerDeploy(ctx context.Context, intent *models.Intent) {
	imageTag, _ := intent.Params["image_tag"].(string)
	if imageTag == "" {
		imageTag = "latest"
	}
	stackName := "dev"
	if is, ok := intent.InfraState["stack_name"].(string); ok {
		stackName = is
	}

	err := m.dispatcher.DeployModel(ctx, stackName, imageTag)
	if err != nil {
		slog.Error("post-training deploy failed", "intent_id", intent.IntentID, "error", err)
		m.emitEvent(ctx, intent.IntentID, "error", nil, nil, map[string]interface{}{
			"action": "deploy_failed", "error": err.Error(),
		})
		return
	}

	m.emitEvent(ctx, intent.IntentID, "infra_update", nil, nil, map[string]interface{}{
		"action": "model_deployed", "image_tag": imageTag,
	})
}

// transition performs a validated state transition.
func (m *Manager) transition(ctx context.Context, intent *models.Intent, to models.IntentStatus) error {
	from := intent.Status
	if !models.IsValidTransition(from, to) {
		return fmt.Errorf("invalid transition %s -> %s for intent %s", from, to, intent.IntentID)
	}

	intent.Status = to
	now := time.Now().UTC()

	switch to {
	case models.IntentStatusResolving:
		if intent.ResolvedAt == nil {
			intent.ResolvedAt = &now
		}
	case models.IntentStatusActive:
		if intent.ActivatedAt == nil {
			intent.ActivatedAt = &now
		}
	case models.IntentStatusAchieved, models.IntentStatusFailed, models.IntentStatusCancelled:
		intent.CompletedAt = &now
	}

	if err := m.intents.Update(ctx, intent); err != nil {
		return err
	}

	m.emitEvent(ctx, intent.IntentID, "state_change", stringPtr(string(from)), stringPtr(string(to)), nil)
	return nil
}

func (m *Manager) emitEvent(ctx context.Context, intentID, eventType string, from, to *string, payload map[string]interface{}) {
	event := &models.IntentEvent{
		IntentID:   intentID,
		EventType:  eventType,
		FromStatus: from,
		ToStatus:   to,
		Payload:    payload,
		Timestamp:  time.Now().UTC(),
	}
	if event.Payload == nil {
		event.Payload = map[string]interface{}{}
	}
	if err := m.intents.EmitEvent(ctx, event); err != nil {
		slog.Error("failed to emit event", "intent_id", intentID, "error", err)
	}
}

func stringPtr(s string) *string { return &s }
