package store

import (
	"context"
	"fmt"
	"log/slog"

	"github.com/jackc/pgx/v5/pgxpool"
)

// Postgres wraps a pgx connection pool and provides migration support.
type Postgres struct {
	Pool *pgxpool.Pool
}

// NewPostgres creates a new connection pool.
func NewPostgres(ctx context.Context, connStr string) (*Postgres, error) {
	pool, err := pgxpool.New(ctx, connStr)
	if err != nil {
		return nil, fmt.Errorf("pgxpool.New: %w", err)
	}
	if err := pool.Ping(ctx); err != nil {
		pool.Close()
		return nil, fmt.Errorf("ping: %w", err)
	}
	slog.Info("connected to postgres")
	return &Postgres{Pool: pool}, nil
}

// Close shuts down the connection pool.
func (p *Postgres) Close() {
	p.Pool.Close()
}

// Migrate creates required tables if they don't exist.
func (p *Postgres) Migrate(ctx context.Context) error {
	ddl := `
	CREATE TABLE IF NOT EXISTS intents (
		id             BIGSERIAL PRIMARY KEY,
		intent_id      TEXT NOT NULL UNIQUE,
		intent_type    TEXT NOT NULL,
		status         TEXT NOT NULL DEFAULT 'declared',
		params         JSONB NOT NULL DEFAULT '{}',
		infra_state    JSONB NOT NULL DEFAULT '{}',
		workflow_ids   JSONB NOT NULL DEFAULT '[]',
		eval_results   JSONB NOT NULL DEFAULT '{}',
		created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
		resolved_at    TIMESTAMPTZ,
		activated_at   TIMESTAMPTZ,
		completed_at   TIMESTAMPTZ,
		error          TEXT,
		requested_by   TEXT NOT NULL DEFAULT 'agent'
	);
	CREATE INDEX IF NOT EXISTS idx_intents_intent_id ON intents(intent_id);
	CREATE INDEX IF NOT EXISTS idx_intents_status ON intents(status);
	CREATE INDEX IF NOT EXISTS idx_intents_intent_type ON intents(intent_type);

	CREATE TABLE IF NOT EXISTS intent_events (
		id          BIGSERIAL PRIMARY KEY,
		intent_id   TEXT NOT NULL,
		event_type  TEXT NOT NULL,
		from_status TEXT,
		to_status   TEXT,
		payload     JSONB NOT NULL DEFAULT '{}',
		timestamp   TIMESTAMPTZ NOT NULL DEFAULT NOW()
	);
	CREATE INDEX IF NOT EXISTS idx_intent_events_intent_id ON intent_events(intent_id);
	CREATE INDEX IF NOT EXISTS idx_intent_events_timestamp ON intent_events(timestamp);

	CREATE TABLE IF NOT EXISTS workflow_executions (
		id               BIGSERIAL PRIMARY KEY,
		workflow_id      TEXT NOT NULL UNIQUE,
		workflow_type    TEXT NOT NULL,
		status           TEXT NOT NULL DEFAULT 'pending',
		current_phase    TEXT NOT NULL DEFAULT 'pending',
		phases_completed JSONB NOT NULL DEFAULT '[]',
		params           JSONB NOT NULL DEFAULT '{}',
		started_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
		completed_at     TIMESTAMPTZ,
		result           JSONB NOT NULL DEFAULT '{}',
		error            TEXT
	);
	CREATE INDEX IF NOT EXISTS idx_workflow_executions_workflow_id ON workflow_executions(workflow_id);
	CREATE INDEX IF NOT EXISTS idx_workflow_executions_status ON workflow_executions(status);

	-- Migrate existing databases created before params was added.
	ALTER TABLE workflow_executions ADD COLUMN IF NOT EXISTS params JSONB NOT NULL DEFAULT '{}';
	`
	_, err := p.Pool.Exec(ctx, ddl)
	if err != nil {
		return fmt.Errorf("migrate: %w", err)
	}
	slog.Info("database migrations applied")
	return nil
}
