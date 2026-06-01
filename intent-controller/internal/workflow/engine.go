package workflow

import (
	"context"
	"fmt"
	"log/slog"
	"time"

	"github.com/google/uuid"
	"github.com/precision-genomics/intent-controller/internal/activity"
	"github.com/precision-genomics/intent-controller/internal/models"
	"github.com/precision-genomics/intent-controller/internal/store"
)

// PhaseFunc executes one phase of a workflow and returns its result.
type PhaseFunc func(ctx context.Context, dispatcher *activity.Dispatcher, params map[string]interface{}, prevResults map[string]interface{}) (map[string]interface{}, error)

// Phase is a named step in a workflow definition. When Parallel is non-empty the
// phase fans out: every PhaseFunc in Parallel runs concurrently (each with retry)
// and their result maps are merged in branch order; Activity is ignored.
// Otherwise Activity runs on its own (with retry).
type Phase struct {
	Name     string
	Activity PhaseFunc
	Parallel []PhaseFunc
}

// Definition describes a workflow type as a sequence of phases.
type Definition struct {
	Type   string
	Phases []Phase
}

// recoverLeaseTTL bounds how long a claimed-but-unfinished workflow stays
// leased. It is comfortably longer than any single phase so a worker that
// crashes mid-resume has its claim reclaimed (orphan recovery) only after the
// in-flight run would plausibly have completed, never while it is still live.
const recoverLeaseTTL = 5 * time.Minute

// Engine manages workflow execution.
type Engine struct {
	workflows   *store.WorkflowRepo
	dispatcher  *activity.Dispatcher
	registry    map[string]Definition
	retryPolicy RetryPolicy
	workerID    string
}

// NewEngine creates a new workflow engine with built-in workflow definitions.
func NewEngine(workflows *store.WorkflowRepo, dispatcher *activity.Dispatcher) *Engine {
	e := &Engine{
		workflows:   workflows,
		dispatcher:  dispatcher,
		registry:    map[string]Definition{},
		retryPolicy: DefaultRetryPolicy(),
		workerID:    "engine",
	}
	e.registerDefaults()
	return e
}

// SetWorkerID sets the stable per-replica identity used to claim running
// workflows during Recover. Call once at startup before Recover. Defaults to
// "engine" so single-replica behaviour needs no configuration.
func (e *Engine) SetWorkerID(workerID string) {
	if workerID != "" {
		e.workerID = workerID
	}
}

func (e *Engine) registerDefaults() {
	e.registry["biomarker_discovery"] = Definition{
		Type: "biomarker_discovery",
		Phases: []Phase{
			{Name: "data_loading", Activity: phaseLoadAndValidate},
			{Name: "imputation", Parallel: fanOutModalities(imputeModality)},
			{Name: "feature_selection", Parallel: fanOutModalities(selectFeaturesForModality)},
			{Name: "integration", Activity: phaseIntegrateAndFilter},
			{Name: "classification", Activity: phaseTrainAndEvaluate},
			{Name: "interpretation", Activity: phaseInterpret},
			{Name: "report", Activity: phaseCompileReport},
		},
	}

	e.registry["sample_qc"] = Definition{
		Type: "sample_qc",
		Phases: []Phase{
			{Name: "data_loading", Activity: phaseLoadClinical},
			{Name: "classification_qc", Activity: phaseClassificationQC},
			{Name: "distance_matching", Activity: phaseDistanceMatrix},
			{Name: "cross_validation", Activity: phaseCrossValidate},
			{Name: "report", Activity: phaseCompileReport},
		},
	}

	e.registry["prompt_optimization"] = Definition{
		Type: "prompt_optimization",
		Phases: []Phase{
			{Name: "synthetic_cohort", Activity: phaseGenerateSynthetic},
			{Name: "baseline_run", Activity: phaseRunPipeline},
			{Name: "dspy_compile", Activity: phaseDSPYCompile},
			{Name: "optimized_run", Activity: phaseRunPipeline},
			{Name: "deploy", Activity: phaseCompareAndDeploy},
		},
	}

	e.registry["cosmo_pipeline"] = Definition{
		Type: "cosmo_pipeline",
		Phases: []Phase{
			{Name: "data_loading", Activity: phaseLoadAndValidate},
			{Name: "imputation", Activity: phaseImpute},
			{Name: "feature_selection", Activity: phaseSelectFeatures},
			{Name: "classification", Activity: phaseTrainAndEvaluate},
			{Name: "cross_omics", Activity: phaseMatchCrossOmics},
			{Name: "interpretation", Activity: phaseInterpret},
		},
	}
}

// Start creates a workflow execution record and begins running it asynchronously.
func (e *Engine) Start(ctx context.Context, workflowType string, params map[string]interface{}) (string, error) {
	def, ok := e.registry[workflowType]
	if !ok {
		return "", fmt.Errorf("unknown workflow type: %s", workflowType)
	}

	workflowID := fmt.Sprintf("%s-%s", workflowType[:min(len(workflowType), 10)], uuid.New().String()[:12])
	now := time.Now().UTC()

	wf := &models.WorkflowExecution{
		WorkflowID:      workflowID,
		WorkflowType:    workflowType,
		Status:          models.WorkflowStatusPending,
		CurrentPhase:    "pending",
		PhasesCompleted: []string{},
		Params:          params,
		StartedAt:       now,
		Result:          map[string]interface{}{},
	}

	if err := e.workflows.Create(ctx, wf); err != nil {
		return "", fmt.Errorf("create workflow: %w", err)
	}

	// Run asynchronously
	go e.execute(context.Background(), workflowID, def, params)

	slog.Info("workflow started", "workflow_id", workflowID, "type", workflowType)
	return workflowID, nil
}

