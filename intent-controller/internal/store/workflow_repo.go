package store

import (
	"context"
	"encoding/json"
	"fmt"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/precision-genomics/intent-controller/internal/models"
)

// WorkflowRepo provides CRUD operations for workflow executions.
type WorkflowRepo struct {
	db *Postgres
}

// NewWorkflowRepo creates a new WorkflowRepo.
func NewWorkflowRepo(db *Postgres) *WorkflowRepo {
	return &WorkflowRepo{db: db}
}

// Create inserts a new workflow execution record.
func (r *WorkflowRepo) Create(ctx context.Context, wf *models.WorkflowExecution) error {
	phasesJSON, _ := json.Marshal(wf.PhasesCompleted)
	paramsJSON, _ := json.Marshal(wf.Params)
	resultJSON, _ := json.Marshal(wf.Result)

	err := r.db.Pool.QueryRow(ctx,
		`INSERT INTO workflow_executions (workflow_id, workflow_type, status, current_phase, phases_completed, params, started_at, result)
		 VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
		 RETURNING id`,
		wf.WorkflowID, wf.WorkflowType, wf.Status,
		wf.CurrentPhase, phasesJSON, paramsJSON, wf.StartedAt, resultJSON,
	).Scan(&wf.ID)
	if err != nil {
		return fmt.Errorf("insert workflow: %w", err)
	}
	return nil
}

// GetByWorkflowID loads a workflow execution by its workflow_id.
func (r *WorkflowRepo) GetByWorkflowID(ctx context.Context, workflowID string) (*models.WorkflowExecution, error) {
	row := r.db.Pool.QueryRow(ctx,
		`SELECT id, workflow_id, workflow_type, status, current_phase, phases_completed, params,
		        started_at, completed_at, result, error
		 FROM workflow_executions WHERE workflow_id = $1`, workflowID)
	return scanWorkflow(row)
}

// Update modifies an existing workflow execution.
func (r *WorkflowRepo) Update(ctx context.Context, wf *models.WorkflowExecution) error {
	phasesJSON, _ := json.Marshal(wf.PhasesCompleted)
	resultJSON, _ := json.Marshal(wf.Result)

	_, err := r.db.Pool.Exec(ctx,
		`UPDATE workflow_executions SET
			status = $1, current_phase = $2, phases_completed = $3,
			completed_at = $4, result = $5, error = $6
		 WHERE workflow_id = $7`,
		wf.Status, wf.CurrentPhase, phasesJSON,
		wf.CompletedAt, resultJSON, wf.Error,
		wf.WorkflowID,
	)
	if err != nil {
		return fmt.Errorf("update workflow: %w", err)
	}
	return nil
}

// List returns workflow executions with optional status filter.
func (r *WorkflowRepo) List(ctx context.Context, status string, limit, offset int) ([]*models.WorkflowExecution, error) {
	query := `SELECT id, workflow_id, workflow_type, status, current_phase, phases_completed, params,
	                 started_at, completed_at, result, error
	          FROM workflow_executions WHERE 1=1`
	args := []interface{}{}
	argIdx := 1

	if status != "" {
		query += fmt.Sprintf(" AND status = $%d", argIdx)
		args = append(args, status)
		argIdx++
	}
	query += " ORDER BY started_at DESC"

	if limit > 0 {
		query += fmt.Sprintf(" LIMIT $%d", argIdx)
		args = append(args, limit)
		argIdx++
	}
	if offset > 0 {
		query += fmt.Sprintf(" OFFSET $%d", argIdx)
		args = append(args, offset)
	}

	rows, err := r.db.Pool.Query(ctx, query, args...)
	if err != nil {
		return nil, fmt.Errorf("list workflows: %w", err)
	}
	defer rows.Close()

	var workflows []*models.WorkflowExecution
	for rows.Next() {
		wf, err := scanWorkflowFromRows(rows)
		if err != nil {
			return nil, err
		}
		workflows = append(workflows, wf)
	}
	return workflows, rows.Err()
}

// UpdateProgress updates specific progress fields on a workflow execution.
func (r *WorkflowRepo) UpdateProgress(ctx context.Context, workflowID string, status *string, currentPhase *string, phaseCompleted *string, result map[string]interface{}, errMsg *string) error {
	wf, err := r.GetByWorkflowID(ctx, workflowID)
	if err != nil || wf == nil {
		return fmt.Errorf("workflow %s not found", workflowID)
	}

	if status != nil {
		wf.Status = models.WorkflowStatus(*status)
	}
	if currentPhase != nil {
		wf.CurrentPhase = *currentPhase
	}
	if phaseCompleted != nil {
		found := false
		for _, p := range wf.PhasesCompleted {
			if p == *phaseCompleted {
				found = true
				break
			}
		}
		if !found {
			wf.PhasesCompleted = append(wf.PhasesCompleted, *phaseCompleted)
		}
	}
	if result != nil {
		wf.Result = result
	}
	if errMsg != nil {
		wf.Error = errMsg
	}
	if status != nil && (*status == "completed" || *status == "failed") {
		t := time.Now().UTC()
		wf.CompletedAt = &t
	}

	return r.Update(ctx, wf)
}

func scanWorkflow(row pgx.Row) (*models.WorkflowExecution, error) {
	var wf models.WorkflowExecution
	var phasesJSON, paramsJSON, resultJSON []byte

	err := row.Scan(
		&wf.ID, &wf.WorkflowID, &wf.WorkflowType, &wf.Status,
		&wf.CurrentPhase, &phasesJSON, &paramsJSON,
		&wf.StartedAt, &wf.CompletedAt, &resultJSON, &wf.Error,
	)
	if err != nil {
		if err == pgx.ErrNoRows {
			return nil, nil
		}
		return nil, fmt.Errorf("scan workflow: %w", err)
	}

	var phases []string
	json.Unmarshal(phasesJSON, &phases)
	wf.PhasesCompleted = phases

	wf.Params = mustUnmarshalMap(paramsJSON)
	wf.Result = mustUnmarshalMap(resultJSON)

	return &wf, nil
}

func scanWorkflowFromRows(rows pgx.Rows) (*models.WorkflowExecution, error) {
	var wf models.WorkflowExecution
	var phasesJSON, paramsJSON, resultJSON []byte

	err := rows.Scan(
		&wf.ID, &wf.WorkflowID, &wf.WorkflowType, &wf.Status,
		&wf.CurrentPhase, &phasesJSON, &paramsJSON,
		&wf.StartedAt, &wf.CompletedAt, &resultJSON, &wf.Error,
	)
	if err != nil {
		return nil, fmt.Errorf("scan workflow row: %w", err)
	}

	var phases []string
	json.Unmarshal(phasesJSON, &phases)
	wf.PhasesCompleted = phases

	wf.Params = mustUnmarshalMap(paramsJSON)
	wf.Result = mustUnmarshalMap(resultJSON)

	return &wf, nil
}
