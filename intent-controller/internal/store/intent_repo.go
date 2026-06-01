package store

import (
	"context"
	"encoding/json"
	"fmt"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/precision-genomics/intent-controller/internal/models"
)

// IntentRepo provides CRUD operations for intents.
type IntentRepo struct {
	db *Postgres
}

// NewIntentRepo creates a new IntentRepo.
func NewIntentRepo(db *Postgres) *IntentRepo {
	return &IntentRepo{db: db}
}

// Create inserts a new intent record.
func (r *IntentRepo) Create(ctx context.Context, intent *models.Intent) error {
	paramsJSON, _ := json.Marshal(intent.Params)
	infraJSON, _ := json.Marshal(intent.InfraState)
	wfJSON, _ := json.Marshal(intent.WorkflowIDs)
	evalJSON, _ := json.Marshal(intent.EvalResults)

	err := r.db.Pool.QueryRow(ctx,
		`INSERT INTO intents (intent_id, intent_type, status, params, infra_state, workflow_ids, eval_results, requested_by, created_at)
		 VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
		 RETURNING id`,
		intent.IntentID, intent.IntentType, intent.Status,
		paramsJSON, infraJSON, wfJSON, evalJSON,
		intent.RequestedBy, intent.CreatedAt,
	).Scan(&intent.ID)
	if err != nil {
		return fmt.Errorf("insert intent: %w", err)
	}
	return nil
}

// GetByIntentID loads an intent by its intent_id.
func (r *IntentRepo) GetByIntentID(ctx context.Context, intentID string) (*models.Intent, error) {
	row := r.db.Pool.QueryRow(ctx,
		`SELECT id, intent_id, intent_type, status, params, infra_state, workflow_ids, eval_results,
		        created_at, resolved_at, activated_at, completed_at, error, requested_by
		 FROM intents WHERE intent_id = $1`, intentID)
	return scanIntent(row)
}

// List returns intents filtered by optional status and type.
func (r *IntentRepo) List(ctx context.Context, status, intentType string, limit, offset int) ([]*models.Intent, error) {
	query := `SELECT id, intent_id, intent_type, status, params, infra_state, workflow_ids, eval_results,
	                 created_at, resolved_at, activated_at, completed_at, error, requested_by
	          FROM intents WHERE 1=1`
	args := []interface{}{}
	argIdx := 1

	if status != "" {
		query += fmt.Sprintf(" AND status = $%d", argIdx)
		args = append(args, status)
		argIdx++
	}
	if intentType != "" {
		query += fmt.Sprintf(" AND intent_type = $%d", argIdx)
		args = append(args, intentType)
		argIdx++
	}

	query += " ORDER BY created_at DESC"

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
		return nil, fmt.Errorf("list intents: %w", err)
	}
	defer rows.Close()

	var intents []*models.Intent
	for rows.Next() {
		intent, err := scanIntentFromRows(rows)
		if err != nil {
			return nil, err
		}
		intents = append(intents, intent)
	}
	return intents, rows.Err()
}

// ClaimIntents atomically leases up to limit non-terminal intents to workerID.
//
// It selects rows whose status is in statuses and whose lease is free (NULL or
// expired), locks them with FOR UPDATE SKIP LOCKED so concurrent callers never
// contend on the same rows, and stamps locked_by + lease_expires_at in a single
// UPDATE. Because SKIP LOCKED hands each row to exactly one transaction, two
// workers calling this concurrently receive DISJOINT row sets. The lease expires
// after ttlSeconds so a worker that crashes mid-process has its claim reclaimed
// by the next caller. With a single worker every eligible row is returned, so
// behaviour is unchanged from the previous List-and-process loop.
//
// The RETURNING list matches List() exactly so the existing scanIntentFromRows
// helper applies and the lease columns stay out of the model struct.
func (r *IntentRepo) ClaimIntents(ctx context.Context, workerID string, statuses []string, ttlSeconds float64, limit int) ([]*models.Intent, error) {
	if limit <= 0 {
		limit = 100
	}
	const query = `
		UPDATE intents SET locked_by = $1, lease_expires_at = now() + make_interval(secs => $2)
		WHERE id IN (
			SELECT id FROM intents
			WHERE status = ANY($3)
			  AND (lease_expires_at IS NULL OR lease_expires_at < now())
			ORDER BY id
			FOR UPDATE SKIP LOCKED
			LIMIT $4
		)
		RETURNING id, intent_id, intent_type, status, params, infra_state, workflow_ids, eval_results,
		          created_at, resolved_at, activated_at, completed_at, error, requested_by`

	rows, err := r.db.Pool.Query(ctx, query, workerID, ttlSeconds, statuses, limit)
	if err != nil {
		return nil, fmt.Errorf("claim intents: %w", err)
	}
	defer rows.Close()

	var intents []*models.Intent
	for rows.Next() {
		intent, err := scanIntentFromRows(rows)
		if err != nil {
			return nil, err
		}
		intents = append(intents, intent)
	}
	return intents, rows.Err()
}

