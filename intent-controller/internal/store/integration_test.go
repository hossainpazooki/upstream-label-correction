//go:build integration

package store

import (
	"context"
	"os"
	"testing"
	"time"

	"github.com/google/uuid"
	"github.com/precision-genomics/intent-controller/internal/models"
)

// TestFSMPersistenceParity is a runtime integration test that proves the intent
// finite-state-machine and its Postgres persistence agree at runtime. It is
// guarded by the `integration` build tag and is therefore excluded from the
// default `go test ./...` run (this machine has no Postgres).
//
// Run it explicitly against a live database with:
//
//	DATABASE_URL=postgresql://postgres:postgres@localhost:5432/precision_genomics \
//	    go test -tags=integration ./internal/store/...
func TestFSMPersistenceParity(t *testing.T) {
	connStr := os.Getenv("DATABASE_URL")
	if connStr == "" {
		t.Skip("DATABASE_URL not set; skipping Postgres integration test")
	}

	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()

	db, err := NewPostgres(ctx, connStr)
	if err != nil {
		t.Fatalf("NewPostgres: %v", err)
	}
	defer db.Close()

	if err := db.Migrate(ctx); err != nil {
		t.Fatalf("Migrate: %v", err)
	}

	repo := NewIntentRepo(db)

	// Unique id so concurrent/repeat runs do not collide.
	intentID := "itest-" + uuid.NewString()

	// Always clean up rows the test creates, even on failure.
	t.Cleanup(func() {
		cleanupCtx, cleanupCancel := context.WithTimeout(context.Background(), 10*time.Second)
		defer cleanupCancel()
		if _, err := db.Pool.Exec(cleanupCtx, `DELETE FROM intent_events WHERE intent_id = $1`, intentID); err != nil {
			t.Errorf("cleanup intent_events: %v", err)
		}
		if _, err := db.Pool.Exec(cleanupCtx, `DELETE FROM intents WHERE intent_id = $1`, intentID); err != nil {
			t.Errorf("cleanup intents: %v", err)
		}
	})

	// 1. Create an Intent in DECLARED and persist it.
	createdAt := time.Now().UTC().Truncate(time.Microsecond)
	intent := &models.Intent{
		IntentID:    intentID,
		IntentType:  "analysis",
		Status:      models.IntentStatusDeclared,
		Params:      map[string]interface{}{"cohort": "tcga-brca"},
		InfraState:  map[string]interface{}{},
		WorkflowIDs: []string{},
		EvalResults: map[string]interface{}{},
		CreatedAt:   createdAt,
		RequestedBy: "integration-test",
	}
	if err := repo.Create(ctx, intent); err != nil {
		t.Fatalf("Create intent: %v", err)
	}
	if intent.ID == 0 {
		t.Fatalf("Create did not populate generated ID")
	}

	// 2. Reload and assert key fields round-trip.
	reloaded, err := repo.GetByIntentID(ctx, intentID)
	if err != nil {
		t.Fatalf("GetByIntentID: %v", err)
	}
	if reloaded == nil {
		t.Fatalf("GetByIntentID returned nil for %s", intentID)
	}
	if reloaded.IntentID != intent.IntentID {
		t.Errorf("IntentID round-trip = %q, want %q", reloaded.IntentID, intent.IntentID)
	}
	if reloaded.IntentType != intent.IntentType {
		t.Errorf("IntentType round-trip = %q, want %q", reloaded.IntentType, intent.IntentType)
	}
	if reloaded.Status != models.IntentStatusDeclared {
		t.Errorf("Status round-trip = %q, want %q", reloaded.Status, models.IntentStatusDeclared)
	}
	if reloaded.RequestedBy != intent.RequestedBy {
		t.Errorf("RequestedBy round-trip = %q, want %q", reloaded.RequestedBy, intent.RequestedBy)
	}
	if got, ok := reloaded.Params["cohort"].(string); !ok || got != "tcga-brca" {
		t.Errorf("Params round-trip = %v, want cohort=tcga-brca", reloaded.Params)
	}
	if !reloaded.CreatedAt.Equal(createdAt) {
		t.Errorf("CreatedAt round-trip = %v, want %v", reloaded.CreatedAt, createdAt)
	}

	// 3. Walk a LEGAL happy path, persisting and reloading each step.
	//    DECLARED -> RESOLVING -> ACTIVE -> VERIFYING -> ACHIEVED.
	legalPath := []models.IntentStatus{
		models.IntentStatusResolving,
		models.IntentStatusActive,
		models.IntentStatusVerifying,
		models.IntentStatusAchieved,
	}
	current := reloaded
	for _, next := range legalPath {
		if !models.IsValidTransition(current.Status, next) {
			t.Fatalf("expected %s -> %s to be a legal transition", current.Status, next)
		}
		current.Status = next
		if err := repo.Update(ctx, current); err != nil {
			t.Fatalf("Update intent to %s: %v", next, err)
		}
		// Reload to prove the persisted FSM state matches the in-memory walk.
		current, err = repo.GetByIntentID(ctx, intentID)
		if err != nil {
			t.Fatalf("GetByIntentID after %s: %v", next, err)
		}
		if current == nil {
			t.Fatalf("intent %s vanished after transition to %s", intentID, next)
		}
		if current.Status != next {
			t.Errorf("persisted status after transition = %q, want %q", current.Status, next)
		}
	}
	if current.Status != models.IntentStatusAchieved {
		t.Errorf("final persisted status = %q, want %q", current.Status, models.IntentStatusAchieved)
	}

	// 4. Assert ILLEGAL transitions are rejected by the FSM before any
	//    persistence is attempted. BLOCKED -> ACTIVE is forbidden after gap
	//    #14.4 (blocked must re-resolve first); DECLARED -> ACTIVE skips
	//    resolution.
	illegal := []struct{ from, to models.IntentStatus }{
		{models.IntentStatusBlocked, models.IntentStatusActive},
		{models.IntentStatusDeclared, models.IntentStatusActive},
	}
	for _, c := range illegal {
		if models.IsValidTransition(c.from, c.to) {
			t.Errorf("expected %s -> %s to be rejected as illegal", c.from, c.to)
		}
	}
}