// remainingPhases returns the phases whose Name is not present in completed,
// preserving the original phase order. It is the resume primitive shared by a
// fresh run (completed empty) and recovery (completed = phases already done).
func remainingPhases(phases []Phase, completed []string) []Phase {
	done := make(map[string]struct{}, len(completed))
	for _, name := range completed {
		done[name] = struct{}{}
	}

	remaining := make([]Phase, 0, len(phases))
	for _, phase := range phases {
		if _, ok := done[phase.Name]; ok {
			continue
		}
		remaining = append(remaining, phase)
	}
	return remaining
}

// execute runs all phases of a fresh workflow sequentially.
func (e *Engine) execute(ctx context.Context, workflowID string, def Definition, params map[string]interface{}) {
	e.runPhases(ctx, workflowID, remainingPhases(def.Phases, nil), params)
}

// runPhases drives the given phases to completion, persisting progress after
// each phase exactly as a fresh run does. It marks the workflow running on
// entry, records each completed phase, and finally marks the workflow
// completed (or failed on the first phase error). It is shared by execute and
// Recover so resumed workflows persist identically to fresh ones.
func (e *Engine) runPhases(ctx context.Context, workflowID string, phases []Phase, params map[string]interface{}) {
	running := string(models.WorkflowStatusRunning)
	e.workflows.UpdateProgress(ctx, workflowID, &running, nil, nil, nil, nil)

	results := map[string]interface{}{}

	for _, phase := range phases {
		e.workflows.UpdateProgress(ctx, workflowID, nil, &phase.Name, nil, nil, nil)

		result, err := e.runPhase(ctx, phase, params, results)
		if err != nil {
			slog.Error("workflow phase failed", "workflow_id", workflowID, "phase", phase.Name, "error", err)
			failed := string(models.WorkflowStatusFailed)
			errMsg := err.Error()
			e.workflows.UpdateProgress(ctx, workflowID, &failed, nil, nil, nil, &errMsg)
			return
		}

		if result != nil {
			results[phase.Name] = result
		}
		e.workflows.UpdateProgress(ctx, workflowID, nil, nil, &phase.Name, nil, nil)
	}

	completed := string(models.WorkflowStatusCompleted)
	e.workflows.UpdateProgress(ctx, workflowID, &completed, nil, nil, results, nil)
	slog.Info("workflow completed", "workflow_id", workflowID)
}

// Recover sweeps for workflows left in the "running" state by a previous
// process and resumes each one from its last completed phase. Workflows whose
// type is no longer registered are marked failed. Each resume runs in its own
// goroutine, mirroring Start, so Recover returns promptly without blocking
// startup.
//
// Recovery is cross-replica safe: instead of listing every running workflow it
// CLAIMS a leased batch (store.WorkflowRepo.ClaimRunning), so two replicas
// starting at once SPLIT the running workflows and never double-resume the same
// one. The lease is dropped when the workflow finalizes (UpdateProgress on a
// terminal status releases it). Workflows whose owner died mid-resume are
// reclaimed once their lease expires (recoverLeaseTTL); since ClaimRunning only
// returns lease-free or expired rows, simply running Recover again — at the
// next replica startup — performs orphan recovery. A standalone periodic
// orphan-reclaim sweep is left as a follow-up (see notes); it would just call
// ClaimRunning on a timer.
func (e *Engine) Recover(ctx context.Context) error {
	wfs, err := e.workflows.ClaimRunning(ctx, e.workerID, recoverLeaseTTL.Seconds(), 0)
	if err != nil {
		return fmt.Errorf("claim running workflows: %w", err)
	}

	for _, wf := range wfs {
		def, ok := e.registry[wf.WorkflowType]
		if !ok {
			slog.Warn("cannot recover workflow: unknown type, marking failed",
				"workflow_id", wf.WorkflowID, "type", wf.WorkflowType)
			failed := string(models.WorkflowStatusFailed)
			errMsg := fmt.Sprintf("unknown workflow type on recovery: %s", wf.WorkflowType)
			e.workflows.UpdateProgress(ctx, wf.WorkflowID, &failed, nil, nil, nil, &errMsg)
			continue
		}

		remaining := remainingPhases(def.Phases, wf.PhasesCompleted)
		slog.Info("recovering running workflow",
			"workflow_id", wf.WorkflowID, "type", wf.WorkflowType,
			"completed", len(wf.PhasesCompleted), "remaining", len(remaining))

		// Resume asynchronously, like Start. Use a background context so the
		// resume is not tied to the recovery sweep's lifetime.
		go e.runPhases(context.Background(), wf.WorkflowID, remaining, wf.Params)
	}

	slog.Info("workflow recovery sweep complete", "recovered", len(wfs))
	return nil
}

// GetWorkflow returns a workflow execution by ID.
func (e *Engine) GetWorkflow(ctx context.Context, workflowID string) (*models.WorkflowExecution, error) {
	return e.workflows.GetByWorkflowID(ctx, workflowID)
}

// CancelWorkflow cancels a running workflow.
func (e *Engine) CancelWorkflow(ctx context.Context, workflowID string) error {
	wf, err := e.workflows.GetByWorkflowID(ctx, workflowID)
	if err != nil || wf == nil {
		return fmt.Errorf("workflow %s not found", workflowID)
	}
	if wf.Status == models.WorkflowStatusCompleted || wf.Status == models.WorkflowStatusFailed || wf.Status == models.WorkflowStatusCancelled {
		return nil
	}
	cancelled := string(models.WorkflowStatusCancelled)
	return e.workflows.UpdateProgress(ctx, workflowID, &cancelled, nil, nil, nil, nil)
}

func min(a, b int) int {
	if a < b {
		return a
	}
	return b
}