// ReleaseIntent clears the lease on an intent so the next reconcile tick can
// re-claim it (to advance the next FSM step). Safe to call on an unclaimed row.
func (r *IntentRepo) ReleaseIntent(ctx context.Context, intentID string) error {
	_, err := r.db.Pool.Exec(ctx,
		`UPDATE intents SET locked_by = NULL, lease_expires_at = NULL WHERE intent_id = $1`,
		intentID,
	)
	if err != nil {
		return fmt.Errorf("release intent: %w", err)
	}
	return nil
}

// Update modifies an existing intent record.
func (r *IntentRepo) Update(ctx context.Context, intent *models.Intent) error {
	paramsJSON, _ := json.Marshal(intent.Params)
	infraJSON, _ := json.Marshal(intent.InfraState)
	wfJSON, _ := json.Marshal(intent.WorkflowIDs)
	evalJSON, _ := json.Marshal(intent.EvalResults)

	_, err := r.db.Pool.Exec(ctx,
		`UPDATE intents SET
			status = $1, params = $2, infra_state = $3, workflow_ids = $4, eval_results = $5,
			resolved_at = $6, activated_at = $7, completed_at = $8, error = $9
		 WHERE intent_id = $10`,
		intent.Status, paramsJSON, infraJSON, wfJSON, evalJSON,
		intent.ResolvedAt, intent.ActivatedAt, intent.CompletedAt, intent.Error,
		intent.IntentID,
	)
	if err != nil {
		return fmt.Errorf("update intent: %w", err)
	}
	return nil
}

// EmitEvent appends an event to the audit trail.
func (r *IntentRepo) EmitEvent(ctx context.Context, event *models.IntentEvent) error {
	payloadJSON, _ := json.Marshal(event.Payload)
	_, err := r.db.Pool.Exec(ctx,
		`INSERT INTO intent_events (intent_id, event_type, from_status, to_status, payload, timestamp)
		 VALUES ($1, $2, $3, $4, $5, $6)`,
		event.IntentID, event.EventType, event.FromStatus, event.ToStatus, payloadJSON, event.Timestamp,
	)
	if err != nil {
		return fmt.Errorf("emit event: %w", err)
	}
	return nil
}

// helpers

func scanIntent(row pgx.Row) (*models.Intent, error) {
	var i models.Intent
	var paramsJSON, infraJSON, wfJSON, evalJSON []byte

	err := row.Scan(
		&i.ID, &i.IntentID, &i.IntentType, &i.Status,
		&paramsJSON, &infraJSON, &wfJSON, &evalJSON,
		&i.CreatedAt, &i.ResolvedAt, &i.ActivatedAt, &i.CompletedAt,
		&i.Error, &i.RequestedBy,
	)
	if err != nil {
		if err == pgx.ErrNoRows {
			return nil, nil
		}
		return nil, fmt.Errorf("scan intent: %w", err)
	}

	i.Params = mustUnmarshalMap(paramsJSON)
	i.InfraState = mustUnmarshalMap(infraJSON)
	i.EvalResults = mustUnmarshalMap(evalJSON)

	var wfIDs []string
	json.Unmarshal(wfJSON, &wfIDs)
	i.WorkflowIDs = wfIDs

	return &i, nil
}

func scanIntentFromRows(rows pgx.Rows) (*models.Intent, error) {
	var i models.Intent
	var paramsJSON, infraJSON, wfJSON, evalJSON []byte

	err := rows.Scan(
		&i.ID, &i.IntentID, &i.IntentType, &i.Status,
		&paramsJSON, &infraJSON, &wfJSON, &evalJSON,
		&i.CreatedAt, &i.ResolvedAt, &i.ActivatedAt, &i.CompletedAt,
		&i.Error, &i.RequestedBy,
	)
	if err != nil {
		return nil, fmt.Errorf("scan intent row: %w", err)
	}

	i.Params = mustUnmarshalMap(paramsJSON)
	i.InfraState = mustUnmarshalMap(infraJSON)
	i.EvalResults = mustUnmarshalMap(evalJSON)

	var wfIDs []string
	json.Unmarshal(wfJSON, &wfIDs)
	i.WorkflowIDs = wfIDs

	return &i, nil
}

func mustUnmarshalMap(data []byte) map[string]interface{} {
	m := map[string]interface{}{}
	if len(data) > 0 {
		json.Unmarshal(data, &m)
	}
	return m
}

// helper used by intent lifecycle
func ptr(s string) *string { return &s }

func now() time.Time { return time.Now().UTC() }
